"""Seed the sample case into whichever store is configured.

Loads `sample-data/fixtures/review-items.json` — the hand-built Haroon Textiles
case with its five planted errors — into the repository, so the review screen,
approve, reject, and the dashboard all work on real persisted data before
`matching/` and `rules/` exist.

Run it from the repo root::

    python scripts/seed_demo_case.py

With no Supabase configured it seeds the local SQLite store — **including a
real login**: the demo auditor from `DEMO_USER_EMAIL` / `DEMO_USER_PASSWORD`
is created as a local user with a password, so `POST /v1/auth/login` (and the
frontend's sign-in screen) works immediately. With `SUPABASE_URL` and the
service-role key set, it seeds Supabase — run `infra/supabase/schema.sql`
and then `infra/supabase/0002-organizations.sql` first, and seed the demo user
with `scripts/seed_demo_user.py`, because `cases.created_by` references
`auth.users`.

The case is seeded into the default organization (`DEFAULT_ORG_ID`), with the
demo auditor as its owner. Every row this writes carries that `org_id`, so a
second firm signing up at `POST /v1/auth/signup` sees none of it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.audit import record_action  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.repository import CaseRepository  # noqa: E402
from app.core.sqlite_store import SqliteCaseRepository  # noqa: E402
from app.core.supabase_client import SupabaseRest  # noqa: E402
from app.core.supabase_store import SupabaseCaseRepository  # noqa: E402
from app.shared.api import ReviewItemsResponse  # noqa: E402
from app.shared.schemas import (  # noqa: E402
    ActorType,
    AuditAction,
    BenfordResult,
    CaseRecord,
    CaseStatus,
    Organization,
    OrganizationMember,
    OrgRole,
)

FIXTURES = REPO_ROOT / "sample-data" / "fixtures"
CLIENT_NAME = "Haroon Textiles"


def build_repository() -> tuple[CaseRepository, str]:
    settings = get_settings()
    if settings.uses_supabase:
        return SupabaseCaseRepository(SupabaseRest(settings)), "Supabase"
    return SqliteCaseRepository(settings.local_database_path), str(
        settings.local_database_path
    )


def seed_local_login(repository: CaseRepository, settings) -> str | None:
    """Create the demo auditor as a real local user. Returns its id.

    SQLite only — with Supabase, identities live in GoTrue and are seeded by
    `scripts/seed_demo_user.py` instead. Idempotent: an existing user with the
    demo password is reused; an existing user with a *different* password is
    left alone (someone changed it on purpose) and this returns None.
    """
    if not isinstance(repository, SqliteCaseRepository):
        return None
    password = settings.demo_user_password
    if not password:
        print("DEMO_USER_PASSWORD is unset — no local login seeded.")
        return None
    email = settings.demo_user_email
    try:
        user_id = repository.create_user(email, password)
        print(f"Created local demo login {email}")
        return user_id
    except ValueError:
        user_id = repository.verify_password(email, password)
        if user_id is None:
            print(f"! {email} exists with a different password; left unchanged.")
        return user_id


def main() -> int:
    settings = get_settings()
    repository, where = build_repository()

    queue = ReviewItemsResponse.model_validate(
        json.loads((FIXTURES / "review-items.json").read_text("utf-8"))
    )
    dashboard = json.loads((FIXTURES / "dashboard.json").read_text("utf-8"))
    benford = BenfordResult.model_validate(dashboard["benford"])
    # Attribute everything to the seeded login where there is one, so the UI
    # greets the signed-in demo auditor with their own case ("Created by: You").
    user_id = seed_local_login(repository, settings) or settings.dev_user_id
    org_id = settings.default_org_id
    now = datetime.now(timezone.utc)

    # The demo auditor's firm. Idempotent, so re-seeding does not duplicate it.
    if repository.get_organization(org_id) is None:
        repository.create_organization(
            Organization(org_id=org_id, name=settings.default_org_name, created_at=now)
        )
    repository.add_member(
        OrganizationMember(
            org_id=org_id, user_id=user_id, role=OrgRole.OWNER, created_at=now
        )
    )

    # The fixtures ship two already-decided items whose `decided_by` is the
    # readable placeholder "user-demo-auditor". SQLite stores that happily;
    # Postgres does not, because `review_items.decided_by` is a uuid referencing
    # `auth.users`. Point them at whoever this store's demo auditor actually is,
    # so the same fixture seeds both backends.
    items = [
        item
        if item.decided_by is None
        else item.model_copy(update={"decided_by": user_id})
        for item in queue.items
    ]

    repository.create_case(
        org_id,
        CaseRecord(
            case_id=queue.case_id,
            client_name=CLIENT_NAME,
            period_start=dashboard["period_start"],
            period_end=dashboard["period_end"],
            status=CaseStatus.READY_FOR_REVIEW,
            created_by=user_id,
            created_at=now,
        ),
    )
    repository.save_review_items(org_id, queue.case_id, items)
    repository.save_benford(org_id, queue.case_id, benford)
    record_action(
        repository, org_id, queue.case_id, ActorType.SYSTEM, "seed_demo_case.py",
        AuditAction.CASE_CREATED,
        detail=f"Seeded {len(queue.items)} review items from the sample fixtures",
    )

    flags = sum(len(item.flags) for item in items)
    print(f"Seeded case {queue.case_id} into {where}")
    print(f"  {len(items)} review items, {flags} flags, Benford over "
          f"{benford.sample_size} amounts")
    print(f"  org_id     = {org_id} ({settings.default_org_name})")
    print(f"  created_by = {user_id}")
    if not settings.uses_supabase and settings.demo_user_password:
        print()
        print("Sign in (frontend or POST /v1/auth/login):")
        print(f"  email    = {settings.demo_user_email}")
        print("  password = DEMO_USER_PASSWORD from .env")
    print()
    print("Try it:")
    print("  curl http://localhost:8000/v1/review-items")
    print(f"  curl -X POST http://localhost:8000/v1/review-items/"
          f"{queue.items[1].review_item_id}/approve -H 'Content-Type: application/json' -d '{{}}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
