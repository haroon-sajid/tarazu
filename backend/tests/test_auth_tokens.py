"""Token verification: both signing schemes, and the traps between them.

A Supabase project signs access tokens one of two ways. New projects use
asymmetric keys (ES256) and publish the public half at
`/auth/v1/.well-known/jwks.json`; older ones use HS256 with the project's shared
secret. Tarazu has to accept whichever its project uses, and — more importantly
— must not accept a token verified against the *wrong* key material.

The live project this was built against turned out to be ES256, which is how the
gap these tests cover was found: login succeeded and every authenticated call
then returned `401`, because `verify_token` only ever tried HS256.

No network here. The ES256 key is generated in-process and the JWKS client is
pointed at it, so what is exercised is the dispatch and the verification, not
Supabase's uptime.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.core.auth import (
    TOKEN_AUDIENCE,
    AuthenticatedUser,
    issue_local_token,
    reset_jwks_cache,
    verify_token,
)
from app.core.config import Settings, get_settings

USER_ID = "d60f2dfc-6709-4e7c-8401-3a860cb99629"


def supabase_settings(**overrides) -> Settings:
    """A Settings that believes it is talking to a project, without one existing."""
    base = get_settings()
    return Settings(
        **{
            **base.__dict__,
            "supabase_url": "https://example-project.supabase.co",
            "supabase_service_role_key": "sb_secret_example",
            "supabase_jwt_secret": "the-legacy-shared-secret",
            **overrides,
        }
    )


def claims(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "sub": USER_ID,
        "email": "auditor@tarazu.local",
        "aud": TOKEN_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=1)).timestamp()),
        **overrides,
    }


@pytest.fixture()
def es256_key():
    """A P-256 keypair, the shape Supabase issues by default."""
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture()
def jwks_project(monkeypatch, es256_key):
    """A project whose JWKS serves `es256_key`, with no network involved."""
    reset_jwks_cache()

    class FakeSigningKey:
        key = es256_key.public_key()

    class FakeJWKClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get_signing_key_from_jwt(self, token):
            return FakeSigningKey()

    monkeypatch.setattr("app.core.auth._jwks_client", lambda url: FakeJWKClient())
    # No reset on teardown: monkeypatch restores the real, still-empty cache
    # after this fixture finalises, and calling cache_clear() on the stand-in
    # would fail because a plain lambda has no cache to clear.
    yield supabase_settings()


# --------------------------------------------------------------------------- #
# Asymmetric (ES256) — what a new Supabase project issues
# --------------------------------------------------------------------------- #


def test_an_es256_token_is_accepted(jwks_project, es256_key) -> None:
    token = jwt.encode(claims(), es256_key, algorithm="ES256")

    user = verify_token(token, jwks_project)

    assert user == AuthenticatedUser(user_id=USER_ID, email="auditor@tarazu.local")


def test_an_es256_token_signed_by_a_different_key_is_refused(jwks_project) -> None:
    """The signature is checked, not merely parsed."""
    impostor = ec.generate_private_key(ec.SECP256R1())
    token = jwt.encode(claims(), impostor, algorithm="ES256")

    with pytest.raises(HTTPException) as raised:
        verify_token(token, jwks_project)
    assert raised.value.status_code == 401


def test_an_expired_es256_token_is_refused(jwks_project, es256_key) -> None:
    past = datetime.now(timezone.utc) - timedelta(hours=2)
    token = jwt.encode(
        claims(exp=int(past.timestamp()), iat=int((past - timedelta(hours=1)).timestamp())),
        es256_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as raised:
        verify_token(token, jwks_project)
    assert raised.value.status_code == 401
    assert "expired" in raised.value.detail.lower()


def test_an_es256_token_for_the_wrong_audience_is_refused(jwks_project, es256_key) -> None:
    token = jwt.encode(claims(aud="anon"), es256_key, algorithm="ES256")

    with pytest.raises(HTTPException) as raised:
        verify_token(token, jwks_project)
    assert raised.value.status_code == 401


def test_a_token_with_no_subject_is_refused(jwks_project, es256_key) -> None:
    """`sub` is what lands in the audit trail. A token without one is useless."""
    payload = claims()
    del payload["sub"]
    token = jwt.encode(payload, es256_key, algorithm="ES256")

    with pytest.raises(HTTPException) as raised:
        verify_token(token, jwks_project)
    assert raised.value.status_code == 401


# --------------------------------------------------------------------------- #
# The algorithm-confusion trap
# --------------------------------------------------------------------------- #


def test_the_public_key_cannot_be_used_as_an_hmac_secret(jwks_project, es256_key) -> None:
    """The classic attack on servers that pick the key from the token's `alg`.

    An attacker who has the (public!) verification key signs an HS256 token with
    it, hoping the server will hand that same key back to an HMAC verifier.
    Tarazu maps HS256 to the shared secret and nothing else, so the forgery is
    checked against material the attacker does not have, and fails.

    The token is assembled by hand because PyJWT refuses to *encode* HS256 with
    a PEM key — a good guard, and one an attacker writing raw bytes does not
    have to respect. This is the attack as it would actually arrive.
    """
    public_pem = es256_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def b64(raw: bytes) -> bytes:
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    signing_input = b".".join(
        (
            b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()),
            b64(json.dumps(claims()).encode()),
        )
    )
    signature = hmac.new(public_pem, signing_input, hashlib.sha256).digest()
    forged = (signing_input + b"." + b64(signature)).decode()

    with pytest.raises(HTTPException) as raised:
        verify_token(forged, jwks_project)
    assert raised.value.status_code == 401


def test_the_none_algorithm_is_refused(jwks_project) -> None:
    unsigned = jwt.encode(claims(), key="", algorithm="none")

    with pytest.raises(HTTPException) as raised:
        verify_token(unsigned, jwks_project)
    assert raised.value.status_code == 401


# --------------------------------------------------------------------------- #
# Symmetric (HS256) — legacy projects, and the local store
# --------------------------------------------------------------------------- #


def test_a_legacy_hs256_project_token_is_accepted() -> None:
    settings = supabase_settings()
    token = jwt.encode(claims(), settings.supabase_jwt_secret, algorithm="HS256")

    assert verify_token(token, settings).user_id == USER_ID


def test_an_hs256_token_signed_with_the_wrong_secret_is_refused() -> None:
    settings = supabase_settings()
    token = jwt.encode(claims(), "not-the-projects-secret", algorithm="HS256")

    with pytest.raises(HTTPException) as raised:
        verify_token(token, settings)
    assert raised.value.status_code == 401


def test_a_local_token_round_trips() -> None:
    """Local mode signs and verifies with LOCAL_JWT_SECRET, no project needed."""
    settings = get_settings()
    assert not settings.uses_supabase

    token, expires_in = issue_local_token(USER_ID, "auditor@tarazu.local", settings)

    assert expires_in > 0
    assert verify_token(token, settings).user_id == USER_ID


def test_a_local_token_is_not_accepted_by_a_supabase_deployment() -> None:
    """A developer's local token must not open a door on a deployed instance."""
    local = get_settings()
    token, _ = issue_local_token(USER_ID, "auditor@tarazu.local", local)

    with pytest.raises(HTTPException) as raised:
        verify_token(token, supabase_settings())
    assert raised.value.status_code == 401


def test_a_supabase_deployment_without_a_jwt_secret_says_so() -> None:
    """A misconfiguration is a 500, not a silent 401 that looks like bad input."""
    settings = supabase_settings(supabase_jwt_secret=None)
    token = jwt.encode(claims(), "anything", algorithm="HS256")

    with pytest.raises(HTTPException) as raised:
        verify_token(token, settings)
    assert raised.value.status_code == 500
    assert "SUPABASE_JWT_SECRET" in raised.value.detail


def test_the_jwks_url_is_where_supabase_publishes_keys() -> None:
    settings = supabase_settings()
    assert settings.jwks_url == (
        "https://example-project.supabase.co/auth/v1/.well-known/jwks.json"
    )
