"""Tests for SQLAlchemy DatabaseStore: decisions, alerts, actions, audit, and feedback."""

from datetime import datetime, timedelta, timezone

import pytest

from goldenminutes.api.store import DatabaseStore


@pytest.fixture
def store():
    """In-memory database store for testing."""
    db = DatabaseStore(db_url="sqlite:///:memory:")
    return db


def test_save_decision_and_create_alert(store):
    now = datetime.now(timezone.utc)
    dec = store.save_decision(
        decision_id="D001",
        txn_id="TXN001",
        ts=now,
        sender_wallet_id="W1",
        recipient_wallet_id="W2",
        amount_bdt=15000.0,
        channel="app",
        device_id="DEV1",
        risk_score=0.92,
        action="hold",
        model_version="m-1.0.0",
        policy_version="0.1",
        latency_ms=25.0,
        reason_codes=[{"code": "RECIPIENT_FAN_IN_BURST", "weight": 0.45}],
        evidence={"inflow_24h": 45000.0},
    )
    assert dec.decision_id == "D001"

    alert = store.create_alert(
        alert_id="A001",
        decision_id="D001",
        txn_id="TXN001",
        sender_wallet_id="W1",
        recipient_wallet_id="W2",
        amount_bdt=15000.0,
        risk_score=0.92,
        action="hold",
        priority=0.92 * 15000.0,
        money_at_risk=15000.0,
        deadline_ts=now + timedelta(minutes=30),
        reason_codes=[{"code": "RECIPIENT_FAN_IN_BURST", "weight": 0.45}],
    )
    assert alert.alert_id == "A001"
    assert alert.status == "open"


def test_list_alerts_and_priority_sorting(store):
    now = datetime.now(timezone.utc)
    # Decision 1
    store.save_decision(
        decision_id="D1", txn_id="T1", ts=now, sender_wallet_id="W1", recipient_wallet_id="W2",
        amount_bdt=1000.0, channel="app", device_id="D1", risk_score=0.5, action="hold",
        model_version="m1", policy_version="p1", latency_ms=10.0, reason_codes=[], evidence={},
    )
    store.create_alert(
        alert_id="A1", decision_id="D1", txn_id="T1", sender_wallet_id="W1", recipient_wallet_id="W2",
        amount_bdt=1000.0, risk_score=0.5, action="hold", priority=500.0, money_at_risk=1000.0,
        deadline_ts=now + timedelta(minutes=30), reason_codes=[],
    )

    # Decision 2 (higher priority)
    store.save_decision(
        decision_id="D2", txn_id="T2", ts=now, sender_wallet_id="W3", recipient_wallet_id="W4",
        amount_bdt=20000.0, channel="app", device_id="D2", risk_score=0.9, action="hold",
        model_version="m1", policy_version="p1", latency_ms=10.0, reason_codes=[], evidence={},
    )
    store.create_alert(
        alert_id="A2", decision_id="D2", txn_id="T2", sender_wallet_id="W3", recipient_wallet_id="W4",
        amount_bdt=20000.0, risk_score=0.9, action="hold", priority=18000.0, money_at_risk=20000.0,
        deadline_ts=now + timedelta(minutes=15), reason_codes=[],
    )

    alerts = store.list_alerts()
    assert len(alerts) == 2
    # Highest priority first
    assert alerts[0].alert_id == "A2"
    assert alerts[1].alert_id == "A1"


def test_analyst_action_and_audit_trail(store):
    now = datetime.now(timezone.utc)
    store.save_decision(
        decision_id="D10", txn_id="T10", ts=now, sender_wallet_id="W1", recipient_wallet_id="W2",
        amount_bdt=5000.0, channel="app", device_id="D1", risk_score=0.8, action="hold",
        model_version="m1", policy_version="p1", latency_ms=10.0, reason_codes=[], evidence={},
    )
    store.create_alert(
        alert_id="A10", decision_id="D10", txn_id="T10", sender_wallet_id="W1", recipient_wallet_id="W2",
        amount_bdt=5000.0, risk_score=0.8, action="hold", priority=4000.0, money_at_risk=5000.0,
        deadline_ts=now + timedelta(minutes=20), reason_codes=[],
    )

    # Analyst approves alert
    alert, action = store.record_analyst_action(
        alert_id="A10",
        action="approve",
        analyst_id="analyst_alice",
        note="Confirmed impersonation attempt with sender",
    )
    assert alert.status == "resolved"
    assert action.action == "approve"
    assert action.analyst_id == "analyst_alice"

    # Check audit log entry exists
    audit_trail = store.get_audit_trail(resource_id="A10")
    assert len(audit_trail) == 1
    assert audit_trail[0].event_type == "analyst_action"
    assert audit_trail[0].user_id == "analyst_alice"
    assert audit_trail[0].action == "approve"


def test_record_feedback_creates_audit(store):
    now = datetime.now(timezone.utc)
    store.save_decision(
        decision_id="D20", txn_id="T20", ts=now, sender_wallet_id="W1", recipient_wallet_id="W2",
        amount_bdt=3000.0, channel="app", device_id="D1", risk_score=0.1, action="allow",
        model_version="m1", policy_version="p1", latency_ms=5.0, reason_codes=[], evidence={},
    )

    fb = store.record_feedback(
        decision_id="D20",
        source="customer",
        label="this_was_me",
        note="Customer confirms authorized transfer",
    )
    assert fb.decision_id == "D20"
    assert fb.label == "this_was_me"

    audit_trail = store.get_audit_trail(resource_id="D20")
    assert len(audit_trail) == 1
    assert audit_trail[0].event_type == "feedback_recorded"
