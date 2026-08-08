"""Coverage and regime-conditioned research summaries."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from persistra.analysis import coverage_summary
from persistra.research._validation import datetime_index, numeric_frame
from persistra.research.model import ResearchSummary


def summarize_regimes(
    returns: pd.DataFrame,
    regimes: pd.Series,
    *,
    periods_per_year: float | None = None,
) -> ResearchSummary:
    """Summarize coverage and returns within explicit regimes.

    Volatility is the sample standard deviation and is annualized only when
    ``periods_per_year`` is supplied. Drawdown resets at regime changes and missing returns so
    separate regime episodes are never compounded together.
    """
    data = numeric_frame(returns)
    datetime_index(data.index, name="return index")
    if not regimes.index.equals(data.index):
        raise ValueError("regimes must use the return index")
    if periods_per_year is not None and (
        not np.isfinite(periods_per_year) or periods_per_year <= 0
    ):
        raise ValueError("periods_per_year must be positive and finite")
    if data.lt(-1).any(axis=None):
        raise ValueError("simple returns must not be less than -1")
    rows: list[dict[str, Any]] = []
    observed_regimes = regimes.dropna().drop_duplicates().tolist()
    for regime in observed_regimes:
        regime_mask = regimes.eq(regime).fillna(False)
        regime_count = int(regime_mask.sum())
        for position, column in enumerate(data.columns):
            series = data.iloc[:, position]
            values = series.loc[regime_mask].dropna()
            volatility = values.std(ddof=1)
            if periods_per_year is not None:
                volatility *= np.sqrt(periods_per_year)
            rows.append(
                {
                    "regime": regime,
                    "column": column,
                    "count": len(values),
                    "coverage": len(values) / regime_count,
                    "mean_return": values.mean(),
                    "volatility": volatility,
                    "max_drawdown": _regime_drawdown(series, regime_mask),
                }
            )
    columns = ["count", "coverage", "mean_return", "volatility", "max_drawdown"]
    if rows:
        statistics = pd.DataFrame(rows).set_index(["regime", "column"])[columns]
    else:
        empty_index = pd.MultiIndex.from_arrays([[], []], names=["regime", "column"])
        statistics = pd.DataFrame(columns=columns, index=empty_index)
    return ResearchSummary(coverage_summary(data), statistics, periods_per_year)


def _regime_drawdown(values: pd.Series, regime_mask: pd.Series) -> float:
    active = regime_mask & values.notna()
    positions = np.flatnonzero(active.to_numpy())
    if not len(positions):
        return float("nan")
    worst = 0.0
    start = 0
    while start < len(positions):
        stop = start + 1
        while stop < len(positions) and positions[stop] == positions[stop - 1] + 1:
            stop += 1
        segment = values.iloc[positions[start:stop]].to_numpy(dtype=float)
        wealth = np.concatenate(([1.0], np.cumprod(1 + segment)))
        drawdown = wealth / np.maximum.accumulate(wealth) - 1
        worst = min(worst, float(drawdown.min()))
        start = stop
    return worst
