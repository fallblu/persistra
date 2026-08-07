"""Analysis for normalized market observations."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from persistra.analysis.general import rolling_volatility

if TYPE_CHECKING:
    from persistra.model import BarSet, TopOfBookSet


def midprice(book: TopOfBookSet) -> pd.DataFrame:
    """Calculate bid-ask midprices while preserving missing sides."""
    result = book.frame[["instrument_id", "provider_symbol", "observed_at"]].copy()
    result["midprice"] = (book.frame["bid_price"] + book.frame["ask_price"]) / 2
    return result


def absolute_spread(book: TopOfBookSet) -> pd.DataFrame:
    """Calculate ask minus bid while preserving missing sides."""
    result = book.frame[["instrument_id", "provider_symbol", "observed_at"]].copy()
    result["absolute_spread"] = book.frame["ask_price"] - book.frame["bid_price"]
    return result


def relative_spread(book: TopOfBookSet) -> pd.DataFrame:
    """Calculate absolute spread divided by midprice."""
    result = absolute_spread(book)
    midpoint = (book.frame["bid_price"] + book.frame["ask_price"]) / 2
    result["relative_spread"] = (result["absolute_spread"] / midpoint).where(midpoint > 0)
    return result


def bar_range(bars: BarSet) -> pd.DataFrame:
    """Calculate high minus low for each normalized bar."""
    result = _bar_identity(bars)
    result["bar_range"] = bars.frame["high"] - bars.frame["low"]
    return result


def true_range(bars: BarSet) -> pd.DataFrame:
    """Calculate true range with previous close within the supplied result."""
    previous_close = bars.frame["close"].shift(1)
    components = pd.concat(
        [
            bars.frame["high"] - bars.frame["low"],
            (bars.frame["high"] - previous_close).abs(),
            (bars.frame["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    result = _bar_identity(bars)
    result["true_range"] = components.max(axis=1, skipna=True)
    return result


def volume_summary(bars: BarSet) -> pd.Series:
    """Summarize available normalized volume observations."""
    volume = bars.frame["volume"].dropna().astype(float)
    return pd.Series(
        {
            "count": len(volume),
            "total": volume.sum(),
            "mean": volume.mean(),
            "median": volume.median(),
            "standard_deviation": volume.std(ddof=1),
        },
        dtype="float64",
    )


def realized_volatility(
    returns: pd.DataFrame,
    *,
    window: int,
    periods_per_year: float,
) -> pd.DataFrame:
    """Calculate annualized realized volatility from explicit returns."""
    return rolling_volatility(
        returns,
        window=window,
        periods_per_year=periods_per_year,
    )


def session_coverage(bars: BarSet) -> pd.DataFrame:
    """Describe observed bar labels without inferring expected sessions."""
    time = bars.frame["timestamp"].combine_first(pd.to_datetime(bars.frame["date"], utc=True))
    grouped = bars.frame.assign(_time=time).groupby(
        ["instrument_id", "interval", "session"], dropna=False, sort=True
    )
    return grouped.agg(
        observed_count=("_time", "count"),
        first_observed=("_time", "min"),
        last_observed=("_time", "max"),
    ).reset_index()


def _bar_identity(bars: BarSet) -> pd.DataFrame:
    return bars.frame[["instrument_id", "date", "timestamp", "interval"]].copy()
