"""Tests for Four-Eyes Dual Authorization Rule on High-Value Interventions."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from goldenminutes.api.main import create_app
from goldenminutes.api.store import get_db_store


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_four_eyes_enforcement_on_high_value_hold(client: TestClient):
    store = get_db_store()

    # 1. Create a high-value alert (৳75,000 >= ৳50,000 threshold)
    alert_id = f"A_HIGH_{uuid.uuid4().hex[:8].upper()}"
    dec_id = f"D_{uuid.uuid4().hex[:8].upper()}"

    store.save_decision(
        decision_id=dec_id,
        txn_id="TX_HIGH_VALUE",
        ts=datetime.now(timezone.utc),
        sender_wallet_id="WAL_TEST_SENDER",
        recipient_wallet_id="WAL_TEST_RECIPIENT",
        amount_bdt=75000.0,
        channel="app",
        device_id="DEV_TEST",
        risk_score=0.92,
        action="hold",
        model_version="m-1.0.0-full",
        policy_version="0.1",
        latency_ms=10.0,
        reason_codes=[{"code": "AMOUNT_UNUSUAL_FOR_SENDER", "weight": 0.8}],
        evidence={},
    )

    store.create_alert(
        alert_id=alert_id,
        decision_id=dec_id,
        txn_id="TX_HIGH_VALUE",
        priority=75000.0 * 0.92,
        money_at_risk=75000.0,
        deadline_ts=datetime.now(timezone.utc) + timedelta(minutes=15),
        sender_wallet_id="WAL_TEST_SENDER",
        recipient_wallet_id="WAL_TEST_RECIPIENT",
        amount_bdt=75000.0,
        risk_score=0.92,
        action="hold",
        reason_codes=[{"code": "AMOUNT_UNUSUAL_FOR_SENDER", "weight": 0.8}],
    )

    # 2. Login as junior analyst (Karim)
    karim_login = client.post(
        "/v1/auth/login",
        json={"username": "analyst_karim", "password": "AnalystPass123!"},
    )
    karim_token = karim_login.json()["access_token"]

    # 3. Junior analyst attempting release on high-value alert MUST receive 403 Forbidden!
    release_resp = client.post(
        f"/v1/alerts/{alert_id}/decision",
        json={"action": "release", "note": "Customer called support and verified transaction"},
        headers={"Authorization": f"Bearer {karim_token}"},
    )
    assert release_resp.status_code == 403
    err = release_resp.json()
    assert err["error"]["code"] == "FOUR_EYES_REQUIRED"
    assert "senior analyst" in err["error"]["message"].lower()

    # 4. Login as senior analyst (Ayesha)
    ayesha_login = client.post(
        "/v1/auth/login",
        json={"username": "senior_ayesha", "password": "SeniorPass123!"},
    )
    ayesha_token = ayesha_login.json()["access_token"]

    # 5. Senior analyst approving/releasing the high-value alert MUST succeed!
    senior_release = client.post(
        f"/v1/alerts/{alert_id}/decision",
        json={"action": "release", "note": "Verified customer identity via national NID database"},
        headers={"Authorization": f"Bearer {ayesha_token}"},
    )
    assert senior_release.status_code == 200
    data = senior_release.json()
    assert data["status"] == "resolved"
    assert data["action_taken"] == "release"
    assert data["analyst_id"] == "USR-AYESHA"
