"""Shared fixtures: a seeded in-memory store, and clients for two separate firms.

Every API test runs against the real repository, the real routes, and the real
audit writer — only the database file is swapped for an in-memory SQLite one.
The SQLite store carries the same append-only triggers as the Postgres schema,
so what these tests prove about the audit trail is a property of the system, not
of one database.

Tenancy is real here too: `client` acts inside the demo firm, `other_client`
inside a second firm that shares the same store. Nothing is mocked to keep them
apart — they are two rows in `organization_members` and two `org_id` values,
exactly as they would be in Postgres.

**The suite is hermetic.** The block below runs before any application module is
imported and pins the environment to local mode: no `.env`, no Supabase, no
Qwen. What `pytest` proves must not depend on whether the developer running it
has credentials configured, and no test may reach a real project by accident.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Before `from app...` — `app.core.config` reads `.env` and caches settings at
# import time, so this has to happen first to have any effect.
# --------------------------------------------------------------------------- #

#: Do not read the developer's `.env`.
os.environ["TARAZU_DOTENV"] = "0"
#: And should one have leaked in through the real environment, unset it: with
#: `SUPABASE_URL` present the app would sign tokens with the project's JWT
#: secret, take the GoTrue branch on login, and talk to a real database.
for _leaked in (
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
    "DASHSCOPE_API_KEY",
    "EXTRACTION_QWEN_API_KEY",
    "LOCAL_DATABASE_PATH",
    "LOCAL_STORAGE_PATH",
):
    os.environ.pop(_leaked, None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.deps import get_repository, get_storage  # noqa: E402
from app.core.auth import AuthenticatedUser, issue_local_token  # noqa: E402
from app.core.config import DEFAULT_ORG_ID, get_settings  # noqa: E402
from app.core.sqlite_store import (  # noqa: E402
    LocalDocumentStore,
    SqliteCaseRepository,
)
from app.main import app  # noqa: E402
from app.shared.api import ReviewItemsResponse  # noqa: E402
from app.shared.schemas import (  # noqa: E402
    BenfordResult,
    CaseRecord,
    CaseStatus,
    Organization,
    OrganizationMember,
    OrgRole,
)

assert not get_settings().uses_supabase, (
    "the test suite must run on the local SQLite store; "
    "something set SUPABASE_URL after conftest cleared it"
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "sample-data" / "fixtures"

DEMO_USER = AuthenticatedUser(
    user_id="00000000-0000-4000-8000-000000000001",
    email="auditor@tarazu.local",
    is_dev_user=True,
)

#: Firm A: the demo auditor's. Its org is the default one, which
#: `get_current_org` joins the demo user to on first use.
DEMO_ORG_ID = DEFAULT_ORG_ID

#: Firm B: a second accounting firm sharing the same database, and the user who
#: works there. Nothing about them is special — they are what any signup makes.
OTHER_ORG_ID = "11111111-1111-4111-8111-111111111111"
OTHER_USER = AuthenticatedUser(
    user_id="11111111-1111-4111-8111-000000000002",
    email="auditor@other-firm.local",
)


def load_sample_queue() -> ReviewItemsResponse:
    return ReviewItemsResponse.model_validate(
        json.loads((FIXTURES_DIR / "review-items.json").read_text("utf-8"))
    )


def load_sample_dashboard() -> dict:
    return json.loads((FIXTURES_DIR / "dashboard.json").read_text("utf-8"))


def join(
    repository: SqliteCaseRepository,
    org_id: str,
    name: str,
    user: AuthenticatedUser,
    role: OrgRole = OrgRole.OWNER,
) -> None:
    """Create an organization if needed and put `user` in it."""
    now = datetime.now(timezone.utc)
    if repository.get_organization(org_id) is None:
        repository.create_organization(
            Organization(org_id=org_id, name=name, created_at=now)
        )
    repository.add_member(
        OrganizationMember(org_id=org_id, user_id=user.user_id, role=role, created_at=now)
    )


@pytest.fixture()
def repository() -> SqliteCaseRepository:
    """An empty in-memory store, with the append-only triggers in place."""
    store = SqliteCaseRepository(":memory:")
    yield store
    store.close()


@pytest.fixture()
def demo_org(repository: SqliteCaseRepository) -> str:
    """Firm A, with the demo auditor in it. Returns its org id."""
    join(repository, DEMO_ORG_ID, "Tarazu Demo Firm", DEMO_USER)
    return DEMO_ORG_ID


@pytest.fixture()
def other_org(repository: SqliteCaseRepository) -> str:
    """Firm B, with its own auditor. Returns its org id."""
    join(repository, OTHER_ORG_ID, "Second Firm & Co", OTHER_USER)
    return OTHER_ORG_ID


@pytest.fixture()
def seeded_case(repository: SqliteCaseRepository, demo_org: str) -> str:
    """The Sethi Textiles sample case, persisted in firm A. Returns its case id."""
    queue = load_sample_queue()
    dashboard = load_sample_dashboard()
    repository.create_case(
        demo_org,
        CaseRecord(
            case_id=queue.case_id,
            client_name=dashboard["client_name"],
            period_start=dashboard["period_start"],
            period_end=dashboard["period_end"],
            status=CaseStatus.READY_FOR_REVIEW,
            created_by=DEMO_USER.user_id,
            created_at=datetime.now(timezone.utc),
        ),
    )
    repository.save_review_items(demo_org, queue.case_id, queue.items)
    repository.save_benford(
        demo_org, queue.case_id, BenfordResult.model_validate(dashboard["benford"])
    )
    return queue.case_id


@pytest.fixture()
def storage(tmp_path: Path) -> LocalDocumentStore:
    return LocalDocumentStore(tmp_path / "documents")


def signed_in(
    repository: SqliteCaseRepository,
    storage: LocalDocumentStore,
    user: AuthenticatedUser | None,
) -> TestClient:
    """A test client for one identity.

    Only the store and the document store are overridden. Identity arrives the
    way it does in production — a signed bearer token that the real
    `current_user` verifies — rather than by replacing the dependency, because
    two clients for two firms have to be able to exist at the same time and a
    dependency override is process-wide.
    """
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_storage] = lambda: storage
    headers = {}
    if user is not None:
        token, _ = issue_local_token(user.user_id, user.email, get_settings())
        headers["Authorization"] = f"Bearer {token}"
    return TestClient(app, headers=headers)


@pytest.fixture()
def client(
    repository: SqliteCaseRepository, storage: LocalDocumentStore
) -> TestClient:
    """A client wired to this test's store, signed in as the demo auditor."""
    with signed_in(repository, storage, DEMO_USER) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def other_client(
    repository: SqliteCaseRepository, storage: LocalDocumentStore, other_org: str
) -> TestClient:
    """A client for firm B: same store, same routes, a different tenant.

    Nothing here says which organization B is in. That is resolved by the real
    `get_current_org` from the real membership rows, so these tests exercise the
    actual scoping rather than a stand-in for it.
    """
    with signed_in(repository, storage, OTHER_USER) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def anonymous_client(
    repository: SqliteCaseRepository, storage: LocalDocumentStore
) -> TestClient:
    """A client with no identity, to prove the routes actually require one."""
    with signed_in(repository, storage, None) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Standing in for the parts that are not built yet
