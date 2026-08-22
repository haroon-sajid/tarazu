"""FastAPI dependencies: the repository, the document store, the caller, the case.

One process-wide repository and document store, chosen once from settings.
`SUPABASE_URL` selects Supabase; without it the app runs on SQLite and the
filesystem. Everything above this line is written against the protocols in
`core/repository.py` and cannot tell the difference.

**`get_principal` is where both authentication and tenancy are decided, and it
is the only place.** A request arrives one of two ways:

- `Authorization: Bearer <jwt>` — a person. Their organization is the one their
  `user_id` is a member of.
- `X-API-Key: trz_live_...` — a machine: n8n, Zapier, the customer's own code.
  Its organization is the one the key was created in.

Either way the client never supplies an org id, and no route accepts one: an org
id that arrived in a request body, a query string, or a token claim would be an
authorisation decision made by the caller. Every repository call below this
dependency is scoped to what `get_principal` returns.

When both credentials are present the API key wins, and the `Authorization`
header is ignored. That is a choice, not an accident: an ambiguous request
should resolve the same way every time, and a stale session cookie or proxy
header must never silently upgrade a machine's request to a person's.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import Depends, HTTPException, Query, Request, status

from app.core.api_keys import hash_api_key, looks_like_an_api_key
from app.core.audit import Actor
from app.core.auth import AuthenticatedUser, current_user
from app.core.config import Settings, get_settings
from app.core.repository import CaseRepository, DocumentStore
from app.core.sqlite_store import LocalDocumentStore, SqliteCaseRepository
from app.core.supabase_client import SupabaseRest, SupabaseStorage
from app.core.supabase_store import SupabaseCaseRepository
from app.shared.schemas import (
    ApiKeyRecord,
    ApiKeyScope,
    Organization,
    OrganizationMember,
    OrgRole,
)

__all__ = [
    "API_KEY_HEADER",
    "Principal",
    "get_case_id",
    "get_principal",
    "get_repository",
    "get_storage",
    "human_only",
    "require_read",
    "require_write",
    "reset_backends",
]

logger = logging.getLogger(__name__)

#: The header a machine presents. Named for the convention every integration
#: tool already knows: n8n's "Header Auth" and Zapier's API-key auth both send
#: exactly this shape with no extra configuration.
API_KEY_HEADER = "X-API-Key"

#: What a signed-in person may do. A human is not scope-limited: scopes exist to
#: restrain a credential that gets pasted into someone else's workflow builder,
#: not to restrain the auditor who owns the account.
ALL_SCOPES = frozenset(ApiKeyScope)


@dataclass(frozen=True)
class Principal:
    """Who is making this request, and which organization they are inside.

    One object for both kinds of caller, so a route never branches on how the
    request was authenticated — it asks for the scope it needs, uses `org_id`
    for every read and write, and hands `actor` to the audit writer.
    """

    org_id: str
    role: OrgRole
    scopes: frozenset[ApiKeyScope]
    #: The accountable person: the signed-in user, or the user who created the
    #: key. Lands in `cases.created_by` and `review_items.decided_by`.
    user_id: str
    #: How the audit trail will name this caller.
    actor: Actor
    #: Present only for a machine. Its `key_prefix` is what the trail records.
    api_key: ApiKeyRecord | None = None

    @property
    def is_api_key(self) -> bool:
        return self.api_key is not None

    def allows(self, scope: ApiKeyScope) -> bool:
        return scope in self.scopes


@lru_cache(maxsize=1)
def _backends() -> tuple[CaseRepository, DocumentStore]:
    settings = get_settings()
    if settings.uses_supabase:
        logger.info("Persistence: Supabase at %s", settings.supabase_url)
        return SupabaseCaseRepository(SupabaseRest(settings)), SupabaseStorage(settings)

    logger.warning(
        "SUPABASE_URL is not set: running on the local SQLite store at %s. "
        "Set the Supabase variables before deploying.",
        settings.local_database_path,
    )
    return (
        SqliteCaseRepository(settings.local_database_path, settings.default_org_id),
        LocalDocumentStore(settings.local_storage_path),
    )


def reset_backends() -> None:
    """Drop the cached backends. For tests, and after changing the environment."""
    _backends.cache_clear()


def get_repository() -> CaseRepository:
    return _backends()[0]


def get_storage() -> DocumentStore:
    return _backends()[1]


def ensure_default_org(repository: CaseRepository, settings: Settings) -> Organization:
    """Create the default organization if it is not there yet, and return it.

    The seeded demo auditor predates tenancy, so there is nowhere for their
    signup to have created an organization. This is that organization: the same
    id the SQL migration backfills existing rows into.
    """
    existing = repository.get_organization(settings.default_org_id)
    if existing is not None:
        return existing
    organization = Organization(
        org_id=settings.default_org_id,
        name=settings.default_org_name,
        created_at=datetime.now(timezone.utc),
    )
    repository.create_organization(organization)
    return organization


#: Every rejection of a presented API key says exactly this. Unknown, malformed,
#: and revoked are one answer on purpose: telling a caller that their key is
#: "revoked" rather than "unknown" confirms it was once real, which is a probe
#: worth denying.
_BAD_KEY = "Invalid or revoked API key."


def _principal_from_api_key(
    presented: str, repository: CaseRepository
) -> Principal:
    """Authenticate a machine. Never logs, echoes, or stores the presented key."""
    if not looks_like_an_api_key(presented):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_KEY
        )

    key = repository.find_api_key_by_hash(hash_api_key(presented))
    if key is None or not key.is_active:
        # One branch, one message, whichever of the two it was.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_KEY
        )

    # Best-effort: "when was this key last used" is an operational nicety, and
    # losing it must never turn a working integration into a 500.
    try:
        repository.touch_api_key(key.key_id, datetime.now(timezone.utc))
    except Exception:  # noqa: BLE001 - deliberately swallowed, see above
        logger.warning("Could not record last_used_at for key %s", key.key_prefix)

    return Principal(
        org_id=key.org_id,
        # A key acts with the standing of the organization, not of a seat in it.
        # Role is what a future member-management screen checks; a key is never
        # the thing that manages members or other keys.
        role=OrgRole.MEMBER,
        scopes=frozenset(key.scopes),
        user_id=key.created_by,
        actor=Actor.api_key(key.key_prefix, key.created_by),
        api_key=key,
    )


def _principal_from_user(
    user: AuthenticatedUser, repository: CaseRepository, settings: Settings
) -> Principal:
    """Authenticate a person, and resolve which organization they are in.

    From the caller's verified `user_id` and nothing else. A user with no
    membership gets `403` and no data — they are authenticated but not a tenant
    of anything, which is a different thing from asking for someone else's case
    (that is a `404`, because a row outside your organization does not exist as
    far as you are concerned).

    The one exception is the seeded demo auditor, who is joined to the default
    organization on first use so the demo keeps working across a store that was
    created before organizations existed.
    """
    membership = repository.get_membership(user.user_id)
    if membership is None and user.user_id == settings.dev_user_id:
        ensure_default_org(repository, settings)
        membership = OrganizationMember(
            org_id=settings.default_org_id,
            user_id=user.user_id,
            role=OrgRole.OWNER,
            created_at=datetime.now(timezone.utc),
        )
        repository.add_member(membership)
        logger.info(
            "Joined the seeded demo auditor to the default organization %s",
            settings.default_org_id,
        )

    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Your account does not belong to an organization. "
                "Create one at POST /v1/auth/signup, or ask an owner to add you."
            ),
        )
    return Principal(
        org_id=membership.org_id,
        role=membership.role,
        scopes=ALL_SCOPES,
        user_id=user.user_id,
        actor=Actor.human(user.user_id),
    )


def get_principal(
    request: Request,
    repository: CaseRepository = Depends(get_repository),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Authenticate this request and resolve the organization it acts inside.

    An `X-API-Key` header makes this a machine's request and is used on its own;
    otherwise the usual token (or the development user) applies. Both paths end
    at the same `Principal`, so nothing downstream has to care which happened.
    """
    presented = request.headers.get(API_KEY_HEADER, "").strip()
    if presented:
        return _principal_from_api_key(presented, repository)
    return _principal_from_user(current_user(request, settings), repository, settings)


