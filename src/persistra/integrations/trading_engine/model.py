"""Typed policies, scenario values, and replay results for Trading Engine."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import (
    decimal_micros,
    decimal_value,
    execution_quantity,
    identifier,
    quantity_value,
)

if TYPE_CHECKING:
    from pathlib import Path

    from persistra.integrations.trading_engine.strategy import StrategyRunResult

type SourceTimestampPosition = Literal["start", "end"]
type EquityBasis = Literal["current_marked_equity"]
type ReferencePrice = Literal["decision_close"]
type QuantityRounding = Literal["down_to_lot"]
type ExecutionModel = Literal["completed_bar_v1"]
type Side = Literal["buy", "sell"]
type OrderKind = Literal["market", "limit"]

TRADING_ENGINE_CONTRACT_VERSION: Final = "3"
_MAX_INTERNAL_EVENTS: Final = 100_000
_MAX_CATALOG_INSTRUMENTS: Final = 4_096
_MAX_INTENTS_PER_BATCH: Final = 4_096


@dataclass(frozen=True, slots=True)
class EngineResourceLimits:
    """Versioned inclusive resource ceilings advertised by an engine."""

    version: str
    scenario_record_bytes: int
    strategy_message_bytes: int
    internal_events: int
    catalog_instruments: int
    intents_per_batch: int
    artifact_record_bytes: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", identifier(self.version, name="resource limit version"))
        for name in (
            "scenario_record_bytes",
            "strategy_message_bytes",
            "internal_events",
            "catalog_instruments",
            "intents_per_batch",
            "artifact_record_bytes",
        ):
            value = cast("object", getattr(self, name))
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class EngineCapabilities:
    """Machine-readable compatibility surface advertised by an engine executable."""

    engine_version: str
    scenario_contract_versions: tuple[str, ...]
    journal_contract_versions: tuple[str, ...]
    scenario_formats: tuple[str, ...]
    journal_formats: tuple[str, ...]
    execution_models: tuple[str, ...]
    strategy_protocol_versions: tuple[str, ...]
    resource_limits: EngineResourceLimits | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "engine_version",
            identifier(self.engine_version, name="engine_version"),
        )
        for name in (
            "scenario_contract_versions",
            "journal_contract_versions",
            "scenario_formats",
            "journal_formats",
            "execution_models",
            "strategy_protocol_versions",
        ):
            raw = cast("object", getattr(self, name))
            if not isinstance(raw, tuple):
                raise TypeError(f"{name} must be a tuple")
            values = tuple(identifier(item, name=name) for item in cast("tuple[object, ...]", raw))
            if not values:
                raise ValueError(f"{name} must not be empty")
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must not contain duplicates")
            object.__setattr__(self, name, values)
        resource_limits = cast("object", self.resource_limits)
        if resource_limits is not None and not isinstance(resource_limits, EngineResourceLimits):
            raise TypeError("resource_limits must be EngineResourceLimits or None")


@dataclass(frozen=True, slots=True)
class BarClockPolicy:
    """Map one intraday source label into causal engine timestamps."""

    source_timestamp_position: SourceTimestampPosition
    bar_duration: timedelta
    availability_delay: timedelta
    receipt_delay: timedelta

    def __post_init__(self) -> None:
        if self.source_timestamp_position not in {"start", "end"}:
            raise ValueError("source_timestamp_position must be start or end")
        if self.bar_duration <= timedelta(0):
            raise ValueError("bar_duration must be positive")
        if self.availability_delay < timedelta(0):
            raise ValueError("availability_delay must be nonnegative")
        if self.receipt_delay < timedelta(0):
            raise ValueError("receipt_delay must be nonnegative")


@dataclass(frozen=True, slots=True)
class SizingPolicy:
    """Document the engine-owned portfolio target sizing rules."""

    equity_basis: EquityBasis = "current_marked_equity"
    reference_price: ReferencePrice = "decision_close"
    quantity_rounding: QuantityRounding = "down_to_lot"

    def __post_init__(self) -> None:
        if self.equity_basis != "current_marked_equity":
            raise ValueError("only the current_marked_equity basis is supported")
        if self.reference_price != "decision_close":
            raise ValueError("only the decision_close reference price is supported")
        if self.quantity_rounding != "down_to_lot":
            raise ValueError("only down_to_lot quantity rounding is supported")


@dataclass(frozen=True, slots=True)
class CashBalance:
    """One explicit initial cash ledger balance."""

    currency: str
    amount: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", identifier(self.currency, name="currency"))
        object.__setattr__(
            self,
            "amount",
            decimal_value(self.amount, name="amount", nonnegative=True),
        )


@dataclass(frozen=True, slots=True)
class FxRate:
    """One currency-to-base mark for a market slice."""

    currency: str
    rate: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", identifier(self.currency, name="currency"))
        object.__setattr__(
            self,
            "rate",
            decimal_value(self.rate, name="rate", positive=True),
        )


@dataclass(frozen=True, slots=True)
class SplitAction:
    """An exact split applied before matching its market slice."""

    action_id: str
    instrument_id: str
    numerator: int
    denominator: int
    type: Literal["split"] = field(default="split", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            identifier(self.action_id, name="action_id"),
        )
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        numerator = quantity_value(self.numerator, name="numerator", positive=True)
        denominator = quantity_value(self.denominator, name="denominator", positive=True)
        if numerator == denominator:
            raise ValueError("split ratio must change the instrument units")
        object.__setattr__(self, "numerator", numerator)
        object.__setattr__(self, "denominator", denominator)


@dataclass(frozen=True, slots=True)
class CashDividendAction:
    """A per-unit cash dividend applied before matching its market slice."""

    action_id: str
    instrument_id: str
    amount_per_unit: Decimal | str | int | float
    type: Literal["cash_dividend"] = field(default="cash_dividend", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "action_id",
            identifier(self.action_id, name="action_id"),
        )
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(
            self,
            "amount_per_unit",
            decimal_value(
                self.amount_per_unit,
                name="amount_per_unit",
                positive=True,
            ),
        )


type CorporateAction = SplitAction | CashDividendAction


@dataclass(frozen=True, slots=True)
class ExecutionInstrument:
    """Executable metadata supplied separately from research identity."""

    instrument_id: str
    symbol: str
    quote_currency: str
    tick_size: Decimal | str | int | float
    lot_size: Decimal | str | int | float = Decimal(1)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(self, "symbol", identifier(self.symbol, name="symbol"))
        object.__setattr__(
            self,
            "quote_currency",
            identifier(self.quote_currency, name="quote_currency"),
        )
        object.__setattr__(
            self,
            "tick_size",
            decimal_value(self.tick_size, name="tick_size", positive=True),
        )
        object.__setattr__(
            self,
            "lot_size",
            execution_quantity(self.lot_size, name="lot_size", positive=True),
        )


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Signed position, exposure, leverage, margin, and borrow limits."""

    max_order_quantity: Decimal | str | int | float
    max_long_position: Decimal | str | int | float
    max_short_position: Decimal | str | int | float
    max_gross_exposure: Decimal | str | int | float
    max_leverage: Decimal | str | int | float
    initial_margin_bps: int
    maintenance_margin_bps: int
    short_borrow_bps: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_order_quantity",
            execution_quantity(
                self.max_order_quantity,
                name="max_order_quantity",
                positive=True,
            ),
        )
        for name in ("max_long_position", "max_short_position"):
            object.__setattr__(
                self,
                name,
                execution_quantity(getattr(self, name), name=name, positive=True),
            )
        for name in ("max_gross_exposure", "max_leverage"):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=name, positive=True),
            )
        initial_margin = quantity_value(self.initial_margin_bps, name="initial_margin_bps")
        maintenance_margin = quantity_value(
            self.maintenance_margin_bps,
            name="maintenance_margin_bps",
        )
        short_borrow = quantity_value(self.short_borrow_bps, name="short_borrow_bps")
        if not 1 <= initial_margin <= 10_000:
            raise ValueError("initial_margin_bps must be between 1 and 10000")
        if not 1 <= maintenance_margin <= 10_000:
            raise ValueError("maintenance_margin_bps must be between 1 and 10000")
        if initial_margin < maintenance_margin:
            raise ValueError("initial margin must not be below maintenance margin")
        if short_borrow > 10_000:
            raise ValueError("short_borrow_bps must not exceed 10000")
        object.__setattr__(self, "initial_margin_bps", initial_margin)
        object.__setattr__(self, "maintenance_margin_bps", maintenance_margin)
        object.__setattr__(self, "short_borrow_bps", short_borrow)


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Completed-slice capacity and fee configuration."""

    participation_bps: int
    fixed_fee: Decimal | str | int | float = Decimal(0)
    fee_bps: int = 0
    model: ExecutionModel = "completed_bar_v1"

    def __post_init__(self) -> None:
        participation = quantity_value(self.participation_bps, name="participation_bps")
        fee_bps = quantity_value(self.fee_bps, name="fee_bps")
        if participation > 10_000:
            raise ValueError("participation_bps must not exceed 10000")
        if fee_bps > 10_000:
            raise ValueError("fee_bps must not exceed 10000")
        if self.model != "completed_bar_v1":
            raise ValueError("only the completed_bar_v1 execution model is supported")
        object.__setattr__(self, "participation_bps", participation)
        object.__setattr__(self, "fee_bps", fee_bps)
        object.__setattr__(
            self,
            "fixed_fee",
            decimal_value(self.fixed_fee, name="fixed_fee", nonnegative=True),
        )


@dataclass(frozen=True, slots=True)
class ScenarioBar:
    """One exact completed bar within a synchronized market slice."""

    instrument_id: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        for name in ("open", "high", "low", "close"):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=name, positive=True),
            )
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("bar OHLC values are inconsistent")
        if self.volume is not None:
            object.__setattr__(
                self,
                "volume",
                execution_quantity(self.volume, name="volume", nonnegative=True),
            )


@dataclass(frozen=True, slots=True)
class MarketSlice:
    """A synchronized set containing exactly one bar per instrument."""

    slice_sequence: int
    start_at: pd.Timestamp
    end_at: pd.Timestamp
    available_at: pd.Timestamp
    received_at: pd.Timestamp
    bars: tuple[ScenarioBar, ...]
    fx_rates: tuple[FxRate, ...]
    corporate_actions: tuple[CorporateAction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "slice_sequence",
            quantity_value(self.slice_sequence, name="slice_sequence", positive=True),
        )
        for name in ("start_at", "end_at", "available_at", "received_at"):
            object.__setattr__(self, name, _timestamp(getattr(self, name), name=name))
        if not self.start_at < self.end_at <= self.available_at <= self.received_at:
            raise ValueError("slice timestamps must satisfy start < end <= available <= received")
        if not self.bars:
            raise ValueError("a market slice must contain at least one bar")
        identities = [bar.instrument_id for bar in self.bars]
        if len(identities) != len(set(identities)):
            raise ValueError("a market slice must contain each instrument exactly once")
        if not self.fx_rates:
            raise ValueError("a market slice must contain FX rates")
        currencies = [item.currency for item in self.fx_rates]
        if len(currencies) != len(set(currencies)):
            raise ValueError("a market slice must contain one FX rate per currency")
        action_ids = [item.action_id for item in self.corporate_actions]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("market slice corporate action identifiers must be unique")
        object.__setattr__(
            self,
            "bars",
            tuple(sorted(self.bars, key=lambda item: item.instrument_id)),
        )
        object.__setattr__(
            self,
            "fx_rates",
            tuple(sorted(self.fx_rates, key=lambda item: item.currency)),
        )
        object.__setattr__(
            self,
            "corporate_actions",
            tuple(sorted(self.corporate_actions, key=lambda item: item.action_id)),
        )


@dataclass(frozen=True, slots=True)
class TargetWeight:
    """One exact signed portfolio weight."""

    instrument_id: str
    weight: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(self, "weight", decimal_value(self.weight, name="weight"))


@dataclass(frozen=True, slots=True)
class TargetQuantity:
    """One exact signed portfolio target."""

    instrument_id: str
    quantity: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(
            self,
            "quantity",
            execution_quantity(self.quantity, name="quantity"),
        )


@dataclass(frozen=True, slots=True)
class TargetWeightsIntent:
    """Request a complete portfolio using current marked equity."""

    targets: tuple[TargetWeight, ...]
    type: Literal["target_weights"] = field(default="target_weights", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))


@dataclass(frozen=True, slots=True)
class TargetQuantitiesIntent:
    """Request a complete portfolio using explicit signed quantities."""

    targets: tuple[TargetQuantity, ...]
    type: Literal["target_quantities"] = field(default="target_quantities", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))


@dataclass(frozen=True, slots=True)
class SubmitOrderIntent:
    """Submit one direct market or limit order."""

    instrument_id: str
    side: Side
    quantity: Decimal | str | int | float
    order_kind: OrderKind
    limit_price: Decimal | str | int | float | None = None
    type: Literal["submit_order"] = field(default="submit_order", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        object.__setattr__(
            self,
            "quantity",
            execution_quantity(self.quantity, name="quantity", positive=True),
        )
        if self.order_kind not in {"market", "limit"}:
            raise ValueError("order_kind must be market or limit")
        if self.limit_price is None:
            if self.order_kind != "market":
                raise ValueError("limit orders require limit_price")
        else:
            if self.order_kind != "limit":
                raise ValueError("market orders require null limit_price")
            object.__setattr__(
                self,
                "limit_price",
                decimal_value(self.limit_price, name="limit_price", positive=True),
            )


@dataclass(frozen=True, slots=True)
class CancelOrderIntent:
    """Cancel one engine order by identifier."""

    order_id: str
    type: Literal["cancel_order"] = field(default="cancel_order", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "order_id", identifier(self.order_id, name="order_id"))


@dataclass(frozen=True, slots=True)
class EmitMetricIntent:
    """Emit one exact string metric into the audit stream."""

    name: str
    value: str
    type: Literal["emit_metric"] = field(default="emit_metric", init=False)

    def __post_init__(self) -> None:
        if not isinstance(cast("object", self.name), str):
            raise TypeError("metric name must be a string")
        value = cast("object", self.value)
        if not isinstance(value, str):
            raise TypeError("metric value must be a string")


type ScenarioIntent = (
    TargetWeightsIntent
    | TargetQuantitiesIntent
    | SubmitOrderIntent
    | CancelOrderIntent
    | EmitMetricIntent
)


@dataclass(frozen=True, slots=True)
class ScheduleItem:
    """Intents evaluated after one synchronized market slice."""

    after_slice_sequence: int
    intents: tuple[ScenarioIntent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "after_slice_sequence",
            quantity_value(
                self.after_slice_sequence,
                name="after_slice_sequence",
                positive=True,
            ),
        )
        intents = tuple(self.intents)
        if len(intents) > _MAX_INTENTS_PER_BATCH:
            raise ValueError("intent batch exceeds the supported engine limit")
        object.__setattr__(self, "intents", intents)


@dataclass(frozen=True, slots=True)
class TradingEngineScenario:
    """A validated deterministic replay scenario."""

    contract_version: Literal["3"] = field(
        default=TRADING_ENGINE_CONTRACT_VERSION,
        init=False,
    )
    run_id: str
    base_currency: str
    initial_cash: tuple[CashBalance, ...]
    instruments: tuple[ExecutionInstrument, ...]
    risk: RiskPolicy
    execution: ExecutionPolicy
    max_internal_events: int
    metadata: Mapping[str, Any]
    schedule: tuple[ScheduleItem, ...]
    slices: tuple[MarketSlice, ...]

    def __post_init__(self) -> None:
        for name in ("initial_cash", "instruments", "schedule", "slices"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "run_id", identifier(self.run_id, name="run_id"))
        object.__setattr__(
            self,
            "base_currency",
            identifier(self.base_currency, name="base_currency"),
        )
        if not self.initial_cash:
            raise ValueError("initial_cash must contain at least one balance")
        cash_currencies = [item.currency for item in self.initial_cash]
        if len(cash_currencies) != len(set(cash_currencies)):
            raise ValueError("initial_cash must contain one balance per currency")
        object.__setattr__(
            self,
            "initial_cash",
            tuple(sorted(self.initial_cash, key=lambda item: item.currency)),
        )
        if not self.instruments:
            raise ValueError("at least one execution instrument is required")
        if len(self.instruments) > _MAX_CATALOG_INSTRUMENTS:
            raise ValueError("instrument catalog exceeds the supported engine limit")
        max_internal_events = quantity_value(
            self.max_internal_events,
            name="max_internal_events",
            positive=True,
        )
        if max_internal_events > _MAX_INTERNAL_EVENTS:
            raise ValueError("max_internal_events exceeds the supported engine range")
        object.__setattr__(self, "max_internal_events", max_internal_events)
        metadata = cast("object", self.metadata)
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(
            self,
            "metadata",
            _freeze_mapping(cast("Mapping[object, object]", metadata)),
        )
        instrument_by_id = {item.instrument_id: item for item in self.instruments}
        instrument_ids = set(instrument_by_id)
        if len(instrument_by_id) != len(self.instruments):
            raise ValueError("execution instrument identifiers must be unique")
        scenario_currencies = {
            self.base_currency,
            *(item.quote_currency for item in self.instruments),
        }
        if set(cash_currencies) != scenario_currencies:
            raise ValueError("initial_cash must contain every scenario currency exactly once")
        max_order_quantity = cast("Decimal", self.risk.max_order_quantity)
        max_long_position = cast("Decimal", self.risk.max_long_position)
        max_short_position = cast("Decimal", self.risk.max_short_position)
        if any(
            cast("Decimal", item.lot_size) > max_order_quantity
            or cast("Decimal", item.lot_size) > max_long_position
            or cast("Decimal", item.lot_size) > max_short_position
            for item in self.instruments
        ):
            raise ValueError("risk quantity limits must be at least every instrument lot size")
        previous_sequence = 0
        previous_end_at: pd.Timestamp | None = None
        previous_received_at: pd.Timestamp | None = None
        slice_by_sequence: dict[int, MarketSlice] = {}
        corporate_action_ids: set[str] = set()
        for market_slice in self.slices:
            if market_slice.slice_sequence <= previous_sequence:
                raise ValueError("slice_sequence must increase globally")
            if {bar.instrument_id for bar in market_slice.bars} != instrument_ids:
                raise ValueError("every market slice must cover all scenario instruments")
            if {item.currency for item in market_slice.fx_rates} != scenario_currencies:
                raise ValueError("every market slice must cover all scenario currencies")
            base_fx = next(
                item.rate for item in market_slice.fx_rates if item.currency == self.base_currency
            )
            if base_fx != 1:
                raise ValueError("the base-currency FX rate must equal one")
            if previous_end_at is not None and market_slice.end_at <= previous_end_at:
                raise ValueError("market slice end_at must increase")
            if previous_received_at is not None and market_slice.received_at < previous_received_at:
                raise ValueError("market slice received_at must not move backward")
            for bar in market_slice.bars:
                instrument = instrument_by_id[bar.instrument_id]
                tick = decimal_micros(cast("Decimal", instrument.tick_size))
                if any(
                    decimal_micros(getattr(bar, name)) % tick
                    for name in ("open", "high", "low", "close")
                ):
                    raise ValueError("bar prices must align with their instrument tick size")
                if bar.volume is not None and bar.volume % cast("Decimal", instrument.lot_size):
                    raise ValueError("bar volume must align with its instrument lot size")
            for action in market_slice.corporate_actions:
                if action.instrument_id not in instrument_ids:
                    raise ValueError("corporate action refers to an unknown instrument")
                if action.action_id in corporate_action_ids:
                    raise ValueError(
                        "corporate action identifiers must be unique across the scenario"
                    )
                corporate_action_ids.add(action.action_id)
            previous_sequence = market_slice.slice_sequence
            previous_end_at = market_slice.end_at
            previous_received_at = market_slice.received_at
            slice_by_sequence[market_slice.slice_sequence] = market_slice
        previous_schedule = 0
        next_slice_by_sequence = {
            current.slice_sequence: following
            for current, following in zip(self.slices, self.slices[1:], strict=False)
        }
        for scheduled in self.schedule:
            if scheduled.after_slice_sequence <= previous_schedule:
                raise ValueError("schedule after_slice_sequence must increase")
            anchor = slice_by_sequence.get(scheduled.after_slice_sequence)
            if anchor is None:
                raise ValueError("scheduled intents refer to a missing market slice")
            self._validate_intents(scheduled.intents, instrument_by_id, self.risk)
            following = next_slice_by_sequence.get(scheduled.after_slice_sequence)
            produces_orders = any(
                isinstance(
                    intent,
                    TargetWeightsIntent
                    | TargetQuantitiesIntent
                    | SubmitOrderIntent
                    | CancelOrderIntent,
                )
                for intent in scheduled.intents
            )
            if (
                produces_orders
                and following is not None
                and anchor.received_at > following.start_at
            ):
                raise ValueError(
                    "scheduled intents must not follow the next executable slice start_at"
                )
            previous_schedule = scheduled.after_slice_sequence

    @staticmethod
    def _validate_intents(
        intents: tuple[ScenarioIntent, ...],
        instrument_by_id: Mapping[str, ExecutionInstrument],
        risk: RiskPolicy,
    ) -> None:
        instrument_ids = set(instrument_by_id)
        for intent in intents:
            if isinstance(intent, TargetWeightsIntent):
                ids = [item.instrument_id for item in intent.targets]
                if set(ids) != instrument_ids or len(ids) != len(instrument_ids):
                    raise ValueError("target weights must cover every instrument exactly once")
                gross = sum(
                    (abs(cast("Decimal", item.weight)) for item in intent.targets),
                    Decimal(0),
                )
                if gross > cast("Decimal", risk.max_leverage):
                    raise ValueError("target gross weight exceeds maximum leverage")
            elif isinstance(intent, TargetQuantitiesIntent):
                ids = [item.instrument_id for item in intent.targets]
                if set(ids) != instrument_ids or len(ids) != len(instrument_ids):
                    raise ValueError("target quantities must cover every instrument exactly once")
                for target in intent.targets:
                    quantity = cast("Decimal", target.quantity)
                    lot_size = cast("Decimal", instrument_by_id[target.instrument_id].lot_size)
                    if quantity % lot_size:
                        raise ValueError("target quantity must align with its instrument lot size")
                    if quantity > cast("Decimal", risk.max_long_position):
                        raise ValueError("target quantity exceeds max_long_position")
                    if quantity < -cast("Decimal", risk.max_short_position):
                        raise ValueError("target quantity exceeds max_short_position")
            elif isinstance(intent, SubmitOrderIntent):
                instrument = instrument_by_id.get(intent.instrument_id)
                if instrument is None:
                    raise ValueError("submit_order refers to an unknown instrument")
                quantity = cast("Decimal", intent.quantity)
                if quantity % cast("Decimal", instrument.lot_size):
                    raise ValueError("order quantity must align with its instrument lot size")
                if quantity > cast("Decimal", risk.max_order_quantity):
                    raise ValueError("order quantity exceeds max_order_quantity")
                if intent.limit_price is not None:
                    tick = decimal_micros(cast("Decimal", instrument.tick_size))
                    if decimal_micros(cast("Decimal", intent.limit_price)) % tick:
                        raise ValueError("order limit price must align with instrument tick size")


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """One immutable, validated audit journal record."""

    contract_version: str
    engine_sequence: int
    event_id: str
    causation_ids: tuple[str, ...]
    run_id: str
    recorded_at: pd.Timestamp
    event_type: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.contract_version != TRADING_ENGINE_CONTRACT_VERSION:
            raise ValueError(
                "unsupported journal event contract_version "
                f"{self.contract_version!r} (expected {TRADING_ENGINE_CONTRACT_VERSION!r})"
            )
        object.__setattr__(self, "event_id", identifier(self.event_id, name="event_id"))
        if not isinstance(cast("object", self.causation_ids), tuple):
            raise TypeError("causation_ids must be a tuple")
        causes = tuple(
            identifier(item, name="causation_id")
            for item in cast("tuple[object, ...]", self.causation_ids)
        )
        if len(causes) != len(set(causes)):
            raise ValueError("causation_ids must not contain duplicates")
        object.__setattr__(self, "causation_ids", causes)
        object.__setattr__(
            self,
            "payload",
            _freeze_mapping(cast("Mapping[object, object]", self.payload)),
        )


@dataclass(frozen=True, slots=True)
class RunCompletion:
    """Terminal engine valuation, order counts, and scenario identity."""

    recorded_at: pd.Timestamp
    engine_sequence: int
    scenario_sha256: str
    execution_model: ExecutionModel
    cash_micros: int
    net_market_value_micros: int
    long_market_value_micros: int
    short_market_value_micros: int
    gross_exposure_micros: int
    cost_basis_micros: int
    realized_pnl_micros: int
    unrealized_pnl_micros: int
    equity_micros: int
    dividend_pnl_micros: int
    execution_fees_micros: int
    borrow_fees_micros: int
    total_fees_micros: int
    total_orders: int
    active_orders: int
    filled_orders: int
    rejected_orders: int
    cancelled_orders: int


@dataclass(frozen=True, slots=True)
class ExecutionReplayResult:
    """Normalized frames imported from one complete engine journal."""

    run_id: str
    scenario_sha256: str
    execution_model: ExecutionModel
    bars: pd.DataFrame
    fx_rates: pd.DataFrame
    targets: pd.DataFrame
    orders: pd.DataFrame
    order_adjustments: pd.DataFrame
    fills: pd.DataFrame
    cancellations: pd.DataFrame
    rejections: pd.DataFrame
    corporate_actions: pd.DataFrame
    margin_limits: pd.DataFrame
    borrow_fees: pd.DataFrame
    margin_events: pd.DataFrame
    valuations: pd.DataFrame
    cash_balances: pd.DataFrame
    positions: pd.DataFrame
    metrics: pd.DataFrame
    events: tuple[JournalEvent, ...]
    completion: RunCompletion
    contract_version: str = TRADING_ENGINE_CONTRACT_VERSION
    base_currency: str | None = None
    initial_cash_balances: pd.DataFrame | None = None
    initial_equity: float | None = None
    initial_equity_micros: int | None = None

    def __post_init__(self) -> None:
        if self.contract_version != TRADING_ENGINE_CONTRACT_VERSION:
            raise ValueError(
                "unsupported replay contract_version "
                f"{self.contract_version!r} (expected {TRADING_ENGINE_CONTRACT_VERSION!r})"
            )
        if self.execution_model != "completed_bar_v1":
            raise ValueError("unsupported replay execution_model")
        object.__setattr__(self, "events", tuple(self.events))
        for name in (
            "bars",
            "fx_rates",
            "targets",
            "orders",
            "order_adjustments",
            "fills",
            "cancellations",
            "rejections",
            "corporate_actions",
            "margin_limits",
            "borrow_fees",
            "margin_events",
            "valuations",
            "cash_balances",
            "positions",
            "metrics",
        ):
            object.__setattr__(self, name, getattr(self, name).copy(deep=True))
        if self.initial_cash_balances is not None:
            object.__setattr__(
                self,
                "initial_cash_balances",
                self.initial_cash_balances.copy(deep=True),
            )


@dataclass(frozen=True, slots=True)
class EngineRunResult:
    """Artifacts and process output from one successful replay."""

    executable: Path
    executable_sha256: str
    capabilities: EngineCapabilities
    scenario_path: Path
    journal_path: Path
    manifest_path: Path
    scenario_sha256: str
    journal_sha256: str
    validation_stdout: str
    validation_stderr: str
    stdout: str
    stderr: str
    replay: ExecutionReplayResult
    strategy: StrategyRunResult | None


@dataclass(slots=True)
class TradingEngineProcessError(RuntimeError):
    """A validation or replay subprocess failed."""

    message: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    journal_path: Path | None = field(default=None)
    strategy_transcript_path: Path | None = field(default=None)

    def __str__(self) -> str:
        return self.message


def _timestamp(value: object, *, name: str) -> pd.Timestamp:
    if not isinstance(value, pd.Timestamp):
        raise TypeError(f"{name} must be a pandas Timestamp")
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    result = value.tz_convert("UTC")
    if result.nanosecond % 1_000:
        raise ValueError(f"{name} must not exceed microsecond precision")
    return result


def _freeze_mapping(value: Mapping[object, object]) -> Mapping[str, Any]:
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("metadata keys must be strings")
        result[key] = _freeze_value(item)
    return MappingProxyType(result)


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(cast("Mapping[object, object]", value))
    if isinstance(value, list | tuple):
        return tuple(_freeze_value(item) for item in cast("Sequence[object]", value))
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("metadata numbers must be finite")
        return value
    raise TypeError("metadata must contain JSON-compatible values")
