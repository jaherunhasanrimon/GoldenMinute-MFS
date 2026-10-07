"""Prompt Injection and Adversarial Input Sanitizer for GoldenMinutes LLM & Narrative Pipeline."""

from __future__ import annotations

import base64
import html
import re
from typing import Any, Dict, Optional, Tuple

# Adversarial prompt injection keywords & patterns (English, Bangla, leetspeak, delimiters)
INJECTION_PATTERNS = [
    # English instruction overrides
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(prior|previous|above)?\s*(rules|prompts|directions|instructions?)", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?(rules|safeguards|limits|checks)", re.IGNORECASE),
    re.compile(r"system\s*prompt:?", re.IGNORECASE),
    re.compile(r"system\s*:?\s*override:?", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"bypass", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(an?\s+)?unrestricted", re.IGNORECASE),
    re.compile(r"(always|must)\s+(output|respond|return)\s+(allow|legit|safe|approved)", re.IGNORECASE),
    re.compile(r"set\s+risk(\s+score)?\s*(to|=)\s*0", re.IGNORECASE),
    re.compile(r"do\s+not\s+(alert|flag|hold|warn|verify)", re.IGNORECASE),
    re.compile(r"jailbreak|dan\s+mode|developer\s+mode", re.IGNORECASE),
    # Delimiters and LLM control tokens
    re.compile(r"<\|im_start\|>|<\|im_end\|>|<\|system\|>|<\|assistant\|>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>", re.IGNORECASE),
    re.compile(r"###\s*(instruction|system|human|assistant)\s*:", re.IGNORECASE),
    re.compile(r"^\s*---\s*system\s*:\s*", re.IGNORECASE | re.MULTILINE),
    # Bangla instruction overrides
    re.compile(r"তুমি\s+(আগের|পূর্বের)\s+সব\s+নির্দেশ\s+(ভুলে\s+যাও|মুছে\s+ফেল)", re.IGNORECASE),
    re.compile(r"সব\s+লেনদেন\s+(অনুমোদন|অ্যালাও|পাস)\s+করো?", re.IGNORECASE),
    re.compile(r"ঝু[\u0981]?কি\s*(স্কোর)?\s*(শূন্য|জিরো|০)\s*করো?", re.IGNORECASE),
    re.compile(r"কোনো\s+(অ্যালার্ট|হোল্ড|সতর্কবার্তা)\s+দিও\s+না", re.IGNORECASE),
    re.compile(r"সিস্টেম\s+ওভাররাইড|নতুন\s+ভূমিকা\s+গ্রহণ\s+করো", re.IGNORECASE),
]


def detect_prompt_injection(text: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Inspect text for prompt injection, jailbreaks, or delimiter manipulation.

    Returns (is_injected, matched_pattern).
    """
    if not text:
        return False, None

    # Check for direct regex matches
    for pattern in INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, match.group(0)

    # Check for hidden base64 encoded injection
    b64_matches = re.findall(r"[A-Za-z0-9+/=]{20,}", text)
    for b64_cand in b64_matches:
        try:
            decoded = base64.b64decode(b64_cand, validate=True).decode("utf-8", errors="ignore")
            for pattern in INJECTION_PATTERNS:
                if pattern.search(decoded):
                    return True, f"base64_encoded:{pattern.pattern}"
        except Exception:
            pass

    return False, None


def sanitize_text(text: Optional[str], max_length: int = 500) -> str:
    """Sanitize free-text fields (e.g. transaction reference, notes) to neutralize prompt injection.

    Strips control characters, HTML entities, and neutralizes jailbreak triggers.
    """
    if not text:
        return ""

    # Truncate
    cleaned = str(text)[:max_length]

    # HTML escape
    cleaned = html.escape(cleaned)

    # Remove LLM control tokens
    cleaned = re.sub(r"<\|.*?\|>", "", cleaned)
    cleaned = re.sub(r"\[/?INST\]|<<SYS>>|<</SYS>>", "", cleaned)
    cleaned = re.sub(r"###\s*(instruction|system|human|assistant)\s*:", "[redacted_directive]:", cleaned, flags=re.IGNORECASE)

    # Neutralize instruction overrides
    for pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub("[REDACTED_ADVERSARIAL_INPUT]", cleaned)

    return cleaned.strip()


def sanitize_evidence_for_narrative(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize evidence dictionary before passing to narrative generator/LLM.

    Ensures that values in references or user strings cannot hijack prompt templates.
    """
    sanitized: Dict[str, Any] = {}
    for k, v in evidence.items():
        if isinstance(v, str):
            sanitized[k] = sanitize_text(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_evidence_for_narrative(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_text(item) if isinstance(item, str) else item for item in v]
        else:
            sanitized[k] = v
    return sanitized
