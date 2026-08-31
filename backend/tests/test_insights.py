"""`GET /v1/insights` and `GET /v1/compare`: the firm, and one period against
another.

What matters here is that the figures are the real ones — counted from the
persisted queue rather than shaped like counts — that a firm with nothing yet
gets zeros instead of an error, that neither route writes to the audit trail,
and that the tenancy boundary holds: firm A's insights are firm A's work and
nothing else's.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import (
    CaseRecord,
    CaseStatus,
    Client,
    EvidenceRequest,
    EvidenceRequestStatus,
    ReviewItem,
)
from conftest import (
    DEMO_ORG_ID,
    DEMO_USER,
    OTHER_ORG_ID,
    OTHER_USER,
    load_sample_queue,
)

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# Building a second case
#
# The fixture queue is the only realistic queue in the suite, so a second case
# is that queue again under new ids. Ids are rewritten rather than reused: both
# stores key review items and flags by their own id, and two cases sharing one
# would be a collision the test wrote, not a behaviour worth proving.
# --------------------------------------------------------------------------- #


def clone_queue(
    case_id: str,
    suffix: str,
    *,
    limit: int | None = None,
    month: str | None = None,
    strip_flags: bool = False,
    rename: dict[str, str] | None = None,
) -> list[ReviewItem]:
    """The sample queue again, under a different case."""
    items = load_sample_queue().items[:limit]
    cloned: list[ReviewItem] = []
    for item in items:
        data = item.model_dump(mode="json")
        data["case_id"] = case_id
        data["review_item_id"] = f"{data['review_item_id']}-{suffix}"
        entry = data["ledger_entry"]
        if month is not None:
            entry["date"] = f"{month}-{entry['date'][-2:]}"
        if rename and entry["party_name"] in rename:
            entry["party_name"] = rename[entry["party_name"]]
        if strip_flags:
            data["flags"] = []
        for flag in data["flags"]:
            flag["flag_id"] = f"{flag['flag_id']}-{suffix}"
        cloned.append(ReviewItem.model_validate(data))
    return cloned


def make_case(
    repository: SqliteCaseRepository,
    org_id: str,
    case_id: str,
    items: list[ReviewItem],
    *,
    client_name: str = "Haroon Textiles",
    created_by: str = DEMO_USER.user_id,
) -> str:
    repository.create_case(
        org_id,
        CaseRecord(
            case_id=case_id,
            client_name=client_name,
            status=CaseStatus.READY_FOR_REVIEW,
            created_by=created_by,
            created_at=NOW,
        ),
    )
    repository.save_review_items(org_id, case_id, items)
    return case_id


def may_period(repository: SqliteCaseRepository) -> str:
    """An earlier, quieter period for the same client: six rows, no flags.

    One party is renamed to a business June never saw, and another is spelled
    the way a different bookkeeper would spell it — "KARACHI PACKAGING COMPANY"
    for "Karachi Packaging Co." — so the party diff has both something to find
    and something it must not report.
    """
    return make_case(
        repository,
        DEMO_ORG_ID,
        "CASE-2026-05-STX",
        clone_queue(
            "CASE-2026-05-STX",
            "MAY",
            limit=6,
            month="2026-05",
            strip_flags=True,
            rename={
                "Ravi Logistics Pvt Ltd": "Lahore Cotton Mills (Pvt) Ltd",
                "Karachi Packaging Co.": "KARACHI PACKAGING COMPANY",
            },
        ),
    )


# --------------------------------------------------------------------------- #
# GET /v1/insights
# --------------------------------------------------------------------------- #


def test_insights_counts_the_firms_one_case(
    client: TestClient, seeded_case: str
) -> None:
    """Every headline figure, against the fixture's known contents."""
    response = client.get("/v1/insights")

    assert response.status_code == 200
    body = response.json()
    assert body["case_count"] == 1
    assert body["client_count"] == 1
    assert body["total_review_items"] == 10
    assert body["pending_items"] == 8  # the fixture ships 1 approved + 1 rejected
    assert body["total_flags"] == 8
    # Both decided items happen to carry no flags, so nothing is reviewed yet.
    assert body["unreviewed_flags"] == 8
    assert body["open_evidence_requests"] == 0
    assert body["estimated_hours_saved"] == 0.7  # 10 items x 4 minutes


