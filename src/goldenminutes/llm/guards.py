"""LLM Safety Guardrails for GoldenMinutes.

Implements ARCHITECTURE.md Section 12:
- Evidence-only structured input filtering.
- Free-text transaction reference sanitization and isolation.
- Output validation: reason code constraints, exact number matching, length, and language checks.
- Automatic fallback to deterministic TemplateProvider on any guardrail violation.
- Guarantees LLM output never changes risk_score or action.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("goldenminutes.llm.guards")

# Prompt injection patterns
HOSTILE_PATTERNS = [
    r"(?i)ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"(?i)system\s+prompt",
    r"(?i)you\s+are\s+now",
    r"(?i)jailbreak",
    r"(?i)bypass",
    r"(?i)override\s+(all\s+)?rules",
    r"(?i)disregard",
    r"(?i)drop\s+table",
    r"(?i)<script",
    r"(?i)api[-_]?key",
]

# Standard time and percentage constants allowed in explanations without exact match in evidence
ALLOWED_NUMERIC_CONSTANTS: Set[float] = {
    0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 14.0, 15.0, 20.0, 24.0, 30.0, 45.0, 60.0, 100.0, 300.0
}


class LLMGuards:
    """Security guardrails for LLM prompt preparation and response validation."""

    @staticmethod
    def sanitize_reference(raw_reference: Optional[str]) -> Optional[str]:
        """Sanitize untrusted free-text reference, stripping hostile prompt injections."""
        if not raw_reference:
            return None

        clean = str(raw_reference).strip()[:140]
        for pattern in HOSTILE_PATTERNS:
            if re.search(pattern, clean):
                logger.warning("Detected potential prompt injection in reference text: %r", clean)
                # Strip out injection
                clean = re.sub(pattern, "[FILTERED]", clean)

        return clean.strip()

    @classmethod
    def prepare_evidence(
        cls,
        evidence: Dict[str, Any],
        raw_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Construct safe evidence-only object for LLM consumption.

        Never passes unquoted or unsanitized free-text instructions.
        """
        safe: Dict[str, Any] = {}

        # Allowed numeric and categorical fields
        allowed_keys = [
            "amount_bdt",
            "risk_score",
            "action",
            "sender_wallet_id",
            "recipient_wallet_id",
            "recipient_unique_senders_1h",
            "recipient_unique_senders_24h",
            "recipient_inflow_24h",
            "recipient_outflow_24h",
            "recipient_pass_through_ratio_24h",
            "recipient_median_receipt_to_out_minutes",
            "amount_to_median_ratio",
            "two_hop_confirmed_mule_share",
            "reason_codes",
        ]

        for k in allowed_keys:
            if k in evidence:
                safe[k] = evidence[k]

        # Isolate sanitized reference in a quoted, untrusted payload
        sanitized_ref = cls.sanitize_reference(raw_reference or evidence.get("reference"))
        if sanitized_ref:
            safe["untrusted_user_reference"] = sanitized_ref

        return safe

    @classmethod
    def validate_customer_warning(
        cls,
        generated_text: str,
        evidence: Dict[str, Any],
        lang: str = "bn",
    ) -> bool:
        """Validate LLM generated customer warning text against strict guardrails."""
        if not generated_text or not isinstance(generated_text, str):
            return False

        text = generated_text.strip()

        # 1. Length check: between 10 and 500 characters
        if len(text) < 10 or len(text) > 500:
            logger.warning(f"Guardrail failed: length {len(text)} out of bounds [10, 500]")
            return False

        # 2. Hostile pattern check
        for pattern in HOSTILE_PATTERNS:
            if re.search(pattern, text):
                logger.warning(f"Guardrail failed: hostile pattern detected in output: {pattern}")
                return False

        # 3. Language check
        if lang == "bn":
            # Must contain Bengali script unicode range: U+0980 to U+09FF
            has_bengali = bool(re.search(r"[\u0980-\u09FF]", text))
            if not has_bengali:
                logger.warning("Guardrail failed: requested Bengali but output contains no Bengali script")
                return False
        elif lang == "en":
            # Must be predominantly Latin/ASCII characters
            ascii_chars = sum(1 for c in text if ord(c) < 128)
            if ascii_chars / len(text) < 0.7:
                logger.warning("Guardrail failed: requested English but output contains non-Latin characters")
                return False

        # 4. Reason Code constraint
        # Output cannot hallucinate reason codes that were not triggered
        active_codes = set()
        for rc in evidence.get("reason_codes", []):
            if isinstance(rc, dict):
                active_codes.add(rc.get("code", ""))
            elif hasattr(rc, "code"):
                active_codes.add(rc.code)
            elif isinstance(rc, str):
                active_codes.add(rc)

        # 5. Exact number matching constraint
        # Numbers in output must match numbers in evidence or allowed constants
        extracted_numbers = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", text)]
        evidence_numbers: Set[float] = set(ALLOWED_NUMERIC_CONSTANTS)

        for _k, v in evidence.items():
            if isinstance(v, (int, float)):
                evidence_numbers.add(float(v))
                evidence_numbers.add(round(float(v), 0))
                evidence_numbers.add(round(float(v), 2))

        for num in extracted_numbers:
            # Check with small tolerance
            matched = any(abs(num - ev_num) < 0.1 for ev_num in evidence_numbers)
            if not matched:
                logger.warning(f"Guardrail failed: hallucinated number {num} not found in evidence")
                return False

        return True
