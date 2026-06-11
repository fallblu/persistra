import math

import pandas as pd
import pytest

from persistra.core.events import BarCloseEvent, OrderEvent, OrderType
from persistra.core.execution import (
    FixedCommission,
    IdealFill,
    ProportionalSlippage,
    VolumeImpact,
)

T = pd.Timestamp("2023-01-03")


def _bar(close=100.0, volume=10_000.0):
    return BarCloseEvent(
        timestamp=T, symbol="AAA", open=close, high=close, low=close, close=close, volume=volume
    )


def _order(qty):
    return OrderEvent(timestamp=T, symbol="AAA", order_type=OrderType.MOC, quantity=qty)


def test_ideal_fill_at_close_zero_commission():
    fill = IdealFill().fill(_order(10), _bar(100.0))
    assert fill.fill_price == 100.0
    assert fill.commission == 0.0
    assert fill.quantity == 10


def test_fixed_commission_is_rate_times_notional():
    fill = FixedCommission(rate=0.001).fill(_order(-10), _bar(100.0))
    assert fill.fill_price == 100.0
    assert fill.commission == pytest.approx(0.001 * abs(-10 * 100.0))


def test_fixed_commission_rejects_negative_rate():
    with pytest.raises(ValueError):
        FixedCommission(rate=-0.1)


def test_proportional_slippage_adverse_direction():
    buy = ProportionalSlippage(bps=10.0).fill(_order(10), _bar(100.0))
    sell = ProportionalSlippage(bps=10.0).fill(_order(-10), _bar(100.0))
    assert buy.fill_price == pytest.approx(100.0 * (1 + 0.001))
    assert sell.fill_price == pytest.approx(100.0 * (1 - 0.001))


def test_volume_impact_sqrt_and_zero_volume_fallback():
    f = VolumeImpact(impact=0.01).fill(_order(10), _bar(100.0, volume=10_000.0))
    assert f.fill_price == pytest.approx(100.0 + 0.01 * math.sqrt(10_000.0))
    f0 = VolumeImpact(impact=0.01).fill(_order(10), _bar(100.0, volume=0.0))
    assert f0.fill_price == 100.0
