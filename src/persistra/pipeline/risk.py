from __future__ import annotations

import math
from abc import ABC, abstractmethod


class RiskConstraint(ABC):
    """Abstract base for portfolio risk constraints.

    Subclasses implement ``project``, which rescales or clips a
    ``{symbol: weight}`` dict so that it satisfies the constraint.
    """

    @abstractmethod
    def project(self, weights: dict[str, float]) -> dict[str, float]:
        """Enforce this risk constraint on a target-weight dict.

        Implementations must rescale or clip the input ``{symbol: weight}``
        dict so that the result satisfies the constraint, then return the
        adjusted dict.  The input must not be mutated.

        Args:
            weights: Proposed target portfolio weights (signed equity fractions).

        Returns:
            Adjusted ``{symbol: weight}`` dict satisfying the constraint.
        """
        ...


class CashFloor(RiskConstraint):
    """Rescale positions so that at least ``min_cash`` of capital stays in cash.

    Args:
        min_cash: Minimum uninvested fraction in [0, 1) (default 0.05).
    """

    def __init__(self, min_cash: float = 0.05) -> None:
        if not 0.0 <= min_cash < 1.0:
            raise ValueError(f"min_cash must be in [0, 1), got {min_cash}")
        self.min_cash = float(min_cash)

    def project(self, weights: dict[str, float]) -> dict[str, float]:
        """Rescale weights so that gross exposure does not exceed ``1 - min_cash``.

        If the sum of absolute weights is already within the limit, the dict
        is returned unchanged.  Otherwise all weights are scaled uniformly.

        Args:
            weights: Proposed target portfolio weights.

        Returns:
            Adjusted weights satisfying ``sum(|w|) <= 1 - min_cash``.
        """
        max_gross = 1.0 - self.min_cash
        gross = sum(abs(w) for w in weights.values())
        if gross <= max_gross or gross == 0:
            return dict(weights)
        scale = max_gross / gross
        return {k: v * scale for k, v in weights.items()}


class MaxGrossExposure(RiskConstraint):
    """Cap total gross exposure (sum of absolute weights).

    Args:
        limit: Maximum allowed gross exposure (e.g. ``1.5`` for 150 %).
    """

    def __init__(self, limit: float) -> None:
        self.limit = float(limit)

    def project(self, weights: dict[str, float]) -> dict[str, float]:
        """Rescale weights so that total gross exposure does not exceed ``limit``.

        If ``sum(|w|) <= limit``, the dict is returned unchanged.  Otherwise
        all weights are scaled uniformly to bring gross down to ``limit``.

        Args:
            weights: Proposed target portfolio weights.

        Returns:
            Adjusted weights satisfying ``sum(|w|) <= limit``.
        """
        gross = sum(abs(w) for w in weights.values())
        if gross <= self.limit or gross == 0:
            return dict(weights)
        scale = self.limit / gross
        return {k: v * scale for k, v in weights.items()}


class MaxNetExposure(RiskConstraint):
    """Clamp net exposure (sum of signed weights) to a ``[low, high]`` band.

    Args:
        low: Minimum net exposure allowed (e.g. ``-0.2`` for −20 %).
        high: Maximum net exposure allowed (e.g. ``0.2`` for +20 %).
    """

    def __init__(self, low: float, high: float) -> None:
        if low > high:
            raise ValueError(f"low ({low}) must be <= high ({high})")
        self.low = float(low)
        self.high = float(high)

    def project(self, weights: dict[str, float]) -> dict[str, float]:
        """Scale weights to clamp net exposure into ``[low, high]``.

        If ``sum(w)`` is already within ``[low, high]``, the dict is returned
        unchanged.  Otherwise all weights are scaled uniformly so that net
        exposure equals the nearer band boundary.

        Args:
            weights: Proposed target portfolio weights.

        Returns:
            Adjusted weights satisfying ``low <= sum(w) <= high``.
        """
        net = sum(weights.values())
        if self.low <= net <= self.high or net == 0:
            return dict(weights)
        target = self.high if net > self.high else self.low
        scale = target / net
        return {k: v * scale for k, v in weights.items()}


class MaxPositionSize(RiskConstraint):
    """Clip each individual weight to ``[-limit, +limit]``.

    Args:
        limit: Maximum absolute weight per position (e.g. ``0.05`` for 5 %).
    """

    def __init__(self, limit: float) -> None:
        self.limit = float(limit)

    def project(self, weights: dict[str, float]) -> dict[str, float]:
        """Clip each individual weight to ``[-limit, +limit]``.

        Weights within the limit are unchanged; larger weights are capped at
        ``±limit`` while preserving sign.

        Args:
            weights: Proposed target portfolio weights.

        Returns:
            Adjusted weights with each entry satisfying ``|w| <= limit``.
        """
        return {k: math.copysign(min(abs(v), self.limit), v) for k, v in weights.items()}
