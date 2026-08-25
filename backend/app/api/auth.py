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

from app.api.deps import Principal, get_repository, human_only
from app.core.auth import AuthenticatedUser, current_user, issue_local_token
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
    """A new user — founding a firm, or joining one by invitation.

    Note what is absent: any way to name an `org_id`. Without `invite_code`
    the organization this creates is new and the caller is its owner. With
    one, the caller joins the organization the code was cut for, with the
    role the owner chose — the code names the org, never the client.
    """

    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    #: Required when founding a firm; ignored when joining one by code.
    organization_name: str | None = Field(default=None, max_length=200)
    #: A single-use join code from an owner (`POST /v1/members/invites`).
    invite_code: str | None = Field(default=None, max_length=40)


class LoginResponse(TarazuModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    email: str | None = None


class ChangePasswordRequest(TarazuModel):
    """The current password proves possession; the new one replaces it."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class ChangePasswordResponse(TarazuModel):
    message: str


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
    """Create a user, then found an organization — or join one by invitation.

    Founding: user, organization, and ownership happen together because none
    is useful alone. Joining: a valid, unused invite code names the
    organization and the role; the code is checked *before* the identity is
    created, so a bad code never leaves an orphaned user behind.
    """
    email = body.email.strip()

    invitation = None
    if body.invite_code and body.invite_code.strip():
        invitation = repository.find_invitation_by_code(body.invite_code.strip())
        if invitation is None or invitation.accepted_at is not None:
            # Used and unknown read the same: a code is single-use, and saying
            # which failure this was would confirm a code once existed.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That invite code is not valid. Ask the owner for a new invitation.",
            )
    elif not (body.organization_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="organization_name is required when signing up without an invite code.",
        )

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

    if invitation is not None:
        repository.add_member(
            OrganizationMember(
                org_id=invitation.org_id,
                user_id=user_id,
                role=invitation.role,
                created_at=now,
            )
        )
        repository.accept_invitation(invitation.invite_id, user_id, now)
        joined = repository.get_organization(invitation.org_id)
        logger.info(
            "User %s joined organization %s via invitation %s",
            user_id,
            invitation.org_id,
            invitation.invite_id,
        )
        return SignupResponse(
            user_id=user_id,
            email=email,
            org_id=invitation.org_id,
            organization_name=joined.name if joined else "Your firm",
            role=invitation.role,
        )

    organization = Organization(
        org_id=str(uuid4()),
        name=(body.organization_name or "").strip(),
        created_at=now,
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


def _set_supabase_password(user_id: str, new_password: str, settings: Settings) -> None:
    """Replace a user's password through the GoTrue admin API."""
    key = settings.supabase_service_role_key or ""
    with httpx.Client(timeout=30.0) as client:
        response = client.put(
            f"{settings.auth_url}/admin/users/{user_id}",
            json={"password": new_password},
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        logger.error("GoTrue rejected a password change: %s", response.status_code)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The identity provider refused the password change.",
        )


#: One message for a wrong current password, however it was wrong.
_BAD_CURRENT_PASSWORD = "The current password is incorrect."


@router.post(
    "/auth/change-password",
    response_model=ChangePasswordResponse,
    summary="Change the signed-in user's password",
)
async def change_password(
    body: ChangePasswordRequest,
    principal: Principal = Depends(human_only),
    user: AuthenticatedUser = Depends(current_user),
    settings: Settings = Depends(get_settings),
    repository: CaseRepository = Depends(get_repository),
) -> ChangePasswordResponse:
    """Replace the caller's own password, after proving they hold the current one.

    Only a signed-in person can reach this (`human_only`): an API key that could
    rotate its creator's password would turn one leaked key into a stolen
    account. Requiring the current password means a walked-away-from browser is
    not enough to lock the owner out.

    Tokens already issued stay valid until they expire — a token says who you
    are, and who you are has not changed. Neither password is ever logged.
    """
    if user.is_dev_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The development user has no password to change.",
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The new password must be different from the current one.",
        )

    if settings.uses_supabase:
        if not user.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This account's email could not be resolved from the session.",
            )
        try:
            sign_in_with_password(user.email, body.current_password, settings)
        except SupabaseError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_BAD_CURRENT_PASSWORD,
            ) from None
        _set_supabase_password(user.user_id, body.new_password, settings)
    else:
        identity = _local_identity(repository)
        email = identity.get_user_email(principal.user_id)
        if email is None or identity.verify_password(email, body.current_password) is None:
            # One answer whether the account has no local password record or
            # the password was wrong — the caller learns nothing either way.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_BAD_CURRENT_PASSWORD,
            )
        identity.set_password(principal.user_id, body.new_password)

    logger.info("Password changed for user %s", principal.user_id)
    return ChangePasswordResponse(
        message=(
            "Password changed. Sessions that are already signed in stay valid "
            "until they expire; new sign-ins need the new password."
        )
    )
