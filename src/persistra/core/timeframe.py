from __future__ import annotations

import re

import pandas as pd

_PATTERN = re.compile(r"(\d+)([dmhw])")
_UNIT_TO_TIMEDELTA = {
    "m": lambda n: pd.Timedelta(minutes=n),
    "h": lambda n: pd.Timedelta(hours=n),
    "d": lambda n: pd.Timedelta(days=n),
    "w": lambda n: pd.Timedelta(weeks=n),
}


def parse_timeframe(timeframe: str) -> tuple[int, str]:
    """Map a timeframe string (e.g. "5m", "1d") to (multiplier, unit_char).

    Unit char is one of ``d`` (day), ``m`` (minute), ``h`` (hour), ``w`` (week).
    Raises ``ValueError`` on anything else.
    """
    match = _PATTERN.fullmatch(timeframe)
    if not match:
        raise ValueError(f"Unsupported timeframe: {timeframe!r}")
    return int(match.group(1)), match.group(2)


def timeframe_duration(timeframe: str) -> pd.Timedelta:
    """The wall-clock span of one bar at ``timeframe`` (used for ordering)."""
    multiplier, unit = parse_timeframe(timeframe)
    return _UNIT_TO_TIMEDELTA[unit](multiplier)
