import pandas as pd
import pytest

from persistra.core.events import (
    BarCloseEvent,
    DividendEvent,
    FillEvent,
    SplitEvent,
)
from persistra.core.portfolio import Portfolio

T = pd.Timestamp("2023-01-03")


def _bar(symbol, close):
    return BarCloseEvent(
        timestamp=T, symbol=symbol, open=close, high=close, low=close, close=close, volume=1.0
    )


def test_fill_updates_cash_and_position():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))
    p.on_fill(FillEvent(timestamp=T, symbol="AAA", quantity=5, fill_price=100.0, commission=1.0))
    snap = p.snapshot()
    assert snap.positions["AAA"] == 5
    assert snap.cash == pytest.approx(1000.0 - 5 * 100.0 - 1.0)
    # equity == cash + mark-to-market
    assert snap.equity == pytest.approx(snap.cash + 5 * 100.0)


def test_conservation_identity_cash_plus_mtm_equals_equity():
    p = Portfolio(1000.0)
    for sym, px in (("AAA", 100.0), ("BBB", 50.0)):
        p.on_bar_close(_bar(sym, px))
        p.on_fill(FillEvent(timestamp=T, symbol=sym, quantity=3, fill_price=px, commission=0.0))
    snap = p.snapshot()
    mtm = sum(snap.positions[s] * px for s, px in (("AAA", 100.0), ("BBB", 50.0)))
    assert snap.cash + mtm == pytest.approx(snap.equity)


def test_split_doubles_position_no_cash_change():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))
    p.on_fill(FillEvent(timestamp=T, symbol="AAA", quantity=4, fill_price=100.0, commission=0.0))
    cash_before = p.snapshot().cash
    p.on_split(SplitEvent(timestamp=T, symbol="AAA", ratio=2.0))
    snap = p.snapshot()
    assert snap.positions["AAA"] == 8
    assert snap.cash == pytest.approx(cash_before)


def test_dividend_credits_cash_by_shares_times_amount():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))
    p.on_fill(FillEvent(timestamp=T, symbol="AAA", quantity=10, fill_price=100.0, commission=0.0))
    cash_before = p.snapshot().cash
    p.on_dividend(DividendEvent(timestamp=T, symbol="AAA", amount=0.25))
    assert p.snapshot().cash == pytest.approx(cash_before + 10 * 0.25)


def test_target_orders_liquidates_symbol_absent_from_targets():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))
    p.on_fill(FillEvent(timestamp=T, symbol="AAA", quantity=5, fill_price=100.0, commission=0.0))
    # New target omits AAA -> should produce a liquidating order for AAA.
    orders = p.target_orders({}, T, p.snapshot().equity)
    assert len(orders) == 1
    assert orders[0].symbol == "AAA"
    assert orders[0].quantity == pytest.approx(-5)


def test_target_orders_skips_symbol_with_no_price():
    p = Portfolio(1000.0)
    orders = p.target_orders({"ZZZ": 0.5}, T, 1000.0)
    assert orders == []
