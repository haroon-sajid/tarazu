"""Two firms, one database, and nothing crossing between them.

A tenant is one accounting firm. These tests put two of them in the same store
and then try, from firm B, every route that could return firm A's data. Nothing
here is mocked to keep them apart: `client` and `other_client` differ only in
which user the token identifies, and the organization each request acts inside
is resolved by the real `get_current_org` from real `organization_members` rows.

**Every cross-tenant attempt must be `404`, never `403`.** A `403` on a case id
that exists is itself a disclosure — it tells a stranger that some firm on this
platform has a case `CASE-abc123` and an item `RI-0007`. From outside the
organization, those rows do not exist, and the API says exactly that. `403` is
reserved for the different situation of an authenticated user who belongs to no
organization at all, where there is no resource in question to leak.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser
from app.core.sqlite_store import SqliteCaseRepository
from app.main import app
from app.shared.schemas import ReviewDecision
from conftest import DEMO_ORG_ID, OTHER_ORG_ID, OTHER_USER, signed_in


def a_pdf(text: str = "STATEMENT") -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 120), text, fontsize=16)
    data = document.tobytes()
    document.close()
    return data


def a_ledger() -> bytes:
    import pandas as pd

    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "Date": ["02/06/2026"],
            "Party Name": ["Gulberg Traders (Pvt) Ltd"],
            "Amount": [284000],
            "Particulars": ["Yarn purchase"],
        }
    ).to_excel(buffer, index=False)
    return buffer.getvalue()


def upload(test_client: TestClient, client_name: str) -> str:
    """Run a real upload through the pipeline and return the case id."""
    response = test_client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
        data={"client_name": client_name},
    )
    assert response.status_code == 201, response.text
    return response.json()["case_id"]


def any_item_id(repository: SqliteCaseRepository, case_id: str) -> str:
    items = repository.list_review_items(DEMO_ORG_ID, case_id)
    assert items, "firm A's case should have a review queue to try to reach"
    return items[0].review_item_id


def pending_item_id(repository: SqliteCaseRepository, case_id: str) -> str:
    for item in repository.list_review_items(DEMO_ORG_ID, case_id):
        if item.decision is ReviewDecision.PENDING:
            return item.review_item_id
    pytest.fail("firm A's case should have a pending item")


# --------------------------------------------------------------------------- #
# Firm B cannot reach firm A's case
# --------------------------------------------------------------------------- #


def test_another_firms_case_id_is_not_found(
    other_client: TestClient, seeded_case: str
) -> None:
    """Naming firm A's case explicitly gets the same answer as naming a fiction."""
    real = other_client.get("/v1/review-items", params={"case_id": seeded_case})
    invented = other_client.get("/v1/review-items", params={"case_id": "CASE-invented"})

    assert real.status_code == 404
    assert invented.status_code == 404
    # Identical shape, so the response cannot be used to tell one from the other.
    assert real.json()["detail"].replace(seeded_case, "X") == invented.json()[
        "detail"
    ].replace("CASE-invented", "X")


def test_another_firms_dashboard_is_not_found(
    other_client: TestClient, seeded_case: str
) -> None:
    response = other_client.get("/v1/dashboard", params={"case_id": seeded_case})
    assert response.status_code == 404
    assert "Haroon" not in response.text


