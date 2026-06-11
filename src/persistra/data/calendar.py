from __future__ import annotations

import exchange_calendars as ec  # pyright: ignore[reportMissingTypeStubs]
import pandas as pd


class TradingCalendar:
    """Thin wrapper over an ``exchange_calendars`` calendar.

    Normalises all session timestamps to tz-naive midnight so the rest of the
    kernel can compare against tz-naive ``bar_time`` values without conversion.
    """

    def __init__(self, name: str = "XNYS") -> None:
        self.name = name
        self._cal = ec.get_calendar(name)

    @staticmethod
    def _naive(ts: str | pd.Timestamp) -> pd.Timestamp:
        t = pd.Timestamp(ts)
        if t.tzinfo is not None:
            t = t.tz_convert("UTC").tz_localize(None)
        return t.normalize()

    def sessions(self, start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
        """Return tz-naive trading-session timestamps in ``[start, end]``."""
        sessions = self._cal.sessions_in_range(self._naive(start), self._naive(end))
        idx = pd.DatetimeIndex(sessions)
        if idx.tz is not None:
            idx = idx.tz_convert("UTC").tz_localize(None)
        return idx

    def is_session(self, ts: str | pd.Timestamp) -> bool:
        """Return ``True`` if ``ts`` falls on a trading session.

        Args:
            ts: Date or timestamp to test.  Timezone information is stripped
                by normalising to tz-naive UTC midnight before the lookup.

        Returns:
            ``True`` when ``ts`` is a trading session in this calendar,
            ``False`` otherwise.
        """
        return bool(self._cal.is_session(self._naive(ts)))
