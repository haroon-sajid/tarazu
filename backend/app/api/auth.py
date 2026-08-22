"""`POST /v1/auth/signup` and `POST /v1/auth/login`.

Signup is what makes a tenant. It creates the user, creates the organization
that user's firm will own, and adds them to it as `owner` — one call, because a
user with no organization has nowhere to put a case and every other route would
refuse them.

The organization id is minted here and never accepted from the client. A signup
body that could name its own `org_id` would be a signup that could join someone
else's firm.

Two identity providers, selected by whether Supabase is configured:

- **Supabase** — users live in `auth.users`; signup goes to the GoTrue admin API
  and login exchanges the password for a project JWT.
- **Local** — the SQLite store is its own identity provider (see
  `core.repository.IdentityStore`), so two firms and two users can be run end to
  end with no network. `scripts/demo_tenant_isolation.py` does exactly that.

The seeded demo auditor keeps working either way: they are joined to the default
organization on their first authenticated request (`app.api.deps.get_principal`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import Field

from app.api.deps import get_repository
from app.core.auth import issue_local_token
from app.core.config import Settings, get_settings
from app.core.repository import CaseRepository, IdentityStore
from app.core.supabase_client import SupabaseError, sign_in_with_password
from app.shared.schemas import Organization, OrganizationMember, OrgRole, TarazuModel

router = APIRouter(tags=["auth"])
logger = logging.getLogger(__name__)


class LoginRequest(TarazuModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class SignupRequest(TarazuModel):
    """A new firm and its first user.

    Note what is absent: any way to name an `org_id`. The organization this
    creates is new, and the caller is its owner.
    """

    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    organization_name: str = Field(min_length=1, max_length=200)


class LoginResponse(TarazuModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str | None = None


class SignupResponse(TarazuModel):
    """The identity and the tenant that now exist. No token: sign in next."""

    user_id: str
    email: str
    org_id: str
    organization_name: str
    role: OrgRole


def _local_identity(repository: CaseRepository) -> IdentityStore:
    """The local store as an identity provider, or a clear 503 if it is not one."""
    if not isinstance(repository, IdentityStore):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Supabase is not configured and this store cannot hold identities. "
                "Set SUPABASE_URL and its keys, or run on the local SQLite store."
            ),
        )
    return repository


def _create_supabase_user(email: str, password: str, settings: Settings) -> str:
    """Create a confirmed user through the GoTrue admin API. Returns its id."""
    key = settings.supabase_service_role_key or ""
    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            f"{settings.auth_url}/admin/users",
            json={"email": email, "password": password, "email_confirm": True},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        # 422 from GoTrue is "already registered". Everything else is ours.
        if response.status_code in (409, 422):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists for that email address.",
            )
        logger.error("GoTrue rejected a signup: %s", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The identity provider refused the signup.",
        )
    return str(response.json()["id"])


@router.post(
    "/auth/signup",
    response_model=SignupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and the organization it owns",
)
async def signup(
    body: SignupRequest,
    settings: Settings = Depends(get_settings),
    repository: CaseRepository = Depends(get_repository),
) -> SignupResponse:
    """Create a user, create their organization, and make them its owner.

    The three happen together because none of them is useful alone: a user with
    no organization cannot open a case, and an organization with no owner cannot
    be reached by anybody.
    """
    email = body.email.strip()

    if settings.uses_supabase:
        user_id = _create_supabase_user(email, body.password, settings)
    else:
        identity = _local_identity(repository)
        try:
            user_id = identity.create_user(email, body.password)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account already exists for that email address.",
            ) from None

    now = datetime.now(timezone.utc)
    organization = Organization(
        org_id=str(uuid4()), name=body.organization_name.strip(), created_at=now
    )
    repository.create_organization(organization)
    repository.add_member(
        OrganizationMember(
            org_id=organization.org_id,
            user_id=user_id,
            role=OrgRole.OWNER,
            created_at=now,
        )
    )
    logger.info("New organization %s created by %s", organization.org_id, user_id)

    return SignupResponse(
        user_id=user_id,
        email=email,
        org_id=organization.org_id,
        organization_name=organization.name,
        role=OrgRole.OWNER,
    )


@router.post("/auth/login", response_model=LoginResponse, summary="Sign in")
async def login(
    body: LoginRequest,
    settings: Settings = Depends(get_settings),
    repository: CaseRepository = Depends(get_repository),
) -> LoginResponse:
    """Exchange an email and password for an access token.

    Send the token back as `Authorization: Bearer <token>` on every other call.
    The token identifies the user; the organization is resolved from their
    membership on each request and is never carried in the token.
    """
    if settings.uses_supabase:
        try:
            session = sign_in_with_password(body.email, body.password, settings)
        except SupabaseError:
            # Never echo the provider's message: it distinguishes "no such user"
            # from "wrong password", which is an account-enumeration leak.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password.",
            ) from None

        user = session.get("user") or {}
        return LoginResponse(
            access_token=session["access_token"],
            expires_in=int(session.get("expires_in", 3600)),
            user_id=str(user.get("id", "")),
            email=user.get("email"),
        )

    identity = _local_identity(repository)
    user_id = identity.verify_password(body.email, body.password)
    if user_id is None:
        # Identical whether the email exists or not, for the same reason.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    token, expires_in = issue_local_token(user_id, body.email.strip(), settings)
    return LoginResponse(
        access_token=token,
        expires_in=expires_in,
        user_id=user_id,
        email=body.email.strip(),
    )
