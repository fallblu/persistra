from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


def _as_array(X: Any) -> np.ndarray:
    arr = np.asarray(X, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


class LogReturn(BaseEstimator, TransformerMixin):
    """Log returns over consecutive rows: ``log(X[1:] / X[:-1])``."""

    def fit(self, X: Any, y: Any = None) -> LogReturn:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute row-over-row log returns.

        Args:
            X: Price array of shape ``(T, n_symbols)`` or ``(T,)``.

        Returns:
            Array of shape ``(T - 1, n_symbols)`` containing ``log(p[t] / p[t-1])``.
            Returns an empty array when fewer than 2 rows are supplied.
        """
        arr = _as_array(X)
        if arr.shape[0] < 2:
            return np.empty((0, arr.shape[1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.log(arr[1:] / arr[:-1])


class SimpleReturn(BaseEstimator, TransformerMixin):
    """Simple percentage return: ``X[1:] / X[:-1] - 1``."""

    def fit(self, X: Any, y: Any = None) -> SimpleReturn:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute row-over-row simple percentage returns.

        Args:
            X: Price array of shape ``(T, n_symbols)`` or ``(T,)``.

        Returns:
            Array of shape ``(T - 1, n_symbols)`` containing ``p[t] / p[t-1] - 1``.
            Returns an empty array when fewer than 2 rows are supplied.
        """
        arr = _as_array(X)
        if arr.shape[0] < 2:
            return np.empty((0, arr.shape[1]))
        return arr[1:] / arr[:-1] - 1.0


class VolScaledReturn(BaseEstimator, TransformerMixin):
    """Log return divided by trailing realised volatility (per column)."""

    def __init__(self, window: int = 21) -> None:
        self.window = window

    def fit(self, X: Any, y: Any = None) -> VolScaledReturn:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute volatility-scaled log returns.

        Divides each log return by the trailing rolling standard deviation
        (window ``self.window``) of that column.  Entries where vol is zero
        or not yet available are ``nan``.

        Args:
            X: Price array of shape ``(T, n_symbols)`` or ``(T,)``.

        Returns:
            Array of shape ``(T - 1, n_symbols)`` containing
            ``log_return / rolling_std``.
        """
        arr = _as_array(X)
        if arr.shape[0] < 2:
            return np.empty((0, arr.shape[1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.log(arr[1:] / arr[:-1])
        vol = pd.DataFrame(rets).rolling(self.window).std().to_numpy()
        # np.where evaluates rets / vol for every element before selecting, so a
        # zero-vol window would raise a divide warning even though the result is
        # discarded in favour of nan. Suppress it; the guard below is the contract.
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(vol > 0, rets / vol, np.nan)


class CumReturn(BaseEstimator, TransformerMixin):
    """Cumulative log-return over the input window.

    Parameters
    ----------
    skip_last : int
        Trailing rows to drop before summing (e.g. 21 = 12-1 momentum).
    input_is_price : bool
        If True, compute log-returns from prices first.
    """

    def __init__(self, skip_last: int = 0, input_is_price: bool = True) -> None:
        if skip_last < 0:
            raise ValueError("skip_last must be >= 0")
        self.skip_last = skip_last
        self.input_is_price = input_is_price

    def fit(self, X: Any, y: Any = None) -> CumReturn:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the cumulative log-return over the input window.

        Converts prices to log returns when ``input_is_price=True``, optionally
        drops the last ``skip_last`` rows before summing, then returns a
        per-symbol total.

        Args:
            X: Price (or return) array of shape ``(T, n_symbols)`` or ``(T,)``.

        Returns:
            Array of shape ``(n_symbols, 1)`` containing the summed log return
            for each symbol.  Returns zeros when there is insufficient data.
        """
        arr = _as_array(X)
        if self.input_is_price:
            if arr.shape[0] < 2:
                return np.zeros((arr.shape[1], 1))
            with np.errstate(divide="ignore", invalid="ignore"):
                rets = np.log(arr[1:] / arr[:-1])
        else:
            rets = arr
        if self.skip_last > 0:
            rets = rets[: -self.skip_last] if rets.shape[0] > self.skip_last else rets[:0]
        if rets.shape[0] == 0:
            return np.zeros((arr.shape[1], 1))
        return np.nansum(rets, axis=0).reshape(-1, 1)
