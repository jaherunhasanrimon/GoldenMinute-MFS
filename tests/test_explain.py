"""Tests for explainability and TreeSHAP feature-to-reason attribution."""

from pathlib import Path

import pytest

from goldenminutes.explain.reasons import (
    FEATURE_TO_REASON,
    VALID_REASON_CODES,
    get_reason_text,
    get_safe_action_hint,
    map_contributions_to_reasons,
)
from goldenminutes.explain.shap_explainer import TreeShapExplainer
from goldenminutes.features.specs import ALL_FEATURE_NAMES
from goldenminutes.models.risk_lgbm import RiskLGBM


def test_all_28_features_mapped_to_valid_codes():
    """Verify that every feature in ALL_FEATURE_NAMES is mapped to a valid reason code."""
    assert len(ALL_FEATURE_NAMES) == 28
    for feat in ALL_FEATURE_NAMES:
        assert feat in FEATURE_TO_REASON, f"Feature {feat} is missing from FEATURE_TO_REASON"
        code = FEATURE_TO_REASON[feat]
        assert code in VALID_REASON_CODES, f"Code {code} for feature {feat} is not in VALID_REASON_CODES"


def test_reason_texts_and_hint():
    """Verify localized reason strings exist for both en and bn."""
    for code in VALID_REASON_CODES:
        text_en = get_reason_text(code, "en")
        text_bn = get_reason_text(code, "bn")
        assert len(text_en) > 5
        assert len(text_bn) > 5

    hint_en = get_safe_action_hint("en")
    hint_bn = get_safe_action_hint("bn")
    assert "call" in hint_en.lower()
    assert len(hint_bn) > 5


def test_map_contributions_to_reasons():
    """Verify aggregation of positive SHAP contributions into normalized reason codes."""
    contribs = {
        "recipient_unique_senders_1h": 2.5,
        "recipient_inflow_24h": 1.5,
        "amount_to_median_ratio": 2.0,
        "sender_txn_count_1h": -1.0,  # Negative: reduces risk, should be ignored
    }
    reasons = map_contributions_to_reasons(contribs, top_k=2)
    assert len(reasons) == 2
    # RECIPIENT_FAN_IN_BURST should have weight (2.5 + 1.5) = 4.0
    # AMOUNT_UNUSUAL_FOR_SENDER should have weight 2.0
    # Total positive = 6.0
    assert reasons[0].code == "RECIPIENT_FAN_IN_BURST"
    assert pytest.approx(reasons[0].weight, 1e-3) == 4.0 / 6.0

    assert reasons[1].code == "AMOUNT_UNUSUAL_FOR_SENDER"
    assert pytest.approx(reasons[1].weight, 1e-3) == 2.0 / 6.0


def test_treeshap_explainer_with_model():
    """Verify TreeShapExplainer on a trained RiskLGBM model."""
    repo_root = Path(__file__).resolve().parents[1]
    model_path = repo_root / "models" / "m-1.0.0-full" / "variant_c_lgbm.joblib"
    if not model_path.exists():
        model_path = repo_root / "models" / "m-1.0.0-small" / "variant_c_lgbm.joblib"
    if not model_path.exists():
        pytest.skip("No trained model artifact available for TreeShapExplainer test")

    model = RiskLGBM.load(model_path)
    explainer = TreeShapExplainer(model)

    test_instance = {feat: 0.0 for feat in ALL_FEATURE_NAMES}
    test_instance["recipient_unique_senders_1h"] = 5
    test_instance["recipient_inflow_24h"] = 50000.0
    test_instance["amount_to_median_ratio"] = 4.0

    shap_vals = explainer.explain_instance(test_instance)
    assert len(shap_vals) == 28
    assert all(feat in shap_vals for feat in ALL_FEATURE_NAMES)

    reasons = explainer.get_top_reasons(test_instance, top_k=3)
    assert len(reasons) > 0
    assert all(r.code in VALID_REASON_CODES for r in reasons)