def test_insights_for_a_firm_with_nothing_yet_is_zeros_not_a_404(
    other_client: TestClient, seeded_case: str
) -> None:
    """Firm B has no cases. That is an answer this screen can render."""
    response = other_client.get("/v1/insights")

    assert response.status_code == 200
    assert response.json() == {
        "case_count": 0,
        "client_count": 0,
        "total_review_items": 0,
        "pending_items": 0,
        "total_flags": 0,
        "unreviewed_flags": 0,
        "open_evidence_requests": 0,
        "estimated_hours_saved": 0.0,
        "vendors": [],
        "rules": [],
        "months": [],
    }


def test_vendors_group_by_party_and_lead_with_the_flags(
    client: TestClient, seeded_case: str
) -> None:
    vendors = client.get("/v1/insights").json()["vendors"]

    # Every party appears, flagged or not; the order is flags first, then
    # amount, so the two-flag parties sort by size.
    assert [vendor["party_name"] for vendor in vendors] == [
        "Hussain Brothers & Sons",
        "Indus Power Solutions",
        "Karachi Packaging Co.",
        "Sialkot Metal Works",
        "Gulberg Traders (Pvt) Ltd",
        "Shalimar Trading Co",
        "Ravi Logistics Pvt Ltd",
        "Al-Habib Stationers",
    ]
    assert vendors[0] == {
        "party_name": "Hussain Brothers & Sons",
        "flag_count": 4,
        "high": 4,
        "medium": 0,
        "low": 0,
        "rules": ["near-limit", "structuring"],  # two each, so alphabetical
        "case_count": 1,
        "item_count": 2,
        "total_amount": "99,000.00",
        "currency": "PKR",
    }
    quiet = next(v for v in vendors if v["party_name"] == "Sialkot Metal Works")
    assert quiet["flag_count"] == 0 and quiet["rules"] == []
    assert quiet["total_amount"] == "312,880.00"


def test_rules_are_counted_across_the_firm_and_track_what_was_reviewed(
    client: TestClient, seeded_case: str
) -> None:
    listed = client.get("/v1/insights").json()["rules"]

    assert listed == [
        {"rule_id": "duplicate-invoice", "count": 2, "severity": "high", "reviewed": 0},
        {"rule_id": "near-limit", "count": 2, "severity": "high", "reviewed": 0},
        {"rule_id": "structuring", "count": 2, "severity": "high", "reviewed": 0},
        {"rule_id": "round-number", "count": 1, "severity": "low", "reviewed": 0},
        {"rule_id": "weekend-entry", "count": 1, "severity": "medium", "reviewed": 0},
    ]

    # Deciding the item carrying the weekend-entry and round-number flags moves
    # both rules' `reviewed`, and takes two flags out of the outstanding pile.
    item_id = next(
        item["review_item_id"]
        for item in client.get("/v1/review-items").json()["items"]
        if any(flag["rule_id"] == "round-number" for flag in item["flags"])
    )
    assert client.post(f"/v1/review-items/{item_id}/approve", json={}).status_code == 200

    body = client.get("/v1/insights").json()
    reviewed = {rule["rule_id"]: rule["reviewed"] for rule in body["rules"]}
    assert reviewed == {
        "duplicate-invoice": 0,
        "near-limit": 0,
        "structuring": 0,
        "round-number": 1,
        "weekend-entry": 1,
    }
    assert body["total_flags"] == 8
    assert body["unreviewed_flags"] == 6


