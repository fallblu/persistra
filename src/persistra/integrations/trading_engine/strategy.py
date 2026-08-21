"""Host and validate external Trading Engine strategy protocol v3 sessions."""

from __future__ import annotations

import json
import math
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Literal, Protocol, TextIO, cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import (
    decimal_value,
    execution_quantity,
    identifier,
    quantity_value,
    weight_toward_zero,
)
from persistra.integrations.trading_engine.model import (
    CancelOrderIntent,
    CashBalance,
    EmitMetricIntent,
    ExecutionInstrument,
    ExecutionPolicy,
    MarketSlice,
    RiskPolicy,
    ScenarioBar,
    ScenarioIntent,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetWeightsIntent,
)
from persistra.integrations.trading_engine.scenario import (
    decode_bar,
    decode_cash_balance,
    decode_execution_policy,
    decode_instrument,
    decode_intent,
    decode_metadata,
    decode_risk_policy,
    decode_slice,
    decode_timestamp,
    encode_intent,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import NoReturn

TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION: Final = "3"
STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES: Final = 1_048_576
_TRANSCRIPT_RECORD_MAX_BYTES: Final = 2 * STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES
_SHA256 = re.compile(r"[0-9a-f]{64}")

type StrategyOrderOrigin = Literal["direct", "target_rebalance", "margin_liquidation"]
type StrategyOrderStatus = Literal["working", "partially_filled", "filled", "cancelled", "rejected"]
type StrategyEvent = (
    MarketSliceClosedEvent | FillReceivedEvent | OrderUpdatedEvent | IntentRejectedEvent
)


@dataclass(frozen=True, slots=True)
class StrategyProcess:
    """Declare one strategy child process and the files that define its behavior."""

    command: tuple[str | Path, ...]
    artifacts: tuple[Path, ...] = ()
    response_timeout: float = 30.0

    def __post_init__(self) -> None:
        raw_command = cast("object", self.command)
        if not isinstance(raw_command, tuple):
            raise TypeError("command must be a tuple")
        if not raw_command:
            raise ValueError("command must not be empty")
        command: list[str] = []
        for index, part in enumerate(cast("tuple[object, ...]", raw_command)):
            if not isinstance(part, str | Path):
                raise TypeError("command elements must be strings or paths")
            value = os.fspath(part)
            if (index == 0 and not value) or "\0" in value:
                raise ValueError(
                    "the strategy executable must be nonempty and arguments must "
                    "contain no NUL bytes"
                )
            command.append(value)
        raw_artifacts = cast("object", self.artifacts)
        if not isinstance(raw_artifacts, tuple):
            raise TypeError("artifacts must be a tuple")
        artifacts: list[Path] = []
        for artifact in cast("tuple[object, ...]", raw_artifacts):
            if not isinstance(artifact, Path):
                raise TypeError("strategy artifacts must be paths")
            artifacts.append(artifact.expanduser())
        if isinstance(self.response_timeout, bool) or not math.isfinite(self.response_timeout):
            raise ValueError("response_timeout must be a positive finite number")
        if self.response_timeout <= 0:
            raise ValueError("response_timeout must be a positive finite number")
        object.__setattr__(self, "command", tuple(command))
        object.__setattr__(self, "artifacts", tuple(artifacts))
        object.__setattr__(self, "response_timeout", float(self.response_timeout))


@dataclass(frozen=True, slots=True)
class StrategyIdentity:
    """Identity reported by a strategy after initialization."""

    name: str
    version: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, name="strategy_name"))
        if self.version is not None:
            object.__setattr__(
                self,
                "version",
                _trimmed_string(self.version, name="strategy_version"),
            )


