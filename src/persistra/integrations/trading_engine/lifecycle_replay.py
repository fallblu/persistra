"""Explicit Trading Engine venue, corporate-action, and lifecycle replay."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    from decimal import Decimal


LIFECYCLE_CONTRACT_VERSION: Final = "1"
MAX_LIFECYCLE_EVENTS_PER_SLICE: Final = 1024
type SessionPolicy = Literal["regular", "early_close", "holiday"]
type SessionPhase = Literal[
    "premarket", "opening_auction", "regular", "closing_auction", "postmarket"
]
type DistributionKind = Literal["stock_dividend", "rights", "spin_off"]
type LifecycleKind = Literal["expiration", "delisting"]


@dataclass(frozen=True, slots=True)
class LifecycleProvenance:
    """Normalized provider identity and adjustment state retained beside an event."""

    provider: str
    dataset_id: str
    source_id: str
    ingested_at: datetime | str
    adjustment_state: Literal["raw", "adjusted_only"]

    def __post_init__(self) -> None:
        for name in ("provider", "dataset_id", "source_id"):
            object.__setattr__(self, name, identifier(getattr(self, name), name=name))
        object.__setattr__(self, "ingested_at", _timestamp(self.ingested_at, name="ingested_at"))
        _choice(self.adjustment_state, {"raw", "adjusted_only"}, name="adjustment_state")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "dataset_id": self.dataset_id,
            "source_id": self.source_id,
            "ingested_at": _timestamp_string(cast("datetime", self.ingested_at)),
            "adjustment_state": self.adjustment_state,
        }


@dataclass(frozen=True, slots=True)
class EventDeliveryPolicy:
    """Explicit effective, availability, and delivery clocks for one source event."""

    effective_at: datetime | str
    available_at: datetime | str
    delivered_at: datetime | str
    slice_sequence: int
    policy: Literal["first_observable_slice"]

    def __post_init__(self) -> None:
        for name in ("effective_at", "available_at", "delivered_at"):
            object.__setattr__(self, name, _timestamp(getattr(self, name), name=name))
        if not (
            cast("datetime", self.effective_at)
            <= cast("datetime", self.available_at)
            <= cast("datetime", self.delivered_at)
        ):
            raise ValueError("effective, availability, and delivery clocks must be causal")
        object.__setattr__(
            self,
            "slice_sequence",
            quantity_value(self.slice_sequence, name="slice_sequence", positive=True),
        )
        _choice(self.policy, {"first_observable_slice"}, name="delivery policy")

    def to_dict(self) -> dict[str, object]:
        return {
            "effective_at": _timestamp_string(cast("datetime", self.effective_at)),
            "available_at": _timestamp_string(cast("datetime", self.available_at)),
            "delivered_at": _timestamp_string(cast("datetime", self.delivered_at)),
            "slice_sequence": str(self.slice_sequence),
            "policy": self.policy,
        }


@dataclass(frozen=True, slots=True)
class VenuePhasePolicy:
    """One venue phase resolved from local policy to absolute instants."""

    phase: SessionPhase
    opens_at: datetime | str
    closes_at: datetime | str

    def __post_init__(self) -> None:
        _choice(
            self.phase,
            {"premarket", "opening_auction", "regular", "closing_auction", "postmarket"},
            name="venue phase",
        )
        object.__setattr__(self, "opens_at", _timestamp(self.opens_at, name="opens_at"))
        object.__setattr__(self, "closes_at", _timestamp(self.closes_at, name="closes_at"))
        if cast("datetime", self.opens_at) >= cast("datetime", self.closes_at):
            raise ValueError("venue phase must have positive duration")

    def to_dict(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "opens_at": _timestamp_string(cast("datetime", self.opens_at)),
            "closes_at": _timestamp_string(cast("datetime", self.closes_at)),
        }


@dataclass(frozen=True, slots=True)
class VenueSessionPolicy:
    """Explicit regular, early-close, or holiday policy for one local date."""

    session_date: date | str
    policy: SessionPolicy
    phases: tuple[VenuePhasePolicy, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_date", _date(self.session_date, name="session_date"))
        _choice(self.policy, {"regular", "early_close", "holiday"}, name="session policy")
        phases = tuple(self.phases)
        if self.policy == "holiday" and phases:
            raise ValueError("holiday session must not contain phases")
        if self.policy != "holiday" and not phases:
            raise ValueError("open session requires at least one phase")
        if len(phases) > 5 or len({item.phase for item in phases}) != len(phases):
            raise ValueError("session phases must be bounded and unique")
        for previous, current in pairwise(phases):
            if cast("datetime", previous.closes_at) > cast("datetime", current.opens_at):
                raise ValueError("session phases must be ordered and nonoverlapping")
        object.__setattr__(self, "phases", phases)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_date": cast("date", self.session_date).isoformat(),
            "policy": self.policy,
            "phases": [item.to_dict() for item in self.phases],
        }


@dataclass(frozen=True, slots=True)
class VenueCalendarPolicy:
    """Versioned venue-local policy mapped to explicit UTC session instants."""

    calendar_id: str
    venue_id: str
    time_zone: str
    instrument_ids: tuple[str, ...]
    sessions: tuple[VenueSessionPolicy, ...]
    calendar_version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        for name in ("calendar_id", "venue_id"):
            object.__setattr__(self, name, identifier(getattr(self, name), name=name))
        try:
            zone = ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("time_zone must name an IANA time zone") from error
        instruments = tuple(
            sorted(identifier(item, name="instrument_id") for item in self.instrument_ids)
        )
        sessions = tuple(sorted(self.sessions, key=lambda item: cast("date", item.session_date)))
        if not instruments or not sessions:
            raise ValueError("venue calendar requires instruments and sessions")
        _unique(instruments, name="calendar instrument IDs")
        _unique((item.session_date for item in sessions), name="session dates")
        for session in sessions:
            for phase in session.phases:
                local_open = cast("datetime", phase.opens_at).astimezone(zone).date()
                local_close = cast("datetime", phase.closes_at).astimezone(zone).date()
                if local_open != session.session_date or local_close not in {
                    session.session_date,
                    cast("date", session.session_date).fromordinal(
                        cast("date", session.session_date).toordinal() + 1
                    ),
                }:
                    raise ValueError("venue phase conflicts with its local session date")
        object.__setattr__(self, "instrument_ids", instruments)
        object.__setattr__(self, "sessions", sessions)

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "calendar_id": self.calendar_id,
            "calendar_version": self.calendar_version,
            "venue_id": self.venue_id,
            "instrument_ids": list(self.instrument_ids),
            "sessions": [item.to_dict() for item in self.sessions],
        }


@dataclass(frozen=True, slots=True)
class FractionalEntitlementPolicy:
    """Explicit rejection or cash-in-lieu behavior for fractional entitlements."""

    policy: Literal["reject", "cash_in_lieu"]
    price: Decimal | str | int | float | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        _choice(self.policy, {"reject", "cash_in_lieu"}, name="fractional policy")
        if self.policy == "reject":
            if self.price is not None or self.currency is not None:
                raise ValueError("reject fractional policy does not accept cash terms")
        else:
            object.__setattr__(
                self, "price", decimal_value(self.price, name="cash-in-lieu price", positive=True)
            )
            object.__setattr__(
                self, "currency", identifier(self.currency, name="cash-in-lieu currency")
            )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"policy": self.policy}
        if self.price is not None:
            result.update(price=_decimal(self.price), currency=self.currency)
        return result


@dataclass(frozen=True, slots=True)
class SplitLifecycleAction:
    action_id: str
    instrument_id: str
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _action_common(self)
        for name in ("numerator", "denominator"):
            object.__setattr__(
                self, name, quantity_value(getattr(self, name), name=name, positive=True)
            )

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "split",
            "action_id": self.action_id,
            "instrument_id": self.instrument_id,
            "numerator": str(self.numerator),
            "denominator": str(self.denominator),
        }


@dataclass(frozen=True, slots=True)
class CashDividendLifecycleAction:
    action_id: str
    instrument_id: str
    amount_per_unit: Decimal | str | int | float

    def __post_init__(self) -> None:
        _action_common(self)
        object.__setattr__(
            self,
            "amount_per_unit",
            decimal_value(self.amount_per_unit, name="amount_per_unit", positive=True),
        )

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "cash_dividend",
            "action_id": self.action_id,
            "instrument_id": self.instrument_id,
            "amount_per_unit": _decimal(self.amount_per_unit),
        }


@dataclass(frozen=True, slots=True)
class DistributionLifecycleAction:
    action_id: str
    instrument_id: str
    destination_instrument_id: str
    kind: DistributionKind
    numerator: int
    denominator: int
    basis_allocation_bps: int
    fractional_policy: FractionalEntitlementPolicy

    def __post_init__(self) -> None:
        _action_common(self)
        object.__setattr__(
            self,
            "destination_instrument_id",
            identifier(self.destination_instrument_id, name="destination_instrument_id"),
        )
        _choice(self.kind, {"stock_dividend", "rights", "spin_off"}, name="distribution kind")
        for name in ("numerator", "denominator"):
            object.__setattr__(
                self, name, quantity_value(getattr(self, name), name=name, positive=True)
            )
        _basis_points(self.basis_allocation_bps, name="basis_allocation_bps")
        if self.kind == "stock_dividend":
            if self.destination_instrument_id != self.instrument_id:
                raise ValueError("stock dividend destination must be its source instrument")
            if self.basis_allocation_bps != 0:
                raise ValueError("stock dividend basis allocation must be zero")
            if self.numerator > 2**63 - 1 - self.denominator:
                raise ValueError("stock dividend total ratio is outside the supported range")
        elif self.destination_instrument_id == self.instrument_id:
            raise ValueError("rights and spin-off destinations must differ from their source")

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": self.kind,
            "action_id": self.action_id,
            "instrument_id": self.instrument_id,
            "destination_instrument_id": self.destination_instrument_id,
            "numerator": str(self.numerator),
            "denominator": str(self.denominator),
            "basis_allocation_bps": self.basis_allocation_bps,
            "fractional_policy": self.fractional_policy.to_dict(),
        }


type LifecycleCorporateAction = (
    SplitLifecycleAction | CashDividendLifecycleAction | DistributionLifecycleAction
)


@dataclass(frozen=True, slots=True)
class TerminalDisposition:
    policy: Literal["hold", "cash_out"]
    price: Decimal | str | int | float | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        _choice(self.policy, {"hold", "cash_out"}, name="terminal policy")
        if self.policy == "hold":
            if self.price is not None or self.currency is not None:
                raise ValueError("hold terminal policy does not accept cash terms")
        else:
            object.__setattr__(
                self, "price", decimal_value(self.price, name="cash-out price", positive=True)
            )
            object.__setattr__(
                self, "currency", identifier(self.currency, name="cash-out currency")
            )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"policy": self.policy}
        if self.price is not None:
            result.update(price=_decimal(self.price), currency=self.currency)
        return result


@dataclass(frozen=True, slots=True)
class HaltLifecycleEvent:
    event_id: str
    instrument_id: str
    reason: str

    def __post_init__(self) -> None:
        _event_common(self)
        object.__setattr__(self, "reason", _reason(self.reason))

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "halt",
            "event_id": self.event_id,
            "instrument_id": self.instrument_id,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class ResumeLifecycleEvent:
    event_id: str
    instrument_id: str

    def __post_init__(self) -> None:
        _event_common(self)

    def to_contract_dict(self) -> dict[str, object]:
        return {"type": "resume", "event_id": self.event_id, "instrument_id": self.instrument_id}


@dataclass(frozen=True, slots=True)
class IdentifierChangeLifecycleEvent:
    event_id: str
    instrument_id: str
    symbol: str
    provider: str
    provider_instrument_id: str

    def __post_init__(self) -> None:
        _event_common(self)
        for name in ("symbol", "provider", "provider_instrument_id"):
            object.__setattr__(self, name, identifier(getattr(self, name), name=name))

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "type": "identifier_change",
            "event_id": self.event_id,
            "instrument_id": self.instrument_id,
            "symbol": self.symbol,
            "provider": self.provider,
            "provider_instrument_id": self.provider_instrument_id,
        }


@dataclass(frozen=True, slots=True)
class TerminalLifecycleEvent:
    event_id: str
    instrument_id: str
    kind: LifecycleKind
    terminal_policy: TerminalDisposition
    reason: str | None = None

    def __post_init__(self) -> None:
        _event_common(self)
        _choice(self.kind, {"expiration", "delisting"}, name="terminal event kind")
        if self.kind == "delisting":
            object.__setattr__(self, "reason", _reason(self.reason))
        elif self.reason is not None:
            raise ValueError("expiration does not accept a delisting reason")

    def to_contract_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "type": self.kind,
            "event_id": self.event_id,
            "instrument_id": self.instrument_id,
            "terminal_policy": self.terminal_policy.to_dict(),
        }
        if self.reason is not None:
            result["reason"] = self.reason
        return result


type LifecycleEvent = (
    HaltLifecycleEvent
    | ResumeLifecycleEvent
    | IdentifierChangeLifecycleEvent
    | TerminalLifecycleEvent
)


@dataclass(frozen=True, slots=True)
class ScheduledCorporateAction:
    action: LifecycleCorporateAction
    delivery: EventDeliveryPolicy
    provenance: LifecycleProvenance

    def __post_init__(self) -> None:
        _source_policy(self.delivery, self.provenance)


@dataclass(frozen=True, slots=True)
class ScheduledLifecycleEvent:
    event: LifecycleEvent
    delivery: EventDeliveryPolicy
    provenance: LifecycleProvenance

    def __post_init__(self) -> None:
        _source_policy(self.delivery, self.provenance)


@dataclass(frozen=True, slots=True)
class LifecycleSliceEvents:
    slice_sequence: int
    corporate_actions: tuple[ScheduledCorporateAction, ...] = ()
    lifecycle_events: tuple[ScheduledLifecycleEvent, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "slice_sequence",
            quantity_value(self.slice_sequence, name="slice_sequence", positive=True),
        )
        actions = tuple(sorted(self.corporate_actions, key=lambda item: item.action.action_id))
        events = tuple(
            sorted(
                self.lifecycle_events, key=lambda item: cast("datetime", item.delivery.available_at)
            )
        )
        if len(actions) + len(events) > MAX_LIFECYCLE_EVENTS_PER_SLICE:
            raise ValueError("lifecycle slice exceeds its bounded event limit")
        _unique((item.action.action_id for item in actions), name="slice action IDs")
        _unique((item.event.event_id for item in events), name="slice lifecycle event IDs")
        for item in (*actions, *events):
            if item.delivery.slice_sequence != self.slice_sequence:
                raise ValueError("event delivery slice differs from its containing slice")
        object.__setattr__(self, "corporate_actions", actions)
        object.__setattr__(self, "lifecycle_events", events)

    def provenance_dict(self) -> dict[str, object]:
        return {
            "slice_sequence": str(self.slice_sequence),
            "corporate_actions": [
                _scheduled_dict(item.action.action_id, item.delivery, item.provenance)
                for item in self.corporate_actions
            ],
            "lifecycle_events": [
                _scheduled_dict(item.event.event_id, item.delivery, item.provenance)
                for item in self.lifecycle_events
            ],
        }


@dataclass(frozen=True, slots=True)
class LifecycleReplayScenario:
    document: Mapping[str, Any]
    calendars: tuple[VenueCalendarPolicy, ...]
    slices: tuple[LifecycleSliceEvents, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "document",
            freeze_portable_mapping(self.document, name="lifecycle replay scenario"),
        )

    @property
    def contract_version(self) -> str:
        return LIFECYCLE_CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return thaw_portable_mapping(self.document)


@dataclass(frozen=True, slots=True)
class LifecycleReplayResult:
    replay: SchemaReplayResult
    applied_actions: tuple[Mapping[str, object], ...]
    applied_lifecycle: tuple[Mapping[str, object], ...]
    order_effects: tuple[Mapping[str, object], ...]
    valuations: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        for name in ("applied_actions", "applied_lifecycle", "order_effects", "valuations"):
            object.__setattr__(
                self,
                name,
                tuple(freeze_portable_mapping(item, name=name) for item in getattr(self, name)),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.replay.contract_version,
            "run_id": self.replay.run_id,
            "applied_actions": len(self.applied_actions),
            "applied_lifecycle": len(self.applied_lifecycle),
            "order_effects": len(self.order_effects),
            "valuations": len(self.valuations),
            "status": "verified",
        }


def require_lifecycle_capabilities(
    capabilities: Mapping[str, Any],
    schemas: TradingEngineContractSchemas,
    *,
    scenario_format: Literal["json", "jsonl"] = "json",
) -> None:
    """Require the first engine contract carrying complete lifecycle semantics."""
    _require_contract(schemas)
    requirements = (
        (
            LIFECYCLE_CONTRACT_VERSION
            in _strings(
                capabilities.get("scenario_contract_versions"), name="scenario_contract_versions"
            ),
            "scenario contract v1",
        ),
        (
            LIFECYCLE_CONTRACT_VERSION
            in _strings(
                capabilities.get("journal_contract_versions"), name="journal_contract_versions"
            ),
            "journal contract v1",
        ),
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
        raise ValueError("incompatible lifecycle capabilities: missing " + ", ".join(missing))


def build_lifecycle_replay_scenario(
    *,
    schemas: TradingEngineContractSchemas,
    base_scenario: Mapping[str, Any],
    calendars: Sequence[VenueCalendarPolicy],
    slices: Sequence[LifecycleSliceEvents],
) -> LifecycleReplayScenario:
    """Build a schema-validated v1 scenario from deliberate executable policies."""
    _require_contract(schemas)
    selected_calendars = tuple(sorted(calendars, key=lambda item: item.calendar_id))
    selected_slices = tuple(sorted(slices, key=lambda item: item.slice_sequence))
    _unique((item.calendar_id for item in selected_calendars), name="calendar IDs")
    _unique((item.slice_sequence for item in selected_slices), name="lifecycle slice sequences")
    document = thaw_portable_mapping(
        freeze_portable_mapping(base_scenario, name="base Trading Engine scenario")
    )
    document["contract_version"] = LIFECYCLE_CONTRACT_VERSION
    document["venue_calendars"] = [item.to_contract_dict() for item in selected_calendars]
    instruments = _instruments(document)
    _validate_calendar_coverage(selected_calendars, instruments=set(instruments))
    by_sequence = {str(item.slice_sequence): item for item in selected_slices}
    actions: set[str] = set()
    events: set[str] = set()
    states = {instrument: "tradable" for instrument in instruments}
    for index, raw in enumerate(cast("list[object]", document.get("slices"))):
        market_slice = _mapping(raw, name="market slice")
        selected = by_sequence.pop(cast("str", market_slice.get("slice_sequence")), None)
        if selected is None:
            raise ValueError("every base market slice requires explicit lifecycle delivery")
        _validate_delivery_bounds(market_slice, selected)
        _validate_slice_semantics(selected, instruments=instruments, states=states)
        for item in selected.corporate_actions:
            if item.action.action_id in actions:
                raise ValueError("corporate action IDs must be globally unique")
            actions.add(item.action.action_id)
        for item in selected.lifecycle_events:
            if item.event.event_id in events:
                raise ValueError("lifecycle event IDs must be globally unique")
            events.add(item.event.event_id)
        market_slice["corporate_actions"] = [
            item.action.to_contract_dict() for item in selected.corporate_actions
        ]
        market_slice["lifecycle_events"] = [
            item.event.to_contract_dict() for item in selected.lifecycle_events
        ]
        cast("list[dict[str, object]]", document["slices"])[index] = market_slice
    if by_sequence:
        raise ValueError("lifecycle delivery refers to an unknown slice")
    schemas.validate_scenario(document)
    for line_number, record in enumerate(_stream_records(document), start=1):
        schemas.validate_stream_record(record, line_number=line_number)
    return LifecycleReplayScenario(
        document,
        selected_calendars,
        selected_slices,
        hashlib.sha256(_canonical_json(document)).hexdigest(),
    )


def lifecycle_scenario_to_json(scenario: LifecycleReplayScenario, *, indent: int | None = 2) -> str:
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


def lifecycle_scenario_to_jsonl(scenario: LifecycleReplayScenario) -> str:
    return "".join(
        json.dumps(item, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in _stream_records(scenario.to_dict())
    )


def write_lifecycle_scenario(
    scenario: LifecycleReplayScenario,
    path: str | Path,
    *,
    stream: bool = False,
    overwrite: bool = False,
) -> Path:
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = (
        lifecycle_scenario_to_jsonl(scenario) if stream else lifecycle_scenario_to_json(scenario)
    )
    with output.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return output


def bind_lifecycle_manifest(
    manifest: Mapping[str, Any], scenario: LifecycleReplayScenario
) -> Mapping[str, Any]:
    document = thaw_portable_mapping(freeze_portable_mapping(manifest, name="replay manifest"))
    contract = document.get("contract")
    if (
        not isinstance(contract, dict)
        or cast("dict[str, object]", contract).get("version") != scenario.contract_version
    ):
        raise ValueError("replay manifest contract differs from lifecycle scenario")
    if "lifecycle" in document:
        raise ValueError("replay manifest already contains lifecycle")
    provenance = [item.provenance_dict() for item in scenario.slices]
    document["lifecycle"] = {
        "contract_version": scenario.contract_version,
        "scenario_content_sha256": scenario.content_sha256,
        "calendar_time_zones": {item.calendar_id: item.time_zone for item in scenario.calendars},
        "provenance_sha256": hashlib.sha256(_canonical_json(provenance)).hexdigest(),
        "slices": provenance,
    }
    return freeze_portable_mapping(document, name="replay manifest")


def reconcile_lifecycle_replay(
    schemas: TradingEngineContractSchemas, scenario_path: str | Path, journal_path: str | Path
) -> LifecycleReplayResult:
    """Reconcile declared actions and lifecycle transitions with their accounting evidence."""
    _require_contract(schemas)
    replay = schemas.read_replay(scenario_path, journal_path)
    try:
        document = _mapping(
            json.loads(Path(scenario_path).read_text(encoding="utf-8")), name="lifecycle scenario"
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TradingEngineContractError("invalid lifecycle scenario JSON") from error
    declared_actions, declared_events, expected_slices = _declared_events(document)
    applied_actions: list[Mapping[str, object]] = []
    applied_lifecycle: list[Mapping[str, object]] = []
    order_effects: list[Mapping[str, object]] = []
    valuations: list[Mapping[str, object]] = []
    for event in replay.events:
        event_type = event.get("event_type")
        payload = _mapping(event.get("payload"), name=f"{event_type} payload")
        if event_type == "market_slice_received":
            _reconcile_received(payload, expected_slices)
        elif event_type in {"split_applied", "cash_dividend_applied", "distribution_applied"}:
            _reconcile_action(payload, declared_actions, event_type=cast("str", event_type))
            applied_actions.append(payload)
        elif event_type == "lifecycle_applied":
            _reconcile_lifecycle(payload, declared_events)
            applied_lifecycle.append(payload)
        elif event_type in {"order_cancelled", "order_adjusted"}:
            order_effects.append(payload)
        elif event_type == "valuation":
            valuations.append(payload)
    if expected_slices or declared_actions or declared_events:
        raise TradingEngineContractError("journal omits declared lifecycle replay evidence")
    if len(valuations) < len(cast("list[object]", document.get("slices"))) + 1:
        raise TradingEngineContractError("journal omits lifecycle valuation boundaries")
    return LifecycleReplayResult(
        replay,
        tuple(applied_actions),
        tuple(applied_lifecycle),
        tuple(order_effects),
        tuple(valuations),
    )


def _validate_slice_semantics(
    data: LifecycleSliceEvents, *, instruments: Mapping[str, str], states: dict[str, str]
) -> None:
    for item in data.corporate_actions:
        action = item.action
        if action.instrument_id not in instruments:
            raise ValueError("corporate action refers to an unknown instrument")
        if states[action.instrument_id] in {"expired", "delisted"}:
            raise ValueError("corporate action refers to a terminal instrument")
        if isinstance(action, DistributionLifecycleAction):
            if action.destination_instrument_id not in instruments:
                raise ValueError("distribution destination is unknown")
            policy = action.fractional_policy
            if (
                policy.currency is not None
                and policy.currency != instruments[action.destination_instrument_id]
            ):
                raise ValueError("cash-in-lieu currency differs from destination quote currency")
    for item in data.lifecycle_events:
        event = item.event
        if event.instrument_id not in instruments:
            raise ValueError("lifecycle event refers to an unknown instrument")
        state = states[event.instrument_id]
        if state in {"expired", "delisted"}:
            raise ValueError("terminal instrument cannot accept another lifecycle event")
        if isinstance(event, HaltLifecycleEvent):
            if state != "tradable":
                raise ValueError("only a tradable instrument can halt")
            states[event.instrument_id] = "halted"
        elif isinstance(event, ResumeLifecycleEvent):
            if state != "halted":
                raise ValueError("only a halted instrument can resume")
            states[event.instrument_id] = "tradable"
        elif isinstance(event, TerminalLifecycleEvent):
            states[event.instrument_id] = "expired" if event.kind == "expiration" else "delisted"
            if (
                event.terminal_policy.currency is not None
                and event.terminal_policy.currency != instruments[event.instrument_id]
            ):
                raise ValueError("cash-out currency differs from instrument quote currency")


def _validate_delivery_bounds(
    market_slice: Mapping[str, object], data: LifecycleSliceEvents
) -> None:
    start = _timestamp(market_slice.get("start_at"), name="slice start_at")
    end = _timestamp(market_slice.get("end_at"), name="slice end_at")
    received = _timestamp(market_slice.get("received_at"), name="slice received_at")
    for item in (*data.corporate_actions, *data.lifecycle_events):
        if not start <= cast("datetime", item.delivery.effective_at) <= end:
            raise ValueError("event effective time falls outside its delivery slice")
        if cast("datetime", item.delivery.delivered_at) > received:
            raise ValueError("event delivery occurs after its slice receipt")


def _validate_calendar_coverage(
    calendars: Sequence[VenueCalendarPolicy], *, instruments: set[str]
) -> None:
    coverage = [instrument for calendar in calendars for instrument in calendar.instrument_ids]
    if set(coverage) != instruments or len(coverage) != len(set(coverage)):
        raise ValueError("venue calendars must cover every instrument exactly once")


def _declared_events(
    document: Mapping[str, object],
) -> tuple[
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
]:
    actions: dict[str, Mapping[str, object]] = {}
    events: dict[str, Mapping[str, object]] = {}
    slices: dict[str, Mapping[str, object]] = {}
    for raw in cast("list[object]", document.get("slices")):
        item = _mapping(raw, name="scenario market slice")
        slices[cast("str", item["slice_sequence"])] = item
        for action in (
            _mapping(value, name="corporate action")
            for value in cast("list[object]", item["corporate_actions"])
        ):
            actions[cast("str", action["action_id"])] = action
        for lifecycle in (
            _mapping(value, name="lifecycle event")
            for value in cast("list[object]", item["lifecycle_events"])
        ):
            events[cast("str", lifecycle["event_id"])] = lifecycle
    return actions, events, slices


def _reconcile_received(
    payload: Mapping[str, object], expected: dict[str, Mapping[str, object]]
) -> None:
    sequence = payload.get("slice_sequence")
    if not isinstance(sequence, str) or sequence not in expected:
        raise TradingEngineContractError("journal market slice is not in lifecycle scenario")
    source = expected.pop(sequence)
    for name in ("corporate_actions", "lifecycle_events"):
        if _portable(payload.get(name)) != _portable(source.get(name)):
            raise TradingEngineContractError(f"journal {name} differs from lifecycle scenario")


def _reconcile_action(
    payload: Mapping[str, object], declared: dict[str, Mapping[str, object]], *, event_type: str
) -> None:
    action = _mapping(payload.get("action"), name="applied corporate action")
    action_id = action.get("action_id")
    if not isinstance(action_id, str) or _portable(action) != _portable(
        declared.pop(action_id, None)
    ):
        raise TradingEngineContractError("applied corporate action differs from scenario")
    kind = action.get("type")
    expected_type = {"split": "split_applied", "cash_dividend": "cash_dividend_applied"}.get(
        cast("str", kind), "distribution_applied"
    )
    if event_type != expected_type:
        raise TradingEngineContractError("corporate action used the wrong journal effect")
    if kind == "split":
        previous = _number(payload, "previous_quantity")
        adjusted = _number(payload, "adjusted_quantity")
        if adjusted * decimal_value(
            action["denominator"], name="denominator"
        ) != previous * decimal_value(action["numerator"], name="numerator"):
            raise TradingEngineContractError("split quantity effect does not reconcile")
    elif kind == "cash_dividend":
        if _number(payload, "cash_amount") != _number(payload, "quantity") * decimal_value(
            action["amount_per_unit"], name="amount_per_unit"
        ):
            raise TradingEngineContractError("cash dividend effect does not reconcile")
    else:
        fractional = _number(payload, "fractional_quantity")
        fractional_basis = _number(payload, "fractional_basis")
        cash = _number(payload, "cash_in_lieu")
        policy = _mapping(action.get("fractional_policy"), name="fractional policy")
        if policy.get("policy") == "reject" and (fractional or fractional_basis or cash):
            raise TradingEngineContractError(
                "rejected fractional distribution has accounting effects"
            )
        if policy.get("policy") == "cash_in_lieu" and cash != fractional * decimal_value(
            policy["price"], name="cash-in-lieu price"
        ):
            raise TradingEngineContractError("distribution cash-in-lieu does not reconcile")


def _reconcile_lifecycle(
    payload: Mapping[str, object], declared: dict[str, Mapping[str, object]]
) -> None:
    event = _mapping(payload.get("lifecycle_event"), name="applied lifecycle event")
    event_id = event.get("event_id")
    if not isinstance(event_id, str) or _portable(event) != _portable(declared.pop(event_id, None)):
        raise TradingEngineContractError("applied lifecycle event differs from scenario")
    listing = _mapping(payload.get("listing"), name="lifecycle listing")
    if listing.get("instrument_id") != event.get("instrument_id"):
        raise TradingEngineContractError("lifecycle transition changed stable instrument identity")
    kind = event.get("type")
    expected_status = {
        "halt": "halted",
        "resume": "tradable",
        "expiration": "expired",
        "delisting": "delisted",
    }.get(cast("str", kind))
    if expected_status is not None and listing.get("status") != expected_status:
        raise TradingEngineContractError("lifecycle listing status does not reconcile")
    if kind == "identifier_change":
        mappings = cast("list[object]", listing.get("provider_mappings"))
        expected = {
            "provider": event.get("provider"),
            "provider_instrument_id": event.get("provider_instrument_id"),
        }
        if listing.get("symbol") != event.get("symbol") or expected not in [
            _mapping(item, name="provider mapping") for item in mappings
        ]:
            raise TradingEngineContractError("identifier change mapping does not reconcile")
    if kind in {"expiration", "delisting"}:
        terminal = _mapping(event.get("terminal_policy"), name="terminal policy")
        quantity = _number(payload, "liquidated_quantity")
        cash = _number(payload, "cash_amount")
        if terminal.get("policy") == "hold" and (quantity or cash):
            raise TradingEngineContractError("terminal hold unexpectedly liquidated the position")
        if terminal.get("policy") == "cash_out" and cash != quantity * decimal_value(
            terminal["price"], name="cash-out price"
        ):
            raise TradingEngineContractError("terminal cash-out does not reconcile")


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
            "contract_version": LIFECYCLE_CONTRACT_VERSION,
            "scenario_sequence": "1",
            "record_type": "scenario_header",
            "payload": header,
        }
    ]
    slices = cast("list[object]", document.get("slices"))
    for index, raw in enumerate(slices, start=2):
        item = _mapping(raw, name="market slice")
        sequence = cast("str", item.get("slice_sequence"))
        records.append(
            {
                "contract_version": LIFECYCLE_CONTRACT_VERSION,
                "scenario_sequence": str(index),
                "record_type": "market_slice",
                "payload": {"market_slice": item, "intents": intents.pop(sequence, [])},
            }
        )
    if intents:
        raise ValueError("schedule refers to a missing market slice")
    records.append(
        {
            "contract_version": LIFECYCLE_CONTRACT_VERSION,
            "scenario_sequence": str(len(records) + 1),
            "record_type": "scenario_end",
            "payload": {"slice_count": str(len(slices))},
        }
    )
    return tuple(records)


def _instruments(document: Mapping[str, Any]) -> dict[str, str]:
    return {
        cast("str", item["instrument_id"]): cast("str", item["quote_currency"])
        for item in (
            _mapping(raw, name="instrument")
            for raw in cast("list[object]", document.get("instruments"))
        )
    }


def _source_policy(delivery: EventDeliveryPolicy, provenance: LifecycleProvenance) -> None:
    if provenance.adjustment_state == "adjusted_only":
        raise ValueError("adjusted-only history cannot produce executable lifecycle events")
    if cast("datetime", provenance.ingested_at) < cast("datetime", delivery.available_at):
        raise ValueError("source ingestion cannot precede event availability")


def _scheduled_dict(
    event_id: str, delivery: EventDeliveryPolicy, provenance: LifecycleProvenance
) -> dict[str, object]:
    return {
        "event_id": event_id,
        "delivery": delivery.to_dict(),
        "provenance": provenance.to_dict(),
    }


def _action_common(
    value: SplitLifecycleAction | CashDividendLifecycleAction | DistributionLifecycleAction,
) -> None:
    object.__setattr__(value, "action_id", identifier(value.action_id, name="action_id"))
    object.__setattr__(
        value, "instrument_id", identifier(value.instrument_id, name="instrument_id")
    )


def _event_common(
    value: HaltLifecycleEvent
    | ResumeLifecycleEvent
    | IdentifierChangeLifecycleEvent
    | TerminalLifecycleEvent,
) -> None:
    object.__setattr__(value, "event_id", identifier(value.event_id, name="event_id"))
    object.__setattr__(
        value, "instrument_id", identifier(value.instrument_id, name="instrument_id")
    )


def _reason(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in value)
    ):
        raise ValueError("lifecycle reason must not be empty or contain whitespace")
    return value


def _require_contract(schemas: TradingEngineContractSchemas) -> None:
    if schemas.version != LIFECYCLE_CONTRACT_VERSION:
        raise ValueError("lifecycle replay requires Trading Engine contract v1")


def _mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TradingEngineContractError(f"{name} must be an object")
    result: dict[str, object] = {}
    for key, item in cast("Mapping[object, object]", value).items():
        if not isinstance(key, str):
            raise TradingEngineContractError(f"{name} keys must be strings")
        result[key] = item
    return result


def _portable(value: object) -> object:
    if isinstance(value, Mapping):
        return thaw_portable_mapping(cast("Mapping[str, Any]", value))
    if isinstance(value, tuple):
        return [_portable(item) for item in cast("tuple[object, ...]", value)]
    return value


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


def _date(value: object, *, name: str) -> date:
    if isinstance(value, datetime):
        raise TypeError(f"{name} must be a date")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError(f"{name} must be an ISO date") from error
    raise TypeError(f"{name} must be a date")


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
