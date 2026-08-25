"""API keys: an organization's machine credentials, and their limits.

These run against the real routes and the real store. A key created through
`POST /v1/api-keys` is then presented as `X-API-Key` on the ordinary endpoints,
exactly as n8n or a curl would — nothing about the authentication path is stubbed.

Four properties get the most attention here, because they are the ones that turn
an integration feature into an incident when they slip:

1. The raw key is returned once and is nowhere else — no listing, no database
   column, no log line.
2. A key reaches its own organization's data and no other's, exactly like the
   person who created it.
3. Scopes actually restrain: a read-only key cannot approve.
4. The audit trail names the key, so "which integration did this" is answerable.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.core.api_keys import KEY_SCHEME, hash_api_key, mint_api_key
from app.core.sqlite_store import SqliteCaseRepository
from app.shared.schemas import ActorType, ReviewDecision
from conftest import DEMO_ORG_ID, OTHER_ORG_ID
from test_tenancy import a_ledger, a_pdf, pending_item_id


def issue(
    test_client: TestClient, name: str = "n8n integration", scopes=("read",)
) -> tuple[str, dict]:
    """Create a key as a signed-in human. Returns `(raw_key, summary)`."""
    response = test_client.post(
        "/v1/api-keys", json={"name": name, "scopes": list(scopes)}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["api_key"], body["key"]


def with_key(test_client: TestClient, raw_key: str) -> dict[str, str]:
    return {"X-API-Key": raw_key}


# --------------------------------------------------------------------------- #
# Minting
# --------------------------------------------------------------------------- #


def test_a_new_key_has_the_documented_shape() -> None:
    minted = mint_api_key()

    assert minted.raw.startswith(KEY_SCHEME)
    assert len(minted.raw) == len(KEY_SCHEME) + 32
    assert int(minted.raw[len(KEY_SCHEME) :], 16) >= 0, "the tail is 32 hex characters"
    assert minted.prefix == minted.raw[: len(KEY_SCHEME) + 8]
    assert minted.key_hash == hash_api_key(minted.raw)
    assert len(minted.key_hash) == 64


def test_two_keys_are_never_the_same() -> None:
    keys = {mint_api_key().raw for _ in range(50)}
    assert len(keys) == 50


def test_creating_a_key_returns_it_once_with_a_warning(client: TestClient) -> None:
    response = client.post(
        "/v1/api-keys", json={"name": "n8n integration", "scopes": ["read", "write"]}
    )
    assert response.status_code == 201
    body = response.json()

    assert body["api_key"].startswith(KEY_SCHEME)
    assert "once" in body["message"].lower()
    assert body["key"]["name"] == "n8n integration"
    assert body["key"]["scopes"] == ["read", "write"]
    assert body["key"]["revoked"] is False
    assert body["key"]["last_used_at"] is None
    # The summary beside it is already the safe shape: no secret, no digest.
    assert "api_key" not in body["key"]
    assert "key_hash" not in body["key"]


def test_a_key_defaults_to_read_only(client: TestClient) -> None:
    """Least privilege. A key that can approve should have to say so."""
    response = client.post("/v1/api-keys", json={"name": "reporting"})
    assert response.status_code == 201
    assert response.json()["key"]["scopes"] == ["read"]


def test_scopes_are_stored_in_a_stable_order(client: TestClient) -> None:
    _, summary = issue(client, scopes=("write", "read", "write"))
    assert summary["scopes"] == ["read", "write"]


def test_a_nonsense_scope_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/api-keys", json={"name": "sneaky", "scopes": ["admin"]}
    )
    assert response.status_code == 422


def test_a_key_needs_at_least_one_scope(client: TestClient) -> None:
    assert client.post("/v1/api-keys", json={"name": "inert", "scopes": []}).status_code == 422


# --------------------------------------------------------------------------- #
# The raw key is nowhere but that one response
# --------------------------------------------------------------------------- #


def test_the_raw_key_is_never_in_a_listing(client: TestClient) -> None:
    raw, _ = issue(client)

    listing = client.get("/v1/api-keys")

    assert listing.status_code == 200
    assert raw not in listing.text
    assert "key_hash" not in listing.text
    for key in listing.json()["keys"]:
        assert set(key) == {
            "key_id", "name", "key_prefix", "scopes", "created_by",
            "created_at", "last_used_at", "revoked_at", "revoked",
        }


def test_the_raw_key_is_never_in_the_database(
    client: TestClient, repository: SqliteCaseRepository
) -> None:
    """Not in `api_keys`, and not anywhere else in the file either."""
    raw, summary = issue(client)

    stored = repository.get_api_key(DEMO_ORG_ID, summary["key_id"])
    assert stored is not None
    assert stored.key_hash == hash_api_key(raw)
    assert raw not in stored.key_hash
    # The prefix is the head of the key and is meant to be there; the 32 random
    # characters after it are what must not be.
    assert stored.key_prefix == raw[: len(KEY_SCHEME) + 8]
    assert raw[len(KEY_SCHEME) + 8 :] not in stored.key_prefix

    everything = "\n".join(
        str(tuple(row))
        for table in ("api_keys", "cases", "audit_trail", "users", "organizations")
        for row in repository._connection.execute(f"select * from {table}")
    )
    assert raw not in everything


def test_the_raw_key_is_not_recoverable_from_the_prefix(client: TestClient) -> None:
    raw, summary = issue(client)
    assert len(summary["key_prefix"]) < len(raw)
    assert raw not in summary["key_prefix"]


# --------------------------------------------------------------------------- #
# Using a key
# --------------------------------------------------------------------------- #


def test_a_key_reads_its_organizations_data(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """The headline: create a key, call the API with it, get real data back."""
    raw, _ = issue(client)

    response = anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))

    assert response.status_code == 200
    body = response.json()
    assert body["case_id"] == seeded_case
    assert body["total"] > 0
    assert body["items"][0]["case_id"] == seeded_case


def test_a_key_reads_the_dashboard_too(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    raw, _ = issue(client)

    response = anonymous_client.get("/v1/dashboard", headers=with_key(anonymous_client, raw))

    assert response.status_code == 200
    assert response.json()["client_name"] == "Haroon Textiles"


def test_using_a_key_records_when_it_was_last_used(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    raw, summary = issue(client)
    assert repository.get_api_key(DEMO_ORG_ID, summary["key_id"]).last_used_at is None

    anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))

    assert repository.get_api_key(DEMO_ORG_ID, summary["key_id"]).last_used_at is not None
    assert client.get("/v1/api-keys").json()["keys"][0]["last_used_at"] is not None


@pytest.mark.parametrize(
    "presented",
    [
        "trz_live_00000000000000000000000000000000",  # well-formed, never issued
        "not-a-key-at-all",
        "trz_live_short",
        "trz_test_00000000000000000000000000000000",  # wrong scheme
        "",
    ],
)
def test_a_key_that_was_never_issued_is_401(
    anonymous_client: TestClient, seeded_case: str, presented: str
) -> None:
    response = anonymous_client.get("/v1/review-items", headers={"X-API-Key": presented})
    assert response.status_code == 401
    assert seeded_case not in response.text


def test_a_revoked_key_is_401(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    raw, summary = issue(client)
    assert anonymous_client.get(
        "/v1/review-items", headers=with_key(anonymous_client, raw)
    ).status_code == 200

    assert client.delete(f"/v1/api-keys/{summary['key_id']}").status_code == 200

    response = anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))
    assert response.status_code == 401
    assert seeded_case not in response.text


def test_an_unknown_key_and_a_revoked_key_are_indistinguishable(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """Saying "revoked" rather than "unknown" would confirm the key was once real."""
    raw, summary = issue(client)
    client.delete(f"/v1/api-keys/{summary['key_id']}")

    revoked = anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))
    unknown = anonymous_client.get(
        "/v1/review-items", headers={"X-API-Key": f"{KEY_SCHEME}{'0' * 32}"}
    )

    assert revoked.status_code == unknown.status_code == 401
    assert revoked.json() == unknown.json()


def test_a_key_beats_a_stale_authorization_header(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """An ambiguous request resolves the same way every time: the key wins."""
    raw, _ = issue(client)

    response = anonymous_client.get(
        "/v1/review-items",
        headers={**with_key(anonymous_client, raw), "Authorization": "Bearer nonsense"},
    )

    assert response.status_code == 200


# --------------------------------------------------------------------------- #
# Scopes
# --------------------------------------------------------------------------- #


def test_a_read_only_key_cannot_approve(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    raw, _ = issue(client, scopes=("read",))
    item_id = pending_item_id(repository, seeded_case)

    response = anonymous_client.post(
        f"/v1/review-items/{item_id}/approve",
        json={},
        headers=with_key(anonymous_client, raw),
    )

    assert response.status_code == 403
    assert "write" in response.json()["detail"]
    assert repository.get_review_item(DEMO_ORG_ID, item_id).decision is ReviewDecision.PENDING


def test_a_read_only_key_cannot_reject_or_upload(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    raw, _ = issue(client, scopes=("read",))
    headers = with_key(anonymous_client, raw)
    item_id = pending_item_id(repository, seeded_case)

    reject = anonymous_client.post(
        f"/v1/review-items/{item_id}/reject", json={"reason": "no"}, headers=headers
    )
    upload = anonymous_client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
        headers=headers,
    )

    assert reject.status_code == 403
    assert upload.status_code == 403
    assert repository.get_review_item(DEMO_ORG_ID, item_id).decision is ReviewDecision.PENDING


def test_a_write_key_can_approve(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    raw, _ = issue(client, scopes=("read", "write"))
    item_id = pending_item_id(repository, seeded_case)

    response = anonymous_client.post(
        f"/v1/review-items/{item_id}/approve",
        json={"note": "Auto-vouched by the nightly reconciliation."},
        headers=with_key(anonymous_client, raw),
    )

    assert response.status_code == 200
    assert repository.get_review_item(DEMO_ORG_ID, item_id).decision is ReviewDecision.APPROVED


def test_a_write_only_key_cannot_read(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """Scopes restrain in both directions, not just the dangerous one."""
    raw, _ = issue(client, scopes=("write",))

    response = anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))

    assert response.status_code == 403
    assert seeded_case not in response.text


def test_a_signed_in_person_is_not_scope_limited(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """Scopes restrain a credential pasted into a workflow builder, not the auditor."""
    item_id = pending_item_id(repository, seeded_case)
    assert client.get("/v1/review-items").status_code == 200
    assert client.post(f"/v1/review-items/{item_id}/approve", json={}).status_code == 200


# --------------------------------------------------------------------------- #
# The audit trail names the key
# --------------------------------------------------------------------------- #


def test_an_approve_by_key_lands_an_audit_row_naming_the_key(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    """The acceptance criterion: the trail always shows which key acted."""
    raw, summary = issue(client, name="n8n integration", scopes=("read", "write"))
    item_id = pending_item_id(repository, seeded_case)
    before = len(repository.list_audit(DEMO_ORG_ID, seeded_case))

    response = anonymous_client.post(
        f"/v1/review-items/{item_id}/approve",
        json={"note": "Matched upstream."},
        headers=with_key(anonymous_client, raw),
    )
    assert response.status_code == 200

    trail = repository.list_audit(DEMO_ORG_ID, seeded_case)
    assert len(trail) == before + 1

    record = trail[-1]
    assert record.actor_type is ActorType.SYSTEM
    assert record.actor_id == f"api-key:{summary['key_prefix']}"
    assert record.item_id == item_id
    # The prefix identifies the key; the key itself is not in the trail.
    assert raw not in record.actor_id


def test_a_decision_by_key_is_still_attributed_to_a_person(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    """The trail says a machine called; the item says which auditor answers for it."""
    raw, summary = issue(client, scopes=("read", "write"))
    item_id = pending_item_id(repository, seeded_case)

    anonymous_client.post(
        f"/v1/review-items/{item_id}/approve", json={}, headers=with_key(anonymous_client, raw)
    )

    decided = repository.get_review_item(DEMO_ORG_ID, item_id)
    assert decided.decided_by == summary["created_by"]
    assert repository.list_audit(DEMO_ORG_ID, seeded_case)[-1].actor_id.startswith("api-key:")


def test_a_decision_by_a_person_is_still_recorded_as_human(
    client: TestClient, repository: SqliteCaseRepository, seeded_case: str
) -> None:
    """The API-key path did not change what a person's click looks like."""
    item_id = pending_item_id(repository, seeded_case)
    client.post(f"/v1/review-items/{item_id}/approve", json={})

    record = repository.list_audit(DEMO_ORG_ID, seeded_case)[-1]
    assert record.actor_type is ActorType.HUMAN
    assert not record.actor_id.startswith("api-key:")


