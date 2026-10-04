"""Tests for GoldenMinutes policy engine and cost evaluation."""

from datetime import datetime, timedelta, timezone

import pytest

from goldenminutes.policy.cost import expected_cost, select_optimal_action
from goldenminutes.policy.engine import PolicyEngine


def test_expected_cost_formula():
    """Verify expected_cost = p * amount * (1 - eff) + (1 - p) * fric."""
    # p = 0.8, amount = 10000, eff = 0.9, fric = 200
    # fraud cost = 0.8 * 10000 * (1 - 0.9) = 800
    # friction cost = (1 - 0.8) * 200 = 40
    # total = 840
    cost = expected_cost("hold", p=0.8, amount_bdt=10000.0, effectiveness=0.9, friction_cost=200.0)
    assert pytest.approx(cost, 1e-4) == 840.0


def test_select_optimal_action_tie_breaking():
    """Tie breaking must favor lower friction: allow < warn < verify < hold."""
    costs = {"hold": 100.0, "verify": 100.0, "warn": 100.0, "allow": 100.0}
    chosen = select_optimal_action(costs)
    assert chosen == "allow"

    costs_without_allow = {"hold": 50.0, "verify": 50.0, "warn": 50.0}
    assert select_optimal_action(costs_without_allow) == "warn"


def test_policy_engine_min_amount():
    """Amounts under min_amount_bdt_for_intervention (300 BDT) must always ALLOW."""
    engine = PolicyEngine()
    # High risk score, but amount is 250 BDT (< 300)
    decision = engine.evaluate(amount_bdt=250.0, risk_score=0.99)
    assert decision.action == "allow"
    assert "below intervention threshold" in (decision.rule_reason or "")


def test_policy_engine_hard_rules():
    """Hard rule 'recipient_blocklisted' must trigger HOLD regardless of amount."""
    engine = PolicyEngine()
    decision = engine.evaluate(
        amount_bdt=150.0,
        risk_score=0.1,
        context={"recipient_blocklisted": True},
    )
    assert decision.action == "hold"
    assert decision.hard_rule_fired == "recipient_blocklisted"


def test_policy_engine_high_risk_triggers_hold():
    """Large amount + high risk score must choose hold."""
    engine = PolicyEngine()
    decision = engine.evaluate(amount_bdt=25000.0, risk_score=0.95)
    assert decision.action == "hold"
    assert decision.priority is not None
    assert decision.priority > 0


def test_policy_engine_low_risk_triggers_allow():
    """Low risk score must choose allow."""
    engine = PolicyEngine()
    decision = engine.evaluate(amount_bdt=5000.0, risk_score=0.0005)
    assert decision.action == "allow"


def test_policy_engine_hold_capacity_fallback():
    """Exceeding hold capacity (20/hour) must fall back to verify."""
    engine = PolicyEngine()
    now = datetime(2026, 2, 14, 12, 0, 0, tzinfo=timezone.utc)

    # Trigger 20 holds
    for i in range(20):
        t = now + timedelta(minutes=i)
        d = engine.evaluate(amount_bdt=20000.0, risk_score=0.95, current_ts=t)
        assert d.action == "hold"
        assert not d.capacity_exceeded

    # 21st hold in the same hour must fall back to verify
    d_fallback = engine.evaluate(
        amount_bdt=20000.0,
        risk_score=0.95,
        current_ts=now + timedelta(minutes=25),
    )
    assert d_fallback.action == "verify"
    assert d_fallback.capacity_exceeded is True
    assert d_fallback.chosen_raw_action == "hold"


def test_policy_engine_no_deny():
    """Engine must NEVER return 'deny'."""
    engine = PolicyEngine()
    for p in [0.0, 0.5, 0.99, 1.0]:
        for amt in [50.0, 300.0, 50000.0]:
            d = engine.evaluate(amount_bdt=amt, risk_score=p)
            assert d.action != "deny"
            assert d.action in ["allow", "warn", "verify", "hold"]


def test_alert_priority_and_urgency():
    """Verify priority formula: priority = p * amount * (1 + urgency)."""
    engine = PolicyEngine()
    now = datetime(2026, 2, 14, 12, 0, 0, tzinfo=timezone.utc)

    # 0 minutes since first inflow -> time_left = 30, urgency = 0.0
    prio, urg, t_left, status, deadline = engine.calculate_priority(
        risk_score=0.9,
        amount_bdt=10000.0,
        minutes_since_first_inflow=0.0,
        current_ts=now,
    )
    assert pytest.approx(t_left) == 30.0
    assert pytest.approx(urg) == 0.0
    # priority = 0.9 * 10000 * (1 + 0) = 9000
    assert pytest.approx(prio) == 9000.0
    assert status == "open"
    assert deadline == now + timedelta(minutes=30)

    # 15 minutes since first inflow -> time_left = 15, urgency = 0.5
    prio, urg, t_left, status, deadline = engine.calculate_priority(
        risk_score=0.9,
        amount_bdt=10000.0,
        minutes_since_first_inflow=15.0,
        current_ts=now,
    )
    assert pytest.approx(t_left) == 15.0
    assert pytest.approx(urg) == 0.5
    # priority = 0.9 * 10000 * (1 + 0.5) = 13500
    assert pytest.approx(prio) == 13500.0
    assert status == "open"

    # Already cashed out -> status late
    prio, urg, t_left, status, deadline = engine.calculate_priority(
        risk_score=0.9,
        amount_bdt=10000.0,
        minutes_since_first_inflow=35.0,
        cashed_out=True,
        current_ts=now,
    )
    assert status == "late"
