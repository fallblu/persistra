from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from persistra.features import CumReturn
from persistra.pipeline import Decile, RankWeighted
from persistra.strategy.base import Strategy

if TYPE_CHECKING:
    from persistra.pipeline.allocation import AllocationRule
    from persistra.strategy.context import StrategyContext


class CrossSectionalMomentum(Strategy):
    """Rank names by trailing cumulative log-return and allocate cross-sectionally.

    Computes per-symbol momentum as the summed log-return over ``lookback`` bars,
    skipping the most recent ``skip`` bars (e.g. ``skip=21`` for 12-1 momentum),
    then maps scores to weights via ``allocation``. Records ``momentum``.

    Args:
        lookback: Total trailing window in bars used for the score.
        skip: Most-recent bars to exclude (reversal control).
        allocation: ``AllocationRule`` mapping scores to weights
            (default ``Decile(0.1)``).
    """

    timeframes = ("1d",)

    def __init__(
        self,
        lookback: int = 252,
        skip: int = 21,
        allocation: AllocationRule | None = None,
    ) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        if skip < 0:
            raise ValueError("skip must be >= 0")
        self.lookback = lookback
        self.skip = skip
        self.allocation = allocation if allocation is not None else Decile(0.1)
        self.warmup = lookback + skip

    def on_bar(self, ctx: StrategyContext) -> None:
        """Score symbols by trailing cumulative log-return and allocate cross-sectionally.

        Fetches ``lookback + skip`` bars of close prices, computes the
        ``CumReturn`` score (summed log-return over ``lookback`` bars, skipping
        the most recent ``skip`` bars), drops NaN-scored names, records
        ``momentum`` per symbol, then signals weights via ``self.allocation``.
        Returns early if insufficient history or no columns are available.

        Args:
            ctx: Point-in-time context providing history and signal emission.
        """
        closes = ctx.history().closes(self.lookback + self.skip)
        if len(closes.index) < self.lookback or not len(closes.columns):
            return
        scores_arr = CumReturn(skip_last=self.skip, input_is_price=True).transform(
            closes.to_numpy()
        )
        scores = pd.Series(np.asarray(scores_arr).ravel(), index=closes.columns)
        scores = scores.dropna()
        if scores.empty:
            return
        ctx.record("momentum", scores)
        ctx.signal(scores, allocation=self.allocation)


class MeanReversion(Strategy):
    """Short recent winners, long recent losers (cross-sectional reversal).

    Scores each name by the negative z-score of its trailing ``lookback``-bar
    return (so recent losers score high), then allocates via ``allocation``.
    Records ``zscore`` (the raw, pre-negation z-score).

    Args:
        lookback: Trailing window in bars for the return and its z-score.
        allocation: ``AllocationRule`` mapping scores to weights
            (default ``RankWeighted()``).
    """

    timeframes = ("1d",)

    def __init__(self, lookback: int = 5, allocation: AllocationRule | None = None) -> None:
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        self.lookback = lookback
        self.allocation = allocation if allocation is not None else RankWeighted()
        self.warmup = lookback + 1

    def on_bar(self, ctx: StrategyContext) -> None:
        """Score symbols by the negative z-score of their trailing return and allocate.

        Fetches ``lookback + 1`` bars of closes, computes each symbol's simple
        return over the window, cross-sectionally z-scores those returns, then
        signals the negative z-score (so recent losers rank highest) via
        ``self.allocation``. Records the raw (pre-negation) ``zscore`` per
        symbol. Returns early if fewer than ``lookback + 1`` bars are available,
        fewer than two symbols are present, or the cross-sectional std is zero.

        Args:
            ctx: Point-in-time context providing history and signal emission.
        """
        closes = ctx.history().closes(self.lookback + 1)
        if len(closes.index) < self.lookback + 1 or len(closes.columns) < 2:
            return
        window_ret = closes.iloc[-1] / closes.iloc[-(self.lookback + 1)] - 1.0
        window_ret = window_ret.dropna()
        if window_ret.empty or float(window_ret.std()) == 0.0:
            return
        zscore = (window_ret - window_ret.mean()) / window_ret.std()
        ctx.record("zscore", zscore)
        ctx.signal(-zscore, allocation=self.allocation)
