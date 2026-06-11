from __future__ import annotations

import pandas as pd

from persistra.viz.benchmark import buy_and_hold_benchmark, equal_weight_benchmark

START = pd.Timestamp("2022-01-03")
END = pd.Timestamp("2022-01-11")


def test_buy_and_hold_benchmark_is_wealth_index(tiny_store):
    s = buy_and_hold_benchmark(tiny_store, "AAA", START, END, initial=1.0)
    assert isinstance(s, pd.Series)
    assert s.iloc[0] == 1.0
    assert (s > 0).all()


def test_equal_weight_benchmark_basket(tiny_store):
    s = equal_weight_benchmark(tiny_store, ["AAA", "BBB", "CCC"], START, END, initial=100.0)
    assert isinstance(s, pd.Series)
    assert abs(s.iloc[0] - 100.0) < 1e-9
    assert len(s) >= 2


def test_equal_weight_benchmark_empty_symbols(tiny_store):
    s = equal_weight_benchmark(tiny_store, [], START, END)
    assert s.empty
