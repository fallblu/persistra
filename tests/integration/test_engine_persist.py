"""Tests for Engine.run() with output_dir — covers core/artifacts.save, logging, hashing."""

from __future__ import annotations

import pandas as pd

from persistra import Engine, Portfolio
from tests.conftest import EqualWeightRebalance, build_store


def _simple_engine(store, times: list, strategy=None) -> Engine:
    if strategy is None:
        strategy = EqualWeightRebalance()
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start=times[0].strftime("%Y-%m-%d"),
        end=times[-1].strftime("%Y-%m-%d"),
    )


def test_run_with_output_dir_writes_artifacts(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0 + i for i in range(6)])},
    )
    engine = _simple_engine(store, times)
    result = engine.run(output_dir=tmp_path / "runs")

    assert "run_id" in result.meta
    run_dir = tmp_path / "runs" / result.meta["run_id"]
    assert run_dir.exists()
    assert (run_dir / "equity_curve.parquet").exists()
    assert (run_dir / "trades.parquet").exists()
    assert (run_dir / "summary.json").exists()


def test_run_with_explicit_run_id(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0 + i for i in range(6)])},
    )
    engine = _simple_engine(store, times)
    result = engine.run(output_dir=tmp_path / "runs", run_id="my_explicit_run")

    assert result.meta["run_id"] == "my_explicit_run"
    assert (tmp_path / "runs" / "my_explicit_run").exists()


def test_run_with_meta_extra(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0 + i for i in range(6)])},
    )
    engine = _simple_engine(store, times)
    result = engine.run(
        output_dir=tmp_path / "runs",
        meta_extra={"alpha_param": 0.5, "version": 2},
    )

    assert result.meta["alpha_param"] == 0.5
    assert result.meta["version"] == 2


def test_run_result_includes_data_hash_and_git_info(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0 + i for i in range(6)])},
    )
    engine = _simple_engine(store, times)
    result = engine.run(output_dir=tmp_path / "runs")

    assert "data_hash" in result.meta
    assert "git_sha" in result.meta
    assert "versions" in result.meta
    assert isinstance(result.meta["versions"], dict)


def test_sessions_returns_datetime_index(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(tmp_path / "store", {"AAA": (times, [100.0] * 6)})
    engine = _simple_engine(store, times)
    sessions = engine.sessions()
    assert isinstance(sessions, pd.DatetimeIndex)
    assert len(sessions) == 6
