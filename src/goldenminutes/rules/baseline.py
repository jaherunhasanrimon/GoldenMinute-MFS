"""Deterministic rules engine (Variant A baseline) for GoldenMinutes.

Implements rules R1–R5 defined in ARCHITECTURE.md Section 9 with thresholds
configured in configs/models.yaml.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yaml


class RulesBaseline:
    """Rules-based fraud detection engine implementing rules R1 to R5."""

    def __init__(self, config_path: Optional[Path | str] = None, rules_cfg: Optional[Dict[str, Any]] = None):
        if rules_cfg is not None:
            self.cfg = rules_cfg
        else:
            if config_path is None:
                repo_root = Path(__file__).resolve().parents[3]
                config_path = repo_root / "configs" / "models.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self.cfg = data.get("rules", {})

        # Rule thresholds with fallback defaults
        self.r1_recipient_age_days = float(self.cfg.get("r1_recipient_age_days", 3.0))
        self.r1_amount_threshold = float(self.cfg.get("r1_amount_threshold", 10000.0))

        self.r2_balance_drain_ratio = float(self.cfg.get("r2_balance_drain_ratio", 0.8))

        self.r3_auth_recent_minutes = float(self.cfg.get("r3_auth_recent_minutes", 60.0))
        self.r3_amount_threshold = float(self.cfg.get("r3_amount_threshold", 15000.0))

        self.r4_unique_senders_1h = int(self.cfg.get("r4_unique_senders_1h", 5))
        self.r4_first_time_share = float(self.cfg.get("r4_first_time_share", 0.6))

        self.r5_rapid_cashout_count = int(self.cfg.get("r5_rapid_cashout_count", 3))
        self.r5_window_minutes = float(self.cfg.get("r5_window_minutes", 10.0))

    def evaluate_batch(self, df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized evaluation of rules R1–R5 across a dataframe.

        Returns a DataFrame with columns:
        - rule_r1, rule_r2, rule_r3, rule_r4, rule_r5 (bool)
        - rules_hit_count (int)
        - risk_score (float in [0.0, 1.0])
        - action (Literal['allow', 'warn', 'verify', 'hold'])
        """
        # R1: recipient younger than 3 days AND amount above threshold
        r1 = (df["recipient_age_days"] < self.r1_recipient_age_days) & (
            df["amount_bdt"] >= self.r1_amount_threshold
        )

        # R2: amount above 80% balance AND first-time recipient
        r2 = (df["balance_drain_ratio"] >= self.r2_balance_drain_ratio) & (
            df["is_first_time_pair"] == 1
        )

        # R3: PIN reset or SIM change within 60 minutes AND high amount
        auth_recent = (df["minutes_since_pin_reset"] <= self.r3_auth_recent_minutes) | (
            df["minutes_since_sim_change"] <= self.r3_auth_recent_minutes
        )
        r3 = auth_recent & (df["amount_bdt"] >= self.r3_amount_threshold)

        # R4: 5+ unique senders in 1h, mostly first-time
        r4 = (df["recipient_unique_senders_1h"] >= self.r4_unique_senders_1h) & (
            df["recipient_first_time_sender_share_24h"] >= self.r4_first_time_share
        )

        # R5: 3+ receipts cashed out within 10 minutes each
        r5 = (df["recipient_median_receipt_to_out_minutes"] <= self.r5_window_minutes) & (
            df["recipient_pass_through_ratio_24h"] > 0.5
        )

        rule_hits = pd.DataFrame(
            {
                "rule_r1": r1.values,
                "rule_r2": r2.values,
                "rule_r3": r3.values,
                "rule_r4": r4.values,
                "rule_r5": r5.values,
            },
            index=df.index,
        )

        rules_hit_count = rule_hits.sum(axis=1).astype(int)
        rule_hits["rules_hit_count"] = rules_hit_count

        # Score mapping: proportional to hit severity and count
        # R4, R5, R3 are high risk (0.85 - 0.95), R1 is medium-high (0.75), R2 is warn (0.45)
        raw_score = (
            rule_hits["rule_r4"].astype(float) * 0.95
            + rule_hits["rule_r5"].astype(float) * 0.90
            + rule_hits["rule_r3"].astype(float) * 0.85
            + rule_hits["rule_r1"].astype(float) * 0.75
            + rule_hits["rule_r2"].astype(float) * 0.45
        )
        risk_score = np.clip(raw_score, 0.0, 1.0)
        rule_hits["risk_score"] = risk_score

        # Action assignment:
        # hold: high severity or multiple rules
        # verify: R1 or R3 alone
        # warn: R2 alone
        # allow: no rules hit
        actions = np.full(len(df), "allow", dtype=object)
        actions[rule_hits["rule_r2"]] = "warn"
        actions[rule_hits["rule_r1"]] = "verify"
        actions[rule_hits["rule_r3"] | rule_hits["rule_r4"] | rule_hits["rule_r5"]] = "hold"
        actions[rules_hit_count >= 2] = "hold"
        rule_hits["action"] = actions

        return rule_hits

    def evaluate_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate rules for a single transaction feature dictionary."""
        r1 = (float(row.get("recipient_age_days", 0.0)) < self.r1_recipient_age_days) and (
            float(row.get("amount_bdt", 0.0)) >= self.r1_amount_threshold
        )
        r2 = (float(row.get("balance_drain_ratio", 0.0)) >= self.r2_balance_drain_ratio) and (
            int(row.get("is_first_time_pair", 0)) == 1
        )
        auth_recent = (
            float(row.get("minutes_since_pin_reset", 43200.0)) <= self.r3_auth_recent_minutes
        ) or (float(row.get("minutes_since_sim_change", 43200.0)) <= self.r3_auth_recent_minutes)
        r3 = auth_recent and (float(row.get("amount_bdt", 0.0)) >= self.r3_amount_threshold)

        r4 = (int(row.get("recipient_unique_senders_1h", 0)) >= self.r4_unique_senders_1h) and (
            float(row.get("recipient_first_time_sender_share_24h", 0.0)) >= self.r4_first_time_share
        )
        r5 = (
            float(row.get("recipient_median_receipt_to_out_minutes", 1440.0)) <= self.r5_window_minutes
        ) and (float(row.get("recipient_pass_through_ratio_24h", 0.0)) > 0.5)

        hits: List[str] = []
        reason_codes: List[Dict[str, Any]] = []

        if r1:
            hits.append("R1")
            reason_codes.append({"code": "RECIPIENT_NEW", "weight": 0.40})
            reason_codes.append({"code": "AMOUNT_UNUSUAL_FOR_SENDER", "weight": 0.35})
        if r2:
            hits.append("R2")
            reason_codes.append({"code": "FIRST_TIME_PAIR", "weight": 0.30})
            reason_codes.append({"code": "AMOUNT_UNUSUAL_FOR_SENDER", "weight": 0.25})
        if r3:
            hits.append("R3")
            reason_codes.append({"code": "DEVICE_OR_PIN_CHANGE_RECENT", "weight": 0.50})
            reason_codes.append({"code": "AMOUNT_UNUSUAL_FOR_SENDER", "weight": 0.35})
        if r4:
            hits.append("R4")
            reason_codes.append({"code": "RECIPIENT_FAN_IN_BURST", "weight": 0.55})
            reason_codes.append({"code": "FIRST_TIME_PAIR", "weight": 0.30})
        if r5:
            hits.append("R5")
            reason_codes.append({"code": "RECIPIENT_FAST_PASS_THROUGH", "weight": 0.60})

        # Score & action
        if r4 or r5 or len(hits) >= 2:
            action = "hold"
            risk_score = 0.92
        elif r3:
            action = "hold"
            risk_score = 0.86
        elif r1:
            action = "verify"
            risk_score = 0.76
        elif r2:
            action = "warn"
            risk_score = 0.48
        else:
            action = "allow"
            risk_score = 0.02

        # Deduplicate top 3 reason codes
        seen = set()
        top_reasons = []
        for rc in sorted(reason_codes, key=lambda x: x["weight"], reverse=True):
            if rc["code"] not in seen and len(top_reasons) < 3:
                seen.add(rc["code"])
                top_reasons.append(rc)

        return {
            "rules_hit": hits,
            "rules_hit_count": len(hits),
            "risk_score": risk_score,
            "action": action,
            "reason_codes": top_reasons,
        }
