"""This module contains the pure per-bar order decision kernels for the bounded event engine."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from persistra.errors import EventSimulationError
from persistra.simulation.event_models import (
    AmbiguityPolicy,
    OrderSide,
    OrderSpec,
    OrderStatus,
    OrderType,
    TimeInForce,
)

if TYPE_CHECKING:
    import random


def unavailable_reference_outcome(
    time_in_force: TimeInForce,
) -> tuple[OrderStatus, str] | None:
    """Return the terminal outcome for an order that has a bar reference that cannot execute."""
    if time_in_force is TimeInForce.IOC:
        return (OrderStatus.CANCELLED, "not_executable")
    if time_in_force is TimeInForce.DAY:
        return (OrderStatus.EXPIRED, "not_executable")
    return None


def fok_capacity_rejected(
    time_in_force: TimeInForce,
    requested: Decimal,
    capacity: Decimal,
) -> bool:
    """Return true if causal bar capacity must cancel a fill-or-kill order."""
    return time_in_force is TimeInForce.FOK and capacity < requested


def remainder_outcome(
    time_in_force: TimeInForce,
) -> tuple[OrderStatus, str] | None:
    """Terminal outcome for an unfilled remainder after the bar executes."""
    if time_in_force is TimeInForce.IOC:
        return (OrderStatus.CANCELLED, "remainder_terminal")
    if time_in_force is TimeInForce.DAY:
        return (OrderStatus.EXPIRED, "remainder_terminal")
    return None


def eligible_reference(
    spec: OrderSpec,
    bar: Any,
    rng: random.Random,
    ambiguity: AmbiguityPolicy,
) -> Decimal | None:
    """Return the reference price for one complete bar with the coarse observation clock."""
    open_price = Decimal(str(bar.open))
    high = Decimal(str(bar.high))
    low = Decimal(str(bar.low))
    close = Decimal(str(bar.close))
    if spec.order_type in {OrderType.MARKET, OrderType.MARKET_ON_OPEN}:
        return open_price
    if spec.order_type is OrderType.MARKET_ON_CLOSE:
        return close
    if spec.order_type is OrderType.LIMIT:
        assert spec.limit_price is not None
        touched = (
            low <= spec.limit_price
            if spec.side is OrderSide.BUY
            else high >= spec.limit_price
        )
        if not touched:
            return None
        if spec.side is OrderSide.BUY and open_price <= spec.limit_price:
            return open_price
        if spec.side is OrderSide.SELL and open_price >= spec.limit_price:
            return open_price
        return spec.limit_price
    assert spec.stop_price is not None
    triggered = (
        high >= spec.stop_price
        if spec.side is OrderSide.BUY
        else low <= spec.stop_price
    )
    if not triggered:
        return None
    if spec.order_type is OrderType.STOP:
        return max(open_price, spec.stop_price) if spec.side is OrderSide.BUY else min(
            open_price, spec.stop_price
        )
    assert spec.limit_price is not None
    limit_touched = (
        low <= spec.limit_price
        if spec.side is OrderSide.BUY
        else high >= spec.limit_price
    )
    if not limit_touched:
        return None
    if ambiguity is AmbiguityPolicy.CONSERVATIVE:
        return None
    if ambiguity is AmbiguityPolicy.REJECT_AMBIGUOUS:
        raise EventSimulationError("stop-limit path is ambiguous")
    if ambiguity is AmbiguityPolicy.SEEDED_RANDOMIZED and not rng.choice((False, True)):
        return None
    return spec.limit_price
