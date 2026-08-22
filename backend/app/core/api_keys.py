"""Minting and recognising API keys.

An organization generates a key so its own tooling — n8n, Zapier, a script — can
reach Tarazu without a person signing in. The key belongs to that organization
and reaches nothing outside it.

**The raw key is never stored and never logged.** It exists in the response to
the call that created it, and after that only in the customer's secret store.
What is kept is:

- `key_prefix` — `trz_live_` plus the key's first eight random characters. Not a
  secret. It is what the UI shows so two keys can be told apart, and what the
  audit trail records as `api-key:<prefix>` so the trail names the key that
  acted.
- `key_hash` — SHA-256 of the whole key, hex. Authentication hashes the presented
  key and looks the digest up.

SHA-256 rather than a slow KDF is deliberate, and it is the opposite of the
advice for passwords. A password is low-entropy and guessable, so the cost of
each guess has to be raised. This key is 128 bits from `secrets.token_hex`:
there is nothing to guess, and a slow hash on the authentication path would only
buy an attacker a cheap way to exhaust the server.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

__all__ = [
    "KEY_SCHEME",
    "MintedApiKey",
    "hash_api_key",
    "looks_like_an_api_key",
    "mint_api_key",
]

#: Every key starts with this. `live` leaves room for a `trz_test_` scheme later
#: without the two ever being confusable, and the fixed head makes a leaked key
#: recognisable on sight — in a log, a paste, or a secret scanner's rules.
KEY_SCHEME = "trz_live_"

#: Bytes of randomness. `secrets.token_hex(16)` gives the 32 hex characters.
_SECRET_BYTES = 16

#: How much of the random part is public. Eight hex characters is 4 billion
#: possibilities — plenty to identify a key among an organization's handful,
#: and 96 bits short of being able to reconstruct one.
_PREFIX_CHARS = 8


@dataclass(frozen=True)
class MintedApiKey:
    """A freshly generated key, in the only moment it is whole.

    `raw` is handed to the caller once and then dropped. Only `prefix` and
    `key_hash` are persisted.
    """

    raw: str
    prefix: str
    key_hash: str


def hash_api_key(raw: str) -> str:
    """SHA-256 of a presented key, hex. The stored form, and the lookup key."""
    return hashlib.sha256(raw.strip().encode("utf-8")).hexdigest()


def mint_api_key() -> MintedApiKey:
    """Generate a new key: `trz_live_` plus 32 random hex characters."""
    secret = secrets.token_hex(_SECRET_BYTES)
    raw = f"{KEY_SCHEME}{secret}"
    return MintedApiKey(
        raw=raw,
        prefix=f"{KEY_SCHEME}{secret[:_PREFIX_CHARS]}",
        key_hash=hash_api_key(raw),
    )


def looks_like_an_api_key(value: str) -> bool:
    """Cheap shape check, before touching the database.

    Not a security control — a well-formed key is still rejected unless its
    digest is on file. It exists so that an obviously malformed header does not
    become a database round trip, and it must never be used to explain *why* a
    key was refused: every rejection says the same thing.
    """
    candidate = value.strip()
    if not candidate.startswith(KEY_SCHEME):
        return False
    secret = candidate[len(KEY_SCHEME) :]
    return len(secret) == _SECRET_BYTES * 2 and all(
        character in "0123456789abcdef" for character in secret.lower()
    )
