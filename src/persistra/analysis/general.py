"""General analysis for explicit wide numeric frames."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from persistra.analysis._validation import numeric_frame as _numeric
from persistra.errors import AnalysisError


def coverage_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Summarize observed and missing labels for each column."""
    data = _numeric(frame)
    output_columns = ["count", "missing", "coverage", "first_observed", "last_observed"]
    rows: list[dict[str, object]] = []
    for column in data:
        observed = data[column].dropna()
        rows.append(
            {
                "column": column,
                "count": len(observed),
                "missing": int(data[column].isna().sum()),
                "coverage": len(observed) / len(data) if len(data) else np.nan,
                "first_observed": observed.index[0] if not observed.empty else None,
                "last_observed": observed.index[-1] if not observed.empty else None,
            }
        )
    if not rows:
        return pd.DataFrame(columns=output_columns, index=pd.Index([], name="column"))
    return pd.DataFrame(rows).set_index("column")[output_columns]


def summary_statistics(frame: pd.DataFrame) -> pd.DataFrame:
    """Return sample statistics and pandas linear quantiles by column."""
    data = _numeric(frame)
    return data.agg(["count", "mean", "std", "min", "median", "max"]).T.join(
        data.quantile([0.25, 0.75]).T.rename(columns={0.25: "25%", 0.75: "75%"})
    )[["count", "mean", "std", "min", "25%", "median", "75%", "max"]]


def absolute_change(frame: pd.DataFrame, *, periods: int = 1) -> pd.DataFrame:
    """Calculate arithmetic differences without bridging missing levels."""
    return _change_inputs(frame, periods).diff(periods)


def percentage_change(frame: pd.DataFrame, *, periods: int = 1) -> pd.DataFrame:
    """Calculate fractional changes without filling missing levels."""
    return _change_inputs(frame, periods).pct_change(periods=periods, fill_method=None)


def log_change(frame: pd.DataFrame, *, periods: int = 1) -> pd.DataFrame:
    """Calculate log-level differences after requiring positive levels."""
    data = _change_inputs(frame, periods)
    _require_positive(data)
    logged = cast("pd.DataFrame", np.log(data))
    return logged.diff(periods)


def simple_returns(frame: pd.DataFrame, *, periods: int = 1) -> pd.DataFrame:
    """Calculate simple price returns without filling missing levels."""
    return percentage_change(frame, periods=periods)


def log_returns(frame: pd.DataFrame, *, periods: int = 1) -> pd.DataFrame:
    """Calculate log price returns after requiring positive levels."""
    return log_change(frame, periods=periods)


def rebase(frame: pd.DataFrame, *, base: float = 100) -> pd.DataFrame:
    """Rebase each column to its first observed positive level."""
    if not np.isfinite(base) or base <= 0:
        raise ValueError("base must be positive and finite")
    data = _numeric(frame)
    _require_positive(data)
    first = pd.Series(
        {
            column: data[column].dropna().iloc[0] if data[column].notna().any() else np.nan
            for column in data
        }
    )
    return data.divide(first).multiply(base)


def cumulative_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Compound simple returns after rejecting internal observed-span gaps."""
    data = _numeric(returns)
    _reject_internal_gaps(data)
    return (1 + data).cumprod() - 1


def drawdowns(returns: pd.DataFrame) -> pd.DataFrame:
    """Calculate drawdowns from simple returns with continuous observed paths."""
    wealth = cumulative_returns(returns) + 1
    return wealth.divide(wealth.cummax()) - 1


def rolling_mean(
    frame: pd.DataFrame, *, window: int, min_periods: int | None = None
) -> pd.DataFrame:
    """Calculate rolling means with complete windows by default."""
    return _numeric(frame).rolling(window, min_periods=min_periods or window).mean()


def rolling_standard_deviation(
    frame: pd.DataFrame, *, window: int, min_periods: int | None = None
) -> pd.DataFrame:
    """Calculate sample rolling standard deviations."""
    return _numeric(frame).rolling(window, min_periods=min_periods or window).std(ddof=1)


def rolling_volatility(
    returns: pd.DataFrame,
    *,
    window: int,
    periods_per_year: float,
    min_periods: int | None = None,
) -> pd.DataFrame:
    """Annualize sample rolling return volatility with an explicit scale."""
    if periods_per_year <= 0 or not np.isfinite(periods_per_year):
        raise ValueError("periods_per_year must be positive and finite")
    return rolling_standard_deviation(returns, window=window, min_periods=min_periods) * np.sqrt(
        periods_per_year
    )


def rolling_zscore(
    frame: pd.DataFrame, *, window: int, min_periods: int | None = None
) -> pd.DataFrame:
    """Calculate rolling sample z-scores."""
    data = _numeric(frame)
    minimum = min_periods or window
    mean = data.rolling(window, min_periods=minimum).mean()
    standard_deviation = data.rolling(window, min_periods=minimum).std(ddof=1)
    return (data - mean) / standard_deviation


def covariance_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate sample covariance with pairwise complete observations."""
    return _numeric(frame).cov(ddof=1)


def correlation_matrix(frame: pd.DataFrame) -> pd.DataFrame:
    """Calculate Pearson correlation with pairwise complete observations."""
    return _numeric(frame).corr(method="pearson")


def _change_inputs(frame: pd.DataFrame, periods: int) -> pd.DataFrame:
    if periods <= 0:
        raise ValueError("periods must be positive")
    return _numeric(frame)


def _require_positive(frame: pd.DataFrame) -> None:
    if (frame.dropna() <= 0).any(axis=None):
        raise AnalysisError("log and rebasing inputs must be positive")


def _reject_internal_gaps(frame: pd.DataFrame) -> None:
    for column in frame:
        observed = frame[column].notna()
        if not observed.any():
            continue
        positions = np.flatnonzero(observed.to_numpy())
        if frame[column].iloc[positions[0] : positions[-1] + 1].isna().any():
            raise AnalysisError(f"{column} contains an internal gap")
