"""Tests for Trading Engine v11 risk, fee, financing, and settlement contracts."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import date
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    EngineCapabilities,
    FeeComponent,
    FeeExecutionPolicy,
    FinancingPolicy,
    InstrumentFeeSchedule,
    InstrumentRiskPolicy,
    RiskFinancingRiskPolicy,
    RiskGroup,
    RiskGroupLimits,
    SchemaReplayResult,
    SettlementCalendar,
    SettlementPolicy,
    SettlementRule,
    TradingEngineContractError,
    TradingEngineContractSchemas,
    bind_risk_financing_manifest,
    build_risk_financing_scenario,
    reconcile_risk_financing_replay,
    require_risk_financing_capabilities,
    risk_financing_scenario_to_json,
    risk_financing_scenario_to_jsonl,
    write_risk_financing_scenario,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class FakeSchemas:
    """Minimal schema double that records both serialization forms."""

    version = "11"

    def __init__(self) -> None:
        self.scenarios: list[object] = []
        self.records: list[object] = []
        self.replay: SchemaReplayResult | None = None

    def validate_scenario(self, value: object) -> None:
        self.scenarios.append(value)

    def validate_stream_record(self, value: object, *, line_number: int) -> None:
        assert line_number == len(self.records) + 1
        self.records.append(value)

    def read_replay(self, scenario_path: Path, journal_path: Path) -> SchemaReplayResult:
        assert scenario_path.is_file() and journal_path.is_file()
        assert self.replay is not None
        return self.replay


def schemas(value: FakeSchemas) -> TradingEngineContractSchemas:
    """Cast the deliberately small schema double to the public boundary."""
    return cast("TradingEngineContractSchemas", cast("object", value))


def risk() -> RiskFinancingRiskPolicy:
    """Return complete aggregate, instrument, and overlapping group risk."""
    instrument = InstrumentRiskPolicy("asset-a", 100, 100, 50, 1_000_000, 5000, 2500, True)
    group = RiskGroup(
        "technology",
        "sector",
        ("asset-a",),
        RiskGroupLimits(max_gross_exposure=500_000, max_concentration="0.8"),
    )
    return RiskFinancingRiskPolicy(1_000_000, 2, 100, (instrument,), (group,))


def execution() -> FeeExecutionPolicy:
    """Return one complete per-instrument fee schedule."""
    return FeeExecutionPolicy(
        5000,
        (
            InstrumentFeeSchedule(
                "asset-a-fees-v1",
                "asset-a",
                "USD",
                (
                    FeeComponent("broker", "USD", "fixed", "0.25", "up"),
                    FeeComponent("exchange", "USD", "notional_bps", 10, "nearest", "taker"),
                ),
                minimum="0.25",
                maximum="1",
            ),
        ),
    )


def financing() -> FinancingPolicy:
    """Return explicit financing behavior."""
    return FinancingPolicy("actual_365", "simple", "reject", "reject", "clip_fill", "close_out")


def settlement() -> SettlementPolicy:
    """Return a versioned T+1 settlement policy."""
    return SettlementPolicy(
        "total_cash",
        "total_positions",
        (SettlementCalendar("us-business", (date(2026, 1, 2), "2026-01-05")),),
        (SettlementRule("asset-a", "us-business", 1),),
    )


def base_scenario() -> dict[str, Any]:
    """Return the non-policy portion of a complete scenario."""
    return {
        "contract_version": "6",
        "metadata": {"source": "unit-test"},
        "run_id": "run-a",
        "base_currency": "USD",
        "initial_portfolio": {
            "cash": [{"currency": "USD", "amount": "100"}],
            "positions": [],
            "marks": [],
            "fx_rates": [{"currency": "USD", "rate": "1"}],
        },
        "instruments": [
            {
                "instrument_id": "asset-a",
                "symbol": "AAA",
                "quote_currency": "USD",
                "tick_size": "0.01",
                "lot_size": "1",
            }
        ],
        "venue_calendars": [],
        "risk": {},
        "execution": {},
        "max_internal_events": 1000,
        "schedule": [],
        "slices": [
            {
                "slice_sequence": "1",
                "start_at": "2026-01-02T14:30:00Z",
                "end_at": "2026-01-02T21:00:00Z",
                "available_at": "2026-01-02T21:00:01Z",
                "received_at": "2026-01-02T21:00:02Z",
                "bars": [],
                "fx_rates": [{"currency": "USD", "rate": "1"}],
                "corporate_actions": [],
                "borrow_observations": [
                    {
                        "instrument_id": "asset-a",
                        "effective_at": "2026-01-02T14:30:00Z",
                        "available_quantity": "50",
                        "annual_rate_bps": 100,
                        "recalled": False,
                    }
                ],
                "cash_rate_observations": [
                    {
                        "currency": "USD",
                        "effective_at": "2026-01-02T14:30:00Z",
                        "credit_rate_bps": 100,
                        "debit_rate_bps": 200,
                    }
                ],
                "settlement_failures": [],
            }
        ],
    }


def scenario(fake: FakeSchemas | None = None):
    """Build one validated v11 scenario."""
    return build_risk_financing_scenario(
        schemas=schemas(fake or FakeSchemas()),
        base_scenario=base_scenario(),
        risk=risk(),
        execution=execution(),
        financing=financing(),
        settlement=settlement(),
    )


def valuation() -> dict[str, object]:
    """Return a fully reconciled zero-position v11 valuation."""
    return {
        "base_currency": "USD",
        "cash": "101",
        "settled_cash": "100",
        "unsettled_cash": "1",
        "net_market_value": "0",
        "long_market_value": "0",
        "short_market_value": "0",
        "gross_exposure": "0",
        "cost_basis": "0",
        "realized_pnl": "1",
        "unrealized_pnl": "0",
        "equity": "101",
        "dividend_pnl": "0",
        "execution_fees": "0.25",
        "borrow_fees": "0.1",
        "cash_interest": "1",
        "total_fees": "0.35",
        "cash_balances": [
            {
                "currency": "USD",
                "amount": "101",
                "fx_rate": "1",
                "base_value": "101",
                "interest": "1",
                "base_interest": "1",
                "settled_amount": "100",
                "unsettled_amount": "1",
                "base_settled_value": "100",
                "base_unsettled_value": "1",
            }
        ],
        "positions": [],
        "margin": {},
        "group_exposures": [],
        "execution_fee_components": [],
    }


def event(event_type: str, payload: Mapping[str, object], sequence: int) -> Mapping[str, object]:
    """Return one compact schema-replay event."""
    return {"event_type": event_type, "payload": payload, "engine_sequence": str(sequence)}


def replay_events() -> tuple[Mapping[str, object], ...]:
    """Return evidence exercising fees, accruals, settlement, and valuation."""
    fill = {
        "fill_id": "fill-a",
        "order_id": "order-a",
        "instrument_id": "asset-a",
        "quote_currency": "USD",
        "side": "buy",
        "quantity": "1",
        "price": "10",
        "notional": "10",
        "fee": "0.25",
        "fee_components": [
            {"name": "broker", "currency": "USD", "amount": "0.25", "quote_amount": "0.25"}
        ],
    }
    instruction = {
        "instruction_id": "fill-a-settlement",
        "fill_id": "fill-a",
        "instrument_id": "asset-a",
        "currency": "USD",
        "cash_movement": "-10.25",
        "position_movement": "1",
        "trade_date": "2026-01-02",
        "due_date": "2026-01-05",
        "status": "pending",
        "settled_at": None,
        "failed_at": None,
        "failure_reason": None,
    }
    interest = {
        "observation": {"currency": "USD", "credit_rate_bps": 100, "debit_rate_bps": 200},
        "opening_balance": "100",
        "applied_rate_bps": 100,
        "amount": "1",
        "closing_balance": "101",
    }
    terminal = {"valuation": valuation()}
    return (
        event("run_started", {}, 1),
        event("order_rejected", {"reason": "instrument_limit"}, 2),
        event("fill_clipped", {"reason": "group_limit"}, 3),
        event("fill_applied", fill, 4),
        event("cash_interest_applied", interest, 5),
        event(
            "borrow_charge_applied",
            {
                "observation": {"instrument_id": "asset-a"},
                "quote_currency": "USD",
                "short_quantity": "1",
                "reference_price": "10",
                "amount": "0.1",
            },
            6,
        ),
        event(
            "borrow_recall_received",
            {"observation": {"instrument_id": "asset-a"}, "short_quantity": "1"},
            7,
        ),
        event("settlement_instruction_created", instruction, 8),
        event("valuation", valuation(), 9),
        event("run_completed", terminal, 10),
    )


def schema_replay(events: tuple[Mapping[str, object], ...]) -> SchemaReplayResult:
    """Wrap compact events in generic schema replay evidence."""
    return SchemaReplayResult(
        "11", "run-a", "completed_bar_v1", "a" * 64, len(events), pd.DataFrame(), events
    )


def test_policy_models_are_canonical_immutable_and_exact() -> None:
    selected = risk()
    assert selected.instrument_policies[0].to_dict()["max_order_quantity"] == "100"
    assert selected.groups[0].to_dict()["group_version"] == "1"
    assert execution().to_dict()["configuration"]["version"] == "2"  # type: ignore[index]
    assert financing().to_dict()["recall_policy"] == "close_out"
    assert settlement().calendars[0].business_dates == (date(2026, 1, 2), date(2026, 1, 5))
    with pytest.raises(FrozenInstanceError):
        selected.groups = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: InstrumentRiskPolicy("a", 1, 1, 1, 1, 0, 1, True), "initial_margin"),
        (lambda: InstrumentRiskPolicy("a", 1, 1, 1, 1, 100, 101, True), "maintenance"),
        (lambda: RiskGroupLimits(), "at least one"),
        (lambda: RiskGroupLimits(max_concentration="1.1"), "exceed one"),
        (lambda: RiskGroup("g", "sector", (), RiskGroupLimits(max_gross_exposure=1)), "empty"),
        (lambda: FeeComponent("x", "USD", "notional_bps", "1", "up"), "integer"),
        (lambda: FeeComponent("x", "USD", "notional_bps", 10001, "up"), "between"),
        (
            lambda: InstrumentFeeSchedule(
                "s", "a", "USD", (FeeComponent("x", "USD", "fixed", 1, "up"),), 2, 1
            ),
            "minimum",
        ),
        (lambda: FeeExecutionPolicy(1, ()), "must not be empty"),
        (lambda: SettlementCalendar("c", ()), "must not be empty"),
        (lambda: SettlementRule("a", "c", 31), "between zero"),
        (
            lambda: SettlementPolicy(
                "total_cash",
                "total_positions",
                (SettlementCalendar("c", ("2026-01-01",)),),
                (SettlementRule("a", "missing", 1),),
            ),
            "unknown calendar",
        ),
    ],
)
def test_policy_models_reject_invalid_contract_values(factory: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_builder_validates_alignment_batch_stream_and_manifest(tmp_path: Path) -> None:
    fake = FakeSchemas()
    built = scenario(fake)

    assert built.contract_version == "11"
    assert built.run_id == "run-a"
    assert built.sha256 == scenario().sha256
    assert len(fake.scenarios) == 1
    assert [cast("dict[str, object]", item)["record_type"] for item in fake.records] == [
        "scenario_header",
        "market_slice",
        "scenario_end",
    ]
    assert json.loads(risk_financing_scenario_to_json(built))["risk"] == risk().to_dict()
    assert len(risk_financing_scenario_to_jsonl(built).splitlines()) == 3
    path = write_risk_financing_scenario(built, tmp_path / "scenario.json")
    assert path.is_file()
    with pytest.raises(FileExistsError):
        write_risk_financing_scenario(built, path)
    manifest = bind_risk_financing_manifest({"contract": {"version": "11"}}, built)
    assert cast("Mapping[str, object]", manifest["risk_financing"])["contract_version"] == "11"
    with pytest.raises(TypeError):
        manifest["changed"] = True  # type: ignore[index]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("catalog", "cover every"),
        ("borrow_instrument", "unknown instrument"),
        ("cash_currency", "unknown currency"),
        ("borrow_time", "effective by slice start"),
    ],
)
def test_builder_rejects_misaligned_catalog_and_observations(mutation: str, message: str) -> None:
    base = base_scenario()
    instruments = cast("list[dict[str, Any]]", base["instruments"])
    slices = cast("list[dict[str, Any]]", base["slices"])
    if mutation == "catalog":
        instruments[0]["instrument_id"] = "other"
    elif mutation == "borrow_instrument":
        cast("list[dict[str, Any]]", slices[0]["borrow_observations"])[0]["instrument_id"] = "other"
    elif mutation == "cash_currency":
        cast("list[dict[str, Any]]", slices[0]["cash_rate_observations"])[0]["currency"] = "EUR"
    else:
        cast("list[dict[str, Any]]", slices[0]["borrow_observations"])[0]["effective_at"] = (
            "2026-01-03T00:00:00Z"
        )
    with pytest.raises(ValueError, match=message):
        build_risk_financing_scenario(
            schemas=schemas(FakeSchemas()),
            base_scenario=base,
            risk=risk(),
            execution=execution(),
            financing=financing(),
            settlement=settlement(),
        )


def test_capability_negotiation_accepts_only_complete_v11_support() -> None:
    capabilities = EngineCapabilities(
        "1.0.0", ("11",), ("11",), ("json", "jsonl"), ("jsonl",), ("completed_bar_v1",), ("8",)
    )
    require_risk_financing_capabilities(capabilities, schemas(FakeSchemas()))
    missing = EngineCapabilities(
        "1.0.0", ("10",), ("10",), ("json",), ("jsonl",), ("completed_bar_v1",), ("8",)
    )
    with pytest.raises(ValueError, match="scenario v11, journal v11"):
        require_risk_financing_capabilities(missing, schemas(FakeSchemas()))


def test_replay_reconciles_all_selected_evidence(tmp_path: Path) -> None:
    built = scenario()
    scenario_path = write_risk_financing_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    fake = FakeSchemas()
    fake.replay = schema_replay(replay_events())

    result = reconcile_risk_financing_replay(schemas(fake), scenario_path, journal_path)
    assert result.to_dict() == {
        "contract_version": "11",
        "run_id": "run-a",
        "scenario_sha256": "a" * 64,
        "rejections": 1,
        "clippings": 1,
        "fills": 1,
        "borrow_charges": 1,
        "borrow_recalls": 1,
        "cash_interest": 1,
        "settlement_instructions": 1,
        "settlement_completions": 0,
        "settlement_failures": 0,
        "valuations": 1,
        "status": "verified",
    }


@pytest.mark.parametrize(
    ("event_type", "status", "time_field", "reason"),
    [
        ("settlement_completed", "settled", "settled_at", None),
        ("settlement_failed", "failed", "failed_at", "counterparty default"),
    ],
)
def test_replay_reconciles_terminal_settlement_states(
    tmp_path: Path,
    event_type: str,
    status: str,
    time_field: str,
    reason: str | None,
) -> None:
    built = scenario()
    scenario_path = write_risk_financing_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    events = list(replay_events())
    created = cast("dict[str, Any]", events[7]["payload"])
    terminal = dict(created)
    terminal["status"] = status
    terminal[time_field] = "2026-01-05T14:30:00Z"
    terminal["failure_reason"] = reason
    events.insert(8, event(event_type, terminal, 9))
    fake = FakeSchemas()
    fake.replay = schema_replay(tuple(events))

    result = reconcile_risk_financing_replay(schemas(fake), scenario_path, journal_path)
    assert (
        len(
            getattr(
                result, "settlement_completions" if status == "settled" else "settlement_failures"
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("notional", "notional"),
        ("fee", "fee"),
        ("closing_balance", "opening and closing"),
        ("applied_rate", "applied rate"),
        ("borrow_quantity", "must be positive"),
        ("settlement_fill", "does not reconcile"),
        ("equity", "equity"),
    ],
)
def test_replay_rejects_inconsistent_evidence(tmp_path: Path, mutation: str, message: str) -> None:
    built = scenario()
    scenario_path = write_risk_financing_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    events = [dict(item) for item in replay_events()]
    payload_index = {
        "notional": 3,
        "fee": 3,
        "closing_balance": 4,
        "applied_rate": 4,
        "borrow_quantity": 5,
        "settlement_fill": 7,
        "equity": 8,
    }
    payload = cast("dict[str, Any]", events[payload_index[mutation]]["payload"])
    values: dict[str, tuple[str, object]] = {
        "notional": ("notional", "9"),
        "fee": ("fee", "1"),
        "closing_balance": ("closing_balance", "100"),
        "applied_rate": ("applied_rate_bps", 200),
        "borrow_quantity": ("short_quantity", "0"),
        "settlement_fill": ("fill_id", "missing"),
        "equity": ("equity", "0"),
    }
    key, value = values[mutation]
    payload[key] = value
    fake = FakeSchemas()
    fake.replay = schema_replay(tuple(events))
    with pytest.raises(TradingEngineContractError, match=message):
        reconcile_risk_financing_replay(schemas(fake), scenario_path, journal_path)


def test_contract_and_manifest_versions_must_match() -> None:
    fake = FakeSchemas()
    fake.version = "10"
    with pytest.raises(ValueError, match="contract v11"):
        build_risk_financing_scenario(
            schemas=schemas(fake),
            base_scenario=base_scenario(),
            risk=risk(),
            execution=execution(),
            financing=financing(),
            settlement=settlement(),
        )
    with pytest.raises(ValueError, match="contract version differs"):
        bind_risk_financing_manifest({"contract": {"version": "10"}}, scenario())
