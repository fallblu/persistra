"""Tests for core/queue.py — EventQueue priority ordering."""

from __future__ import annotations

import pandas as pd

from persistra.core.events import BarCloseEvent, DividendEvent, FillEvent, OrderEvent, OrderType
from persistra.core.queue import EventQueue

T = pd.Timestamp("2023-01-03")


def _bar(close: float = 100.0) -> BarCloseEvent:
    return BarCloseEvent(
        timestamp=T, symbol="AAA", open=close, high=close, low=close, close=close, volume=1.0
    )


def _fill() -> FillEvent:
    return FillEvent(timestamp=T, symbol="AAA", quantity=1.0, fill_price=100.0, commission=0.0)


def test_queue_empty_initially():
    q = EventQueue()
    assert q.empty()
    assert len(q) == 0


def test_put_then_get_returns_correct_event():
    q = EventQueue()
    bar = _bar()
    q.put(bar)
    assert not q.empty()
    assert len(q) == 1
    result = q.get()
    assert result is bar
    assert q.empty()


def test_priority_order_div_before_bar_before_order_before_fill():
    q = EventQueue()
    fill = _fill()
    bar = _bar()
    div = DividendEvent(timestamp=T, symbol="AAA", amount=1.0)
    order = OrderEvent(timestamp=T, symbol="AAA", order_type=OrderType.MOC, quantity=1.0)
    # Insert in arbitrary order
    for e in (fill, bar, order, div):
        q.put(e)
    got = [q.get() for _ in range(4)]
    assert got[0] is div
    assert got[1] is bar
    assert got[2] is order
    assert got[3] is fill


def test_fifo_within_same_priority():
    """Two BarCloseEvents at the same timestamp should come out FIFO."""
    q = EventQueue()
    bar1 = BarCloseEvent(
        timestamp=T, symbol="AAA", open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0
    )
    bar2 = BarCloseEvent(
        timestamp=T, symbol="BBB", open=2.0, high=2.0, low=2.0, close=2.0, volume=1.0
    )
    q.put(bar1)
    q.put(bar2)
    assert q.get() is bar1
    assert q.get() is bar2


def test_peek_does_not_remove_event():
    q = EventQueue()
    bar = _bar()
    q.put(bar)
    peeked = q.peek()
    assert peeked is bar
    assert len(q) == 1  # still there


def test_peek_empty_returns_none():
    q = EventQueue()
    assert q.peek() is None


def test_earlier_timestamp_comes_first():
    q = EventQueue()
    late_div = DividendEvent(timestamp=T + pd.Timedelta(days=1), symbol="AAA", amount=1.0)
    early_fill = _fill()  # earlier timestamp, lower priority class
    q.put(late_div)
    q.put(early_fill)
    first = q.get()
    assert first is early_fill