def test_approving_another_firms_item_is_not_found(
    other_client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = pending_item_id(repository, seeded_case)

    response = other_client.post(f"/v1/review-items/{item_id}/approve", json={})

    assert response.status_code == 404
    # And the decision did not happen.
    assert (
        repository.get_review_item(DEMO_ORG_ID, item_id).decision
        is ReviewDecision.PENDING
    )


def test_rejecting_another_firms_item_is_not_found(
    other_client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = pending_item_id(repository, seeded_case)

    response = other_client.post(
        f"/v1/review-items/{item_id}/reject", json={"reason": "Not mine to reject."}
    )

    assert response.status_code == 404
    assert (
        repository.get_review_item(DEMO_ORG_ID, item_id).decision
        is ReviewDecision.PENDING
    )


def test_a_decided_item_in_another_firm_is_still_not_found(
    other_client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """A `409` would confirm the item exists and was already decided. `404` does not."""
    decided = next(
        item
        for item in repository.list_review_items(DEMO_ORG_ID, seeded_case)
        if item.decision is not ReviewDecision.PENDING
    )
    response = other_client.post(
        f"/v1/review-items/{decided.review_item_id}/approve", json={}
    )
    assert response.status_code == 404


def test_another_firms_item_audit_trail_is_not_found(
    other_client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    item_id = any_item_id(repository, seeded_case)

    response = other_client.get(f"/v1/review-items/{item_id}/audit")

    assert response.status_code == 404
    assert response.json() == {"detail": f"No review item with id {item_id!r}."}


def test_a_decision_in_one_firm_writes_no_trail_the_other_can_read(
    client: TestClient,
    other_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    item_id = pending_item_id(repository, seeded_case)
    assert client.post(f"/v1/review-items/{item_id}/approve", json={"note": "ok"}).status_code == 200

    assert other_client.get(f"/v1/review-items/{item_id}/audit").status_code == 404
    assert repository.list_audit(OTHER_ORG_ID, seeded_case) == []
    assert repository.list_audit(DEMO_ORG_ID, seeded_case), "A's own trail is intact"


def test_firm_b_with_no_cases_is_told_to_upload_not_shown_firm_as(
    other_client: TestClient, seeded_case: str
) -> None:
    """With A's case the only one in the database, B still has no cases."""
    for path in ("/v1/review-items", "/v1/dashboard"):
        response = other_client.get(path)
        assert response.status_code == 404, path
        assert "upload" in response.json()["detail"].lower()


# --------------------------------------------------------------------------- #
# The whole pipeline, twice, in one database
# --------------------------------------------------------------------------- #


def test_an_upload_by_one_firm_is_invisible_to_the_other(
    client: TestClient,
    other_client: TestClient,
    repository: SqliteCaseRepository,
    demo_org: str,
    other_org: str,
    demo_mode,
) -> None:
    """A uploads and gets a queue. B lists, and sees nothing at all."""
    case_id = upload(client, "Haroon Textiles")

    mine = client.get("/v1/review-items").json()
    assert mine["case_id"] == case_id
    assert mine["total"] > 0

    listed = other_client.get("/v1/review-items")
    assert listed.status_code == 404
    assert case_id not in listed.text

    named = other_client.get("/v1/review-items", params={"case_id": case_id})
    assert named.status_code == 404
    assert "Haroon" not in named.text


def test_two_firms_uploads_do_not_mix(
    client: TestClient,
    other_client: TestClient,
    demo_org: str,
    other_org: str,
    demo_mode,
) -> None:
    """Each firm's dashboard counts its own queue and no one else's."""
    a_case = upload(client, "Haroon Textiles")
    b_case = upload(other_client, "Karachi Metals Ltd")

    assert a_case != b_case

    a_dashboard = client.get("/v1/dashboard").json()
    b_dashboard = other_client.get("/v1/dashboard").json()

    assert a_dashboard["case_id"] == a_case
    assert a_dashboard["client_name"] == "Haroon Textiles"
    assert b_dashboard["case_id"] == b_case
    assert b_dashboard["client_name"] == "Karachi Metals Ltd"

    # Neither total includes the other's items.
    a_items = client.get("/v1/review-items").json()["items"]
    b_items = other_client.get("/v1/review-items").json()["items"]
    assert a_dashboard["total_review_items"] == len(a_items)
    assert b_dashboard["total_review_items"] == len(b_items)
    assert {item["case_id"] for item in a_items} == {a_case}
    assert {item["case_id"] for item in b_items} == {b_case}


def test_the_default_case_is_never_another_firms_most_recent(
    client: TestClient,
    other_client: TestClient,
    demo_org: str,
    other_org: str,
    demo_mode,
) -> None:
    """`latest_case_id` is per-organization, so "my most recent" cannot drift."""
    upload(client, "Haroon Textiles")
    b_case = upload(other_client, "Karachi Metals Ltd")
    a_case = upload(client, "Haroon Textiles")  # A uploads again, last

    assert other_client.get("/v1/review-items").json()["case_id"] == b_case
    assert client.get("/v1/review-items").json()["case_id"] == a_case


def test_each_firm_decides_only_its_own_items(
    client: TestClient,
    other_client: TestClient,
    repository: SqliteCaseRepository,
    demo_org: str,
    other_org: str,
    demo_mode,
) -> None:
    a_case = upload(client, "Haroon Textiles")
    upload(other_client, "Karachi Metals Ltd")

    a_item = client.get("/v1/review-items").json()["items"][0]["review_item_id"]

    assert other_client.post(f"/v1/review-items/{a_item}/approve", json={}).status_code == 404
    assert client.post(f"/v1/review-items/{a_item}/approve", json={}).status_code == 200

    trail = repository.list_audit(DEMO_ORG_ID, a_case)
    assert trail[-1].item_id == a_item
    assert repository.list_audit(OTHER_ORG_ID, a_case) == []


# --------------------------------------------------------------------------- #
# Belonging to no organization at all
# --------------------------------------------------------------------------- #


ORPHAN = AuthenticatedUser(
    user_id="99999999-9999-4999-8999-999999999999", email="nobody@nowhere.local"
)


@pytest.fixture()
def orphan_client(repository, storage) -> TestClient:
    """Authenticated, but a member of nothing. Not the same as a stranger."""
    with signed_in(repository, storage, ORPHAN) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/review-items"),
        ("get", "/v1/dashboard"),
        ("post", "/v1/review-items/RI-0002/approve"),
        ("get", "/v1/review-items/RI-0002/audit"),
    ],
)
def test_a_user_in_no_organization_gets_403_and_no_data(
    orphan_client: TestClient, seeded_case: str, method: str, path: str
) -> None:
    """403 is about the caller, not about the resource, so it discloses nothing.

    There is no case id in the request and none in the response: the request
    never gets as far as naming a row, which is why this one is allowed to be a
    403 while every cross-tenant lookup is a 404.
    """
    call = getattr(orphan_client, method)
    response = call(path, json={}) if method == "post" else call(path)
    assert response.status_code == 403
    assert "organization" in response.json()["detail"]
    assert seeded_case not in response.text


# --------------------------------------------------------------------------- #
# Signup makes a tenant
# --------------------------------------------------------------------------- #


def test_signup_creates_a_user_an_organization_and_an_owner(
    anonymous_client: TestClient, repository: SqliteCaseRepository
) -> None:
    response = anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "partner@lahore-audit.pk",
            "password": "a-long-enough-password",
            "organization_name": "Lahore Audit Associates",
        },
    )
    assert response.status_code == 201
    body = response.json()

    assert body["role"] == "owner"
    assert body["organization_name"] == "Lahore Audit Associates"

    organization = repository.get_organization(body["org_id"])
    assert organization is not None and organization.name == "Lahore Audit Associates"

    membership = repository.get_membership(body["user_id"])
    assert membership is not None
    assert membership.org_id == body["org_id"]
    assert membership.role.value == "owner"


def test_signup_cannot_name_its_own_organization_id(
    anonymous_client: TestClient, demo_org: str
) -> None:
    """Joining an existing firm is not something a signup body can ask for."""
    response = anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "intruder@example.com",
            "password": "a-long-enough-password",
            "organization_name": "Intruders LLP",
            "org_id": DEMO_ORG_ID,
        },
    )
    # `extra="forbid"` on every shared schema: the unknown key is refused
    # outright rather than quietly dropped.
    assert response.status_code == 422


