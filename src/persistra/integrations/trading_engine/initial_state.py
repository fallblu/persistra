"""Typed Trading Engine initial portfolio scenarios and reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.integrations.trading_engine._scalars import (
    decimal_string,
    decimal_value,
    execution_quantity,
    identifier,
    quantity_value,
    weight_toward_zero,
)
from persistra.integrations.trading_engine.contracts import (
    SchemaReplayResult,
    TradingEngineContractError,
    TradingEngineContractSchemas,
)
from persistra.integrations.trading_engine.model import ExecutionInstrument
from persistra.integrations.trading_engine.risk_financing import (
    FinancingPolicy,
    InstrumentRiskPolicy,
    RiskFinancingRiskPolicy,
    RiskGroup,
    RiskGroupLimits,
    SettlementCalendar,
    SettlementPolicy,
    SettlementRule,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


INITIAL_STATE_CONTRACT_VERSION: Final = "1"
_MICRO = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class InitialCashBalance:
    """One signed native-currency cash ledger at replay start."""

    currency: str
    amount: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", identifier(self.currency, name="currency"))
        object.__setattr__(self, "amount", decimal_value(self.amount, name="amount"))


@dataclass(frozen=True, slots=True)
class InitialPosition:
    """One signed opening quantity with complete accounting attribution."""

    instrument_id: str
    quantity: Decimal | str | int | float
    cost_basis: Decimal | str | int | float
    realized_pnl: Decimal | str | int | float = Decimal(0)
    dividend_pnl: Decimal | str | int | float = Decimal(0)
    execution_fees: Decimal | str | int | float = Decimal(0)
    borrow_fees: Decimal | str | int | float = Decimal(0)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        quantity = execution_quantity(self.quantity, name="initial quantity")
        if quantity == 0:
            raise ValueError("initial position quantity must be nonzero")
        basis = decimal_value(self.cost_basis, name="initial cost_basis")
        if (quantity > 0) != (basis > 0):
            raise ValueError("initial cost_basis must have the same sign as quantity")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "cost_basis", basis)
        for name in ("realized_pnl", "dividend_pnl"):
            object.__setattr__(
                self,
                name,
                decimal_value(getattr(self, name), name=f"initial {name}"),
            )
        for name in ("execution_fees", "borrow_fees"):
            object.__setattr__(
                self,
                name,
                decimal_value(
                    getattr(self, name),
                    name=f"initial {name}",
                    nonnegative=True,
                ),
            )


@dataclass(frozen=True, slots=True)
class InitialMark:
    """One positive opening price for an initial position."""

    instrument_id: str
    price: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "instrument_id",
            identifier(self.instrument_id, name="instrument_id"),
        )
        object.__setattr__(
            self,
            "price",
            decimal_value(self.price, name="initial mark", positive=True),
        )


@dataclass(frozen=True, slots=True)
class InitialFxRate:
    """One positive currency-to-base opening rate."""

    currency: str
    rate: Decimal | str | int | float

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency", identifier(self.currency, name="currency"))
        object.__setattr__(
            self,
            "rate",
            decimal_value(self.rate, name="initial FX rate", positive=True),
        )


@dataclass(frozen=True, slots=True)
class InitialPortfolioState:
    """One intrinsically coherent immutable opening portfolio."""

    cash: tuple[InitialCashBalance, ...]
    positions: tuple[InitialPosition, ...]
    marks: tuple[InitialMark, ...]
    fx_rates: tuple[InitialFxRate, ...]

    def __post_init__(self) -> None:
        for name in ("cash", "positions", "marks", "fx_rates"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not self.cash:
            raise ValueError("initial cash must contain at least one currency")
        _unique((item.currency for item in self.cash), name="initial cash currencies")
        position_ids = tuple(item.instrument_id for item in self.positions)
        mark_ids = tuple(item.instrument_id for item in self.marks)
        _unique(position_ids, name="initial position instruments")
        _unique(mark_ids, name="initial mark instruments")
        if set(position_ids) != set(mark_ids):
            raise ValueError("initial marks must cover every initial position exactly once")
        fx_currencies = tuple(item.currency for item in self.fx_rates)
        _unique(fx_currencies, name="initial FX currencies")
        if {item.currency for item in self.cash} != set(fx_currencies):
            raise ValueError("initial FX rates must cover every cash currency exactly once")
        object.__setattr__(self, "cash", tuple(sorted(self.cash, key=lambda item: item.currency)))
        object.__setattr__(
            self,
            "positions",
            tuple(sorted(self.positions, key=lambda item: item.instrument_id)),
        )
        object.__setattr__(
            self,
            "marks",
            tuple(sorted(self.marks, key=lambda item: item.instrument_id)),
        )
        object.__setattr__(
            self,
            "fx_rates",
            tuple(sorted(self.fx_rates, key=lambda item: item.currency)),
        )

    def to_dict(self) -> dict[str, object]:
        """Return the exact scenario v1 initial-portfolio payload."""
        return {
            "cash": [
                {"currency": item.currency, "amount": decimal_string(cast("Decimal", item.amount))}
                for item in self.cash
            ],
            "positions": [
                {
                    "instrument_id": item.instrument_id,
                    "quantity": decimal_string(cast("Decimal", item.quantity)),
                    "cost_basis": decimal_string(cast("Decimal", item.cost_basis)),
                    "realized_pnl": decimal_string(cast("Decimal", item.realized_pnl)),
                    "dividend_pnl": decimal_string(cast("Decimal", item.dividend_pnl)),
                    "execution_fees": decimal_string(cast("Decimal", item.execution_fees)),
                    "borrow_fees": decimal_string(cast("Decimal", item.borrow_fees)),
                }
                for item in self.positions
            ],
            "marks": [
                {
                    "instrument_id": item.instrument_id,
                    "price": decimal_string(cast("Decimal", item.price)),
                }
                for item in self.marks
            ],
            "fx_rates": [
                {"currency": item.currency, "rate": decimal_string(cast("Decimal", item.rate))}
                for item in self.fx_rates
            ],
        }

    @property
    def sha256(self) -> str:
        """Return the canonical initial-portfolio content identity."""
        return hashlib.sha256(_canonical_json(self.to_dict())).hexdigest()


@dataclass(frozen=True, slots=True)
class InitialStateScenario:
    """One complete schema-v1 scenario containing a typed initial portfolio."""

    run_id: str
    base_currency: str
    initial_portfolio: InitialPortfolioState
    instruments: tuple[ExecutionInstrument, ...]
    venue_calendars: tuple[Mapping[str, Any], ...]
    risk: RiskFinancingRiskPolicy
    execution: Mapping[str, Any]
    financing: FinancingPolicy
    settlement: SettlementPolicy
    max_internal_events: int
    metadata: Mapping[str, Any]
    schedule: tuple[Mapping[str, Any], ...]
    slices: tuple[Mapping[str, Any], ...]
    contract_version: Literal["1"] = field(
        default=INITIAL_STATE_CONTRACT_VERSION,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", identifier(self.run_id, name="run_id"))
        object.__setattr__(
            self,
            "base_currency",
            identifier(self.base_currency, name="base_currency"),
        )
        instruments = tuple(sorted(self.instruments, key=lambda item: item.instrument_id))
        if not instruments:
            raise ValueError("initial-state scenario requires instruments")
        _unique(
            (item.instrument_id for item in instruments),
            name="execution instrument identifiers",
        )
        object.__setattr__(self, "instruments", instruments)
        object.__setattr__(
            self,
            "max_internal_events",
            quantity_value(
                self.max_internal_events,
                name="max_internal_events",
                positive=True,
            ),
        )
        for name in ("venue_calendars", "schedule", "slices"):
            values = tuple(
                freeze_portable_mapping(value, name=name) for value in getattr(self, name)
            )
            object.__setattr__(self, name, values)
        object.__setattr__(
            self,
            "execution",
            freeze_portable_mapping(self.execution, name="execution"),
        )
        object.__setattr__(
            self,
            "metadata",
            freeze_portable_mapping(self.metadata, name="metadata"),
        )
        _validate_portfolio_policy(self)

    def to_dict(self) -> dict[str, object]:
        """Return the exact complete scenario v1 document."""
        return {
            "contract_version": self.contract_version,
            "metadata": thaw_portable_mapping(self.metadata),
            "run_id": self.run_id,
            "base_currency": self.base_currency,
            "initial_portfolio": self.initial_portfolio.to_dict(),
            "instruments": [_instrument_payload(item) for item in self.instruments],
            "venue_calendars": [thaw_portable_mapping(item) for item in self.venue_calendars],
            "risk": _risk_payload(self.risk),
            "execution": thaw_portable_mapping(self.execution),
            "financing": self.financing.to_dict(),
            "settlement": self.settlement.to_dict(),
            "max_internal_events": self.max_internal_events,
            "schedule": [thaw_portable_mapping(item) for item in self.schedule],
            "slices": [thaw_portable_mapping(item) for item in self.slices],
        }


@dataclass(frozen=True, slots=True)
class InitialStateReconciliation:
    """Verified schema replay with reconciled opening audit evidence."""

    replay: SchemaReplayResult
    portfolio_sha256: str
    initial_state_sequence: int
    first_valuation_sequence: int
    valuation: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "valuation",
            freeze_portable_mapping(self.valuation, name="initial valuation"),
        )

    def to_dict(self) -> dict[str, object]:
        """Return stable manifest-ready reconciliation evidence."""
        return {
            "contract_version": self.replay.contract_version,
            "run_id": self.replay.run_id,
            "scenario_sha256": self.replay.scenario_sha256,
            "initial_portfolio_sha256": self.portfolio_sha256,
            "initial_state_sequence": self.initial_state_sequence,
            "first_valuation_sequence": self.first_valuation_sequence,
            "status": "verified",
        }


def build_initial_state_scenario(
    *,
    schemas: TradingEngineContractSchemas,
    run_id: str,
    base_currency: str,
    initial_portfolio: InitialPortfolioState,
    instruments: Sequence[ExecutionInstrument],
    venue_calendars: Sequence[Mapping[str, Any]],
    risk: RiskFinancingRiskPolicy,
    execution: Mapping[str, Any],
    financing: FinancingPolicy,
    settlement: SettlementPolicy,
    max_internal_events: int,
    metadata: Mapping[str, Any] | None = None,
    schedule: Sequence[Mapping[str, Any]] = (),
    slices: Sequence[Mapping[str, Any]] = (),
) -> InitialStateScenario:
    """Build and structurally validate one complete scenario v1 document."""
    _require_contract(schemas)
    scenario = InitialStateScenario(
        run_id,
        base_currency,
        initial_portfolio,
        tuple(instruments),
        tuple(venue_calendars),
        risk,
        execution,
        financing,
        settlement,
        max_internal_events,
        {} if metadata is None else metadata,
        tuple(schedule),
        tuple(slices),
    )
    schemas.validate_scenario(scenario.to_dict())
    for line_number, record in enumerate(_stream_records(scenario), start=1):
        schemas.validate_stream_record(record, line_number=line_number)
    return scenario


def initial_state_scenario_to_json(
    scenario: InitialStateScenario, *, indent: int | None = 2
) -> str:
    """Serialize one batch scenario using canonical decimal strings."""
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


def initial_state_scenario_to_jsonl(scenario: InitialStateScenario) -> str:
    """Serialize one scenario as bounded-memory v1 JSON Lines records."""
    return "".join(
        json.dumps(record, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
        for record in _stream_records(scenario)
    )


def write_initial_state_scenario(
    scenario: InitialStateScenario,
    path: str | Path,
    *,
    stream: bool = False,
    overwrite: bool = False,
) -> Path:
    """Write one batch or JSON Lines initial-state scenario without replacement."""
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    document = (
        initial_state_scenario_to_jsonl(scenario)
        if stream
        else initial_state_scenario_to_json(scenario)
    )
    with output.open("w" if overwrite else "x", encoding="utf-8", newline="\n") as handle:
        handle.write(document)
    return output


def reconcile_initial_state_replay(
    schemas: TradingEngineContractSchemas,
    scenario_path: str | Path,
    journal_path: str | Path,
) -> InitialStateReconciliation:
    """Reconcile opening portfolio and valuation evidence against a v1 scenario."""
    _require_contract(schemas)
    scenario_file = Path(scenario_path)
    try:
        raw = json.loads(scenario_file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TradingEngineContractError("invalid initial-state scenario JSON") from error
    schemas.validate_scenario(raw)
    scenario = _scenario_from_document(raw)
    replay = schemas.read_replay(scenario_file, journal_path)
    events = replay.events
    if len(events) < 3 or events[1].get("event_type") != "initial_state":
        raise TradingEngineContractError("journal must record initial_state after run_started")
    initial_payload = _mapping(events[1].get("payload"), name="initial_state payload")
    portable_initial_payload = thaw_portable_mapping(initial_payload)
    if portable_initial_payload.get("portfolio") != scenario.initial_portfolio.to_dict():
        raise TradingEngineContractError("journal initial portfolio differs from scenario")
    valuation = _mapping(
        portable_initial_payload.get("valuation"),
        name="initial_state valuation",
    )
    expected = _expected_valuation(scenario)
    if valuation != expected:
        raise TradingEngineContractError("journal initial valuation differs from scenario")
    first_valuation = events[2]
    if first_valuation.get("event_type") != "valuation":
        raise TradingEngineContractError("journal must value the initial state before replay")
    first_payload = thaw_portable_mapping(
        _mapping(first_valuation.get("payload"), name="first valuation payload")
    )
    if first_payload != valuation:
        raise TradingEngineContractError("first journal valuation differs from initial_state")
    return InitialStateReconciliation(
        replay,
        scenario.initial_portfolio.sha256,
        _sequence(events[1]),
        _sequence(first_valuation),
        valuation,
    )


def bind_initial_state_manifest(
    manifest: Mapping[str, Any], scenario: InitialStateScenario
) -> Mapping[str, Any]:
    """Return an immutable replay manifest with explicit v1 opening-state identity."""
    document = thaw_portable_mapping(freeze_portable_mapping(manifest, name="replay manifest"))
    contract = document.get("contract")
    if not isinstance(contract, dict):
        raise ValueError("replay manifest contract version differs from initial-state scenario")
    typed_contract = cast("dict[str, object]", contract)
    if typed_contract.get("version") != scenario.contract_version:
        raise ValueError("replay manifest contract version differs from initial-state scenario")
    if "initial_state" in document:
        raise ValueError("replay manifest already contains initial_state")
    document["initial_state"] = {
        "contract_version": scenario.contract_version,
        "portfolio_sha256": scenario.initial_portfolio.sha256,
        "portfolio": scenario.initial_portfolio.to_dict(),
    }
    return freeze_portable_mapping(document, name="replay manifest")


def _validate_portfolio_policy(scenario: InitialStateScenario) -> None:
    state = scenario.initial_portfolio
    instruments = {item.instrument_id: item for item in scenario.instruments}
    currencies = {scenario.base_currency, *(item.quote_currency for item in scenario.instruments)}
    cash = {item.currency: cast("Decimal", item.amount) for item in state.cash}
    fx = {item.currency: cast("Decimal", item.rate) for item in state.fx_rates}
    if set(cash) != currencies or set(fx) != currencies:
        raise ValueError(
            "initial cash and FX rates must cover every scenario currency exactly once"
        )
    if fx[scenario.base_currency] != 1:
        raise ValueError("initial base-currency FX rate must equal one")
    marks = {item.instrument_id: cast("Decimal", item.price) for item in state.marks}
    policies = {item.instrument_id: item for item in scenario.risk.instrument_policies}
    if set(policies) != set(instruments):
        raise ValueError("risk policies must cover every scenario instrument exactly once")
    settlement_rules = {item.instrument_id for item in scenario.settlement.rules}
    if settlement_rules != set(instruments):
        raise ValueError("settlement policies must cover every scenario instrument exactly once")
    if any(set(item.instrument_ids) - set(instruments) for item in scenario.risk.groups):
        raise ValueError("risk group refers to an unknown instrument")
    gross = Decimal(0)
    net = Decimal(0)
    initial_requirement = Decimal(0)
    for position in state.positions:
        instrument = instruments.get(position.instrument_id)
        if instrument is None:
            raise ValueError("initial position refers to an unknown instrument")
        quantity = cast("Decimal", position.quantity)
        lot = cast("Decimal", instrument.lot_size)
        policy = policies[position.instrument_id]
        if quantity % lot != 0:
            raise ValueError("initial position quantity is not aligned to its instrument lot")
        if quantity > cast("Decimal", policy.max_long_position):
            raise ValueError("initial position exceeds maximum long position")
        if quantity < -cast("Decimal", policy.max_short_position):
            raise ValueError("initial position exceeds maximum short position")
        if quantity < 0 and not policy.shorting_allowed:
            raise ValueError("initial short position is not allowed")
        mark = marks[position.instrument_id]
        if mark % cast("Decimal", instrument.tick_size) != 0:
            raise ValueError("initial mark is not aligned to its instrument tick size")
        base_value = quantity * mark * fx[instrument.quote_currency]
        if abs(base_value) > cast("Decimal", policy.max_notional_exposure):
            raise ValueError("initial position exceeds maximum notional exposure")
        net += base_value
        gross += abs(base_value)
        initial_requirement += _bps_ceil(abs(base_value), policy.initial_margin_bps)
    base_cash = sum((amount * fx[currency] for currency, amount in cash.items()), Decimal(0))
    equity = base_cash + net
    if gross > cast("Decimal", scenario.risk.max_gross_exposure):
        raise ValueError("initial portfolio exceeds maximum gross exposure")
    if gross > equity * cast("Decimal", scenario.risk.max_leverage):
        raise ValueError("initial portfolio exceeds maximum leverage")
    if equity - initial_requirement < 0:
        raise ValueError("initial portfolio violates initial margin")


def _expected_valuation(scenario: InitialStateScenario) -> dict[str, object]:
    state = scenario.initial_portfolio
    instruments = {item.instrument_id: item for item in scenario.instruments}
    cash = {item.currency: cast("Decimal", item.amount) for item in state.cash}
    fx = {item.currency: cast("Decimal", item.rate) for item in state.fx_rates}
    marks = {item.instrument_id: cast("Decimal", item.price) for item in state.marks}
    policies = {item.instrument_id: item for item in scenario.risk.instrument_policies}
    initial = Decimal(0)
    maintenance = Decimal(0)
    rows: list[dict[str, object]] = []
    base_market_values: dict[str, Decimal] = {}
    totals = {
        name: Decimal(0)
        for name in (
            "net",
            "long",
            "short",
            "gross",
            "cost",
            "realized",
            "unrealized",
            "dividend",
            "execution",
            "borrow",
            "fees",
        )
    }
    for position in state.positions:
        instrument = instruments[position.instrument_id]
        rate = fx[instrument.quote_currency]
        quantity = cast("Decimal", position.quantity)
        mark = marks[position.instrument_id]
        market = quantity * mark
        base_market = market * rate
        base_market_values[position.instrument_id] = base_market
        cost = cast("Decimal", position.cost_basis)
        realized = cast("Decimal", position.realized_pnl)
        unrealized = market - cost
        dividend = cast("Decimal", position.dividend_pnl)
        execution = cast("Decimal", position.execution_fees)
        borrow = cast("Decimal", position.borrow_fees)
        fees = execution + borrow
        totals["net"] += base_market
        totals["long"] += max(base_market, Decimal(0))
        totals["short"] += max(-base_market, Decimal(0))
        totals["gross"] += abs(base_market)
        totals["cost"] += cost * rate
        totals["realized"] += realized * rate
        totals["unrealized"] += unrealized * rate
        totals["dividend"] += dividend * rate
        totals["execution"] += execution * rate
        totals["borrow"] += borrow * rate
        totals["fees"] += fees * rate
        policy = policies[position.instrument_id]
        initial += _bps_ceil(abs(base_market), policy.initial_margin_bps)
        maintenance += _bps_ceil(abs(base_market), policy.maintenance_margin_bps)
        rows.append(
            {
                "instrument_id": position.instrument_id,
                "quote_currency": instrument.quote_currency,
                "quantity": decimal_string(quantity),
                "settled_quantity": decimal_string(quantity),
                "unsettled_quantity": "0",
                "mark": decimal_string(mark),
                "fx_rate": decimal_string(rate),
                "market_value": decimal_string(market),
                "base_market_value": decimal_string(base_market),
                "cost_basis": decimal_string(cost),
                "base_cost_basis": decimal_string(cost * rate),
                "realized_pnl": decimal_string(realized),
                "base_realized_pnl": decimal_string(realized * rate),
                "unrealized_pnl": decimal_string(unrealized),
                "base_unrealized_pnl": decimal_string(unrealized * rate),
                "dividend_pnl": decimal_string(dividend),
                "base_dividend_pnl": decimal_string(dividend * rate),
                "execution_fees": decimal_string(execution),
                "base_execution_fees": decimal_string(execution * rate),
                "execution_fee_components": [],
                "borrow_fees": decimal_string(borrow),
                "base_borrow_fees": decimal_string(borrow * rate),
                "total_fees": decimal_string(fees),
                "base_total_fees": decimal_string(fees * rate),
            }
        )
    base_cash = sum((amount * fx[currency] for currency, amount in cash.items()), Decimal(0))
    equity = base_cash + totals["net"]
    group_exposures: list[dict[str, object]] = []
    for group in scenario.risk.groups:
        member_values = [
            base_market_values.get(instrument_id, Decimal(0))
            for instrument_id in group.instrument_ids
        ]
        group_net = sum(member_values, Decimal(0))
        group_long = sum((max(value, Decimal(0)) for value in member_values), Decimal(0))
        group_short = sum((max(-value, Decimal(0)) for value in member_values), Decimal(0))
        group_gross = group_long + group_short
        group_exposures.append(
            {
                "group_id": group.group_id,
                "gross_exposure": decimal_string(group_gross),
                "net_exposure": decimal_string(group_net),
                "long_exposure": decimal_string(group_long),
                "short_exposure": decimal_string(group_short),
                "concentration": (
                    None
                    if equity <= 0
                    else decimal_string(weight_toward_zero(group_gross, equity=equity))
                ),
            }
        )
    return {
        "base_currency": scenario.base_currency,
        "cash": decimal_string(base_cash),
        "settled_cash": decimal_string(base_cash),
        "unsettled_cash": "0",
        "net_market_value": decimal_string(totals["net"]),
        "long_market_value": decimal_string(totals["long"]),
        "short_market_value": decimal_string(totals["short"]),
        "gross_exposure": decimal_string(totals["gross"]),
        "cost_basis": decimal_string(totals["cost"]),
        "realized_pnl": decimal_string(totals["realized"]),
        "unrealized_pnl": decimal_string(totals["unrealized"]),
        "equity": decimal_string(equity),
        "dividend_pnl": decimal_string(totals["dividend"]),
        "execution_fees": decimal_string(totals["execution"]),
        "borrow_fees": decimal_string(totals["borrow"]),
        "total_fees": decimal_string(totals["fees"]),
        "cash_interest": "0",
        "execution_fee_components": [],
        "group_exposures": group_exposures,
        "cash_balances": [
            {
                "currency": item.currency,
                "amount": decimal_string(cast("Decimal", item.amount)),
                "settled_amount": decimal_string(cast("Decimal", item.amount)),
                "unsettled_amount": "0",
                "fx_rate": decimal_string(fx[item.currency]),
                "base_value": decimal_string(cast("Decimal", item.amount) * fx[item.currency]),
                "base_settled_value": decimal_string(
                    cast("Decimal", item.amount) * fx[item.currency]
                ),
                "base_unsettled_value": "0",
                "interest": "0",
                "base_interest": "0",
            }
            for item in state.cash
        ],
        "positions": rows,
        "margin": {
            "initial_requirement": decimal_string(initial),
            "maintenance_requirement": decimal_string(maintenance),
            "initial_excess": decimal_string(equity - initial),
            "maintenance_excess": decimal_string(equity - maintenance),
            "margin_call": equity - maintenance < 0,
        },
    }


def _stream_records(scenario: InitialStateScenario) -> tuple[dict[str, object], ...]:
    batch = scenario.to_dict()
    header = {
        key: value
        for key, value in batch.items()
        if key not in {"contract_version", "schedule", "slices"}
    }
    intents: dict[str, object] = {}
    for item in cast("list[object]", batch["schedule"]):
        value = _mapping(item, name="schedule item")
        sequence = value.get("after_slice_sequence")
        if not isinstance(sequence, str) or sequence in intents:
            raise ValueError("schedule sequences must be unique canonical strings")
        intents[sequence] = value.get("intents")
    records: list[dict[str, object]] = [
        {
            "contract_version": INITIAL_STATE_CONTRACT_VERSION,
            "scenario_sequence": "1",
            "record_type": "scenario_header",
            "payload": header,
        }
    ]
    slices = cast("list[object]", batch["slices"])
    for index, raw_slice in enumerate(slices, start=2):
        market_slice = _mapping(raw_slice, name="market slice")
        slice_sequence = market_slice.get("slice_sequence")
        records.append(
            {
                "contract_version": INITIAL_STATE_CONTRACT_VERSION,
                "scenario_sequence": str(index),
                "record_type": "market_slice",
                "payload": {
                    "market_slice": market_slice,
                    "intents": intents.pop(cast("str", slice_sequence), []),
                },
            }
        )
    if intents:
        raise ValueError("schedule refers to a missing market slice")
    records.append(
        {
            "contract_version": INITIAL_STATE_CONTRACT_VERSION,
            "scenario_sequence": str(len(records) + 1),
            "record_type": "scenario_end",
            "payload": {"slice_count": str(len(slices))},
        }
    )
    return tuple(records)


def _scenario_from_document(value: object) -> InitialStateScenario:
    item = _mapping(value, name="scenario")
    if item.get("contract_version") != INITIAL_STATE_CONTRACT_VERSION:
        raise TradingEngineContractError("initial-state scenario must use contract version 1")
    return InitialStateScenario(
        cast("str", item["run_id"]),
        cast("str", item["base_currency"]),
        _portfolio_from_document(item["initial_portfolio"]),
        tuple(_instrument_from_document(raw) for raw in cast("list[object]", item["instruments"])),
        tuple(cast("list[Mapping[str, Any]]", item["venue_calendars"])),
        _risk_from_document(item["risk"]),
        cast("Mapping[str, Any]", item["execution"]),
        _financing_from_document(item["financing"]),
        _settlement_from_document(item["settlement"]),
        cast("int", item["max_internal_events"]),
        cast("Mapping[str, Any]", item["metadata"]),
        tuple(cast("list[Mapping[str, Any]]", item["schedule"])),
        tuple(cast("list[Mapping[str, Any]]", item["slices"])),
    )


def _portfolio_from_document(value: object) -> InitialPortfolioState:
    item = _mapping(value, name="initial_portfolio")
    return InitialPortfolioState(
        tuple(
            InitialCashBalance(**cast("dict[str, Any]", raw))
            for raw in cast("list[object]", item["cash"])
        ),
        tuple(
            InitialPosition(**cast("dict[str, Any]", raw))
            for raw in cast("list[object]", item["positions"])
        ),
        tuple(
            InitialMark(**cast("dict[str, Any]", raw))
            for raw in cast("list[object]", item["marks"])
        ),
        tuple(
            InitialFxRate(**cast("dict[str, Any]", raw))
            for raw in cast("list[object]", item["fx_rates"])
        ),
    )


def _instrument_from_document(value: object) -> ExecutionInstrument:
    return ExecutionInstrument(**cast("dict[str, Any]", _mapping(value, name="instrument")))


def _risk_from_document(value: object) -> RiskFinancingRiskPolicy:
    item = _mapping(value, name="risk")
    policies = tuple(
        InstrumentRiskPolicy(**cast("dict[str, Any]", _mapping(raw, name="instrument policy")))
        for raw in cast("list[object]", item["instrument_policies"])
    )
    groups: list[RiskGroup] = []
    for raw in cast("list[object]", item["groups"]):
        group = _mapping(raw, name="risk group")
        groups.append(
            RiskGroup(
                group_id=cast("str", group["group_id"]),
                group_type=cast("Any", group["group_type"]),
                instrument_ids=tuple(cast("list[str]", group["instrument_ids"])),
                limits=RiskGroupLimits(
                    **cast("dict[str, Any]", _mapping(group["limits"], name="risk limits"))
                ),
                group_version=cast("Literal['1']", group["group_version"]),
            )
        )
    return RiskFinancingRiskPolicy(
        max_gross_exposure=cast("Any", item["max_gross_exposure"]),
        max_leverage=cast("Any", item["max_leverage"]),
        instrument_policies=policies,
        groups=tuple(groups),
    )


def _financing_from_document(value: object) -> FinancingPolicy:
    return FinancingPolicy(**cast("dict[str, Any]", _mapping(value, name="financing")))


def _settlement_from_document(value: object) -> SettlementPolicy:
    item = _mapping(value, name="settlement")
    calendars = tuple(
        SettlementCalendar(**cast("dict[str, Any]", _mapping(raw, name="settlement calendar")))
        for raw in cast("list[object]", item["calendars"])
    )
    rules = tuple(
        SettlementRule(**cast("dict[str, Any]", _mapping(raw, name="settlement rule")))
        for raw in cast("list[object]", item["rules"])
    )
    return SettlementPolicy(
        cash_buying_power=cast("Any", item["cash_buying_power"]),
        position_availability=cast("Any", item["position_availability"]),
        calendars=calendars,
        rules=rules,
    )


def _instrument_payload(value: ExecutionInstrument) -> dict[str, object]:
    return {
        "instrument_id": value.instrument_id,
        "symbol": value.symbol,
        "quote_currency": value.quote_currency,
        "tick_size": decimal_string(cast("Decimal", value.tick_size)),
        "lot_size": decimal_string(cast("Decimal", value.lot_size)),
    }


def _risk_payload(value: RiskFinancingRiskPolicy) -> dict[str, object]:
    return value.to_dict()


def _require_contract(schemas: TradingEngineContractSchemas) -> None:
    if schemas.version != INITIAL_STATE_CONTRACT_VERSION:
        raise ValueError("initial portfolio state requires Trading Engine contract v1")


def _mapping(value: object, *, name: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TradingEngineContractError(f"{name} must be an object")
    typed_value = cast("Mapping[object, object]", value)
    result: dict[str, object] = {}
    for key, item in typed_value.items():
        if not isinstance(key, str):
            raise TradingEngineContractError(f"{name} keys must be strings")
        result[key] = item
    return result


def _sequence(event: Mapping[str, object]) -> int:
    value = event.get("engine_sequence")
    if not isinstance(value, str) or not value.isdigit():
        raise TradingEngineContractError("initial-state journal sequence is invalid")
    return int(value)


def _unique(values: Iterable[str], *, name: str) -> None:
    selected = tuple(values)
    if len(selected) != len(set(selected)):
        raise ValueError(f"{name} must be unique")


def _bps_ceil(value: Decimal, bps: int) -> Decimal:
    return (value * Decimal(bps) / Decimal(10_000)).quantize(_MICRO, rounding=ROUND_CEILING)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
