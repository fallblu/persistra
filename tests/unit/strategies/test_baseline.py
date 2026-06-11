from __future__ import annotations

from persistra import Engine, Portfolio
from persistra.strategies.baseline import BuyAndHold, EqualWeightRebalance


def _run(store, strategy):
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()


def test_buy_and_hold_trades_once(tiny_store):
    result = _run(tiny_store, BuyAndHold())
    # 3 symbols entered on the first eligible bar, never re-traded.
    assert len(result.trades) == 3
    assert result.trades["timestamp"].nunique() == 1


def test_buy_and_hold_defers_when_universe_empty():
    # An empty universe on the first bar must NOT permanently mark the strategy
    # as emitted; it should still enter once the universe is non-empty.
    class _EmptyCtx:
        universe: frozenset[str] = frozenset()

        def signal(self, weights: object) -> None:
            raise AssertionError("should not signal on an empty universe")

    strat = BuyAndHold()
    strat.on_bar(_EmptyCtx())  # type: ignore[arg-type]
    assert strat._emitted is False


def test_buy_and_hold_explicit_weights(tiny_store):
    result = _run(tiny_store, BuyAndHold(weights={"AAA": 1.0}))
    assert set(result.trades["symbol"]) == {"AAA"}


def test_equal_weight_rebalance_every_2_trades_on_alternating_bars(tiny_store):
    result = _run(tiny_store, EqualWeightRebalance(every=2))
    n_bars = result.equity_curve.shape[0]
    rebalanced_bars = result.trades["timestamp"].nunique()
    assert rebalanced_bars <= (n_bars // 2) + 1


def test_equal_weight_rebalance_rejects_bad_cadence():
    import pytest

    with pytest.raises(ValueError):
        EqualWeightRebalance(every=0)
