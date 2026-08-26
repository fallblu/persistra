"""Shared strict validation for Monte Carlo arrays and labeled parameters."""

from __future__ import annotations

from numbers import Real
from typing import cast

import numpy as np
import pandas as pd


def finite_scalar(value: object, *, name: str, positive: bool = False) -> float:
    """Return one finite real scalar with an optional strict-positive requirement."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a finite real scalar")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if positive and result <= 0.0:
        raise ValueError(f"{name} must be positive")
    return result


def named_vector(
    values: pd.Series,
    *,
    name: str,
    positive: bool = False,
) -> pd.Series:
    """Return a defensive finite vector with unique ordered string labels."""
    if values.empty:
        raise ValueError(f"{name} must not be empty")
    if not values.index.is_unique:
        raise ValueError(f"{name} labels must be unique")
    labels = cast("list[object]", values.index.tolist())
    if any(not isinstance(label, str) or not label for label in labels):
        raise ValueError(f"{name} labels must be nonempty strings")
    if not pd.api.types.is_numeric_dtype(values.dtype):
        raise TypeError(f"{name} must be numeric")
    result = values.astype(float).copy(deep=True)
    array = result.to_numpy(dtype=float)
    if not np.isfinite(array).all():
        raise ValueError(f"{name} must be finite and complete")
    if positive and (array <= 0.0).any():
        raise ValueError(f"{name} must be positive")
    return result


def covariance_matrix(
    covariance: pd.DataFrame,
    labels: pd.Index,
    *,
    name: str,
    tolerance: float = 1e-12,
) -> pd.DataFrame:
    """Return a defensive symmetric positive-semidefinite labeled covariance."""
    if not covariance.index.equals(labels) or not covariance.columns.equals(labels):
        raise ValueError(f"{name} must use the declared ordered axes")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in covariance.dtypes):
        raise TypeError(f"{name} must be numeric")
    result = covariance.astype(float).copy(deep=True)
    values = result.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{name} must be finite and complete")
    if not np.allclose(values, values.T, rtol=0.0, atol=tolerance):
        raise ValueError(f"{name} must be symmetric")
    if float(np.linalg.eigvalsh(values).min()) < -tolerance:
        raise ValueError(f"{name} must be positive semidefinite")
    return result


def sample_size(size: tuple[int, ...]) -> tuple[int, ...]:
    """Validate one ordered NumPy sample shape."""
    dimensions = cast("tuple[object, ...]", size)
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in dimensions
    ):
        raise ValueError("sample size dimensions must be nonnegative integers")
    return tuple(size)
