import pandas as pd

from persistra.core.events import BarCloseEvent
from persistra.core.history import HistoryView


def _bar(t, symbol, close):
    return BarCloseEvent(
        timestamp=t, symbol=symbol, open=close, high=close, low=close, close=close, volume=1.0
    )


def test_closes_returns_sorted_columns_and_recent_rows(populated_history):
    closes = populated_history.closes(10)
    assert list(closes.columns) == ["AAA", "BBB"]
    assert closes["AAA"].tolist() == [100.0, 110.0, 99.0, 115.0]
    assert len(closes.index) == 4


def test_available_bars_caps_at_max_bars():
    hist = HistoryView(max_bars=3)
    times = list(pd.bdate_range("2022-01-03", periods=6))
    for t in times:
        hist.update(_bar(t, "AAA", 100.0))
    assert hist.available_bars() == 3
    # Only the last 3 timestamps survive.
    assert hist.closes(10).index.tolist() == times[-3:]


def test_lookback_truncates_returned_rows(populated_history):
    assert len(populated_history.closes(2).index) == 2
