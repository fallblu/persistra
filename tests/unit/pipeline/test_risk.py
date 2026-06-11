import pytest

from persistra.pipeline.risk import (
    CashFloor,
    MaxGrossExposure,
    MaxNetExposure,
    MaxPositionSize,
)


def test_cash_floor_scales_down_when_over_invested():
    out = CashFloor(min_cash=0.05).project({"A": 0.6, "B": 0.6})  # gross 1.2 > 0.95
    assert sum(abs(v) for v in out.values()) == pytest.approx(0.95)


def test_cash_floor_passthrough_when_within_limit():
    w = {"A": 0.4, "B": 0.4}
    assert CashFloor(min_cash=0.05).project(w) == w


def test_cash_floor_rejects_bad_min_cash():
    with pytest.raises(ValueError):
        CashFloor(min_cash=1.0)


def test_max_gross_exposure_caps_gross():
    out = MaxGrossExposure(limit=1.0).project({"A": 1.0, "B": -1.0})  # gross 2.0
    assert sum(abs(v) for v in out.values()) == pytest.approx(1.0)


def test_max_net_exposure_clamps_band():
    out = MaxNetExposure(low=-0.2, high=0.2).project({"A": 0.6, "B": 0.4})  # net 1.0
    assert sum(out.values()) == pytest.approx(0.2)


def test_max_net_exposure_rejects_inverted_band():
    with pytest.raises(ValueError):
        MaxNetExposure(low=0.5, high=-0.5)


def test_max_position_size_clips_each_weight():
    out = MaxPositionSize(limit=0.3).project({"A": 0.5, "B": -0.5, "C": 0.1})
    assert out == {"A": pytest.approx(0.3), "B": pytest.approx(-0.3), "C": pytest.approx(0.1)}
