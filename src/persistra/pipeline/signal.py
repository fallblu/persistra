from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class SignalCombiner(ABC):
    """Abstract base for multi-feature signal combination.

    Subclasses implement ``combine``, which takes a ``(n_symbols, n_features)``
    ``DataFrame`` and returns a ``Series`` of composite scores indexed by symbol.
    """

    @abstractmethod
    def combine(self, features: pd.DataFrame) -> pd.Series:
        """Combine feature columns into a single composite score per symbol.

        Implementations receive a ``(n_symbols, n_features)`` DataFrame and
        must return a ``pd.Series`` of composite scores indexed by symbol,
        where higher values indicate a more bullish view.

        Args:
            features: DataFrame with symbols as the index and feature names as
                columns.

        Returns:
            Series indexed by symbol containing composite scores.
        """
        ...


class LinearSignal(SignalCombiner):
    """Weighted linear combination of named feature columns.

    Args:
        weights: ``{feature_name: scalar_weight}`` mapping. Features absent from
            the input ``DataFrame`` are silently skipped.
    """

    def __init__(self, weights: dict[str, float]) -> None:
        self.weights = dict(weights)

    def combine(self, features: pd.DataFrame) -> pd.Series:
        """Compute a weighted sum of named feature columns.

        Iterates over ``self.weights`` and accumulates ``weight * column`` for
        each feature name present in the DataFrame.  Missing columns are
        silently skipped.

        Args:
            features: DataFrame with symbols as the index and feature names as
                columns.

        Returns:
            Series of composite scores indexed by symbol.  Starts at zero and
            accumulates contributions from matched feature columns.
        """
        score = pd.Series(0.0, index=features.index)
        for fname, w in self.weights.items():
            if fname in features.columns:
                score = score + w * features[fname].astype(float)
        return score
