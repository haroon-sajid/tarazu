"""Create the demo auditor in Supabase Auth, and put them in the default firm.

Everybody else signs themselves up at `POST /v1/auth/signup`, which creates a
user, creates their organization, and makes them its owner. The demo auditor
predates all of that and is referenced by `AUTH_DEV_USER_ID` and by the tenancy
migration's backfill, so it is seeded here instead.

Run it from the repo root, with `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`DEMO_USER_EMAIL`, and `DEMO_USER_PASSWORD` set::

    python scripts/seed_demo_user.py

It prints the user's UUID. Put that in `AUTH_DEV_USER_ID` so the local SQLite
store and Supabase agree on who the demo auditor is.

The dashboard equivalent is Authentication → Users → Add user, with "Auto
confirm user" ticked — but that half does not create the membership, so run
this script, or add the `organization_members` row by hand afterwards.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import Settings, get_settings  # noqa: E402


def join_default_org(
    client: httpx.Client, headers: dict, settings: Settings, user_id: str
) -> None:
    """Put the demo auditor in the default organization, creating it if needed.

    The same `org_id` `infra/supabase/0002-organizations.sql` backfills existing
    rows into. Without this row the demo auditor is authenticated but a member
    of nothing, and every route answers `403`.

    Both writes go through PostgREST with the service role, and both are
    upserts, so running this script twice changes nothing.
    """
    rest = f"{settings.supabase_url.rstrip('/')}/rest/v1"
    upsert = {**headers, "Prefer": "resolution=merge-duplicates,return=minimal"}

    organization = client.post(
        f"{rest}/organizations",
        json=[{"org_id": settings.default_org_id, "name": settings.default_org_name}],
        headers=upsert,
    )
    membership = client.post(
        f"{rest}/organization_members",
        json=[{"org_id": settings.default_org_id, "user_id": user_id, "role": "owner"}],
        headers=upsert,
    )
    for label, response in (("organizations", organization), ("membership", membership)):
        if response.status_code >= 400:
            print(
                f"  ! could not write {label}: {response.status_code} "
                f"{response.text[:200]}. Has 0002-organizations.sql been run?",
                file=sys.stderr,
            )
            return
    print(f"  in organization {settings.default_org_id} ({settings.default_org_name}) as owner")


def main() -> int:
    settings = get_settings()

    if not settings.uses_supabase:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set.", file=sys.stderr)
        return 1
    if not settings.demo_user_password:
        print("DEMO_USER_PASSWORD is not set. Choose one and put it in .env.", file=sys.stderr)
        return 1

    key = settings.supabase_service_role_key or ""
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    with httpx.Client(timeout=30.0) as client:
        existing = client.get(
            f"{settings.auth_url}/admin/users",
            params={"page": 1, "per_page": 200},
            headers=headers,
        )
        if existing.status_code < 400:
            for user in existing.json().get("users", []):
                if user.get("email", "").lower() == settings.demo_user_email.lower():
                    print(f"Demo user already exists: {settings.demo_user_email}")
                    join_default_org(client, headers, settings, user["id"])
                    print(f"AUTH_DEV_USER_ID={user['id']}")
                    return 0

        created = client.post(
            f"{settings.auth_url}/admin/users",
            json={
                "email": settings.demo_user_email,
                "password": settings.demo_user_password,
                "email_confirm": True,
            },
            headers=headers,
        )
        if created.status_code >= 400:
            print(f"Could not create the user: {created.status_code} {created.text[:300]}",
                  file=sys.stderr)
            return 1

        user_id = created.json()["id"]
        join_default_org(client, headers, settings, user_id)

    print(f"Created demo user {settings.demo_user_email}")
    print()
    print("Add this to your .env so the local store agrees on the same identity:")
    print(f"AUTH_DEV_USER_ID={user_id}")
    print()
    print("Sign in with:")
    print("  curl -X POST http://localhost:8000/v1/auth/login \\")
    print("    -H 'Content-Type: application/json' \\")
    print(f"    -d '{{\"email\":\"{settings.demo_user_email}\",\"password\":\"...\"}}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
