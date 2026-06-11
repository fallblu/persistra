from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from persistra.core.history import HistoryView
    from persistra.core.state import PortfolioState


class Sizer(ABC):
    """Abstract base for position-sizing rules.

    Subclasses implement ``size``, which converts a ``{symbol: direction}``
    weight dict (sign = direction, magnitude may be ignored) into a final
    ``{symbol: weight}`` dict expressed as a fraction of portfolio equity.
    """

    @abstractmethod
    def size(
        self,
        weights: dict[str, float],
        portfolio: PortfolioState,
        history: HistoryView,
    ) -> dict[str, float]:
        """Convert directional weights to position sizes as equity fractions.

        Implementations receive a ``{symbol: direction}`` dict (sign indicates
        side; magnitude may be ignored) and must return a ``{symbol: weight}``
        dict where each weight is a signed fraction of current portfolio equity.

        Args:
            weights: Input direction map from the allocation rule.
            portfolio: Current portfolio snapshot (equity, cash, positions).
            history: Rolling bar history for volatility estimates etc.

        Returns:
            Dict of ``{symbol: target_weight}`` expressed as signed fractions
            of equity.
        """
        ...


class EqualWeight(Sizer):
    """Allocate equal capital to every active position.

    Args:
        target_gross: Total gross exposure to fill (default 1.0 = fully invested).
    """

    def __init__(self, target_gross: float = 1.0) -> None:
        self.target_gross = target_gross

    def size(
        self,
        weights: dict[str, float],
        portfolio: PortfolioState,
        history: HistoryView,
    ) -> dict[str, float]:
        """Assign equal fractional weight to every active (non-zero) position.

        Distributes ``target_gross`` evenly across all active symbols,
        preserving the sign of each input weight.

        Args:
            weights: Input direction map ``{symbol: signed_direction}``.
            portfolio: Current portfolio snapshot (unused by this sizer).
            history: Bar history (unused by this sizer).

        Returns:
            Dict of ``{symbol: ±(target_gross / n_active)}``.  Returns ``{}``
            when all weights are zero.
        """
        active = {s: w for s, w in weights.items() if w != 0.0}
        if not active:
            return {}
        per = self.target_gross / len(active)
        return {s: math.copysign(per, w) for s, w in active.items()}


class FixedDollar(Sizer):
    """Allocate a fixed notional dollar amount to each active position.

    Args:
        dollars_per_position: Dollar notional per position; converted to a
            fraction of current equity each bar.
    """

    def __init__(self, dollars_per_position: float) -> None:
        self.dollars_per_position = dollars_per_position

    def size(
        self,
        weights: dict[str, float],
        portfolio: PortfolioState,
        history: HistoryView,
    ) -> dict[str, float]:
        """Assign a fixed notional dollar amount to each active position.

        Converts ``dollars_per_position`` to a fraction of current equity and
        applies it with the sign from each input weight.

        Args:
            weights: Input direction map ``{symbol: signed_direction}``.
            portfolio: Current portfolio snapshot; ``equity`` is used to
                compute the fractional size.
            history: Bar history (unused by this sizer).

        Returns:
            Dict of ``{symbol: ±(dollars_per_position / equity)}``.
            Returns ``{}`` when all weights are zero or equity is non-positive.
        """
        active = {s: w for s, w in weights.items() if w != 0.0}
        if not active or portfolio.equity <= 0:
            return {}
        fraction = self.dollars_per_position / portfolio.equity
        return {s: math.copysign(fraction, w) for s, w in active.items()}


class VolTarget(Sizer):
    """Scale each position so its individual volatility contribution hits a target.

    Uses trailing close-price volatility (annualised) to size each leg so that
    the standalone vol of each position equals ``annual_vol / n_active``.

    Args:
        annual_vol: Desired portfolio annualized volatility target (default 0.10).
        lookback: Bars of history used to estimate realised vol (default 60).
    """

    def __init__(self, annual_vol: float = 0.10, lookback: int = 60) -> None:
        self.annual_vol = annual_vol
        self.lookback = lookback

    def size(
        self,
        weights: dict[str, float],
        portfolio: PortfolioState,
        history: HistoryView,
    ) -> dict[str, float]:
        """Scale each position so its individual realised vol equals the per-leg target.

        Estimates annualised vol for each active symbol from ``lookback`` bars
        of close prices (``pct_change().std() * sqrt(252)``).  The per-leg
        volatility target is ``annual_vol / n_active``.  Symbols with
        insufficient or zero vol are excluded.

        Args:
            weights: Input direction map ``{symbol: signed_direction}``.
            portfolio: Current portfolio snapshot (unused by this sizer).
            history: Bar history from which trailing closes are read.

        Returns:
            Dict of ``{symbol: ±(target_per_leg / annualised_vol)}``.
            Returns ``{}`` when no active symbols have estimable volatility.
        """
        active = {s: w for s, w in weights.items() if w != 0.0}
        if not active:
            return {}
        closes = history.closes(self.lookback)
        active_cols = [s for s in active if s in closes.columns]
        if not active_cols:
            return {}
        # One pct_change + std call across all active symbols; iloc[1:] drops the
        # leading all-NaN row that pct_change always produces.
        returns = closes[active_cols].pct_change().iloc[1:]
        daily_vols = returns.std()  # skipna=True by default; all-NaN col -> NaN
        viable: dict[str, float] = {
            str(s): float(v) * math.sqrt(252)
            for s, v in daily_vols.items()
            if v > 0 and np.isfinite(v)
        }
        if not viable:
            return {}
        n = len(viable)
        target_per = self.annual_vol / n
        return {s: math.copysign(target_per / v, active[s]) for s, v in viable.items()}
