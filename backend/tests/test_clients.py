"""`/v1/clients`: the firm's recurring clients (ADR 0005).

What matters here is the same as everywhere else in this suite. The counts on a
client are read off its persisted periods rather than estimated; the tenancy
boundary holds, so another firm's client is a `404` and never appears in a
list; archiving hides a relationship without deleting a single thing behind it;
and every write lands in the append-only trail, keyed by the client id because
a client event has no case.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import (
    AuditAction,
    EvidenceRequest,
    EvidenceRequestStatus,
)
from conftest import DEMO_ORG_ID, OTHER_ORG_ID
from test_api_keys import issue, with_key


def add_client(test_client: TestClient, name: str = "Haroon Textiles", **fields) -> dict:
    """Create a client as a signed-in auditor. Returns the summary."""
    response = test_client.post("/v1/clients", json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def attach(
    repository: SqliteCaseRepository,
    case_id: str,
    client_id: str,
    *,
    org_id: str = DEMO_ORG_ID,
    client_name: str = "Haroon Textiles",
    period_start: str | None = "2026-06-01",
    period_end: str | None = "2026-06-30",
) -> None:
    """Make an existing case one period of a client."""
    updated = repository.update_case(
        org_id,
        case_id,
        client_name=client_name,
        period_start=date.fromisoformat(period_start) if period_start else None,
        period_end=date.fromisoformat(period_end) if period_end else None,
        client_id=client_id,
    )
    assert updated is not None and updated.client_id == client_id


def raise_evidence_request(
    repository: SqliteCaseRepository,
    case_id: str,
    request_id: str,
    status: EvidenceRequestStatus = EvidenceRequestStatus.OPEN,
    org_id: str = DEMO_ORG_ID,
) -> None:
    now = datetime.now(timezone.utc)
    repository.save_evidence_request(
        org_id,
        EvidenceRequest(
            request_id=request_id,
            case_id=case_id,
            title="Send invoice #43",
            status=status,
            requested_by="auditor",
            requested_at=now,
            # The schema insists a state be complete: an answered request says
            # when it was answered, a closed one when it was closed.
            responded_by="the client" if status is not EvidenceRequestStatus.OPEN else None,
            responded_at=now if status is not EvidenceRequestStatus.OPEN else None,
            closed_by="auditor" if status.is_closed else None,
            closed_at=now if status.is_closed else None,
        ),
    )


# --------------------------------------------------------------------------- #
# Adding, listing, reading
# --------------------------------------------------------------------------- #


def test_a_new_client_starts_with_defaults_and_no_history(
    client: TestClient, demo_org: str
) -> None:
    body = add_client(client, "Haroon Textiles")

    assert body["client_id"].startswith("CLI-")
    assert body["name"] == "Haroon Textiles"
    assert body["currency"] == "PKR"
    assert body["language"] == "en"
    assert body["archived"] is False
    assert body["rules"]["approval_limits"] == [50_000, 100_000, 500_000]
    assert body["rules"]["require_sign_off"] is False
    assert body["period_count"] == 0
    assert body["pending_items"] == 0
    assert body["open_evidence_requests"] == 0
    assert body["last_period_end"] is None
    assert body["last_activity_at"] is None


def test_a_client_can_be_created_with_its_own_settings(
    client: TestClient, demo_org: str
) -> None:
    body = add_client(
        client,
        "Karachi Spices (Pvt) Ltd",
        reference="  KS-001  ",
        currency="USD",
        language="ur",
        relationship_owner="Haroon",
        notes="Quarterly, VAT registered.",
        rules={"approval_limits": [25_000, 75_000], "require_sign_off": True},
    )

    assert body["reference"] == "KS-001"  # trimmed
    assert body["currency"] == "USD"
    assert body["language"] == "ur"
    assert body["relationship_owner"] == "Haroon"
    assert body["rules"]["approval_limits"] == [25_000, 75_000]
    assert body["rules"]["require_sign_off"] is True


def test_clients_are_listed_and_read_back(client: TestClient, demo_org: str) -> None:
    first = add_client(client, "Haroon Textiles")
    second = add_client(client, "Karachi Spices")

    listed = client.get("/v1/clients")
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    # Newest first, the same order the case list uses.
    assert [row["client_id"] for row in body["clients"]] == [
        second["client_id"],
        first["client_id"],
    ]

    detail = client.get(f"/v1/clients/{first['client_id']}")
    assert detail.status_code == 200
    assert detail.json()["client"]["name"] == "Haroon Textiles"
    assert detail.json()["periods"] == []


def test_a_blank_name_is_refused(client: TestClient, demo_org: str) -> None:
    response = client.post("/v1/clients", json={"name": "   "})

    assert response.status_code == 422
    assert "name" in response.json()["detail"].lower()
    assert client.get("/v1/clients").json()["total"] == 0


def test_an_unknown_client_is_not_found(client: TestClient, demo_org: str) -> None:
    assert client.get("/v1/clients/CLI-nope").status_code == 404


# --------------------------------------------------------------------------- #
# The counts, read off the client's periods
# --------------------------------------------------------------------------- #


def test_the_counts_come_from_the_clients_periods(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    created = add_client(client, "Haroon Textiles")
    attach(repository, seeded_case, created["client_id"])
    raise_evidence_request(repository, seeded_case, "EVR-1")
    raise_evidence_request(
        repository, seeded_case, "EVR-2", EvidenceRequestStatus.ANSWERED
    )
    # Resolved work is finished work and is not outstanding with the client.
    raise_evidence_request(
        repository, seeded_case, "EVR-3", EvidenceRequestStatus.RESOLVED
    )

    row = client.get("/v1/clients").json()["clients"][0]

    assert row["period_count"] == 1
    assert row["pending_items"] == 8  # the fixtures ship 1 approved + 1 rejected
    assert row["open_evidence_requests"] == 2
    assert row["last_period_end"] == "2026-06-30"
    assert row["last_activity_at"] is not None


def test_the_detail_lists_the_periods_with_their_own_counts(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    created = add_client(client, "Haroon Textiles")
    attach(repository, seeded_case, created["client_id"])

    body = client.get(f"/v1/clients/{created['client_id']}").json()

    assert body["client"]["period_count"] == 1
    assert len(body["periods"]) == 1
    period = body["periods"][0]
    assert period["case_id"] == seeded_case
    assert period["client_id"] == created["client_id"]
    assert period["total_review_items"] == 10
    assert period["pending_items"] == 8
    assert period["flagged_items"] > 0


def test_a_decision_moves_the_clients_pending_count(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    created = add_client(client, "Haroon Textiles")
    attach(repository, seeded_case, created["client_id"])
    item_id = next(
        item["review_item_id"]
        for item in client.get("/v1/review-items").json()["items"]
        if item["decision"] == "pending"
    )

    assert client.post(f"/v1/review-items/{item_id}/approve", json={}).status_code == 200

    assert client.get("/v1/clients").json()["clients"][0]["pending_items"] == 7


def test_a_case_with_no_client_belongs_to_nobodys_history(
    client: TestClient, seeded_case: str
) -> None:
    """A one-off engagement stays valid and is nobody's period (ADR 0005)."""
    created = add_client(client, "Haroon Textiles")

    row = client.get(f"/v1/clients/{created['client_id']}").json()

    assert row["client"]["period_count"] == 0
    assert row["periods"] == []


