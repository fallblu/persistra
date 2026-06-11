from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


def _as_frame(X: Any) -> pd.DataFrame:
    if isinstance(X, pd.DataFrame):
        return X
    arr = np.asarray(X)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return pd.DataFrame(arr)


class RollingZScore(BaseEstimator, TransformerMixin):
    """Rolling z-score normalisation (sklearn transformer).

    Subtracts the rolling mean and divides by the rolling standard deviation.

    Args:
        window: Look-back window in bars.
        min_periods: Minimum observations required; defaults to ``window``.
    """

    def __init__(self, window: int = 63, min_periods: int | None = None) -> None:
        self.window = window
        self.min_periods = min_periods

    def fit(self, X: Any, y: Any = None) -> RollingZScore:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Apply rolling z-score normalisation to each column.

        Args:
            X: Input array or DataFrame of shape ``(T, n_features)``.

        Returns:
            Array of shape ``(T, n_features)`` with ``(x - rolling_mean)
            / rolling_std``; ``nan`` where the window is not yet filled or
            std is zero.
        """
        df = _as_frame(X)
        min_p = self.min_periods or self.window
        mean = df.rolling(self.window, min_periods=min_p).mean()
        std = df.rolling(self.window, min_periods=min_p).std()
        return ((df - mean) / std.replace(0.0, np.nan)).to_numpy()


class RollingMean(BaseEstimator, TransformerMixin):
    """Rolling arithmetic mean (sklearn transformer).

    Args:
        window: Look-back window in bars.
    """

    def __init__(self, window: int = 63) -> None:
        self.window = window

    def fit(self, X: Any, y: Any = None) -> RollingMean:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the rolling arithmetic mean of each column.

        Args:
            X: Input array or DataFrame of shape ``(T, n_features)``.

        Returns:
            Array of shape ``(T, n_features)`` with ``nan`` for rows where
            the window is not yet filled.
        """
        return _as_frame(X).rolling(self.window).mean().to_numpy()


class RollingStd(BaseEstimator, TransformerMixin):
    """Rolling standard deviation (sklearn transformer).

    Args:
        window: Look-back window in bars.
    """

    def __init__(self, window: int = 63) -> None:
        self.window = window

    def fit(self, X: Any, y: Any = None) -> RollingStd:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the rolling sample standard deviation (ddof=1) of each column.

        Args:
            X: Input array or DataFrame of shape ``(T, n_features)``.

        Returns:
            Array of shape ``(T, n_features)`` with ``nan`` for rows where
            the window is not yet filled.
        """
        return _as_frame(X).rolling(self.window).std().to_numpy()


class RollingQuantile(BaseEstimator, TransformerMixin):
    """Rolling sample quantile (sklearn transformer).

    Args:
        window: Look-back window in bars.
        q: Quantile to compute, in [0, 1] (default 0.5 = median).
    """

    def __init__(self, window: int = 63, q: float = 0.5) -> None:
        self.window = window
        self.q = q

    def fit(self, X: Any, y: Any = None) -> RollingQuantile:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the rolling sample quantile ``q`` of each column.

        Args:
            X: Input array or DataFrame of shape ``(T, n_features)``.

        Returns:
            Array of shape ``(T, n_features)`` with ``nan`` for rows where
            the window is not yet filled.
        """
        return _as_frame(X).rolling(self.window).quantile(self.q).to_numpy()


class RollingSkew(BaseEstimator, TransformerMixin):
    """Rolling sample skewness (sklearn transformer).

    Args:
        window: Look-back window in bars.
    """

    def __init__(self, window: int = 63) -> None:
        self.window = window

    def fit(self, X: Any, y: Any = None) -> RollingSkew:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the rolling sample skewness of each column.

        Args:
            X: Input array or DataFrame of shape ``(T, n_features)``.

        Returns:
            Array of shape ``(T, n_features)`` with ``nan`` for rows where
            the window is not yet filled.
        """
        return _as_frame(X).rolling(self.window).skew().to_numpy()


class RollingKurt(BaseEstimator, TransformerMixin):
    """Rolling sample excess kurtosis (sklearn transformer).

    Args:
        window: Look-back window in bars.
    """

    def __init__(self, window: int = 63) -> None:
        self.window = window

    def fit(self, X: Any, y: Any = None) -> RollingKurt:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the rolling sample excess kurtosis of each column.

        Args:
            X: Input array or DataFrame of shape ``(T, n_features)``.

        Returns:
            Array of shape ``(T, n_features)`` with ``nan`` for rows where
            the window is not yet filled.
        """
        return _as_frame(X).rolling(self.window).kurt().to_numpy()
