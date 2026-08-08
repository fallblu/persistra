"""Tests for coverage and regime-conditioned research summaries."""

import numpy as np
import pandas as pd
import pytest

from persistra.research import summarize_regimes


def test_regime_summary_reports_coverage_statistics_and_episode_drawdown() -> None:
    index = pd.date_range("2025-01-01", periods=5)
    returns = pd.DataFrame(
        {"asset": [0.1, -0.2, 0.05, -0.5, np.nan]},
        index=index,
    )
    regimes = pd.Series(["a", "a", "b", "a", "b"], index=index)

    result = summarize_regimes(returns, regimes, periods_per_year=4)

    assert result.coverage.loc["asset", "coverage"] == 0.8
    statistics = result.regime_statistics.reset_index()
    a = statistics[statistics["regime"].eq("a")].iloc[0]
    assert a["count"] == 3
    assert a["coverage"] == 1
    assert a["mean_return"] == pytest.approx(-0.2)
    assert a["volatility"] == pytest.approx(returns.iloc[[0, 1, 3], 0].std() * 2)
    assert a["max_drawdown"] == pytest.approx(-0.5)
    b = statistics[statistics["regime"].eq("b")].iloc[0]
    assert b["count"] == 1
    assert b["coverage"] == 0.5
    assert b["max_drawdown"] == 0


def test_regime_summary_requires_explicit_alignment_and_valid_scale() -> None:
    returns = pd.DataFrame({"asset": [0.1]}, index=pd.date_range("2025-01-01", periods=1))
    regimes = pd.Series(["a"], index=pd.date_range("2025-01-02", periods=1))
    with pytest.raises(ValueError, match="return index"):
        summarize_regimes(returns, regimes)
    with pytest.raises(ValueError, match="positive and finite"):
        summarize_regimes(returns, pd.Series(["a"], index=returns.index), periods_per_year=0)
    with pytest.raises(ValueError, match="less than -1"):
        summarize_regimes(
            pd.DataFrame({"asset": [-1.1], "missing": [np.nan]}, index=returns.index),
            pd.Series(["a"], index=returns.index),
        )


def test_regime_summary_handles_no_observed_regimes() -> None:
    index = pd.date_range("2025-01-01", periods=2)
    result = summarize_regimes(
        pd.DataFrame({"asset": [0.1, np.nan]}, index=index),
        pd.Series([pd.NA, pd.NA], index=index, dtype="string"),
    )

    assert result.regime_statistics.empty
