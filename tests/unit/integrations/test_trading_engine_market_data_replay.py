"""Tests for Trading Engine v15 quote, trade, and order-book replay."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
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
    SchemaReplayResult,
    TradingEngineContractError,
    TradingEngineContractSchemas,
    bind_market_data_manifest,
    build_market_data_replay_scenario,
    market_data_model_capabilities,
    market_data_scenario_to_json,
    market_data_scenario_to_jsonl,
    reconcile_market_data_replay,
    require_market_data_capabilities,
    write_market_data_scenario,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime
    from pathlib import Path


class FakeSchemas:
    """Small schema double that records validation and supplies replay evidence."""

    version = "15"

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
    """Expose the deliberately narrow double through the public protocol."""
    return cast("TradingEngineContractSchemas", cast("object", value))


def clock(sequence: int = 1, minute: int = 31) -> ReplayEventClock:
    """Return a causal event clock inside the only test slice."""
    prefix = f"2026-01-02T14:{minute:02d}"
    return ReplayEventClock(f"{prefix}:00Z", f"{prefix}:01Z", f"{prefix}:02Z", sequence)


def provenance(sequence: int = 1, *, received_minute: int = 31) -> ObservationProvenance:
    """Return normalized provider metadata retained outside the engine wire contract."""
    return ObservationProvenance(
        "sip", "normalized-us-equities", sequence, f"2026-01-02T14:{received_minute:02d}:03Z"
    )


def quote(sequence: int = 1) -> ExecutableQuote:
    """Return one aligned executable quote."""
    return ExecutableQuote("asset-a", clock(sequence), provenance(sequence), 99, 20, 101, 20)


def trade(sequence: int = 2, *, minute: int = 32) -> ExecutableTrade:
    """Return one sell-aggressor print capable of filling a resting buy."""
    return ExecutableTrade(
        "asset-a",
        clock(sequence, minute),
        provenance(sequence, received_minute=minute),
        100,
        10,
        "sell",
    )


def snapshot(sequence: int = 1) -> OrderBookSnapshot:
    """Return one complete opening level-two snapshot."""
    return OrderBookSnapshot(
        "asset-a",
        clock(sequence),
        provenance(sequence),
        sequence,
        (OrderBookLevel(99, 10), OrderBookLevel(98, 5)),
        (OrderBookLevel(101, 10), OrderBookLevel(102, 5)),
    )


def schedule() -> InstrumentFeeSchedule:
    """Return a complete fee schedule accepted by v15."""
    return InstrumentFeeSchedule(
        "asset-a-fees", "asset-a", "USD", (FeeComponent("broker", "USD", "fixed", 1, "up"),)
    )


def policy(model: str = "quote_trade_v1") -> MarketDataExecutionPolicy:
    """Return a selected market-data execution model."""
    return MarketDataExecutionPolicy(
        cast("Any", model), 5000, (schedule(),), 10 if model == "order_book_v1" else None
    )


def base_scenario() -> dict[str, Any]:
    """Return the stable non-market-data portion of a v15 scenario."""
    return {
        "contract_version": "11",
        "metadata": {"source": "unit-test"},
        "run_id": "market-data-run",
        "base_currency": "USD",
        "initial_portfolio": {"cash": [], "positions": [], "marks": [], "fx_rates": []},
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
        "financing": {},
        "settlement": {},
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
                "fx_rates": [],
                "corporate_actions": [],
                "borrow_observations": [],
                "cash_rate_observations": [],
                "settlement_failures": [],
                "lifecycle_events": [],
            }
        ],
    }


def scenario(fake: FakeSchemas | None = None, *, model: str = "quote_trade_v1"):
    """Build one validated quote/trade or order-book scenario."""
    events = (
        ReplaySliceMarketData(1, (quote(), trade()))
        if model == "quote_trade_v1"
        else ReplaySliceMarketData(1, order_book_events=(snapshot(),))
    )
    return build_market_data_replay_scenario(
        schemas=schemas(fake or FakeSchemas()),
        base_scenario=base_scenario(),
        execution=policy(model),
        slices=(events,),
    )


def capabilities() -> dict[str, object]:
    """Return both complete advertised model contracts."""
    return {
        "scenario_formats": ["json", "jsonl"],
        "journal_formats": ["jsonl"],
        "execution_model_contracts": [
            {
                "name": "quote_trade_v1",
                "configuration_versions": ["1"],
                "scenario_contract_versions": ["15"],
                "required_fields": ["market_events"],
                "data_requirements": [
                    "causally_ordered_bid_ask_quotes",
                    "aggressor_classified_trades_for_passive_fills",
                    "completed_bars_for_valuation",
                ],
            },
            {
                "name": "order_book_v1",
                "configuration_versions": ["1"],
                "scenario_contract_versions": ["15"],
                "required_fields": ["order_book_events"],
                "data_requirements": [
                    "slice_open_level_two_snapshot",
                    "contiguous_absolute_level_updates",
                    "aggressor_classified_depth_consuming_trades",
                    "completed_bars_for_valuation",
                ],
            },
        ],
    }


def replay(model: str, events: tuple[Mapping[str, object], ...]) -> SchemaReplayResult:
    """Return a schema replay envelope for reconciliation tests."""
    return SchemaReplayResult(
        "15", "market-data-run", model, "a" * 64, len(events), pd.DataFrame(), events
    )


def test_observation_models_are_canonical_immutable_and_causal() -> None:
    event = quote()
    assert event.to_contract_dict()["bid_price"] == "99"
    assert event.clock.to_dict()["event_at"] == "2026-01-02T14:31:00.000000Z"
    assert event.provenance.to_dict()["dataset_sequence"] == "1"
    with pytest.raises(FrozenInstanceError):
        event.instrument_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="causal"):
        ReplayEventClock("2026-01-02T14:31:02Z", "2026-01-02T14:31:01Z", "2026-01-02T14:31:03Z", 1)
    with pytest.raises(ValueError, match="ingested_at"):
        ExecutableQuote(
            "asset-a",
            clock(),
            ObservationProvenance("p", "d", 1, "2026-01-02T14:31:01Z"),
            99,
            1,
            101,
            1,
        )


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: ExecutableQuote("asset-a", clock(), provenance(), 102, 1, 101, 1), "crossed"),
        (lambda: ExecutableTrade("asset-a", clock(), provenance(), 100, 0, "buy"), "positive"),
        (
            lambda: ExecutableTrade("asset-a", clock(), provenance(), 100, 1, cast("Any", "none")),
            "aggressor",
        ),
        (lambda: ObservationProvenance("p", "d", 0, "2026-01-02T14:31:03Z"), "positive"),
    ],
)
def test_quote_trade_observations_reject_non_executable_data(factory: Any, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        factory()


def test_order_book_models_preserve_depth_side_sequence_and_liquidity() -> None:
    opening = snapshot()
    assert opening.bids[0].price == 99
    assert opening.asks[0].price == 101
    set_event = OrderBookSet(
        "asset-a", clock(2, 32), provenance(2, received_minute=32), 2, "bid", 99, 7
    )
    delete = OrderBookDelete(
        "asset-a", clock(3, 33), provenance(3, received_minute=33), 3, "ask", 102
    )
    book_trade = OrderBookTrade(
        "asset-a", clock(4, 34), provenance(4, received_minute=34), 4, 99, 3, "sell"
    )
    data = ReplaySliceMarketData(1, order_book_events=(opening, set_event, delete, book_trade))
    built = build_market_data_replay_scenario(
        schemas=schemas(FakeSchemas()),
        base_scenario=base_scenario(),
        execution=policy("order_book_v1"),
        slices=(data,),
    )
    types = [item["type"] for item in built.to_dict()["slices"][0]["order_book_events"]]
    assert types == ["snapshot", "set", "delete", "trade"]


@pytest.mark.parametrize(
    ("events", "message"),
    [
        ((OrderBookSet("asset-a", clock(), provenance(), 1, "bid", 99, 1),), "snapshot"),
        (
            (
                snapshot(),
                OrderBookDelete(
                    "asset-a", clock(2, 32), provenance(2, received_minute=32), 2, "bid", 97
                ),
            ),
            "missing depth",
        ),
        (
            (
                snapshot(),
                OrderBookSet(
                    "asset-a", clock(2, 32), provenance(2, received_minute=32), 3, "bid", 99, 1
                ),
            ),
            "contiguous",
        ),
        (
            (
                snapshot(),
                OrderBookSet(
                    "asset-a", clock(2, 32), provenance(2, received_minute=32), 2, "bid", 102, 1
                ),
            ),
            "crossed",
        ),
    ],
)
def test_order_book_stream_rejects_incomplete_updates(
    events: tuple[Any, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_market_data_replay_scenario(
            schemas=schemas(FakeSchemas()),
            base_scenario=base_scenario(),
            execution=policy("order_book_v1"),
            slices=(ReplaySliceMarketData(1, order_book_events=events),),
        )


def test_policy_and_capability_negotiation_are_strict() -> None:
    parsed = market_data_model_capabilities(capabilities())
    assert [item.name for item in parsed] == ["order_book_v1", "quote_trade_v1"]
    require_market_data_capabilities(capabilities(), schemas(FakeSchemas()), policy())
    require_market_data_capabilities(
        capabilities(), schemas(FakeSchemas()), policy("order_book_v1"), scenario_format="jsonl"
    )
    with pytest.raises(ValueError, match="max_depth_levels"):
        MarketDataExecutionPolicy("order_book_v1", 1, (schedule(),), 0)
    with pytest.raises(ValueError, match="does not accept"):
        MarketDataExecutionPolicy("quote_trade_v1", 1, (schedule(),), 1)
    missing = capabilities()
    cast("list[dict[str, object]]", missing["execution_model_contracts"])[0][
        "data_requirements"
    ] = ["completed_bars_for_valuation"]
    with pytest.raises(ValueError, match="data requirements"):
        require_market_data_capabilities(missing, schemas(FakeSchemas()), policy())


def test_builder_serialization_stream_manifest_and_write(tmp_path: Path) -> None:
    fake = FakeSchemas()
    built = scenario(fake)
    assert built.contract_version == "15"
    assert len(fake.records) == 3
    assert json.loads(market_data_scenario_to_json(built))["execution"]["model"] == "quote_trade_v1"
    assert len(market_data_scenario_to_jsonl(built).splitlines()) == 3
    path = write_market_data_scenario(built, tmp_path / "nested" / "scenario.json")
    assert path.read_text(encoding="utf-8") == market_data_scenario_to_json(built)
    with pytest.raises(FileExistsError):
        write_market_data_scenario(built, path)
    stream = write_market_data_scenario(built, tmp_path / "scenario.jsonl", stream=True)
    assert len(stream.read_text(encoding="utf-8").splitlines()) == 3
    manifest = bind_market_data_manifest({"contract": {"version": "15"}}, built)
    market_data = cast("Mapping[str, object]", manifest["market_data"])
    assert market_data["model"] == "quote_trade_v1"
    assert len(cast("list[object]", market_data["slices"])) == 1


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("sequence", "every base market slice"),
        ("missing-slice", "unknown slice"),
        ("family", "requires only quote"),
        ("instrument", "unknown instrument"),
        ("tick", "tick"),
    ],
)
def test_builder_rejects_incompatible_observations(case: str, message: str) -> None:
    base = base_scenario()
    data = ReplaySliceMarketData(1, (quote(),))
    if case == "sequence":
        data = ReplaySliceMarketData(2, data.market_events)
    elif case == "missing-slice":
        base["slices"] = []
    elif case == "family":
        data = ReplaySliceMarketData(1, order_book_events=(snapshot(),))
    elif case == "instrument":
        base["instruments"] = []
    else:
        data = ReplaySliceMarketData(1, (replace(quote(), bid_price="99.001"),))
    with pytest.raises(ValueError, match=message):
        build_market_data_replay_scenario(
            schemas=schemas(FakeSchemas()), base_scenario=base, execution=policy(), slices=(data,)
        )


def test_reconcile_matches_passive_fill_to_exact_source(tmp_path: Path) -> None:
    built = scenario()
    scenario_path = write_market_data_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    received = built.to_dict()["slices"][0]
    fill = {
        "fill_id": "fill-a",
        "instrument_id": "asset-a",
        "side": "buy",
        "quantity": "6",
        "price": "100",
        "executed_at": "2026-01-02T14:32:00Z",
        "slice_sequence": "1",
    }
    fake = FakeSchemas()
    fake.replay = replay(
        "quote_trade_v1",
        (
            {"event_type": "market_slice_received", "payload": received},
            {"event_type": "fill_applied", "payload": fill},
        ),
    )
    result = reconcile_market_data_replay(schemas(fake), scenario_path, journal_path)
    assert result.to_dict()["status"] == "verified"
    assert result.matched_fill_sources[0]["source_ingest_sequence"] == "2"


def test_reconcile_rejects_changed_events_and_exhausted_liquidity(tmp_path: Path) -> None:
    built = scenario()
    scenario_path = write_market_data_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    received = built.to_dict()["slices"][0]
    fill = {
        "fill_id": "fill-a",
        "instrument_id": "asset-a",
        "side": "buy",
        "quantity": "6",
        "price": "100",
        "executed_at": "2026-01-02T14:32:00Z",
        "slice_sequence": "1",
    }
    fake = FakeSchemas()
    fake.replay = replay(
        "quote_trade_v1",
        (
            {"event_type": "market_slice_received", "payload": received},
            {"event_type": "fill_applied", "payload": fill},
            {"event_type": "fill_applied", "payload": {**fill, "fill_id": "fill-b"}},
        ),
    )
    with pytest.raises(TradingEngineContractError, match="exactly one"):
        reconcile_market_data_replay(schemas(fake), scenario_path, journal_path)
    changed = json.loads(json.dumps(received))
    changed["market_events"][0]["ask_price"] = "102"
    fake.replay = replay(
        "quote_trade_v1", ({"event_type": "market_slice_received", "payload": changed},)
    )
    with pytest.raises(TradingEngineContractError, match="differs"):
        reconcile_market_data_replay(schemas(fake), scenario_path, journal_path)


def test_timestamp_and_slice_receipt_bounds_are_enforced() -> None:
    late_clock = ReplayEventClock(
        "2026-01-02T14:31:00Z", "2026-01-02T21:00:01Z", "2026-01-02T21:00:03Z", 1
    )
    late = ExecutableQuote(
        "asset-a",
        late_clock,
        ObservationProvenance("p", "d", 1, "2026-01-02T21:00:04Z"),
        99,
        1,
        101,
        1,
    )
    with pytest.raises(ValueError, match="receipt time"):
        build_market_data_replay_scenario(
            schemas=schemas(FakeSchemas()),
            base_scenario=base_scenario(),
            execution=policy(),
            slices=(ReplaySliceMarketData(1, (late,)),),
        )
    assert cast("datetime", late.clock.event_at).tzinfo is not None