@dataclass(frozen=True, slots=True)
class StrategyArtifact:
    """One declared strategy input bound into a successful run."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(self, "sha256", _hash(self.sha256, name="strategy artifact sha256"))


@dataclass(frozen=True, slots=True)
class StrategyRunResult:
    """Strategy identity and immutable artifacts retained by a successful run."""

    identity: StrategyIdentity
    executable: Path
    executable_sha256: str
    artifacts: tuple[StrategyArtifact, ...]
    transcript_path: Path
    transcript_sha256: str
    event_count: int
    response_timeout: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "executable", Path(self.executable))
        object.__setattr__(
            self,
            "executable_sha256",
            _hash(self.executable_sha256, name="strategy executable sha256"),
        )
        if not isinstance(cast("object", self.artifacts), tuple):
            raise TypeError("strategy result artifacts must be a tuple")
        object.__setattr__(self, "transcript_path", Path(self.transcript_path))
        object.__setattr__(
            self,
            "transcript_sha256",
            _hash(self.transcript_sha256, name="strategy transcript sha256"),
        )
        object.__setattr__(
            self,
            "event_count",
            quantity_value(self.event_count, name="strategy event_count"),
        )
        if isinstance(self.response_timeout, bool) or not math.isfinite(self.response_timeout):
            raise ValueError("strategy response_timeout must be a positive finite number")
        if self.response_timeout <= 0:
            raise ValueError("strategy response_timeout must be a positive finite number")
        object.__setattr__(self, "response_timeout", float(self.response_timeout))


@dataclass(frozen=True, slots=True)
class StrategyInitialization:
    """Static scenario state supplied before strategy events."""

    engine_version: str
    scenario_contract_version: str
    scenario_sha256: str
    run_id: str
    base_currency: str
    initial_cash: tuple[CashBalance, ...]
    instruments: tuple[ExecutionInstrument, ...]
    risk: RiskPolicy
    execution: ExecutionPolicy
    metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "engine_version",
            identifier(self.engine_version, name="engine_version"),
        )
        object.__setattr__(
            self,
            "scenario_contract_version",
            identifier(self.scenario_contract_version, name="scenario_contract_version"),
        )
        object.__setattr__(
            self,
            "scenario_sha256",
            _hash(self.scenario_sha256, name="scenario_sha256"),
        )
        object.__setattr__(self, "run_id", identifier(self.run_id, name="run_id"))
        object.__setattr__(
            self,
            "base_currency",
            identifier(self.base_currency, name="base_currency"),
        )
        _require_tuple(self.initial_cash, name="initial_cash")
        _require_tuple(self.instruments, name="instruments")
        if not self.initial_cash:
            raise ValueError("initial_cash must not be empty")
        if not self.instruments:
            raise ValueError("instruments must not be empty")
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata, name="metadata"))


@dataclass(frozen=True, slots=True)
class StrategyCashBalance:
    """One marked native-currency cash ledger in a strategy portfolio."""

    currency: str
    amount: Decimal | str | int | float
    fx_rate: Decimal | str | int | float
    base_value: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", identifier(self.currency, name="currency"))
        object.__setattr__(
            self,
            "amount",
            decimal_value(self.amount, name="strategy cash amount"),
        )
        object.__setattr__(
            self,
            "fx_rate",
            decimal_value(self.fx_rate, name="strategy cash fx_rate", positive=True),
        )
        object.__setattr__(
            self,
            "base_value",
            decimal_value(self.base_value, name="strategy cash base_value"),
        )


@dataclass(frozen=True, slots=True)
class StrategyPosition:
    """One marked position and realized portfolio weight."""

    instrument_id: str
    quantity: Decimal | str | int | float
    mark: Decimal | str | int | float
    base_market_value: Decimal | str | int | float
    weight: Decimal | str | int | float | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(
            self,
            "quantity",
            execution_quantity(self.quantity, name="position quantity"),
        )
        object.__setattr__(
            self,
            "mark",
            decimal_value(self.mark, name="position mark", positive=True),
        )
        object.__setattr__(
            self,
            "base_market_value",
            decimal_value(self.base_market_value, name="position base_market_value"),
        )
        object.__setattr__(
            self,
            "weight",
            None if self.weight is None else decimal_value(self.weight, name="position weight"),
        )


@dataclass(frozen=True, slots=True)
class StrategyPortfolio:
    """Authoritative marked account state at one strategy boundary."""

    base_currency: str
    cash: Decimal | str | int | float
    net_market_value: Decimal | str | int | float
    long_market_value: Decimal | str | int | float
    short_market_value: Decimal | str | int | float
    gross_exposure: Decimal | str | int | float
    equity: Decimal | str | int | float
    weights_available: bool
    cash_weight: Decimal | str | int | float | None
    cash_balances: tuple[StrategyCashBalance, ...]
    positions: tuple[StrategyPosition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "base_currency",
            identifier(self.base_currency, name="base_currency"),
        )
        for name in ("cash", "net_market_value", "equity"):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=f"portfolio {name}"),
            )
        for name in ("long_market_value", "short_market_value", "gross_exposure"):
            object.__setattr__(
                self,
                name,
                decimal_value(
                    getattr(self, name),
                    name=f"portfolio {name}",
                    nonnegative=True,
                ),
            )
        if not isinstance(cast("object", self.weights_available), bool):
            raise TypeError("weights_available must be a boolean")
        object.__setattr__(
            self,
            "cash_weight",
            (
                None
                if self.cash_weight is None
                else decimal_value(self.cash_weight, name="portfolio cash_weight")
            ),
        )
        for name in ("cash_balances", "positions"):
            _require_tuple(getattr(self, name), name=name)
            if not getattr(self, name):
                raise ValueError(f"{name} must not be empty")
        if len({balance.currency for balance in self.cash_balances}) != len(self.cash_balances):
            raise ValueError("cash_balances must contain unique currencies")
        if len({position.instrument_id for position in self.positions}) != len(self.positions):
            raise ValueError("positions must contain unique instruments")
        equity = cast("Decimal", self.equity)
        cash = cast("Decimal", self.cash)
        net_market_value = cast("Decimal", self.net_market_value)
        long_market_value = cast("Decimal", self.long_market_value)
        short_market_value = cast("Decimal", self.short_market_value)
        gross_exposure = cast("Decimal", self.gross_exposure)
        if self.weights_available:
            if equity <= 0:
                raise ValueError("weights require positive portfolio equity")
            if self.cash_weight is None or any(
                position.weight is None for position in self.positions
            ):
                raise ValueError("all weights must be present when weights are available")
        elif self.cash_weight is not None or any(
            position.weight is not None for position in self.positions
        ):
            raise ValueError("all weights must be null when weights are unavailable")
        elif equity > 0:
            raise ValueError("positive portfolio equity must expose weights")
        if long_market_value - short_market_value != net_market_value:
            raise ValueError("portfolio net market value does not reconcile")
        if long_market_value + short_market_value != gross_exposure:
            raise ValueError("portfolio gross exposure does not reconcile")
        if cash + net_market_value != equity:
            raise ValueError("portfolio equity does not reconcile")
        cash_total = sum(
            (cast("Decimal", balance.base_value) for balance in self.cash_balances),
            start=Decimal(0),
        )
        if cash_total != cash:
            raise ValueError("portfolio cash balances do not reconcile")
        if (
            sum(
                (cast("Decimal", position.base_market_value) for position in self.positions),
                start=Decimal(0),
            )
            != net_market_value
        ):
            raise ValueError("portfolio positions do not reconcile")
        if self.weights_available:
            cash_weight = cast("Decimal", self.cash_weight)
            if cash_weight != weight_toward_zero(cash, equity=equity):
                raise ValueError(
                    "portfolio cash_weight does not reconcile with cash and equity"
                )
            for position in self.positions:
                position_weight = cast("Decimal", position.weight)
                base_market_value = cast("Decimal", position.base_market_value)
                if position_weight != weight_toward_zero(
                    base_market_value,
                    equity=equity,
                ):
                    raise ValueError(
                        "position weight does not reconcile with base_market_value and "
                        f"equity for {position.instrument_id!r}"
                    )

    def position(self, instrument_id: str) -> StrategyPosition:
        """Return the marked position for one configured instrument."""
        checked_id = identifier(instrument_id, name="instrument_id")
        try:
            return next(item for item in self.positions if item.instrument_id == checked_id)
        except StopIteration as error:
            raise KeyError(checked_id) from error


@dataclass(frozen=True, slots=True)
class StrategyOrder:
    """One complete order snapshot in an event or context."""

    order_id: str
    instrument_id: str
    side: Literal["buy", "sell"]
    quantity: Decimal | str | int | float
    order_kind: Literal["market", "limit"]
    limit_price: Decimal | str | int | float | None
    origin: StrategyOrderOrigin
    created_event_id: str
    updated_event_id: str
    created_sequence: int | str
    created_at: pd.Timestamp
    eligible_after_slice_sequence: int | str
    filled_quantity: Decimal | str | int | float
    filled_notional: Decimal | str | int | float
    status: StrategyOrderStatus
    rejection_reason: str | None

    def __post_init__(self) -> None:
        for name in ("order_id", "instrument_id", "created_event_id", "updated_event_id"):
            object.__setattr__(self, name, identifier(getattr(self, name), name=name))
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if self.order_kind not in {"market", "limit"}:
            raise ValueError("order_kind must be market or limit")
        if self.origin not in {"direct", "target_rebalance", "margin_liquidation"}:
            raise ValueError("unsupported order origin")
        if self.status not in {"working", "partially_filled", "filled", "cancelled", "rejected"}:
            raise ValueError("unsupported order status")
        checked_quantity = execution_quantity(self.quantity, name="order quantity", positive=True)
        checked_filled = execution_quantity(
            self.filled_quantity,
            name="filled_quantity",
            nonnegative=True,
        )
        if checked_filled > checked_quantity:
            raise ValueError("filled_quantity must not exceed order quantity")
        checked_limit = (
            None
            if self.limit_price is None
            else decimal_value(self.limit_price, name="limit_price", positive=True)
        )
        if (self.order_kind == "market") != (checked_limit is None):
            raise ValueError("limit_price must be null exactly for market orders")
        object.__setattr__(self, "quantity", checked_quantity)
        object.__setattr__(self, "limit_price", checked_limit)
        object.__setattr__(
            self,
            "created_sequence",
            quantity_value(self.created_sequence, name="created_sequence", positive=True),
        )
        object.__setattr__(
            self,
            "created_at",
            _checked_timestamp(self.created_at, name="created_at"),
        )
        object.__setattr__(
            self,
            "eligible_after_slice_sequence",
            quantity_value(
                self.eligible_after_slice_sequence,
                name="eligible_after_slice_sequence",
            ),
        )
        object.__setattr__(self, "filled_quantity", checked_filled)
        object.__setattr__(
            self,
            "filled_notional",
            decimal_value(self.filled_notional, name="filled_notional", nonnegative=True),
        )
        if self.rejection_reason is not None:
            object.__setattr__(
                self,
                "rejection_reason",
                _trimmed_string(self.rejection_reason, name="rejection_reason"),
            )
        if (self.status == "rejected") != (self.rejection_reason is not None):
            raise ValueError("rejection_reason must be present exactly for rejected orders")


@dataclass(frozen=True, slots=True)
class StrategyFill:
    """One fill delivered to an external strategy."""

    fill_id: str
    order_id: str
    instrument_id: str
    quote_currency: str
    side: Literal["buy", "sell"]
    quantity: Decimal | str | int | float
    price: Decimal | str | int | float
    notional: Decimal | str | int | float
    fee: Decimal | str | int | float
    executed_at: pd.Timestamp
    slice_sequence: int | str

    def __post_init__(self) -> None:
        for name in ("fill_id", "order_id", "instrument_id", "quote_currency"):
            object.__setattr__(self, name, identifier(getattr(self, name), name=name))
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        object.__setattr__(
            self,
            "quantity",
            execution_quantity(self.quantity, name="fill quantity", positive=True),
        )
        object.__setattr__(
            self,
            "price",
            decimal_value(self.price, name="fill price", positive=True),
        )
        object.__setattr__(
            self,
            "notional",
            decimal_value(self.notional, name="fill notional", positive=True),
        )
        object.__setattr__(
            self,
            "fee",
            decimal_value(self.fee, name="fill fee", nonnegative=True),
        )
        object.__setattr__(
            self,
            "executed_at",
            _checked_timestamp(self.executed_at, name="executed_at"),
        )
        object.__setattr__(
            self,
            "slice_sequence",
            quantity_value(self.slice_sequence, name="slice_sequence", positive=True),
        )


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Complete engine state visible at one causal strategy boundary."""

    now: pd.Timestamp
    portfolio: StrategyPortfolio
    working_orders: tuple[StrategyOrder, ...]
    latest_bars: tuple[ScenarioBar, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "now", _checked_timestamp(self.now, name="now"))
        for name in ("working_orders", "latest_bars"):
            _require_tuple(getattr(self, name), name=name)


