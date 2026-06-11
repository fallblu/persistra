from __future__ import annotations

from persistra import Engine, Portfolio
from persistra.strategies.trend import SMACrossover


def _run(store, strategy, start="2022-01-03", end="2022-01-11"):
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start=start,
        end=end,
    ).run()


def test_sma_crossover_rejects_fast_ge_slow():
    import pytest

    with pytest.raises(ValueError):
        SMACrossover(fast=10, slow=10)


def test_sma_crossover_records_signals(tiny_store):
    result = _run(tiny_store, SMACrossover(fast=2, slow=3))
    names = set(result.diagnostics["name"]) if not result.diagnostics.empty else set()
    assert {"sma_fast", "sma_slow", "spread"} <= names


def test_sma_crossover_warmup_matches_slow():
    assert SMACrossover(fast=2, slow=5).warmup == 5
