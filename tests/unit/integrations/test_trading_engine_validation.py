"""Boundary validation tests for exact engine values and typed models."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine._scalars import (
    INT64_MAX,
    decimal_string,
    decimal_value,
    exact_fields,
    identifier,
    metric_name,
    quantity_value,
)
from persistra.integrations.trading_engine.model import (
    BarClockPolicy,
    CancelOrderIntent,
    CashBalance,
    EmitMetricIntent,
    EngineCapabilities,
    ExecutionInstrument,
    ExecutionPolicy,
    FxRate,
    JournalEvent,
    MarketSlice,
    RiskPolicy,
    ScenarioBar,
    ScheduleItem,
    SizingPolicy,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetQuantity,
    TargetWeight,
    TargetWeightsIntent,
    TradingEngineScenario,
)


def engine_capabilities(**changes: Any) -> EngineCapabilities:
    """Construct a capability document while allowing one field to vary."""
    values: dict[str, Any] = {
        "engine_version": "test-engine-1",
        "scenario_contract_versions": ("3",),
        "journal_contract_versions": ("3",),
        "scenario_formats": ("json",),
        "journal_formats": ("jsonl",),
        "execution_models": ("completed_bar_v1",),
        "strategy_protocol_versions": ("2",),
    }
    values.update(changes)
    return EngineCapabilities(**values)


def test_engine_capabilities_require_nonempty_unique_tuples() -> None:
    assert engine_capabilities().scenario_contract_versions == ("3",)
    with pytest.raises(TypeError, match="must be a tuple"):
        engine_capabilities(scenario_formats=["json"])
    with pytest.raises(ValueError, match="must not be empty"):
        engine_capabilities(journal_formats=())
    with pytest.raises(ValueError, match="must not contain duplicates"):
        engine_capabilities(execution_models=("completed_bar_v1", "completed_bar_v1"))


def test_journal_event_rejects_an_unsupported_contract() -> None:
    with pytest.raises(ValueError, match="journal event contract_version"):
        JournalEvent(
            contract_version="2",
            event_id="test-event-000000000001",
            causation_ids=(),
            engine_sequence=1,
            run_id="test",
            recorded_at=pd.Timestamp("2026-01-02T00:00:00Z"),
            event_type="run_started",
            payload={},
        )


@pytest.mark.parametrize(
    ("value", "error", "message", "options"),
    [
        (True, TypeError, "decimal number", {}),
        (object(), TypeError, "decimal number", {}),
        (".", ValueError, "decimal number", {}),
        ("NaN", ValueError, "finite", {}),
        ("1.0000001", ValueError, "at most six", {}),
        (0, ValueError, "positive", {"positive": True}),
        (-1, ValueError, "nonnegative", {"nonnegative": True}),
        (Decimal(INT64_MAX) + 1, ValueError, "supported range", {}),
    ],
)
def test_decimal_value_rejects_unsupported_engine_values(
    value: object,
    error: type[Exception],
    message: str,
    options: dict[str, bool],
) -> None:
    with pytest.raises(error, match=message):
        decimal_value(value, name="value", **options)


def test_decimal_value_and_string_use_exact_canonical_micros() -> None:
    assert decimal_value(Decimal("1.250000"), name="value") == Decimal("1.250000")
    assert decimal_value(2.5, name="value") == Decimal("2.5")
    assert decimal_string(Decimal("1.250000")) == "1.25"
    assert decimal_string(Decimal("-0.000000")) == "0"


@pytest.mark.parametrize(
    ("value", "error", "message", "positive"),
    [
        (True, TypeError, "whole number", False),
        (Decimal("1.5"), ValueError, "whole number", False),
        (1.5, ValueError, "whole number", False),
        ("", ValueError, "whole number", False),
        ("no", ValueError, "whole number", False),
        ("01", ValueError, "canonical", False),
        (object(), TypeError, "whole number", False),
        (-1, ValueError, "nonnegative", False),
        (0, ValueError, "positive", True),
        (INT64_MAX + 1, ValueError, "supported range", False),
    ],
)
def test_quantity_value_rejects_unsupported_engine_values(
    value: object,
    error: type[Exception],
    message: str,
    positive: bool,
) -> None:
    with pytest.raises(error, match=message):
        quantity_value(value, name="quantity", positive=positive)


def test_quantity_value_accepts_integral_decimal_float_and_string() -> None:
    assert quantity_value(Decimal(2), name="quantity") == 2
    assert quantity_value(3.0, name="quantity") == 3
    assert quantity_value("4", name="quantity") == 4


@pytest.mark.parametrize(
    ("value", "error", "message"),
    [
        (1, TypeError, "string"),
        (" padded", ValueError, "empty or padded"),
        ("line\nbreak", ValueError, "whitespace or control"),
    ],
)
def test_identifier_rejects_nonportable_values(
    value: object,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        identifier(value, name="identifier")


def test_exact_fields_requires_an_exact_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        exact_fields([], {"value"}, name="item")
    with pytest.raises(ValueError, match=r"missing=.*value.*extra=.*other"):
        exact_fields({"other": 1}, {"value"}, name="item")


def valid_bar() -> ScenarioBar:
    """Return a directly constructed valid exact bar."""
    return ScenarioBar(
        instrument_id="asset-a",
        open=Decimal("99"),
        high=Decimal("101"),
        low=Decimal("98"),
        close=Decimal("100"),
        volume=Decimal(100),
    )


def valid_risk(
    *,
    max_order_quantity: int = 100,
    max_long_position: int = 100,
    max_short_position: int = 100,
    max_leverage: int = 2,
) -> RiskPolicy:
    """Return a complete v3 risk policy for direct model tests."""
    return RiskPolicy(
        max_order_quantity=max_order_quantity,
        max_long_position=max_long_position,
        max_short_position=max_short_position,
        max_gross_exposure=1_000_000,
        max_leverage=max_leverage,
        initial_margin_bps=5_000,
        maintenance_margin_bps=2_500,
        short_borrow_bps=0,
    )


def test_policy_models_reject_each_unsupported_setting() -> None:
    with pytest.raises(ValueError, match="start or end"):
        BarClockPolicy(cast("Any", "middle"), timedelta(1), timedelta(0), timedelta(0))
    with pytest.raises(ValueError, match="availability_delay"):
        BarClockPolicy("start", timedelta(1), timedelta(microseconds=-1), timedelta(0))
    with pytest.raises(ValueError, match="receipt_delay"):
        BarClockPolicy("start", timedelta(1), timedelta(0), timedelta(microseconds=-1))
    with pytest.raises(ValueError, match="bar_duration"):
        BarClockPolicy("start", timedelta(0), timedelta(0), timedelta(0))
    with pytest.raises(ValueError, match="current_marked_equity"):
        SizingPolicy(equity_basis=cast("Any", "initial_cash"))
    with pytest.raises(ValueError, match="decision_close"):
        SizingPolicy(reference_price=cast("Any", "open"))
    with pytest.raises(ValueError, match="down_to_lot"):
        SizingPolicy(quantity_rounding=cast("Any", "nearest"))
    with pytest.raises(ValueError, match="fee_bps"):
        ExecutionPolicy(participation_bps=1, fee_bps=10_001)
    with pytest.raises(ValueError, match="participation_bps"):
        ExecutionPolicy(participation_bps=10_001)
    with pytest.raises(ValueError, match="completed_bar_v1"):
        ExecutionPolicy(participation_bps=1, model=cast("Any", "future_model"))
    with pytest.raises(ValueError, match="nonnegative"):
        ExecutionPolicy(participation_bps=1, fixed_fee=-1)


def test_bar_slice_and_target_models_enforce_exact_causal_values() -> None:
    bar = valid_bar()
    assert bar.volume == 100
    with pytest.raises(ValueError, match="OHLC"):
        replace(bar, low=Decimal("100.5"))
    with pytest.raises(ValueError, match="nonnegative"):
        replace(bar, volume=-1)
    market_slice = MarketSlice(
        1,
        pd.Timestamp("2026-01-02T14:30:00Z"),
        pd.Timestamp("2026-01-02T14:35:00Z"),
        pd.Timestamp("2026-01-02T14:35:00Z"),
        pd.Timestamp("2026-01-02T14:35:00Z"),
        (bar,),
        (FxRate("USD", 1),),
    )
    with pytest.raises(ValueError, match="slice timestamps"):
        replace(market_slice, end_at=market_slice.start_at)
    with pytest.raises(TypeError, match="pandas Timestamp"):
        replace(market_slice, start_at=cast("Any", "not-a-timestamp"))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(market_slice, start_at=pd.Timestamp("2026-01-02T14:30:00"))
    with pytest.raises(ValueError, match="microsecond precision"):
        replace(market_slice, start_at=pd.Timestamp("2026-01-02T14:30:00.000000001Z"))
    with pytest.raises(ValueError, match="at least one bar"):
        replace(market_slice, bars=())
    with pytest.raises(ValueError, match="exactly once"):
        replace(market_slice, bars=(bar, bar))
    assert TargetWeight("asset-a", "-1.000001").weight == Decimal("-1.000001")

    instrument = ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size=2)
    with pytest.raises(ValueError, match="max_long_position"):
        TradingEngineScenario(
            run_id="invalid",
            base_currency="USD",
            initial_cash=(CashBalance("USD", 100),),
            instruments=(instrument,),
            risk=valid_risk(max_order_quantity=10, max_long_position=10),
            execution=ExecutionPolicy(10_000),
            max_internal_events=10,
            metadata={},
            schedule=(
                ScheduleItem(
                    1,
                    (TargetQuantitiesIntent((TargetQuantity("asset-a", 12),)),),
                ),
            ),
            slices=(market_slice,),
        )


@pytest.mark.parametrize(
    ("intent", "message"),
    [
        (
            lambda: SubmitOrderIntent("asset-a", cast("Any", "hold"), 1, "market"),
            "side must be",
        ),
        (
            lambda: SubmitOrderIntent("asset-a", "buy", 1, cast("Any", "stop")),
            "order_kind must be",
        ),
        (
            lambda: SubmitOrderIntent("asset-a", "buy", 1, "limit"),
            "require limit_price",
        ),
        (
            lambda: SubmitOrderIntent("asset-a", "buy", 1, "market", "1"),
            "market orders require null",
        ),
    ],
)
def test_direct_intent_models_reject_ambiguous_orders(intent: Any, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        intent()
    with pytest.raises(TypeError, match="metric value"):
        EmitMetricIntent("signal", cast("Any", 1))
    with pytest.raises(TypeError, match="metric name"):
        EmitMetricIntent(cast("Any", 1), "1")
    assert EmitMetricIntent("daily signal", "1").name == "daily signal"
    assert EmitMetricIntent(" signal", "1").name == " signal"
    assert EmitMetricIntent("", "1").name == ""
    with pytest.raises(TypeError, match="metric name"):
        metric_name(1)
    with pytest.raises(ValueError, match="nonempty and trimmed"):
        metric_name(" padded")
    assert metric_name("\vsignal\N{NO-BREAK SPACE}") == "\vsignal\N{NO-BREAK SPACE}"


def scenario_parts() -> tuple[ExecutionInstrument, MarketSlice]:
    """Return one instrument and one aligned slice for direct model tests."""
    bar = valid_bar()
    return (
        ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size=2),
        MarketSlice(
            1,
            pd.Timestamp("2026-01-02T14:30:00Z"),
            pd.Timestamp("2026-01-02T14:35:00Z"),
            pd.Timestamp("2026-01-02T14:35:00Z"),
            pd.Timestamp("2026-01-02T14:35:00Z"),
            (bar,),
            (FxRate("USD", 1),),
        ),
    )


def direct_scenario(**changes: Any) -> TradingEngineScenario:
    """Construct a scenario while allowing one invariant to be changed."""
    instrument, market_slice = scenario_parts()
    values: dict[str, Any] = {
        "run_id": "direct-validation",
        "base_currency": "USD",
        "initial_cash": (CashBalance("USD", 1000),),
        "instruments": (instrument,),
        "risk": valid_risk(),
        "execution": ExecutionPolicy(10_000),
        "max_internal_events": 100,
        "metadata": {},
        "schedule": (),
        "slices": (market_slice,),
    }
    values.update(changes)
    return TradingEngineScenario(**values)


def test_scenario_models_copy_collection_inputs() -> None:
    instrument, market_slice = scenario_parts()
    targets = [TargetQuantity("asset-a", 2)]
    target_intent = TargetQuantitiesIntent(cast("Any", targets))
    intents = [target_intent]
    schedule_item = ScheduleItem(1, cast("Any", intents))
    cash = [CashBalance("USD", 1000)]
    instruments = [instrument]
    schedule = [schedule_item]
    slices = [market_slice]
    scenario = TradingEngineScenario(
        run_id="copied-collections",
        base_currency="USD",
        initial_cash=cast("Any", cash),
        instruments=cast("Any", instruments),
        risk=valid_risk(),
        execution=ExecutionPolicy(10_000),
        max_internal_events=100,
        metadata={},
        schedule=cast("Any", schedule),
        slices=cast("Any", slices),
    )

    targets.clear()
    intents.clear()
    cash.clear()
    instruments.clear()
    schedule.clear()
    slices.clear()

    assert len(target_intent.targets) == 1
    assert len(schedule_item.intents) == 1
    assert len(scenario.initial_cash) == 1
    assert len(scenario.instruments) == 1
    assert len(scenario.schedule) == 1
    assert len(scenario.slices) == 1


def test_scenario_model_rejects_cross_field_configuration_errors() -> None:
    instrument, market_slice = scenario_parts()
    with pytest.raises(ValueError, match="supported engine range"):
        direct_scenario(max_internal_events=1 << 62)
    with pytest.raises(ValueError, match="at least one execution instrument"):
        direct_scenario(instruments=())
    with pytest.raises(TypeError, match="metadata must be a mapping"):
        direct_scenario(metadata=cast("Any", []))
    with pytest.raises(ValueError, match="identifiers must be unique"):
        direct_scenario(instruments=(instrument, instrument))
    with pytest.raises(ValueError, match="initial_cash must contain every scenario currency"):
        direct_scenario(instruments=(replace(instrument, quote_currency="EUR"),))
    with pytest.raises(ValueError, match="risk quantity limits"):
        direct_scenario(
            risk=valid_risk(
                max_order_quantity=1,
                max_long_position=1,
                max_short_position=1,
            )
        )
    with pytest.raises(ValueError, match="cover all scenario instruments"):
        direct_scenario(
            slices=(replace(market_slice, bars=(replace(valid_bar(), instrument_id="b"),)),)
        )
    with pytest.raises(ValueError, match="tick size"):
        direct_scenario(
            slices=(replace(market_slice, bars=(replace(valid_bar(), close=Decimal("100.005")),)),)
        )
    with pytest.raises(TypeError, match="metadata keys"):
        direct_scenario(metadata=cast("Any", {1: "value"}))
    with pytest.raises(TypeError, match="JSON-compatible"):
        direct_scenario(metadata={"value": Decimal("1")})


def test_scenario_model_enforces_slice_and_schedule_progress() -> None:
    _instrument, first = scenario_parts()
    second = MarketSlice(
        2,
        pd.Timestamp("2026-01-02T14:40:00Z"),
        pd.Timestamp("2026-01-02T14:45:00Z"),
        pd.Timestamp("2026-01-02T14:45:00Z"),
        pd.Timestamp("2026-01-02T14:45:00Z"),
        (valid_bar(),),
        (FxRate("USD", 1),),
    )
    with pytest.raises(ValueError, match="slice_sequence"):
        direct_scenario(slices=(first, replace(second, slice_sequence=1)))
    earlier = replace(
        second,
        start_at=pd.Timestamp("2026-01-02T14:20:00Z"),
        end_at=pd.Timestamp("2026-01-02T14:25:00Z"),
        available_at=pd.Timestamp("2026-01-02T14:25:00Z"),
        received_at=pd.Timestamp("2026-01-02T14:25:00Z"),
    )
    with pytest.raises(ValueError, match="end_at must increase"):
        direct_scenario(slices=(first, earlier))
    delayed_first = replace(first, received_at=pd.Timestamp("2026-01-02T14:50:00Z"))
    with pytest.raises(ValueError, match="received_at"):
        direct_scenario(slices=(delayed_first, second))
    with pytest.raises(ValueError, match="schedule after_slice_sequence"):
        direct_scenario(
            schedule=(ScheduleItem(1, ()), ScheduleItem(1, ())),
            slices=(first, second),
        )
    with pytest.raises(ValueError, match="missing market slice"):
        direct_scenario(schedule=(ScheduleItem(2, ()),))

    late = replace(first, received_at=pd.Timestamp("2026-01-02T14:42:00Z"))
    scenario = direct_scenario(
        schedule=(
            ScheduleItem(
                1,
                (EmitMetricIntent("signal", "1"),),
            ),
        ),
        slices=(late, second),
    )
    assert scenario.schedule[0].after_slice_sequence == 1
    with pytest.raises(ValueError, match="next executable slice"):
        direct_scenario(
            schedule=(ScheduleItem(1, (CancelOrderIntent("order-1"),)),),
            slices=(late, second),
        )


def test_scenario_model_validates_all_order_producing_intents() -> None:
    instrument, market_slice = scenario_parts()
    second = replace(instrument, instrument_id="asset-b", symbol="BBB")
    second_bar = replace(valid_bar(), instrument_id="asset-b")
    two_instrument_slice = replace(market_slice, bars=(valid_bar(), second_bar))
    common = {
        "instruments": (instrument, second),
        "slices": (two_instrument_slice,),
    }
    with pytest.raises(ValueError, match="target weights must cover"):
        direct_scenario(
            **common,
            schedule=(ScheduleItem(1, (TargetWeightsIntent((TargetWeight("asset-a", "0.5"),)),)),),
        )
    with pytest.raises(ValueError, match="maximum leverage"):
        direct_scenario(
            **common,
            schedule=(
                ScheduleItem(
                    1,
                    (
                        TargetWeightsIntent(
                            (TargetWeight("asset-a", "1.1"), TargetWeight("asset-b", "1.1"))
                        ),
                    ),
                ),
            ),
        )
    with pytest.raises(ValueError, match="unknown instrument"):
        direct_scenario(
            schedule=(ScheduleItem(1, (SubmitOrderIntent("missing", "buy", 2, "market"),)),)
        )
    with pytest.raises(ValueError, match="lot size"):
        direct_scenario(
            schedule=(ScheduleItem(1, (SubmitOrderIntent("asset-a", "buy", 3, "market"),)),)
        )
    with pytest.raises(ValueError, match="max_order_quantity"):
        direct_scenario(
            risk=valid_risk(max_order_quantity=2),
            schedule=(ScheduleItem(1, (SubmitOrderIntent("asset-a", "buy", 4, "market"),)),),
        )
    with pytest.raises(ValueError, match="tick size"):
        direct_scenario(
            schedule=(ScheduleItem(1, (SubmitOrderIntent("asset-a", "buy", 2, "limit", "1.005"),)),)
        )
    with pytest.raises(ValueError, match="finite"):
        TradingEngineScenario(
            run_id="invalid",
            base_currency="USD",
            initial_cash=(CashBalance("USD", 100),),
            instruments=(instrument,),
            risk=valid_risk(max_order_quantity=10, max_long_position=10),
            execution=ExecutionPolicy(10_000),
            max_internal_events=10,
            metadata={"bad": float("nan")},
            schedule=(),
            slices=(market_slice,),
        )
