"""Shared bounded HTTP retry guidance."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

MAX_RETRY_AFTER_SECONDS = 60.0


def retry_after_seconds(value: str | None, *, now: datetime) -> float | None:
    """Return accepted Retry-After seconds, bounded to one minute."""
    if value is None:
        return None
    text = value.strip()
    if text.isascii() and text.isdigit():
        seconds = float(int(text))
    else:
        try:
            retry_at = parsedate_to_datetime(text)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None or now.tzinfo is None:
            return None
        seconds = max(0.0, (retry_at - now).total_seconds())
    if not isfinite(seconds) or seconds > MAX_RETRY_AFTER_SECONDS:
        return None
    return seconds
