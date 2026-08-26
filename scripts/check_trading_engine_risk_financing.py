"""Verify Persistra risk and financing support against pinned Trading Engine v1."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from persistra.integrations.trading_engine import (
    RISK_FINANCING_CONTRACT_VERSION,
    EngineCapabilities,
    FeeComponent,
    FeeExecutionPolicy,
    FinancingPolicy,
    InstrumentFeeSchedule,
    InstrumentRiskPolicy,
    RiskFinancingRiskPolicy,
    RiskGroup,
    RiskGroupLimits,
    SettlementCalendar,
    SettlementPolicy,
    SettlementRule,
    TradingEngineContractSchemas,
    build_risk_financing_scenario,
    reconcile_risk_financing_replay,
    require_risk_financing_capabilities,
)


def main() -> None:
    """Build and reconcile canonical v1 scenarios against advertised capabilities."""
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: check_trading_engine_risk_financing.py CONTRACT_DIRECTORY EXECUTABLE"
        )
    schemas = TradingEngineContractSchemas.load(sys.argv[1])
    fixture_directory = schemas.directory / "fixtures"
    demo_path = fixture_directory / "demo.scenario.json"
    raw = json.loads(demo_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit("canonical v1 scenario must be an object")
    document = cast("dict[str, Any]", raw)
    built = build_risk_financing_scenario(
        schemas=schemas,
        base_scenario=document,
        risk=_risk(document["risk"]),
        execution=_execution(document["execution"]),
        financing=_financing(document["financing"]),
        settlement=_settlement(document["settlement"]),
    )
    if built.contract_version != RISK_FINANCING_CONTRACT_VERSION:
        raise SystemExit("canonical scenario selected an unexpected contract version")
    capabilities = _capabilities(Path(sys.argv[2]))
    require_risk_financing_capabilities(capabilities, schemas)
    demo = reconcile_risk_financing_replay(
        schemas,
        demo_path,
        fixture_directory / "demo.journal.jsonl",
    )
    clipped = reconcile_risk_financing_replay(
        schemas,
        fixture_directory / "fill-clipped.scenario.json",
        fixture_directory / "fill-clipped.journal.jsonl",
    )
    if not demo.fills or not demo.cash_interest or not demo.settlement_instructions:
        raise SystemExit("canonical v1 fixture omits fee, financing, or settlement evidence")
    if not clipped.clippings:
        raise SystemExit("canonical v1 clipping fixture omits risk evidence")
    print(
        f"Trading Engine risk and financing v{schemas.version}: {schemas.sha256} "
        f"({len(demo.fills)} fills, {len(demo.cash_interest)} accruals, "
        f"{len(demo.settlement_instructions)} settlements, {len(clipped.clippings)} clips)"
    )


def _risk(value: object) -> RiskFinancingRiskPolicy:
    item = _object(value)
    policies = tuple(
        InstrumentRiskPolicy(**cast("dict[str, Any]", raw))
        for raw in cast("list[object]", item["instrument_policies"])
    )
    groups: list[RiskGroup] = []
    for raw in cast("list[object]", item["groups"]):
        group = _object(raw)
        groups.append(
            RiskGroup(
                cast("str", group["group_id"]),
                cast("Any", group["group_type"]),
                tuple(cast("list[str]", group["instrument_ids"])),
                RiskGroupLimits(**cast("dict[str, Any]", group["limits"])),
            )
        )
    return RiskFinancingRiskPolicy(
        cast("Any", item["max_gross_exposure"]),
        cast("Any", item["max_leverage"]),
        policies,
        tuple(groups),
    )


def _execution(value: object) -> FeeExecutionPolicy:
    configuration = _object(_object(value)["configuration"])
    schedules: list[InstrumentFeeSchedule] = []
    for raw in cast("list[object]", configuration["fee_schedules"]):
        item = _object(raw)
        schedules.append(
            InstrumentFeeSchedule(
                cast("str", item["schedule_id"]),
                cast("str", item["instrument_id"]),
                cast("str", item["settlement_currency"]),
                tuple(
                    FeeComponent(**cast("dict[str, Any]", component))
                    for component in cast("list[object]", item["components"])
                ),
                cast("Any", item["minimum"]),
                cast("Any", item["maximum"]),
            )
        )
    return FeeExecutionPolicy(cast("int", configuration["participation_bps"]), tuple(schedules))


def _financing(value: object) -> FinancingPolicy:
    return FinancingPolicy(**cast("dict[str, Any]", _object(value)))


def _settlement(value: object) -> SettlementPolicy:
    item = _object(value)
    calendars = tuple(
        SettlementCalendar(
            cast("str", calendar["calendar_id"]),
            tuple(cast("list[str]", calendar["business_dates"])),
        )
        for calendar in (_object(raw) for raw in cast("list[object]", item["calendars"]))
    )
    rules = tuple(
        SettlementRule(**cast("dict[str, Any]", raw)) for raw in cast("list[object]", item["rules"])
    )
    return SettlementPolicy(
        cast("Any", item["cash_buying_power"]),
        cast("Any", item["position_availability"]),
        calendars,
        rules,
    )


def _capabilities(executable: Path) -> EngineCapabilities:
    result = subprocess.run(
        (str(executable), "--capabilities"),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    item = _object(json.loads(result.stdout))
    return EngineCapabilities(
        cast("str", item["engine_version"]),
        tuple(cast("list[str]", item["scenario_contract_versions"])),
        tuple(cast("list[str]", item["journal_contract_versions"])),
        tuple(cast("list[str]", item["scenario_formats"])),
        tuple(cast("list[str]", item["journal_formats"])),
        tuple(cast("list[str]", item["execution_models"])),
        tuple(cast("list[str]", item["strategy_protocol_versions"])),
    )


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("canonical Trading Engine fixture field must be an object")
    return cast("dict[str, object]", value)


if __name__ == "__main__":
    main()