# --------------------------------------------------------------------------- #
# Editing
# --------------------------------------------------------------------------- #


def test_a_client_can_be_corrected_and_retuned(
    client: TestClient, demo_org: str
) -> None:
    created = add_client(client, "Haroon Textiles", reference="HT-1")

    response = client.patch(
        f"/v1/clients/{created['client_id']}",
        json={
            "name": "Haroon Textiles Ltd",
            "currency": "USD",
            "language": "ur",
            "rules": {"approval_limits": [25_000], "require_sign_off": True},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Haroon Textiles Ltd"
    assert body["currency"] == "USD"
    assert body["language"] == "ur"
    assert body["rules"]["approval_limits"] == [25_000]
    assert body["rules"]["require_sign_off"] is True
    assert body["reference"] == "HT-1"  # a field left out keeps its value
    assert client.get("/v1/clients").json()["clients"][0]["name"] == "Haroon Textiles Ltd"


def test_free_text_can_be_cleared_but_the_settings_cannot(
    client: TestClient, demo_org: str
) -> None:
    created = add_client(
        client, "Haroon Textiles", reference="HT-1", notes="Monthly", currency="USD"
    )

    cleared = client.patch(
        f"/v1/clients/{created['client_id']}",
        json={"reference": None, "notes": None, "currency": None, "language": None},
    )

    assert cleared.status_code == 200
    assert cleared.json()["reference"] is None
    assert cleared.json()["notes"] is None
    # `null` for a setting means "leave it alone": a client always has a
    # currency and a language.
    assert cleared.json()["currency"] == "USD"
    assert cleared.json()["language"] == "en"


def test_a_client_cannot_be_renamed_to_nothing(
    client: TestClient, demo_org: str
) -> None:
    created = add_client(client, "Haroon Textiles")

    response = client.patch(f"/v1/clients/{created['client_id']}", json={"name": "  "})

    assert response.status_code == 422
    assert client.get("/v1/clients").json()["clients"][0]["name"] == "Haroon Textiles"


def test_an_empty_patch_changes_and_records_nothing(
    client: TestClient, repository: SqliteCaseRepository, demo_org: str
) -> None:
    created = add_client(client, "Haroon Textiles")
    before = len(repository.list_audit(DEMO_ORG_ID, created["client_id"]))

    response = client.patch(f"/v1/clients/{created['client_id']}", json={})

    assert response.status_code == 200
    assert response.json()["name"] == "Haroon Textiles"
    assert len(repository.list_audit(DEMO_ORG_ID, created["client_id"])) == before


# --------------------------------------------------------------------------- #
# Archiving and restoring
# --------------------------------------------------------------------------- #


def test_archiving_hides_the_client_without_deleting_its_history(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    created = add_client(client, "Haroon Textiles")
    attach(repository, seeded_case, created["client_id"])

    archived = client.post(f"/v1/clients/{created['client_id']}/archive")

    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert archived.json()["archived_at"] is not None
    assert archived.json()["period_count"] == 1

    assert client.get("/v1/clients").json()["total"] == 0
    with_archived = client.get("/v1/clients", params={"include_archived": True}).json()
    assert with_archived["total"] == 1
    assert with_archived["clients"][0]["archived"] is True

    # Nothing underneath the relationship moved.
    assert repository.get_case(DEMO_ORG_ID, seeded_case) is not None
    assert len(repository.list_review_items(DEMO_ORG_ID, seeded_case)) == 10
    detail = client.get(f"/v1/clients/{created['client_id']}").json()
    assert len(detail["periods"]) == 1


def test_an_archived_client_can_be_restored(client: TestClient, demo_org: str) -> None:
    created = add_client(client, "Haroon Textiles")
    client.post(f"/v1/clients/{created['client_id']}/archive")

    restored = client.post(f"/v1/clients/{created['client_id']}/restore")

    assert restored.status_code == 200
    assert restored.json()["archived"] is False
    assert restored.json()["archived_at"] is None
    assert client.get("/v1/clients").json()["total"] == 1


def test_archiving_twice_is_not_an_error_and_records_once(
    client: TestClient, repository: SqliteCaseRepository, demo_org: str
) -> None:
    created = add_client(client, "Haroon Textiles")

    first = client.post(f"/v1/clients/{created['client_id']}/archive")
    second = client.post(f"/v1/clients/{created['client_id']}/archive")

    assert first.status_code == second.status_code == 200
    assert second.json()["archived_at"] == first.json()["archived_at"]
    records = repository.list_audit(DEMO_ORG_ID, created["client_id"])
    assert [r.action for r in records].count(AuditAction.CLIENT_ARCHIVED) == 1


# --------------------------------------------------------------------------- #
# The audit trail
# --------------------------------------------------------------------------- #


def test_every_client_event_lands_in_the_trail(
    client: TestClient, repository: SqliteCaseRepository, demo_org: str
) -> None:
    created = add_client(client, "Haroon Textiles")
    client_id = created["client_id"]
    client.patch(f"/v1/clients/{client_id}", json={"name": "Haroon Textiles Ltd"})
    client.post(f"/v1/clients/{client_id}/archive")
    client.post(f"/v1/clients/{client_id}/restore")

    # The trail is keyed by case; a client event uses the client id as its key.
    records = repository.list_audit(DEMO_ORG_ID, client_id)

    assert [record.action for record in records] == [
        AuditAction.CLIENT_CREATED,
        AuditAction.CLIENT_UPDATED,
        AuditAction.CLIENT_ARCHIVED,
        AuditAction.CLIENT_UPDATED,
    ]
    assert all(record.item_id == client_id for record in records)
    assert all(record.actor_type.value == "human" for record in records)
    assert "Haroon Textiles" in (records[0].detail or "")
    assert "renamed" in (records[1].detail or "")
    assert "Haroon Textiles Ltd" in (records[1].detail or "")
    assert "archived" in (records[2].detail or "")
    assert "restored" in (records[3].detail or "")


def test_retuning_the_rules_says_so_in_the_trail(
    client: TestClient, repository: SqliteCaseRepository, demo_org: str
) -> None:
    created = add_client(client, "Haroon Textiles")

    client.patch(
        f"/v1/clients/{created['client_id']}",
        json={"rules": {"approval_limits": [25_000], "require_sign_off": True}},
    )

    detail = repository.list_audit(DEMO_ORG_ID, created["client_id"])[-1].detail or ""
    assert "rule thresholds updated" in detail
    assert "25000" in detail
    assert "sign-off required" in detail


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #


def test_another_firms_client_is_never_listed(
    client: TestClient, other_client: TestClient, demo_org: str
) -> None:
    add_client(client, "Haroon Textiles")

    assert other_client.get("/v1/clients").json() == {"total": 0, "clients": []}
    assert (
        other_client.get("/v1/clients", params={"include_archived": True}).json()["total"]
        == 0
    )


def test_another_firms_client_is_not_found_never_forbidden(
    client: TestClient,
    other_client: TestClient,
    repository: SqliteCaseRepository,
    demo_org: str,
) -> None:
    created = add_client(client, "Haroon Textiles")
    client_id = created["client_id"]

    read = other_client.get(f"/v1/clients/{client_id}")
    patched = other_client.patch(f"/v1/clients/{client_id}", json={"name": "Ours now"})
    archived = other_client.post(f"/v1/clients/{client_id}/archive")
    restored = other_client.post(f"/v1/clients/{client_id}/restore")

    assert [r.status_code for r in (read, patched, archived, restored)] == [404] * 4
    untouched = repository.get_client(DEMO_ORG_ID, client_id)
    assert untouched is not None
    assert untouched.name == "Haroon Textiles"
    assert untouched.archived_at is None
    assert repository.get_client(OTHER_ORG_ID, client_id) is None


def test_two_firms_keep_their_own_client_lists(
    client: TestClient, other_client: TestClient, demo_org: str
) -> None:
    ours = add_client(client, "Haroon Textiles")
    theirs = add_client(other_client, "Second Firm's Client")

    assert [row["client_id"] for row in client.get("/v1/clients").json()["clients"]] == [
        ours["client_id"]
    ]
    assert [
        row["client_id"] for row in other_client.get("/v1/clients").json()["clients"]
    ] == [theirs["client_id"]]


# --------------------------------------------------------------------------- #
# Credentials and scopes
# --------------------------------------------------------------------------- #


def test_managing_clients_needs_a_credential(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/v1/clients").status_code == 401
    assert anonymous_client.post("/v1/clients", json={"name": "X"}).status_code == 401
    assert anonymous_client.patch("/v1/clients/CLI-x", json={}).status_code == 401
    assert anonymous_client.post("/v1/clients/CLI-x/archive").status_code == 401


def test_clients_respect_key_scopes(
    client: TestClient, anonymous_client: TestClient, demo_org: str
) -> None:
    read_raw, _ = issue(client, scopes=("read",))
    write_raw, _ = issue(client, scopes=("write",))

    listed = anonymous_client.get(
        "/v1/clients", headers=with_key(anonymous_client, read_raw)
    )
    refused = anonymous_client.post(
        "/v1/clients",
        json={"name": "By a read-only key"},
        headers=with_key(anonymous_client, read_raw),
    )
    created = anonymous_client.post(
        "/v1/clients",
        json={"name": "By a write key"},
        headers=with_key(anonymous_client, write_raw),
    )

    assert listed.status_code == 200
    assert refused.status_code == 403
    assert created.status_code == 201
    assert created.json()["name"] == "By a write key"
