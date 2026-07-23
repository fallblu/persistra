"""This module contains the deterministic event-simulation identities and immutable requests."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId
from persistra.errors import EventSimulationRequestError

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.accounting import AccountingBookId, AccountingOpening
    from persistra.market import BarSpecRef
    from persistra.portfolio.safety_models import (
        DecisionInputManifestRef,
        UnsafeDecisionInputOverride,
    )
    from persistra.reference import AsOfContext, InstrumentId
    from persistra.simulation.models import RunRecordId


class EventSimulationId(EntityId):
    KIND: ClassVar[str] = "event_simulation"


class OrderId(EntityId):
    KIND: ClassVar[str] = "order"


class FillId(EntityId):
    KIND: ClassVar[str] = "fill"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    MARKET_ON_OPEN = "market_on_open"
    MARKET_ON_CLOSE = "market_on_close"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderStatus(StrEnum):
    CREATED = "created"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    ACTIVE = "active"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    REJECTED = "rejected"


class AmbiguityPolicy(StrEnum):
    CONSERVATIVE = "conservative"
    OPTIMISTIC = "optimistic"
    SEEDED_RANDOMIZED = "seeded_randomized"
    REJECT_AMBIGUOUS = "reject_ambiguous"


@dataclass(frozen=True, slots=True)
class OrderSpec:
    client_key: str
    instrument_id: InstrumentId
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce
    submitted_at: datetime
    eligibility_at: datetime
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    cancel_at: datetime | None = None
    replaces_client_key: str | None = None

    def __post_init__(self) -> None:
        limit_required = self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}
        stop_required = self.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}
        if (
            not self.client_key
            or self.quantity <= 0
            or self.submitted_at.tzinfo is None
            or self.eligibility_at.tzinfo is None
            or self.eligibility_at < self.submitted_at
            or (self.limit_price is not None) != limit_required
            or (self.stop_price is not None) != stop_required
            or (self.limit_price is not None and self.limit_price <= 0)
            or (self.stop_price is not None and self.stop_price <= 0)
            or (self.cancel_at is not None and self.cancel_at < self.submitted_at)
            or (
                self.order_type in {OrderType.MARKET_ON_OPEN, OrderType.MARKET_ON_CLOSE}
                and self.time_in_force in {TimeInForce.IOC, TimeInForce.FOK}
            )
        ):
            raise EventSimulationRequestError("event order specification is invalid")


@dataclass(frozen=True, slots=True)
class EventExecutionPolicy:
    ambiguity: AmbiguityPolicy = AmbiguityPolicy.CONSERVATIVE
    participation_limit: Decimal = Decimal("0.10")
    spread_bps: Decimal = Decimal(0)
    slippage_bps: Decimal = Decimal(0)
    impact_bps: Decimal = Decimal(0)
    fee_bps: Decimal = Decimal(0)
    seed: int = 0
    short_borrow_quantity: Decimal = Decimal(0)
    settlement_sessions: int = 1

    def __post_init__(self) -> None:
        if (
            not Decimal(0) < self.participation_limit <= 1
            or min(
                self.spread_bps,
                self.slippage_bps,
                self.impact_bps,
                self.fee_bps,
                self.short_borrow_quantity,
            )
            < 0
            or self.settlement_sessions < 0
        ):
            raise EventSimulationRequestError("event execution policy is invalid")


@dataclass(frozen=True, slots=True)
class EventSimulationRequest:
    market_context: AsOfContext
    market_database: str
    bar_spec: BarSpecRef
    decision_inputs: DecisionInputManifestRef
    opening: AccountingOpening
    orders: tuple[OrderSpec, ...]
    horizon_at: datetime
    execution: EventExecutionPolicy = EventExecutionPolicy()
    unsafe_override: UnsafeDecisionInputOverride | None = None

    def __post_init__(self) -> None:
        keys = [order.client_key for order in self.orders]
        boundaries = [
            boundary
            for order in self.orders
            for boundary in (
                order.submitted_at,
                order.eligibility_at,
                order.cancel_at,
            )
            if boundary is not None
        ]
        known: set[str] = set()
        replacements_valid = True
        for order in sorted(self.orders, key=lambda item: item.submitted_at):
            if (
                order.replaces_client_key is not None
                and order.replaces_client_key not in known
            ):
                replacements_valid = False
            known.add(order.client_key)
        if (
            not self.market_database
            or not self.orders
            or self.horizon_at.tzinfo is None
            or self.horizon_at <= self.opening.effective_at
            or any(self.horizon_at <= boundary for boundary in boundaries)
            or len(keys) != len(set(keys))
            or not replacements_valid
        ):
            raise EventSimulationRequestError("event simulation request is invalid")


@dataclass(frozen=True, slots=True)
class EventSimulationPlan:
    request: EventSimulationRequest
    execution_content_id: ContentId


@dataclass(frozen=True, slots=True)
class EventRunRef:
    event_simulation_id: EventSimulationId
    run_record_id: RunRecordId
    accounting_book_id: AccountingBookId
    execution_content_id: ContentId
    result_manifest_content_id: ContentId
    event_count: int
    order_count: int
    fill_count: int
