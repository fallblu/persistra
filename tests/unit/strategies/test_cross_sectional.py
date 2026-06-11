from __future__ import annotations

from persistra import Engine, Portfolio
from persistra.pipeline import TopN
from persistra.strategies.cross_sectional import CrossSectionalMomentum


def _run(store, strategy):
    return Engine(
        data=store,
        strategy=strategy,
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()


def test_momentum_records_score(tiny_store):
    strat = CrossSectionalMomentum(lookback=3, skip=0, allocation=TopN(n=1, long_short=False))
    result = _run(tiny_store, strat)
    assert "momentum" in set(result.diagnostics["name"])


def test_momentum_warmup_covers_lookback():
    strat = CrossSectionalMomentum(lookback=20, skip=5)
    assert strat.warmup >= 25


def test_momentum_rejects_invalid_lookback():
    import pytest

    with pytest.raises(ValueError, match="lookback"):
        CrossSectionalMomentum(lookback=1)


def test_momentum_rejects_negative_skip():
    import pytest

    with pytest.raises(ValueError, match="skip"):
        CrossSectionalMomentum(skip=-1)


def test_mean_reversion_records_zscore(tiny_store):
    from persistra.strategies.cross_sectional import MeanReversion

    strat = MeanReversion(lookback=3)
    result = _run(tiny_store, strat)
    assert "zscore" in set(result.diagnostics["name"])
