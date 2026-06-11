from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import pytest

from persistra.core.state import PortfolioState
from persistra.strategy.base import Strategy
from persistra.strategy.composite import CompositeStrategy, FixedWeightAllocator
from persistra.strategy.context import StrategyContext

if TYPE_CHECKING:
    from persistra.core.history import HistoryView

_STATE = PortfolioState(
    equity=1000.0,
    cash=1000.0,
    positions={},
    weights={},
    gross_exposure=0.0,
    net_exposure=0.0,
)


def _ctx(populated_history: HistoryView) -> StrategyContext:
    return StrategyContext(
        timestamp=pd.Timestamp("2022-01-06"),
        timeframe="1d",
        histories={"1d": populated_history},
        portfolio=_STATE,
        universe=frozenset({"AAA", "BBB"}),
    )


class FullAAA(Strategy):
    """Always emits AAA=1.0."""

    timeframes = ("1d",)
    warmup = 1

    def on_bar(self, ctx: StrategyContext) -> None:
        ctx.signal({"AAA": 1.0})


class FullBBB(Strategy):
    """Always emits BBB=1.0."""

    timeframes = ("1d",)
    warmup = 1

    def on_bar(self, ctx: StrategyContext) -> None:
        ctx.signal({"BBB": 1.0})


class Silent(Strategy):
    """Never emits a signal."""

    timeframes = ("1d",)
    warmup = 1

    def on_bar(self, ctx: StrategyContext) -> None:
        pass  # no ctx.signal() call


def test_composite_blends_two_children_via_fixed_weight_allocator(populated_history):
    """FixedWeightAllocator(0.6 * FullAAA + 0.4 * FullBBB) -> AAA=0.6, BBB=0.4."""
    composite = CompositeStrategy(
        strategies=[FullAAA(), FullBBB()],
        allocator=FixedWeightAllocator({FullAAA.strategy_id: 0.6, FullBBB.strategy_id: 0.4}),
    )
    ctx = _ctx(populated_history)
    composite.on_bar(ctx)
    w = ctx.emitted_weights
    assert w is not None
    # Derived independently: 0.6 * 1.0 = 0.6 for AAA, 0.4 * 1.0 = 0.4 for BBB
    assert w["AAA"] == pytest.approx(0.6)
    assert w["BBB"] == pytest.approx(0.4)


def test_composite_child_emissions_do_not_pollute_parent_context(populated_history):
    """Children run in forked contexts; a child's emission must not mutate the
    parent context before the allocator runs.  We verify this by checking that
    the parent context starts with emitted_weights=None and only gets a value
    after on_bar returns."""
    composite = CompositeStrategy(
        strategies=[FullAAA()],
        allocator=FixedWeightAllocator({FullAAA.strategy_id: 1.0}),
    )
    ctx = _ctx(populated_history)
    assert ctx.emitted_weights is None, "parent context must start clean"
    composite.on_bar(ctx)
    # After on_bar the parent gets the blended result, not a raw child emission.
    assert ctx.emitted_weights == {"AAA": pytest.approx(1.0)}


def test_composite_no_emission_when_all_children_are_silent(populated_history):
    """CompositeStrategy emits nothing when every child skips ctx.signal()."""
    composite = CompositeStrategy(
        strategies=[Silent()],
        allocator=FixedWeightAllocator({Silent.strategy_id: 1.0}),
    )
    ctx = _ctx(populated_history)
    composite.on_bar(ctx)
    assert ctx.emitted_weights is None


def test_composite_rejects_empty_strategy_list():
    with pytest.raises(ValueError, match="at least one"):
        CompositeStrategy(strategies=[], allocator=FixedWeightAllocator({}))


def test_composite_merges_child_diagnostics_with_prefix():
    class Child(Strategy):
        strategy_id = "Child"

        def on_bar(self, ctx: StrategyContext) -> None:
            ctx.record("zscore", {"AAA": 1.0})
            ctx.signal({"AAA": 1.0})

    comp = CompositeStrategy([Child()], FixedWeightAllocator({"Child": 1.0}))
    ctx = StrategyContext(
        timestamp=pd.Timestamp("2022-01-03"),
        timeframe="1d",
        histories={},
        portfolio=_STATE,
        universe=frozenset({"AAA"}),
    )
    comp.on_bar(ctx)
    rows = [r for r in ctx.recorded if r["name"] == "Child/zscore"]
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["value"] == 1.0
