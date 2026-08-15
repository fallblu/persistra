"""Tests for trading-engine scenario construction and serialization."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    BarClockPolicy,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
    build_scenario,
    read_scenario,
    scenario_from_json,
    scenario_to_json,
    write_scenario,
)
from persistra.model import BarSet, Instrument, InstrumentKind, ResultMetadata
from persistra.model._frames import BAR_DTYPES, typed_frame

if TYPE_CHECKING:
    from pathlib import Path


def execution_bars(
    instrument_id: str,
    symbol: str,
    *,
    closes: tuple[float, ...] = (100.0, 101.0),
    adjustment: str = "raw",
    interval: str = "5min",
    volume: float | None = 100.0,
) -> BarSet:
    """Create small tick-aligned intraday bars."""
    timestamps = pd.date_range("2026-01-02T14:30:00Z", periods=len(closes), freq="5min")
    opens = [value - 1 for value in closes]
    frame = typed_frame(
        {
            "instrument_id": [instrument_id] * len(closes),
            "provider": ["test"] * len(closes),
            "provider_symbol": [symbol] * len(closes),
            "interval": [interval] * len(closes),
            "date": [pd.NaT] * len(closes),
            "timestamp": timestamps,
            "timestamp_position": ["provider_label"] * len(closes),
            "source_timezone": ["UTC"] * len(closes),
            "session": ["regular"] * len(closes),
            "price_adjustment": [adjustment] * len(closes),
            "currency": ["USD"] * len(closes),
            "open": opens,
            "high": [value + 1 for value in closes],
            "low": [value - 2 for value in closes],
            "close": closes,
            "adjusted_close": [pd.NA] * len(closes),
            "volume": [volume if volume is not None else pd.NA] * len(closes),
            "dividend_amount": [pd.NA] * len(closes),
            "split_coefficient": [pd.NA] * len(closes),
            "provider_as_of": [pd.NaT] * len(closes),
            "retrieved_at": [datetime(2026, 1, 3, tzinfo=UTC)] * len(closes),
        },
        BAR_DTYPES,
    )
    return BarSet(
        Instrument(instrument_id, InstrumentKind.EQUITY, symbol),
        frame,
        ResultMetadata(
            provider="test",
            operation="bars",
            request_parameters={},
            retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
    )


def policies() -> tuple[BarClockPolicy, SizingPolicy, RiskPolicy, ExecutionPolicy]:
    """Return the explicit supported integration policies."""
    return (
        BarClockPolicy(
            source_timestamp_position="start",
            bar_duration=timedelta(minutes=5),
            availability_delay=timedelta(0),
            receipt_delay=timedelta(0),
        ),
        SizingPolicy(),
        RiskPolicy(max_order_quantity=1_000, max_position=1_000),
        ExecutionPolicy(participation_bps=5_000, fixed_fee="0.25", fee_bps=10),
    )


def built_scenario(*, volume: float | None = 100.0):
    """Build a deterministic two-instrument target-weight scenario."""
    first = execution_bars("asset-a", "AAA", volume=volume)
    second = execution_bars("asset-b", "BBB", closes=(200.0, 202.0), volume=volume)
    targets = pd.DataFrame(
        {"asset-b": [0.25, 0.0], "asset-a": [0.5, 0.75]},
        index=first.frame["timestamp"],
    )
    clock, sizing, risk, execution = policies()
    return build_scenario(
        [second, first],
        targets,
        instruments=[
            ExecutionInstrument("asset-b", "BBB", "USD", "0.01"),
            ExecutionInstrument("asset-a", "AAA", "USD", "0.01"),
        ],
        initial_cash="10000",
        clock_policy=clock,
        sizing_policy=sizing,
        risk=risk,
        execution=execution,
        run_id="unit-demo",
    )


def test_build_scenario_sequences_groups_and_sizes_targets() -> None:
    scenario = built_scenario()

    assert [item.instrument_id for item in scenario.instruments] == ["asset-a", "asset-b"]
    assert [(item.source_sequence, item.instrument_id) for item in scenario.bars] == [
        (1, "asset-a"),
        (2, "asset-b"),
        (3, "asset-a"),
        (4, "asset-b"),
    ]
    assert [item.after_bar_sequence for item in scenario.decisions] == [2, 2, 4, 4]
    assert [item.quantity for item in scenario.decisions] == [50, 12, 74, 0]
    assert scenario.bars[0].end_at == pd.Timestamp("2026-01-02T14:35:00Z")
    assert scenario.bars[0].available_at == pd.Timestamp("2026-01-02T14:35:00Z")
    assert scenario.bars[0].received_at == pd.Timestamp("2026-01-02T14:35:00Z")


def test_scenario_json_is_stable_round_trippable_and_exclusive(tmp_path: Path) -> None:
    scenario = built_scenario()
    document = scenario_to_json(scenario)

    assert document == scenario_to_json(scenario)
    assert scenario_to_json(scenario_from_json(document)) == document
    payload = json.loads(document)
    assert payload["schema_version"] == 1
    assert payload["initial_cash"] == "10000"
    assert payload["schedule"][0]["after_bar_sequence"] == "2"
    assert payload["bars"][0]["open"] == "99"

    path = tmp_path / "scenario.json"
    assert write_scenario(scenario, path) == path
    assert read_scenario(path).run_id == "unit-demo"
    with pytest.raises(FileExistsError):
        write_scenario(scenario, path)
    write_scenario(scenario, path, overwrite=True)


def test_scenario_reader_rejects_intents_outside_the_supported_profile() -> None:
    payload = json.loads(scenario_to_json(built_scenario()))
    payload["schedule"][0]["intents"].append(
        {"type": "emit_metric", "name": "signal", "value": "0.5"}
    )

    with pytest.raises(ValueError, match="target_position intents only"):
        scenario_from_json(json.dumps(payload))


def test_build_scenario_accepts_explicit_quantities_and_checks_lots() -> None:
    bars = execution_bars("asset-a", "AAA")
    quantities = pd.DataFrame(
        {"asset-a": [10, 12]},
        index=bars.frame["timestamp"],
    )
    clock, sizing, risk, execution = policies()
    scenario = build_scenario(
        [bars],
        target_quantities=quantities,
        instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size=2)],
        initial_cash=10_000,
        clock_policy=clock,
        sizing_policy=sizing,
        risk=risk,
        execution=execution,
        run_id="quantities",
    )
    assert [item.quantity for item in scenario.decisions] == [10, 12]

    quantities.iloc[0, 0] = 11
    with pytest.raises(ValueError, match="lot aligned"):
        build_scenario(
            [bars],
            target_quantities=quantities,
            instruments=[
                ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size=2)
            ],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="quantities",
        )


@pytest.mark.parametrize(
    ("adjustment", "interval", "message"),
    [
        ("adjusted", "5min", "raw, unadjusted"),
        ("raw", "daily", "unsupported intraday interval"),
    ],
)
def test_build_scenario_rejects_unsupported_bar_semantics(
    adjustment: str,
    interval: str,
    message: str,
) -> None:
    bars = execution_bars("asset-a", "AAA", adjustment=adjustment, interval=interval)
    target = pd.DataFrame({"asset-a": [1.0, 1.0]}, index=bars.frame["timestamp"])
    clock, sizing, risk, execution = policies()
    with pytest.raises(ValueError, match=message):
        build_scenario(
            [bars],
            target,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )


def test_build_scenario_rejects_tick_misalignment_and_short_weights() -> None:
    bars = execution_bars("asset-a", "AAA", closes=(100.005, 101.0))
    target = pd.DataFrame({"asset-a": [1.0, 1.0]}, index=bars.frame["timestamp"])
    clock, sizing, risk, execution = policies()

    def build(selected_bars: BarSet, selected_target: pd.DataFrame):
        return build_scenario(
            [selected_bars],
            selected_target,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )

    with pytest.raises(ValueError, match="tick aligned"):
        build(bars, target)

    valid_bars = execution_bars("asset-a", "AAA")
    target.iloc[:, :] = -0.1
    target.index = valid_bars.frame["timestamp"]
    with pytest.raises(ValueError, match="long-only"):
        build(valid_bars, target)


def test_build_scenario_rejects_decisions_received_after_the_next_bar_starts() -> None:
    bars = execution_bars("asset-a", "AAA")
    targets = pd.DataFrame({"asset-a": [1.0, 1.0]}, index=bars.frame["timestamp"])
    _, sizing, risk, execution = policies()
    delayed_clock = BarClockPolicy(
        source_timestamp_position="start",
        bar_duration=timedelta(minutes=5),
        availability_delay=timedelta(seconds=1),
        receipt_delay=timedelta(0),
    )

    with pytest.raises(ValueError, match="next executable bar start_at"):
        build_scenario(
            [bars],
            targets,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=delayed_clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="causal-clock",
        )


def test_policy_and_scalar_models_reject_unsupported_values() -> None:
    with pytest.raises(ValueError, match="positive"):
        BarClockPolicy("start", timedelta(0), timedelta(0), timedelta(0))
    with pytest.raises(ValueError, match="at most six"):
        ExecutionInstrument("asset", "AAA", "USD", "0.0000001")
    with pytest.raises(ValueError, match="10000"):
        ExecutionPolicy(participation_bps=10_001)
    with pytest.raises(ValueError, match="positive"):
        RiskPolicy(max_order_quantity=0, max_position=1)
    with pytest.raises(ValueError, match="exactly one"):
        clock, sizing, risk, execution = policies()
        build_scenario(
            [execution_bars("asset-a", "AAA")],
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=1,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="missing-targets",
        )
