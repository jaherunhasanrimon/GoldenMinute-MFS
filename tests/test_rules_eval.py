"""Unit tests for deterministic rules baseline (Variant A) and evaluation metrics."""

import numpy as np

from goldenminutes.eval.metrics import (
    compute_bootstrap_ci,
    compute_brier_score,
    compute_expected_calibration_error,
    compute_false_friction_rate,
    compute_precision_at_k,
    compute_value_weighted_recall,
)
from goldenminutes.rules.baseline import RulesBaseline


def test_rule_r1_new_recipient_large_amount():
    """R1 fires when recipient is < 3 days old and amount >= 10,000."""
    rules = RulesBaseline()
    row = {
        "recipient_age_days": 1.5,
        "amount_bdt": 15000.0,
        "balance_drain_ratio": 0.3,
        "is_first_time_pair": 0,
        "minutes_since_pin_reset": 43200.0,
        "minutes_since_sim_change": 43200.0,
        "recipient_unique_senders_1h": 1,
        "recipient_first_time_sender_share_24h": 0.0,
        "recipient_median_receipt_to_out_minutes": 1440.0,
        "recipient_pass_through_ratio_24h": 0.0,
    }
    res = rules.evaluate_row(row)
    assert "R1" in res["rules_hit"]
    assert res["action"] in ["verify", "hold"]
    assert any(rc["code"] == "RECIPIENT_NEW" for rc in res["reason_codes"])


def test_rule_r2_balance_drain_first_time():
    """R2 fires when balance drain >= 0.8 and first time pair."""
    rules = RulesBaseline()
    row = {
        "recipient_age_days": 100.0,
        "amount_bdt": 5000.0,
        "balance_drain_ratio": 0.95,
        "is_first_time_pair": 1,
        "minutes_since_pin_reset": 43200.0,
        "minutes_since_sim_change": 43200.0,
        "recipient_unique_senders_1h": 1,
        "recipient_first_time_sender_share_24h": 0.0,
        "recipient_median_receipt_to_out_minutes": 1440.0,
        "recipient_pass_through_ratio_24h": 0.0,
    }
    res = rules.evaluate_row(row)
    assert "R2" in res["rules_hit"]
    assert res["action"] == "warn"


def test_rule_r3_recent_auth_large_amount():
    """R3 fires when PIN reset or SIM change <= 60 min and amount >= 15,000."""
    rules = RulesBaseline()
    row = {
        "recipient_age_days": 50.0,
        "amount_bdt": 20000.0,
        "balance_drain_ratio": 0.4,
        "is_first_time_pair": 0,
        "minutes_since_pin_reset": 25.0,  # 25 mins ago
        "minutes_since_sim_change": 43200.0,
        "recipient_unique_senders_1h": 1,
        "recipient_first_time_sender_share_24h": 0.0,
        "recipient_median_receipt_to_out_minutes": 1440.0,
        "recipient_pass_through_ratio_24h": 0.0,
    }
    res = rules.evaluate_row(row)
    assert "R3" in res["rules_hit"]
    assert res["action"] == "hold"


def test_rule_r4_fan_in_burst():
    """R4 fires when 5+ unique senders in 1h with high first-time share."""
    rules = RulesBaseline()
    row = {
        "recipient_age_days": 20.0,
        "amount_bdt": 2000.0,
        "balance_drain_ratio": 0.1,
        "is_first_time_pair": 1,
        "minutes_since_pin_reset": 43200.0,
        "minutes_since_sim_change": 43200.0,
        "recipient_unique_senders_1h": 6,
        "recipient_first_time_sender_share_24h": 0.8,
        "recipient_median_receipt_to_out_minutes": 1440.0,
        "recipient_pass_through_ratio_24h": 0.0,
    }
    res = rules.evaluate_row(row)
    assert "R4" in res["rules_hit"]
    assert res["action"] == "hold"


def test_rule_r5_rapid_cashout():
    """R5 fires when median receipt to cashout <= 10 min and high pass through."""
    rules = RulesBaseline()
    row = {
        "recipient_age_days": 40.0,
        "amount_bdt": 3000.0,
        "balance_drain_ratio": 0.1,
        "is_first_time_pair": 0,
        "minutes_since_pin_reset": 43200.0,
        "minutes_since_sim_change": 43200.0,
        "recipient_unique_senders_1h": 1,
        "recipient_first_time_sender_share_24h": 0.0,
        "recipient_median_receipt_to_out_minutes": 4.5,
        "recipient_pass_through_ratio_24h": 0.9,
    }
    res = rules.evaluate_row(row)
    assert "R5" in res["rules_hit"]
    assert res["action"] == "hold"


def test_rules_legitimate_normal_transaction():
    """Normal transaction does not trigger any rules."""
    rules = RulesBaseline()
    row = {
        "recipient_age_days": 180.0,
        "amount_bdt": 1200.0,
        "balance_drain_ratio": 0.15,
        "is_first_time_pair": 0,
        "minutes_since_pin_reset": 43200.0,
        "minutes_since_sim_change": 43200.0,
        "recipient_unique_senders_1h": 0,
        "recipient_first_time_sender_share_24h": 0.0,
        "recipient_median_receipt_to_out_minutes": 1440.0,
        "recipient_pass_through_ratio_24h": 0.0,
    }
    res = rules.evaluate_row(row)
    assert len(res["rules_hit"]) == 0
    assert res["action"] == "allow"
    assert res["risk_score"] < 0.1


def test_metrics_toy_vectors():
    """Verify evaluation metric calculations on known toy vectors."""
    y_true = np.array([0, 0, 0, 0, 1, 1])
    actions = np.array(["allow", "allow", "warn", "allow", "hold", "allow"])
    amounts = np.array([100.0, 200.0, 300.0, 400.0, 5000.0, 5000.0])

    # FFR: 1 out of 4 legit has friction ('warn') -> 1/4 = 0.25
    ffr = compute_false_friction_rate(y_true, actions)
    assert np.isclose(ffr, 0.25)

    # Value-weighted recall: 5000 out of 10000 fraud value receives hold -> 0.50
    vwr = compute_value_weighted_recall(y_true, actions, amounts)
    assert np.isclose(vwr, 0.50)

    # Precision at K
    scores = np.array([0.1, 0.2, 0.3, 0.4, 0.9, 0.8])
    # Top 2 scores are index 4 (1) and 5 (1) -> precision = 1.0
    prec2 = compute_precision_at_k(y_true, scores, k=2)
    assert np.isclose(prec2, 1.0)

    # Brier score
    brier = compute_brier_score(y_true, scores)
    assert brier >= 0.0

    # ECE
    ece = compute_expected_calibration_error(y_true, scores, n_bins=5)
    assert 0.0 <= ece <= 1.0

    # Bootstrap CI
    pt, low, high = compute_bootstrap_ci(y_true, actions, compute_false_friction_rate, n_bootstraps=50)
    assert np.isclose(pt, 0.25)
    assert 0.0 <= low <= high <= 1.0