#
# `matching/` and `rules/` are owned by Dev-D and still raise
# `NotImplementedError`. These two fixtures let a test drive the whole pipeline
# anyway. **The monkeypatching happens here in the tests, never in the
# application** — `matching/service.py` and `rules/service.py` are untouched.
# --------------------------------------------------------------------------- #


@pytest.fixture()
def demo_mode(monkeypatch: pytest.MonkeyPatch):
    """Run extraction from the cached fixtures, so no test touches the network."""
    monkeypatch.setenv("DEMO_MODE", "true")
    from app.modules.extraction import settings as extraction_settings

    extraction_settings.reset_settings_cache()
    yield
    extraction_settings.reset_settings_cache()


@pytest.fixture()
def implemented_modules(monkeypatch: pytest.MonkeyPatch):
    """Stand-ins for Dev-D's two functions, so the whole flow can be exercised.

    Deliberately trivial: this is not a matching implementation and makes no
    claim to be one. It exists to prove the wiring either side of those two
    calls.
    """
    from app.modules.matching import service as matching
    from app.modules.rules import service as rules
    from app.shared.schemas import (
        Flag,
        MatchResult,
        MatchStatus,
        MatchStrength,
        Severity,
    )

    def fake_matching(ledger, bank, invoices):
        return [
            MatchResult(
                ledger_row_id=entry.ledger_row_id,
                bank_row_id=None,
                invoice_id=None,
                status=MatchStatus.UNMATCHED,
                match_strength=MatchStrength.LOW,
                reason="Stand-in used in tests; no real matching was performed.",
                rule_id="test-stub",
            )
            for entry in ledger
        ]

    def fake_rules(ledger, matches, config):
        return [
            Flag(
                flag_id=f"FLG-{index:04d}",
                rule_id="round-number",
                severity=Severity.LOW,
                explanation=f"{entry.amount} is a round figure.",
                source_row_id=entry.ledger_row_id,
            )
            for index, entry in enumerate(ledger)
            if entry.amount % 1000 == 0
        ]

    monkeypatch.setattr(matching, "run_matching", fake_matching)
    monkeypatch.setattr(rules, "evaluate_flags", fake_rules)
    return fake_matching, fake_rules
