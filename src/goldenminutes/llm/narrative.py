"""Narrative generation models and utilities for GoldenMinutes.

Implements ARCHITECTURE.md Section 4 and Section 12:
- CaseNarrative data model
- Evidence formatting for bilingual summaries
- Extraction of safe structured evidence for analyst case drawers
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from goldenminutes.llm.provider import CaseNarrative, NarrativeProvider, get_narrative_provider


def build_evidence_summary(
    risk_score: float,
    action: str,
    reason_codes: List[Dict[str, Any]],
    features: Optional[Dict[str, Any]] = None,
    txn_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Construct safe structured evidence object according to Section 12 guardrails."""
    feat = features or {}
    ctx = txn_context or {}

    return {
        "risk_score": float(risk_score),
        "action": str(action),
        "amount_bdt": float(ctx.get("amount_bdt", feat.get("amount_bdt", 0.0))),
        "sender_wallet_id": str(ctx.get("sender_wallet_id", "")),
        "recipient_wallet_id": str(ctx.get("recipient_wallet_id", "")),
        "reason_codes": [rc.get("code") for rc in reason_codes if isinstance(rc, dict) and "code" in rc],
        "reasons_detail": reason_codes,
        "new_device": bool(feat.get("new_device_flag", 0) > 0),
        "tenure_days": float(feat.get("sender_tenure_days", 0.0)),
        "inflow_velocity_1h": int(feat.get("recipient_unique_senders_1h", 0)),
        "pass_through_ratio": float(feat.get("recipient_pass_through_ratio_24h", 0.0)),
    }


def generate_case_narrative(
    evidence: Dict[str, Any],
    provider: Optional[NarrativeProvider] = None,
) -> CaseNarrative:
    """Generate structured narrative using the configured narrative provider."""
    narrative_svc = provider or get_narrative_provider()
    return narrative_svc.summarize_case(evidence)
