"""`POST /v1/auth/change-password` on the local identity store.

The flow a real user takes: sign up, sign in, change the password, and prove
the old password is dead while the new one works. Plus the refusals that make
the route safe: wrong current password, an API key, and an anonymous caller.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

EMAIL = "partner@change-pw-test.local"
OLD_PASSWORD = "original-password-1"
NEW_PASSWORD = "replacement-password-2"


def _signup_and_token(client: TestClient) -> str:
    response = client.post(
        "/v1/auth/signup",
        json={
            "email": EMAIL,
            "password": OLD_PASSWORD,
            "organization_name": "Change PW Test Firm",
        },
    )
    assert response.status_code == 201, response.text
    login = client.post(
        "/v1/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD}
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_change_password_end_to_end(anonymous_client: TestClient) -> None:
    token = _signup_and_token(anonymous_client)
    auth = {"Authorization": f"Bearer {token}"}

    changed = anonymous_client.post(
        "/v1/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=auth,
    )
    assert changed.status_code == 200, changed.text

    # The old password is dead; the new one signs in.
    old_login = anonymous_client.post(
        "/v1/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD}
    )
    assert old_login.status_code == 401
    new_login = anonymous_client.post(
        "/v1/auth/login", json={"email": EMAIL, "password": NEW_PASSWORD}
    )
    assert new_login.status_code == 200


def test_wrong_current_password_is_refused(anonymous_client: TestClient) -> None:
    token = _signup_and_token(anonymous_client)

    response = anonymous_client.post(
        "/v1/auth/change-password",
        json={"current_password": "not-the-password", "new_password": NEW_PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400

    # Nothing changed: the original password still signs in.
    login = anonymous_client.post(
        "/v1/auth/login", json={"email": EMAIL, "password": OLD_PASSWORD}
    )
    assert login.status_code == 200


def test_same_password_is_refused(anonymous_client: TestClient) -> None:
    token = _signup_and_token(anonymous_client)

    response = anonymous_client.post(
        "/v1/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": OLD_PASSWORD},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


def test_short_new_password_is_refused(anonymous_client: TestClient) -> None:
    token = _signup_and_token(anonymous_client)

    response = anonymous_client.post(
        "/v1/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": "short"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


def test_anonymous_caller_is_refused(anonymous_client: TestClient) -> None:
    response = anonymous_client.post(
        "/v1/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401


def test_api_key_cannot_change_a_password(anonymous_client: TestClient) -> None:
    """A machine credential must never rotate its creator's password."""
    token = _signup_and_token(anonymous_client)

    minted = anonymous_client.post(
        "/v1/api-keys",
        json={"name": "test key", "scopes": ["read", "write"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert minted.status_code == 201, minted.text

    response = anonymous_client.post(
        "/v1/auth/change-password",
        json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD},
        headers={"X-API-Key": minted.json()["api_key"]},
    )
    assert response.status_code == 403
