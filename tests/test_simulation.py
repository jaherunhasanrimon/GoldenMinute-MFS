"""Backend test for attack simulation scenario escalation."""

from fastapi.testclient import TestClient

from goldenminutes.api.main import create_app


def test_attack_scenario_reaches_at_least_verify():
    """PHASES_GoldenMinutes.md P6 gate requirement:

    'Add a backend test asserting the scenario reaches at least verify by its last step.'
    """
    app = create_app()
    client = TestClient(app)
    headers = {"X-API-Key": "demo_customer_secret_key"}

    # 1. Reset simulation first to ensure clean state
    reset_resp = client.post("/v1/simulate/reset", headers=headers)
    assert reset_resp.status_code == 200

    # 2. Trigger attack simulation
    resp = client.post("/v1/simulate/attack", json={"scenario_id": "impersonation_scam_01"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "started"
    assert "steps" in data
    steps = data["steps"]
    assert len(steps) >= 5

    # Check that the scenario culminates in an intervention reaching at least verify or hold
    # Steps escalate from low-risk to intervention
    actions = [s.get("action") for s in steps if s.get("action")]
    print("DEBUG ACTIONS:", actions)
    print("DEBUG STEPS:", steps)
    assert len(actions) > 0, "Scenario steps must contain scored actions"

    last_action = actions[-1]
    assert last_action in ["verify", "hold"], (
        f"Expected attack scenario to reach at least verify or hold by its last step, got {last_action}"
    )

    # Verify that an alert was created if action is hold
    if last_action == "hold":
        alert_ids = [s.get("alert_id") for s in steps if s.get("alert_id")]
        assert len(alert_ids) > 0, "Held attack scenario must produce an alert_id"
