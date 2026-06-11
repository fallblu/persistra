"""Tests for experiments/sweep_result.py and experiments/compare.py."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from persistra import Engine, Portfolio
from persistra.core.result import Result
from persistra.experiments.compare import compare
from persistra.experiments.sweep_result import (
    ComparisonResult,
    SweepResult,
    WalkForwardResult,
)
from tests.conftest import EqualWeightRebalance, build_store

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tiny_result(
    capital: float = 1_000_000.0, n: int = 10, tmp_path: Path = Path("/tmp")
) -> Result:
    """Build a minimal Result from a short engine run."""
    times = list(pd.bdate_range("2022-01-03", periods=n))
    store = build_store(
        tmp_path / "s",
        {"AAA": (times, [100.0 + i for i in range(n)]), "BBB": (times, [50.0] * n)},
    )
    engine = Engine(
        data=store,
        strategy=EqualWeightRebalance(),
        portfolio=Portfolio(initial_capital=capital),
        start=times[0].strftime("%Y-%m-%d"),
        end=times[-1].strftime("%Y-%m-%d"),
    )
    return engine.run()


# ---------------------------------------------------------------------------
# SweepResult
# ---------------------------------------------------------------------------


def test_sweep_result_summary_dataframe_shape(tmp_path):
    result_a = _tiny_result(tmp_path=tmp_path / "a")
    result_b = _tiny_result(tmp_path=tmp_path / "b")
    sweep = SweepResult(
        params=[{"x": 1}, {"x": 2}],
        results=[result_a, result_b],
    )
    df = sweep.summary_dataframe()
    assert len(df) == 2
    assert "x" in df.columns
    assert "sharpe" in df.columns


def test_sweep_result_best_returns_valid_pair(tmp_path):
    result_a = _tiny_result(tmp_path=tmp_path / "a")
    result_b = _tiny_result(tmp_path=tmp_path / "b")
    sweep = SweepResult(params=[{"x": 1}, {"x": 2}], results=[result_a, result_b])
    params, best_result = sweep.best(metric="sharpe")
    assert isinstance(params, dict)
    assert isinstance(best_result, Result)


def test_sweep_result_best_raises_on_empty():
    empty = SweepResult(params=[], results=[])
    with pytest.raises(ValueError, match="empty"):
        empty.best()


def test_sweep_result_best_raises_on_bad_metric(tmp_path):
    result = _tiny_result(tmp_path=tmp_path)
    sweep = SweepResult(params=[{}], results=[result])
    with pytest.raises(KeyError):
        sweep.best(metric="nonexistent_metric_xyz")


# ---------------------------------------------------------------------------
# WalkForwardResult
# ---------------------------------------------------------------------------


def _make_walk_forward_result(tmp_path) -> WalkForwardResult:
    """Build a WalkForwardResult with two tiny folds."""
    r1 = _tiny_result(tmp_path=tmp_path / "r1")
    r2 = _tiny_result(tmp_path=tmp_path / "r2")
    folds = [
        (pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-10"), pd.Timestamp("2022-01-14"), r1),
        (pd.Timestamp("2022-01-10"), pd.Timestamp("2022-01-14"), pd.Timestamp("2022-01-21"), r2),
    ]
    return WalkForwardResult(folds=folds)


def test_walk_forward_test_results_length(tmp_path):
    wf = _make_walk_forward_result(tmp_path)
    assert len(wf.test_results()) == 2


def test_walk_forward_test_results_preserve_trimmed_diagnostics(tmp_path):
    result = _tiny_result(tmp_path=tmp_path / "diag")
    result.diagnostics = pd.DataFrame(
        {
            "bar_time": pd.to_datetime(["2022-01-07", "2022-01-11", "2022-01-18"]),
            "timeframe": ["1d", "1d", "1d"],
            "name": ["score", "score", "score"],
            "symbol": ["AAA", "AAA", "AAA"],
            "value": [1.0, 2.0, 3.0],
        }
    )
    wf = WalkForwardResult(
        folds=[
            (
                pd.Timestamp("2022-01-03"),
                pd.Timestamp("2022-01-10"),
                pd.Timestamp("2022-01-14"),
                result,
            )
        ]
    )

    trimmed = wf.test_results()[0]

    assert list(trimmed.diagnostics["value"]) == [2.0]


def test_walk_forward_stitched_equity_curve_is_series(tmp_path):
    wf = _make_walk_forward_result(tmp_path)
    stitched = wf.stitched_equity_curve()
    assert isinstance(stitched, pd.Series)


def test_walk_forward_stitched_empty_when_no_folds():
    wf = WalkForwardResult(folds=[])
    stitched = wf.stitched_equity_curve()
    assert stitched.empty


def test_walk_forward_fold_metrics_columns(tmp_path):
    wf = _make_walk_forward_result(tmp_path)
    df = wf.fold_metrics()
    assert "train_start" in df.columns
    assert "test_start" in df.columns
    assert "test_end" in df.columns
    assert "sharpe" in df.columns
    assert len(df) == 2


# ---------------------------------------------------------------------------
# ComparisonResult
# ---------------------------------------------------------------------------


def test_comparison_result_overlay_equity_returns_figure(tmp_path):
    r1 = _tiny_result(tmp_path=tmp_path / "r1")
    r2 = _tiny_result(tmp_path=tmp_path / "r2")
    cr = ComparisonResult(
        metrics=pd.DataFrame({"sharpe": [0.1, 0.2]}, index=["run_0", "run_1"]),
        _results=[r1, r2],
        _run_ids=["run_0", "run_1"],
    )
    import plotly.graph_objects as go

    fig = cr.overlay_equity()
    assert isinstance(fig, go.Figure)
    assert isinstance(fig.data, tuple)
    assert len(fig.data) == 2  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------


def test_compare_builds_metrics_dataframe(tmp_path):
    r1 = _tiny_result(tmp_path=tmp_path / "r1")
    r2 = _tiny_result(tmp_path=tmp_path / "r2")
    cr = compare([r1, r2])
    assert cr.metrics.shape[0] == 2
    assert "sharpe" in cr.metrics.columns


def test_compare_deduplicates_run_ids(tmp_path):
    """Two runs with the same run_id should get suffixes."""
    r1 = _tiny_result(tmp_path=tmp_path / "r1")
    r2 = _tiny_result(tmp_path=tmp_path / "r2")
    r1.meta["run_id"] = "my_run"
    r2.meta["run_id"] = "my_run"
    cr = compare([r1, r2])
    assert len(cr._run_ids) == 2
    assert cr._run_ids[0] != cr._run_ids[1]


def test_compare_raises_on_empty_list():
    with pytest.raises(ValueError, match="at least one run"):
        compare([])


def test_compare_single_run(tmp_path):
    r = _tiny_result(tmp_path=tmp_path)
    cr = compare([r])
    assert cr.metrics.shape[0] == 1


def test_comparison_metric_bars_and_drawdown_overlay(tiny_store):
    from typing import Any, cast

    import plotly.graph_objects as go

    from persistra import Engine, Portfolio
    from persistra.experiments import compare
    from persistra.strategies import BuyAndHold, EqualWeightRebalance

    def run(strategy):
        return Engine(
            data=tiny_store,
            strategy=strategy,
            portfolio=Portfolio(initial_capital=1_000_000.0),
            start="2022-01-03",
            end="2022-01-11",
        ).run()

    comp = compare([run(BuyAndHold()), run(EqualWeightRebalance())])
    bars = comp.metric_bars("sharpe")
    assert isinstance(bars, go.Figure)
    assert len(cast("tuple[Any, ...]", bars.data)) == 1
    dd = comp.drawdown_overlay()
    assert isinstance(dd, go.Figure)
    assert len(cast("tuple[Any, ...]", dd.data)) == 2
