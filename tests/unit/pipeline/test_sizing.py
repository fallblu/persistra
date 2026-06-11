import math

import pytest

from persistra.core.state import PortfolioState
from persistra.pipeline.sizing import EqualWeight, FixedDollar, VolTarget

_STATE = PortfolioState(
    equity=1000.0, cash=1000.0, positions={}, weights={}, gross_exposure=0.0, net_exposure=0.0
)


def test_equal_weight_splits_target_gross_and_keeps_sign(populated_history):
    out = EqualWeight(target_gross=1.0).size({"AAA": 1.0, "BBB": -1.0}, _STATE, populated_history)
    assert out["AAA"] == pytest.approx(0.5)
    assert out["BBB"] == pytest.approx(-0.5)


def test_equal_weight_empty_when_all_zero(populated_history):
    assert EqualWeight().size({"AAA": 0.0}, _STATE, populated_history) == {}


def test_fixed_dollar_is_fraction_of_equity(populated_history):
    out = FixedDollar(dollars_per_position=250.0).size({"AAA": 1.0}, _STATE, populated_history)
    assert out["AAA"] == pytest.approx(250.0 / 1000.0)


def test_voltarget_inversely_weights_higher_vol(populated_history):
    # AAA is far more volatile than BBB in the fixture -> smaller magnitude.
    out = VolTarget(annual_vol=0.10, lookback=10).size(
        {"AAA": 1.0, "BBB": 1.0}, _STATE, populated_history
    )
    assert abs(out["AAA"]) < abs(out["BBB"])
    assert math.copysign(1, out["AAA"]) == 1.0
