import pandas as pd

from persistra.viz.benchmark import buy_and_hold_benchmark, equal_weight_benchmark
from tests.conftest import build_store


def test_equal_weight_benchmark_is_split_adjusted(tmp_path):
    # AAA price halves 100 -> 50 on a 2-for-1 split; split-adjusted it is flat.
    times = list(pd.bdate_range("2022-01-03", periods=5))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0, 100.0, 50.0, 50.0, 50.0])},
        actions=[
            {
                "date": str(times[2].date()),
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 2.0,
            }
        ],
    )
    s = equal_weight_benchmark(store, ["AAA"], times[0], times[-1])
    moves = s.pct_change().dropna().abs()
    assert (moves < 1e-9).all()  # split cliff removed -> no spurious move


def test_buy_and_hold_benchmark_is_split_adjusted(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=5))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0, 100.0, 50.0, 50.0, 50.0])},
        actions=[
            {
                "date": str(times[2].date()),
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 2.0,
            }
        ],
    )
    s = buy_and_hold_benchmark(store, "AAA", times[0], times[-1])
    moves = s.pct_change().dropna().abs()
    assert (moves < 1e-9).all()


def test_equal_weight_benchmark_no_split_cliffs_on_real_data(sample_data_dir):
    from persistra.data.store import ParquetMarketData, UniverseQuery

    store = ParquetMarketData(sample_data_dir)
    syms = store.universe(UniverseQuery(pd.Timestamp("2022-06-01"), pd.Timestamp("2022-08-31")))
    s = equal_weight_benchmark(store, syms, pd.Timestamp("2022-06-01"), pd.Timestamp("2022-08-31"))
    # Without split adjustment, AMZN/GOOGL 20:1 splits produce ~9-10% basket cliffs.
    assert s.pct_change().abs().max() < 0.06


def test_equal_weight_benchmark_accumulates_multiple_splits(tmp_path):
    # AAA: 2-for-1 on day 2 (100 -> 50), then 3-for-1 on day 4 (50 -> ~16.667).
    # Each ex-date close is exactly the prior close divided by the ratio, so the
    # split-adjusted series is flat (no real price change).
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(
        tmp_path / "store",
        {"AAA": (times, [100.0, 100.0, 50.0, 50.0, 50.0 / 3.0, 50.0 / 3.0])},
        actions=[
            {
                "date": str(times[2].date()),
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 2.0,
            },
            {
                "date": str(times[4].date()),
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 3.0,
            },
        ],
    )
    s = equal_weight_benchmark(store, ["AAA"], times[0], times[-1])
    moves = s.pct_change().dropna().abs()
    assert (moves < 1e-9).all()
