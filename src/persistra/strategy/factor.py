from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from persistra.pipeline.allocation import AllocationRule
    from persistra.pipeline.risk import RiskConstraint
    from persistra.pipeline.signal import SignalCombiner
    from persistra.pipeline.sizing import Sizer

    from .context import StrategyContext

from .base import Strategy


class FactorStrategy(Strategy):
    """Convenience strategy: override ``compute_features`` only.

    ``on_bar`` calls ``compute_features``, combines features into scores via the
    ``SignalCombiner``, then emits via ``ctx.signal()``. Return an empty
    DataFrame from ``compute_features`` to skip emission this bar.
    """

    def __init__(
        self,
        signal_combiner: SignalCombiner,
        allocation: AllocationRule | None = None,
        sizer: Sizer | None = None,
        risk: RiskConstraint | None = None,
    ) -> None:
        self._signal_combiner = signal_combiner
        self._allocation = allocation
        self._sizer = sizer
        self._risk = risk

    def compute_features(self, ctx: StrategyContext) -> pd.DataFrame:
        """Override: return DataFrame with index=symbols, columns=feature names."""
        raise NotImplementedError

    def on_bar(self, ctx: StrategyContext) -> None:
        """Compute features, combine into scores, and emit a signal each bar.

        Calls :meth:`compute_features`; if the result is an empty DataFrame,
        no signal is emitted this bar.  Otherwise combines features into
        cross-sectional scores via ``self._signal_combiner`` and calls
        ``ctx.signal()`` with the optional allocation, sizer, and risk objects.

        Args:
            ctx: The strategy context for the current bar.
        """
        features = self.compute_features(ctx)
        if features.empty:
            return
        scores = self._signal_combiner.combine(features)
        ctx.signal(
            scores,
            allocation=self._allocation,
            sizer=self._sizer,
            risk=self._risk,
        )
