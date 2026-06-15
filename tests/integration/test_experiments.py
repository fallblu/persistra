import pandas as pd

from persistra import Engine, ParquetMarketData, Portfolio
from persistra.experiments.grid import enumerate_grid, grid_search, resolve_sweep_dir
from persistra.experiments.walk_forward import enumerate_folds, walk_forward_grid_search
from tests.conftest import EqualWeightRebalance


def test_enumerate_grid_sorted_cartesian():
    grid = enumerate_grid({"b": [1, 2], "a": ["x"]})
    assert grid == [{"a": "x", "b": 1}, {"a": "x", "b": 2}]


def test_enumerate_grid_empty_yields_single_empty_cell():
    assert enumerate_grid({}) == [{}]


def test_enumerate_folds_non_overlapping():
    sessions = pd.DatetimeIndex(pd.bdate_range("2022-01-03", periods=20))
    folds = enumerate_folds(sessions, train_window=5, test_window=5, step=5)
    assert len(folds) == 3  # tests at [5:10], [10:15], [15:20]
    for start, end in folds:
        assert start <= end


def test_resolve_sweep_dir_generates_unique_inspectable_paths(tmp_path):
    paths = [resolve_sweep_dir(tmp_path) for _ in range(20)]

    assert len(set(paths)) == len(paths)
    for path in paths:
        assert path is not None
        assert path.parent == tmp_path
        assert path.is_dir()
        assert path.name.startswith("sweep_20")
        assert len(path.name.rsplit("-", maxsplit=1)[-1]) == 6


def test_resolve_sweep_dir_returns_none_without_output_dir():
    assert resolve_sweep_dir(None) is None


def _factory(params):
    return EqualWeightRebalance()


def test_grid_search_deterministic_on_sample_data(sample_data_dir):
    def builder(strategy):
        return Engine(
            data=ParquetMarketData(sample_data_dir),
            strategy=strategy,
            portfolio=Portfolio(initial_capital=1_000_000.0),
            start="2022-01-03",
            end="2022-06-30",
        )

    sweep = grid_search(_factory, {"dummy": [1, 2]}, engine_builder=builder, n_jobs=1)
    df = sweep.summary_dataframe()
    assert len(df) == 2
    # Same strategy + same data -> identical equity end-points across cells.
    assert (
        sweep.results[0].equity_curve["equity"].iloc[-1]
        == (sweep.results[1].equity_curve["equity"].iloc[-1])
    )


def test_grid_search_forwards_builder_kwargs(sample_data_dir):
    seen: list[tuple[str, str]] = []

    def builder(strategy, *, start="2022-01-03", end="2022-06-30"):
        seen.append((str(start), str(end)))
        return Engine(
            data=ParquetMarketData(sample_data_dir),
            strategy=strategy,
            portfolio=Portfolio(initial_capital=1_000_000.0),
            start=start,
            end=end,
        )

    grid_search(
        _factory,
        {"dummy": [1]},
        engine_builder=builder,
        n_jobs=1,
        builder_kwargs={"start": "2022-02-01", "end": "2022-02-28"},
    )

    assert seen == [("2022-02-01", "2022-02-28")]


def test_walk_forward_grid_search_selects_and_trims(sample_data_dir):
    def builder(strategy, *, start="2022-01-03", end="2022-04-29"):
        return Engine(
            data=ParquetMarketData(sample_data_dir),
            strategy=strategy,
            portfolio=Portfolio(initial_capital=1_000_000.0),
            start=start,
            end=end,
        )

    result = walk_forward_grid_search(
        _factory,
        {"dummy": [1, 2]},
        engine_builder=builder,
        train_window=10,
        test_window=5,
        step=20,
        n_jobs=1,
    )

    assert result.folds
    assert all(
        params in ({"dummy": 1}, {"dummy": 2}) for *_prefix, params, _sweep, _run in result.folds
    )
    assert len(result.test_results()) == len(result.folds)
    selected = result.selected_params_dataframe()
    assert len(selected) == len(result.folds)
    assert "param_dummy" in selected.columns
    for (_train_start, test_start, test_end, _params, _sweep, _run), test_result in zip(
        result.folds,
        result.test_results(),
        strict=True,
    ):
        assert test_result.equity_curve.index.min() >= test_start
        assert test_result.equity_curve.index.max() <= test_end