def test_an_upload_by_key_is_recorded_as_the_key(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    demo_org: str,
    demo_mode,
    implemented_modules,
) -> None:
    raw, summary = issue(client, name="nightly drop", scopes=("read", "write"))

    response = anonymous_client.post(
        "/v1/upload",
        files=[
            ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf()))),
            ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger()))),
            ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
        ],
        data={"client_name": "Haroon Textiles"},
        headers=with_key(anonymous_client, raw),
    )
    assert response.status_code == 201
    case_id = response.json()["case_id"]

    trail = repository.list_audit(DEMO_ORG_ID, case_id)
    assert trail[0].actor_id == f"api-key:{summary['key_prefix']}"
    assert trail[0].actor_type is ActorType.SYSTEM
    # The case belongs to the auditor whose key it is, not to nobody.
    assert repository.get_case(DEMO_ORG_ID, case_id).created_by == summary["created_by"]


# --------------------------------------------------------------------------- #
# A key is bound to its organization
# --------------------------------------------------------------------------- #


def test_a_key_cannot_reach_another_organizations_case(
    other_client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    """Firm B's key, pointed at firm A's case. Same `404` a person would get."""
    raw, _ = issue(other_client, scopes=("read", "write"))
    headers = with_key(anonymous_client, raw)
    item_id = pending_item_id(repository, seeded_case)

    named = anonymous_client.get(
        "/v1/review-items", params={"case_id": seeded_case}, headers=headers
    )
    dashboard = anonymous_client.get(
        "/v1/dashboard", params={"case_id": seeded_case}, headers=headers
    )
    approve = anonymous_client.post(
        f"/v1/review-items/{item_id}/approve", json={}, headers=headers
    )
    trail = anonymous_client.get(f"/v1/review-items/{item_id}/audit", headers=headers)

    for response in (named, dashboard, approve, trail):
        assert response.status_code == 404, response.text
        assert "Haroon" not in response.text
    assert repository.get_review_item(DEMO_ORG_ID, item_id).decision is ReviewDecision.PENDING


def test_a_key_belongs_to_the_org_that_created_it(
    other_client: TestClient, repository: SqliteCaseRepository, other_org: str
) -> None:
    _, summary = issue(other_client)

    assert repository.get_api_key(OTHER_ORG_ID, summary["key_id"]) is not None
    assert repository.get_api_key(DEMO_ORG_ID, summary["key_id"]) is None


def test_a_key_with_no_case_of_its_own_is_told_to_upload(
    other_client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """Firm A's case is right there in the database. Firm B's key still sees none."""
    raw, _ = issue(other_client)

    response = anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))

    assert response.status_code == 404
    assert "upload" in response.json()["detail"].lower()
    assert seeded_case not in response.text


