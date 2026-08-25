"""The `/v1/profile` routes: a person's editable profile, and its limits.

The profile is deliberately powerless — a display name, a picture, contact
details. What these tests pin down is the boundary: only a signed-in person
reaches it, only their own row, the avatar is a size-capped inline image, and
none of it leaks into anyone else's view.
"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from test_api_keys import issue, with_key

A_TINY_PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG fake").decode()


def test_a_fresh_profile_is_all_nones(client: TestClient) -> None:
    response = client.get("/v1/profile")

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] is None
    assert body["job_title"] is None
    assert body["phone"] is None
    assert body["avatar"] is None
    assert body["user_id"]


def test_saving_and_reading_back_a_profile(client: TestClient) -> None:
    saved = client.put(
        "/v1/profile",
        json={
            "full_name": "Haroon Sajid",
            "job_title": "Audit Partner",
            "phone": "+92 300 1234567",
            "avatar": A_TINY_PNG,
            "gender": "male",
            "date_of_birth": "1990-03-14",
            "location": "Lahore",
            "license_number": "ICAP-12345",
            "language": "ur",
            "notify_case_ready": True,
            "notify_high_severity": False,
            "notify_weekly_digest": True,
        },
    )
    assert saved.status_code == 200
    assert saved.json()["full_name"] == "Haroon Sajid"

    fetched = client.get("/v1/profile").json()
    assert fetched["full_name"] == "Haroon Sajid"
    assert fetched["job_title"] == "Audit Partner"
    assert fetched["phone"] == "+92 300 1234567"
    assert fetched["avatar"] == A_TINY_PNG
    assert fetched["gender"] == "male"
    assert fetched["date_of_birth"] == "1990-03-14"
    assert fetched["location"] == "Lahore"
    assert fetched["license_number"] == "ICAP-12345"
    assert fetched["language"] == "ur"
    assert fetched["notify_case_ready"] is True
    assert fetched["notify_high_severity"] is False
    assert fetched["notify_weekly_digest"] is True


def test_notification_preferences_have_sensible_defaults(client: TestClient) -> None:
    fresh = client.get("/v1/profile").json()
    assert fresh["notify_case_ready"] is True
    assert fresh["notify_high_severity"] is True
    assert fresh["notify_weekly_digest"] is False


def test_an_unsupported_language_is_refused(client: TestClient) -> None:
    assert client.put("/v1/profile", json={"language": "fr"}).status_code == 422
    assert client.put("/v1/profile", json={"language": "ur"}).status_code == 200


def test_a_nonsense_date_of_birth_is_refused(client: TestClient) -> None:
    assert client.put(
        "/v1/profile", json={"date_of_birth": "not-a-date"}
    ).status_code == 422


def test_put_is_a_full_replacement(client: TestClient) -> None:
    """An omitted field is cleared, not kept — the contract is PUT-shaped."""
    client.put("/v1/profile", json={"full_name": "Haroon Sajid", "phone": "+92 300 1"})

    client.put("/v1/profile", json={"full_name": "Haroon S."})

    fetched = client.get("/v1/profile").json()
    assert fetched["full_name"] == "Haroon S."
    assert fetched["phone"] is None


def test_blank_strings_read_back_as_nothing(client: TestClient) -> None:
    client.put("/v1/profile", json={"full_name": "   ", "job_title": ""})
    fetched = client.get("/v1/profile").json()
    assert fetched["full_name"] is None
    assert fetched["job_title"] is None


def test_an_avatar_must_be_an_inline_image(client: TestClient) -> None:
    for bad in (
        "https://example.com/me.png",
        "data:text/html;base64,PGI+",
        "javascript:alert(1)",
    ):
        response = client.put("/v1/profile", json={"avatar": bad})
        assert response.status_code == 422, bad
    assert client.get("/v1/profile").json()["avatar"] is None


def test_a_giant_avatar_is_refused(client: TestClient) -> None:
    huge = "data:image/png;base64," + "A" * 500_000
    assert client.put("/v1/profile", json={"avatar": huge}).status_code == 422


def test_profiles_are_per_person(
    client: TestClient, other_client: TestClient
) -> None:
    client.put("/v1/profile", json={"full_name": "Firm A Auditor"})

    assert other_client.get("/v1/profile").json()["full_name"] is None


def test_a_profile_needs_a_signed_in_person(anonymous_client: TestClient) -> None:
    assert anonymous_client.get("/v1/profile").status_code == 401
    assert anonymous_client.put("/v1/profile", json={}).status_code == 401


def test_a_key_cannot_read_or_write_a_profile(
    client: TestClient, anonymous_client: TestClient
) -> None:
    """A machine credential has no face; it must not redecorate its owner's."""
    raw, _ = issue(client, scopes=("read", "write"))
    headers = with_key(anonymous_client, raw)

    assert anonymous_client.get("/v1/profile", headers=headers).status_code == 403
    assert (
        anonymous_client.put(
            "/v1/profile", json={"full_name": "bot"}, headers=headers
        ).status_code
        == 403
    )
    assert client.get("/v1/profile").json()["full_name"] is None
