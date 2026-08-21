"""Analysis for economic and interest-rate series."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.analysis._validation import numeric_frame
from persistra.errors import AnalysisError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from persistra.model import SeriesSet

_MATURITY_YEARS = {
    "3month": 0.25,
    "2year": 2.0,
    "5year": 5.0,
    "7year": 7.0,
    "10year": 10.0,
    "30year": 30.0,
}


def basis_point_change(values: pd.DataFrame, *, rate_unit: str, periods: int = 1) -> pd.DataFrame:
    """Calculate rate changes in basis points from an explicit input unit."""
    checked_periods = require_integer(periods, name="periods", minimum=1)
    factors = {"decimal": 10_000.0, "percent": 100.0, "basis_points": 1.0}
    if rate_unit not in factors:
        raise ValueError("rate_unit must be decimal, percent, or basis_points")
    return numeric_frame(values).diff(checked_periods) * factors[rate_unit]


def growth_rate(values: pd.DataFrame, *, lag: int = 1) -> pd.DataFrame:
    """Calculate fractional growth over one explicit positive lag."""
    checked_lag = require_integer(lag, name="lag", minimum=1)
    result = numeric_frame(values).pct_change(periods=checked_lag, fill_method=None)
    return result.replace([np.inf, -np.inf], np.nan)


def yield_curve(series: Iterable[SeriesSet], *, period_label: str) -> pd.DataFrame:
    """Build one observed Treasury curve without interpolation."""
    rows = _yield_rows(series)
    result = rows[rows["period_label"] == period_label].copy()
    if result.empty:
        raise AnalysisError(f"no Treasury observations for {period_label}")
    return result.sort_values("maturity_years", kind="stable").reset_index(drop=True)


def yield_curve_history(series: Iterable[SeriesSet]) -> pd.DataFrame:
    """Pivot observed Treasury values while preserving missing maturities."""
    rows = _yield_rows(series)
    return rows.pivot(index="period_label", columns="maturity", values="value").sort_index()


def _yield_rows(series: Iterable[SeriesSet]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    frequencies: set[str] = set()
    units: set[str] = set()
    for result in series:
        maturity = result.definition.maturity
        if maturity not in _MATURITY_YEARS:
            raise AnalysisError("every yield series must have a supported Treasury maturity")
        frequencies.add(result.definition.frequency)
        units.add(result.definition.unit)
        frame = result.frame[["period_label", "value"]].copy()
        frame["maturity"] = maturity
        frame["maturity_years"] = _MATURITY_YEARS[maturity]
        frames.append(frame)
    if not frames:
        raise AnalysisError("at least one Treasury series is required")
    if len(frequencies) != 1 or len(units) != 1:
        raise AnalysisError("Treasury series must have compatible frequency and units")
    return pd.concat(frames, ignore_index=True)
