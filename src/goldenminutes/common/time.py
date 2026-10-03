"""Timezone and time calculation utilities for GoldenMinutes.

Implements ARCHITECTURE.md Section 5 (Asia/Dhaka and UTC timestamp conventions)
and Section 11 (golden window time calculations).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

DHAKA_TZ = ZoneInfo("Asia/Dhaka")
UTC_TZ = timezone.utc


def now_utc() -> datetime:
    """Return the current datetime in UTC."""
    return datetime.now(UTC_TZ)


def now_dhaka() -> datetime:
    """Return the current datetime in Asia/Dhaka."""
    return datetime.now(DHAKA_TZ)


def to_utc(dt: datetime) -> datetime:
    """Ensure datetime has UTC timezone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(UTC_TZ)


def to_dhaka(dt: datetime) -> datetime:
    """Convert datetime to Asia/Dhaka timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(DHAKA_TZ)


def calculate_golden_window_remaining(
    first_inflow_ts: datetime,
    current_ts: Optional[datetime] = None,
    golden_window_minutes: float = 30.0,
) -> float:
    """Calculate remaining minutes in the 30-minute golden window before physical cashout."""
    now = current_ts or now_utc()
    elapsed_minutes = (now - first_inflow_ts).total_seconds() / 60.0
    return max(0.0, golden_window_minutes - elapsed_minutes)
