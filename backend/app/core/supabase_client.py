"""Supabase clients for Postgres (PostgREST), Storage, and Auth (GoTrue).

Plain `httpx` against the REST APIs rather than the `supabase` SDK: the SDK
would pull in a dependency tree for three endpoints we call by hand anyway, and
`httpx` is already here for the Qwen client.

**The audit-trail writer exposed through here is append-only by construction.**
There is no update helper and no delete helper, and the database refuses both
regardless — see the hardening section of `infra/supabase/schema.sql`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import Settings, get_settings

__all__ = ["SupabaseError", "SupabaseRest", "SupabaseStorage", "sign_in_with_password"]

logger = logging.getLogger(__name__)


class SupabaseError(RuntimeError):
    """Supabase rejected a request."""


class SupabaseRest:
    """A thin PostgREST client.

    Uses the service-role key: the backend is the only thing that talks to the
    database, and it enforces the audit trail itself. Row-level security still
    applies to everything the browser touches directly, and the `audit_trail`
    REVOKE applies to the service role too — that is the whole point of it.
    """

    def __init__(
        self, settings: Settings | None = None, http_client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        key = self.settings.supabase_service_role_key or ""
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def _url(self, table: str) -> str:
        return f"{self.settings.rest_url}/{table}"

    def _check(self, response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise SupabaseError(
                f"HTTP {response.status_code} from PostgREST: {response.text[:500]}"
            )
        if not response.content or response.status_code == 204:
            return None
        return response.json()

    def select(
        self,
        table: str,
        params: dict[str, str] | None = None,
    ) -> list[dict]:
        response = self._http.get(
            self._url(table), params={"select": "*", **(params or {})}, headers=self._headers
        )
        return self._check(response) or []

    def insert(self, table: str, rows: list[dict], upsert: bool = False) -> list[dict]:
        headers = dict(self._headers)
        headers["Prefer"] = (
            "return=representation,resolution=merge-duplicates"
            if upsert
            else "return=representation"
        )
        return self._check(self._http.post(self._url(table), json=rows, headers=headers)) or []

    def update(self, table: str, params: dict[str, str], values: dict) -> list[dict]:
        headers = dict(self._headers)
        headers["Prefer"] = "return=representation"
        return (
            self._check(
                self._http.patch(
                    self._url(table), params=params, json=values, headers=headers
                )
            )
            or []
        )

    def delete(self, table: str, params: dict[str, str]) -> None:
        # Deliberately not usable on audit_trail: the database refuses it. This
        # exists for clearing a case's review items before re-running matching.
        if table == "audit_trail":
            raise SupabaseError("audit_trail is append-only; it cannot be deleted from")
        self._check(self._http.delete(self._url(table), params=params, headers=self._headers))


class SupabaseStorage:
    """Client documents in a private Storage bucket."""

    def __init__(
        self, settings: Settings | None = None, http_client: httpx.Client | None = None
    ) -> None:
        self.settings = settings or get_settings()
        key = self.settings.supabase_service_role_key or ""
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0))
        self._auth = {"apikey": key, "Authorization": f"Bearer {key}"}
        self._bucket = self.settings.storage_bucket

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def put(self, path: str, content: bytes, content_type: str) -> str:
        response = self._http.post(
            f"{self.settings.storage_url}/object/{self._bucket}/{path}",
            content=content,
            headers={
                **self._auth,
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        if response.status_code >= 400:
            raise SupabaseError(
                f"HTTP {response.status_code} uploading {path}: {response.text[:300]}"
            )
        return path

    def get(self, path: str) -> bytes:
        response = self._http.get(
            f"{self.settings.storage_url}/object/{self._bucket}/{path}", headers=self._auth
        )
        if response.status_code >= 400:
            raise SupabaseError(
                f"HTTP {response.status_code} downloading {path}: {response.text[:300]}"
            )
        return response.content

    def signed_url(self, path: str, expires_in: int = 3600) -> str | None:
        """A short-lived URL for the browser. The bucket stays private."""
        response = self._http.post(
            f"{self.settings.storage_url}/object/sign/{self._bucket}/{path}",
            json={"expiresIn": expires_in},
            headers={**self._auth, "Content-Type": "application/json"},
        )
        if response.status_code >= 400:
            logger.warning("Could not sign %s: HTTP %s", path, response.status_code)
            return None
        signed = response.json().get("signedURL", "")
        return f"{self.settings.storage_url}{signed}" if signed else None


def sign_in_with_password(
    email: str,
    password: str,
    settings: Settings | None = None,
    http_client: httpx.Client | None = None,
) -> dict:
    """Exchange an email and password for a Supabase session (GoTrue).

    Raises:
        SupabaseError: The credentials were rejected.
    """
    settings = settings or get_settings()
    client = http_client or httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0))
    try:
        response = client.post(
            f"{settings.auth_url}/token",
            params={"grant_type": "password"},
            json={"email": email, "password": password},
            headers={
                "apikey": settings.supabase_anon_key or "",
                "Content-Type": "application/json",
            },
        )
        if response.status_code >= 400:
            raise SupabaseError(f"sign-in rejected: {response.text[:300]}")
        return response.json()
    finally:
        if http_client is None:
            client.close()
