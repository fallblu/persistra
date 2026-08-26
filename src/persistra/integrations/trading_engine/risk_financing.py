"""Typed Trading Engine risk, fees, financing, and settlement contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.integrations.trading_engine._scalars import (
    decimal_string,
    decimal_value,
    identifier,
)
from persistra.integrations.trading_engine.contracts import (
    SchemaReplayResult,
    TradingEngineContractError,
    TradingEngineContractSchemas,
)

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from persistra.integrations.trading_engine.model import EngineCapabilities


RISK_FINANCING_CONTRACT_VERSION: Final = "1"
type GroupType = Literal["issuer", "sector", "currency", "country", "asset_class", "custom"]
type FeeKind = Literal["fixed", "notional_bps", "per_unit"]
type FeeRounding = Literal["up", "down", "nearest"]
type FeeApplicability = Literal["any", "maker", "taker"]
type DayCount = Literal["actual_365", "actual_360"]
type Compounding = Literal["simple", "daily"]
type MissingFinancingData = Literal["reject", "zero"]
type LocatePolicy = Literal["reject_order", "clip_fill"]
type RecallPolicy = Literal["reject_new_shorts", "close_out"]
type CashBuyingPower = Literal["total_cash", "settled_cash"]
type PositionAvailability = Literal["total_positions", "settled_positions"]


@dataclass(frozen=True, slots=True)
class InstrumentRiskPolicy:
    """Approved risk limits for exactly one catalog instrument."""

    instrument_id: str
    max_order_quantity: Decimal | str | int | float
    max_long_position: Decimal | str | int | float
    max_short_position: Decimal | str | int | float
    max_notional_exposure: Decimal | str | int | float
    initial_margin_bps: int
    maintenance_margin_bps: int
    shorting_allowed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", identifier(self.instrument_id, name="instrument_id")
        )
        for name in (
            "max_order_quantity",
            "max_long_position",
            "max_short_position",
            "max_notional_exposure",
        ):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=name, positive=True),
            )
        _basis_points(self.initial_margin_bps, name="initial_margin_bps", positive=True)
        _basis_points(
            self.maintenance_margin_bps,
            name="maintenance_margin_bps",
            positive=True,
        )
        if self.maintenance_margin_bps > self.initial_margin_bps:
            raise ValueError("maintenance_margin_bps must not exceed initial_margin_bps")
        if not isinstance(cast("object", self.shorting_allowed), bool):
            raise TypeError("shorting_allowed must be boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "max_order_quantity": _decimal(self.max_order_quantity),
            "max_long_position": _decimal(self.max_long_position),
            "max_short_position": _decimal(self.max_short_position),
            "max_notional_exposure": _decimal(self.max_notional_exposure),
            "initial_margin_bps": self.initial_margin_bps,
            "maintenance_margin_bps": self.maintenance_margin_bps,
            "shorting_allowed": self.shorting_allowed,
        }


@dataclass(frozen=True, slots=True)
class RiskGroupLimits:
    """Optional v1 exposure ceilings for a named risk group."""

    max_gross_exposure: Decimal | str | int | float | None = None
    max_long_exposure: Decimal | str | int | float | None = None
    max_short_exposure: Decimal | str | int | float | None = None
    max_absolute_net_exposure: Decimal | str | int | float | None = None
    max_concentration: Decimal | str | int | float | None = None

    def __post_init__(self) -> None:
        for name in (
            "max_gross_exposure",
            "max_long_exposure",
            "max_short_exposure",
            "max_absolute_net_exposure",
            "max_concentration",
        ):
            raw = getattr(self, name)
            if raw is not None:
                value = decimal_value(raw, name=name, positive=True)
                if name == "max_concentration" and value > 1:
                    raise ValueError("max_concentration must not exceed one")
                object.__setattr__(self, name, value)
        if all(getattr(self, name) is None for name in self.__dataclass_fields__):
            raise ValueError("risk group must declare at least one limit")

    def to_dict(self) -> dict[str, object]:
        return {
            name: None if getattr(self, name) is None else _decimal(getattr(self, name))
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class RiskGroup:
    """Versioned, explicitly sourced group membership and limits."""

    group_id: str
    group_type: GroupType
    instrument_ids: tuple[str, ...]
    limits: RiskGroupLimits
    group_version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", identifier(self.group_id, name="group_id"))
        _choice(
            self.group_type,
            {"issuer", "sector", "currency", "country", "asset_class", "custom"},
            name="group_type",
        )
        members = tuple(identifier(item, name="instrument_id") for item in self.instrument_ids)
        _unique(members, name="risk group instruments")
        if not members:
            raise ValueError("risk group instruments must not be empty")
        object.__setattr__(self, "instrument_ids", tuple(sorted(members)))

    def to_dict(self) -> dict[str, object]:
        return {
            "group_id": self.group_id,
            "group_version": self.group_version,
            "group_type": self.group_type,
            "instrument_ids": list(self.instrument_ids),
            "limits": self.limits.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class RiskFinancingRiskPolicy:
    """Aggregate and per-instrument v1 risk policy."""

    max_gross_exposure: Decimal | str | int | float
    max_leverage: Decimal | str | int | float
    instrument_policies: tuple[InstrumentRiskPolicy, ...]
    groups: tuple[RiskGroup, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_gross_exposure",
            decimal_value(self.max_gross_exposure, name="max_gross_exposure", positive=True),
        )
        object.__setattr__(
            self,
            "max_leverage",
            decimal_value(self.max_leverage, name="max_leverage", positive=True),
        )
        policies = tuple(sorted(self.instrument_policies, key=lambda item: item.instrument_id))
        groups = tuple(sorted(self.groups, key=lambda item: item.group_id))
        if not policies:
            raise ValueError("instrument_policies must not be empty")
        _unique((item.instrument_id for item in policies), name="instrument risk policies")
        _unique((item.group_id for item in groups), name="risk groups")
        object.__setattr__(self, "instrument_policies", policies)
        object.__setattr__(self, "groups", groups)

    def to_dict(self) -> dict[str, object]:
        return {
            "max_gross_exposure": _decimal(self.max_gross_exposure),
            "max_leverage": _decimal(self.max_leverage),
            "instrument_policies": [item.to_dict() for item in self.instrument_policies],
            "groups": [item.to_dict() for item in self.groups],
        }


@dataclass(frozen=True, slots=True)
class FeeComponent:
    """One named native-currency fee or rebate component."""

    name: str
    currency: str
    kind: FeeKind
    value: Decimal | str | int | float
    rounding: FeeRounding
    applies_to: FeeApplicability = "any"

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", identifier(self.name, name="fee component name"))
        object.__setattr__(self, "currency", identifier(self.currency, name="fee currency"))
        _choice(self.kind, {"fixed", "notional_bps", "per_unit"}, name="fee kind")
        _choice(self.rounding, {"up", "down", "nearest"}, name="fee rounding")
        _choice(self.applies_to, {"any", "maker", "taker"}, name="fee applicability")
        if self.kind == "notional_bps":
            if isinstance(self.value, bool) or not isinstance(self.value, int):
                raise TypeError("notional_bps fee value must be an integer")
            if not -10_000 <= self.value <= 10_000:
                raise ValueError("notional_bps fee value must be between -10000 and 10000")
        else:
            object.__setattr__(self, "value", decimal_value(self.value, name="fee value"))

    def to_dict(self) -> dict[str, object]:
        value: object = self.value if self.kind == "notional_bps" else _decimal(self.value)
        return {
            "name": self.name,
            "currency": self.currency,
            "kind": self.kind,
            "value": value,
            "rounding": self.rounding,
            "applies_to": self.applies_to,
        }


@dataclass(frozen=True, slots=True)
class InstrumentFeeSchedule:
    """Composable fee schedule selected for one instrument."""

    schedule_id: str
    instrument_id: str
    settlement_currency: str
    components: tuple[FeeComponent, ...]
    minimum: Decimal | str | int | float | None = None
    maximum: Decimal | str | int | float | None = None

    def __post_init__(self) -> None:
        for name in ("schedule_id", "instrument_id", "settlement_currency"):
            object.__setattr__(self, name, identifier(getattr(self, name), name=name))
        components = tuple(self.components)
        if not components:
            raise ValueError("fee schedule components must not be empty")
        _unique((item.name for item in components), name="fee component names")
        object.__setattr__(self, "components", components)
        for name in ("minimum", "maximum"):
            raw = getattr(self, name)
            if raw is not None:
                object.__setattr__(
                    self,
                    name,
                    decimal_value(raw, name=f"fee {name}", nonnegative=True),
                )
        if self.minimum is not None and self.maximum is not None:
            if cast("Decimal", self.minimum) > cast("Decimal", self.maximum):
                raise ValueError("fee minimum must not exceed maximum")

    def to_dict(self) -> dict[str, object]:
        return {
            "schedule_id": self.schedule_id,
            "instrument_id": self.instrument_id,
            "settlement_currency": self.settlement_currency,
            "minimum": None if self.minimum is None else _decimal(self.minimum),
            "maximum": None if self.maximum is None else _decimal(self.maximum),
            "components": [item.to_dict() for item in self.components],
        }


@dataclass(frozen=True, slots=True)
class FeeExecutionPolicy:
    """Current completed-bar execution configuration with per-instrument fees."""

    participation_bps: int
    fee_schedules: tuple[InstrumentFeeSchedule, ...]
    model: Literal["completed_bar_v1"] = "completed_bar_v1"
    configuration_version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        _basis_points(self.participation_bps, name="participation_bps")
        schedules = tuple(sorted(self.fee_schedules, key=lambda item: item.instrument_id))
        if not schedules:
            raise ValueError("fee_schedules must not be empty")
        _unique((item.schedule_id for item in schedules), name="fee schedule identifiers")
        _unique((item.instrument_id for item in schedules), name="fee schedule instruments")
        object.__setattr__(self, "fee_schedules", schedules)

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "configuration": {
                "version": self.configuration_version,
                "participation_bps": self.participation_bps,
                "fee_schedules": [item.to_dict() for item in self.fee_schedules],
            },
        }


@dataclass(frozen=True, slots=True)
class FinancingPolicy:
    """Version-10 financing accrual, locate, and recall choices."""

    day_count: DayCount
    compounding: Compounding
    borrow_missing_data: MissingFinancingData
    cash_missing_data: MissingFinancingData
    locate_policy: LocatePolicy
    recall_policy: RecallPolicy

    def __post_init__(self) -> None:
        _choice(self.day_count, {"actual_365", "actual_360"}, name="day_count")
        _choice(self.compounding, {"simple", "daily"}, name="compounding")
        _choice(self.borrow_missing_data, {"reject", "zero"}, name="borrow_missing_data")
        _choice(self.cash_missing_data, {"reject", "zero"}, name="cash_missing_data")
        _choice(self.locate_policy, {"reject_order", "clip_fill"}, name="locate_policy")
        _choice(self.recall_policy, {"reject_new_shorts", "close_out"}, name="recall_policy")

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class SettlementCalendar:
    """Versioned canonical business-date set for settlement."""

    calendar_id: str
    business_dates: tuple[date | str, ...]
    version: Literal["1"] = "1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "calendar_id", identifier(self.calendar_id, name="calendar_id"))
        dates = tuple(_date(item, name="settlement business date") for item in self.business_dates)
        _unique(dates, name="settlement business dates")
        if not dates:
            raise ValueError("settlement business_dates must not be empty")
        object.__setattr__(self, "business_dates", tuple(sorted(dates)))

    def to_dict(self) -> dict[str, object]:
        return {
            "calendar_id": self.calendar_id,
            "version": self.version,
            "business_dates": [cast("date", item).isoformat() for item in self.business_dates],
        }


@dataclass(frozen=True, slots=True)
class SettlementRule:
    """Business-day settlement lag for one instrument."""

    instrument_id: str
    calendar_id: str
    lag_business_days: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "instrument_id", identifier(self.instrument_id, name="instrument_id")
        )
        object.__setattr__(self, "calendar_id", identifier(self.calendar_id, name="calendar_id"))
        lag = cast("object", self.lag_business_days)
        if isinstance(lag, bool) or not isinstance(lag, int) or not 0 <= lag <= 30:
            raise ValueError("lag_business_days must be an integer between zero and 30")

    def to_dict(self) -> dict[str, object]:
        return {
            "instrument_id": self.instrument_id,
            "calendar_id": self.calendar_id,
            "lag_business_days": self.lag_business_days,
        }


@dataclass(frozen=True, slots=True)
class SettlementPolicy:
    """Buying-power, availability, calendar, and lag choices."""

    cash_buying_power: CashBuyingPower
    position_availability: PositionAvailability
    calendars: tuple[SettlementCalendar, ...]
    rules: tuple[SettlementRule, ...]

    def __post_init__(self) -> None:
        _choice(self.cash_buying_power, {"total_cash", "settled_cash"}, name="cash_buying_power")
        _choice(
            self.position_availability,
            {"total_positions", "settled_positions"},
            name="position_availability",
        )
        calendars = tuple(sorted(self.calendars, key=lambda item: item.calendar_id))
        rules = tuple(sorted(self.rules, key=lambda item: item.instrument_id))
        if not calendars or not rules:
            raise ValueError("settlement calendars and rules must not be empty")
        _unique((item.calendar_id for item in calendars), name="settlement calendars")
        _unique((item.instrument_id for item in rules), name="settlement rules")
        calendar_ids = {item.calendar_id for item in calendars}
        if any(item.calendar_id not in calendar_ids for item in rules):
            raise ValueError("settlement rule refers to an unknown calendar")
        object.__setattr__(self, "calendars", calendars)
        object.__setattr__(self, "rules", rules)

    def to_dict(self) -> dict[str, object]:
        return {
            "cash_buying_power": self.cash_buying_power,
            "position_availability": self.position_availability,
            "calendars": [item.to_dict() for item in self.calendars],
            "rules": [item.to_dict() for item in self.rules],
        }


@dataclass(frozen=True, slots=True)
class RiskFinancingScenario:
    """One immutable, schema-validated Trading Engine v1 scenario."""

    document: Mapping[str, Any]
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "document",
            freeze_portable_mapping(self.document, name="risk-financing scenario"),
        )

    @property
    def contract_version(self) -> str:
        return RISK_FINANCING_CONTRACT_VERSION

    @property
    def run_id(self) -> str:
        return cast("str", self.document["run_id"])

    def to_dict(self) -> dict[str, Any]:
        return thaw_portable_mapping(self.document)


@dataclass(frozen=True, slots=True)
class RiskFinancingReplay:
    """Schema replay with reconciled risk, fee, accrual, and settlement evidence."""

    replay: SchemaReplayResult
    rejections: tuple[Mapping[str, object], ...]
    clippings: tuple[Mapping[str, object], ...]
    fills: tuple[Mapping[str, object], ...]
    borrow_charges: tuple[Mapping[str, object], ...]
    borrow_recalls: tuple[Mapping[str, object], ...]
    cash_interest: tuple[Mapping[str, object], ...]
    settlement_instructions: tuple[Mapping[str, object], ...]
    settlement_completions: tuple[Mapping[str, object], ...]
    settlement_failures: tuple[Mapping[str, object], ...]
    valuations: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            if name == "replay":
                continue
            values = tuple(
                freeze_portable_mapping(item, name=name)
                for item in cast("tuple[Mapping[str, Any], ...]", getattr(self, name))
            )
            object.__setattr__(self, name, values)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.replay.contract_version,
            "run_id": self.replay.run_id,
            "scenario_sha256": self.replay.scenario_sha256,
            "rejections": len(self.rejections),
            "clippings": len(self.clippings),
            "fills": len(self.fills),
            "borrow_charges": len(self.borrow_charges),
            "borrow_recalls": len(self.borrow_recalls),
            "cash_interest": len(self.cash_interest),
            "settlement_instructions": len(self.settlement_instructions),
            "settlement_completions": len(self.settlement_completions),
            "settlement_failures": len(self.settlement_failures),
            "valuations": len(self.valuations),
            "status": "verified",
        }


def require_risk_financing_capabilities(
    capabilities: EngineCapabilities,
    schemas: TradingEngineContractSchemas,
    *,
    scenario_format: Literal["json", "jsonl"] = "json",
) -> None:
    """Reject an engine or schema set that cannot execute the selected v1 contract."""
    _require_contract(schemas)
    requirements = (
        (
            RISK_FINANCING_CONTRACT_VERSION in capabilities.scenario_contract_versions,
            "scenario v1",
        ),
        (RISK_FINANCING_CONTRACT_VERSION in capabilities.journal_contract_versions, "journal v1"),
        (scenario_format in capabilities.scenario_formats, f"{scenario_format} scenarios"),
        ("jsonl" in capabilities.journal_formats, "JSON Lines journals"),
        ("completed_bar_v1" in capabilities.execution_models, "completed_bar_v1"),
    )
    missing = [name for supported, name in requirements if not supported]
    if missing:
        raise ValueError("incompatible trading-engine capabilities: missing " + ", ".join(missing))


def build_risk_financing_scenario(
    *,
    schemas: TradingEngineContractSchemas,
    base_scenario: Mapping[str, Any],
    risk: RiskFinancingRiskPolicy,
    execution: FeeExecutionPolicy,
    financing: FinancingPolicy,
    settlement: SettlementPolicy,
) -> RiskFinancingScenario:
    """Select v1 policies, validate alignment, and build batch and stream contracts."""
    _require_contract(schemas)
    document = thaw_portable_mapping(
        freeze_portable_mapping(base_scenario, name="base Trading Engine scenario")
    )
    document.update(
        {
            "contract_version": RISK_FINANCING_CONTRACT_VERSION,
            "risk": risk.to_dict(),
            "execution": execution.to_dict(),
            "financing": financing.to_dict(),
            "settlement": settlement.to_dict(),
        }
    )
    _validate_alignment(document, risk=risk, execution=execution, settlement=settlement)
    schemas.validate_scenario(document)
    for line_number, record in enumerate(_stream_records(document), start=1):
        schemas.validate_stream_record(record, line_number=line_number)
    digest = hashlib.sha256(_canonical_json(document)).hexdigest()
    return RiskFinancingScenario(document, digest)


def risk_financing_scenario_to_json(
    scenario: RiskFinancingScenario, *, indent: int | None = 2
) -> str:
    """Serialize one v1 batch scenario."""
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


def risk_financing_scenario_to_jsonl(scenario: RiskFinancingScenario) -> str:
    """Serialize one v1 scenario as JSON Lines records."""
    return "".join(
        json.dumps(item, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        for item in _stream_records(scenario.to_dict())
    )


def write_risk_financing_scenario(
    scenario: RiskFinancingScenario,
    path: str | Path,
    *,
    stream: bool = False,
    overwrite: bool = False,
) -> Path:
    """Write one selected v1 scenario without replacing artifacts by default."""
    from pathlib import Path

    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    content = (
        risk_financing_scenario_to_jsonl(scenario)
        if stream
        else risk_financing_scenario_to_json(scenario)
    )
    with output.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return output


def reconcile_risk_financing_replay(
    schemas: TradingEngineContractSchemas,
    scenario_path: str | Path,
    journal_path: str | Path,
) -> RiskFinancingReplay:
    """Validate and reconcile every v1 risk, fee, financing, and settlement event."""
    _require_contract(schemas)
    replay = schemas.read_replay(scenario_path, journal_path)
    selected: dict[str, list[Mapping[str, object]]] = {
        name: []
        for name in (
            "order_rejected",
            "fill_clipped",
            "fill_applied",
            "borrow_charge_applied",
            "borrow_recall_received",
            "cash_interest_applied",
            "settlement_instruction_created",
            "settlement_completed",
            "settlement_failed",
            "valuation",
        )
    }
    for event in replay.events:
        event_type = event.get("event_type")
        if event_type in selected:
            selected[cast("str", event_type)].append(
                _mapping(event.get("payload"), name=f"{event_type} payload")
            )
    for fill in selected["fill_applied"]:
        _reconcile_fill(fill)
    for item in selected["cash_interest_applied"]:
        _reconcile_cash_interest(item)
    for item in selected["borrow_charge_applied"]:
        _reconcile_borrow_charge(item)
    _reconcile_settlements(selected)
    for valuation in selected["valuation"]:
        _reconcile_valuation(valuation)
    completed = _mapping(replay.events[-1].get("payload"), name="run_completed payload")
    _reconcile_valuation(_mapping(completed.get("valuation"), name="terminal valuation"))
    return RiskFinancingReplay(
        replay,
        tuple(selected["order_rejected"]),
        tuple(selected["fill_clipped"]),
        tuple(selected["fill_applied"]),
        tuple(selected["borrow_charge_applied"]),
        tuple(selected["borrow_recall_received"]),
        tuple(selected["cash_interest_applied"]),
        tuple(selected["settlement_instruction_created"]),
        tuple(selected["settlement_completed"]),
        tuple(selected["settlement_failed"]),
        tuple(selected["valuation"]),
    )


def bind_risk_financing_manifest(
    manifest: Mapping[str, Any], scenario: RiskFinancingScenario
) -> Mapping[str, Any]:
    """Bind exact policy and scenario identities into an immutable replay manifest."""
    document = thaw_portable_mapping(freeze_portable_mapping(manifest, name="replay manifest"))
    contract = document.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("replay manifest contract version differs from risk-financing scenario")
    contract_item = cast("dict[str, object]", contract)
    if contract_item.get("version") != scenario.contract_version:
        raise ValueError("replay manifest contract version differs from risk-financing scenario")
    if "risk_financing" in document:
        raise ValueError("replay manifest already contains risk_financing")
    payload = scenario.to_dict()
    policies = {name: payload[name] for name in ("risk", "execution", "financing", "settlement")}
    document["risk_financing"] = {
        "contract_version": scenario.contract_version,
        "scenario_content_sha256": scenario.sha256,
        "policies_sha256": hashlib.sha256(_canonical_json(policies)).hexdigest(),
        "policies": policies,
    }
    return freeze_portable_mapping(document, name="replay manifest")


def _validate_alignment(
    document: dict[str, Any],
    *,
    risk: RiskFinancingRiskPolicy,
    execution: FeeExecutionPolicy,
    settlement: SettlementPolicy,
) -> None:
    instruments = cast("list[object]", document.get("instruments"))
    instrument_items = [_mapping(item, name="instrument") for item in instruments]
    instrument_ids = {cast("str", item["instrument_id"]) for item in instrument_items}
    currencies = {cast("str", document.get("base_currency"))}
    currencies.update(cast("str", item["quote_currency"]) for item in instrument_items)
    policy_ids = {item.instrument_id for item in risk.instrument_policies}
    schedule_ids = {item.instrument_id for item in execution.fee_schedules}
    rule_ids = {item.instrument_id for item in settlement.rules}
    if policy_ids != instrument_ids or schedule_ids != instrument_ids or rule_ids != instrument_ids:
        raise ValueError("risk, fee, and settlement policies must cover every instrument exactly")
    if any(set(item.instrument_ids) - instrument_ids for item in risk.groups):
        raise ValueError("risk group refers to an unknown instrument")
    if any(item.settlement_currency not in currencies for item in execution.fee_schedules):
        raise ValueError("fee settlement currency is outside the scenario currency catalog")
    for schedule in execution.fee_schedules:
        if any(item.currency not in currencies for item in schedule.components):
            raise ValueError("fee component currency is outside the scenario currency catalog")
    policies = {item.instrument_id: item for item in risk.instrument_policies}
    for instrument in instrument_items:
        policy = policies[cast("str", instrument["instrument_id"])]
        lot = decimal_value(instrument["lot_size"], name="lot_size", positive=True)
        for limit in (
            policy.max_order_quantity,
            policy.max_long_position,
            policy.max_short_position,
        ):
            if cast("Decimal", limit) % lot != 0:
                raise ValueError("instrument risk quantity limits must align to lot size")
    _validate_slice_observations(document, instrument_ids=instrument_ids, currencies=currencies)


def _validate_slice_observations(
    document: Mapping[str, Any], *, instrument_ids: set[str], currencies: set[str]
) -> None:
    slices = cast("list[object]", document.get("slices"))
    for raw in slices:
        item = _mapping(raw, name="market slice")
        start = _timestamp(item.get("start_at"), name="slice start_at")
        borrow = cast("list[object]", item.get("borrow_observations"))
        cash = cast("list[object]", item.get("cash_rate_observations"))
        borrow_ids: list[str] = []
        cash_ids: list[str] = []
        for raw_observation in borrow:
            observation = _mapping(raw_observation, name="borrow observation")
            instrument_id = cast("str", observation.get("instrument_id"))
            if instrument_id not in instrument_ids:
                raise ValueError("borrow observation refers to an unknown instrument")
            if _timestamp(observation.get("effective_at"), name="borrow effective_at") > start:
                raise ValueError("borrow observation must be effective by slice start")
            borrow_ids.append(instrument_id)
        for raw_observation in cash:
            observation = _mapping(raw_observation, name="cash rate observation")
            currency = cast("str", observation.get("currency"))
            if currency not in currencies:
                raise ValueError("cash rate observation refers to an unknown currency")
            if _timestamp(observation.get("effective_at"), name="cash effective_at") > start:
                raise ValueError("cash rate observation must be effective by slice start")
            cash_ids.append(currency)
        _unique(borrow_ids, name="slice borrow observations")
        _unique(cash_ids, name="slice cash rate observations")


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
            "contract_version": RISK_FINANCING_CONTRACT_VERSION,
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
                "contract_version": RISK_FINANCING_CONTRACT_VERSION,
                "scenario_sequence": str(index),
                "record_type": "market_slice",
                "payload": {"market_slice": item, "intents": intents.pop(sequence, [])},
            }
        )
    if intents:
        raise ValueError("schedule refers to a missing market slice")
    records.append(
        {
            "contract_version": RISK_FINANCING_CONTRACT_VERSION,
            "scenario_sequence": str(len(records) + 1),
            "record_type": "scenario_end",
            "payload": {"slice_count": str(len(slices))},
        }
    )
    return tuple(records)


def _reconcile_fill(payload: Mapping[str, object]) -> None:
    quantity = _number(payload, "quantity")
    price = _number(payload, "price")
    if _number(payload, "notional") != quantity * price:
        raise TradingEngineContractError("fill notional does not reconcile to quantity and price")
    components = cast("list[object]", payload.get("fee_components"))
    total = sum(
        (_number(_mapping(item, name="fee component"), "quote_amount") for item in components),
        Decimal(0),
    )
    if total != _number(payload, "fee"):
        raise TradingEngineContractError("fill fee does not reconcile to fee components")


def _reconcile_cash_interest(payload: Mapping[str, object]) -> None:
    if _number(payload, "opening_balance") + _number(payload, "amount") != _number(
        payload, "closing_balance"
    ):
        raise TradingEngineContractError(
            "cash interest does not reconcile opening and closing cash"
        )
    observation = _mapping(payload.get("observation"), name="cash interest observation")
    opening = _number(payload, "opening_balance")
    expected_rate = observation.get("credit_rate_bps" if opening >= 0 else "debit_rate_bps")
    if payload.get("applied_rate_bps") != expected_rate:
        raise TradingEngineContractError("cash interest applied rate differs from observation")


def _reconcile_borrow_charge(payload: Mapping[str, object]) -> None:
    observation = _mapping(payload.get("observation"), name="borrow charge observation")
    if payload.get("quote_currency") is None or observation.get("instrument_id") is None:
        raise TradingEngineContractError("borrow charge omits instrument or currency attribution")
    if _number(payload, "short_quantity") <= 0 or _number(payload, "reference_price") <= 0:
        raise TradingEngineContractError("borrow charge quantity and price must be positive")


def _reconcile_settlements(selected: Mapping[str, list[Mapping[str, object]]]) -> None:
    fills = {cast("str", item["fill_id"]) for item in selected["fill_applied"]}
    created: dict[str, Mapping[str, object]] = {}
    for item in selected["settlement_instruction_created"]:
        instruction_id = cast("str", item["instruction_id"])
        if instruction_id in created:
            raise TradingEngineContractError("settlement instruction identifier is duplicated")
        if item.get("fill_id") not in fills or item.get("status") != "pending":
            raise TradingEngineContractError("settlement instruction does not reconcile to a fill")
        created[instruction_id] = item
    if len(created) != len(fills):
        raise TradingEngineContractError("every fill must create one settlement instruction")
    final: set[str] = set()
    for event_type in ("settlement_completed", "settlement_failed"):
        expected_status = "settled" if event_type == "settlement_completed" else "failed"
        for item in selected[event_type]:
            instruction_id = cast("str", item["instruction_id"])
            original = created.get(instruction_id)
            if original is None or instruction_id in final or item.get("status") != expected_status:
                raise TradingEngineContractError(
                    "settlement completion does not match an instruction"
                )
            for name in (
                "fill_id",
                "instrument_id",
                "currency",
                "cash_movement",
                "position_movement",
                "trade_date",
                "due_date",
            ):
                if item.get(name) != original.get(name):
                    raise TradingEngineContractError(
                        "settlement attribution differs from instruction"
                    )
            final.add(instruction_id)


def _reconcile_valuation(payload: Mapping[str, object]) -> None:
    cash_rows = cast("list[object]", payload.get("cash_balances"))
    position_rows = cast("list[object]", payload.get("positions"))
    cash = sum(
        (_number(_mapping(item, name="cash attribution"), "base_value") for item in cash_rows),
        Decimal(0),
    )
    settled_cash = sum(
        (
            _number(_mapping(item, name="cash attribution"), "base_settled_value")
            for item in cash_rows
        ),
        Decimal(0),
    )
    unsettled_cash = sum(
        (
            _number(_mapping(item, name="cash attribution"), "base_unsettled_value")
            for item in cash_rows
        ),
        Decimal(0),
    )
    interest = sum(
        (_number(_mapping(item, name="cash attribution"), "base_interest") for item in cash_rows),
        Decimal(0),
    )
    for raw in position_rows:
        item = _mapping(raw, name="position attribution")
        if _number(item, "settled_quantity") + _number(item, "unsettled_quantity") != _number(
            item, "quantity"
        ):
            raise TradingEngineContractError(
                "settled and unsettled position quantities do not reconcile"
            )
    checks = (
        (cash, _number(payload, "cash"), "cash attribution"),
        (settled_cash, _number(payload, "settled_cash"), "settled cash"),
        (unsettled_cash, _number(payload, "unsettled_cash"), "unsettled cash"),
        (interest, _number(payload, "cash_interest"), "cash interest"),
        (
            _number(payload, "long_market_value") - _number(payload, "short_market_value"),
            _number(payload, "net_market_value"),
            "net market value",
        ),
        (
            _number(payload, "long_market_value") + _number(payload, "short_market_value"),
            _number(payload, "gross_exposure"),
            "gross exposure",
        ),
        (
            _number(payload, "cash") + _number(payload, "net_market_value"),
            _number(payload, "equity"),
            "equity",
        ),
        (
            _number(payload, "execution_fees") + _number(payload, "borrow_fees"),
            _number(payload, "total_fees"),
            "total fees",
        ),
    )
    for actual, expected, name in checks:
        if actual != expected:
            raise TradingEngineContractError(f"valuation {name} does not reconcile")


def _require_contract(schemas: TradingEngineContractSchemas) -> None:
    if schemas.version != RISK_FINANCING_CONTRACT_VERSION:
        raise ValueError("risk and financing support requires Trading Engine contract v1")


def _mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TradingEngineContractError(f"{name} must be an object")
    result: dict[str, object] = {}
    for key, item in cast("Mapping[object, object]", value).items():
        if not isinstance(key, str):
            raise TradingEngineContractError(f"{name} keys must be strings")
        result[key] = item
    return result


def _number(value: Mapping[str, object], name: str) -> Decimal:
    return decimal_value(value.get(name), name=name)


def _decimal(value: object) -> str:
    return decimal_string(cast("Decimal", value))


def _basis_points(value: object, *, name: str, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    minimum = 1 if positive else 0
    if not minimum <= value <= 10_000:
        raise ValueError(f"{name} must be between {minimum} and 10000")


def _choice(value: object, choices: set[str], *, name: str) -> None:
    if value not in choices:
        raise ValueError(f"unsupported {name}: {value!r}")


def _unique(values: Iterable[object], *, name: str) -> None:
    selected = tuple(values)
    if len(selected) != len(set(selected)):
        raise ValueError(f"{name} must be unique")


def _date(value: date | str, *, name: str) -> date:
    if isinstance(value, datetime):
        raise TypeError(f"{name} must be a date without a time")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO date") from error


def _timestamp(value: object, *, name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a UTC offset")
    return parsed


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
