import pandas as pd

from persistra.core.events import (
    BarCloseEvent,
    DividendEvent,
    FillEvent,
    OrderEvent,
    OrderType,
    SplitEvent,
)

T = pd.Timestamp("2023-01-03")


def _bar(close=100.0):
    return BarCloseEvent(
        timestamp=T, symbol="AAA", open=close, high=close, low=close, close=close, volume=1.0
    )


def test_corporate_actions_sort_before_bar_close():
    div = DividendEvent(timestamp=T, symbol="AAA", amount=1.0)
    split = SplitEvent(timestamp=T, symbol="AAA", ratio=2.0)
    assert div < _bar()
    assert split < _bar()


def test_priority_chain_corporate_close_order_fill():
    div = DividendEvent(timestamp=T, symbol="AAA", amount=1.0)
    bar = _bar()
    order = OrderEvent(timestamp=T, symbol="AAA", order_type=OrderType.MOC, quantity=1.0)
    fill = FillEvent(timestamp=T, symbol="AAA", quantity=1.0, fill_price=100.0, commission=0.0)
    ordered = sorted([fill, order, bar, div])
    assert ordered == [div, bar, order, fill]


def test_earlier_timestamp_sorts_first_regardless_of_priority():
    early_fill = FillEvent(timestamp=T, symbol="AAA", quantity=1.0, fill_price=1.0, commission=0.0)
    late_div = DividendEvent(timestamp=T + pd.Timedelta(days=1), symbol="AAA", amount=1.0)
    assert early_fill < late_div