def test_months_bucket_on_the_ledger_date_oldest_first(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    may_period(repository)

    months = client.get("/v1/insights").json()["months"]

    assert months == [
        {
            "month": "2026-05",
            "item_count": 6,
            "flag_count": 0,
            "total_amount": "589,050.00",
            "currency": "PKR",
        },
        {
            "month": "2026-06",
            "item_count": 10,
            "flag_count": 8,
            "total_amount": "2,685,830.00",
            "currency": "PKR",
        },
    ]


def test_insights_span_every_case_in_the_firm(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    may_period(repository)

    body = client.get("/v1/insights").json()

    assert body["case_count"] == 2
    assert body["total_review_items"] == 16
    assert body["pending_items"] == 12  # 8 in June, 4 in May
    assert body["total_flags"] == 8  # the May clone carries none
    assert body["estimated_hours_saved"] == 1.1  # 16 items x 4 minutes
    # The same client both periods, so one business, not two.
    assert body["client_count"] == 1
    hussain = next(
        vendor
        for vendor in body["vendors"]
        if vendor["party_name"] == "Hussain Brothers & Sons"
    )
    assert hussain["case_count"] == 2
    assert hussain["item_count"] == 4


def test_client_count_covers_registered_clients_without_double_counting(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """A registered client the firm already ran a case for is one business."""
    repository.create_client(
        DEMO_ORG_ID,
        Client(
            client_id="CL-1",
            name="Haroon Textiles (Pvt) Ltd",
            created_by=DEMO_USER.user_id,
            created_at=NOW,
        ),
    )
    assert client.get("/v1/insights").json()["client_count"] == 1

    repository.create_client(
        DEMO_ORG_ID,
        Client(
            client_id="CL-2",
            name="Sialkot Metal Works",
            created_by=DEMO_USER.user_id,
            created_at=NOW,
        ),
    )
    assert client.get("/v1/insights").json()["client_count"] == 2


def test_only_unclosed_evidence_requests_count_as_open(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    repository.save_evidence_request(
        DEMO_ORG_ID,
        EvidenceRequest(
            request_id="ER-open",
            case_id=seeded_case,
            title="Invoice for the 14 June payment",
            requested_by=DEMO_USER.user_id,
            requested_at=NOW,
        ),
    )
    repository.save_evidence_request(
        DEMO_ORG_ID,
        EvidenceRequest(
            request_id="ER-done",
            case_id=seeded_case,
            title="Bank confirmation",
            status=EvidenceRequestStatus.RESOLVED,
            requested_by=DEMO_USER.user_id,
            requested_at=NOW,
            closed_by=DEMO_USER.user_id,
            closed_at=NOW,
        ),
    )

    assert client.get("/v1/insights").json()["open_evidence_requests"] == 1


def test_insights_write_nothing_to_the_audit_trail(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """A read is a read. Looking at your own numbers is not an auditable act."""
    assert client.get("/v1/insights").status_code == 200
    assert client.get(
        "/v1/compare", params={"left": seeded_case, "right": seeded_case}
    ).status_code == 200

    assert repository.list_audit(DEMO_ORG_ID, seeded_case) == []


# --------------------------------------------------------------------------- #
# Tenancy
# --------------------------------------------------------------------------- #


def test_one_firms_insights_never_include_anothers(
    client: TestClient,
    other_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    make_case(
        repository,
        OTHER_ORG_ID,
        "CASE-OTHER-FIRM",
        clone_queue(
            "CASE-OTHER-FIRM",
            "B",
            limit=3,
            rename={"Gulberg Traders (Pvt) Ltd": "Quetta Dry Fruits"},
        ),
        client_name="Second Firm's Client",
        created_by=OTHER_USER.user_id,
    )

    mine = client.get("/v1/insights").json()
    assert mine["case_count"] == 1
    assert mine["total_review_items"] == 10
    assert "Quetta Dry Fruits" not in [v["party_name"] for v in mine["vendors"]]

    theirs = other_client.get("/v1/insights").json()
    assert theirs["case_count"] == 1
    assert theirs["total_review_items"] == 3
    assert "Quetta Dry Fruits" in [v["party_name"] for v in theirs["vendors"]]


# --------------------------------------------------------------------------- #
# GET /v1/compare
# --------------------------------------------------------------------------- #


def test_compare_puts_the_two_periods_side_by_side(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    may = may_period(repository)

    response = client.get("/v1/compare", params={"left": may, "right": seeded_case})

    assert response.status_code == 200
    body = response.json()
    assert body["left"]["case_id"] == may
    assert body["left"]["total_review_items"] == 6
    assert body["left"]["pending_items"] == 4
    assert body["left"]["flagged_items"] == 0
    assert body["right"]["case_id"] == seeded_case
    assert body["right"]["total_review_items"] == 10
    assert body["right"]["flagged_items"] == 5

    assert body["deltas"] == [
        {"label": "Review items", "left": "6", "right": "10", "change": "+4", "notable": True},
        {"label": "Matched", "left": "5", "right": "8", "change": "+3", "notable": True},
        {"label": "Partial matches", "left": "1", "right": "1", "change": "", "notable": False},
        {"label": "Unmatched", "left": "0", "right": "1", "change": "+1", "notable": True},
        {"label": "Pending decisions", "left": "4", "right": "8", "change": "+4", "notable": True},
        {"label": "Flags raised", "left": "0", "right": "8", "change": "+8", "notable": True},
        {"label": "High-severity flags", "left": "0", "right": "6", "change": "+6", "notable": True},
        {
            "label": "Total ledger amount",
            "left": "PKR 589,050.00",
            "right": "PKR 2,685,830.00",
            "change": "+356.0%",
            "notable": True,
        },
    ]


def test_compare_names_the_parties_that_came_and_went(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    may = may_period(repository)

    body = client.get(
        "/v1/compare", params={"left": may, "right": seeded_case}
    ).json()

    assert body["new_parties"] == [
        "Indus Power Solutions",
        "Ravi Logistics Pvt Ltd",
        "Shalimar Trading Co",
        "Sialkot Metal Works",
    ]
    assert body["dropped_parties"] == ["Lahore Cotton Mills (Pvt) Ltd"]
    # "KARACHI PACKAGING COMPANY" and "Karachi Packaging Co." are one business,
    # so the diff must not report either as news.
    assert not [
        name
        for name in body["new_parties"] + body["dropped_parties"]
        if "KARACHI" in name.upper()
    ]


def test_comparing_a_period_with_itself_shows_no_movement(
    client: TestClient, seeded_case: str
) -> None:
    body = client.get(
        "/v1/compare", params={"left": seeded_case, "right": seeded_case}
    ).json()

    assert all(delta["change"] == "" for delta in body["deltas"])
    assert not any(delta["notable"] for delta in body["deltas"])
    assert body["new_parties"] == [] and body["dropped_parties"] == []


def test_comparing_a_shrinking_period_is_notable_in_both_directions(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """A period with far less in it is as much a question as one with more."""
    may = may_period(repository)

    body = client.get(
        "/v1/compare", params={"left": seeded_case, "right": may}
    ).json()

    by_label = {delta["label"]: delta for delta in body["deltas"]}
    assert by_label["Review items"] == {
        "label": "Review items",
        "left": "10",
        "right": "6",
        "change": "-4",
        "notable": True,
    }
    # Flags falling is not "flags up", but it is still a big swing.
    assert by_label["Flags raised"]["change"] == "-8"
    assert by_label["Flags raised"]["notable"] is True


def test_comparing_an_unknown_case_is_not_found(
    client: TestClient, seeded_case: str
) -> None:
    response = client.get(
        "/v1/compare", params={"left": seeded_case, "right": "CASE-invented"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "No case with id 'CASE-invented'."}


def test_comparing_another_firms_case_is_not_found(
    other_client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """Real, and someone else's. Identical to a case that never existed."""
    make_case(
        repository,
        OTHER_ORG_ID,
        "CASE-OTHER-FIRM",
        clone_queue("CASE-OTHER-FIRM", "B", limit=3),
        client_name="Second Firm's Client",
        created_by=OTHER_USER.user_id,
    )

    response = other_client.get(
        "/v1/compare", params={"left": "CASE-OTHER-FIRM", "right": seeded_case}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": f"No case with id {seeded_case!r}."}


def test_compare_needs_both_sides(client: TestClient, seeded_case: str) -> None:
    assert client.get("/v1/compare", params={"left": seeded_case}).status_code == 422


def test_insights_and_compare_require_a_caller(
    anonymous_client: TestClient, seeded_case: str
) -> None:
    assert anonymous_client.get("/v1/insights").status_code == 401
    assert (
        anonymous_client.get(
            "/v1/compare", params={"left": seeded_case, "right": seeded_case}
        ).status_code
        == 401
    )
