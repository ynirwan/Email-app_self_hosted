# backend/core/timezone.py
"""
Timezone helpers.

Backend stores all timestamps in UTC (per CLAUDE.md §13.4). These helpers
convert at the boundary — for example, when an email body or a webhook
notification needs to show a time in the user's local timezone.

Do NOT use these to mutate stored timestamps. They produce display strings
or aware datetimes only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as _tz
from typing import Optional

import pytz

logger = logging.getLogger(__name__)

DEFAULT_TIMEZONE = "UTC"


def safe_zone(name: str | None) -> pytz.BaseTzInfo:
    """Return a pytz timezone, falling back to UTC on invalid input."""
    if not name:
        return pytz.UTC
    try:
        return pytz.timezone(name)
    except pytz.exceptions.UnknownTimeZoneError:
        logger.warning("Unknown timezone %r, falling back to UTC", name)
        return pytz.UTC


def is_valid_timezone(name: str | None) -> bool:
    """True if `name` is a known IANA zone."""
    if not name:
        return False
    try:
        pytz.timezone(name)
        return True
    except pytz.exceptions.UnknownTimeZoneError:
        return False


def to_user_tz(dt: Optional[datetime], user_tz: str | None) -> Optional[datetime]:
    """
    Convert a (naive UTC or aware) datetime to the user's timezone.

    - Naive datetimes are assumed to be UTC (matches the rest of the codebase).
    - Returns an aware datetime in the user's tz.
    - None in -> None out.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_tz.utc)
    return dt.astimezone(safe_zone(user_tz))


def format_for_user(
    dt: Optional[datetime],
    user_tz: str | None,
    fmt: str = "%Y-%m-%d %H:%M %Z",
) -> str:
    """Format a UTC datetime in the user's tz. Empty string for None."""
    converted = to_user_tz(dt, user_tz)
    if converted is None:
        return ""
    return converted.strftime(fmt)