def test_the_same_email_cannot_sign_up_twice(anonymous_client: TestClient) -> None:
    body = {
        "email": "partner@lahore-audit.pk",
        "password": "a-long-enough-password",
        "organization_name": "Lahore Audit Associates",
    }
    assert anonymous_client.post("/v1/auth/signup", json=body).status_code == 201
    assert anonymous_client.post("/v1/auth/signup", json=body).status_code == 409


def test_a_signed_up_user_sees_their_own_empty_workspace(
    anonymous_client: TestClient, seeded_case: str
) -> None:
    """A brand-new firm's first request must not land in whoever was here first."""
    signup = anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "partner@lahore-audit.pk",
            "password": "a-long-enough-password",
            "organization_name": "Lahore Audit Associates",
        },
    ).json()
    token = anonymous_client.post(
        "/v1/auth/login",
        json={"email": "partner@lahore-audit.pk", "password": "a-long-enough-password"},
    ).json()["access_token"]

    response = anonymous_client.get(
        "/v1/review-items", headers={"Authorization": f"Bearer {token}"}
    )

    assert signup["org_id"] != DEMO_ORG_ID
    assert response.status_code == 404
    assert "upload" in response.json()["detail"].lower()
    assert seeded_case not in response.text


def test_login_is_identical_for_a_wrong_password_and_an_unknown_email(
    anonymous_client: TestClient,
) -> None:
    anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "partner@lahore-audit.pk",
            "password": "a-long-enough-password",
            "organization_name": "Lahore Audit Associates",
        },
    )
    wrong = anonymous_client.post(
        "/v1/auth/login",
        json={"email": "partner@lahore-audit.pk", "password": "not-the-password"},
    )
    unknown = anonymous_client.post(
        "/v1/auth/login", json={"email": "nobody@nowhere.pk", "password": "whatever-x"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_the_seeded_demo_auditor_still_works(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """The one user who predates organizations is in the default one."""
    assert client.get("/v1/review-items").json()["case_id"] == seeded_case

    membership = repository.get_membership("00000000-0000-4000-8000-000000000001")
    assert membership is not None
    assert membership.org_id == DEMO_ORG_ID


def test_the_demo_auditor_is_joined_to_the_default_org_on_first_use(
    client: TestClient, repository: SqliteCaseRepository, demo_mode
) -> None:
    """Even in a store where nothing has created that membership yet."""
    assert repository.get_membership("00000000-0000-4000-8000-000000000001") is None

    upload(client, "Haroon Textiles")

    membership = repository.get_membership("00000000-0000-4000-8000-000000000001")
    assert membership is not None
    assert membership.org_id == DEMO_ORG_ID
    assert membership.role.value == "owner"


def test_a_second_firms_user_is_not_bootstrapped_into_the_default_org(
    repository: SqliteCaseRepository, other_client: TestClient
) -> None:
    """Only the seeded demo identity gets that courtesy, and only into its own org."""
    membership = repository.get_membership(OTHER_USER.user_id)
    assert membership is not None
    assert membership.org_id == OTHER_ORG_ID
