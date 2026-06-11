from __future__ import annotations

from typing import TYPE_CHECKING

from .timeframe import parse_timeframe, timeframe_duration

if TYPE_CHECKING:
    import pandas as pd

    from persistra.data.calendar import TradingCalendar


class Clock:
    """Schedules the timeframe grid the engine iterates over.

    The engine is data-driven: the clock yields calendar sessions for the outer
    loop and validates the subscribed timeframes; it does not generate an
    intraday grid. Bar-close timing within a session comes from the bars
    themselves (see ``Engine``).
    """

    def __init__(self, calendar: TradingCalendar, timeframes: tuple[str, ...] = ("1d",)) -> None:
        for tf in timeframes:
            parse_timeframe(tf)  # raises ValueError on an unparseable timeframe
        self._calendar = calendar
        self.timeframes = tuple(timeframes)

    def sessions(self, start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
        """Return all trading sessions between ``start`` and ``end`` inclusive.

        Args:
            start: First date of the range, as an ISO string or
                ``pd.Timestamp``.
            end: Last date of the range, as an ISO string or
                ``pd.Timestamp``.

        Returns:
            A ``pd.DatetimeIndex`` of session open timestamps in ascending
            order, as reported by the underlying ``TradingCalendar``.
        """
        return self._calendar.sessions(start, end)

    @property
    def finest(self) -> str:
        """The subscribed timeframe with the smallest bar duration."""
        return min(self.timeframes, key=timeframe_duration)
