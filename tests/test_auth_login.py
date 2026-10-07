"""Unit & Contract Tests for JWT Authentication, Session Management, and Account Lockout."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from goldenminutes.api.main import create_app
from goldenminutes.api.store import get_db_store


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_seeded_users_exist():
    store = get_db_store()
    karim = store.get_user_by_username("analyst_karim")
    assert karim is not None
    assert karim.role == "analyst"

    ayesha = store.get_user_by_username("senior_ayesha")
    assert ayesha is not None
    assert ayesha.role == "senior_analyst"

    tariq = store.get_user_by_username("admin_tariq")
    assert tariq is not None
    assert tariq.role == "admin"


def test_login_success_and_cookies(client: TestClient):
    resp = client.post(
        "/v1/auth/login",
        json={"username": "analyst_karim", "password": "AnalystPass123!"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "analyst_karim"
    assert data["user"]["role"] == "analyst"

    # Verify httpOnly cookies were set
    assert "gm_access_token" in resp.cookies
    assert "gm_refresh_token" in resp.cookies


def test_login_invalid_password(client: TestClient):
    resp = client.post(
        "/v1/auth/login",
        json={"username": "analyst_karim", "password": "WrongPassword!"},
    )
    assert resp.status_code == 401
    data = resp.json()
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


def test_account_lockout_after_consecutive_failures(client: TestClient):
    store = get_db_store()
    # Reset any lockout for tariq
    with store.get_session() as session:
        u = store.get_user_by_username("admin_tariq")
        if u:
            u.failed_login_attempts = 0
            u.locked_until = None
            session.commit()

    # Trigger 5 consecutive failed attempts
    for _ in range(5):
        client.post(
            "/v1/auth/login",
            json={"username": "admin_tariq", "password": "WrongPassword!"},
        )

    # 6th attempt should return 403 Forbidden with ACCOUNT_LOCKED
    locked_resp = client.post(
        "/v1/auth/login",
        json={"username": "admin_tariq", "password": "AdminPass123!"},
    )
    assert locked_resp.status_code == 403
    assert locked_resp.json()["error"]["code"] == "ACCOUNT_LOCKED"

    # Clean up lockout after test
    with store.get_session() as session:
        u = store.get_user_by_username("admin_tariq")
        if u:
            u.failed_login_attempts = 0
            u.locked_until = None
            session.commit()


def test_get_current_user_profile(client: TestClient):
    # 1. Login
    login_resp = client.post(
        "/v1/auth/login",
        json={"username": "senior_ayesha", "password": "SeniorPass123!"},
    )
    token = login_resp.json()["access_token"]

    # 2. Get profile with Bearer header
    me_resp = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert user_data["username"] == "senior_ayesha"
    assert user_data["role"] == "senior_analyst"
    assert user_data["full_name"] == "Ayesha Siddiqua"


def test_refresh_token_rotation(client: TestClient):
    # 1. Login
    login_resp = client.post(
        "/v1/auth/login",
        json={"username": "analyst_karim", "password": "AnalystPass123!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # 2. Refresh
    ref_resp = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_resp.status_code == 200
    new_data = ref_resp.json()
    assert "access_token" in new_data
    assert new_data["refresh_token"] != refresh_token


def test_logout_revokes_token(client: TestClient):
    # 1. Login
    login_resp = client.post(
        "/v1/auth/login",
        json={"username": "analyst_karim", "password": "AnalystPass123!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # 2. Logout
    logout_resp = client.post(
        "/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_resp.status_code == 200

    # 3. Trying to use revoked refresh token should fail
    ref_resp = client.post(
        "/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert ref_resp.status_code == 401
