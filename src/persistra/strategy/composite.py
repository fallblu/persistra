from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .base import Strategy

if TYPE_CHECKING:
    from .context import StrategyContext


class Allocator(ABC):
    """Interface for blending per-child weight maps into a single weight map.

    Implementors receive a ``{strategy_id: {symbol: weight}}`` mapping from
    ``CompositeStrategy`` and must return a single merged ``{symbol: weight}``
    dict representing the blended target weights.
    """

    @abstractmethod
    def allocate(self, per_strategy: dict[str, dict[str, float]]) -> dict[str, float]:
        """Blend per-child weight maps into a single target-weight mapping.

        Args:
            per_strategy: Mapping of ``strategy_id`` to the symbol-weight dict
                emitted by that child on the current bar.

        Returns:
            Merged ``{symbol: weight}`` dict representing the blended portfolio.
        """
        ...


class FixedWeightAllocator(Allocator):
    """Scale each child's weights by a fixed scalar and sum. Unknown strategy ids ignored."""

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = dict(weights)

    def allocate(self, per_strategy: dict[str, dict[str, float]]) -> dict[str, float]:
        """Scale each child's weights by its fixed scalar and sum across children.

        Unknown strategy ids (not present in ``self.weights``) are silently
        skipped. Symbols that appear in multiple children accumulate their
        scaled contributions.

        Args:
            per_strategy: Mapping of ``strategy_id`` to the symbol-weight dict
                emitted by that child on the current bar.

        Returns:
            Merged ``{symbol: weight}`` dict with each child's contribution
            scaled by the corresponding fixed weight.
        """
        combined: dict[str, float] = {}
        for sid, weight_map in per_strategy.items():
            scalar = self.weights.get(sid)
            if scalar is None:
                continue
            for sym, w in weight_map.items():
                combined[sym] = combined.get(sym, 0.0) + scalar * float(w)
        return combined


class CompositeStrategy(Strategy):
    """Run multiple child strategies and blend their emissions via an Allocator.

    ``warmup`` and ``timeframes`` are set as instance attributes from the children
    so the engine reads the correct values at construction time.
    """

    def __init__(self, strategies: list[Strategy], allocator: Allocator) -> None:
        if not strategies:
            raise ValueError("CompositeStrategy requires at least one child strategy")
        ids = [s.strategy_id for s in strategies]
        if len(set(ids)) != len(ids):
            raise ValueError("Child strategies must have unique strategy_id values")
        timeframes_set = {s.timeframes for s in strategies}
        if len(timeframes_set) > 1:
            raise ValueError(
                f"All child strategies must declare identical timeframes; got {timeframes_set}"
            )
        self._strategies = list(strategies)
        self._allocator = allocator
        self.timeframes = strategies[0].timeframes
        self.warmup = max(s.warmup for s in strategies)

    def on_start(self, ctx: StrategyContext) -> None:
        """Forward the start event to every child strategy in order.

        Args:
            ctx: The strategy context at the start of the backtest.
        """
        for child in self._strategies:
            child.on_start(ctx)
        super().on_start(ctx)

    def on_bar(self, ctx: StrategyContext) -> None:
        """Run each child strategy on a forked context, then blend their emissions.

        Each child receives its own forked context so that individual
        ``ctx.signal()`` calls do not propagate upstream.  The collected
        ``{strategy_id: weights}`` map is passed to the ``Allocator``, and
        the blended result is emitted on the parent context.  No signal is
        emitted when no child produces one this bar.

        Args:
            ctx: The strategy context for the current bar.
        """
        latest: dict[str, dict[str, float]] = {}
        for child in self._strategies:
            child_ctx = ctx._fork()
            child.on_bar(child_ctx)
            if child_ctx.emitted_weights is not None:
                latest[child.strategy_id] = child_ctx.emitted_weights
            for row in child_ctx.recorded:
                prefixed = f"{child.strategy_id}/{row['name']}"
                raw_symbol = row["symbol"]
                sym = str(raw_symbol) if raw_symbol is not None else None
                val = float(row["value"])  # type: ignore[arg-type]  # always numeric per record()
                if sym is None:
                    ctx.record(prefixed, val)
                else:
                    ctx.record(prefixed, {sym: val})
        if latest:
            ctx.signal(self._allocator.allocate(latest))

    def on_finish(self, ctx: StrategyContext) -> None:
        """Forward the finish event to every child strategy in order.

        Args:
            ctx: The strategy context at the end of the backtest.
        """
        for child in self._strategies:
            child.on_finish(ctx)
        super().on_finish(ctx)
