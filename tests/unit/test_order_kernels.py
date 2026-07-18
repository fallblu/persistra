from __future__ import annotations

import random
from datetime import UTC, datetime
from decimal import Decimal
from typing import NamedTuple

import pytest

from persistra.errors import EventSimulationError
from persistra.reference import InstrumentId
from persistra.simulation import OrderSide, OrderSpec, OrderStatus, OrderType, TimeInForce
from persistra.simulation.event_models import AmbiguityPolicy
from persistra.simulation.order_kernels import (
    eligible_reference,
    fok_capacity_rejected,
    remainder_outcome,
    unavailable_reference_outcome,
)

_AT = datetime(2025, 1, 2, tzinfo=UTC)


class _Bar(NamedTuple):
    open: str
    high: str
    low: str
    close: str


def _spec(
    order_type: OrderType,
    side: OrderSide = OrderSide.BUY,
    *,
    time_in_force: TimeInForce = TimeInForce.GTC,
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
) -> OrderSpec:
    return OrderSpec(
        "kernel-test",
        InstrumentId.new(),
        side,
        Decimal("10"),
        order_type,
        time_in_force,
        _AT,
        _AT,
        limit_price=limit_price,
        stop_price=stop_price,
    )


def test_time_in_force_outcomes_are_exact() -> None:
    assert unavailable_reference_outcome(TimeInForce.IOC) == (
        OrderStatus.CANCELLED,
        "not_executable",
    )
    assert unavailable_reference_outcome(TimeInForce.DAY) == (
        OrderStatus.EXPIRED,
        "not_executable",
    )
    assert unavailable_reference_outcome(TimeInForce.GTC) is None
    assert unavailable_reference_outcome(TimeInForce.FOK) is None

    assert remainder_outcome(TimeInForce.IOC) == (
        OrderStatus.CANCELLED,
        "remainder_terminal",
    )
    assert remainder_outcome(TimeInForce.DAY) == (
        OrderStatus.EXPIRED,
        "remainder_terminal",
    )
    assert remainder_outcome(TimeInForce.GTC) is None

    assert fok_capacity_rejected(TimeInForce.FOK, Decimal("10"), Decimal("9"))
    assert not fok_capacity_rejected(TimeInForce.FOK, Decimal("10"), Decimal("10"))
    assert not fok_capacity_rejected(TimeInForce.GTC, Decimal("10"), Decimal("0"))


def test_market_and_close_references_use_bar_boundaries() -> None:
    bar = _Bar("10", "12", "9", "11")
    rng = random.Random(0)
    conservative = AmbiguityPolicy.CONSERVATIVE
    assert eligible_reference(
        _spec(OrderType.MARKET), bar, rng, conservative
    ) == Decimal("10")
    assert eligible_reference(
        _spec(OrderType.MARKET_ON_OPEN), bar, rng, conservative
    ) == Decimal("10")
    assert eligible_reference(
        _spec(OrderType.MARKET_ON_CLOSE), bar, rng, conservative
    ) == Decimal("11")


def test_limit_references_respect_touch_and_gap_semantics() -> None:
    bar = _Bar("10", "12", "9", "11")
    rng = random.Random(0)
    conservative = AmbiguityPolicy.CONSERVATIVE
    untouched_buy = _spec(OrderType.LIMIT, limit_price=Decimal("8"))
    assert eligible_reference(untouched_buy, bar, rng, conservative) is None
    gap_buy = _spec(OrderType.LIMIT, limit_price=Decimal("10.5"))
    assert eligible_reference(gap_buy, bar, rng, conservative) == Decimal("10")
    touched_buy = _spec(OrderType.LIMIT, limit_price=Decimal("9.5"))
    assert eligible_reference(touched_buy, bar, rng, conservative) == Decimal("9.5")
    gap_sell = _spec(
        OrderType.LIMIT, OrderSide.SELL, limit_price=Decimal("9.5")
    )
    assert eligible_reference(gap_sell, bar, rng, conservative) == Decimal("10")
    touched_sell = _spec(
        OrderType.LIMIT, OrderSide.SELL, limit_price=Decimal("11.5")
    )
    assert eligible_reference(touched_sell, bar, rng, conservative) == Decimal("11.5")


def test_stop_and_stop_limit_references_follow_ambiguity_policy() -> None:
    bar = _Bar("10", "12", "9", "11")
    rng = random.Random(0)
    conservative = AmbiguityPolicy.CONSERVATIVE
    dormant = _spec(OrderType.STOP, stop_price=Decimal("13"))
    assert eligible_reference(dormant, bar, rng, conservative) is None
    triggered_buy = _spec(OrderType.STOP, stop_price=Decimal("11"))
    assert eligible_reference(triggered_buy, bar, rng, conservative) == Decimal("11")
    triggered_sell = _spec(
        OrderType.STOP, OrderSide.SELL, stop_price=Decimal("9.5")
    )
    assert eligible_reference(triggered_sell, bar, rng, conservative) == Decimal("9.5")

    ambiguous = _spec(
        OrderType.STOP_LIMIT,
        stop_price=Decimal("11"),
        limit_price=Decimal("9.5"),
    )
    assert eligible_reference(ambiguous, bar, rng, conservative) is None
    with pytest.raises(EventSimulationError):
        eligible_reference(
            ambiguous, bar, rng, AmbiguityPolicy.REJECT_AMBIGUOUS
        )
    randomized = {
        eligible_reference(
            ambiguous,
            _Bar("10", "12", "9", "11"),
            random.Random(seed),
            AmbiguityPolicy.SEEDED_RANDOMIZED,
        )
        for seed in range(8)
    }
    assert randomized == {None, Decimal("9.5")}
    limit_never_touched = _spec(
        OrderType.STOP_LIMIT,
        stop_price=Decimal("11"),
        limit_price=Decimal("8"),
    )
    assert eligible_reference(limit_never_touched, bar, rng, conservative) is None
