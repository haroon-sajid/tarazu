"""The API on real persisted data: the queue, decisions, the trail, the dashboard.

These run against the real routes, the real repository, and the real audit
writer. The only substitution is an in-memory SQLite database in place of
Supabase Postgres — and it carries the same append-only triggers.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.config import DEFAULT_ORG_ID as DEMO_ORG_ID
from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import AuditAction, MatchStatus, ReviewDecision


def pending_id(repository: SqliteCaseRepository, case_id: str) -> str:
    for item in repository.list_review_items(DEMO_ORG_ID, case_id):
        if item.decision is ReviewDecision.PENDING:
            return item.review_item_id
    pytest.fail("the seeded case needs at least one pending item")


# --------------------------------------------------------------------------- #
# Health and auth
# --------------------------------------------------------------------------- #


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_needs_no_token(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/review-items"),
        ("get", "/v1/dashboard"),
        ("post", "/v1/review-items/RI-0002/approve"),
    ],
)
def test_every_other_route_requires_an_identity(
    anonymous_client: TestClient, seeded_case: str, method: str, path: str
) -> None:
    """No action can reach the audit trail without a user attached to it."""
    response = getattr(anonymous_client, method)(path)
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# The review queue, from the database
# --------------------------------------------------------------------------- #


def test_review_items_come_from_the_store(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    response = client.get("/v1/review-items")
    assert response.status_code == 200
    body = response.json()

    assert body["case_id"] == seeded_case
    assert body["total"] == len(repository.list_review_items(DEMO_ORG_ID, seeded_case))
    first = body["items"][0]
    assert "extraction_confidence" in first
    assert "match_strength" in first["match"]
    assert "confidence" not in first


def test_review_items_can_be_filtered(client: TestClient, seeded_case: str) -> None:
    everything = client.get("/v1/review-items").json()["total"]
    unmatched = client.get("/v1/review-items", params={"match_status": "unmatched"}).json()
    flagged = client.get("/v1/review-items", params={"flagged": True}).json()

    assert 0 < unmatched["total"] < everything
    assert all(item["match"]["status"] == "unmatched" for item in unmatched["items"])
    assert all(item["flags"] for item in flagged["items"])


def test_an_empty_store_says_so_rather_than_returning_nothing(client: TestClient) -> None:
    response = client.get("/v1/review-items")
    assert response.status_code == 404
    assert "upload" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# Human decisions land in the database and in the trail
# --------------------------------------------------------------------------- #


def test_approve_persists_the_decision(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = pending_id(repository, seeded_case)

    response = client.post(
        f"/v1/review-items/{item_id}/approve",
        json={"note": "Vouched against the supplier statement."},
    )
    assert response.status_code == 200

    stored = repository.get_review_item(DEMO_ORG_ID, item_id)
    assert stored is not None
    assert stored.decision is ReviewDecision.APPROVED
    assert stored.decided_by == "00000000-0000-4000-8000-000000000001"
    assert stored.decided_at is not None


def test_an_approve_click_lands_a_row_in_audit_trail(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """The acceptance criterion, asserted against the database."""
    item_id = pending_id(repository, seeded_case)
    before = len(repository.list_audit(DEMO_ORG_ID, seeded_case))

    response = client.post(f"/v1/review-items/{item_id}/approve", json={})
    assert response.status_code == 200

    after = repository.list_audit(DEMO_ORG_ID, seeded_case)
    assert len(after) == before + 1

    record = after[-1]
    assert record.action is AuditAction.ITEM_APPROVED
    assert record.actor_type.value == "human"
    assert record.actor_id == "00000000-0000-4000-8000-000000000001"
    assert record.item_id == item_id
    # The response hands the caller the record it wrote, so the UI can show it.
    assert response.json()["audit_record"]["audit_id"] == record.audit_id


def test_reject_persists_the_reason_and_the_trail_entry(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = pending_id(repository, seeded_case)
    reason = "No supporting invoice provided by the client."

    response = client.post(f"/v1/review-items/{item_id}/reject", json={"reason": reason})
    assert response.status_code == 200

    stored = repository.get_review_item(DEMO_ORG_ID, item_id)
    assert stored.decision is ReviewDecision.REJECTED
    assert stored.rejection_reason == reason
    assert repository.list_audit(DEMO_ORG_ID, seeded_case)[-1].action is AuditAction.ITEM_REJECTED


def test_reject_requires_a_reason(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = pending_id(repository, seeded_case)
    assert client.post(f"/v1/review-items/{item_id}/reject", json={}).status_code == 422


def test_a_refused_decision_writes_nothing(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """A rejected request must not leave a half-decision or a stray audit row."""
    item_id = pending_id(repository, seeded_case)
    before = len(repository.list_audit(DEMO_ORG_ID, seeded_case))

    client.post(f"/v1/review-items/{item_id}/reject", json={})

    assert repository.get_review_item(DEMO_ORG_ID, item_id).decision is ReviewDecision.PENDING
    assert len(repository.list_audit(DEMO_ORG_ID, seeded_case)) == before


def test_deciding_an_already_decided_item_conflicts(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    decided = next(
        item
        for item in repository.list_review_items(DEMO_ORG_ID, seeded_case)
        if item.decision is not ReviewDecision.PENDING
    )
    response = client.post(f"/v1/review-items/{decided.review_item_id}/approve", json={})
    assert response.status_code == 409


def test_unknown_review_item_is_not_found(client: TestClient, seeded_case: str) -> None:
    assert client.post("/v1/review-items/RI-nope/approve", json={}).status_code == 404


def test_the_item_audit_trail_is_readable(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = pending_id(repository, seeded_case)
    client.post(f"/v1/review-items/{item_id}/approve", json={"note": "checked"})

    trail = client.get(f"/v1/review-items/{item_id}/audit").json()
    assert [entry["action"] for entry in trail] == ["item_approved"]
    assert trail[0]["detail"] == "checked"


# --------------------------------------------------------------------------- #
# Dashboard, counted from the database
# --------------------------------------------------------------------------- #


def test_dashboard_counts_the_persisted_queue(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    items = repository.list_review_items(DEMO_ORG_ID, seeded_case)
    body = client.get("/v1/dashboard").json()

    assert body["total_review_items"] == len(items)
    assert body["client_name"] == "Sethi Textiles (Pvt) Ltd"
    assert (
        body["match_status"]["matched"]
        + body["match_status"]["partial"]
        + body["match_status"]["unmatched"]
        == len(items)
    )
    assert body["total_flags"] == sum(len(item.flags) for item in items)


def test_dashboard_returns_benford_ready_to_chart(
    client: TestClient, seeded_case: str
) -> None:
    """Observed, expected, deviation per digit, plus the chi-square statistic."""
    benford = client.get("/v1/dashboard").json()["benford"]

    assert [digit["digit"] for digit in benford["digits"]] == list(range(1, 10))
    for digit in benford["digits"]:
        assert {"observed_count", "observed_frequency", "expected_frequency", "deviation"} <= set(digit)
    assert benford["chi_square"] >= 0
    assert benford["degrees_of_freedom"] == 8
    assert isinstance(benford["deviates_significantly"], bool)


def test_dashboard_readiness_score_tracks_real_decisions(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """Reviewing a flagged item should move the score, and say which part moved."""
    flagged = next(
        item
        for item in repository.list_review_items(DEMO_ORG_ID, seeded_case)
        if item.flags and item.decision is ReviewDecision.PENDING
    )
    before = client.get("/v1/dashboard").json()["audit_readiness_score"]

    client.post(f"/v1/review-items/{flagged.review_item_id}/approve", json={})

    after = client.get("/v1/dashboard").json()["audit_readiness_score"]
    assert after["score"] > before["score"]
    assert after["flags_reviewed"]["count"] > before["flags_reviewed"]["count"]
    # Matching and completeness are untouched by a decision.
    assert after["matched"] == before["matched"]
    assert after["completeness"] == before["completeness"]


def test_dashboard_readiness_shows_its_working(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    items = repository.list_review_items(DEMO_ORG_ID, seeded_case)
    readiness = client.get("/v1/dashboard").json()["audit_readiness_score"]

    assert 0 <= readiness["score"] <= 100
    for part in ("matched", "flags_reviewed", "completeness"):
        component = readiness[part]
        assert component["count"] <= component["total"]
        assert 0.0 <= component["percent"] <= 100.0

    assert readiness["matched"]["total"] == len(items)
    assert readiness["matched"]["count"] == sum(
        1 for item in items if item.match.status is MatchStatus.MATCHED
    )
    assert readiness["flags_reviewed"]["total"] == sum(len(item.flags) for item in items)


def test_dashboard_returns_a_computed_confidence_sentence(
    client: TestClient, seeded_case: str
) -> None:
    sentence = client.get("/v1/dashboard").json()["data_confidence"]
    assert sentence.startswith("Based on ")
    assert sentence.endswith(".")
    assert "unmatched item" in sentence


def test_dashboard_returns_next_best_actions(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    actions = client.get("/v1/dashboard").json()["next_best_actions"]

    assert 0 < len(actions) <= 5
    severities = [action["severity"] for action in actions]
    rank = {"high": 0, "medium": 1, "low": 2}
    assert severities == sorted(severities, key=lambda s: rank[s]), "most severe first"

    known_ids = {item.review_item_id for item in repository.list_review_items(DEMO_ORG_ID, seeded_case)}
    for action in actions:
        assert action["review_item_id"] in known_ids
        assert action["party_name"]
        assert action["action"][0].isupper()


def test_next_best_actions_drop_off_as_items_are_decided(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """The list is a queue of outstanding work, not a static list of flags."""
    before = client.get("/v1/dashboard").json()["next_best_actions"]
    target = before[0]["review_item_id"]

    client.post(f"/v1/review-items/{target}/approve", json={})

    after = client.get("/v1/dashboard").json()["next_best_actions"]
    assert target not in {action["review_item_id"] for action in after}


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def _file(name: str, content: bytes = b"stub content") -> tuple[str, io.BytesIO]:
    return (name, io.BytesIO(content))


def test_upload_rejects_a_wrong_file_type(client: TestClient) -> None:
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", _file("statement.docx")),
            ("ledger", _file("ledger.xlsx")),
            ("invoices", _file("inv.pdf")),
        ],
    )
    assert response.status_code == 415


def test_upload_rejects_an_empty_file(client: TestClient) -> None:
    response = client.post(
        "/v1/upload",
        files=[
            ("bank_statement", _file("statement.pdf", b"")),
            ("ledger", _file("ledger.csv")),
            ("invoices", _file("inv.pdf")),
        ],
    )
    assert response.status_code == 422
