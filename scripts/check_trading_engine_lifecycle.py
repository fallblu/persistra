"""Verify Persistra lifecycle replay against pinned Trading Engine v12."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from persistra.integrations.trading_engine import (
    CashDividendLifecycleAction,
    EventDeliveryPolicy,
    HaltLifecycleEvent,
    IdentifierChangeLifecycleEvent,
    LifecycleProvenance,
    LifecycleSliceEvents,
    ResumeLifecycleEvent,
    ScheduledCorporateAction,
    ScheduledLifecycleEvent,
    SplitLifecycleAction,
    TerminalDisposition,
    TerminalLifecycleEvent,
    TradingEngineContractSchemas,
    VenueCalendarPolicy,
    VenuePhasePolicy,
    VenueSessionPolicy,
    build_lifecycle_replay_scenario,
    reconcile_lifecycle_replay,
    require_lifecycle_capabilities,
    write_lifecycle_scenario,
)


def main() -> None:
    """Build, execute, and reconcile a complete v12 lifecycle transition sequence."""
    if len(sys.argv) != 3:
        raise SystemExit("usage: check_trading_engine_lifecycle.py CONTRACT_DIRECTORY EXECUTABLE")
    schemas = TradingEngineContractSchemas.load(sys.argv[1])
    executable = Path(sys.argv[2])
    document = _object(
        json.loads((schemas.directory / "fixtures/demo.scenario.json").read_text(encoding="utf-8"))
    )
    document["schedule"] = []
    require_lifecycle_capabilities(_capabilities(executable), schemas)
    built = build_lifecycle_replay_scenario(
        schemas=schemas,
        base_scenario=document,
        calendars=_calendars(document["venue_calendars"]),
        slices=_slices(document),
    )
    with tempfile.TemporaryDirectory(prefix="persistra-lifecycle-") as raw_directory:
        directory = Path(raw_directory)
        scenario_path = write_lifecycle_scenario(built, directory / "scenario.json")
        journal_path = directory / "journal.jsonl"
        subprocess.run(
            (str(executable), "-i", str(scenario_path), "-j", str(journal_path)),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        result = reconcile_lifecycle_replay(schemas, scenario_path, journal_path)
    if len(result.applied_actions) != 2 or len(result.applied_lifecycle) != 4:
        raise SystemExit("v12 replay omitted action or lifecycle evidence")
    print(
        f"Trading Engine lifecycle v{schemas.version}: {schemas.sha256} "
        f"({len(result.applied_actions)} actions, {len(result.applied_lifecycle)} transitions, "
        f"{len(result.order_effects)} order effects, {len(result.valuations)} valuations)"
    )


def _calendars(value: object) -> tuple[VenueCalendarPolicy, ...]:
    selected: list[VenueCalendarPolicy] = []
    for raw in cast("list[object]", value):
        item = _object(raw)
        sessions: list[VenueSessionPolicy] = []
        for raw_session in cast("list[object]", item["sessions"]):
            session = _object(raw_session)
            phases = tuple(
                VenuePhasePolicy(**cast("dict[str, Any]", raw_phase))
                for raw_phase in cast("list[object]", session["phases"])
            )
            sessions.append(
                VenueSessionPolicy(
                    cast("str", session["session_date"]),
                    cast("Any", session["policy"]),
                    phases,
                )
            )
        selected.append(
            VenueCalendarPolicy(
                cast("str", item["calendar_id"]),
                cast("str", item["venue_id"]),
                "America/New_York",
                tuple(cast("list[str]", item["instrument_ids"])),
                tuple(sessions),
            )
        )
    return tuple(selected)


def _slices(document: dict[str, object]) -> tuple[LifecycleSliceEvents, ...]:
    instrument = "demo-equity-acme"
    plan: dict[int, tuple[tuple[object, ...], tuple[object, ...]]] = {
        1: (
            (
                SplitLifecycleAction("split-v12", instrument, 2, 1),
                CashDividendLifecycleAction("dividend-v12", instrument, "1"),
            ),
            (IdentifierChangeLifecycleEvent("rename-v12", instrument, "ACME2", "sip", "ACME2.X"),),
        ),
        2: ((), (HaltLifecycleEvent("halt-v12", instrument, "volatility"),)),
        3: ((), (ResumeLifecycleEvent("resume-v12", instrument),)),
        4: (
            (),
            (
                TerminalLifecycleEvent(
                    "expire-v12",
                    instrument,
                    "expiration",
                    TerminalDisposition("cash_out", "100", "USD"),
                ),
            ),
        ),
    }
    selected: list[LifecycleSliceEvents] = []
    for raw in cast("list[object]", document["slices"]):
        market_slice = _object(raw)
        sequence = int(cast("str", market_slice["slice_sequence"]))
        actions, events = plan[sequence]
        delivery = EventDeliveryPolicy(
            cast("str", market_slice["start_at"]),
            cast("str", market_slice["end_at"]),
            cast("str", market_slice["received_at"]),
            sequence,
            "first_observable_slice",
        )
        received_at = cast("str", market_slice["received_at"])
        selected.append(
            LifecycleSliceEvents(
                sequence,
                tuple(
                    ScheduledCorporateAction(
                        cast("Any", action),
                        delivery,
                        LifecycleProvenance(
                            "fixture",
                            "trading-engine-v12",
                            cast("Any", action).action_id,
                            received_at,
                            "raw",
                        ),
                    )
                    for action in actions
                ),
                tuple(
                    ScheduledLifecycleEvent(
                        cast("Any", event),
                        delivery,
                        LifecycleProvenance(
                            "fixture",
                            "trading-engine-v12",
                            cast("Any", event).event_id,
                            received_at,
                            "raw",
                        ),
                    )
                    for event in events
                ),
            )
        )
    return tuple(selected)


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
