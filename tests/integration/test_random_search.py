"""Tests for experiments/random.py — random_search + _sample_one."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from persistra import Engine, Portfolio
from persistra.experiments.random import _sample_one, random_search
from persistra.experiments.sweep_result import SweepResult
from tests.conftest import EqualWeightRebalance, build_store

# ---------------------------------------------------------------------------
# _sample_one
# ---------------------------------------------------------------------------


def test_sample_one_fixed_scalar():
    rng = np.random.default_rng(0)
    params = _sample_one({"lr": 0.001, "hidden": 64}, rng)
    assert params["lr"] == 0.001
    assert params["hidden"] == 64


def test_sample_one_categorical_list():
    rng = np.random.default_rng(42)
    choices = [1, 2, 3, 4, 5]
    params = _sample_one({"x": choices}, rng)
    assert params["x"] in choices


def test_sample_one_keys_sorted():
    """_sample_one iterates keys in sorted order — output should contain all."""
    rng = np.random.default_rng(0)
    params = _sample_one({"z": 10, "a": 20, "m": 30}, rng)
    assert set(params.keys()) == {"z", "a", "m"}


def test_sample_one_scipy_dist():
    """A scipy.stats-style distribution (has .rvs) should be sampled."""

    class FakeDist:
        def rvs(self, random_state=None):
            return 3.14

    rng = np.random.default_rng(0)
    params = _sample_one({"p": FakeDist()}, rng)
    assert params["p"] == pytest.approx(3.14)


# ---------------------------------------------------------------------------
# random_search
# ---------------------------------------------------------------------------


def _factory(params):
    return EqualWeightRebalance()


def test_random_search_returns_sweep_result(tmp_path):
    times = list(pd.bdate_range("2022-01-03", periods=8))
    store = build_store(tmp_path / "store", {"AAA": (times, [100.0 + i for i in range(8)])})

    def builder(strategy):
        return Engine(
            data=store,
            strategy=strategy,
            portfolio=Portfolio(initial_capital=1_000_000.0),
            start=times[0].strftime("%Y-%m-%d"),
            end=times[-1].strftime("%Y-%m-%d"),
        )

    sweep = random_search(
        _factory,
        {"dummy": [1, 2, 3]},
        n_iter=2,
        engine_builder=builder,
        n_jobs=1,
        seed=0,
    )
    assert isinstance(sweep, SweepResult)
    assert len(sweep.results) == 2
    assert len(sweep.params) == 2


def test_random_search_seeded_reproducibility(tmp_path):
    """Same seed → same param draw."""
    times = list(pd.bdate_range("2022-01-03", periods=6))
    store = build_store(tmp_path / "store", {"AAA": (times, [100.0] * 6)})

    def builder(strategy):
        return Engine(
            data=store,
            strategy=strategy,
            portfolio=Portfolio(initial_capital=1_000_000.0),
            start=times[0].strftime("%Y-%m-%d"),
            end=times[-1].strftime("%Y-%m-%d"),
        )

    sweep1 = random_search(
        _factory, {"x": [1, 2, 3, 4, 5]}, n_iter=3, engine_builder=builder, seed=42
    )
    sweep2 = random_search(
        _factory, {"x": [1, 2, 3, 4, 5]}, n_iter=3, engine_builder=builder, seed=42
    )
    assert sweep1.params == sweep2.params
