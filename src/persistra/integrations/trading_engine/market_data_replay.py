"""Causal Trading Engine quote, trade, and order-book replay contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.integrations.trading_engine._scalars import (
    decimal_string,
    decimal_value,
    identifier,
    quantity_value,
)
from persistra.integrations.trading_engine.contracts import (
    SchemaReplayResult,
    TradingEngineContractError,
    TradingEngineContractSchemas,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from persistra.integrations.trading_engine.risk_financing import InstrumentFeeSchedule


MARKET_DATA_CONTRACT_VERSION: Final = "1"
MAX_MARKET_EVENTS_PER_SLICE: Final = 4096
type MarketDataModel = Literal["quote_trade_v1", "order_book_v1"]
type AggressorSide = Literal["buy", "sell", "unknown"]
type BookSide = Literal["bid", "ask"]


@dataclass(frozen=True, slots=True)
class ObservationProvenance:
    """Provider and normalized-dataset ordering retained beside an engine event."""

    provider: str
    dataset_id: str
    dataset_sequence: int
    ingested_at: datetime | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", identifier(self.provider, name="provider"))
        object.__setattr__(self, "dataset_id", identifier(self.dataset_id, name="dataset_id"))
        object.__setattr__(
            self,
            "dataset_sequence",
            quantity_value(self.dataset_sequence, name="dataset_sequence", positive=True),
        )
        object.__setattr__(self, "ingested_at", _timestamp(self.ingested_at, name="ingested_at"))

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "dataset_id": self.dataset_id,
            "dataset_sequence": str(self.dataset_sequence),
            "ingested_at": _timestamp_string(cast("datetime", self.ingested_at)),
        }


@dataclass(frozen=True, slots=True)
class ReplayEventClock:
    """Economic, availability, receipt, and ingest ordering for one observation."""

    event_at: datetime | str
    available_at: datetime | str
    received_at: datetime | str
    ingest_sequence: int

    def __post_init__(self) -> None:
        for name in ("event_at", "available_at", "received_at"):
            object.__setattr__(self, name, _timestamp(getattr(self, name), name=name))
        event_at = cast("datetime", self.event_at)
        available_at = cast("datetime", self.available_at)
        received_at = cast("datetime", self.received_at)
        if not event_at <= available_at <= received_at:
            raise ValueError("event, availability, and receipt clocks must be causal")
        object.__setattr__(
            self,
            "ingest_sequence",
            quantity_value(self.ingest_sequence, name="ingest_sequence", positive=True),
        )

    @property
    def causal_key(self) -> tuple[datetime, datetime, int]:
        return (
            cast("datetime", self.available_at),
            cast("datetime", self.received_at),
            self.ingest_sequence,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "event_at": _timestamp_string(cast("datetime", self.event_at)),
            "available_at": _timestamp_string(cast("datetime", self.available_at)),
            "received_at": _timestamp_string(cast("datetime", self.received_at)),
            "ingest_sequence": str(self.ingest_sequence),
        }


@dataclass(frozen=True, slots=True)
class ExecutableQuote:
    """Two-sided displayed quote with positive executable liquidity."""

    instrument_id: str
    clock: ReplayEventClock
    provenance: ObservationProvenance
    bid_price: Decimal | str | int | float
    bid_quantity: Decimal | str | int | float
    ask_price: Decimal | str | int | float
    ask_quantity: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", identifier(self.instrument_id, name="instrument_id")
        )
        for name in ("bid_price", "bid_quantity", "ask_price", "ask_quantity"):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=name, positive=True),
            )
        if cast("Decimal", self.bid_price) > cast("Decimal", self.ask_price):
            raise ValueError("executable quote must not be crossed")
        _require_ingested_after_receipt(self.clock, self.provenance)

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "quote",
            "instrument_id": self.instrument_id,
            **self.clock.to_dict(),
            "bid_price": _decimal(self.bid_price),
            "bid_quantity": _decimal(self.bid_quantity),
            "ask_price": _decimal(self.ask_price),
            "ask_quantity": _decimal(self.ask_quantity),
        }


@dataclass(frozen=True, slots=True)
class ExecutableTrade:
    """Print with explicit aggressor classification and executable quantity."""

    instrument_id: str
    clock: ReplayEventClock
    provenance: ObservationProvenance
    price: Decimal | str | int | float
    quantity: Decimal | str | int | float
    aggressor_side: AggressorSide

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", identifier(self.instrument_id, name="instrument_id")
        )
        object.__setattr__(
            self, "price", decimal_value(self.price, name="trade price", positive=True)
        )
        object.__setattr__(
            self,
            "quantity",
            decimal_value(self.quantity, name="trade quantity", positive=True),
        )
        _choice(self.aggressor_side, {"buy", "sell", "unknown"}, name="aggressor_side")
        _require_ingested_after_receipt(self.clock, self.provenance)

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "trade",
            "instrument_id": self.instrument_id,
            **self.clock.to_dict(),
            "price": _decimal(self.price),
            "quantity": _decimal(self.quantity),
            "aggressor_side": self.aggressor_side,
        }


@dataclass(frozen=True, slots=True)
class OrderBookLevel:
    """One absolute level-two price and displayed quantity."""

    price: Decimal | str | int | float
    quantity: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "price", decimal_value(self.price, name="book price", positive=True)
        )
        object.__setattr__(
            self,
            "quantity",
            decimal_value(self.quantity, name="book quantity", positive=True),
        )

    def to_dict(self) -> dict[str, object]:
        return {"price": _decimal(self.price), "quantity": _decimal(self.quantity)}


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    """Complete per-instrument opening book for one slice."""

    instrument_id: str
    clock: ReplayEventClock
    provenance: ObservationProvenance
    book_sequence: int
    bids: tuple[OrderBookLevel, ...]
    asks: tuple[OrderBookLevel, ...]

    def __post_init__(self) -> None:
        _book_common(self)
        bids = tuple(sorted(self.bids, key=lambda item: cast("Decimal", item.price), reverse=True))
        asks = tuple(sorted(self.asks, key=lambda item: cast("Decimal", item.price)))
        if not bids or not asks:
            raise ValueError("order-book snapshot requires bid and ask depth")
        _unique((_decimal(item.price) for item in bids), name="snapshot bid prices")
        _unique((_decimal(item.price) for item in asks), name="snapshot ask prices")
        if cast("Decimal", bids[0].price) > cast("Decimal", asks[0].price):
            raise ValueError("order-book snapshot must not be crossed")
        object.__setattr__(self, "bids", bids)
        object.__setattr__(self, "asks", asks)

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "snapshot",
            "instrument_id": self.instrument_id,
            **self.clock.to_dict(),
            "book_sequence": str(self.book_sequence),
            "bids": [item.to_dict() for item in self.bids],
            "asks": [item.to_dict() for item in self.asks],
        }


@dataclass(frozen=True, slots=True)
class OrderBookSet:
    """Absolute set update for one side and price."""

    instrument_id: str
    clock: ReplayEventClock
    provenance: ObservationProvenance
    book_sequence: int
    side: BookSide
    price: Decimal | str | int | float
    quantity: Decimal | str | int | float

    def __post_init__(self) -> None:
        _book_common(self)
        _choice(self.side, {"bid", "ask"}, name="book side")
        object.__setattr__(
            self, "price", decimal_value(self.price, name="book price", positive=True)
        )
        object.__setattr__(
            self,
            "quantity",
            decimal_value(self.quantity, name="book quantity", positive=True),
        )

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "set",
            "instrument_id": self.instrument_id,
            **self.clock.to_dict(),
            "book_sequence": str(self.book_sequence),
            "side": self.side,
            "price": _decimal(self.price),
            "quantity": _decimal(self.quantity),
        }


@dataclass(frozen=True, slots=True)
class OrderBookDelete:
    """Delete update for an explicitly existing side and price."""

    instrument_id: str
    clock: ReplayEventClock
    provenance: ObservationProvenance
    book_sequence: int
    side: BookSide
    price: Decimal | str | int | float

    def __post_init__(self) -> None:
        _book_common(self)
        _choice(self.side, {"bid", "ask"}, name="book side")
        object.__setattr__(
            self, "price", decimal_value(self.price, name="book price", positive=True)
        )

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "delete",
            "instrument_id": self.instrument_id,
            **self.clock.to_dict(),
            "book_sequence": str(self.book_sequence),
            "side": self.side,
            "price": _decimal(self.price),
        }


@dataclass(frozen=True, slots=True)
class OrderBookTrade:
    """Aggressor-classified depth-consuming book trade."""

    instrument_id: str
    clock: ReplayEventClock
    provenance: ObservationProvenance
    book_sequence: int
    price: Decimal | str | int | float
    quantity: Decimal | str | int | float
    aggressor_side: AggressorSide

    def __post_init__(self) -> None:
        _book_common(self)
        object.__setattr__(
            self, "price", decimal_value(self.price, name="trade price", positive=True)
        )
        object.__setattr__(
            self,
            "quantity",
            decimal_value(self.quantity, name="trade quantity", positive=True),
        )
        _choice(self.aggressor_side, {"buy", "sell", "unknown"}, name="aggressor_side")

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "trade",
            "instrument_id": self.instrument_id,
            **self.clock.to_dict(),
            "book_sequence": str(self.book_sequence),
            "price": _decimal(self.price),
            "quantity": _decimal(self.quantity),
            "aggressor_side": self.aggressor_side,
        }


type QuoteTradeObservation = ExecutableQuote | ExecutableTrade
type OrderBookObservation = OrderBookSnapshot | OrderBookSet | OrderBookDelete | OrderBookTrade


@dataclass(frozen=True, slots=True)
class ReplaySliceMarketData:
    """Causally ordered executable observations assigned to one market slice."""

    slice_sequence: int
    market_events: tuple[QuoteTradeObservation, ...] = ()
    order_book_events: tuple[OrderBookObservation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "slice_sequence",
            quantity_value(self.slice_sequence, name="slice_sequence", positive=True),
        )
        market = tuple(sorted(self.market_events, key=lambda item: item.clock.causal_key))
        books = tuple(sorted(self.order_book_events, key=lambda item: item.clock.causal_key))
        if len(market) + len(books) > MAX_MARKET_EVENTS_PER_SLICE:
            raise ValueError("market-data slice exceeds the bounded observation limit")
        _validate_observation_order((*market, *books))
        object.__setattr__(self, "market_events", market)
        object.__setattr__(self, "order_book_events", books)

    def provenance_dict(self) -> dict[str, object]:
        rows = [
            {
                "family": family,
                "instrument_id": item.instrument_id,
                "ingest_sequence": str(item.clock.ingest_sequence),
                **item.provenance.to_dict(),
            }
            for family, values in (
                ("quote_trade", self.market_events),
                ("order_book", self.order_book_events),
            )
            for item in values
        ]
        return {"slice_sequence": str(self.slice_sequence), "observations": rows}


@dataclass(frozen=True, slots=True)
class MarketDataExecutionPolicy:
    """Selected v1 model, fee schedules, and bounded depth configuration."""

    model: MarketDataModel
    participation_bps: int
    fee_schedules: tuple[InstrumentFeeSchedule, ...]
    max_depth_levels: int | None = None
    configuration_version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        _choice(self.model, {"quote_trade_v1", "order_book_v1"}, name="market-data model")
        _basis_points(self.participation_bps, name="participation_bps")
        schedules = tuple(sorted(self.fee_schedules, key=lambda item: item.instrument_id))
        if not schedules:
            raise ValueError("fee_schedules must not be empty")
        _unique((item.instrument_id for item in schedules), name="fee schedule instruments")
        object.__setattr__(self, "fee_schedules", schedules)
        if self.model == "order_book_v1":
            depth = cast("object", self.max_depth_levels)
            if isinstance(depth, bool) or not isinstance(depth, int) or not 1 <= depth <= 1024:
                raise ValueError("order_book_v1 max_depth_levels must be between 1 and 1024")
        elif self.max_depth_levels is not None:
            raise ValueError("quote_trade_v1 does not accept max_depth_levels")

    def to_dict(self) -> dict[str, object]:
        configuration: dict[str, object] = {
            "version": self.configuration_version,
            "participation_bps": self.participation_bps,
            "fee_schedules": [item.to_dict() for item in self.fee_schedules],
        }
        if self.max_depth_levels is not None:
            configuration["max_depth_levels"] = self.max_depth_levels
        return {"model": self.model, "configuration": configuration}


@dataclass(frozen=True, slots=True)
class MarketDataModelCapability:
    """Required configuration and normalized data declared for one engine model."""

    name: str
    configuration_versions: tuple[str, ...]
    scenario_contract_versions: tuple[str, ...]
    required_fields: tuple[str, ...]
    data_requirements: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, name="model name"))
        for field in (
            "configuration_versions",
            "scenario_contract_versions",
            "required_fields",
            "data_requirements",
        ):
            values = tuple(identifier(item, name=field) for item in getattr(self, field))
            if not values:
                raise ValueError(f"{field} must not be empty")
            _unique(values, name=field)
            object.__setattr__(self, field, values)


@dataclass(frozen=True, slots=True)
class MarketDataReplayScenario:
    """Immutable schema-v1 scenario plus lossless observation provenance."""

    document: Mapping[str, Any]
    execution: MarketDataExecutionPolicy
    slices: tuple[ReplaySliceMarketData, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "document",
            freeze_portable_mapping(self.document, name="market-data replay scenario"),
        )
        object.__setattr__(self, "slices", tuple(self.slices))

    @property
    def contract_version(self) -> str:
        return MARKET_DATA_CONTRACT_VERSION

    @property
    def run_id(self) -> str:
        return cast("str", self.document["run_id"])

    def to_dict(self) -> dict[str, Any]:
        return thaw_portable_mapping(self.document)


@dataclass(frozen=True, slots=True)
class MarketDataReplayResult:
    """Schema replay with source-matched model-specific fills."""

    replay: SchemaReplayResult
    model: MarketDataModel
    market_slices: tuple[Mapping[str, object], ...]
    fills: tuple[Mapping[str, object], ...]
    matched_fill_sources: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        for name in ("market_slices", "fills", "matched_fill_sources"):
            object.__setattr__(
                self,
                name,
                tuple(
                    freeze_portable_mapping(item, name=name)
                    for item in cast("tuple[Mapping[str, Any], ...]", getattr(self, name))
                ),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.replay.contract_version,
            "run_id": self.replay.run_id,
            "scenario_sha256": self.replay.scenario_sha256,
            "model": self.model,
            "market_slices": len(self.market_slices),
            "fills": len(self.fills),
            "matched_fill_sources": len(self.matched_fill_sources),
            "status": "verified",
        }


def market_data_model_capabilities(
    value: Mapping[str, Any],
) -> tuple[MarketDataModelCapability, ...]:
    """Parse the exact market-data execution capability declarations."""
    raw = value.get("execution_model_contracts")
    if not isinstance(raw, list):
        raise ValueError("engine capabilities omit execution_model_contracts")
    selected: list[MarketDataModelCapability] = []
    for candidate in cast("list[object]", raw):
        item = _mapping(candidate, name="execution model capability")
        if item.get("name") not in {"quote_trade_v1", "order_book_v1"}:
            continue
        selected.append(
            MarketDataModelCapability(
                cast("str", item["name"]),
                _strings(item.get("configuration_versions"), name="configuration_versions"),
                _strings(item.get("scenario_contract_versions"), name="scenario_contract_versions"),
                _strings(item.get("required_fields"), name="required_fields"),
                _strings(item.get("data_requirements"), name="data_requirements"),
            )
        )
    return tuple(sorted(selected, key=lambda item: item.name))


def require_market_data_capabilities(
    capabilities: Mapping[str, Any],
    schemas: TradingEngineContractSchemas,
    policy: MarketDataExecutionPolicy,
    *,
    scenario_format: Literal["json", "jsonl"] = "json",
) -> None:
    """Negotiate model, configuration, contract, format, and data requirements."""
    _require_contract(schemas)
    models = {item.name: item for item in market_data_model_capabilities(capabilities)}
    selected = models.get(policy.model)
    if selected is None:
        raise ValueError(f"engine capabilities omit {policy.model}")
    expected_requirements = {
        "quote_trade_v1": {
            "causally_ordered_bid_ask_quotes",
            "aggressor_classified_trades_for_passive_fills",
            "completed_bars_for_valuation",
        },
        "order_book_v1": {
            "slice_open_level_two_snapshot",
            "contiguous_absolute_level_updates",
            "aggressor_classified_depth_consuming_trades",
            "completed_bars_for_valuation",
        },
    }[policy.model]
    requirements = (
        (policy.configuration_version in selected.configuration_versions, "configuration version"),
        (
            MARKET_DATA_CONTRACT_VERSION in selected.scenario_contract_versions,
            "scenario contract v1",
        ),
        (expected_requirements.issubset(selected.data_requirements), "model data requirements"),
        (
            scenario_format
            in _strings(capabilities.get("scenario_formats"), name="scenario_formats"),
            "scenario format",
        ),
        (
            "jsonl" in _strings(capabilities.get("journal_formats"), name="journal_formats"),
            "journal format",
        ),
    )
    missing = [name for supported, name in requirements if not supported]
    if missing:
        raise ValueError("incompatible market-data capabilities: missing " + ", ".join(missing))


def build_market_data_replay_scenario(
    *,
    schemas: TradingEngineContractSchemas,
    base_scenario: Mapping[str, Any],
    execution: MarketDataExecutionPolicy,
    slices: Sequence[ReplaySliceMarketData],
) -> MarketDataReplayScenario:
    """Map executable observations into a validated bounded v1 scenario and stream."""
    _require_contract(schemas)
    selected_slices = tuple(sorted(slices, key=lambda item: item.slice_sequence))
    _unique((item.slice_sequence for item in selected_slices), name="market-data slice sequences")
    _validate_model_families(selected_slices, model=execution.model)
    document = thaw_portable_mapping(
        freeze_portable_mapping(base_scenario, name="base Trading Engine scenario")
    )
    document["contract_version"] = MARKET_DATA_CONTRACT_VERSION
    document["execution"] = execution.to_dict()
    raw_slices = cast("list[object]", document.get("slices"))
    by_sequence = {str(item.slice_sequence): item for item in selected_slices}
    instruments = _instrument_contracts(document)
    for index, raw in enumerate(raw_slices):
        item = _mapping(raw, name="market slice")
        sequence = cast("str", item.get("slice_sequence"))
        observations = by_sequence.pop(sequence, None)
        if observations is None:
            raise ValueError("every base market slice requires explicit market-data observations")
        _validate_slice_bounds(item, observations)
        _validate_observations(observations, instruments=instruments, execution=execution)
        item["market_events"] = [event.to_contract_dict() for event in observations.market_events]
        item["order_book_events"] = [
            event.to_contract_dict() for event in observations.order_book_events
        ]
        cast("list[dict[str, object]]", document["slices"])[index] = item
    if by_sequence:
        raise ValueError("market-data observations refer to an unknown slice")
    schemas.validate_scenario(document)
    for line_number, record in enumerate(_stream_records(document), start=1):
        schemas.validate_stream_record(record, line_number=line_number)
    return MarketDataReplayScenario(
        document,
        execution,
        selected_slices,
        hashlib.sha256(_canonical_json(document)).hexdigest(),
    )


def market_data_scenario_to_json(
    scenario: MarketDataReplayScenario, *, indent: int | None = 2
) -> str:
    """Serialize one v1 batch market-data scenario."""
    if indent is not None and (type(indent) is bool or indent < 0):
        raise ValueError("indent must be a nonnegative integer or None")
    return (
        json.dumps(
            scenario.to_dict(),
            allow_nan=False,
            indent=indent,
            sort_keys=True,
            separators=(",", ":") if indent is None else None,
        )
        + "\n"
    )


def market_data_scenario_to_jsonl(scenario: MarketDataReplayScenario) -> str:
    """Serialize one bounded v1 scenario stream."""
    return "".join(
        json.dumps(item, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in _stream_records(scenario.to_dict())
    )


def write_market_data_scenario(
    scenario: MarketDataReplayScenario,
    path: str | Path,
    *,
    stream: bool = False,
    overwrite: bool = False,
) -> Path:
    """Write a batch or streaming scenario without replacement by default."""
    from pathlib import Path

    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = (
        market_data_scenario_to_jsonl(scenario)
        if stream
        else market_data_scenario_to_json(scenario)
    )
    with output.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return output


def bind_market_data_manifest(
    manifest: Mapping[str, Any], scenario: MarketDataReplayScenario
) -> Mapping[str, Any]:
    """Bind selected model and lossless normalized observation provenance."""
    document = thaw_portable_mapping(freeze_portable_mapping(manifest, name="replay manifest"))
    contract = document.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("replay manifest contract differs from market-data scenario")
    if cast("dict[str, object]", contract).get("version") != scenario.contract_version:
        raise ValueError("replay manifest contract differs from market-data scenario")
    if "market_data" in document:
        raise ValueError("replay manifest already contains market_data")
    provenance = [item.provenance_dict() for item in scenario.slices]
    document["market_data"] = {
        "contract_version": scenario.contract_version,
        "model": scenario.execution.model,
        "scenario_content_sha256": scenario.content_sha256,
        "provenance_sha256": hashlib.sha256(_canonical_json(provenance)).hexdigest(),
        "slices": provenance,
    }
    return freeze_portable_mapping(document, name="replay manifest")


def reconcile_market_data_replay(
    schemas: TradingEngineContractSchemas,
    scenario_path: str | Path,
    journal_path: str | Path,
) -> MarketDataReplayResult:
    """Reconcile received observations and every fill to executable source liquidity."""
    _require_contract(schemas)
    replay = schemas.read_replay(scenario_path, journal_path)
    model = cast("MarketDataModel", replay.execution_model)
    if model not in {"quote_trade_v1", "order_book_v1"}:
        raise TradingEngineContractError("replay does not use a market-data execution model")
    try:
        scenario = json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TradingEngineContractError("invalid market-data scenario JSON") from error
    scenario_item = _mapping(scenario, name="market-data scenario")
    expected: dict[str, Mapping[str, object]] = {
        cast("str", item["slice_sequence"]): item
        for item in (
            _mapping(raw, name="scenario market slice")
            for raw in cast("list[object]", scenario_item.get("slices"))
        )
    }
    received: list[Mapping[str, object]] = []
    fills: list[Mapping[str, object]] = []
    for event in replay.events:
        event_type = event.get("event_type")
        if event_type == "market_slice_received":
            payload = _mapping(event.get("payload"), name="market_slice_received payload")
            _reconcile_received_slice(payload, expected)
            received.append(payload)
        elif event_type == "fill_applied":
            fills.append(_mapping(event.get("payload"), name="fill_applied payload"))
    if expected:
        raise TradingEngineContractError("journal omits scenario market slices")
    remaining_liquidity: dict[tuple[object, ...], Decimal] = {}
    matches = tuple(
        _match_fill_source(
            fill,
            received,
            model=model,
            remaining_liquidity=remaining_liquidity,
        )
        for fill in fills
    )
    return MarketDataReplayResult(replay, model, tuple(received), tuple(fills), matches)


def _validate_observations(
    data: ReplaySliceMarketData,
    *,
    instruments: Mapping[str, tuple[Decimal, Decimal]],
    execution: MarketDataExecutionPolicy,
) -> None:
    for event in (*data.market_events, *data.order_book_events):
        contract = instruments.get(event.instrument_id)
        if contract is None:
            raise ValueError("market-data observation refers to an unknown instrument")
        tick, lot = contract
        payload = event.to_contract_dict()
        for name in ("bid_price", "ask_price", "price"):
            if name in payload and decimal_value(payload[name], name=name) % tick != 0:
                raise ValueError("market-data price is not aligned to instrument tick")
        for name in ("bid_quantity", "ask_quantity", "quantity"):
            if name in payload and decimal_value(payload[name], name=name) % lot != 0:
                raise ValueError("market-data quantity is not aligned to instrument lot")
        if isinstance(event, OrderBookSnapshot):
            if execution.max_depth_levels is None:
                raise ValueError("order-book snapshot requires a depth limit")
            if (
                len(event.bids) > execution.max_depth_levels
                or len(event.asks) > execution.max_depth_levels
            ):
                raise ValueError("order-book snapshot exceeds configured depth")
            for level in (*event.bids, *event.asks):
                if (
                    cast("Decimal", level.price) % tick != 0
                    or cast("Decimal", level.quantity) % lot != 0
                ):
                    raise ValueError("order-book level is not tick and lot aligned")
    if data.order_book_events:
        _validate_book_updates(data.order_book_events, execution=execution)


def _validate_book_updates(
    events: Sequence[OrderBookObservation], *, execution: MarketDataExecutionPolicy
) -> None:
    by_instrument: dict[str, list[OrderBookObservation]] = {}
    for event in events:
        by_instrument.setdefault(event.instrument_id, []).append(event)
    for instrument_events in by_instrument.values():
        first = instrument_events[0]
        if not isinstance(first, OrderBookSnapshot):
            raise ValueError("each instrument book bundle must begin with a complete snapshot")
        bids = {_decimal(item.price): _decimal(item.quantity) for item in first.bids}
        asks = {_decimal(item.price): _decimal(item.quantity) for item in first.asks}
        previous = first.book_sequence
        for event in instrument_events[1:]:
            if event.book_sequence != previous + 1:
                raise ValueError("order-book sequences must be contiguous")
            previous = event.book_sequence
            if isinstance(event, OrderBookSet):
                selected = bids if event.side == "bid" else asks
                selected[_decimal(event.price)] = _decimal(event.quantity)
            elif isinstance(event, OrderBookDelete):
                selected = bids if event.side == "bid" else asks
                if selected.pop(_decimal(event.price), None) is None:
                    raise ValueError("order-book delete refers to missing depth")
            if execution.max_depth_levels is not None:
                if len(bids) > execution.max_depth_levels or len(asks) > execution.max_depth_levels:
                    raise ValueError("order-book update exceeds configured depth")
            if bids and asks and max(map(Decimal, bids)) > min(map(Decimal, asks)):
                raise ValueError("order-book update creates a crossed book")


def _validate_observation_order(
    observations: Sequence[QuoteTradeObservation | OrderBookObservation],
) -> None:
    ingest = [item.clock.ingest_sequence for item in observations]
    _unique(ingest, name="slice ingest sequences")
    datasets: dict[str, list[int]] = {}
    for item in sorted(observations, key=lambda candidate: candidate.clock.causal_key):
        datasets.setdefault(item.provenance.dataset_id, []).append(item.provenance.dataset_sequence)
    for sequences in datasets.values():
        if sequences != sorted(sequences):
            raise ValueError("dataset sequence conflicts with causal replay order")


def _validate_slice_bounds(item: Mapping[str, object], data: ReplaySliceMarketData) -> None:
    start = _timestamp(item.get("start_at"), name="slice start_at")
    end = _timestamp(item.get("end_at"), name="slice end_at")
    received = _timestamp(item.get("received_at"), name="slice received_at")
    for event in (*data.market_events, *data.order_book_events):
        event_at = cast("datetime", event.clock.event_at)
        if not start <= event_at <= end:
            raise ValueError("market-data economic time falls outside its slice")
        if cast("datetime", event.clock.received_at) > received:
            raise ValueError("market-data receipt time exceeds its slice receipt time")


def _validate_model_families(
    slices: Sequence[ReplaySliceMarketData], *, model: MarketDataModel
) -> None:
    market = sum((len(item.market_events) for item in slices), 0)
    books = sum((len(item.order_book_events) for item in slices), 0)
    if model == "quote_trade_v1" and (not market or books):
        raise ValueError("quote_trade_v1 requires only quote and trade observations")
    if model == "order_book_v1" and (not books or market):
        raise ValueError("order_book_v1 requires only order-book observations")


def _reconcile_received_slice(
    payload: Mapping[str, object], expected: dict[str, Mapping[str, object]]
) -> None:
    sequence = payload.get("slice_sequence")
    if not isinstance(sequence, str) or sequence not in expected:
        raise TradingEngineContractError("journal market slice sequence is not in scenario")
    source = expected.pop(sequence)
    for family in ("market_events", "order_book_events"):
        actual_events = cast("list[object]", payload.get(family))
        source_events = cast("list[object]", source.get(family))
        if len(actual_events) != len(source_events):
            raise TradingEngineContractError(f"journal {family} count differs from scenario")
        for actual, declared in zip(actual_events, source_events, strict=True):
            if _normalized_event(_mapping(actual, name=family)) != _normalized_event(
                _mapping(declared, name=family)
            ):
                raise TradingEngineContractError(f"journal {family} differs from scenario")


def _match_fill_source(
    fill: Mapping[str, object],
    slices: Sequence[Mapping[str, object]],
    *,
    model: MarketDataModel,
    remaining_liquidity: dict[tuple[object, ...], Decimal],
) -> Mapping[str, object]:
    sequence = fill.get("slice_sequence")
    instrument = fill.get("instrument_id")
    executed_at = _timestamp(fill.get("executed_at"), name="fill executed_at")
    price = _number(fill, "price")
    quantity = _number(fill, "quantity")
    side = fill.get("side")
    if side not in {"buy", "sell"}:
        raise TradingEngineContractError("fill side is not executable")
    family = "market_events" if model == "quote_trade_v1" else "order_book_events"
    candidates: list[dict[str, object]] = []
    for slice_payload in slices:
        if slice_payload.get("slice_sequence") != sequence:
            continue
        for raw in cast("list[object]", slice_payload.get(family)):
            event = _mapping(raw, name="fill source event")
            if event.get("instrument_id") != instrument:
                continue
            if _timestamp(event.get("event_at"), name="source event_at") != executed_at:
                continue
            event_type = event.get("type")
            if event_type == "quote":
                price_name, quantity_name = (
                    ("ask_price", "ask_quantity")
                    if side == "buy"
                    else ("bid_price", "bid_quantity")
                )
                prices = {decimal_value(event.get(price_name), name=price_name)}
                liquidity = decimal_value(event.get(quantity_name), name=quantity_name)
            elif event_type == "trade":
                expected_aggressor = "sell" if side == "buy" else "buy"
                if event.get("aggressor_side") != expected_aggressor:
                    continue
                prices = {decimal_value(event.get("price"), name="trade price")}
                liquidity = decimal_value(event.get("quantity"), name="trade quantity")
            else:
                continue
            source_key = (
                sequence,
                instrument,
                family,
                event.get("ingest_sequence"),
                event.get("book_sequence"),
            )
            remaining = remaining_liquidity.setdefault(source_key, liquidity)
            if price in prices and quantity <= remaining:
                candidates.append(event)
    if len(candidates) != 1:
        raise TradingEngineContractError("fill does not match exactly one executable market event")
    source = candidates[0]
    source_key = (
        sequence,
        instrument,
        family,
        source.get("ingest_sequence"),
        source.get("book_sequence"),
    )
    remaining_liquidity[source_key] -= quantity
    return {
        "fill_id": fill.get("fill_id"),
        "slice_sequence": sequence,
        "instrument_id": instrument,
        "source_type": source.get("type"),
        "source_event_at": _timestamp_string(executed_at),
        "source_ingest_sequence": source.get("ingest_sequence"),
    }


def _normalized_event(value: Mapping[str, object]) -> dict[str, object]:
    result = cast("dict[str, object]", thaw_portable_mapping(value))
    for name in ("event_at", "available_at", "received_at"):
        result[name] = _timestamp_string(_timestamp(result.get(name), name=name))
    return result


def _instrument_contracts(document: Mapping[str, Any]) -> dict[str, tuple[Decimal, Decimal]]:
    result: dict[str, tuple[Decimal, Decimal]] = {}
    for raw in cast("list[object]", document.get("instruments")):
        item = _mapping(raw, name="instrument")
        instrument_id = cast("str", item.get("instrument_id"))
        result[instrument_id] = (
            decimal_value(item.get("tick_size"), name="tick_size", positive=True),
            decimal_value(item.get("lot_size"), name="lot_size", positive=True),
        )
    return result


def _stream_records(document: Mapping[str, Any]) -> tuple[dict[str, object], ...]:
    header = {
        key: value
        for key, value in document.items()
        if key not in {"contract_version", "schedule", "slices"}
    }
    intents: dict[str, object] = {}
    for raw in cast("list[object]", document.get("schedule")):
        item = _mapping(raw, name="schedule item")
        sequence = item.get("after_slice_sequence")
        if not isinstance(sequence, str) or sequence in intents:
            raise ValueError("schedule sequences must be unique canonical strings")
        intents[sequence] = item.get("intents")
    records: list[dict[str, object]] = [
        {
            "contract_version": MARKET_DATA_CONTRACT_VERSION,
            "scenario_sequence": "1",
            "record_type": "scenario_header",
            "payload": header,
        }
    ]
    slices = cast("list[object]", document.get("slices"))
    for index, raw in enumerate(slices, start=2):
        item = _mapping(raw, name="market slice")
        sequence = item.get("slice_sequence")
        if not isinstance(sequence, str):
            raise ValueError("slice_sequence must be a canonical string")
        records.append(
            {
                "contract_version": MARKET_DATA_CONTRACT_VERSION,
                "scenario_sequence": str(index),
                "record_type": "market_slice",
                "payload": {"market_slice": item, "intents": intents.pop(sequence, [])},
            }
        )
    if intents:
        raise ValueError("schedule refers to a missing market slice")
    records.append(
        {
            "contract_version": MARKET_DATA_CONTRACT_VERSION,
            "scenario_sequence": str(len(records) + 1),
            "record_type": "scenario_end",
            "payload": {"slice_count": str(len(slices))},
        }
    )
    return tuple(records)


def _book_common(
    value: OrderBookSnapshot | OrderBookSet | OrderBookDelete | OrderBookTrade,
) -> None:
    object.__setattr__(
        value, "instrument_id", identifier(value.instrument_id, name="instrument_id")
    )
    object.__setattr__(
        value,
        "book_sequence",
        quantity_value(value.book_sequence, name="book_sequence", positive=True),
    )
    _require_ingested_after_receipt(value.clock, value.provenance)


def _require_ingested_after_receipt(
    clock: ReplayEventClock, provenance: ObservationProvenance
) -> None:
    if cast("datetime", provenance.ingested_at) < cast("datetime", clock.received_at):
        raise ValueError("ingested_at must not precede received_at")


def _require_contract(schemas: TradingEngineContractSchemas) -> None:
    if schemas.version != MARKET_DATA_CONTRACT_VERSION:
        raise ValueError("market-data replay requires Trading Engine contract v1")


def _mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TradingEngineContractError(f"{name} must be an object")
    result: dict[str, object] = {}
    for key, item in cast("Mapping[object, object]", value).items():
        if not isinstance(key, str):
            raise TradingEngineContractError(f"{name} keys must be strings")
        result[key] = item
    return result


def _strings(value: object, *, name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"engine capability {name} must be an array")
    return tuple(identifier(item, name=name) for item in cast("list[object]", value))


def _timestamp(value: object, *, name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{name} must be an ISO timestamp") from error
    else:
        raise TypeError(f"{name} must be a timestamp")
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _timestamp_string(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _number(value: Mapping[str, object], name: str) -> Decimal:
    return decimal_value(value.get(name), name=name)


def _decimal(value: object) -> str:
    return decimal_string(cast("Decimal", value))


def _basis_points(value: object, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 0 <= value <= 10_000:
        raise ValueError(f"{name} must be between zero and 10000")


def _choice(value: object, choices: set[str], *, name: str) -> None:
    if value not in choices:
        raise ValueError(f"unsupported {name}: {value!r}")


def _unique(values: Iterable[object], *, name: str) -> None:
    selected = tuple(values)
    if len(selected) != len(set(selected)):
        raise ValueError(f"{name} must be unique")


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
