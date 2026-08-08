"""Shared validation for portfolio research inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError


def datetime_index(index: pd.Index, *, name: str) -> pd.DatetimeIndex:
    """Validate a sorted, unique datetime index."""
    if not isinstance(index, pd.DatetimeIndex):
        raise TypeError(f"{name} must be a DatetimeIndex")
    result = index.copy()
    if result.hasnans:
        raise ValueError(f"{name} must not contain missing values")
    if not result.is_unique:
        raise ValueError(f"{name} must be unique")
    if not result.is_monotonic_increasing:
        raise ValueError(f"{name} must be sorted")
    return result


def asset_panel(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    """Copy a numeric date-by-asset panel with a fixed universe."""
    result = frame.copy(deep=True)
    datetime_index(result.index, name=f"{name} index")
    if result.columns.hasnans:
        raise ValueError(f"{name} columns must not contain missing values")
    if not result.columns.is_unique:
        raise ValueError(f"{name} columns must be unique")
    if result.shape[1] == 0:
        raise ValueError(f"{name} must contain at least one asset")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in result.dtypes):
        raise AnalysisError(f"{name} columns must be numeric")
    values = result.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise AnalysisError(f"{name} must not contain infinite values")
    return result.astype(float)


def finite_scalar(value: float, *, name: str, minimum: float | None = None) -> float:
    """Validate one finite scalar and an optional inclusive lower bound."""
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result
