"""Tests for explicit Trading Engine opening portfolio state."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    ExecutionInstrument,
    FinancingPolicy,
    InitialCashBalance,
    InitialFxRate,
    InitialMark,
    InitialPortfolioState,
    InitialPosition,
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
    bind_initial_state_manifest,
    build_initial_state_scenario,
    initial_state_scenario_to_json,
    initial_state_scenario_to_jsonl,
    reconcile_initial_state_replay,
    write_initial_state_scenario,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class FakeSchemas:
    """Record validations and return configured replay evidence."""

    version = "1"

    def __init__(self) -> None:
        self.scenarios: list[object] = []
        self.stream_records: list[object] = []
        self.replay: SchemaReplayResult | None = None

    def validate_scenario(self, value: object) -> None:
        self.scenarios.append(value)

    def validate_stream_record(self, value: object, *, line_number: int) -> None:
        assert line_number == len(self.stream_records) + 1
        self.stream_records.append(value)

    def read_replay(self, scenario_path: Path, journal_path: Path) -> SchemaReplayResult:
        assert scenario_path.is_file()
        assert journal_path.is_file()
        assert self.replay is not None
        return self.replay


def schemas(value: FakeSchemas) -> TradingEngineContractSchemas:
    """Treat the intentionally small contract double as the public validator."""
    return cast("TradingEngineContractSchemas", cast("object", value))


def portfolio() -> InitialPortfolioState:
    """Return a deterministic opening state with complete attribution."""
    return InitialPortfolioState(
        cash=(InitialCashBalance("USD", "10000"),),
        positions=(
            InitialPosition(
                "asset-a",
                "1",
                "90",
                realized_pnl="5",
                dividend_pnl="1",
                execution_fees="0.5",
                borrow_fees="0.25",
            ),
        ),
        marks=(InitialMark("asset-a", "100"),),
        fx_rates=(InitialFxRate("USD", "1"),),
    )


def financing() -> FinancingPolicy:
    """Return a strict deterministic financing policy."""
    return FinancingPolicy("actual_365", "simple", "reject", "reject", "clip_fill", "close_out")


def settlement() -> SettlementPolicy:
    """Return a settlement policy covering the test instrument."""
    return SettlementPolicy(
        "total_cash",
        "total_positions",
        (SettlementCalendar("weekday-v1", ("2026-01-02",)),),
        (SettlementRule("asset-a", "weekday-v1", 0),),
    )


def scenario(fake: FakeSchemas | None = None, *, groups: tuple[RiskGroup, ...] = ()):
    """Build a minimal semantically valid v1 scenario."""
    selected = fake or FakeSchemas()
    return build_initial_state_scenario(
        schemas=schemas(selected),
        run_id="run-a",
        base_currency="USD",
        initial_portfolio=portfolio(),
        instruments=(ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size="0.001"),),
        venue_calendars=(),
        risk=RiskFinancingRiskPolicy(
            max_gross_exposure=1_000_000,
            max_leverage=2,
            instrument_policies=(
                InstrumentRiskPolicy(
                    "asset-a",
                    max_order_quantity=1000,
                    max_long_position=1000,
                    max_short_position=1000,
                    max_notional_exposure=1_000_000,
                    initial_margin_bps=5000,
                    maintenance_margin_bps=2500,
                    shorting_allowed=True,
                ),
            ),
            groups=groups,
        ),
        execution={"model": "completed_bar_v1", "configuration": {"version": "1"}},
        financing=financing(),
        settlement=settlement(),
        max_internal_events=1000,
    )


def expected_valuation() -> dict[str, object]:
    """Return the Trading Engine v1 opening valuation for ``portfolio``."""
    return {
        "base_currency": "USD",
        "cash": "10000",
        "settled_cash": "10000",
        "unsettled_cash": "0",
        "net_market_value": "100",
        "long_market_value": "100",
        "short_market_value": "0",
        "gross_exposure": "100",
        "cost_basis": "90",
        "realized_pnl": "5",
        "unrealized_pnl": "10",
        "equity": "10100",
        "dividend_pnl": "1",
        "execution_fees": "0.5",
        "borrow_fees": "0.25",
        "total_fees": "0.75",
        "cash_interest": "0",
        "execution_fee_components": [],
        "group_exposures": [],
        "cash_balances": [
            {
                "currency": "USD",
                "amount": "10000",
                "settled_amount": "10000",
                "unsettled_amount": "0",
                "fx_rate": "1",
                "base_value": "10000",
                "base_settled_value": "10000",
                "base_unsettled_value": "0",
                "interest": "0",
                "base_interest": "0",
            }
        ],
        "positions": [
            {
                "instrument_id": "asset-a",
                "quote_currency": "USD",
                "quantity": "1",
                "settled_quantity": "1",
                "unsettled_quantity": "0",
                "mark": "100",
                "fx_rate": "1",
                "market_value": "100",
                "base_market_value": "100",
                "cost_basis": "90",
                "base_cost_basis": "90",
                "realized_pnl": "5",
                "base_realized_pnl": "5",
                "unrealized_pnl": "10",
                "base_unrealized_pnl": "10",
                "dividend_pnl": "1",
                "base_dividend_pnl": "1",
                "execution_fees": "0.5",
                "base_execution_fees": "0.5",
                "execution_fee_components": [],
                "borrow_fees": "0.25",
                "base_borrow_fees": "0.25",
                "total_fees": "0.75",
                "base_total_fees": "0.75",
            }
        ],
        "margin": {
            "initial_requirement": "50",
            "maintenance_requirement": "25",
            "initial_excess": "10050",
            "maintenance_excess": "10075",
            "margin_call": False,
        },
    }


def test_initial_state_is_canonical_immutable_and_complete() -> None:
    state = InitialPortfolioState(
        cash=(InitialCashBalance("USD", 1), InitialCashBalance("EUR", 2)),
        positions=(InitialPosition("b", -1, -2), InitialPosition("a", 1, 2)),
        marks=(InitialMark("b", 3), InitialMark("a", 2)),
        fx_rates=(InitialFxRate("USD", 1), InitialFxRate("EUR", "1.1")),
    )

    assert [item.instrument_id for item in state.positions] == ["a", "b"]
    assert [item.currency for item in state.cash] == ["EUR", "USD"]
    assert len(state.sha256) == 64
    with pytest.raises(FrozenInstanceError):
        state.cash = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: InitialPosition("a", 0, 1), "nonzero"),
        (lambda: InitialPosition("a", -1, 1), "same sign"),
        (lambda: InitialPosition("a", 1, 1, execution_fees=-1), "nonnegative"),
        (
            lambda: InitialPortfolioState(
                (InitialCashBalance("USD", 1),),
                (InitialPosition("a", 1, 1),),
                (),
                (InitialFxRate("USD", 1),),
            ),
            "marks must cover",
        ),
    ],
)
def test_initial_state_rejects_invalid_accounting(factory: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        factory()


def test_builder_validates_batch_and_stream_and_serializes(tmp_path: Path) -> None:
    fake = FakeSchemas()
    built = scenario(fake)

    assert built.contract_version == "1"
    assert len(fake.scenarios) == 1
    assert [cast("dict[str, object]", item)["record_type"] for item in fake.stream_records] == [
        "scenario_header",
        "scenario_end",
    ]
    assert (
        json.loads(initial_state_scenario_to_json(built))["initial_portfolio"]
        == portfolio().to_dict()
    )
    assert [
        json.loads(line)["scenario_sequence"]
        for line in initial_state_scenario_to_jsonl(built).splitlines()
    ] == ["1", "2"]
    output = write_initial_state_scenario(built, tmp_path / "scenario.json")
    assert output.read_text(encoding="utf-8") == initial_state_scenario_to_json(built)
    with pytest.raises(FileExistsError):
        write_initial_state_scenario(built, output)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"quantity": "1.5"}, "lot"),
        ({"instrument_id": "missing"}, "unknown instrument"),
        ({"quantity": "1001", "cost_basis": "1001"}, "maximum long"),
    ],
)
def test_builder_rejects_initial_positions_outside_policy(
    change: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {"instrument_id": "asset-a", "quantity": "1", "cost_basis": "90"}
    values.update(change)
    state = InitialPortfolioState(
        (InitialCashBalance("USD", "10000"),),
        (InitialPosition(**cast("dict[str, Any]", values)),),
        (InitialMark(cast("str", values["instrument_id"]), "100"),),
        (InitialFxRate("USD", "1"),),
    )
    with pytest.raises(ValueError, match=message):
        build_initial_state_scenario(
            schemas=schemas(FakeSchemas()),
            run_id="run-a",
            base_currency="USD",
            initial_portfolio=state,
            instruments=(ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size="1"),),
            venue_calendars=(),
            risk=scenario().risk,
            execution={"model": "completed_bar_v1"},
            financing=financing(),
            settlement=settlement(),
            max_internal_events=1000,
        )


def replay(events: tuple[Mapping[str, object], ...]) -> SchemaReplayResult:
    """Build schema replay evidence for reconciliation tests."""
    return SchemaReplayResult(
        "1", "run-a", "completed_bar_v1", "a" * 64, len(events), pd.DataFrame(), events
    )


def journal_events(
    built: Any, valuation: Mapping[str, object] | None = None
) -> tuple[Mapping[str, object], ...]:
    """Return the minimum ordered v1 opening audit sequence."""
    selected_valuation = expected_valuation() if valuation is None else valuation
    return (
        {"engine_sequence": "1", "event_type": "run_started", "payload": {}},
        {
            "engine_sequence": "2",
            "event_type": "initial_state",
            "payload": {
                "portfolio": built.initial_portfolio.to_dict(),
                "valuation": selected_valuation,
            },
        },
        {"engine_sequence": "3", "event_type": "valuation", "payload": selected_valuation},
        {"engine_sequence": "4", "event_type": "run_completed", "payload": {}},
    )


def test_reconciliation_derives_canonical_risk_group_exposures(tmp_path: Path) -> None:
    """Accept exact group rows and reject missing, extra, duplicate, or altered rows."""
    group = RiskGroup(
        "research-universe",
        "custom",
        ("asset-a",),
        RiskGroupLimits(max_gross_exposure=1_000_000),
    )
    built = scenario(groups=(group,))
    valuation = expected_valuation()
    valuation["group_exposures"] = [
        {
            "group_id": "research-universe",
            "gross_exposure": "100",
            "net_exposure": "100",
            "long_exposure": "100",
            "short_exposure": "0",
            "concentration": "0.0099",
        }
    ]
    scenario_path = write_initial_state_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    fake = FakeSchemas()
    fake.replay = replay(journal_events(built, valuation))
    reconciled = reconcile_initial_state_replay(schemas(fake), scenario_path, journal_path)
    reconciled_rows = cast(
        "tuple[Mapping[str, object], ...]", reconciled.valuation["group_exposures"]
    )
    assert reconciled_rows[0]["group_id"] == "research-universe"

    rows = cast("list[dict[str, object]]", valuation["group_exposures"])
    invalid_rows: tuple[list[dict[str, object]], ...] = (
        [],
        rows * 2,
        [*rows, {**rows[0], "group_id": "extra"}],
        [{**rows[0], "gross_exposure": "0"}],
    )
    for group_rows in invalid_rows:
        invalid = {**valuation, "group_exposures": group_rows}
        fake.replay = replay(journal_events(built, invalid))
        with pytest.raises(TradingEngineContractError, match="initial valuation"):
            reconcile_initial_state_replay(schemas(fake), scenario_path, journal_path)


def test_reconcile_verifies_opening_state_and_manifest(tmp_path: Path) -> None:
    built = scenario()
    scenario_path = write_initial_state_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    fake = FakeSchemas()
    fake.replay = replay(journal_events(built))

    result = reconcile_initial_state_replay(schemas(fake), scenario_path, journal_path)
    assert result.initial_state_sequence == 2
    assert result.first_valuation_sequence == 3
    assert result.valuation["equity"] == "10100"
    manifest = bind_initial_state_manifest({"contract": {"version": "1"}}, built)
    assert (
        cast("Mapping[str, object]", manifest["initial_state"])["portfolio_sha256"]
        == portfolio().sha256
    )
    with pytest.raises(TypeError):
        manifest["changed"] = True  # type: ignore[index]


@pytest.mark.parametrize("mutation", ["portfolio", "initial_valuation", "first_valuation"])
def test_reconcile_rejects_tampered_opening_evidence(tmp_path: Path, mutation: str) -> None:
    built = scenario()
    scenario_path = write_initial_state_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    events = [dict(item) for item in journal_events(built)]
    if mutation == "portfolio":
        cast("dict[str, Any]", events[1]["payload"])["portfolio"] = {}
    elif mutation == "initial_valuation":
        cast("dict[str, Any]", events[1]["payload"])["valuation"] = {}
    else:
        events[2]["payload"] = {}
    fake = FakeSchemas()
    fake.replay = replay(tuple(events))

    with pytest.raises(TradingEngineContractError, match="differs"):
        reconcile_initial_state_replay(schemas(fake), scenario_path, journal_path)


@pytest.mark.parametrize(
    ("event_mutation", "message"),
    [
        ("truncated", "must record initial_state"),
        ("initial_type", "must record initial_state"),
        ("valuation_type", "must value the initial state"),
    ],
)
def test_reconcile_rejects_missing_or_misordered_opening_events(
    tmp_path: Path, event_mutation: str, message: str
) -> None:
    built = scenario()
    scenario_path = write_initial_state_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    events = [dict(item) for item in journal_events(built)]
    if event_mutation == "truncated":
        events = events[:1]
    elif event_mutation == "initial_type":
        events[1]["event_type"] = "valuation"
    else:
        events[2]["event_type"] = "market_slice"
    fake = FakeSchemas()
    fake.replay = replay(tuple(events))

    with pytest.raises(TradingEngineContractError, match=message):
        reconcile_initial_state_replay(schemas(fake), scenario_path, journal_path)


def test_contract_version_must_be_v1() -> None:
    fake = FakeSchemas()
    fake.version = "5"
    with pytest.raises(ValueError, match="contract v1"):
        scenario(fake)
