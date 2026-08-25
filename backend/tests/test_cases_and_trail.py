"""`GET /v1/cases` and `GET /v1/audit-trail`: the engagement list and the
case-wide trail. Both are reads over data other tests already exercise; what
matters here is the counts being honest and the tenancy boundary holding.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import CaseRecord, CaseStatus
from conftest import DEMO_ORG_ID
from test_api_keys import issue, with_key


# --------------------------------------------------------------------------- #
# Cases
# --------------------------------------------------------------------------- #


def test_the_case_list_carries_honest_counts(
    client: TestClient, seeded_case: str
) -> None:
    response = client.get("/v1/cases")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    case = body["cases"][0]
    assert case["case_id"] == seeded_case
    assert case["total_review_items"] == 10
    assert case["pending_items"] == 8  # the fixtures ship 1 approved + 1 rejected
    assert case["flagged_items"] > 0
    assert case["status"] == "ready_for_review"


def test_cases_are_listed_newest_first(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    repository.create_case(
        DEMO_ORG_ID,
        CaseRecord(
            case_id="CASE-NEWER",
            client_name="Second Client Ltd",
            status=CaseStatus.UPLOADED,
            created_by="someone",
            created_at=datetime.now(timezone.utc),
        ),
    )

    cases = client.get("/v1/cases").json()["cases"]

    assert [case["case_id"] for case in cases] == ["CASE-NEWER", seeded_case]
    assert cases[0]["total_review_items"] == 0


def test_a_decision_moves_the_pending_count(
    client: TestClient, seeded_case: str
) -> None:
    before = client.get("/v1/cases").json()["cases"][0]["pending_items"]
    item_id = next(
        item["review_item_id"]
        for item in client.get("/v1/review-items").json()["items"]
        if item["decision"] == "pending"
    )

    assert client.post(f"/v1/review-items/{item_id}/approve", json={}).status_code == 200

    assert client.get("/v1/cases").json()["cases"][0]["pending_items"] == before - 1


def test_another_organization_sees_no_cases(
    other_client: TestClient, seeded_case: str
) -> None:
    body = other_client.get("/v1/cases").json()
    assert body == {"total": 0, "cases": []}


def test_a_read_key_can_list_cases_and_a_write_only_key_cannot(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    read_raw, _ = issue(client, scopes=("read",))
    write_raw, _ = issue(client, scopes=("write",))

    ok = anonymous_client.get("/v1/cases", headers=with_key(anonymous_client, read_raw))
    refused = anonymous_client.get(
        "/v1/cases", headers=with_key(anonymous_client, write_raw)
    )

    assert ok.status_code == 200
    assert ok.json()["total"] == 1
    assert refused.status_code == 403


def test_listing_cases_needs_a_credential(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/v1/cases").status_code == 401


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #


def test_the_trail_serves_the_whole_case(client: TestClient, seeded_case: str) -> None:
    """The route resolves the latest case and returns its records verbatim.

    The test fixture seeds the queue without audit rows (the decision tests
    write them), so an empty-but-well-formed trail is the correct baseline.
    """
    response = client.get("/v1/audit-trail")

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == seeded_case
    assert body["total"] == len(body["records"])


def test_a_decision_lands_in_the_case_trail(
    client: TestClient, seeded_case: str
) -> None:
    before = client.get("/v1/audit-trail").json()["total"]
    item_id = next(
        item["review_item_id"]
        for item in client.get("/v1/review-items").json()["items"]
        if item["decision"] == "pending"
    )

    client.post(f"/v1/review-items/{item_id}/approve", json={})

    body = client.get("/v1/audit-trail").json()
    assert body["total"] == before + 1
    latest = body["records"][-1]
    assert latest["action"] == "item_approved"
    assert latest["actor_type"] == "human"
    assert latest["item_id"] == item_id


def test_the_trail_of_another_organizations_case_is_not_found(
    other_client: TestClient, seeded_case: str
) -> None:
    named = other_client.get("/v1/audit-trail", params={"case_id": seeded_case})
    assert named.status_code == 404


def test_the_trail_respects_key_scopes(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    read_raw, _ = issue(client, scopes=("read",))
    write_raw, _ = issue(client, scopes=("write",))

    assert (
        anonymous_client.get(
            "/v1/audit-trail", headers=with_key(anonymous_client, read_raw)
        ).status_code
        == 200
    )
    assert (
        anonymous_client.get(
            "/v1/audit-trail", headers=with_key(anonymous_client, write_raw)
        ).status_code
        == 403
    )
