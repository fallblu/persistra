from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from persistra.strategy.base import Strategy

if TYPE_CHECKING:
    from persistra.pipeline.allocation import AllocationRule
    from persistra.strategy.context import StrategyContext


class SMACrossover(Strategy):
    """Long names whose fast SMA is above their slow SMA; flat otherwise.

    Each bar, computes per-symbol fast and slow simple moving averages from
    trailing closes and goes (equal-weight) long the names with a positive
    fast-minus-slow spread. Records ``sma_fast``, ``sma_slow``, and ``spread``
    per symbol.

    Args:
        fast: Fast SMA window in bars (must be < ``slow``).
        slow: Slow SMA window in bars; also the warmup.
        allocation: Optional ``AllocationRule`` applied to the unit long scores
            (default: equal weight across the longs).
    """

    timeframes = ("1d",)

    def __init__(
        self,
        fast: int = 20,
        slow: int = 50,
        allocation: AllocationRule | None = None,
    ) -> None:
        if fast >= slow:
            raise ValueError("fast must be < slow")
        self.fast = fast
        self.slow = slow
        self.allocation = allocation
        self.warmup = slow

    def on_bar(self, ctx: StrategyContext) -> None:
        """Go equal-weight long symbols whose fast SMA exceeds their slow SMA.

        Fetches ``slow`` bars of closes, computes per-symbol ``fast``-bar and
        ``slow``-bar simple moving averages, and records ``sma_fast``,
        ``sma_slow``, and ``spread`` (fast minus slow) per symbol. Names with a
        positive spread are longs; if no names qualify the book is flattened via
        an empty signal. Otherwise assigns unit scores to longs and emits either
        via ``self.allocation`` (if set) or plain equal weights.

        Args:
            ctx: Point-in-time context providing history and signal emission.
        """
        closes = ctx.history().closes(self.slow)
        if len(closes.index) < self.slow or not len(closes.columns):
            return
        fast = closes.tail(self.fast).mean()
        slow = closes.mean()
        spread = fast - slow
        ctx.record("sma_fast", fast)
        ctx.record("sma_slow", slow)
        ctx.record("spread", spread)

        longs = [str(s) for s in closes.columns if float(spread.get(s, 0.0)) > 0.0]
        if not longs:
            ctx.signal({})  # flatten the book when no name is in an uptrend
            return
        scores = pd.Series(1.0, index=longs)
        if self.allocation is not None:
            ctx.signal(scores, allocation=self.allocation)
        else:
            w = 1.0 / len(longs)
            ctx.signal({s: w for s in longs})