@dataclass(frozen=True, slots=True)
class MarketSliceClosedEvent:
    """A completed market slice is available to the strategy."""

    market_slice: MarketSlice
    type: Literal["market_slice_closed"] = field(default="market_slice_closed", init=False)


@dataclass(frozen=True, slots=True)
class FillReceivedEvent:
    """A fill changed cash and position state."""

    fill: StrategyFill
    type: Literal["fill_received"] = field(default="fill_received", init=False)


@dataclass(frozen=True, slots=True)
class OrderUpdatedEvent:
    """An order reached a new lifecycle state."""

    order: StrategyOrder
    type: Literal["order_updated"] = field(default="order_updated", init=False)


@dataclass(frozen=True, slots=True)
class IntentRejectedEvent:
    """The engine rejected a strategy intent before order creation."""

    reason: str
    type: Literal["intent_rejected"] = field(default="intent_rejected", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _trimmed_string(self.reason, name="reason"))


class ExternalStrategy(Protocol):
    """Typed lifecycle implemented by a strategy hosted over standard I/O."""

    @property
    def name(self) -> str:
        """Stable strategy identifier reported during initialization."""

        ...

    @property
    def version(self) -> str | None:
        """Optional strategy implementation version."""

        ...

    def initialize(self, initialization: StrategyInitialization) -> None:
        """Receive immutable scenario configuration before any events."""

        ...

    def on_event(
        self,
        context: StrategyContext,
        event: StrategyEvent,
    ) -> Sequence[ScenarioIntent]:
        """Return intents for one engine event."""

        ...

    def shutdown(self) -> None:
        """Release strategy resources before the process exits."""

        ...


