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


class EWMA(BaseEstimator, TransformerMixin):
    """Exponentially weighted moving average.

    Supports ``partial_fit`` for streaming updates.

    Parameters
    ----------
    span : float
        Pandas-style span. Maps to alpha = 2 / (span + 1).
    adjust : bool
        Match ``pd.DataFrame.ewm(adjust=...)``. Default True (batch-friendly).
    """

    def __init__(self, span: float = 20.0, adjust: bool = True) -> None:
        if span <= 0:
            raise ValueError("span must be > 0")
        self.span = span
        self.adjust = adjust
        self._state: np.ndarray | None = None

    @property
    def signal(self) -> float:
        """EMA smoothing factor alpha derived from ``span``.

        Returns:
            ``2 / (span + 1)``, the per-step decay coefficient used by
            ``partial_fit``.
        """
        return 2.0 / (self.span + 1.0)

    def fit(self, X: Any, y: Any = None) -> EWMA:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute the batch EWMA for the full input window.

        Uses ``pd.DataFrame.ewm(span=self.span, adjust=self.adjust)``, so the
        first value equals the first observation when ``adjust=True``.

        Args:
            X: Price or signal array of shape ``(T, n_symbols)`` or ``(T,)``.

        Returns:
            Array of shape ``(T, n_symbols)`` with EWMA values.
        """
        arr = _as_array(X)
        return pd.DataFrame(arr).ewm(span=self.span, adjust=self.adjust).mean().to_numpy()

    def partial_fit(self, X: Any, y: Any = None) -> EWMA:
        """Update the running EWMA state with one or more new rows.

        Iterates row-by-row, applying ``alpha = 2 / (span + 1)`` to blend
        each new observation into the stored state.  ``nan`` inputs are
        skipped; the state is initialised from the first finite observation
        per column.

        Args:
            X: New observations of shape ``(T, n_symbols)`` or ``(T,)``.
                Column count must match any previously fitted state.

        Returns:
            ``self`` (the state is stored in ``self._state``).
        """
        arr = _as_array(X)
        alpha = self.signal
        prior = self._state if self._state is not None else np.full(arr.shape[1], np.nan)
        state = np.asarray(prior)
        if state.shape[0] != arr.shape[1]:
            raise ValueError("partial_fit column count must match prior state")
        for i in range(arr.shape[0]):
            row = np.asarray(arr[i])
            mask = np.asarray(np.isfinite(row))
            init = np.asarray(np.isnan(state)) & mask
            state = np.asarray(np.where(init, row, state))
            state = np.asarray(np.where(mask & ~init, alpha * row + (1 - alpha) * state, state))
        self._state = state
        return self

    def latest(self) -> np.ndarray:
        """Return the current EWMA state as a 1-D array.

        Returns:
            Array of shape ``(n_symbols,)`` with the last computed EWMA per
            symbol, or an empty array if ``partial_fit`` has never been called.
        """
        if self._state is None:
            return np.array([])
        return self._state.copy()


class EWVolatility(BaseEstimator, TransformerMixin):
    """Exponentially weighted realised volatility.

    Input shape:  (T, n_symbols) — raw prices
    Output shape: (T - 1, n_symbols) — vol estimates aligned with log-return rows.
    """

    def __init__(self, span: float = 20.0) -> None:
        if span <= 0:
            raise ValueError("span must be > 0")
        self.span = span
        self._state: np.ndarray | None = None

    def fit(self, X: Any, y: Any = None) -> EWVolatility:
        """No-op fit; returns ``self`` (stateless transformer, kept for the scikit-learn API)."""
        return self

    def transform(self, X: Any) -> np.ndarray:
        """Compute batch exponentially weighted volatility from a price array.

        Converts prices to log returns, then computes the EW variance with
        ``pd.DataFrame.ewm(span=self.span, adjust=True)`` and takes the
        square root.

        Args:
            X: Price array of shape ``(T, n_symbols)`` or ``(T,)``.

        Returns:
            Array of shape ``(T - 1, n_symbols)`` with per-row EW volatility
            estimates.  Returns an empty array when fewer than 2 rows are
            supplied.
        """
        arr = _as_array(X)
        if arr.shape[0] < 2:
            return np.empty((0, arr.shape[1]))
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.log(arr[1:] / arr[:-1])
        return np.sqrt(pd.DataFrame(rets).ewm(span=self.span, adjust=True).var().to_numpy())

    def partial_fit(self, X: Any, y: Any = None) -> EWVolatility:
        """Update the running EW-variance state with one or more new price rows.

        Computes log returns from consecutive rows, then blends each squared
        return into the stored variance state using
        ``alpha = 2 / (span + 1)``.  Non-finite returns are skipped; the
        state is initialised from the first finite squared return per column.

        Args:
            X: New price observations of shape ``(T, n_symbols)`` or ``(T,)``.
                Requires at least 2 rows to update; fewer rows are a no-op.

        Returns:
            ``self`` (the state is stored in ``self._state`` as EW variance).
        """
        arr = _as_array(X)
        if arr.shape[0] < 2:
            return self
        with np.errstate(divide="ignore", invalid="ignore"):
            rets = np.log(arr[1:] / arr[:-1])
        alpha = 2.0 / (self.span + 1.0)
        prior = self._state if self._state is not None else np.full(rets.shape[1], np.nan)
        state = np.asarray(prior)
        for i in range(rets.shape[0]):
            row = np.asarray(rets[i])
            sq = row * row
            mask = np.asarray(np.isfinite(sq))
            init = np.asarray(np.isnan(state)) & mask
            state = np.asarray(np.where(init, sq, state))
            state = np.asarray(np.where(mask & ~init, alpha * sq + (1 - alpha) * state, state))
        self._state = state
        return self

    def latest(self) -> np.ndarray:
        """Return the current EW volatility estimate as a 1-D array.

        Returns:
            Array of shape ``(n_symbols,)`` containing ``sqrt(EW_variance)``
            per symbol, or an empty array if ``partial_fit`` has never been
            called.
        """
        if self._state is None:
            return np.array([])
        return np.sqrt(self._state).copy()
