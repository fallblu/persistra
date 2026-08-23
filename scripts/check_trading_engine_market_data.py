"""Verify Persistra market-data replay against pinned Trading Engine v15."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from persistra.integrations.trading_engine import (
    MARKET_DATA_CONTRACT_VERSION,
    ExecutableQuote,
    ExecutableTrade,
    FeeComponent,
    InstrumentFeeSchedule,
    MarketDataExecutionPolicy,
    ObservationProvenance,
    OrderBookDelete,
    OrderBookLevel,
    OrderBookSet,
    OrderBookSnapshot,
    OrderBookTrade,
    ReplayEventClock,
    ReplaySliceMarketData,
    TradingEngineContractSchemas,
    build_market_data_replay_scenario,
    reconcile_market_data_replay,
    require_market_data_capabilities,
)


def main() -> None:
    """Build and reconcile both canonical v15 market-data models."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_trading_engine_market_data.py CONTRACT_DIRECTORY EXECUTABLE")
    schemas = TradingEngineContractSchemas.load(sys.argv[1])
    capabilities = _capabilities(Path(sys.argv[2]))
    verified: list[str] = []
    for name in ("quote-trade", "order-book"):
        scenario_path = schemas.directory / "fixtures" / f"{name}.scenario.json"
        journal_path = schemas.directory / "fixtures" / f"{name}.journal.jsonl"
        document = _object(json.loads(scenario_path.read_text(encoding="utf-8")))
        execution = _execution(document["execution"])
        require_market_data_capabilities(capabilities, schemas, execution)
        built = build_market_data_replay_scenario(
            schemas=schemas,
            base_scenario=document,
            execution=execution,
            slices=_slices(document),
        )
        replay = reconcile_market_data_replay(schemas, scenario_path, journal_path)
        if built.contract_version != MARKET_DATA_CONTRACT_VERSION or not replay.fills:
            raise SystemExit(f"canonical {name} replay omitted required evidence")
        verified.append(f"{replay.model}:{len(replay.fills)} fills")
    print(
        f"Trading Engine market data v{schemas.version}: {schemas.sha256} ({', '.join(verified)})"
    )


def _execution(value: object) -> MarketDataExecutionPolicy:
    item = _object(value)
    configuration = _object(item["configuration"])
    schedules: list[InstrumentFeeSchedule] = []
    for raw in cast("list[object]", configuration["fee_schedules"]):
        fee = _object(raw)
        schedules.append(
            InstrumentFeeSchedule(
                cast("str", fee["schedule_id"]),
                cast("str", fee["instrument_id"]),
                cast("str", fee["settlement_currency"]),
                tuple(
                    FeeComponent(**cast("dict[str, Any]", component))
                    for component in cast("list[object]", fee["components"])
                ),
                cast("Any", fee.get("minimum")),
                cast("Any", fee.get("maximum")),
            )
        )
    model = cast("str", item["model"])
    return MarketDataExecutionPolicy(
        cast("Any", model),
        cast("int", configuration["participation_bps"]),
        tuple(schedules),
        cast("int | None", configuration.get("max_depth_levels")),
    )


def _slices(document: dict[str, object]) -> tuple[ReplaySliceMarketData, ...]:
    selected: list[ReplaySliceMarketData] = []
    for raw_slice in cast("list[object]", document["slices"]):
        item = _object(raw_slice)
        selected.append(
            ReplaySliceMarketData(
                int(cast("str", item["slice_sequence"])),
                tuple(_market_event(raw) for raw in cast("list[object]", item["market_events"])),
                tuple(_book_event(raw) for raw in cast("list[object]", item["order_book_events"])),
            )
        )
    return tuple(selected)


def _clock(item: dict[str, object]) -> ReplayEventClock:
    return ReplayEventClock(
        cast("str", item["event_at"]),
        cast("str", item["available_at"]),
        cast("str", item["received_at"]),
        int(cast("str", item["ingest_sequence"])),
    )


def _provenance(item: dict[str, object]) -> ObservationProvenance:
    return ObservationProvenance(
        "trading-engine-fixture",
        "canonical-v15",
        int(cast("str", item["ingest_sequence"])),
        cast("str", item["received_at"]),
    )


def _market_event(value: object) -> ExecutableQuote | ExecutableTrade:
    item = _object(value)
    common = (cast("str", item["instrument_id"]), _clock(item), _provenance(item))
    if item["type"] == "quote":
        return ExecutableQuote(
            *common,
            cast("Any", item["bid_price"]),
            cast("Any", item["bid_quantity"]),
            cast("Any", item["ask_price"]),
            cast("Any", item["ask_quantity"]),
        )
    return ExecutableTrade(
        *common,
        cast("Any", item["price"]),
        cast("Any", item["quantity"]),
        cast("Any", item["aggressor_side"]),
    )


def _book_event(
    value: object,
) -> OrderBookSnapshot | OrderBookSet | OrderBookDelete | OrderBookTrade:
    item = _object(value)
    common = (
        cast("str", item["instrument_id"]),
        _clock(item),
        _provenance(item),
        int(cast("str", item["book_sequence"])),
    )
    kind = item["type"]
    if kind == "snapshot":
        return OrderBookSnapshot(
            *common,
            tuple(
                OrderBookLevel(**cast("dict[str, Any]", raw))
                for raw in cast("list[object]", item["bids"])
            ),
            tuple(
                OrderBookLevel(**cast("dict[str, Any]", raw))
                for raw in cast("list[object]", item["asks"])
            ),
        )
    if kind == "set":
        return OrderBookSet(
            *common,
            cast("Any", item["side"]),
            cast("Any", item["price"]),
            cast("Any", item["quantity"]),
        )
    if kind == "delete":
        return OrderBookDelete(*common, cast("Any", item["side"]), cast("Any", item["price"]))
    return OrderBookTrade(
        *common,
        cast("Any", item["price"]),
        cast("Any", item["quantity"]),
        cast("Any", item["aggressor_side"]),
    )


def _capabilities(executable: Path) -> dict[str, object]:
    result = subprocess.run(
        (str(executable), "--capabilities"),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return _object(json.loads(result.stdout))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError("canonical Trading Engine fixture field must be an object")
    return cast("dict[str, object]", value)


if __name__ == "__main__":
    main()
