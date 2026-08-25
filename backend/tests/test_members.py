"""Members and invitations: how a second person gets into a firm.

The flow under test is the whole loop: the owner cuts a single-use code, the
invitee presents it at signup, and from then on they see the firm's cases —
and only that firm's. The failure modes matter as much: used codes, revoked
codes, members trying to invite, and machine credentials trying anything.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import DEMO_ORG_ID
from test_api_keys import issue, with_key


def invite(client: TestClient, email: str = "junior@lahore-audit.pk") -> dict:
    response = client.post("/v1/members/invites", json={"email": email})
    assert response.status_code == 201, response.text
    return response.json()


def join(anonymous_client: TestClient, code: str, email: str) -> dict:
    response = anonymous_client.post(
        "/v1/auth/signup",
        json={"email": email, "password": "a-strong-password", "invite_code": code},
    )
    assert response.status_code == 201, response.text
    return response.json()


def signed_in(anonymous_client: TestClient, email: str) -> dict[str, str]:
    login = anonymous_client.post(
        "/v1/auth/login", json={"email": email, "password": "a-strong-password"}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


# --------------------------------------------------------------------------- #
# The happy loop
# --------------------------------------------------------------------------- #


def test_the_member_list_starts_with_the_owner(client: TestClient) -> None:
    body = client.get("/v1/members").json()

    assert body["total"] == 1
    assert body["members"][0]["role"] == "owner"
    # The fixture owner is a manufactured token with no local identity row, so
    # its email is None by design; a signed-up member's resolves (tested below).


def test_an_invitation_admits_one_person_into_the_firm(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    invitation = invite(client)
    assert invitation["code"].startswith("TZ-")
    assert invitation["accepted"] is False

    joined = join(anonymous_client, invitation["code"], "junior@lahore-audit.pk")

    assert joined["org_id"] == DEMO_ORG_ID
    assert joined["role"] == "member"

    # The new member sees the firm's case immediately...
    headers = signed_in(anonymous_client, "junior@lahore-audit.pk")
    cases = anonymous_client.get("/v1/cases", headers=headers).json()
    assert [case["case_id"] for case in cases["cases"]] == [seeded_case]

    # ...and both people now show on the member list, the newcomer's email
    # resolved from the local identity their signup created.
    members = client.get("/v1/members").json()
    assert members["total"] == 2
    assert {member["role"] for member in members["members"]} == {"owner", "member"}
    newcomer = next(m for m in members["members"] if m["role"] == "member")
    assert newcomer["email"] == "junior@lahore-audit.pk"

    # The invitation is closed and says who came through it.
    listed = client.get("/v1/members/invites").json()["invitations"][0]
    assert listed["accepted"] is True
    assert listed["accepted_by"] == joined["user_id"]


def test_a_code_is_single_use(
    client: TestClient, anonymous_client: TestClient
) -> None:
    invitation = invite(client)
    join(anonymous_client, invitation["code"], "first@lahore-audit.pk")

    second = anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "second@lahore-audit.pk",
            "password": "a-strong-password",
            "invite_code": invitation["code"],
        },
    )

    assert second.status_code == 400
    # And the refused signup left no account behind.
    refused_login = anonymous_client.post(
        "/v1/auth/login",
        json={"email": "second@lahore-audit.pk", "password": "a-strong-password"},
    )
    assert refused_login.status_code == 401


def test_a_revoked_code_admits_nobody(
    client: TestClient, anonymous_client: TestClient
) -> None:
    invitation = invite(client)

    remaining = client.delete(f"/v1/members/invites/{invitation['invite_id']}")
    assert remaining.status_code == 200
    assert remaining.json()["total"] == 0

    refused = anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "late@lahore-audit.pk",
            "password": "a-strong-password",
            "invite_code": invitation["code"],
        },
    )
    assert refused.status_code == 400


def test_a_nonsense_code_is_refused(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        "/v1/auth/signup",
        json={
            "email": "hopeful@lahore-audit.pk",
            "password": "a-strong-password",
            "invite_code": "TZ-NOPE0000",
        },
    )
    assert response.status_code == 400


def test_founding_still_needs_an_organization_name(
    anonymous_client: TestClient,
) -> None:
    response = anonymous_client.post(
        "/v1/auth/signup",
        json={"email": "founder@lahore-audit.pk", "password": "a-strong-password"},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Who may do what
# --------------------------------------------------------------------------- #


def test_a_member_can_see_the_list_but_cannot_invite(
    client: TestClient, anonymous_client: TestClient
) -> None:
    invitation = invite(client)
    join(anonymous_client, invitation["code"], "member@lahore-audit.pk")
    headers = signed_in(anonymous_client, "member@lahore-audit.pk")

    seen = anonymous_client.get("/v1/members", headers=headers)
    assert seen.status_code == 200
    assert seen.json()["total"] == 2

    refused = anonymous_client.post(
        "/v1/members/invites",
        json={"email": "friend@lahore-audit.pk"},
        headers=headers,
    )
    assert refused.status_code == 403
    assert (
        anonymous_client.get("/v1/members/invites", headers=headers).status_code == 403
    )


def test_another_organizations_invitation_cannot_be_revoked(
    client: TestClient, other_client: TestClient
) -> None:
    invitation = invite(client)

    response = other_client.delete(f"/v1/members/invites/{invitation['invite_id']}")

    assert response.status_code == 404
    assert client.get("/v1/members/invites").json()["total"] == 1


def test_keys_cannot_touch_membership(
    client: TestClient, anonymous_client: TestClient
) -> None:
    raw, _ = issue(client, scopes=("read", "write"))
    headers = with_key(anonymous_client, raw)

    assert anonymous_client.get("/v1/members", headers=headers).status_code == 403
    assert (
        anonymous_client.post(
            "/v1/members/invites",
            json={"email": "bot@lahore-audit.pk"},
            headers=headers,
        ).status_code
        == 403
    )


def test_membership_needs_an_identity_at_all(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/v1/members").status_code == 401
    assert (
        anonymous_client.post(
            "/v1/members/invites", json={"email": "x@y.pk"}
        ).status_code
        == 401
    )
