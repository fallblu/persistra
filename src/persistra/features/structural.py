from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin


def _as_array(X: Any) -> np.ndarray:
    arr = np.asarray(X, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return arr


class RollingPCA(BaseEstimator, TransformerMixin):
    """First-principal-component loading per symbol via SVD."""

    def __init__(self, n_components: int = 1) -> None:
        if n_components < 1:
            raise ValueError("n_components must be >= 1")
        self.n_components = n_components

    def fit(self, X: Any, y: Any = None) -> RollingPCA:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the top-``n_components`` PCA loadings from the input window.

        Mean-centres the columns, runs a full SVD, and returns the right
        singular vectors (loadings) for the top components.  NaN entries are
        replaced with column means before the SVD.

        Args:
            X: Price or return array of shape ``(T, n_symbols)``.

        Returns:
            Array of shape ``(n_symbols, n_components)`` where each column is
            a principal-component loading vector.  Returns zeros when fewer
            than 2 rows are supplied or the SVD fails.
        """
        arr = _as_array(X)
        if arr.shape[0] < 2:
            return np.zeros((arr.shape[1], self.n_components))
        clean = np.where(np.isfinite(arr), arr, np.nan)
        col_mean = np.nanmean(clean, axis=0, keepdims=True)
        centered = np.where(np.isnan(clean), 0.0, clean - col_mean)
        try:
            _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
        except np.linalg.LinAlgError:
            return np.zeros((arr.shape[1], self.n_components))
        k = min(self.n_components, vt.shape[0])
        loadings = vt[:k].T
        out = np.zeros((arr.shape[1], self.n_components))
        out[:, :k] = loadings
        return out


class CointegrationCoefficients(BaseEstimator, TransformerMixin):
    """Per-symbol OLS hedge ratio against a reference column."""

    def __init__(self, reference_index: int = 0) -> None:
        self.reference_index = reference_index

    def fit(self, X: Any, y: Any = None) -> CointegrationCoefficients:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Estimate OLS hedge ratios of each symbol against the reference column.

        Computes log prices, then regresses each non-reference column on the
        reference column (demeaned covariance / variance) to obtain a scalar
        hedge ratio.  The reference symbol gets a ratio of 1.0.

        Args:
            X: Price array of shape ``(T, n_symbols)`` where column
                ``reference_index`` is the reference asset.

        Returns:
            Array of shape ``(n_symbols, 1)`` of OLS hedge ratios.
            Returns zeros when fewer than 2 rows are supplied; individual
            entries are ``nan`` when there is insufficient finite data.
        """
        arr = _as_array(X)
        n_sym = arr.shape[1]
        if arr.shape[0] < 2 or n_sym == 0:
            return np.zeros((n_sym, 1))
        ref_idx = self.reference_index
        if not 0 <= ref_idx < n_sym:
            return np.zeros((n_sym, 1))
        with np.errstate(divide="ignore", invalid="ignore"):
            log_prices = np.log(arr)
        ref = log_prices[:, ref_idx]
        out = np.zeros((n_sym, 1))
        for j in range(n_sym):
            if j == ref_idx:
                out[j, 0] = 1.0
                continue
            col = log_prices[:, j]
            mask = np.isfinite(col) & np.isfinite(ref)
            if mask.sum() < 2:
                out[j, 0] = np.nan
                continue
            c = col[mask] - col[mask].mean()
            r = ref[mask] - ref[mask].mean()
            cov = float(np.nanmean(np.asarray(c) * np.asarray(r)))
            var_ref = float(np.nanvar(ref[mask]))
            out[j, 0] = cov / var_ref if var_ref > 0 else np.nan
        return out


class KalmanHedgeRatio(BaseEstimator, TransformerMixin):
    """Recursive (1D) hedge-ratio estimate against a reference column."""

    def __init__(self, reference_index: int = 0, delta: float = 1e-4) -> None:
        if not 0.0 < delta < 1.0:
            raise ValueError("delta must be in (0, 1)")
        self.reference_index = reference_index
        self.delta = delta

    def fit(self, X: Any, y: Any = None) -> KalmanHedgeRatio:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Estimate a time-varying hedge ratio via a 1-D Kalman filter.

        For each non-reference symbol, runs a scalar Kalman filter on log
        prices to recursively estimate beta such that
        ``log(y) ≈ beta * log(ref)``.  The state variance is inflated by
        ``1 / (1 - delta)`` each step to allow the ratio to drift.

        Args:
            X: Price array of shape ``(T, n_symbols)`` where column
                ``reference_index`` is the reference asset.

        Returns:
            Array of shape ``(n_symbols, 1)`` containing the final Kalman
            hedge ratio for each symbol.  The reference column is always
            1.0.  Returns zeros when fewer than 2 rows are supplied.
        """
        arr = _as_array(X)
        n_sym = arr.shape[1]
        if arr.shape[0] < 2 or n_sym == 0:
            return np.zeros((n_sym, 1))
        ref_idx = self.reference_index
        if not 0 <= ref_idx < n_sym:
            return np.zeros((n_sym, 1))
        with np.errstate(divide="ignore", invalid="ignore"):
            lp = np.log(arr)
        ref = lp[:, ref_idx]
        out = np.zeros((n_sym, 1))
        lam = 1.0 - self.delta
        for j in range(n_sym):
            if j == ref_idx:
                out[j, 0] = 1.0
                continue
            col = lp[:, j]
            beta = 0.0
            var = 1.0
            for t in range(arr.shape[0]):
                x = ref[t]
                y_t = col[t]
                if not (np.isfinite(x) and np.isfinite(y_t)):
                    var = var / lam
                    continue
                k = var * x / (lam + x * var * x)
                beta = beta + k * (y_t - beta * x)
                var = (var - k * x * var) / lam
            out[j, 0] = beta
        return out
