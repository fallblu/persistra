from __future__ import annotations

from typing import TYPE_CHECKING

from persistra.strategy.base import Strategy

if TYPE_CHECKING:
    from persistra.strategy.context import StrategyContext


class BuyAndHold(Strategy):
    """Allocate once at warmup, then never re-trade.

    Args:
        weights: Optional fixed ``{symbol: weight}`` target. When ``None``, the
            initial universe is equal-weighted. After the first emission the
            strategy stays silent (holds), so the book drifts with the market.
    """

    timeframes = ("1d",)
    warmup = 1

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = dict(weights) if weights is not None else None
        self._emitted = False

    def on_bar(self, ctx: StrategyContext) -> None:
        """Emit target weights on the first bar only, then stay silent.

        On the first call, signals either the user-supplied ``weights`` dict or
        an equal-weight allocation across ``ctx.universe``. All subsequent bars
        are no-ops, allowing the book to drift with the market.

        Args:
            ctx: Point-in-time context; ``ctx.universe`` is used when no
                explicit weights were provided.
        """
        if self._emitted:
            return
        if self._weights is not None:
            ctx.signal(self._weights)
        else:
            n = len(ctx.universe)
            if not n:
                return
            ctx.signal({sym: 1.0 / n for sym in ctx.universe})
        self._emitted = True


class EqualWeightRebalance(Strategy):
    """Rebalance the whole universe to equal weight every ``every`` bars.

    Args:
        every: Rebalance cadence in bars (``1`` = rebalance every bar).
    """

    timeframes = ("1d",)
    warmup = 1

    def __init__(self, every: int = 1) -> None:
        if every < 1:
            raise ValueError("every must be >= 1")
        self.every = every
        self._i = 0

    def on_bar(self, ctx: StrategyContext) -> None:
        """Emit equal target weights across the current universe every ``every`` bars.

        Rebalances on bar indices that are multiples of ``every`` (0-indexed),
        producing a ``1/n`` weight for each symbol in ``ctx.universe``. Bars
        that do not fall on a rebalance cadence emit no signal.

        Args:
            ctx: Point-in-time context; ``ctx.universe`` gives the tradable set
                and ``ctx.signal(...)`` records the target weights.
        """
        do_rebalance = self._i % self.every == 0
        self._i += 1
        if not do_rebalance:
            return
        n = len(ctx.universe)
        if n:
            ctx.signal({sym: 1.0 / n for sym in ctx.universe})