# --------------------------------------------------------------------------- #
# Listing and revoking
# --------------------------------------------------------------------------- #


def test_listing_shows_only_this_organizations_keys(
    client: TestClient, other_client: TestClient
) -> None:
    issue(client, name="firm a key")
    issue(other_client, name="firm b key")

    a_names = [key["name"] for key in client.get("/v1/api-keys").json()["keys"]]
    b_names = [key["name"] for key in other_client.get("/v1/api-keys").json()["keys"]]

    assert a_names == ["firm a key"]
    assert b_names == ["firm b key"]


def test_revoking_marks_the_key_without_deleting_the_row(
    client: TestClient, repository: SqliteCaseRepository
) -> None:
    """The row survives, so the trail's `api-key:<prefix>` stays resolvable."""
    _, summary = issue(client, name="n8n integration")

    response = client.delete(f"/v1/api-keys/{summary['key_id']}")

    assert response.status_code == 200
    assert response.json()["revoked"] is True
    assert response.json()["revoked_at"] is not None

    stored = repository.get_api_key(DEMO_ORG_ID, summary["key_id"])
    assert stored is not None, "revoking must not delete the row"
    assert stored.name == "n8n integration"
    assert stored.revoked_at is not None
    # And it is still listed, so "when did we turn this off" stays answerable.
    assert [key["key_id"] for key in client.get("/v1/api-keys").json()["keys"]] == [
        summary["key_id"]
    ]


