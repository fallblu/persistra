"""Tests for core/artifacts.py — save/load round-trips and error paths."""

from __future__ import annotations

import pandas as pd
import pytest

from persistra.core.artifacts import IncompleteRunError, load, save
from persistra.core.result import Result


def _make_result(n: int = 3) -> Result:
    idx = pd.bdate_range("2022-01-03", periods=n)
    ec = pd.DataFrame(
        {
            "equity": [1_000.0 + i * 10 for i in range(n)],
            "cash": [800.0] * n,
            "gross_exposure": [0.2] * n,
            "net_exposure": [0.2] * n,
        },
        index=idx,
    )
    trades = pd.DataFrame(
        {
            "timestamp": idx[:1],
            "symbol": ["AAA"],
            "quantity": [5.0],
            "fill_price": [100.0],
            "commission": [0.0],
        }
    )
    positions = pd.DataFrame({"bar_time": idx[:1], "symbol": ["AAA"], "weight": [0.2]})
    return Result(equity_curve=ec, trades=trades, positions=positions, meta={"n_sessions": n})


def test_save_creates_expected_files(tmp_path):
    result = _make_result()
    run_dir = tmp_path / "run001"
    save(result, run_dir)
    assert (run_dir / "equity_curve.parquet").exists()
    assert (run_dir / "trades.parquet").exists()
    assert (run_dir / "positions.parquet").exists()
    assert (run_dir / "meta.json").exists()
    assert (run_dir / "summary.json").exists()


def test_save_and_load_round_trip(tmp_path):
    original = _make_result()
    run_dir = tmp_path / "run002"
    save(original, run_dir)
    restored = load(run_dir)

    assert len(restored.equity_curve) == len(original.equity_curve)
    assert len(restored.trades) == len(original.trades)
    assert restored.meta["n_sessions"] == 3
    # load() adds run_dir to meta
    assert "run_dir" in restored.meta


def test_load_raises_on_missing_summary(tmp_path):
    incomplete = tmp_path / "run_incomplete"
    incomplete.mkdir()
    with pytest.raises(IncompleteRunError, match="summary.json"):
        load(incomplete)


def test_save_strips_run_dir_from_written_meta(tmp_path):
    """run_dir key must not be written to disk (it's injected on load)."""
    import json

    result = _make_result()
    result.meta["run_dir"] = "/some/old/path"
    run_dir = tmp_path / "run003"
    save(result, run_dir)
    with open(run_dir / "meta.json") as f:
        written = json.load(f)
    assert "run_dir" not in written


def test_summary_json_contains_metrics(tmp_path):
    import json

    result = _make_result(5)
    run_dir = tmp_path / "run004"
    save(result, run_dir)
    with open(run_dir / "summary.json") as f:
        summary = json.load(f)
    assert "metrics" in summary
    assert "sharpe" in summary["metrics"]


def test_save_load_roundtrips_diagnostics(tmp_path):
    import pandas as pd

    from persistra.core.artifacts import load, save
    from persistra.core.result import Result

    diag = pd.DataFrame(
        [
            {
                "bar_time": pd.Timestamp("2022-01-03"),
                "timeframe": "1d",
                "name": "z",
                "symbol": "AAA",
                "value": 1.0,
            }
        ]
    )
    eq = pd.DataFrame({"equity": [1.0]}, index=[pd.Timestamp("2022-01-03")])
    result = Result(eq, pd.DataFrame(), pd.DataFrame(), diagnostics=diag)
    save(result, tmp_path / "run")
    assert (tmp_path / "run" / "diagnostics.parquet").exists()
    reloaded = load(tmp_path / "run")
    assert not reloaded.diagnostics.empty
    assert reloaded.diagnostic("z").loc[pd.Timestamp("2022-01-03"), "AAA"] == 1.0


def test_load_without_diagnostics_file_yields_empty_frame(tmp_path):
    import pandas as pd

    from persistra.core.artifacts import load, save
    from persistra.core.result import Result

    eq = pd.DataFrame({"equity": [1.0]}, index=[pd.Timestamp("2022-01-03")])
    result = Result(eq, pd.DataFrame(), pd.DataFrame())  # empty diagnostics
    save(result, tmp_path / "run")
    assert not (tmp_path / "run" / "diagnostics.parquet").exists()
    reloaded = load(tmp_path / "run")
    assert reloaded.diagnostics.empty
    assert list(reloaded.diagnostics.columns) == [
        "bar_time",
        "timeframe",
        "name",
        "symbol",
        "value",
    ]
