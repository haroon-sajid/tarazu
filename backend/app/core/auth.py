"""Access-token verification, and token issuance for the local store.

A user signs up at `POST /v1/auth/signup`, signs in at `POST /v1/auth/login`,
stores the returned access token, and sends it as `Authorization: Bearer
<token>`. This module verifies it and turns it into an `AuthenticatedUser`,
whose `user_id` is what lands in the audit trail and what the caller's
organization is resolved from.

**A token says who you are. It never says which tenant you are in.** Tenancy is
resolved server-side from `organization_members` (see
`app.api.deps.get_principal`), so no claim a client can influence decides
which firm's data a request touches.

Two token issuers, selected by whether Supabase is configured:

- **Supabase** — project JWTs. Which algorithm depends on the project, and both
  are supported:

  - **Asymmetric (ES256, RS256, EdDSA)** — the modern default. The project
    publishes its public keys at `/auth/v1/.well-known/jwks.json`, and the token
    header's `kid` says which one signed it. Nothing secret is involved in
    verification, which is the point: a compromised backend cannot mint tokens.
  - **HS256** — the legacy scheme, symmetric, using `SUPABASE_JWT_SECRET`
    (Project Settings → API → JWT Settings).

  The algorithm is read from the token header and mapped to the right key —
  never the other way round. HS256 always means the shared secret and never a
  JWKS public key, which is what closes the classic confusion attack where a
  token is signed with a public key used as an HMAC secret.

- **Local** — the SQLite store is its own identity provider, so the whole
  multi-tenant flow can be run end to end without a network. Tokens are signed
  with `LOCAL_JWT_SECRET` and carry the same claims Supabase's do: `sub`,
  `email`, `aud`, `exp`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.core.config import Settings, get_settings

__all__ = [
    "AuthenticatedUser",
    "current_user",
    "issue_local_token",
    "reset_jwks_cache",
    "verify_token",
]

logger = logging.getLogger(__name__)

#: The audience claim both issuers use, matching Supabase's.
TOKEN_AUDIENCE = "authenticated"

#: Symmetric. Verified with a shared secret this process holds.
SYMMETRIC_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})

#: Asymmetric. Verified with a public key fetched from the project's JWKS.
ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "ES384", "ES512", "RS256", "RS384",
                                   "RS512", "PS256", "PS384", "PS512", "EdDSA"})


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> "jwt.PyJWKClient":
    """One client per project, caching keys between requests.

    `PyJWKClient` keeps the fetched keys in memory and refetches when it meets a
    `kid` it does not know, which is what makes key rotation a non-event: the
    first token signed by the new key triggers one fetch, and nothing needs
    redeploying.
    """
    return jwt.PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)


def reset_jwks_cache() -> None:
    """Drop cached signing keys. For tests, and after changing the project."""
    _jwks_client.cache_clear()


@dataclass(frozen=True)
class AuthenticatedUser:
    """Who is making this request. `user_id` is what lands in the audit trail."""

    user_id: str
    email: str | None = None
    #: True when this identity came from AUTH_ALLOW_DEV_USER, not a real token.
    is_dev_user: bool = False


def _symmetric_secret(settings: Settings) -> str:
    """The shared secret this deployment's HS256 tokens are signed with.

    With Supabase configured that is the project's JWT secret and nothing else:
    the local secret is never accepted, so a token minted by a developer's local
    run cannot be presented to a deployed instance.
    """
    if settings.uses_supabase:
        if not settings.supabase_jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_JWT_SECRET is not configured, so tokens cannot be verified.",
            )
        return settings.supabase_jwt_secret
    return settings.local_jwt_secret


def _verification_key(token: str, settings: Settings) -> tuple[object, list[str]]:
    """The key and the algorithm allow-list for this particular token.

    The token's own header chooses which *branch* is taken, and the branch
    chooses the key. A token claiming `alg: HS256` is checked against the shared
    secret; one claiming `ES256` is checked against the project's published
    public key. Neither can be verified with the other's material, so declaring
    a different algorithm gains an attacker nothing.
    """
    try:
        algorithm = jwt.get_unverified_header(token).get("alg", "")
    except jwt.InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {error}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    if algorithm in ASYMMETRIC_ALGORITHMS and settings.uses_supabase:
        try:
            key = _jwks_client(settings.jwks_url).get_signing_key_from_jwt(token).key
        except Exception as error:  # noqa: BLE001 - network, parse, or unknown kid
            logger.warning("Could not resolve a signing key from the JWKS: %s", error)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This token's signing key could not be verified.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        return key, [algorithm]

    if algorithm in SYMMETRIC_ALGORITHMS:
        return _symmetric_secret(settings), ["HS256"]

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=f"Unsupported token algorithm: {algorithm!r}.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def issue_local_token(user_id: str, email: str | None, settings: Settings) -> tuple[str, int]:
    """Mint an access token for the local store. Returns `(token, expires_in)`.

    Only reachable when Supabase is not configured; with Supabase configured,
    GoTrue issues the token and this is never called.
    """
    expires_in = settings.local_token_ttl_seconds
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "aud": TOKEN_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        },
        settings.local_jwt_secret,
        algorithm="HS256",
    )
    return token, expires_in


def verify_token(token: str, settings: Settings) -> AuthenticatedUser:
    """Verify an access token and return the user it identifies.

    Raises:
        HTTPException: 401 if the token is missing a subject, expired, or not
            signed by this deployment's issuer.
    """
    key, algorithms = _verification_key(token, settings)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            audience=TOKEN_AUDIENCE,
            options={"require": ["sub", "exp"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid access token: {error}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return AuthenticatedUser(user_id=str(claims["sub"]), email=claims.get("email"))


def current_user(
    request: Request, settings: Settings = Depends(get_settings)
) -> AuthenticatedUser:
    """FastAPI dependency: the authenticated user for this request.

    Every route except `/health`, `/v1/auth/login`, and `/v1/auth/signup`
    depends on this, so no action can reach the audit trail without an identity
    attached to it — and, through `get_principal`, without a tenant.

    When `AUTH_ALLOW_DEV_USER=true` and no token is presented, this yields the
    fixed development user instead. That switch defaults to off and must stay
    off anywhere the app is deployed — a warning is logged every time it is used.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")

    if token and scheme.lower() == "bearer":
        return verify_token(token, settings)

    if settings.allow_dev_user:
        logger.warning(
            "AUTH_ALLOW_DEV_USER is on: serving %s as the development user. "
            "This must be off in any deployed environment.",
            request.url.path,
        )
        return AuthenticatedUser(
            user_id=settings.dev_user_id,
            email=settings.demo_user_email,
            is_dev_user=True,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Sign in at POST /v1/auth/login and send the access token as a Bearer header.",
        headers={"WWW-Authenticate": "Bearer"},
    )
