"""`GET /v1/cases` and `GET /v1/audit-trail`: the engagement list and the
case-wide trail, plus the two verbs that manage a case — `PATCH` (rename,
correct the period) and `DELETE` (remove the engagement and its working
data). What matters here is the counts being honest, the tenancy boundary
holding, the working data going with a deleted case while the trail outlives
it, and every one of those acts landing in the trail.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import AuditAction, CaseRecord, CaseStatus
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
# Editing a case (PATCH /v1/cases/{case_id})
# --------------------------------------------------------------------------- #


def test_a_case_can_be_renamed(client: TestClient, seeded_case: str) -> None:
    response = client.patch(
        f"/v1/cases/{seeded_case}", json={"client_name": "Haroon Textiles Ltd"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == seeded_case
    assert body["client_name"] == "Haroon Textiles Ltd"
    assert body["total_review_items"] == 10  # the counts survive an edit

    case = client.get("/v1/cases").json()["cases"][0]
    assert case["client_name"] == "Haroon Textiles Ltd"

    record = client.get("/v1/audit-trail").json()["records"][-1]
    assert record["action"] == "case_updated"
    assert "renamed" in record["detail"]
    assert "Haroon Textiles Ltd" in record["detail"]


def test_the_period_can_be_corrected_and_cleared(
    client: TestClient, seeded_case: str
) -> None:
    corrected = client.patch(
        f"/v1/cases/{seeded_case}",
        json={"period_start": "2026-06-02", "period_end": "2026-06-29"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["period_start"] == "2026-06-02"
    assert corrected.json()["period_end"] == "2026-06-29"

    # A field the request leaves out keeps its value...
    renamed = client.patch(f"/v1/cases/{seeded_case}", json={"client_name": "Haroon"})
    assert renamed.json()["period_start"] == "2026-06-02"

    # ...and `null` clears a period.
    cleared = client.patch(f"/v1/cases/{seeded_case}", json={"period_end": None})
    assert cleared.json()["period_end"] is None


def test_a_blank_client_name_is_refused(client: TestClient, seeded_case: str) -> None:
    response = client.patch(f"/v1/cases/{seeded_case}", json={"client_name": "   "})

    assert response.status_code == 422
    assert (
        client.get("/v1/cases").json()["cases"][0]["client_name"] == "Haroon Textiles"
    )


def test_the_period_cannot_end_before_it_starts(
    client: TestClient, seeded_case: str
) -> None:
    response = client.patch(
        f"/v1/cases/{seeded_case}",
        json={"period_start": "2026-07-01", "period_end": "2026-06-01"},
    )
    assert response.status_code == 422


def test_another_organizations_case_cannot_be_edited_or_deleted(
    other_client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    edited = other_client.patch(
        f"/v1/cases/{seeded_case}", json={"client_name": "Ours now"}
    )
    deleted = other_client.delete(f"/v1/cases/{seeded_case}")

    assert edited.status_code == 404
    assert deleted.status_code == 404
    assert repository.get_case(DEMO_ORG_ID, seeded_case) is not None


def test_case_management_respects_key_scopes(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    read_raw, _ = issue(client, scopes=("read",))
    write_raw, _ = issue(client, scopes=("write",))

    refused = anonymous_client.patch(
        f"/v1/cases/{seeded_case}",
        json={"client_name": "By key"},
        headers=with_key(anonymous_client, read_raw),
    )
    renamed = anonymous_client.patch(
        f"/v1/cases/{seeded_case}",
        json={"client_name": "By key"},
        headers=with_key(anonymous_client, write_raw),
    )
    deleted = anonymous_client.delete(
        f"/v1/cases/{seeded_case}", headers=with_key(anonymous_client, write_raw)
    )

    assert refused.status_code == 403
    assert renamed.status_code == 200
    assert renamed.json()["client_name"] == "By key"
    assert deleted.status_code == 200


def test_managing_cases_needs_a_credential(
    anonymous_client: TestClient, seeded_case: str
) -> None:
    assert anonymous_client.patch(f"/v1/cases/{seeded_case}", json={}).status_code == 401
    assert anonymous_client.delete(f"/v1/cases/{seeded_case}").status_code == 401


# --------------------------------------------------------------------------- #
# Deleting a case (DELETE /v1/cases/{case_id})
# --------------------------------------------------------------------------- #


def test_deleting_a_case_removes_its_working_data(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    response = client.delete(f"/v1/cases/{seeded_case}")

    assert response.status_code == 200
    assert response.json() == {"case_id": seeded_case, "deleted": True}
    assert repository.get_case(DEMO_ORG_ID, seeded_case) is None
    assert repository.list_review_items(DEMO_ORG_ID, seeded_case) == []
    assert repository.list_documents(DEMO_ORG_ID, seeded_case) == []
    assert repository.list_extractions(DEMO_ORG_ID, seeded_case) == []
    assert repository.get_benford(DEMO_ORG_ID, seeded_case) is None
    assert client.get("/v1/cases").json()["total"] == 0


def test_the_deletion_is_recorded_in_a_trail_that_outlives_the_case(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    client.delete(f"/v1/cases/{seeded_case}")

    records = repository.list_audit(DEMO_ORG_ID, seeded_case)
    assert records, "the trail survives the case it describes"
    last = records[-1]
    assert last.action == AuditAction.CASE_DELETED
    assert "Haroon Textiles" in (last.detail or "")
    assert "10 review items" in (last.detail or "")


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
