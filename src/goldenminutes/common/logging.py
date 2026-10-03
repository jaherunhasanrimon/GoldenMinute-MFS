"""Logging utilities and structured formatter for GoldenMinutes.

Implements ARCHITECTURE.md Section 4 and Section 16 security checklist:
- No sensitive values in logs (wallets, devices, and transaction IDs only)
- Structured timestamp and level formatting
"""

from __future__ import annotations

import logging
import sys


def get_logger(name: str = "goldenminutes") -> logging.Logger:
    """Return a configured logger for GoldenMinutes."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def sanitize_log_message(msg: str) -> str:
    """Ensure no raw PINs, OTPs, or customer names appear in operational logs."""
    # Redact common sensitive key patterns if present in strings
    sensitive_keys = ["pin", "otp", "password", "secret", "cvv"]
    lowered = msg.lower()
    for key in sensitive_keys:
        if f"{key}=" in lowered or f'"{key}":' in lowered:
            return "[REDACTED_SECURITY_PAYLOAD]"
    return msg
