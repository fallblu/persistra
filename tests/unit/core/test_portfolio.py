import pandas as pd
import pytest

from persistra.core.events import (
    BarCloseEvent,
    DividendEvent,
    FillEvent,
    SplitEvent,
)
from persistra.core.portfolio import Portfolio, PortfolioConstraint, PortfolioPolicy

T = pd.Timestamp("2023-01-03")


def _bar(symbol, close):
    return BarCloseEvent(
        timestamp=T, symbol=symbol, open=close, high=close, low=close, close=close, volume=1.0
    )


def test_fill_updates_cash_and_position():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))
    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=5, fill_price=100.0, commission=1.0)
    )
    snap = p.snapshot()
    assert decision.accepted
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


def test_policy_rejects_insufficient_cash_without_mutating_ledgers():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=11, fill_price=100.0, commission=0.0)
    )

    assert not decision.accepted
    assert decision.constraint is PortfolioConstraint.INSUFFICIENT_CASH
    snap = p.snapshot()
    assert snap.cash == pytest.approx(1000.0)
    assert snap.positions == {}


def test_policy_rejects_short_when_shorts_disabled():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=-1, fill_price=100.0, commission=0.0)
    )

    assert not decision.accepted
    assert decision.constraint is PortfolioConstraint.SHORT_DISABLED
    assert p.snapshot().positions == {}


def test_policy_allows_selling_down_existing_long_position():
    p = Portfolio(1000.0)
    p.on_bar_close(_bar("AAA", 100.0))
    p.on_fill(FillEvent(timestamp=T, symbol="AAA", quantity=5, fill_price=100.0, commission=0.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=-2, fill_price=100.0, commission=0.0)
    )

    assert decision.accepted
    snap = p.snapshot()
    assert snap.positions["AAA"] == pytest.approx(3)
    assert snap.cash == pytest.approx(700.0)


def test_policy_rejects_max_gross_exposure_breach():
    p = Portfolio(1000.0, policy=PortfolioPolicy(max_gross_exposure=0.5))
    p.on_bar_close(_bar("AAA", 100.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=6, fill_price=100.0, commission=0.0)
    )

    assert not decision.accepted
    assert decision.constraint is PortfolioConstraint.MAX_GROSS_EXPOSURE
    assert p.snapshot().positions == {}


def test_policy_rejects_max_net_exposure_breach():
    p = Portfolio(1000.0, policy=PortfolioPolicy(max_net_exposure=0.4))
    p.on_bar_close(_bar("AAA", 100.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=5, fill_price=100.0, commission=0.0)
    )

    assert not decision.accepted
    assert decision.constraint is PortfolioConstraint.MAX_NET_EXPOSURE
    assert p.snapshot().positions == {}


def test_policy_rejects_negative_max_net_exposure_breach_when_shorts_enabled():
    p = Portfolio(
        1000.0,
        policy=PortfolioPolicy(
            allow_short=True,
            max_gross_exposure=2.0,
            max_net_exposure=0.4,
        ),
    )
    p.on_bar_close(_bar("AAA", 100.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=-5, fill_price=100.0, commission=0.0)
    )

    assert not decision.accepted
    assert decision.constraint is PortfolioConstraint.MAX_NET_EXPOSURE
    assert p.snapshot().positions == {}


def test_policy_rejects_min_cash_breach():
    p = Portfolio(1000.0, policy=PortfolioPolicy(min_cash=0.2))
    p.on_bar_close(_bar("AAA", 100.0))

    decision = p.on_fill(
        FillEvent(timestamp=T, symbol="AAA", quantity=9, fill_price=100.0, commission=0.0)
    )

    assert not decision.accepted
    assert decision.constraint is PortfolioConstraint.INSUFFICIENT_CASH
    assert p.snapshot().cash == pytest.approx(1000.0)