class StrategyProtocolError(ValueError):
    """A strategy protocol stream violated version, shape, or lifecycle rules."""


@dataclass(frozen=True, slots=True)
class StrategyTranscript:
    """Validated summary of one successful strategy transcript artifact."""

    path: Path
    initialization: StrategyInitialization
    identity: StrategyIdentity
    record_count: int
    event_count: int
    decisions: tuple[StrategyDecision, ...]


@dataclass(frozen=True, slots=True)
class StrategyDecision:
    """One nonempty strategy intent batch and its known decision slice."""

    after_slice_sequence: int | None
    intents: tuple[ScenarioIntent, ...]

    def __post_init__(self) -> None:
        if self.after_slice_sequence is not None:
            object.__setattr__(
                self,
                "after_slice_sequence",
                quantity_value(
                    self.after_slice_sequence,
                    name="after_slice_sequence",
                    positive=True,
                ),
            )
        if not isinstance(cast("object", self.intents), tuple):
            raise TypeError("strategy decision intents must be a tuple")
        if not self.intents:
            raise ValueError("strategy decision intents must not be empty")


@dataclass(frozen=True, slots=True)
class _Message:
    sequence: int
    message_type: str
    payload: dict[str, Any]


def serve_strategy(
    strategy: ExternalStrategy,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> None:
    """Serve one synchronous protocol v3 session on standard input and output."""
    source = sys.stdin if input_stream is None else input_stream
    sink = sys.stdout if output_stream is None else output_stream
    expected_sequence = 1
    try:
        identity = StrategyIdentity(strategy.name, strategy.version)
    except Exception as error:
        _fail_session(sink, expected_sequence, str(error), cause=error)
    message = _read_request(source, expected_sequence=expected_sequence, sink=sink)
    if message.message_type != "initialize":
        _fail_session(sink, expected_sequence, "first strategy request must be initialize")
    try:
        initialization = _initialization_from_payload(message.payload)
    except Exception as error:
        _fail_session(sink, expected_sequence, str(error), cause=error)
    try:
        strategy.initialize(initialization)
    except Exception as error:
        _fail_callback(sink, expected_sequence, "initialize", error)
    try:
        _write_message(
            sink,
            expected_sequence,
            "ready",
            {"strategy_name": identity.name, "strategy_version": identity.version},
        )
    except Exception as error:
        _fail_session(sink, expected_sequence, str(error), cause=error)
    while True:
        expected_sequence += 1
        message = _read_request(source, expected_sequence=expected_sequence, sink=sink)
        if message.message_type == "event":
            try:
                context, event = _event_payload(message.payload)
            except Exception as error:
                _fail_session(sink, expected_sequence, str(error), cause=error)
            intents: tuple[ScenarioIntent, ...] = ()
            try:
                result = cast("object", strategy.on_event(context, event))
                if isinstance(result, str | bytes) or not isinstance(result, Sequence):
                    raise TypeError("on_event must return a sequence of strategy intents")
                raw_intents = tuple(cast("Sequence[object]", result))
                if not all(isinstance(item, _INTENT_TYPES) for item in raw_intents):
                    raise TypeError("on_event returned a value that is not a strategy intent")
                intents = cast("tuple[ScenarioIntent, ...]", raw_intents)
            except Exception as error:
                _fail_callback(sink, expected_sequence, "on_event", error)
            try:
                _write_message(
                    sink,
                    expected_sequence,
                    "intents",
                    {"intents": [encode_intent(item) for item in intents]},
                )
            except Exception as error:
                _fail_session(sink, expected_sequence, str(error), cause=error)
            continue
        if message.message_type == "shutdown":
            try:
                _empty_payload(message.payload, name="shutdown payload")
            except Exception as error:
                _fail_session(sink, expected_sequence, str(error), cause=error)
            try:
                strategy.shutdown()
            except Exception as error:
                _fail_callback(sink, expected_sequence, "shutdown", error)
            try:
                _write_message(sink, expected_sequence, "stopped", {})
            except Exception as error:
                _fail_session(sink, expected_sequence, str(error), cause=error)
            return
        _fail_session(sink, expected_sequence, "strategy request must be event or shutdown")


def read_strategy_transcript(
    path: str | Path,
    *,
    scenario_sha256: str | None = None,
    run_id: str | None = None,
) -> StrategyTranscript:
    """Read and strictly validate a successful protocol v3 transcript."""
    transcript_path = Path(path).expanduser().resolve(strict=True)
    if not transcript_path.is_file():
        raise ValueError(f"strategy transcript is not a regular file: {transcript_path}")
    expected_hash = None
    if scenario_sha256 is not None:
        expected_hash = _hash(scenario_sha256, name="scenario_sha256")
    expected_run_id = None if run_id is None else identifier(run_id, name="run_id")
    initialization: StrategyInitialization | None = None
    identity: StrategyIdentity | None = None
    pending: _Message | None = None
    event_count = 0
    record_count = 0
    stopped = False
    decisions: list[StrategyDecision] = []
    pending_slice_sequence: int | None = None
    for record_count, record in enumerate(_transcript_records(transcript_path), start=1):
        item = _exact_fields(
            record,
            {"strategy_protocol_version", "transcript_sequence", "direction", "message"},
            name="strategy transcript record",
        )
        if item["strategy_protocol_version"] != TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION:
            raise StrategyProtocolError("unsupported strategy transcript protocol version")
        sequence = quantity_value(
            item["transcript_sequence"],
            name="transcript_sequence",
            positive=True,
        )
        if sequence != record_count:
            raise StrategyProtocolError(
                f"expected transcript sequence {record_count} but received {sequence}"
            )
        expected_direction = "engine_to_strategy" if record_count % 2 else "strategy_to_engine"
        if item["direction"] != expected_direction:
            raise StrategyProtocolError(
                f"transcript sequence {record_count} has the wrong direction"
            )
        message = _message_from_object(item["message"])
        request_sequence = (record_count + 1) // 2
        if message.sequence != request_sequence:
            raise StrategyProtocolError(f"transcript message sequence must be {request_sequence}")
        if expected_direction == "engine_to_strategy":
            if stopped:
                raise StrategyProtocolError("strategy transcript contains data after shutdown")
            if pending is not None:
                raise StrategyProtocolError("strategy transcript contains two outstanding requests")
            if request_sequence == 1:
                if message.message_type != "initialize":
                    raise StrategyProtocolError("strategy transcript must start with initialize")
                initialization = _initialization_from_payload(message.payload)
                if expected_hash is not None and initialization.scenario_sha256 != expected_hash:
                    raise StrategyProtocolError(
                        "strategy transcript scenario SHA-256 does not match"
                    )
                if expected_run_id is not None and initialization.run_id != expected_run_id:
                    raise StrategyProtocolError("strategy transcript run_id does not match")
            elif message.message_type == "event":
                if initialization is None:
                    raise StrategyProtocolError("strategy event precedes initialization")
                _context, event = _event_payload(message.payload)
                if isinstance(event, MarketSliceClosedEvent):
                    pending_slice_sequence = event.market_slice.slice_sequence
                elif isinstance(event, FillReceivedEvent):
                    pending_slice_sequence = cast("int", event.fill.slice_sequence)
                else:
                    # Order and rejection events do not carry a slice identifier.
                    # Receipt timestamps may legally repeat across slices, so a
                    # preceding event cannot disambiguate their decision slice.
                    pending_slice_sequence = None
                event_count += 1
            elif message.message_type == "shutdown":
                _empty_payload(message.payload, name="shutdown payload")
                stopped = True
            else:
                raise StrategyProtocolError("unsupported engine request in strategy transcript")
            pending = message
            continue
        if pending is None:
            raise StrategyProtocolError("strategy response has no matching request")
        response_type = message.message_type
        if response_type == "error":
            error_payload = _exact_fields(message.payload, {"message"}, name="error payload")
            _trimmed_string(error_payload["message"], name="strategy error message")
            raise StrategyProtocolError("successful strategy transcript contains an error response")
        if pending.message_type == "initialize":
            if response_type != "ready":
                raise StrategyProtocolError("initialize request must be followed by ready")
            identity = _identity_from_payload(message.payload)
        elif pending.message_type == "event":
            if response_type != "intents":
                raise StrategyProtocolError("event request must be followed by intents")
            intents = _intents_from_payload(message.payload)
            if intents:
                decisions.append(StrategyDecision(pending_slice_sequence, intents))
        elif pending.message_type == "shutdown":
            if response_type != "stopped":
                raise StrategyProtocolError("shutdown request must be followed by stopped")
            _empty_payload(message.payload, name="stopped payload")
        pending = None
    if record_count == 0:
        raise StrategyProtocolError("strategy transcript must not be empty")
    if record_count % 2 or pending is not None:
        raise StrategyProtocolError("strategy transcript ends with an outstanding request")
    if initialization is None or identity is None:
        raise StrategyProtocolError("strategy transcript is missing initialization")
    if not stopped:
        raise StrategyProtocolError("strategy transcript is missing shutdown")
    return StrategyTranscript(
        path=transcript_path,
        initialization=initialization,
        identity=identity,
        record_count=record_count,
        event_count=event_count,
        decisions=tuple(decisions),
    )


_INTENT_TYPES = (
    TargetWeightsIntent,
    TargetQuantitiesIntent,
    SubmitOrderIntent,
    CancelOrderIntent,
    EmitMetricIntent,
)


def _read_request(source: TextIO, *, expected_sequence: int, sink: TextIO) -> _Message:
    try:
        line = source.readline(STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES + 1)
        if not line:
            raise StrategyProtocolError("external engine closed strategy input")
        if len(line.encode("utf-8")) > STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES:
            raise StrategyProtocolError("strategy request exceeds the maximum message size")
        message = _message_from_json(line)
        if message.sequence != expected_sequence:
            raise StrategyProtocolError(
                f"expected strategy sequence {expected_sequence} but received {message.sequence}"
            )
        return message
    except Exception as error:
        _fail_session(sink, expected_sequence, str(error), cause=error)


def _message_from_json(document: str) -> _Message:
    try:
        value = json.loads(document, object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise StrategyProtocolError(f"invalid strategy protocol JSON: {error}") from error
    return _message_from_object(value)


def _message_from_object(value: object) -> _Message:
    item = _exact_fields(
        value,
        {"strategy_protocol_version", "strategy_sequence", "message_type", "payload"},
        name="strategy message",
    )
    if item["strategy_protocol_version"] != TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION:
        raise StrategyProtocolError(
            f"unsupported strategy protocol version: {item['strategy_protocol_version']!r}"
        )
    return _Message(
        sequence=quantity_value(
            item["strategy_sequence"],
            name="strategy_sequence",
            positive=True,
        ),
        message_type=identifier(item["message_type"], name="message_type"),
        payload=_exact_object(item["payload"], name="strategy payload"),
    )


def _initialization_from_payload(payload: object) -> StrategyInitialization:
    item = _exact_fields(
        payload,
        {
            "engine_version",
            "scenario_contract_version",
            "scenario_sha256",
            "run_id",
            "base_currency",
            "initial_cash",
            "instruments",
            "risk",
            "execution",
            "metadata",
        },
        name="initialize payload",
    )
    return StrategyInitialization(
        engine_version=identifier(item["engine_version"], name="engine_version"),
        scenario_contract_version=identifier(
            item["scenario_contract_version"],
            name="scenario_contract_version",
        ),
        scenario_sha256=_hash(item["scenario_sha256"], name="scenario_sha256"),
        run_id=identifier(item["run_id"], name="run_id"),
        base_currency=identifier(item["base_currency"], name="base_currency"),
        initial_cash=tuple(
            decode_cash_balance(value)
            for value in _array(item["initial_cash"], name="initial_cash")
        ),
        instruments=tuple(
            decode_instrument(value) for value in _array(item["instruments"], name="instruments")
        ),
        risk=decode_risk_policy(item["risk"]),
        execution=decode_execution_policy(item["execution"]),
        metadata=decode_metadata(item["metadata"]),
    )


def _event_payload(payload: object) -> tuple[StrategyContext, StrategyEvent]:
    item = _exact_fields(payload, {"context", "event"}, name="event payload")
    return _context_from_json(item["context"]), _event_from_json(item["event"])


def _context_from_json(value: object) -> StrategyContext:
    item = _exact_fields(
        value,
        {"now", "portfolio", "working_orders", "latest_bars"},
        name="strategy context",
    )
    return StrategyContext(
        now=decode_timestamp(item["now"], name="now"),
        portfolio=_portfolio_from_json(item["portfolio"]),
        working_orders=tuple(
            _order_from_json(order)
            for order in _array(item["working_orders"], name="working_orders")
        ),
        latest_bars=tuple(
            decode_bar(bar) for bar in _array(item["latest_bars"], name="latest_bars")
        ),
    )


def _event_from_json(value: object) -> StrategyEvent:
    raw = _exact_object(value, name="strategy event")
    event_type = raw.get("type")
    if event_type == "market_slice_closed":
        item = _exact_fields(raw, {"type", "market_slice"}, name="market slice event")
        return MarketSliceClosedEvent(decode_slice(item["market_slice"]))
    if event_type == "fill_received":
        item = _exact_fields(raw, {"type", "fill"}, name="fill event")
        return FillReceivedEvent(_fill_from_json(item["fill"]))
    if event_type == "order_updated":
        item = _exact_fields(raw, {"type", "order"}, name="order event")
        return OrderUpdatedEvent(_order_from_json(item["order"]))
    if event_type == "intent_rejected":
        item = _exact_fields(raw, {"type", "reason"}, name="intent rejection event")
        return IntentRejectedEvent(_trimmed_string(item["reason"], name="reason"))
    raise StrategyProtocolError("unsupported strategy event type")


def _position_from_json(value: object) -> StrategyPosition:
    item = _exact_fields(
        value,
        {"instrument_id", "quantity", "mark", "base_market_value", "weight"},
        name="strategy position",
    )
    return StrategyPosition(
        item["instrument_id"],
        item["quantity"],
        item["mark"],
        item["base_market_value"],
        item["weight"],
    )


def _portfolio_from_json(value: object) -> StrategyPortfolio:
    item = _exact_fields(
        value,
        {
            "base_currency",
            "cash",
            "net_market_value",
            "long_market_value",
            "short_market_value",
            "gross_exposure",
            "equity",
            "weights_available",
            "cash_weight",
            "cash_balances",
            "positions",
        },
        name="strategy portfolio",
    )
    balances = tuple(
        _strategy_cash_balance_from_json(balance)
        for balance in _array(item["cash_balances"], name="cash_balances")
    )
    positions = tuple(
        _position_from_json(position)
        for position in _array(item["positions"], name="positions")
    )
    try:
        return StrategyPortfolio(
            base_currency=item["base_currency"],
            cash=item["cash"],
            net_market_value=item["net_market_value"],
            long_market_value=item["long_market_value"],
            short_market_value=item["short_market_value"],
            gross_exposure=item["gross_exposure"],
            equity=item["equity"],
            weights_available=item["weights_available"],
            cash_weight=item["cash_weight"],
            cash_balances=balances,
            positions=positions,
        )
    except (TypeError, ValueError) as error:
        raise StrategyProtocolError(f"invalid strategy portfolio: {error}") from error


def _strategy_cash_balance_from_json(value: object) -> StrategyCashBalance:
    item = _exact_fields(
        value,
        {"currency", "amount", "fx_rate", "base_value"},
        name="strategy cash balance",
    )
    return StrategyCashBalance(
        item["currency"],
        item["amount"],
        item["fx_rate"],
        item["base_value"],
    )


def _order_from_json(value: object) -> StrategyOrder:
    item = _exact_fields(
        value,
        {
            "order_id",
            "instrument_id",
            "side",
            "quantity",
            "order_kind",
            "limit_price",
            "origin",
            "created_event_id",
            "updated_event_id",
            "created_sequence",
            "created_at",
            "eligible_after_slice_sequence",
            "filled_quantity",
            "filled_notional",
            "status",
            "rejection_reason",
        },
        name="strategy order",
    )
    return StrategyOrder(
        order_id=item["order_id"],
        instrument_id=item["instrument_id"],
        side=cast("Any", _choice(item["side"], {"buy", "sell"}, name="side")),
        quantity=item["quantity"],
        order_kind=cast(
            "Any",
            _choice(item["order_kind"], {"market", "limit"}, name="order_kind"),
        ),
        limit_price=item["limit_price"],
        origin=cast(
            "Any",
            _choice(
                item["origin"],
                {"direct", "target_rebalance", "margin_liquidation"},
                name="origin",
            ),
        ),
        created_event_id=item["created_event_id"],
        updated_event_id=item["updated_event_id"],
        created_sequence=item["created_sequence"],
        created_at=decode_timestamp(item["created_at"], name="created_at"),
        eligible_after_slice_sequence=item["eligible_after_slice_sequence"],
        filled_quantity=item["filled_quantity"],
        filled_notional=item["filled_notional"],
        status=cast(
            "Any",
            _choice(
                item["status"],
                {"working", "partially_filled", "filled", "cancelled", "rejected"},
                name="status",
            ),
        ),
        rejection_reason=(
            None
            if item["rejection_reason"] is None
            else _trimmed_string(item["rejection_reason"], name="rejection_reason")
        ),
    )


def _fill_from_json(value: object) -> StrategyFill:
    item = _exact_fields(
        value,
        {
            "fill_id",
            "order_id",
            "instrument_id",
            "quote_currency",
            "side",
            "quantity",
            "price",
            "notional",
            "fee",
            "executed_at",
            "slice_sequence",
        },
        name="strategy fill",
    )
    return StrategyFill(
        fill_id=item["fill_id"],
        order_id=item["order_id"],
        instrument_id=item["instrument_id"],
        quote_currency=item["quote_currency"],
        side=cast("Any", _choice(item["side"], {"buy", "sell"}, name="side")),
        quantity=item["quantity"],
        price=item["price"],
        notional=item["notional"],
        fee=item["fee"],
        executed_at=decode_timestamp(item["executed_at"], name="executed_at"),
        slice_sequence=item["slice_sequence"],
    )


def _identity_from_payload(value: object) -> StrategyIdentity:
    item = _exact_fields(value, {"strategy_name", "strategy_version"}, name="ready payload")
    version = item["strategy_version"]
    return StrategyIdentity(
        identifier(item["strategy_name"], name="strategy_name"),
        None if version is None else _trimmed_string(version, name="strategy_version"),
    )


def _intents_from_payload(value: object) -> tuple[ScenarioIntent, ...]:
    item = _exact_fields(value, {"intents"}, name="intents payload")
    return tuple(decode_intent(intent) for intent in _array(item["intents"], name="intents"))


def _write_message(
    sink: TextIO,
    sequence: int,
    message_type: str,
    payload: Mapping[str, object],
) -> None:
    document = json.dumps(
        {
            "strategy_protocol_version": TRADING_ENGINE_STRATEGY_PROTOCOL_VERSION,
            "strategy_sequence": str(sequence),
            "message_type": message_type,
            "payload": payload,
        },
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(document.encode("utf-8")) > STRATEGY_PROTOCOL_MAX_MESSAGE_BYTES:
        raise StrategyProtocolError("strategy response exceeds the maximum message size")
    sink.write(f"{document}\n")
    sink.flush()


def _fail_callback(sink: TextIO, sequence: int, stage: str, error: Exception) -> None:
    message = f"strategy {stage} failed: {type(error).__name__}: {error}"
    _fail_session(sink, sequence, message, cause=error)


def _fail_session(
    sink: TextIO,
    sequence: int,
    message: str,
    *,
    cause: Exception | None = None,
) -> NoReturn:
    rendered = " ".join(message.split()) or "strategy protocol failed"
    rendered = rendered.encode("utf-8")[:4096].decode("utf-8", errors="ignore")
    try:
        _write_message(sink, sequence, "error", {"message": rendered})
    except Exception:
        pass
    error = StrategyProtocolError(rendered)
    if cause is None:
        raise error
    raise error from cause


def _transcript_records(path: Path) -> Iterator[object]:
    with path.open("rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            if len(line) > _TRANSCRIPT_RECORD_MAX_BYTES:
                raise StrategyProtocolError(
                    f"strategy transcript line {line_number} exceeds the maximum size"
                )
            try:
                yield json.loads(line.decode("utf-8"), object_pairs_hook=_unique_object)
            except (json.JSONDecodeError, UnicodeError) as error:
                raise StrategyProtocolError(
                    f"strategy transcript line {line_number} is invalid JSON: {error}"
                ) from error


def _exact_fields(
    value: object,
    expected: set[str],
    *,
    name: str,
) -> dict[str, Any]:
    result = _exact_object(value, name=name)
    if set(result) != expected:
        missing = sorted(expected.difference(result))
        extra = sorted(set(result).difference(expected))
        raise StrategyProtocolError(f"{name} fields differ: missing={missing}, extra={extra}")
    return result


def _exact_object(value: object, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StrategyProtocolError(f"{name} must be a JSON object")
    return cast("dict[str, Any]", value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise StrategyProtocolError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _array(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise StrategyProtocolError(f"{name} must be a JSON array")
    return cast("list[object]", value)


def _empty_payload(value: object, *, name: str) -> None:
    _exact_fields(value, set(), name=name)


def _choice(value: object, choices: set[str], *, name: str) -> str:
    checked = identifier(value, name=name)
    if checked not in choices:
        raise StrategyProtocolError(f"unsupported {name} {checked!r}")
    return checked


def _hash(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _trimmed_string(value: object, *, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be a nonempty trimmed string")
    return value


def _checked_timestamp(value: object, *, name: str) -> pd.Timestamp:
    if not isinstance(value, pd.Timestamp):
        raise TypeError(f"{name} must be a pandas Timestamp")
    if pd.isna(value) or value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    result = value.tz_convert("UTC")
    if result.nanosecond % 1_000:
        raise ValueError(f"{name} must not exceed microsecond precision")
    return result


def _require_tuple(value: object, *, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")


def _freeze_mapping(value: Mapping[str, object], *, name: str) -> Mapping[str, object]:
    raw_value = cast("object", value)
    if not isinstance(raw_value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    result: dict[str, object] = {}
    for key, item in cast("Mapping[object, object]", raw_value).items():
        if not isinstance(key, str):
            raise TypeError(f"{name} keys must be strings")
        result[key] = _freeze_json(item, name=name)
    return MappingProxyType(result)


def _freeze_json(value: object, *, name: str) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(cast("Mapping[str, object]", value), name=name)
    if isinstance(value, list | tuple):
        return tuple(_freeze_json(item, name=name) for item in cast("Sequence[object]", value))
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"{name} must contain JSON-compatible values")
