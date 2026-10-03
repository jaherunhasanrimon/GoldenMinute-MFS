"""Reason code definitions and feature-to-reason mapping for GoldenMinutes.

Implements ARCHITECTURE.md Section 12 and PHASES_GoldenMinutes.md Phase P5:
- Maps every one of the 28 features to a human-understandable reason code.
- Provides bilingual (Bangla and English) user-facing warning strings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import yaml

from goldenminutes.common.schemas import ReasonCode
from goldenminutes.features.specs import ALL_FEATURE_NAMES

# Complete mapping from all 28 point-in-time features to reason codes
FEATURE_TO_REASON: Dict[str, str] = {
    # Sender features
    "amount_to_median_ratio": "AMOUNT_UNUSUAL_FOR_SENDER",
    "sender_txn_count_1h": "AMOUNT_UNUSUAL_FOR_SENDER",
    "sender_txn_count_24h": "AMOUNT_UNUSUAL_FOR_SENDER",
    "sender_amount_sum_24h": "AMOUNT_UNUSUAL_FOR_SENDER",
    "sender_tenure_days": "DEVICE_OR_PIN_CHANGE_RECENT",
    "balance_drain_ratio": "AMOUNT_UNUSUAL_FOR_SENDER",
    "hour_of_day": "AMOUNT_UNUSUAL_FOR_SENDER",
    "is_night": "AMOUNT_UNUSUAL_FOR_SENDER",
    # Pair features
    "is_first_time_pair": "FIRST_TIME_PAIR",
    "pair_history_count": "FIRST_TIME_PAIR",
    # Device and Auth features
    "new_device_flag": "DEVICE_OR_PIN_CHANGE_RECENT",
    "minutes_since_pin_reset": "DEVICE_OR_PIN_CHANGE_RECENT",
    "minutes_since_sim_change": "DEVICE_OR_PIN_CHANGE_RECENT",
    "session_seconds": "DEVICE_OR_PIN_CHANGE_RECENT",
    # Recipient features
    "recipient_age_days": "RECIPIENT_NEW",
    "recipient_owner_type_code": "RING_LINK",
    "recipient_unique_senders_1h": "RECIPIENT_FAN_IN_BURST",
    "recipient_unique_senders_24h": "RECIPIENT_FAN_IN_BURST",
    "recipient_first_time_sender_share_24h": "RECIPIENT_FAN_IN_BURST",
    "recipient_inflow_24h": "RECIPIENT_FAN_IN_BURST",
    "recipient_outflow_24h": "RECIPIENT_FAST_PASS_THROUGH",
    "recipient_pass_through_ratio_24h": "RECIPIENT_FAST_PASS_THROUGH",
    "recipient_median_receipt_to_out_minutes": "RECIPIENT_FAST_PASS_THROUGH",
    # Graph features
    "recipient_fan_in_7d": "RECIPIENT_FAN_IN_BURST",
    "recipient_fan_out_7d": "RECIPIENT_FAST_PASS_THROUGH",
    "shared_device_wallet_count": "RING_LINK",
    "component_size_7d": "RING_LINK",
    "two_hop_confirmed_mule_share": "RING_LINK",
}

# Verify that every feature in ALL_FEATURE_NAMES is mapped
assert all(f in FEATURE_TO_REASON for f in ALL_FEATURE_NAMES), (
    "Not all features are mapped to reason codes!"
)

VALID_REASON_CODES: Set[str] = {
    "RECIPIENT_NEW",
    "RECIPIENT_FAN_IN_BURST",
    "RECIPIENT_FAST_PASS_THROUGH",
    "AMOUNT_UNUSUAL_FOR_SENDER",
    "DEVICE_OR_PIN_CHANGE_RECENT",
    "FIRST_TIME_PAIR",
    "RING_LINK",
}


def load_reasons_config(config_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Load reasons configuration containing translations and mappings."""
    if config_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        config_path = repo_root / "configs" / "reasons.yaml"

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_reason_text(code: str, lang: str = "en") -> str:
    """Get localized text for a reason code."""
    cfg = load_reasons_config()
    code_data = cfg.get(code, {})
    return str(code_data.get(lang, code))


def get_safe_action_hint(lang: str = "en") -> str:
    """Get localized call-first hint."""
    cfg = load_reasons_config()
    hint_data = cfg.get("SAFE_ACTION_HINT", {})
    return str(hint_data.get(lang, "Before sending, call the person directly."))


def map_contributions_to_reasons(
    feature_contributions: Dict[str, float],
    top_k: int = 3,
) -> List[ReasonCode]:
    """Aggregate feature SHAP contributions into prioritized reason codes.

    Positive SHAP values represent evidence increasing the probability of fraud.
    """
    code_weights: Dict[str, float] = {}

    for feat_name, contrib in feature_contributions.items():
        if contrib > 0:
            code = FEATURE_TO_REASON.get(feat_name, "RING_LINK")
            code_weights[code] = code_weights.get(code, 0.0) + float(contrib)

    if not code_weights:
        return []

    # Normalize weights so they sum to 1.0 (or proportional confidence)
    total_pos = sum(code_weights.values())
    sorted_codes = sorted(code_weights.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

    return [
        ReasonCode(
            code=code,
            weight=round(weight / total_pos, 4),
        )
        for code, weight in sorted_codes
    ]
