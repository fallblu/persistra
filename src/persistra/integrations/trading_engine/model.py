"""Typed policies and results for the trading-engine integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import (
    decimal_micros,
    decimal_value,
    identifier,
    quantity_value,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

type SourceTimestampPosition = Literal["start", "end"]
type EquityBasis = Literal["initial_cash"]
type ReferencePrice = Literal["decision_close"]
type QuantityRounding = Literal["down_to_lot"]


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
    """Convert target weights into whole-lot positions."""

    equity_basis: EquityBasis = "initial_cash"
    reference_price: ReferencePrice = "decision_close"
    quantity_rounding: QuantityRounding = "down_to_lot"

    def __post_init__(self) -> None:
        if self.equity_basis != "initial_cash":
            raise ValueError("only the initial_cash equity basis is supported")
        if self.reference_price != "decision_close":
            raise ValueError("only the decision_close reference price is supported")
        if self.quantity_rounding != "down_to_lot":
            raise ValueError("only down_to_lot quantity rounding is supported")


@dataclass(frozen=True, slots=True)
class ExecutionInstrument:
    """Executable metadata supplied separately from research identity."""

    instrument_id: str
    symbol: str
    quote_currency: str
    tick_size: Decimal | str | int | float
    lot_size: int = 1

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
            quantity_value(self.lot_size, name="lot_size", positive=True),
        )


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    """Global long-only engine quantity limits."""

    max_order_quantity: int
    max_position: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_order_quantity",
            quantity_value(
                self.max_order_quantity,
                name="max_order_quantity",
                positive=True,
            ),
        )
        object.__setattr__(
            self,
            "max_position",
            quantity_value(self.max_position, name="max_position", positive=True),
        )


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """Completed-bar capacity and fee configuration."""

    participation_bps: int
    fixed_fee: Decimal | str | int | float = Decimal(0)
    fee_bps: int = 0

    def __post_init__(self) -> None:
        participation = quantity_value(self.participation_bps, name="participation_bps")
        fee_bps = quantity_value(self.fee_bps, name="fee_bps")
        if participation > 10_000:
            raise ValueError("participation_bps must not exceed 10000")
        if fee_bps > 10_000:
            raise ValueError("fee_bps must not exceed 10000")
        object.__setattr__(self, "participation_bps", participation)
        object.__setattr__(self, "fee_bps", fee_bps)
        object.__setattr__(
            self,
            "fixed_fee",
            decimal_value(self.fixed_fee, name="fixed_fee", nonnegative=True),
        )


@dataclass(frozen=True, slots=True)
class ScenarioBar:
    """One exact completed bar in global replay order."""

    source_sequence: int
    instrument_id: str
    source_timestamp: pd.Timestamp
    start_at: pd.Timestamp
    end_at: pd.Timestamp
    available_at: pd.Timestamp
    received_at: pd.Timestamp
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_sequence",
            quantity_value(self.source_sequence, name="source_sequence"),
        )
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        for name in ("source_timestamp", "start_at", "end_at", "available_at", "received_at"):
            object.__setattr__(self, name, _timestamp(getattr(self, name), name=name))
        for name in ("open", "high", "low", "close"):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=name, positive=True),
            )
        if not self.start_at < self.end_at <= self.available_at <= self.received_at:
            raise ValueError("bar timestamps must satisfy start < end <= available <= received")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("bar OHLC values are inconsistent")
        if self.volume is not None:
            object.__setattr__(
                self,
                "volume",
                quantity_value(self.volume, name="volume"),
            )


@dataclass(frozen=True, slots=True)
class TargetDecision:
    """A target position anchored after a complete same-period bar group."""

    after_bar_sequence: int
    decision_at: pd.Timestamp
    instrument_id: str
    quantity: int
    reference_close: Decimal
    target_weight: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "after_bar_sequence",
            quantity_value(self.after_bar_sequence, name="after_bar_sequence"),
        )
        object.__setattr__(
            self,
            "decision_at",
            _timestamp(self.decision_at, name="decision_at"),
        )
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(self, "quantity", quantity_value(self.quantity, name="quantity"))
        object.__setattr__(
            self,
            "reference_close",
            decimal_value(self.reference_close, name="reference_close", positive=True),
        )
        if self.target_weight is not None:
            if not 0 <= self.target_weight <= 1:
                raise ValueError("target_weight must be between zero and one")


@dataclass(frozen=True, slots=True)
class TradingEngineScenario:
    """A validated version 1 replay scenario and its research decisions."""

    run_id: str
    base_currency: str
    initial_cash: Decimal
    instruments: tuple[ExecutionInstrument, ...]
    risk: RiskPolicy
    execution: ExecutionPolicy
    max_internal_events: int
    bars: tuple[ScenarioBar, ...]
    decisions: tuple[TargetDecision, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("only trading-engine scenario schema version 1 is supported")
        object.__setattr__(self, "run_id", identifier(self.run_id, name="run_id"))
        object.__setattr__(
            self,
            "base_currency",
            identifier(self.base_currency, name="base_currency"),
        )
        object.__setattr__(
            self,
            "initial_cash",
            decimal_value(self.initial_cash, name="initial_cash", nonnegative=True),
        )
        if not self.instruments:
            raise ValueError("at least one execution instrument is required")
        object.__setattr__(
            self,
            "max_internal_events",
            quantity_value(
                self.max_internal_events,
                name="max_internal_events",
                positive=True,
            ),
        )
        instrument_by_id = {item.instrument_id: item for item in self.instruments}
        if len(instrument_by_id) != len(self.instruments):
            raise ValueError("execution instrument identifiers must be unique")
        if any(item.quote_currency != self.base_currency for item in self.instruments):
            raise ValueError("every instrument quote currency must match base_currency")
        previous_source_sequence: int | None = None
        previous_received_at: pd.Timestamp | None = None
        previous_end: dict[str, pd.Timestamp] = {}
        bar_sequences: set[int] = set()
        for bar in self.bars:
            instrument = instrument_by_id.get(bar.instrument_id)
            if instrument is None:
                raise ValueError("bar refers to an unknown execution instrument")
            if (
                previous_source_sequence is not None
                and bar.source_sequence <= previous_source_sequence
            ):
                raise ValueError("bar source_sequence must increase globally")
            if previous_received_at is not None and bar.received_at < previous_received_at:
                raise ValueError("bar received_at must not move backward")
            prior_end = previous_end.get(bar.instrument_id)
            if prior_end is not None and bar.end_at <= prior_end:
                raise ValueError("each instrument's bar end must increase")
            tick = decimal_micros(cast("Decimal", instrument.tick_size))
            if any(
                decimal_micros(getattr(bar, name)) % tick
                for name in ("open", "high", "low", "close")
            ):
                raise ValueError("bar prices must align with their instrument tick size")
            previous_source_sequence = bar.source_sequence
            previous_received_at = bar.received_at
            previous_end[bar.instrument_id] = bar.end_at
            bar_sequences.add(bar.source_sequence)
        for decision in self.decisions:
            instrument = instrument_by_id.get(decision.instrument_id)
            if instrument is None:
                raise ValueError("target refers to an unknown execution instrument")
            if decision.after_bar_sequence not in bar_sequences:
                raise ValueError("target refers to a missing bar source sequence")
            if decision.quantity % instrument.lot_size:
                raise ValueError("target quantity must align with its instrument lot size")
            later_bars = [
                bar
                for bar in self.bars
                if bar.instrument_id == decision.instrument_id
                and bar.source_sequence > decision.after_bar_sequence
            ]
            if later_bars:
                next_bar = min(later_bars, key=lambda item: item.source_sequence)
                if decision.decision_at > next_bar.start_at:
                    raise ValueError(
                        "target decision_at must not follow its next executable bar start_at"
                    )


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """One immutable, schema-validated audit journal record."""

    engine_sequence: int
    run_id: str
    recorded_at: pd.Timestamp
    event_type: str
    payload: Mapping[str, Any]
    schema_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class RunCompletion:
    """Terminal engine valuation and order counts."""

    recorded_at: pd.Timestamp
    engine_sequence: int
    cash_micros: int
    market_value_micros: int
    cost_basis_micros: int
    realized_pnl_micros: int
    unrealized_pnl_micros: int
    equity_micros: int
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
    bars: pd.DataFrame
    targets: pd.DataFrame
    orders: pd.DataFrame
    fills: pd.DataFrame
    cancellations: pd.DataFrame
    rejections: pd.DataFrame
    valuations: pd.DataFrame
    metrics: pd.DataFrame
    events: tuple[JournalEvent, ...]
    completion: RunCompletion
    base_currency: str | None = None
    initial_cash: float | None = None
    initial_cash_micros: int | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in (
            "bars",
            "targets",
            "orders",
            "fills",
            "cancellations",
            "rejections",
            "valuations",
            "metrics",
        ):
            frame = getattr(self, name)
            object.__setattr__(self, name, frame.copy(deep=True))


@dataclass(frozen=True, slots=True)
class EngineRunResult:
    """Artifacts and process output from one successful replay."""

    executable: Path
    scenario_path: Path
    journal_path: Path
    scenario_sha256: str
    journal_sha256: str
    validation_stdout: str
    validation_stderr: str
    stdout: str
    stderr: str
    replay: ExecutionReplayResult


@dataclass(frozen=True, slots=True)
class TradingEngineProcessError(RuntimeError):
    """A validation or replay subprocess failed."""

    message: str
    command: tuple[str, ...]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    journal_path: Path | None = field(default=None)

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
