"""Tests for role-based authentication and security (X-API-Key)."""

from fastapi.testclient import TestClient

from goldenminutes.api.main import app

client = TestClient(app)

CUSTOMER_HEADERS = {"X-API-Key": "demo_customer_secret_key"}
ANALYST_HEADERS = {"X-API-Key": "demo_analyst_secret_key"}
INVALID_HEADERS = {"X-API-Key": "completely_wrong_key"}


def test_missing_api_key_returns_401():
    res = client.post("/v1/score", json={
        "txn_id": "T1",
        "sender_wallet_id": "W1",
        "recipient_wallet_id": "W2",
        "amount_bdt": 1000,
        "device_id": "D1",
        "balance_before": 5000,
    })
    assert res.status_code == 401
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_invalid_api_key_returns_403():
    res = client.post("/v1/score", json={
        "txn_id": "T1",
        "sender_wallet_id": "W1",
        "recipient_wallet_id": "W2",
        "amount_bdt": 1000,
        "device_id": "D1",
        "balance_before": 5000,
    }, headers=INVALID_HEADERS)
    assert res.status_code == 403
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "FORBIDDEN"


def test_customer_role_can_score():
    res = client.post("/v1/score", json={
        "txn_id": "T1",
        "sender_wallet_id": "W1",
        "recipient_wallet_id": "W2",
        "amount_bdt": 1000,
        "device_id": "D1",
        "balance_before": 5000,
    }, headers=CUSTOMER_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers


def test_customer_role_cannot_access_analyst_queue():
    res = client.get("/v1/alerts", headers=CUSTOMER_HEADERS)
    assert res.status_code == 403
    data = res.json()
    assert data["error"]["code"] == "FORBIDDEN"


def test_analyst_role_can_access_analyst_queue():
    res = client.get("/v1/alerts", headers=ANALYST_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert "alerts" in data
    assert isinstance(data["alerts"], list)


def test_analyst_role_can_access_metrics():
    res = client.get("/v1/metrics", headers=ANALYST_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert "ablation_table" in data
