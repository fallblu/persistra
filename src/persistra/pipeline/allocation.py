from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


class AllocationRule(ABC):
    """Abstract base for signal-to-weight allocation rules.

    Subclasses implement ``allocate``, which maps a ``pd.Series`` of raw
    scores (higher = more bullish) to a ``{symbol: weight}`` dict that
    represents target portfolio weights.
    """

    @abstractmethod
    def allocate(self, scores: pd.Series) -> dict[str, float]:
        """Convert raw scores to a target-weight dict.

        Implementations must map a ``pd.Series`` of cross-sectional scores
        (higher = more bullish) to a ``{symbol: weight}`` dict where weights
        represent target portfolio fractions (positive = long, negative = short).

        Args:
            scores: Cross-sectional signal scores indexed by symbol.

        Returns:
            Dict mapping symbol strings to target portfolio weights.
        """
        ...


class TopN(AllocationRule):
    """Equal-weight top-N (and bottom-N) allocation.

    Args:
        n: Number of longs (and shorts when ``long_short=True``).
        long_short: If ``True``, short the bottom-N with equal magnitude.
    """

    def __init__(self, n: int, long_short: bool = True) -> None:
        if n < 1:
            raise ValueError("n must be >= 1")
        self.n = n
        self.long_short = long_short

    def allocate(self, scores: pd.Series) -> dict[str, float]:
        """Allocate equal weight to the top-N longs and (optionally) bottom-N shorts.

        Selects the ``n`` highest-scored symbols as longs; when
        ``long_short=True``, also selects the ``n`` lowest-scored as shorts
        with the same magnitude.  Each leg is weighted at
        ``1 / (n × (1 + long_short))``.

        Args:
            scores: Cross-sectional signal scores indexed by symbol.

        Returns:
            Dict of ``{symbol: weight}`` with equal weights summing to 1.0
            gross in all modes (long/short is dollar-neutral: net 0). Returns
            ``{}`` when the universe is too small.
        """
        if len(scores) == 0:
            return {}
        if self.long_short and len(scores) < 2:
            return {}
        n = min(self.n, len(scores) // (2 if self.long_short else 1))
        if n == 0:
            return {}
        ranked = scores.sort_values(ascending=False)
        n_active = n * (2 if self.long_short else 1)
        weight_per = 1.0 / n_active
        weights: dict[str, float] = {}
        long_syms: set = set()
        for sym in ranked.head(n).index:
            weights[str(sym)] = weight_per
            long_syms.add(sym)
        if self.long_short:
            for sym in ranked.tail(n).index:
                if sym not in long_syms:
                    weights[str(sym)] = -weight_per
        return weights


class Decile(AllocationRule):
    """Equal-weight top/bottom fraction of the universe.

    Args:
        fraction: Tail fraction selected for long (and short) legs (default 0.10).
        long_short: If ``True``, short the bottom fraction with equal magnitude.
    """

    def __init__(self, fraction: float = 0.10, long_short: bool = True) -> None:
        if not 0.0 < fraction <= 0.5:
            raise ValueError("fraction must be in (0, 0.5]")
        self.fraction = fraction
        self.long_short = long_short

    def allocate(self, scores: pd.Series) -> dict[str, float]:
        """Allocate equal weight to the top and bottom ``fraction`` of the universe.

        Computes ``n = ceil(len(scores) * fraction)`` then delegates to
        :class:`TopN` with that ``n``.

        Args:
            scores: Cross-sectional signal scores indexed by symbol.

        Returns:
            Dict of ``{symbol: weight}`` — equal weights across the selected
            longs/shorts.  Returns ``{}`` for an empty universe.
        """
        if len(scores) == 0:
            return {}
        n = max(1, math.ceil(len(scores) * self.fraction))
        return TopN(n=n, long_short=self.long_short).allocate(scores)


class RankWeighted(AllocationRule):
    """Rank-demeaned weights proportional to cross-sectional rank.

    Ranks scores, demeans the ranks, then normalises so the sum of absolute
    weights equals 1.0.  Produces a dollar-neutral long/short book.
    """

    def allocate(self, scores: pd.Series) -> dict[str, float]:
        """Allocate weights proportional to demeaned cross-sectional ranks.

        Ranks scores, subtracts the mean rank, then normalises so that the
        sum of absolute weights equals 1.0, producing a dollar-neutral
        long/short book.

        Args:
            scores: Cross-sectional signal scores indexed by symbol.

        Returns:
            Dict of ``{symbol: weight}`` with sum of absolute values = 1.0.
            Returns ``{}`` for an empty universe or when all ranks are tied.
        """
        if len(scores) == 0:
            return {}
        ranks = scores.rank()
        demeaned = ranks - ranks.mean()
        total = float(demeaned.abs().sum())
        if total == 0.0:
            return {}
        normalised = demeaned / total
        return {str(sym): float(w) for sym, w in normalised.items()}


class Direct(AllocationRule):
    """Pass-through allocation: scores are used as target weights unchanged."""

    def allocate(self, scores: pd.Series) -> dict[str, float]:
        """Pass scores through as target weights unchanged.

        Args:
            scores: Cross-sectional signal scores indexed by symbol.

        Returns:
            Dict of ``{symbol: score}`` with no normalisation applied.
        """
        return {str(sym): float(w) for sym, w in scores.items()}
