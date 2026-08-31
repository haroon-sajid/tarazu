"""The firm's own letterhead: `GET`/`PUT /v1/org-profile`.

Presentation only — nothing on this row is an authorization input and nothing
here changes a number. What the tests pin is who may change it: the letterhead
a client receives is the firm's identity rather than one auditor's preference,
so reading is any member's and writing is an owner's.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.auth import AuthenticatedUser
from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import OrgRole
from tests.conftest import DEMO_ORG_ID, join, signed_in

A_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="

JUNIOR = AuthenticatedUser(
    user_id="00000000-0000-4000-8000-0000000000f2",
    email="junior@tarazu.local",
)


@pytest.fixture()
def junior_client(
    repository: SqliteCaseRepository, storage, demo_org: str
) -> TestClient:
    """A member of the same firm who does not own it."""
    join(repository, DEMO_ORG_ID, "Tarazu Demo Firm", JUNIOR, role=OrgRole.MEMBER)
    with signed_in(repository, storage, JUNIOR) as test_client:
        yield test_client


def test_an_unfilled_profile_still_names_the_firm(client, demo_org: str) -> None:
    """A firm that has filled nothing in still has something to print."""
    body = client.get("/v1/org-profile").json()
    assert body["org_id"] == demo_org
    assert body["name"] == "Tarazu Demo Firm"
    assert body["legal_name"] is None
    assert body["logo"] is None


def test_an_owner_can_set_the_letterhead(client, demo_org: str) -> None:
    response = client.put(
        "/v1/org-profile",
        json={
            "legal_name": "Lahore Audit Associates",
            "address": "12 Gulberg III, Lahore",
            "contact_email": "partners@lahore-audit.pk",
            "registration_number": "ICAP-1234",
            "logo": A_PNG,
            "report_footer": "Prepared under ISA 500.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["legal_name"] == "Lahore Audit Associates"
    assert response.json()["logo"] == A_PNG
    assert response.json()["updated_at"]

    # And it is persisted, not just echoed.
    assert client.get("/v1/org-profile").json()["registration_number"] == "ICAP-1234"


def test_a_put_replaces_rather_than_merges(client, demo_org: str) -> None:
    """PUT semantics, like the user profile: an omitted field is cleared."""
    client.put("/v1/org-profile", json={"legal_name": "First", "phone": "+92 42 111"})
    client.put("/v1/org-profile", json={"legal_name": "Second"})

    body = client.get("/v1/org-profile").json()
    assert body["legal_name"] == "Second"
    assert body["phone"] is None


def test_a_member_can_read_but_not_change_it(junior_client, demo_org: str) -> None:
    assert junior_client.get("/v1/org-profile").status_code == 200

    denied = junior_client.put("/v1/org-profile", json={"legal_name": "Mine now"})
    assert denied.status_code == 403
    assert "owner" in denied.json()["detail"].lower()


def test_a_logo_must_be_an_inline_image(client, demo_org: str) -> None:
    response = client.put(
        "/v1/org-profile", json={"logo": "https://example.com/logo.png"}
    )
    assert response.status_code == 422


def test_each_firm_has_its_own_letterhead(client, other_client, demo_org, other_org) -> None:
    client.put("/v1/org-profile", json={"legal_name": "Firm A"})
    other_client.put("/v1/org-profile", json={"legal_name": "Firm B"})

    assert client.get("/v1/org-profile").json()["legal_name"] == "Firm A"
    assert other_client.get("/v1/org-profile").json()["legal_name"] == "Firm B"


def test_an_api_key_cannot_change_the_letterhead(client, demo_org: str) -> None:
    """`human_only`: a credential pasted into a workflow builder is not the firm."""
    created = client.post(
        "/v1/api-keys", json={"name": "n8n", "scopes": ["read", "write"]}
    )
    assert created.status_code == 201, created.text
    key = created.json()["api_key"]

    denied = client.put(
        "/v1/org-profile",
        json={"legal_name": "By a key"},
        headers={"X-API-Key": key},
    )
    assert denied.status_code == 403
