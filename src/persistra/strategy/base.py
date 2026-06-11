from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from .context import StrategyContext


class Strategy:
    """Unified strategy base.

    Subclass and override the hooks you need. A strategy is a plain object: it
    may hold arbitrary state (models, sub-signals, external data) as instance
    attributes. Declare the timeframes you need via ``timeframes`` (primary
    first); ``on_bar`` fires after each subscribed timeframe's bar closes.

    Multiple timeframes are supported (declare them in ``timeframes``); the
    ``target_weights`` emit path is the only emit path so far (signal/pipeline
    routing arrives in Phase 3).
    """

    timeframes: tuple[str, ...] = ("1d",)
    warmup: int = 1
    strategy_id: str = ""

    def universe_on(self, date: pd.Timestamp, pool: frozenset[str]) -> frozenset[str]:
        """Return the subset of pool this strategy trades on date. Default: full pool."""
        return pool

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "strategy_id" not in cls.__dict__ or cls.__dict__["strategy_id"] == "":
            cls.strategy_id = cls.__name__

    def on_start(self, ctx: StrategyContext) -> None:
        """Optional: called once before the first bar (init state / models)."""

    def on_bar(self, ctx: StrategyContext) -> None:
        """Main hook: called after each subscribed timeframe's bar closes."""

    def on_finish(self, ctx: StrategyContext) -> None:
        """Optional: called once after the final bar (teardown / reporting)."""
