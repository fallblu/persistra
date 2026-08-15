"""Tests for Trading Engine scenario construction and serialization."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    BarClockPolicy,
    EmitMetricIntent,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
    TargetQuantitiesIntent,
    TargetWeightsIntent,
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
    offset: str | None = None,
) -> BarSet:
    """Create small tick-aligned intraday bars."""
    timestamps = pd.date_range("2026-01-02T14:30:00Z", periods=len(closes), freq="5min")
    if offset is not None:
        timestamps += pd.Timedelta(offset)
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
            "open": [value - 1 for value in closes],
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
            request_parameters={"symbol": symbol, "api_key": "redacted"},
            retrieved_at=datetime(2026, 1, 3, tzinfo=UTC),
        ),
    )


def policies() -> tuple[BarClockPolicy, SizingPolicy, RiskPolicy, ExecutionPolicy]:
    """Return explicit integration policies."""
    return (
        BarClockPolicy("start", timedelta(minutes=5), timedelta(0), timedelta(0)),
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
        metadata={"research": {"name": "unit"}},
    )


def test_build_scenario_creates_synchronized_slices_and_portable_weights() -> None:
    scenario = built_scenario()

    assert [item.instrument_id for item in scenario.instruments] == ["asset-a", "asset-b"]
    assert [item.slice_sequence for item in scenario.slices] == [1, 2]
    assert [[bar.instrument_id for bar in item.bars] for item in scenario.slices] == [
        ["asset-a", "asset-b"],
        ["asset-a", "asset-b"],
    ]
    assert [item.after_slice_sequence for item in scenario.schedule] == [1, 2]
    first_intent = scenario.schedule[0].intents[0]
    assert isinstance(first_intent, TargetWeightsIntent)
    assert [target.weight for target in first_intent.targets] == [
        Decimal("0.5"),
        Decimal("0.25"),
    ]
    assert scenario.slices[0].end_at == pd.Timestamp("2026-01-02T14:35:00Z")
    generated = scenario.metadata["persistra"]
    assert generated["sizing_policy"]["equity_basis"] == "current_marked_equity"
    assert generated["original_targets"][0]["intents"][0]["type"] == "target_weights"


def test_scenario_json_is_stable_round_trippable_and_exclusive(tmp_path: Path) -> None:
    scenario = built_scenario()
    document = scenario_to_json(scenario)

    assert document == scenario_to_json(scenario)
    assert scenario_to_json(scenario_from_json(document)) == document
    payload = json.loads(document)
    assert payload["contract_version"] == "1"
    assert payload["initial_cash"] == "10000"
    assert payload["schedule"][0]["after_slice_sequence"] == "1"
    assert payload["schedule"][0]["intents"][0]["targets"][0]["weight"] == "0.5"
    assert payload["slices"][0]["bars"][0]["open"] == "99"
    assert "start_at" not in payload["slices"][0]["bars"][0]

    path = tmp_path / "scenario.json"
    assert write_scenario(scenario, path) == path
    assert read_scenario(path).run_id == "unit-demo"
    with pytest.raises(FileExistsError):
        write_scenario(scenario, path)
    write_scenario(scenario, path, overwrite=True)


def test_scenario_reader_supports_all_typed_scripted_intents() -> None:
    payload = json.loads(scenario_to_json(built_scenario()))
    payload["schedule"][0]["intents"].extend(
        [
            {
                "type": "submit_order",
                "instrument_id": "asset-a",
                "side": "buy",
                "quantity": "2",
                "order_kind": "limit",
                "limit_price": "99",
            },
            {"type": "cancel_order", "order_id": "order-1"},
            {"type": "emit_metric", "name": " padded signal ", "value": "0.5"},
        ]
    )
    scenario = scenario_from_json(json.dumps(payload))
    assert isinstance(scenario.schedule[0].intents[-1], EmitMetricIntent)
    assert scenario.schedule[0].intents[-1].name == " padded signal "
    reparsed = json.loads(scenario_to_json(scenario))
    assert reparsed["schedule"][0]["intents"][-1]["name"] == " padded signal "
    assert [item["type"] for item in reparsed["schedule"][0]["intents"][-3:]] == [
        "submit_order",
        "cancel_order",
        "emit_metric",
    ]

    payload["schedule"][0]["intents"][-1]["type"] = "unknown"
    with pytest.raises(ValueError, match="unsupported intent type"):
        scenario_from_json(json.dumps(payload))


def test_build_scenario_accepts_explicit_quantities_and_checks_lots() -> None:
    bars = execution_bars("asset-a", "AAA")
    quantities = pd.DataFrame({"asset-a": [10, 12]}, index=bars.frame["timestamp"])
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
    intent = scenario.schedule[0].intents[0]
    assert isinstance(intent, TargetQuantitiesIntent)
    assert intent.targets[0].quantity == 10

    quantities.iloc[0, 0] = 11
    with pytest.raises(ValueError, match="lot aligned"):
        build_scenario(
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


@pytest.mark.parametrize(
    ("adjustment", "interval", "message"),
    [
        ("adjusted", "5min", "raw, unadjusted"),
        ("raw", "daily", "unsupported intraday interval"),
    ],
)
def test_build_scenario_rejects_unsupported_bar_semantics(
    adjustment: str, interval: str, message: str
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


def test_build_scenario_rejects_unsynchronized_tick_misaligned_and_short_data() -> None:
    first = execution_bars("asset-a", "AAA")
    second = execution_bars("asset-b", "BBB", offset="1min")
    target = pd.DataFrame(
        {"asset-a": [0.5, 0.5], "asset-b": [0.5, 0.5]}, index=first.frame["timestamp"]
    )
    clock, sizing, risk, execution = policies()

    def build(selected: list[BarSet], selected_target: pd.DataFrame) -> None:
        build_scenario(
            selected,
            selected_target,
            instruments=[
                ExecutionInstrument("asset-a", "AAA", "USD", "0.01"),
                ExecutionInstrument("asset-b", "BBB", "USD", "0.01"),
            ],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )

    with pytest.raises(ValueError, match="every market slice"):
        build([first, second], target)
    misaligned = execution_bars("asset-a", "AAA", closes=(100.005, 101.0))
    single = target[["asset-a"]]
    with pytest.raises(ValueError, match="tick aligned"):
        build_scenario(
            [misaligned],
            single,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )
    single.iloc[:, :] = -0.1
    single.index = first.frame["timestamp"]
    with pytest.raises(ValueError, match="nonnegative"):
        build_scenario(
            [first],
            single,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )


def test_build_scenario_rejects_decisions_after_next_slice_starts() -> None:
    bars = execution_bars("asset-a", "AAA")
    targets = pd.DataFrame({"asset-a": [1.0, 1.0]}, index=bars.frame["timestamp"])
    _, sizing, risk, execution = policies()
    clock = BarClockPolicy("start", timedelta(minutes=5), timedelta(seconds=1), timedelta(0))
    with pytest.raises(ValueError, match="next executable slice"):
        build_scenario(
            [bars],
            targets,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="causal-clock",
        )


def test_build_scenario_requires_exactly_one_target_mode_and_inputs() -> None:
    bars = execution_bars("asset-a", "AAA")
    targets = pd.DataFrame({"asset-a": [1.0, 1.0]}, index=bars.frame["timestamp"])
    clock, sizing, risk, execution = policies()
    instrument = ExecutionInstrument("asset-a", "AAA", "USD", "0.01")

    def build(
        selected_bars: list[BarSet],
        selected_targets: pd.DataFrame | None,
        *,
        quantities: pd.DataFrame | None = None,
        selected_instruments: list[ExecutionInstrument] | None = None,
    ) -> None:
        build_scenario(
            selected_bars,
            selected_targets,
            target_quantities=quantities,
            instruments=[instrument] if selected_instruments is None else selected_instruments,
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )

    with pytest.raises(ValueError, match="exactly one"):
        build([bars], None)
    with pytest.raises(ValueError, match="exactly one"):
        build([bars], targets, quantities=targets)
    with pytest.raises(ValueError, match="at least one BarSet"):
        build([], targets)
    with pytest.raises(ValueError, match="at least one execution instrument"):
        build([bars], targets, selected_instruments=[])
    with pytest.raises(TypeError, match="PortfolioConstructionResult or DataFrame"):
        build_scenario(
            [bars],
            cast("Any", object()),
            instruments=[instrument],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid",
        )


def test_build_scenario_validates_target_axes_and_alignment() -> None:
    bars = execution_bars("asset-a", "AAA")
    clock, sizing, risk, execution = policies()

    def build(frame: pd.DataFrame) -> None:
        build_scenario(
            [bars],
            frame,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid-targets",
        )

    valid = pd.DataFrame({"asset-a": [0.5, 0.5]}, index=bars.frame["timestamp"])
    with pytest.raises(ValueError, match="must not be empty"):
        build(valid.iloc[:0])
    with pytest.raises(TypeError, match="DatetimeIndex"):
        build(valid.reset_index(drop=True))
    naive = valid.copy()
    naive.index = pd.DatetimeIndex(naive.index).tz_localize(None)
    with pytest.raises(ValueError, match="timezone-aware"):
        build(naive)
    duplicated = pd.concat([valid.iloc[:1], valid.iloc[:1]])
    with pytest.raises(ValueError, match="unique and complete"):
        build(duplicated)
    reversed_targets = valid.iloc[::-1]
    with pytest.raises(ValueError, match="index must increase"):
        build(reversed_targets)
    duplicate_columns = pd.DataFrame(
        [[0.5, 0.5], [0.5, 0.5]],
        index=valid.index,
        columns=["asset-a", "asset-a"],
    )
    with pytest.raises(ValueError, match="columns must be unique"):
        build(duplicate_columns)
    wrong_identity = valid.rename(columns={"asset-a": "asset-b"})
    with pytest.raises(ValueError, match="instrument identities"):
        build(wrong_identity)
    missing_slice = valid.copy()
    missing_slice.index += pd.Timedelta(minutes=1)
    with pytest.raises(ValueError, match="synchronized market slice"):
        build(missing_slice)


def test_build_scenario_rejects_inconsistent_bar_sources_and_metadata() -> None:
    bars = execution_bars("asset-a", "AAA")
    targets = pd.DataFrame({"asset-a": [0.5, 0.5]}, index=bars.frame["timestamp"])
    clock, sizing, risk, execution = policies()

    def build(
        selected: list[BarSet],
        *,
        selected_targets: pd.DataFrame = targets,
        metadata: dict[object, object] | None = None,
    ) -> None:
        build_scenario(
            selected,
            selected_targets,
            instruments=[ExecutionInstrument("asset-a", "AAA", "USD", "0.01")],
            initial_cash=10_000,
            clock_policy=clock,
            sizing_policy=sizing,
            risk=risk,
            execution=execution,
            run_id="invalid-bars",
            metadata=cast("Any", metadata),
        )

    with pytest.raises(ValueError, match="one BarSet per instrument"):
        build([bars, bars])
    other = execution_bars("asset-b", "BBB")
    with pytest.raises(ValueError, match="identities must match"):
        build([other])
    empty = BarSet(bars.instrument, bars.frame.iloc[:0].copy(), bars.metadata)
    with pytest.raises(ValueError, match="must not be empty"):
        build([empty])
    currency_frame = bars.frame.copy()
    currency_frame["currency"] = pd.Series(["EUR"] * len(currency_frame), dtype="string")
    with pytest.raises(ValueError, match="bar currency"):
        build([BarSet(bars.instrument, currency_frame, bars.metadata)])
    position_frame = bars.frame.copy()
    position_frame["timestamp_position"] = pd.Series(["end"] * len(position_frame), dtype="string")
    with pytest.raises(ValueError, match="clock policy conflicts"):
        build([BarSet(bars.instrument, position_frame, bars.metadata)])
    unsupported_position = bars.frame.copy()
    unsupported_position["timestamp_position"] = pd.Series(
        ["unknown"] * len(unsupported_position), dtype="string"
    )
    with pytest.raises(ValueError, match="unsupported timestamp_position"):
        build([BarSet(bars.instrument, unsupported_position, bars.metadata)])
    with pytest.raises(ValueError, match=r"metadata\.persistra is reserved"):
        build([bars], metadata={"persistra": {}})
    with pytest.raises(ValueError, match="finite JSON numbers"):
        build([bars], metadata={"bad": float("inf")})
    with pytest.raises(TypeError, match="keys must be strings"):
        build([bars], metadata={1: "bad"})


def test_scenario_parser_rejects_noncanonical_and_malformed_documents() -> None:
    payload = json.loads(scenario_to_json(built_scenario()))
    with pytest.raises(ValueError, match="invalid scenario JSON"):
        scenario_from_json("{")
    with pytest.raises(ValueError, match="duplicate JSON field"):
        scenario_from_json('{"run_id":"a","run_id":"b"}')

    invalid = deepcopy(payload)
    del invalid["contract_version"]
    with pytest.raises(ValueError, match="scenario fields differ"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["contract_version"] = "2"
    with pytest.raises(ValueError, match="unsupported scenario contract_version"):
        scenario_from_json(json.dumps(invalid))

    invalid = deepcopy(payload)
    invalid["initial_cash"] = 10_000
    with pytest.raises(ValueError, match="exact decimal string"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["initial_cash"] = "10000.0"
    with pytest.raises(ValueError, match="canonical decimal"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["max_internal_events"] = "1000"
    with pytest.raises(ValueError, match="JSON integer"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["metadata"] = []
    with pytest.raises(ValueError, match="metadata must be a JSON object"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["schedule"][0]["intents"] = [None]
    with pytest.raises(ValueError, match="intent must be a JSON object"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["schedule"][0]["intents"] = [{"type": "emit_metric", "name": "signal", "value": 1}]
    with pytest.raises(ValueError, match="metric value"):
        scenario_from_json(json.dumps(invalid))
    invalid = deepcopy(payload)
    invalid["schedule"][0]["intents"] = [
        {
            "type": "submit_order",
            "instrument_id": "asset-a",
            "side": "hold",
            "quantity": "1",
            "order_kind": "market",
            "limit_price": None,
        }
    ]
    with pytest.raises(ValueError, match="unsupported side"):
        scenario_from_json(json.dumps(invalid))


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-01-02 14:30:00Z",
        "2026-01-02T14:30:00.0000001Z",
        "2026-01-02T14:30:00+0000",
        "2026-01-02T14:30:60Z",
    ],
)
def test_scenario_parser_requires_exact_rfc3339_timestamps(timestamp: str) -> None:
    payload = json.loads(scenario_to_json(built_scenario()))
    payload["slices"][0]["start_at"] = timestamp
    with pytest.raises(ValueError, match="RFC3339 syntax"):
        scenario_from_json(json.dumps(payload))


def test_scenario_parser_accepts_lowercase_rfc3339_separators() -> None:
    payload = json.loads(scenario_to_json(built_scenario()))
    payload["slices"][0]["start_at"] = "2026-01-02t14:30:00z"
    assert scenario_from_json(json.dumps(payload)).slices[0].start_at == pd.Timestamp(
        "2026-01-02T14:30:00Z"
    )


def test_scenario_json_accepts_compact_output_and_checks_indent() -> None:
    document = scenario_to_json(built_scenario(), indent=None)
    assert "\n " not in document
    with pytest.raises(ValueError, match="indent"):
        scenario_to_json(built_scenario(), indent=-1)
    with pytest.raises(ValueError, match="indent"):
        scenario_to_json(built_scenario(), indent=cast("Any", True))
