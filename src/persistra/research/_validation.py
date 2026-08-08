"""Shared validation for point-in-time research inputs."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError

ZERO_DAYS = pd.Timedelta(0)

if TYPE_CHECKING:
    from datetime import date, datetime


def calendar_date(
    value: date | datetime | str | pd.Timestamp,
    *,
    name: str,
) -> pd.Timestamp:
    """Return one normalized timezone-naive calendar date."""
    result = pd.Timestamp(value)
    if pd.isna(result):
        raise ValueError(f"{name} must not be missing")
    if result.tz is not None:
        raise ValueError(f"{name} must be timezone-naive")
    if result != result.normalize():
        raise ValueError(f"{name} must be a calendar date")
    return result


def calendar_index(index: pd.Index, *, name: str) -> pd.DatetimeIndex:
    """Validate a sorted unique calendar-date index."""
    result = datetime_index(index, name=name)
    if result.tz is not None:
        raise ValueError(f"{name} must be timezone-naive")
    if not result.equals(result.normalize()):
        raise ValueError(f"{name} must contain calendar dates")
    return result


def datetime_index(index: pd.Index, *, name: str) -> pd.DatetimeIndex:
    """Validate a sorted unique datetime index without changing its timezone."""
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


def numeric_frame(frame: pd.DataFrame, *, positive: bool = False) -> pd.DataFrame:
    """Copy a finite numeric frame and optionally require positive observations."""
    result = frame.copy(deep=True)
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in result.dtypes):
        raise AnalysisError("research input columns must be numeric")
    values = result.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(values).any():
        raise AnalysisError("research input must not contain infinite values")
    if positive and (values[~np.isnan(values)] <= 0).any():
        raise AnalysisError("level observations must be positive")
    return result


def cross_sectional_frame(
    frame: pd.DataFrame,
    *,
    name: str,
    positive: bool = False,
) -> pd.DataFrame:
    """Validate one numeric date-by-asset panel with a fixed explicit universe."""
    result = numeric_frame(frame, positive=positive)
    datetime_index(result.index, name=f"{name} index")
    if result.columns.hasnans:
        raise ValueError(f"{name} columns must not contain missing values")
    if not result.columns.is_unique:
        raise ValueError(f"{name} columns must be unique")
    return result


def aligned_panel(frame: pd.DataFrame, reference: pd.DataFrame, *, name: str) -> pd.DataFrame:
    """Copy a panel whose date and asset axes exactly match a reference panel."""
    result = frame.copy(deep=True)
    if not result.index.equals(reference.index) or not result.columns.equals(reference.columns):
        raise ValueError(f"{name} must use the same index and columns as the signal panel")
    return result


def require_whole_days(value: pd.Timedelta, *, name: str) -> None:
    """Require a nonnegative duration expressed in whole calendar days."""
    if value < ZERO_DAYS:
        raise ValueError(f"{name} must not be negative")
    if value % pd.Timedelta(days=1):
        raise ValueError(f"{name} must use whole calendar days")
