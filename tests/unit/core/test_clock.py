import pytest

from persistra.core.clock import Clock
from persistra.data.calendar import TradingCalendar


def test_clock_finest_is_smallest_duration():
    clock = Clock(TradingCalendar("XNYS"), timeframes=("1d", "1h"))
    assert clock.finest == "1h"


def test_clock_rejects_bad_timeframe():
    with pytest.raises(ValueError):
        Clock(TradingCalendar("XNYS"), timeframes=("banana",))


def test_clock_sessions_excludes_weekends():
    clock = Clock(TradingCalendar("XNYS"))
    sessions = clock.sessions("2022-01-03", "2022-01-10")  # Mon..Mon
    # 2022-01-08/09 are a weekend; expect 6 sessions (Mon-Fri + Mon).
    assert len(sessions) == 6
    assert sessions.tz is None
