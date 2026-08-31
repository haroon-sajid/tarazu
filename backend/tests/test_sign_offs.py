"""Maker-checker: a second person signs a finished engagement off.

Every test here is about a refusal, because that is what the feature is. A
sign-off adds a gate and can never open one: it approves nothing, it cannot be
recorded while anything is still pending, and the person who made the decisions
is precisely the person who may not sign them off.

The gate is opt-in per client (`ClientRuleConfig.require_sign_off`), so a firm
that does not work this way is unaffected — which is also why the default
answer to "is a sign-off required" is no.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser
from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import AuditAction, CaseStatus, OrgRole
from tests.conftest import DEMO_ORG_ID, join, signed_in

#: A colleague at the same firm who decides nothing. The second pair of eyes.
PARTNER = AuthenticatedUser(
    user_id="00000000-0000-4000-8000-0000000000f1",
    email="partner@tarazu.local",
)


@pytest.fixture()
def partner_client(
    repository: SqliteCaseRepository, storage, demo_org: str
) -> TestClient:
    join(repository, DEMO_ORG_ID, "Tarazu Demo Firm", PARTNER, role=OrgRole.MEMBER)
    with signed_in(repository, storage, PARTNER) as test_client:
        yield test_client


def _decide_everything(client: TestClient, case_id: str) -> tuple[int, int, int]:
    """Approve everything still pending. Returns (total, approved, rejected).

    The seeded queue already carries decisions of its own — including a
    rejection — so the counts are read back rather than assumed: what the
    sign-off records is the state of the case, not the state this helper left.
    """
    items = client.get(f"/v1/review-items?case_id={case_id}").json()["items"]
    for item in items:
        if item["decision"] == "pending":
            approved = client.post(
                f"/v1/review-items/{item['review_item_id']}/approve", json={}
            )
            assert approved.status_code == 200, approved.text

    decided = client.get(f"/v1/review-items?case_id={case_id}").json()["items"]
    return (
        len(decided),
        sum(1 for item in decided if item["decision"] == "approved"),
        sum(1 for item in decided if item["decision"] == "rejected"),
    )


def test_a_case_with_pending_items_cannot_be_signed_off(
    partner_client, seeded_case: str
) -> None:
    response = partner_client.post("/v1/sign-offs", json={"case_id": seeded_case})
    assert response.status_code == 409
    assert "await a decision" in response.json()["detail"]


def test_the_person_who_decided_cannot_sign_their_own_work_off(
    client, seeded_case: str
) -> None:
    """The whole point of a second pair of eyes."""
    _decide_everything(client, seeded_case)

    response = client.post("/v1/sign-offs", json={"case_id": seeded_case})
    assert response.status_code == 409
    assert "cannot also sign it off" in response.json()["detail"]


def test_a_colleague_can_sign_a_fully_decided_case_off(
    client, partner_client, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    total, approved, rejected = _decide_everything(client, seeded_case)

    response = partner_client.post(
        "/v1/sign-offs", json={"case_id": seeded_case, "note": "Reviewed the flags."}
    )
    assert response.status_code == 201, response.text
    sign_off = response.json()["sign_off"]

    assert sign_off["signed_by"] == PARTNER.user_id
    assert sign_off["item_count"] == total
    assert sign_off["approved_count"] == approved
    assert sign_off["rejected_count"] == rejected
    assert approved + rejected == total, "a signed case has nothing pending"
    assert response.json()["audit_record"]["action"] == AuditAction.CASE_SIGNED_OFF.value

    # A signed engagement is `approved` — reviewed end to end, not yet reported.
    assert repository.get_case(DEMO_ORG_ID, seeded_case).status is CaseStatus.APPROVED


def test_sign_offs_are_listed_with_whether_one_is_required(
    client, partner_client, seeded_case: str
) -> None:
    listing = client.get(f"/v1/sign-offs?case_id={seeded_case}").json()
    assert listing["total"] == 0
    # A case with no client requires nothing: the firm opts in per client.
    assert listing["required"] is False
    assert listing["satisfied"] is False

    _decide_everything(client, seeded_case)
    partner_client.post("/v1/sign-offs", json={"case_id": seeded_case})

    after = client.get(f"/v1/sign-offs?case_id={seeded_case}").json()
    assert after["total"] == 1
    assert after["satisfied"] is True


def test_a_sign_off_cannot_be_changed_or_removed(
    client, partner_client, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """Append-only, like the trail and the reports: it is somebody's signature."""
    from app.core.sqlite_store import SignOffImmutable

    _decide_everything(client, seeded_case)
    partner_client.post("/v1/sign-offs", json={"case_id": seeded_case})

    with pytest.raises(SignOffImmutable):
        repository._write(
            [("update sign_offs set note = ? where case_id = ?", ("edited", seeded_case))]
        )
    with pytest.raises(SignOffImmutable):
        repository._write([("delete from sign_offs where case_id = ?", (seeded_case,))])


def test_a_case_with_no_items_cannot_be_signed_off(
    partner_client, repository: SqliteCaseRepository, demo_org: str
) -> None:
    from datetime import datetime, timezone

    from app.shared.schemas import CaseRecord

    repository.create_case(
        demo_org,
        CaseRecord(
            case_id="CASE-empty",
            client_name="Nobody",
            created_by="tester",
            created_at=datetime.now(timezone.utc),
        ),
    )
    response = partner_client.post("/v1/sign-offs", json={"case_id": "CASE-empty"})
    assert response.status_code == 409
    assert "no review items" in response.json()["detail"]


def test_another_firm_cannot_sign_off_or_read(
    client, other_client, seeded_case: str
) -> None:
    _decide_everything(client, seeded_case)

    assert (
        other_client.post("/v1/sign-offs", json={"case_id": seeded_case}).status_code
        == 404
    )
    assert (
        other_client.get(f"/v1/sign-offs?case_id={seeded_case}").status_code == 404
    )