def test_revoking_twice_is_not_an_error_and_keeps_the_first_timestamp(
    client: TestClient,
) -> None:
    _, summary = issue(client)

    first = client.delete(f"/v1/api-keys/{summary['key_id']}")
    second = client.delete(f"/v1/api-keys/{summary['key_id']}")

    assert first.status_code == second.status_code == 200
    assert first.json()["revoked_at"] == second.json()["revoked_at"]


def test_revoking_another_organizations_key_is_not_found(
    client: TestClient, other_client: TestClient, repository: SqliteCaseRepository
) -> None:
    _, mine = issue(client, name="firm a key")

    response = other_client.delete(f"/v1/api-keys/{mine['key_id']}")

    assert response.status_code == 404
    assert repository.get_api_key(DEMO_ORG_ID, mine["key_id"]).revoked_at is None


def test_revoking_a_key_that_never_existed_is_not_found(client: TestClient) -> None:
    assert client.delete("/v1/api-keys/AK-nope").status_code == 404


# --------------------------------------------------------------------------- #
# Renaming — the one editable thing about a key
# --------------------------------------------------------------------------- #


def test_renaming_a_key_changes_the_label_and_nothing_else(
    client: TestClient, repository: SqliteCaseRepository
) -> None:
    _, summary = issue(client, name="n8n automation", scopes=("read", "write"))

    response = client.patch(
        f"/v1/api-keys/{summary['key_id']}", json={"name": "nightly reconciliation"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "nightly reconciliation"
    assert body["key_id"] == summary["key_id"]
    assert body["key_prefix"] == summary["key_prefix"]
    assert body["scopes"] == ["read", "write"]
    assert client.get("/v1/api-keys").json()["keys"][0]["name"] == "nightly reconciliation"


def test_renaming_cannot_touch_scopes(client: TestClient) -> None:
    """Unknown keys are rejected, so a rename cannot smuggle in an escalation."""
    _, summary = issue(client, scopes=("read",))

    response = client.patch(
        f"/v1/api-keys/{summary['key_id']}",
        json={"name": "bigger", "scopes": ["read", "write"]},
    )

    assert response.status_code == 422
    assert client.get("/v1/api-keys").json()["keys"][0]["scopes"] == ["read"]


def test_renaming_to_an_empty_name_is_refused(client: TestClient) -> None:
    _, summary = issue(client, name="keep me")
    assert client.patch(
        f"/v1/api-keys/{summary['key_id']}", json={"name": ""}
    ).status_code == 422
    assert client.get("/v1/api-keys").json()["keys"][0]["name"] == "keep me"


def test_renaming_another_organizations_key_is_not_found(
    client: TestClient, other_client: TestClient, repository: SqliteCaseRepository
) -> None:
    _, mine = issue(client, name="firm a key")

    response = other_client.patch(
        f"/v1/api-keys/{mine['key_id']}", json={"name": "hijacked"}
    )

    assert response.status_code == 404
    assert repository.get_api_key(DEMO_ORG_ID, mine["key_id"]).name == "firm a key"


def test_renaming_a_key_that_never_existed_is_not_found(client: TestClient) -> None:
    assert client.patch("/v1/api-keys/AK-nope", json={"name": "x"}).status_code == 404


def test_a_key_cannot_rename_a_key(
    client: TestClient, anonymous_client: TestClient, repository: SqliteCaseRepository
) -> None:
    raw, summary = issue(client, name="honest label", scopes=("read", "write"))

    response = anonymous_client.patch(
        f"/v1/api-keys/{summary['key_id']}",
        json={"name": "innocuous"},
        headers=with_key(anonymous_client, raw),
    )

    assert response.status_code == 403
    assert repository.get_api_key(DEMO_ORG_ID, summary["key_id"]).name == "honest label"


# --------------------------------------------------------------------------- #
# Deleting — permanent, and effective immediately
# --------------------------------------------------------------------------- #


def test_deleting_a_revoked_key_removes_the_row(
    client: TestClient, repository: SqliteCaseRepository
) -> None:
    _, summary = issue(client, name="retired integration")
    assert client.delete(f"/v1/api-keys/{summary['key_id']}").status_code == 200

    response = client.delete(f"/v1/api-keys/{summary['key_id']}/record")

    assert response.status_code == 200
    assert response.json() == {"key_id": summary["key_id"], "deleted": True}
    assert repository.get_api_key(DEMO_ORG_ID, summary["key_id"]) is None
    assert client.get("/v1/api-keys").json()["keys"] == []


def test_deleting_an_active_key_stops_it_immediately(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """No revoke step needed: the hash goes with the row, so the key is dead."""
    raw, summary = issue(client, name="still in use")
    assert anonymous_client.get(
        "/v1/review-items", headers=with_key(anonymous_client, raw)
    ).status_code == 200

    response = client.delete(f"/v1/api-keys/{summary['key_id']}/record")

    assert response.status_code == 200
    assert anonymous_client.get(
        "/v1/review-items", headers=with_key(anonymous_client, raw)
    ).status_code == 401
    assert client.get("/v1/api-keys").json()["keys"] == []


def test_a_deleted_keys_raw_key_stays_dead(
    client: TestClient, anonymous_client: TestClient, seeded_case: str
) -> None:
    """Deleting the row must not resurrect the credential as an unknown-key 401."""
    raw, summary = issue(client)
    client.delete(f"/v1/api-keys/{summary['key_id']}")
    client.delete(f"/v1/api-keys/{summary['key_id']}/record")

    response = anonymous_client.get("/v1/review-items", headers=with_key(anonymous_client, raw))
    assert response.status_code == 401


def test_deleting_leaves_the_audit_trail_untouched(
    client: TestClient,
    anonymous_client: TestClient,
    repository: SqliteCaseRepository,
    seeded_case: str,
) -> None:
    """The trail keeps its `api-key:<prefix>` rows; they just stop resolving."""
    raw, summary = issue(client, scopes=("read", "write"))
    item_id = pending_item_id(repository, seeded_case)
    anonymous_client.post(
        f"/v1/review-items/{item_id}/approve", json={}, headers=with_key(anonymous_client, raw)
    )

    client.delete(f"/v1/api-keys/{summary['key_id']}")
    client.delete(f"/v1/api-keys/{summary['key_id']}/record")

    trail = repository.list_audit(DEMO_ORG_ID, seeded_case)
    assert trail[-1].actor_id == f"api-key:{summary['key_prefix']}"


def test_deleting_a_key_that_never_existed_is_not_found(client: TestClient) -> None:
    assert client.delete("/v1/api-keys/AK-nope/record").status_code == 404


def test_deleting_another_organizations_key_is_not_found(
    client: TestClient, other_client: TestClient, repository: SqliteCaseRepository
) -> None:
    _, mine = issue(client, name="firm a key")
    client.delete(f"/v1/api-keys/{mine['key_id']}")

    response = other_client.delete(f"/v1/api-keys/{mine['key_id']}/record")

    assert response.status_code == 404
    assert repository.get_api_key(DEMO_ORG_ID, mine["key_id"]) is not None


# --------------------------------------------------------------------------- #
# Keys cannot manage keys
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("method,path", [("get", "/v1/api-keys"), ("post", "/v1/api-keys")])
def test_a_key_cannot_mint_or_list_keys(
    client: TestClient, anonymous_client: TestClient, method: str, path: str
) -> None:
    """A credential that issues credentials makes one leak permanent."""
    raw, _ = issue(client, scopes=("read", "write"))

    call = getattr(anonymous_client, method)
    headers = with_key(anonymous_client, raw)
    response = (
        call(path, json={"name": "escalation", "scopes": ["read", "write"]}, headers=headers)
        if method == "post"
        else call(path, headers=headers)
    )

    assert response.status_code == 403
    assert "cannot manage" in response.json()["detail"]


def test_a_key_cannot_revoke_a_key(
    client: TestClient, anonymous_client: TestClient, repository: SqliteCaseRepository
) -> None:
    """Nor can it turn off the key someone is using to catch it."""
    raw, summary = issue(client, scopes=("read", "write"))

    response = anonymous_client.delete(
        f"/v1/api-keys/{summary['key_id']}", headers=with_key(anonymous_client, raw)
    )

    assert response.status_code == 403
    assert repository.get_api_key(DEMO_ORG_ID, summary["key_id"]).revoked_at is None


def test_a_key_cannot_delete_a_key(
    client: TestClient, anonymous_client: TestClient, repository: SqliteCaseRepository
) -> None:
    """Nor erase the record of another one that was already turned off."""
    raw, _ = issue(client, name="live credential", scopes=("read", "write"))
    _, target = issue(client, name="retired integration")
    client.delete(f"/v1/api-keys/{target['key_id']}")

    response = anonymous_client.delete(
        f"/v1/api-keys/{target['key_id']}/record", headers=with_key(anonymous_client, raw)
    )

    assert response.status_code == 403
    assert repository.get_api_key(DEMO_ORG_ID, target["key_id"]) is not None


def test_key_management_needs_an_identity_at_all(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/v1/api-keys").status_code == 401
    assert anonymous_client.post("/v1/api-keys", json={"name": "x"}).status_code == 401
