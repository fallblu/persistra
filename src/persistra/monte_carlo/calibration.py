"""Pure explicit calibration helpers for Monte Carlo models."""

from __future__ import annotations

import numpy as np
import pandas as pd

from persistra.monte_carlo._validation import finite_scalar, named_vector
from persistra.monte_carlo.models import GeometricBrownianMotion


def fit_geometric_brownian_motion(
    log_returns: pd.DataFrame,
    *,
    initial_prices: pd.Series,
    periods_per_year: float,
) -> GeometricBrownianMotion:
    """Fit GBM after the caller has chosen log returns, sample, and annualization."""
    annualization = finite_scalar(periods_per_year, name="periods_per_year", positive=True)
    initial = named_vector(initial_prices, name="initial_prices", positive=True)
    if len(log_returns) < 2:
        raise ValueError("log_returns must contain at least two observations")
    if not log_returns.columns.equals(initial.index):
        raise ValueError("log_returns must use the initial price axis")
    if not log_returns.index.is_unique or not log_returns.index.is_monotonic_increasing:
        raise ValueError("log_returns index must be unique and ordered")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in log_returns.dtypes):
        raise TypeError("log_returns must be numeric")
    sample = log_returns.astype(float).copy(deep=True)
    if not np.isfinite(sample.to_numpy(dtype=float)).all():
        raise ValueError("log_returns must be finite and complete")
    covariance = sample.cov().mul(annualization)
    covariance.index = initial.index.copy()
    covariance.columns = initial.index.copy()
    drift = sample.mean().mul(annualization).add(np.diag(covariance) / 2.0)
    drift.index = initial.index.copy()
    return GeometricBrownianMotion(initial, drift, covariance)
