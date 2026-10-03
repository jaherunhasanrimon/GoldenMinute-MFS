"""Narrative provider interfaces and factory for GoldenMinutes.

Defines NarrativeProvider contract, CaseNarrative data structure,
and provider selection via GM_LLM_PROVIDER environment setting.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from goldenminutes.common.config import get_settings

logger = logging.getLogger("goldenminutes.llm.provider")


@dataclass
class CaseNarrative:
    """Structured narrative summary for analysts and customers."""
    summary_en: str
    summary_bn: str
    key_evidence: Dict[str, Any] = field(default_factory=dict)
    customer_warning_en: str = ""
    customer_warning_bn: str = ""
    source: str = "template"  # "template" or "llm"


class NarrativeProvider(ABC):
    """Abstract interface for explanation and narrative generation."""

    @abstractmethod
    def summarize_case(self, evidence: Dict[str, Any]) -> CaseNarrative:
        """Generate structured narrative summary for analyst case drawer."""
        pass

    @abstractmethod
    def customer_warning(self, evidence: Dict[str, Any], lang: str = "bn") -> str:
        """Generate localized warning message for customer send-money screen."""
        pass


def get_narrative_provider(provider_type: Optional[str] = None) -> NarrativeProvider:
    """Factory selecting NarrativeProvider based on config / GM_LLM_PROVIDER.

    Defaults to TemplateProvider (safe offline default).
    If 'llm' is specified, wraps LLMProvider with strict LLMGuards and template fallback.
    """
    if provider_type is None:
        settings = get_settings()
        provider_type = settings.gm_llm_provider.lower()

    if provider_type in ["template", "default"]:
        from goldenminutes.llm.template_provider import TemplateProvider
        return TemplateProvider()
    elif provider_type in ["llm", "openai", "gemini"]:
        from goldenminutes.llm.llm_provider import GuardedLLMProvider
        return GuardedLLMProvider()
    else:
        logger.warning(f"Unknown narrative provider '{provider_type}', falling back to TemplateProvider")
        from goldenminutes.llm.template_provider import TemplateProvider
        return TemplateProvider()
