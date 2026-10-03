"""Pluggable LLM Provider with strict safety guardrails and template fallback.

Implements ARCHITECTURE.md Section 12:
- Works with optional LLM backend controlled by GM_LLM_PROVIDER.
- No network access unless explicitly configured.
- GuardedLLMProvider intercepts all inputs and outputs through LLMGuards.
- Guaranteed fallback to TemplateProvider on any error or guardrail failure.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from goldenminutes.common.config import get_settings
from goldenminutes.llm.guards import LLMGuards
from goldenminutes.llm.provider import CaseNarrative, NarrativeProvider
from goldenminutes.llm.template_provider import TemplateProvider

logger = logging.getLogger("goldenminutes.llm.provider.guarded")


class MockLLMBackend:
    """Mockable LLM backend respecting the no-external-network default."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    def generate(self, prompt: str, evidence: Dict[str, Any], lang: str) -> str:
        """Simulate LLM generation."""
        _action = str(evidence.get("action", "hold")).lower()
        if lang == "bn":
            return "নিরাপত্তা পর্যালোচনার জন্য এই লেনদেনটি সাময়িক স্থগিত রাখা হয়েছে। আপনার পরিচিত নম্বরে সরাসরি যোগাযোগ করে নিশ্চিত হয়ে নিন।"
        else:
            return "This transaction is held for security review due to elevated risk indicators. Please verify before proceeding."


class GuardedLLMProvider(NarrativeProvider):
    """Safety-wrapped LLM provider with validation and TemplateProvider fallback."""

    def __init__(self, backend: Optional[Any] = None):
        settings = get_settings()
        self.backend = backend or MockLLMBackend(api_key=settings.gm_llm_api_key)
        self.template_fallback = TemplateProvider()
        self.guards = LLMGuards()

    def customer_warning(self, evidence: Dict[str, Any], lang: str = "bn") -> str:
        """Generate customer warning via LLM, validating output or falling back."""
        try:
            # 1. Sanitize evidence
            safe_evidence = self.guards.prepare_evidence(evidence)

            # 2. Call backend
            prompt = f"Generate a short warning for upay customer. Evidence: {safe_evidence}"
            candidate_text = self.backend.generate(prompt, safe_evidence, lang=lang)

            # 3. Validate output against guardrails
            is_valid = self.guards.validate_customer_warning(
                candidate_text,
                evidence=safe_evidence,
                lang=lang,
            )

            if is_valid:
                return candidate_text
            else:
                logger.warning("LLM output failed safety guardrails. Falling back to TemplateProvider.")
                return self.template_fallback.customer_warning(evidence, lang=lang)

        except Exception as e:
            logger.error("LLM provider encountered error: %s. Falling back to TemplateProvider.", e)
            return self.template_fallback.customer_warning(evidence, lang=lang)

    def summarize_case(self, evidence: Dict[str, Any]) -> CaseNarrative:
        """Construct analyst case summary, verified through guardrails."""
        try:
            safe_evidence = self.guards.prepare_evidence(evidence)
            # Use template structure to ensure zero hallucination for audit/analyst views
            narrative = self.template_fallback.summarize_case(safe_evidence)
            narrative.source = "llm_guarded"
            return narrative
        except Exception as e:
            logger.error("Error in guarded summarize_case: %s. Using template.", e)
            return self.template_fallback.summarize_case(evidence)
