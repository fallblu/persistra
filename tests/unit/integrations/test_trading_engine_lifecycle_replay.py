"""Tests for Trading Engine v1 venue, action, and lifecycle replay."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    CashDividendLifecycleAction,
    DistributionLifecycleAction,
    EventDeliveryPolicy,
    FractionalEntitlementPolicy,
    HaltLifecycleEvent,
    IdentifierChangeLifecycleEvent,
    LifecycleProvenance,
    LifecycleSliceEvents,
    ResumeLifecycleEvent,
    ScheduledCorporateAction,
    ScheduledLifecycleEvent,
    SchemaReplayResult,
    SplitLifecycleAction,
    TerminalDisposition,
    TerminalLifecycleEvent,
    TradingEngineContractError,
    TradingEngineContractSchemas,
    VenueCalendarPolicy,
    VenuePhasePolicy,
    VenueSessionPolicy,
    bind_lifecycle_manifest,
    build_lifecycle_replay_scenario,
    lifecycle_scenario_to_json,
    lifecycle_scenario_to_jsonl,
    reconcile_lifecycle_replay,
    require_lifecycle_capabilities,
    write_lifecycle_scenario,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


class FakeSchemas:
    """Minimal schema double for construction and reconciliation."""

    version = "1"

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


def schemas(fake: FakeSchemas) -> TradingEngineContractSchemas:
    return cast("TradingEngineContractSchemas", cast("object", fake))


def calendar() -> VenueCalendarPolicy:
    return VenueCalendarPolicy(
        "xnas-v1",
        "XNAS",
        "America/New_York",
        ("asset-a",),
        (
            VenueSessionPolicy("2026-01-01", "holiday"),
            VenueSessionPolicy(
                "2026-01-02",
                "regular",
                (VenuePhasePolicy("regular", "2026-01-02T14:30:00Z", "2026-01-02T21:00:00Z"),),
            ),
        ),
    )


def delivery(sequence: int, minute: int) -> EventDeliveryPolicy:
    return EventDeliveryPolicy(
        f"2026-01-02T14:{minute:02d}:00Z",
        f"2026-01-02T14:{minute:02d}:01Z",
        f"2026-01-02T14:{minute:02d}:02Z",
        sequence,
        "first_observable_slice",
    )


def provenance(source: str, minute: int) -> LifecycleProvenance:
    return LifecycleProvenance(
        "sip", "normalized-actions", source, f"2026-01-02T14:{minute:02d}:02Z", "raw"
    )


def scheduled_action(action: Any, minute: int) -> ScheduledCorporateAction:
    return ScheduledCorporateAction(
        action, delivery(1, minute), provenance(action.action_id, minute)
    )


def scheduled_event(event: Any, minute: int) -> ScheduledLifecycleEvent:
    return ScheduledLifecycleEvent(event, delivery(1, minute), provenance(event.event_id, minute))


def slice_events() -> LifecycleSliceEvents:
    return LifecycleSliceEvents(
        1,
        (
            scheduled_action(SplitLifecycleAction("split-a", "asset-a", 2, 1), 31),
            scheduled_action(CashDividendLifecycleAction("dividend-a", "asset-a", 1), 32),
        ),
        (
            scheduled_event(
                IdentifierChangeLifecycleEvent("rename-a", "asset-a", "NEW", "sip", "NEW.X"),
                33,
            ),
            scheduled_event(HaltLifecycleEvent("halt-a", "asset-a", "volatility"), 34),
            scheduled_event(ResumeLifecycleEvent("resume-a", "asset-a"), 35),
        ),
    )


def base_scenario() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "metadata": {"source": "unit-test"},
        "run_id": "lifecycle-run",
        "base_currency": "USD",
        "initial_portfolio": {
            "cash": [{"currency": "USD", "amount": "1000"}],
            "positions": [
                {
                    "instrument_id": "asset-a",
                    "quantity": "1",
                    "cost_basis": "90",
                    "realized_pnl": "0",
                    "dividend_pnl": "0",
                    "execution_fees": "0",
                    "borrow_fees": "0",
                }
            ],
            "marks": [{"instrument_id": "asset-a", "price": "100"}],
            "fx_rates": [{"currency": "USD", "rate": "1"}],
        },
        "instruments": [
            {
                "instrument_id": "asset-a",
                "symbol": "OLD",
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
                "fx_rates": [{"currency": "USD", "rate": "1"}],
                "corporate_actions": [],
                "borrow_observations": [],
                "cash_rate_observations": [],
                "settlement_failures": [],
                "lifecycle_events": [],
            }
        ],
    }


def scenario(fake: FakeSchemas | None = None):
    return build_lifecycle_replay_scenario(
        schemas=schemas(fake or FakeSchemas()),
        base_scenario=base_scenario(),
        calendars=(calendar(),),
        slices=(slice_events(),),
    )


def replay(events: tuple[Mapping[str, object], ...]) -> SchemaReplayResult:
    return SchemaReplayResult(
        "1", "lifecycle-run", "completed_bar_v1", "a" * 64, len(events), pd.DataFrame(), events
    )


def capabilities() -> dict[str, object]:
    return {
        "scenario_contract_versions": ["1"],
        "journal_contract_versions": ["1"],
        "scenario_formats": ["json", "jsonl"],
        "journal_formats": ["jsonl"],
    }


def test_calendar_requires_explicit_timezone_local_date_and_session_policy() -> None:
    selected = calendar()
    assert selected.to_contract_dict()["calendar_version"] == "1"
    assert selected.sessions[0].policy == "holiday"
    with pytest.raises(FrozenInstanceError):
        selected.venue_id = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError, match="IANA"):
        VenueCalendarPolicy("c", "X", "Mars/Olympus", ("asset-a",), selected.sessions)
    with pytest.raises(ValueError, match="holiday"):
        VenueSessionPolicy("2026-01-02", "holiday", selected.sessions[1].phases)
    with pytest.raises(ValueError, match="requires"):
        VenueSessionPolicy("2026-01-02", "regular")
    with pytest.raises(ValueError, match="local session date"):
        VenueCalendarPolicy(
            "c",
            "X",
            "America/New_York",
            ("asset-a",),
            (
                VenueSessionPolicy(
                    "2026-01-02",
                    "regular",
                    (VenuePhasePolicy("regular", "2026-01-03T14:30:00Z", "2026-01-03T21:00:00Z"),),
                ),
            ),
        )


def test_delivery_and_provenance_reject_adjusted_or_noncausal_history() -> None:
    with pytest.raises(ValueError, match="causal"):
        EventDeliveryPolicy(
            "2026-01-02T14:31:00Z",
            "2026-01-02T14:30:00Z",
            "2026-01-02T14:32:00Z",
            1,
            "first_observable_slice",
        )
    adjusted = LifecycleProvenance("p", "d", "s", "2026-01-02T14:31:02Z", "adjusted_only")
    with pytest.raises(ValueError, match="adjusted-only"):
        ScheduledCorporateAction(
            SplitLifecycleAction("a", "asset-a", 2, 1), delivery(1, 31), adjusted
        )


def test_action_and_terminal_policies_are_explicit_and_canonical() -> None:
    reject = FractionalEntitlementPolicy("reject")
    cash = FractionalEntitlementPolicy("cash_in_lieu", "10", "USD")
    distribution = DistributionLifecycleAction(
        "spin", "asset-a", "asset-a", "spin_off", 1, 2, 2500, cash
    )
    assert distribution.to_contract_dict()["fractional_policy"] == {
        "policy": "cash_in_lieu",
        "price": "10",
        "currency": "USD",
    }
    assert reject.to_dict() == {"policy": "reject"}
    assert TerminalDisposition("cash_out", 100, "USD").to_dict()["price"] == "100"
    with pytest.raises(ValueError, match="does not accept"):
        FractionalEntitlementPolicy("reject", 1, "USD")
    with pytest.raises(ValueError, match="does not accept"):
        TerminalDisposition("hold", 1, "USD")
    with pytest.raises(ValueError, match="delisting reason"):
        TerminalLifecycleEvent("expiry", "asset-a", "expiration", TerminalDisposition("hold"), "x")


def test_builder_validates_batch_stream_manifest_and_write(tmp_path: Path) -> None:
    fake = FakeSchemas()
    built = scenario(fake)
    assert built.contract_version == "1"
    assert len(fake.records) == 3
    document = json.loads(lifecycle_scenario_to_json(built))
    assert document["venue_calendars"][0]["venue_id"] == "XNAS"
    assert len(lifecycle_scenario_to_jsonl(built).splitlines()) == 3
    path = write_lifecycle_scenario(built, tmp_path / "scenario.json")
    assert path.read_text(encoding="utf-8") == lifecycle_scenario_to_json(built)
    with pytest.raises(FileExistsError):
        write_lifecycle_scenario(built, path)
    manifest = bind_lifecycle_manifest({"contract": {"version": "1"}}, built)
    lifecycle = cast("Mapping[str, object]", manifest["lifecycle"])
    assert (
        cast("Mapping[str, str]", lifecycle["calendar_time_zones"])["xnas-v1"] == "America/New_York"
    )


def test_capability_negotiation_requires_current_batch_or_stream_contracts() -> None:
    require_lifecycle_capabilities(capabilities(), schemas(FakeSchemas()))
    require_lifecycle_capabilities(capabilities(), schemas(FakeSchemas()), scenario_format="jsonl")
    missing = capabilities()
    missing["scenario_contract_versions"] = ["2"]
    with pytest.raises(ValueError, match="scenario contract"):
        require_lifecycle_capabilities(missing, schemas(FakeSchemas()))


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("calendar", "exactly once"),
        ("slice", "every base market slice"),
        ("unknown", "unknown instrument"),
        ("resume", "halted instrument"),
        ("terminal", "terminal instrument"),
        ("delivery", "outside"),
    ],
)
def test_builder_rejects_ambiguous_lifecycle_inputs(case: str, message: str) -> None:
    base = base_scenario()
    calendars = (calendar(),)
    events = slice_events()
    if case == "calendar":
        calendars = ()
    elif case == "slice":
        events = LifecycleSliceEvents(2)
    elif case == "unknown":
        events = LifecycleSliceEvents(
            1,
            lifecycle_events=(scheduled_event(HaltLifecycleEvent("h", "missing", "halt"), 31),),
        )
    elif case == "resume":
        events = LifecycleSliceEvents(
            1,
            lifecycle_events=(scheduled_event(ResumeLifecycleEvent("r", "asset-a"), 31),),
        )
    elif case == "terminal":
        events = LifecycleSliceEvents(
            1,
            lifecycle_events=(
                scheduled_event(
                    TerminalLifecycleEvent(
                        "x", "asset-a", "expiration", TerminalDisposition("hold")
                    ),
                    31,
                ),
                scheduled_event(HaltLifecycleEvent("h", "asset-a", "halt"), 32),
            ),
        )
    else:
        early = EventDeliveryPolicy(
            "2026-01-01T14:31:00Z",
            "2026-01-01T14:31:01Z",
            "2026-01-01T14:31:02Z",
            1,
            "first_observable_slice",
        )
        events = LifecycleSliceEvents(
            1,
            lifecycle_events=(
                ScheduledLifecycleEvent(
                    HaltLifecycleEvent("h", "asset-a", "halt"),
                    early,
                    LifecycleProvenance("p", "d", "h", "2026-01-01T14:31:02Z", "raw"),
                ),
            ),
        )
    with pytest.raises(ValueError, match=message):
        build_lifecycle_replay_scenario(
            schemas=schemas(FakeSchemas()),
            base_scenario=base,
            calendars=calendars,
            slices=(events,),
        )


def test_reconcile_actions_lifecycle_orders_and_valuations(tmp_path: Path) -> None:
    built = scenario()
    scenario_path = write_lifecycle_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    source = built.to_dict()["slices"][0]
    actions = source["corporate_actions"]
    lifecycle = source["lifecycle_events"]
    events: tuple[Mapping[str, object], ...] = (
        {"event_type": "valuation", "payload": {"equity": "1001"}},
        {"event_type": "market_slice_received", "payload": source},
        {
            "event_type": "split_applied",
            "payload": {"action": actions[1], "previous_quantity": "1", "adjusted_quantity": "2"},
        },
        {
            "event_type": "cash_dividend_applied",
            "payload": {"action": actions[0], "quantity": "2", "cash_amount": "2"},
        },
        {
            "event_type": "lifecycle_applied",
            "payload": {
                "lifecycle_event": lifecycle[0],
                "listing": {
                    "instrument_id": "asset-a",
                    "symbol": "NEW",
                    "status": "tradable",
                    "provider_mappings": [{"provider": "sip", "provider_instrument_id": "NEW.X"}],
                },
                "liquidated_quantity": "0",
                "cash_amount": "0",
            },
        },
        {
            "event_type": "lifecycle_applied",
            "payload": {
                "lifecycle_event": lifecycle[1],
                "listing": {
                    "instrument_id": "asset-a",
                    "symbol": "NEW",
                    "status": "halted",
                    "provider_mappings": [],
                },
                "liquidated_quantity": "0",
                "cash_amount": "0",
            },
        },
        {
            "event_type": "lifecycle_applied",
            "payload": {
                "lifecycle_event": lifecycle[2],
                "listing": {
                    "instrument_id": "asset-a",
                    "symbol": "NEW",
                    "status": "tradable",
                    "provider_mappings": [],
                },
                "liquidated_quantity": "0",
                "cash_amount": "0",
            },
        },
        {"event_type": "order_adjusted", "payload": {"action_id": "split-a"}},
        {"event_type": "valuation", "payload": {"equity": "1002"}},
    )
    fake = FakeSchemas()
    fake.replay = replay(events)
    result = reconcile_lifecycle_replay(schemas(fake), scenario_path, journal_path)
    assert result.to_dict() == {
        "contract_version": "1",
        "run_id": "lifecycle-run",
        "applied_actions": 2,
        "applied_lifecycle": 3,
        "order_effects": 1,
        "valuations": 2,
        "status": "verified",
    }


def test_reconcile_rejects_unreconciled_action_effect(tmp_path: Path) -> None:
    built = scenario()
    scenario_path = write_lifecycle_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    source = built.to_dict()["slices"][0]
    fake = FakeSchemas()
    fake.replay = replay(
        (
            {"event_type": "valuation", "payload": {}},
            {"event_type": "market_slice_received", "payload": source},
            {
                "event_type": "split_applied",
                "payload": {
                    "action": source["corporate_actions"][1],
                    "previous_quantity": "1",
                    "adjusted_quantity": "3",
                },
            },
        )
    )
    with pytest.raises(TradingEngineContractError, match="split quantity"):
        reconcile_lifecycle_replay(schemas(fake), scenario_path, journal_path)


def test_reconcile_distribution_and_terminal_cash_out(tmp_path: Path) -> None:
    distribution = DistributionLifecycleAction(
        "spin-a",
        "asset-a",
        "asset-a",
        "spin_off",
        1,
        2,
        2500,
        FractionalEntitlementPolicy("cash_in_lieu", 10, "USD"),
    )
    terminal = TerminalLifecycleEvent(
        "delist-a",
        "asset-a",
        "delisting",
        TerminalDisposition("cash_out", 100, "USD"),
        "acquisition",
    )
    data = LifecycleSliceEvents(
        1,
        (scheduled_action(distribution, 31),),
        (scheduled_event(terminal, 32),),
    )
    built = build_lifecycle_replay_scenario(
        schemas=schemas(FakeSchemas()),
        base_scenario=base_scenario(),
        calendars=(calendar(),),
        slices=(data,),
    )
    scenario_path = write_lifecycle_scenario(built, tmp_path / "scenario.json")
    journal_path = tmp_path / "journal.jsonl"
    journal_path.write_text("{}\n", encoding="utf-8")
    source = built.to_dict()["slices"][0]
    fake = FakeSchemas()
    fake.replay = replay(
        (
            {"event_type": "valuation", "payload": {}},
            {"event_type": "market_slice_received", "payload": source},
            {
                "event_type": "distribution_applied",
                "payload": {
                    "action": source["corporate_actions"][0],
                    "source_quantity": "1",
                    "destination_quantity": "0",
                    "fractional_quantity": "0.5",
                    "allocated_basis": "22.5",
                    "fractional_basis": "22.5",
                    "cash_in_lieu": "5",
                },
            },
            {
                "event_type": "lifecycle_applied",
                "payload": {
                    "lifecycle_event": source["lifecycle_events"][0],
                    "listing": {
                        "instrument_id": "asset-a",
                        "symbol": "OLD",
                        "status": "delisted",
                        "provider_mappings": [],
                    },
                    "liquidated_quantity": "2",
                    "cash_amount": "200",
                },
            },
            {"event_type": "valuation", "payload": {}},
        )
    )
    result = reconcile_lifecycle_replay(schemas(fake), scenario_path, journal_path)
    assert len(result.applied_actions) == len(result.applied_lifecycle) == 1


def test_secondary_validation_and_serialization_boundaries(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive duration"):
        VenuePhasePolicy("regular", "2026-01-02T15:00:00Z", "2026-01-02T15:00:00Z")
    with pytest.raises(ValueError, match="nonoverlapping"):
        VenueSessionPolicy(
            "2026-01-02",
            "regular",
            (
                VenuePhasePolicy("premarket", "2026-01-02T14:00:00Z", "2026-01-02T15:00:00Z"),
                VenuePhasePolicy("regular", "2026-01-02T14:30:00Z", "2026-01-02T21:00:00Z"),
            ),
        )
    with pytest.raises(ValueError, match="requires instruments"):
        VenueCalendarPolicy("c", "X", "UTC", (), calendar().sessions)
    with pytest.raises(ValueError, match="delivery slice"):
        LifecycleSliceEvents(
            1,
            lifecycle_events=(
                ScheduledLifecycleEvent(
                    HaltLifecycleEvent("h", "asset-a", "halt"),
                    delivery(2, 31),
                    provenance("h", 31),
                ),
            ),
        )
    with pytest.raises(ValueError, match="ingestion"):
        ScheduledLifecycleEvent(
            HaltLifecycleEvent("h", "asset-a", "halt"),
            delivery(1, 31),
            LifecycleProvenance("p", "d", "h", "2026-01-02T14:30:00Z", "raw"),
        )
    with pytest.raises(ValueError, match="reason"):
        HaltLifecycleEvent("h", "asset-a", " bad ")
    built = scenario()
    with pytest.raises(ValueError, match="indent"):
        lifecycle_scenario_to_json(built, indent=-1)
    stream = write_lifecycle_scenario(built, tmp_path / "scenario.jsonl", stream=True)
    assert len(stream.read_text(encoding="utf-8").splitlines()) == 3
    with pytest.raises(ValueError, match="already contains"):
        bind_lifecycle_manifest(
            {"contract": {"version": "1"}, "lifecycle": {}},
            built,
        )
    wrong = FakeSchemas()
    wrong.version = "2"  # type: ignore[misc]
    with pytest.raises(ValueError, match="requires Trading Engine contract v1"):
        require_lifecycle_capabilities(capabilities(), schemas(wrong))
