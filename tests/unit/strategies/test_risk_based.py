from __future__ import annotations

from persistra import Engine, Portfolio
from persistra.strategies.risk_based import VolTargetedEqualWeight


def test_vol_targeted_equal_weight_runs(tiny_store):
    result = Engine(
        data=tiny_store,
        strategy=VolTargetedEqualWeight(annual_vol=0.1, lookback=3),
        portfolio=Portfolio(initial_capital=1_000_000.0),
        start="2022-01-03",
        end="2022-01-11",
    ).run()
    assert result.equity_curve.shape[0] >= 1


def test_vol_targeted_equal_weight_rejects_bad_params():
    import pytest

    with pytest.raises(ValueError, match="annual_vol"):
        VolTargetedEqualWeight(annual_vol=0.0)
    with pytest.raises(ValueError, match="lookback"):
        VolTargetedEqualWeight(lookback=1)
