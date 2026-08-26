"""Tests for general explicit wide-frame analysis."""

import numpy as np
import pandas as pd
import pytest

from persistra.analysis import (
    absolute_change,
    correlation_matrix,
    covariance_matrix,
    coverage_summary,
    cumulative_returns,
    drawdowns,
    log_change,
    log_returns,
    percentage_change,
    rebase,
    rolling_mean,
    rolling_standard_deviation,
    rolling_volatility,
    rolling_zscore,
    simple_returns,
    summary_statistics,
)
from persistra.errors import AnalysisError


def levels() -> pd.DataFrame:
    """Return a small hand-calculated level frame."""
    return pd.DataFrame(
        {"a": [100.0, 110.0, np.nan, 121.0], "b": [50.0, 50.0, 55.0, 60.5]},
        index=pd.date_range("2025-01-01", periods=4),
    )


def test_coverage_and_summary_statistics() -> None:
    frame = levels()
    coverage = coverage_summary(frame)
    assert coverage.loc["a", "count"] == 3
    assert coverage.loc["a", "coverage"] == 0.75
    summary = summary_statistics(frame)
    assert summary.loc["b", "mean"] == pytest.approx(53.875)
    assert "75%" in summary
    assert coverage_summary(frame.iloc[:0])["coverage"].isna().all()
    assert coverage_summary(pd.DataFrame()).empty


def test_changes_and_returns_preserve_internal_gaps() -> None:
    frame = levels()
    assert absolute_change(frame).at[frame.index[1], "a"] == 10
    assert percentage_change(frame).at[frame.index[1], "a"] == pytest.approx(0.1)
    assert percentage_change(frame).at[frame.index[2], "a"] is np.nan or pd.isna(
        percentage_change(frame).at[frame.index[2], "a"]
    )
    pd.testing.assert_frame_equal(simple_returns(frame), percentage_change(frame))
    assert log_change(frame).at[frame.index[1], "a"] == pytest.approx(np.log(1.1))
    pd.testing.assert_frame_equal(log_returns(frame), log_change(frame))
    with pytest.raises(ValueError, match="periods"):
        absolute_change(frame, periods=0)


def test_rebase_cumulative_returns_and_drawdowns() -> None:
    complete = levels()[["b"]]
    rebased = rebase(complete)
    assert rebased.iloc[0, 0] == 100
    returns = simple_returns(complete)
    cumulative = cumulative_returns(returns)
    assert cumulative.iloc[-1, 0] == pytest.approx(0.21)
    assert drawdowns(returns).dropna().le(0).all(axis=None)
    with pytest.raises(AnalysisError, match="internal gap"):
        cumulative_returns(levels()[["a"]])
    with pytest.raises(ValueError, match="base"):
        rebase(complete, base=0)
    with pytest.raises(AnalysisError, match="positive"):
        rebase(pd.DataFrame({"x": [1.0, 0.0]}))


def test_rolling_and_matrix_statistics() -> None:
    frame = levels().dropna()
    assert rolling_mean(frame, window=2).iloc[0].isna().all()
    standard = rolling_standard_deviation(frame, window=2)
    assert standard.iloc[1].notna().all()
    volatility = rolling_volatility(frame, window=2, periods_per_year=12)
    pd.testing.assert_frame_equal(volatility, standard * np.sqrt(12))
    zscore = rolling_zscore(frame, window=2)
    assert pd.notna(zscore.iloc[1]["a"])
    assert pd.isna(zscore.iloc[1]["b"])
    assert covariance_matrix(frame).shape == (2, 2)
    assert correlation_matrix(frame).loc["a", "a"] == 1
    with pytest.raises(ValueError, match="periods_per_year"):
        rolling_volatility(frame, window=2, periods_per_year=0)


def test_general_analysis_rejects_nonnumeric_and_infinite_inputs() -> None:
    with pytest.raises(AnalysisError, match="numeric"):
        summary_statistics(pd.DataFrame({"x": ["text"]}))
    with pytest.raises(AnalysisError, match="non-boolean"):
        summary_statistics(pd.DataFrame({"x": [True]}))
    with pytest.raises(AnalysisError, match="infinite"):
        summary_statistics(pd.DataFrame({"x": [np.inf]}))
    with pytest.raises(AnalysisError, match="positive"):
        log_change(pd.DataFrame({"x": [-1.0, 2.0]}))
