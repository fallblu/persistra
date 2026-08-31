"""Verify explicit opening-state support against pinned Trading Engine v1 fixtures."""

from __future__ import annotations

import json
import sys
from typing import Any, cast

from persistra.integrations.trading_engine import (
    INITIAL_STATE_CONTRACT_VERSION,
    ExecutionInstrument,
    FinancingPolicy,
    InitialCashBalance,
    InitialFxRate,
    InitialMark,
    InitialPortfolioState,
    InitialPosition,
    InitialStateScenario,
    InstrumentRiskPolicy,
    RiskFinancingRiskPolicy,
    RiskGroup,
    RiskGroupLimits,
    SettlementCalendar,
    SettlementPolicy,
    SettlementRule,
    TradingEngineContractSchemas,
    build_initial_state_scenario,
    reconcile_initial_state_replay,
)


def build_fixture_scenario(
    schemas: TradingEngineContractSchemas, *, with_risk_group: bool = False
) -> InitialStateScenario:
    """Rebuild the authoritative fixture through the public typed initial-state API."""
    fixture = schemas.directory / "fixtures" / "demo.scenario.json"
    document = cast("dict[str, Any]", json.loads(fixture.read_text(encoding="utf-8")))
    raw_portfolio = cast("dict[str, Any]", document["initial_portfolio"])
    raw_risk = cast("dict[str, Any]", document["risk"])
    raw_settlement = cast("dict[str, Any]", document["settlement"])
    groups = (
        (
            RiskGroup(
                "research-universe",
                "custom",
                ("demo-equity-acme",),
                RiskGroupLimits(max_gross_exposure="1000000"),
            ),
        )
        if with_risk_group
        else ()
    )
    return build_initial_state_scenario(
        schemas=schemas,
        run_id=cast("str", document["run_id"]),
        base_currency=cast("str", document["base_currency"]),
        initial_portfolio=InitialPortfolioState(
            tuple(InitialCashBalance(**item) for item in raw_portfolio["cash"]),
            tuple(InitialPosition(**item) for item in raw_portfolio["positions"]),
            tuple(InitialMark(**item) for item in raw_portfolio["marks"]),
            tuple(InitialFxRate(**item) for item in raw_portfolio["fx_rates"]),
        ),
        instruments=tuple(
            ExecutionInstrument(**item)
            for item in cast("list[dict[str, Any]]", document["instruments"])
        ),
        venue_calendars=cast("list[dict[str, Any]]", document["venue_calendars"]),
        risk=RiskFinancingRiskPolicy(
            max_gross_exposure=raw_risk["max_gross_exposure"],
            max_leverage=raw_risk["max_leverage"],
            instrument_policies=tuple(
                InstrumentRiskPolicy(**item) for item in raw_risk["instrument_policies"]
            ),
            groups=groups,
        ),
        execution=cast("dict[str, Any]", document["execution"]),
        financing=FinancingPolicy(**cast("dict[str, Any]", document["financing"])),
        settlement=SettlementPolicy(
            cash_buying_power=raw_settlement["cash_buying_power"],
            position_availability=raw_settlement["position_availability"],
            calendars=tuple(
                SettlementCalendar(**item) for item in raw_settlement["calendars"]
            ),
            rules=tuple(SettlementRule(**item) for item in raw_settlement["rules"]),
        ),
        max_internal_events=cast("int", document["max_internal_events"]),
        metadata=cast("dict[str, Any]", document["metadata"]),
        schedule=cast("list[dict[str, Any]]", document["schedule"]),
        slices=cast("list[dict[str, Any]]", document["slices"]),
    )


def main() -> None:
    """Validate and reconcile the canonical v1 opening portfolio replay."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_trading_engine_initial_state.py CONTRACT_DIRECTORY")
    schemas = TradingEngineContractSchemas.load(sys.argv[1])
    if schemas.version != INITIAL_STATE_CONTRACT_VERSION:
        raise SystemExit(
            "Persistra initial-state contract differs from pinned Trading Engine schemas: "
            f"expected {INITIAL_STATE_CONTRACT_VERSION}, found {schemas.version}"
        )
    built = build_fixture_scenario(schemas, with_risk_group=True)
    if not {"financing", "settlement"} <= set(built.to_dict()):
        raise SystemExit("typed initial-state builder omitted required policies")
    fixture_directory = schemas.directory / "fixtures"
    result = reconcile_initial_state_replay(
        schemas,
        fixture_directory / "demo.scenario.json",
        fixture_directory / "demo.journal.jsonl",
    )
    print(
        f"Trading Engine initial state v{schemas.version}: "
        f"{result.portfolio_sha256} ({result.replay.journal_records} journal records)"
    )


if __name__ == "__main__":
    main()