def _requires(scope: ApiKeyScope):
    """Build a dependency that admits only callers holding `scope`.

    A person holds every scope. A key holds what it was granted, so a read-only
    key reaching an approve route is `403` — it is a real credential for a real
    organization, and there is no resource to conceal by pretending otherwise.
    """

    def dependency(principal: Principal = Depends(get_principal)) -> Principal:
        if principal.allows(scope):
            return principal
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"This API key does not have the {scope.value!r} scope. "
                f"It was created with {[s.value for s in sorted(principal.scopes, key=lambda s: s.value)]}. "
                "Create a new key with the scope you need; scopes are fixed for a key's lifetime."
            ),
        )

    return dependency


#: Guards every GET.
require_read = _requires(ApiKeyScope.READ)
#: Guards upload, approve, and reject.
require_write = _requires(ApiKeyScope.WRITE)


def human_only(principal: Principal = Depends(get_principal)) -> Principal:
    """Admit signed-in people only. Guards the key-management routes.

    **A key cannot mint, list, or revoke a key.** A credential that can issue
    credentials turns one leaked key into permanent access, and turns revocation
    into something the attacker can undo. Managing keys stays with a person
    holding a session.
    """
    if principal.is_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "API keys cannot manage API keys. Sign in at POST /v1/auth/login "
                "and use the access token for this route."
            ),
        )
    return principal


def get_case_id(
    case_id: str | None = Query(
        default=None, description="Defaults to your most recent case."
    ),
    principal: Principal = Depends(get_principal),
    repository: CaseRepository = Depends(get_repository),
) -> str:
    """Resolve which case a request is about, within the caller's organization.

    The review screen and the dashboard are always about one case. Rather than
    make the frontend track that before it has uploaded anything, an absent
    `case_id` means "the most recent one".

    A `case_id` belonging to another organization is `404`, identically to one
    that was never created — the lookup is filtered by `org_id`, so this code
    cannot tell the two apart either, and therefore cannot leak the difference.

    For an integration, "most recent" means the most recent case belonging to
    the person whose key it is, falling back to the organization's. That keeps a
    key polling `GET /v1/review-items` pointed at the same place a person would
    see, rather than at whichever colleague uploaded last.
    """
    resolved = case_id or repository.latest_case_id(principal.org_id, principal.user_id)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No cases yet. Upload documents at POST /v1/upload to start one.",
        )
    if repository.get_case(principal.org_id, resolved) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No case with id {resolved!r}."
        )
    return resolved
