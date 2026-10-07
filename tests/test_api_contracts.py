"""Endpoint contract smoke tests for GoldenMinutes Section 13 API."""

from fastapi.testclient import TestClient

from goldenminutes.api.main import app

client = TestClient(app)

CUSTOMER_HEADERS = {"X-API-Key": "demo_customer_secret_key"}
ANALYST_HEADERS = {"X-API-Key": "demo_analyst_secret_key"}


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "model_version" in data
    assert "policy_version" in data
    assert "environment" in data


def test_request_id_middleware_and_timing():
    custom_id = "test-req-12345"
    res = client.get("/health", headers={"X-Request-ID": custom_id})
    assert res.status_code == 200
    assert res.headers.get("x-request-id") == custom_id
    assert "x-process-time" in res.headers


def test_score_endpoint_contract():
    payload = {
        "txn_id": "TXN-SMOKE-1",
        "type": "send_money",
        "sender_wallet_id": "W001",
        "recipient_wallet_id": "W002",
        "amount_bdt": 20000.0,
        "channel": "app",
        "device_id": "D001",
        "balance_before": 25000.0,
    }
    res = client.post("/v1/score", json=payload, headers=CUSTOMER_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers

    data = res.json()
    assert data["txn_id"] == "TXN-SMOKE-1"
    assert "risk_score" in data
    assert data["action"] in ["allow", "warn", "verify", "hold"]
    assert "reason_codes" in data
    assert "customer_message" in data
    assert "bn" in data["customer_message"]
    assert "en" in data["customer_message"]
    assert "latency_ms" in data


def test_score_validation_error_shape():
    # Negative amount should trigger 422 with standard error shape
    payload = {
        "txn_id": "TXN-FAIL",
        "type": "send_money",
        "sender_wallet_id": "W001",
        "recipient_wallet_id": "W002",
        "amount_bdt": -50.0,
        "channel": "app",
        "device_id": "D001",
        "balance_before": 100.0,
    }
    res = client.post("/v1/score", json=payload, headers=CUSTOMER_HEADERS)
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]


def test_alerts_endpoints_contract():
    # Score a high-risk transfer to generate an alert
    score_payload = {
        "txn_id": "TXN-SMOKE-ALERT",
        "type": "send_money",
        "sender_wallet_id": "W01928",
        "recipient_wallet_id": "W08371",
        "amount_bdt": 25000.0,
        "channel": "app",
        "device_id": "D_TEST",
        "balance_before": 45000.0,
    }
    score_res = client.post("/v1/score", json=score_payload, headers=CUSTOMER_HEADERS)
    assert score_res.status_code == 200
    score_data = score_res.json()
    assert score_data["alert_id"] is not None
    created_alert_id = score_data["alert_id"]

    # List alerts
    res = client.get("/v1/alerts", headers=ANALYST_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert "alerts" in data
    assert data["total"] >= 1
    alert_ids = [a["alert_id"] for a in data["alerts"]]
    assert created_alert_id in alert_ids

    # Get alert detail
    res_detail = client.get(f"/v1/alerts/{created_alert_id}", headers=ANALYST_HEADERS)
    assert res_detail.status_code == 200
    assert "x-gm-stub" not in res_detail.headers
    detail_data = res_detail.json()
    assert detail_data["alert_id"] == created_alert_id
    assert "evidence" in detail_data
    assert "narrative" in detail_data

    # Decision on alert: approve
    res_decision = client.post(
        f"/v1/alerts/{created_alert_id}/decision",
        json={"action": "approve", "note": "Confirmed synthetic fraud scenario"},
        headers=ANALYST_HEADERS,
    )
    assert res_decision.status_code == 200
    assert "x-gm-stub" not in res_decision.headers
    decision_data = res_decision.json()
    assert decision_data["alert_id"] == created_alert_id
    assert decision_data["action_taken"] == "approve"


def test_feedback_endpoint_contract():
    res = client.post(
        "/v1/feedback",
        json={"decision_id": "D-101", "source": "customer", "label": "this_was_me"},
        headers=CUSTOMER_HEADERS,
    )
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert data["status"] == "recorded"
    assert "feedback_id" in data


def test_graph_endpoint_contract():
    res = client.get("/v1/graph/W00999", headers=ANALYST_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert data["wallet_id"] == "W00999"
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0


def test_metrics_endpoint_contract():
    res = client.get("/v1/metrics", headers=ANALYST_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert "fraud_value_intercepted_bdt" in data
    assert "false_friction_rate" in data
    assert "ablation_table" in data
    assert len(data["ablation_table"]) == 6


def test_simulation_endpoints_contract():
    # Attack simulation
    res_attack = client.post("/v1/simulate/attack", json={"scenario_id": "test_scam"}, headers=CUSTOMER_HEADERS)
    assert res_attack.status_code == 200
    assert "x-gm-stub" not in res_attack.headers
    attack_data = res_attack.json()
    assert attack_data["status"] == "started"
    assert len(attack_data["steps"]) > 0

    # Reset simulation
    res_reset = client.post("/v1/simulate/reset", json={}, headers=CUSTOMER_HEADERS)
    assert res_reset.status_code == 200
    assert "x-gm-stub" not in res_reset.headers
    reset_data = res_reset.json()
    assert reset_data["status"] == "reset_completed"


def test_demo_accounts_endpoint_contract():
    res = client.get("/v1/demo/accounts", headers=CUSTOMER_HEADERS)
    assert res.status_code == 200
    assert "x-gm-stub" not in res.headers
    data = res.json()
    assert "senders" in data
    assert "recipients" in data
    assert len(data["senders"]) > 0
    assert len(data["recipients"]) > 0
