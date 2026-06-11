from persistra.data.calendar import TradingCalendar


def test_sessions_are_tz_naive_and_exclude_holidays():
    cal = TradingCalendar("XNYS")
    sessions = cal.sessions("2021-12-31", "2022-01-03")
    # 2022-01-01 (Sat/holiday) and 2022-01-02 (Sun) are not sessions.
    assert sessions.tz is None
    dates = [s.strftime("%Y-%m-%d") for s in sessions]
    assert "2022-01-01" not in dates
    assert "2021-12-31" in dates
    assert "2022-01-03" in dates


def test_is_session_true_for_weekday_false_for_weekend():
    cal = TradingCalendar("XNYS")
    assert cal.is_session("2022-01-03") is True  # Monday
    assert cal.is_session("2022-01-01") is False  # Saturday
