"""Evidence requests: the ask, its answer, its close, and who may see it.

These tests run against the real routes, the real SQLite store, and the real
audit writer, so what they prove about the trail is a property of the system.
Three things are being pinned down:

- the lifecycle is one-way — open, answered, resolved or cancelled, and never
  back — and the state the row lands in always carries the timestamps the schema
  demands;
- `open_total` counts the work outstanding, which includes answered requests
  nobody has looked at yet;
- a request is a row inside one organization, so another firm cannot list it,
  answer it, or close it, and is told `404` rather than `403`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.shared.schemas import (
    AuditAction,
    CaseRecord,
    CaseStatus,
    EvidenceRequestStatus,
)
from tests.conftest import DEMO_ORG_ID, DEMO_USER, OTHER_ORG_ID, OTHER_USER


def raise_request(client: TestClient, **body) -> dict:
    """Create one request through the API and return it, failing loudly if not."""
    response = client.post("/v1/evidence-requests", json={"title": "The invoice", **body})
    assert response.status_code == 201, response.text
    return response.json()["request"]


def a_case(repository, org_id: str, case_id: str, created_by: str) -> str:
    repository.create_case(
        org_id,
        CaseRecord(
            case_id=case_id,
            client_name="Second Client",
            status=CaseStatus.READY_FOR_REVIEW,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        ),
    )
    return case_id


def actions(repository, case_id: str, request_id: str) -> list[AuditAction]:
    return [
        record.action
        for record in repository.list_audit(DEMO_ORG_ID, case_id, item_id=request_id)
    ]


# --------------------------------------------------------------------------- #
# Raising an ask
# --------------------------------------------------------------------------- #


def test_raising_a_request_records_the_ask_and_who_made_it(
    client: TestClient, repository, seeded_case: str
) -> None:
    response = client.post(
        "/v1/evidence-requests",
        json={
            "title": "Invoice for the 12 June payment",
            "detail": "PKR 284,000 to Sadiq Traders has no invoice behind it.",
            "review_item_id": "RI-0001",
            "due_date": "2026-09-15",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    request = body["request"]

    assert request["request_id"].startswith("EVR-")
    assert request["case_id"] == seeded_case
    assert request["review_item_id"] == "RI-0001"
    assert request["status"] == EvidenceRequestStatus.OPEN.value
    assert request["due_date"] == "2026-09-15"
    assert request["requested_by"] == DEMO_USER.user_id
    assert request["responded_at"] is None and request["closed_at"] is None

    assert body["audit_record"]["action"] == AuditAction.EVIDENCE_REQUESTED.value
    assert body["audit_record"]["item_id"] == request["request_id"]
    assert "RI-0001" in body["audit_record"]["detail"]

    stored = repository.get_evidence_request(DEMO_ORG_ID, request["request_id"])
    assert stored is not None and stored.title == "Invoice for the 12 June payment"


def test_a_request_needs_a_case(client: TestClient, demo_org: str) -> None:
    """No case, nothing to ask about. The same `404` every case-scoped route gives."""
    assert client.post("/v1/evidence-requests", json={"title": "Anything"}).status_code == 404


def test_a_request_needs_a_title(client: TestClient, seeded_case: str) -> None:
    assert client.post("/v1/evidence-requests", json={"title": ""}).status_code == 422


def test_an_unknown_review_item_is_refused(client: TestClient, seeded_case: str) -> None:
    response = client.post(
        "/v1/evidence-requests", json={"title": "x", "review_item_id": "RI-9999"}
    )
    assert response.status_code == 404
    assert "RI-9999" in response.json()["detail"]


def test_a_review_item_from_another_case_is_refused(
    client: TestClient, repository, seeded_case: str
) -> None:
    """The ask stays with the case that raised it, even inside one firm."""
    other_case = a_case(repository, DEMO_ORG_ID, "CASE-OTHER", DEMO_USER.user_id)
    response = client.post(
        "/v1/evidence-requests",
        json={"title": "x", "case_id": other_case, "review_item_id": "RI-0001"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert seeded_case in detail and other_case in detail
    assert repository.list_evidence_requests(DEMO_ORG_ID, other_case) == []


# --------------------------------------------------------------------------- #
# The lifecycle
# --------------------------------------------------------------------------- #


def test_a_request_runs_from_open_through_answered_to_resolved(
    client: TestClient, repository, seeded_case: str
) -> None:
    request_id = raise_request(client, title="Invoice #43")["request_id"]

    listed = client.get("/v1/evidence-requests").json()
    assert listed == {
        **listed,
        "case_id": seeded_case,
        "total": 1,
        "open_total": 1,
    }
    assert listed["requests"][0]["status"] == "open"

    answered = client.post(
        f"/v1/evidence-requests/{request_id}/respond",
        json={"response_note": "Client emailed a scan of invoice #43."},
    )
    assert answered.status_code == 200, answered.text
    request = answered.json()["request"]
    assert request["status"] == EvidenceRequestStatus.ANSWERED.value
    assert request["response_note"] == "Client emailed a scan of invoice #43."
    assert request["responded_by"] == DEMO_USER.user_id
    assert request["responded_at"] is not None
    assert request["closed_at"] is None
    # Answered is not finished: somebody still has to read it.
    assert client.get("/v1/evidence-requests").json()["open_total"] == 1

    resolved = client.post(f"/v1/evidence-requests/{request_id}/resolve")
    assert resolved.status_code == 200, resolved.text
    request = resolved.json()["request"]
    assert request["status"] == EvidenceRequestStatus.RESOLVED.value
    assert request["closed_by"] == DEMO_USER.user_id
    assert request["closed_at"] is not None
    # The answer is not thrown away by closing it.
    assert request["response_note"] == "Client emailed a scan of invoice #43."

    final = client.get("/v1/evidence-requests").json()
    assert final["total"] == 1 and final["open_total"] == 0


def test_resolving_straight_from_open_is_allowed(
    client: TestClient, seeded_case: str
) -> None:
    """Evidence often arrives outside the product; the auditor may just say so."""
    request_id = raise_request(client)["request_id"]
    resolved = client.post(f"/v1/evidence-requests/{request_id}/resolve").json()["request"]
    assert resolved["status"] == "resolved"
    assert resolved["response_note"] is None
    assert resolved["closed_at"] is not None


def test_cancelling_closes_the_ask_and_the_trail_says_so(
    client: TestClient, repository, seeded_case: str
) -> None:
    request_id = raise_request(client, title="Contract behind the round number")["request_id"]
    response = client.post(f"/v1/evidence-requests/{request_id}/cancel")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["request"]["status"] == EvidenceRequestStatus.CANCELLED.value
    assert body["request"]["closed_by"] == DEMO_USER.user_id
    assert body["request"]["closed_at"] is not None
    assert body["request"]["responded_at"] is None

    assert body["audit_record"]["action"] == AuditAction.EVIDENCE_CANCELLED.value
    assert "Cancelled without a response" in body["audit_record"]["detail"]
    assert client.get("/v1/evidence-requests").json()["open_total"] == 0


def test_a_closed_request_is_never_reopened(client: TestClient, seeded_case: str) -> None:
    resolved = raise_request(client, title="Already settled")["request_id"]
    assert client.post(f"/v1/evidence-requests/{resolved}/resolve").status_code == 200

    for route in ("respond", "resolve", "cancel"):
        payload = {"response_note": "late"} if route == "respond" else None
        conflict = client.post(f"/v1/evidence-requests/{resolved}/{route}", json=payload)
        assert conflict.status_code == 409, route
        assert "already resolved" in conflict.json()["detail"]

    cancelled = raise_request(client, title="Withdrawn")["request_id"]
    assert client.post(f"/v1/evidence-requests/{cancelled}/cancel").status_code == 200
    late = client.post(
        f"/v1/evidence-requests/{cancelled}/respond", json={"response_note": "late"}
    )
    assert late.status_code == 409
    assert "already cancelled" in late.json()["detail"]


def test_acting_on_a_request_that_does_not_exist_is_404(
    client: TestClient, seeded_case: str
) -> None:
    assert client.post("/v1/evidence-requests/EVR-nope/resolve").status_code == 404


# --------------------------------------------------------------------------- #
# The list and its counts
# --------------------------------------------------------------------------- #


def test_the_list_is_newest_first_and_counts_the_work_outstanding(
    client: TestClient, seeded_case: str
) -> None:
    first = raise_request(client, title="First ask")["request_id"]
    second = raise_request(client, title="Second ask")["request_id"]
    third = raise_request(client, title="Third ask")["request_id"]
    fourth = raise_request(client, title="Fourth ask")["request_id"]

    client.post(
        f"/v1/evidence-requests/{second}/respond", json={"response_note": "sent"}
    )
    client.post(f"/v1/evidence-requests/{third}/resolve")
    client.post(f"/v1/evidence-requests/{fourth}/cancel")

    listed = client.get("/v1/evidence-requests", params={"case_id": seeded_case}).json()
    assert [request["request_id"] for request in listed["requests"]] == [
        fourth, third, second, first,
    ]
    assert listed["total"] == 4
    # Open (first) plus answered (second). Resolved and cancelled are done.
    assert listed["open_total"] == 2


def test_the_list_is_empty_for_a_case_with_no_asks(
    client: TestClient, repository, seeded_case: str
) -> None:
    raise_request(client)
    quiet = a_case(repository, DEMO_ORG_ID, "CASE-QUIET", DEMO_USER.user_id)
    listed = client.get("/v1/evidence-requests", params={"case_id": quiet}).json()
    assert listed == {"case_id": quiet, "total": 0, "open_total": 0, "requests": []}


# --------------------------------------------------------------------------- #
# The audit trail
# --------------------------------------------------------------------------- #


def test_every_transition_is_recorded_against_the_request(
    client: TestClient, repository, seeded_case: str
) -> None:
    request_id = raise_request(client, title="Bank confirmation")["request_id"]
    client.post(f"/v1/evidence-requests/{request_id}/respond", json={"response_note": "in hand"})
    client.post(f"/v1/evidence-requests/{request_id}/resolve")

    assert actions(repository, seeded_case, request_id) == [
        AuditAction.EVIDENCE_REQUESTED,
        AuditAction.EVIDENCE_ANSWERED,
        AuditAction.EVIDENCE_RESOLVED,
    ]
    trail = repository.list_audit(DEMO_ORG_ID, seeded_case, item_id=request_id)
    assert {record.actor_id for record in trail} == {DEMO_USER.user_id}
    assert "in hand" in trail[1].detail


def test_a_cancelled_ask_keeps_both_events(
    client: TestClient, repository, seeded_case: str
) -> None:
    request_id = raise_request(client)["request_id"]
    client.post(f"/v1/evidence-requests/{request_id}/cancel")
    assert actions(repository, seeded_case, request_id) == [
        AuditAction.EVIDENCE_REQUESTED,
        AuditAction.EVIDENCE_CANCELLED,
    ]


def test_cancelling_can_carry_a_note(
    client: TestClient, repository, seeded_case: str
) -> None:
    """A withdrawal reason travels with the request and the trail."""
    request_id = raise_request(client, title="Contract behind the round number")["request_id"]
    response = client.post(
        f"/v1/evidence-requests/{request_id}/cancel",
        json={"note": "Client confirmed by phone"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["request"]["status"] == EvidenceRequestStatus.CANCELLED.value
    assert body["request"]["cancellation_note"] == "Client confirmed by phone"
    assert body["audit_record"]["action"] == AuditAction.EVIDENCE_CANCELLED.value
    assert "Client confirmed by phone" in body["audit_record"]["detail"]


def test_a_refused_transition_writes_nothing(
    client: TestClient, repository, seeded_case: str
) -> None:
    """A `409` is not an event: the trail records what happened, not what was tried."""
    request_id = raise_request(client)["request_id"]
    client.post(f"/v1/evidence-requests/{request_id}/resolve")
    before = actions(repository, seeded_case, request_id)
    client.post(f"/v1/evidence-requests/{request_id}/resolve")
    assert actions(repository, seeded_case, request_id) == before


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #


def test_another_firm_cannot_see_or_close_a_request(
    client: TestClient, other_client: TestClient, repository, seeded_case: str
) -> None:
    request_id = raise_request(client, title="Firm A's ask")["request_id"]
    a_case(repository, OTHER_ORG_ID, "CASE-FIRM-B", OTHER_USER.user_id)

    # Firm B's own case exists and is empty; firm A's requests are not in it.
    listed = other_client.get("/v1/evidence-requests").json()
    assert listed["case_id"] == "CASE-FIRM-B"
    assert listed["total"] == 0 and listed["requests"] == []

    # Firm A's case does not exist as far as firm B is concerned.
    assert other_client.get(
        "/v1/evidence-requests", params={"case_id": seeded_case}
    ).status_code == 404
    assert other_client.post(
        "/v1/evidence-requests", json={"title": "x", "case_id": seeded_case}
    ).status_code == 404

    # Nor does firm A's request, by id.
    for route, payload in (
        ("respond", {"response_note": "not yours"}),
        ("resolve", None),
        ("cancel", None),
    ):
        response = other_client.post(
            f"/v1/evidence-requests/{request_id}/{route}", json=payload
        )
        assert response.status_code == 404, route

    # And none of that touched it.
    stored = repository.get_evidence_request(DEMO_ORG_ID, request_id)
    assert stored is not None and stored.status is EvidenceRequestStatus.OPEN


def test_a_request_needs_an_identity(
    anonymous_client: TestClient, seeded_case: str
) -> None:
    assert anonymous_client.get("/v1/evidence-requests").status_code == 401
    assert anonymous_client.post(
        "/v1/evidence-requests", json={"title": "x"}
    ).status_code == 401
