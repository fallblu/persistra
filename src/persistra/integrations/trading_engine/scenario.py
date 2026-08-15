"""Build and serialize version 1 trading-engine scenarios."""

from __future__ import annotations

import json
import math
import re
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import (
    decimal_micros,
    decimal_string,
    decimal_value,
    exact_fields,
    identifier,
    quantity_value,
)
from persistra.integrations.trading_engine.model import (
    BarClockPolicy,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    ScenarioBar,
    SizingPolicy,
    TargetDecision,
    TradingEngineScenario,
)
from persistra.portfolio import PortfolioConstructionResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.model import BarSet

_INTERVAL = re.compile(r"([1-9][0-9]*)min")
_SCENARIO_FIELDS = {
    "schema_version",
    "run_id",
    "base_currency",
    "initial_cash",
    "instruments",
    "risk",
    "execution",
    "max_internal_events",
    "schedule",
    "bars",
}

type _PendingBar = tuple[
    str,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    pd.Timestamp,
    Decimal,
    Decimal,
    Decimal,
    Decimal,
    int | None,
]


def build_scenario(
    bars: Sequence[BarSet],
    targets: PortfolioConstructionResult | pd.DataFrame | None = None,
    *,
    target_quantities: pd.DataFrame | None = None,
    instruments: Sequence[ExecutionInstrument],
    initial_cash: Decimal | str | int | float,
    clock_policy: BarClockPolicy,
    sizing_policy: SizingPolicy,
    risk: RiskPolicy,
    execution: ExecutionPolicy,
    run_id: str,
    max_internal_events: int = 1_000,
) -> TradingEngineScenario:
    """Build a deterministic long-only scenario from raw intraday bars and targets."""
    if (targets is None) == (target_quantities is None):
        raise ValueError("provide exactly one of targets or target_quantities")
    if not bars:
        raise ValueError("bars must contain at least one BarSet")
    if not instruments:
        raise ValueError("instruments must contain at least one execution instrument")
    checked_run_id = identifier(run_id, name="run_id")
    checked_cash = decimal_value(initial_cash, name="initial_cash", nonnegative=True)
    checked_events = quantity_value(
        max_internal_events,
        name="max_internal_events",
        positive=True,
    )
    execution_instruments = tuple(sorted(instruments, key=lambda item: item.instrument_id))
    _require_unique_instruments(execution_instruments)
    base_currencies = {item.quote_currency for item in execution_instruments}
    if len(base_currencies) != 1:
        raise ValueError("all execution instruments must use one quote currency")
    base_currency = next(iter(base_currencies))
    scenario_bars = _build_bars(
        bars,
        instruments=execution_instruments,
        base_currency=base_currency,
        clock_policy=clock_policy,
    )
    target_frame, weights = _target_frame(targets, target_quantities)
    decisions = _build_decisions(
        target_frame,
        weights=weights,
        bars=scenario_bars,
        instruments=execution_instruments,
        initial_cash=checked_cash,
        sizing_policy=sizing_policy,
    )
    return TradingEngineScenario(
        run_id=checked_run_id,
        base_currency=base_currency,
        initial_cash=checked_cash,
        instruments=execution_instruments,
        risk=risk,
        execution=execution,
        max_internal_events=checked_events,
        bars=scenario_bars,
        decisions=decisions,
    )


def scenario_to_json(scenario: TradingEngineScenario, *, indent: int | None = 2) -> str:
    """Serialize a scenario as stable UTF-8-compatible version 1 JSON."""
    if indent is not None and (isinstance(indent, bool) or indent < 0):
        raise ValueError("indent must be nonnegative or None")
    document = json.dumps(
        _scenario_dictionary(scenario),
        allow_nan=False,
        indent=indent,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
    )
    return f"{document}\n"


def scenario_from_json(document: str) -> TradingEngineScenario:
    """Parse the supported target-position subset of scenario version 1 JSON."""
    try:
        raw = json.loads(document, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid scenario JSON: {error.msg}") from error
    payload = exact_fields(raw, _SCENARIO_FIELDS, name="scenario")
    version = _integer(payload["schema_version"], name="schema_version", positive=True)
    if version != 1:
        raise ValueError("unsupported scenario schema_version")
    run_id = identifier(payload["run_id"], name="run_id")
    base_currency = identifier(payload["base_currency"], name="base_currency")
    initial_cash = decimal_value(payload["initial_cash"], name="initial_cash", nonnegative=True)
    max_events = _integer(
        payload["max_internal_events"],
        name="max_internal_events",
        positive=True,
    )
    instrument_items = _array(payload["instruments"], name="instruments")
    instruments = tuple(_instrument_from_json(item) for item in instrument_items)
    if not instruments:
        raise ValueError("scenario must define at least one instrument")
    _require_unique_instruments(instruments)
    if any(item.quote_currency != base_currency for item in instruments):
        raise ValueError("every instrument quote currency must match base_currency")
    risk = _risk_from_json(payload["risk"])
    execution = _execution_from_json(payload["execution"])
    bars = tuple(_bar_from_json(item) for item in _array(payload["bars"], name="bars"))
    decisions = _decisions_from_json(payload["schedule"], bars, instruments)
    return TradingEngineScenario(
        run_id=run_id,
        base_currency=base_currency,
        initial_cash=initial_cash,
        instruments=instruments,
        risk=risk,
        execution=execution,
        max_internal_events=max_events,
        bars=bars,
        decisions=decisions,
        schema_version=version,
    )


def write_scenario(
    scenario: TradingEngineScenario,
    path: str | Path,
    *,
    indent: int | None = 2,
    overwrite: bool = False,
) -> Path:
    """Write a stable scenario document without silently replacing an artifact."""
    output = Path(path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with output.open(mode, encoding="utf-8", newline="\n") as stream:
        stream.write(scenario_to_json(scenario, indent=indent))
    return output


def read_scenario(path: str | Path) -> TradingEngineScenario:
    """Read and validate the supported version 1 scenario profile."""
    return scenario_from_json(Path(path).expanduser().read_text(encoding="utf-8"))


def _build_bars(
    bar_sets: Sequence[BarSet],
    *,
    instruments: tuple[ExecutionInstrument, ...],
    base_currency: str,
    clock_policy: BarClockPolicy,
) -> tuple[ScenarioBar, ...]:
    instrument_by_id = {item.instrument_id: item for item in instruments}
    bar_ids = [item.instrument.instrument_id for item in bar_sets]
    if len(set(bar_ids)) != len(bar_ids):
        raise ValueError("bars must contain one BarSet per instrument")
    if set(bar_ids) != set(instrument_by_id):
        raise ValueError("bar and execution instrument identities must match exactly")
    pending: list[_PendingBar] = []
    expected_duration = pd.Timedelta(clock_policy.bar_duration)
    for bar_set in bar_sets:
        frame = bar_set.frame
        if frame.empty:
            raise ValueError(f"bars for {bar_set.instrument.instrument_id} must not be empty")
        if set(frame["price_adjustment"].astype(str)) != {"raw"}:
            raise ValueError("execution scenarios require raw, unadjusted bars")
        if set(frame["currency"].astype(str)) != {base_currency}:
            raise ValueError("every bar currency must match the scenario base currency")
        if frame["date"].notna().any() or frame["timestamp"].isna().any():
            raise ValueError("the initial execution profile supports intraday bars only")
        instrument = instrument_by_id[bar_set.instrument.instrument_id]
        for _row_index, row in frame.iterrows():
            interval = str(row["interval"])
            match = _INTERVAL.fullmatch(interval)
            if match is None:
                raise ValueError(f"unsupported intraday interval: {interval}")
            if pd.Timedelta(minutes=int(match.group(1))) != expected_duration:
                raise ValueError("bar_duration must match every normalized bar interval")
            normalized_position = str(row["timestamp_position"])
            if normalized_position in {"start", "end"}:
                if normalized_position != clock_policy.source_timestamp_position:
                    raise ValueError("clock policy conflicts with normalized timestamp_position")
            elif normalized_position != "provider_label":
                raise ValueError(f"unsupported timestamp_position: {normalized_position}")
            source_timestamp = _timestamp(row["timestamp"], name="bar timestamp")
            if clock_policy.source_timestamp_position == "start":
                start_at = source_timestamp
                end_at = source_timestamp + expected_duration
            else:
                start_at = source_timestamp - expected_duration
                end_at = source_timestamp
            available_at = end_at + pd.Timedelta(clock_policy.availability_delay)
            received_at = available_at + pd.Timedelta(clock_policy.receipt_delay)
            open_price = decimal_value(row["open"], name="bar open", positive=True)
            high_price = decimal_value(row["high"], name="bar high", positive=True)
            low_price = decimal_value(row["low"], name="bar low", positive=True)
            close_price = decimal_value(row["close"], name="bar close", positive=True)
            prices = (open_price, high_price, low_price, close_price)
            for name, price in zip(
                ("open", "high", "low", "close"), prices, strict=True
            ):
                if decimal_micros(price) % decimal_micros(cast("Decimal", instrument.tick_size)):
                    raise ValueError(
                        f"bar {name} for {instrument.instrument_id} is not tick aligned"
                    )
            volume = _optional_quantity(row["volume"], name="bar volume")
            pending.append(
                (
                    instrument.instrument_id,
                    source_timestamp,
                    start_at,
                    end_at,
                    available_at,
                    received_at,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume,
                )
            )
    pending.sort(key=lambda item: (item[5], item[3], item[0], item[1]))
    result: list[ScenarioBar] = []
    previous_by_instrument: dict[str, pd.Timestamp] = {}
    for source_sequence, item in enumerate(pending, start=1):
        (
            instrument_id,
            source_timestamp,
            start_at,
            end_at,
            available_at,
            received_at,
            open_price,
            high_price,
            low_price,
            close_price,
            volume,
        ) = item
        previous_end = previous_by_instrument.get(instrument_id)
        if previous_end is not None and end_at <= previous_end:
            raise ValueError("each instrument's bar end must increase")
        previous_by_instrument[instrument_id] = end_at
        result.append(
            ScenarioBar(
                source_sequence=source_sequence,
                instrument_id=instrument_id,
                source_timestamp=source_timestamp,
                start_at=start_at,
                end_at=end_at,
                available_at=available_at,
                received_at=received_at,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
    return tuple(result)


def _target_frame(
    targets: PortfolioConstructionResult | pd.DataFrame | None,
    target_quantities: pd.DataFrame | None,
) -> tuple[pd.DataFrame, bool]:
    if target_quantities is not None:
        return _validate_target_axes(target_quantities, name="target_quantities"), False
    if isinstance(targets, PortfolioConstructionResult):
        return _validate_target_axes(targets.weights, name="targets.weights"), True
    if isinstance(targets, pd.DataFrame):
        return _validate_target_axes(targets, name="targets"), True
    raise TypeError("targets must be a PortfolioConstructionResult or DataFrame")


def _validate_target_axes(frame: pd.DataFrame, *, name: str) -> pd.DataFrame:
    result = frame.copy(deep=True)
    if result.empty:
        raise ValueError(f"{name} must not be empty")
    if not isinstance(result.index, pd.DatetimeIndex):
        raise TypeError(f"{name} must use a DatetimeIndex")
    if result.index.tz is None:
        raise ValueError(f"{name} index must be timezone-aware")
    if result.index.hasnans or result.index.has_duplicates:
        raise ValueError(f"{name} index must be unique and complete")
    if not result.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must increase")
    if result.columns.has_duplicates:
        raise ValueError(f"{name} columns must be unique instrument identifiers")
    result.index = result.index.tz_convert("UTC")
    return result


def _build_decisions(
    target_frame: pd.DataFrame,
    *,
    weights: bool,
    bars: tuple[ScenarioBar, ...],
    instruments: tuple[ExecutionInstrument, ...],
    initial_cash: Decimal,
    sizing_policy: SizingPolicy,
) -> tuple[TargetDecision, ...]:
    del sizing_policy  # The checked policy documents the only supported conversion.
    instrument_by_id = {item.instrument_id: item for item in instruments}
    if set(target_frame.columns) != set(instrument_by_id):
        raise ValueError("target and execution instrument identities must match exactly")
    bars_by_label: dict[pd.Timestamp, dict[str, ScenarioBar]] = {}
    for bar in bars:
        bars_by_label.setdefault(bar.source_timestamp, {})[bar.instrument_id] = bar
    decisions: list[TargetDecision] = []
    for label, row in target_frame.iterrows():
        timestamp = _timestamp(label, name="target timestamp")
        period_bars = bars_by_label.get(timestamp)
        if period_bars is None or set(period_bars) != set(instrument_by_id):
            raise ValueError("each target timestamp requires same-period bars for every instrument")
        anchor = max(item.source_sequence for item in period_bars.values())
        decision_at = max(item.received_at for item in period_bars.values())
        if weights:
            checked_weights = {
                instrument_id: _weight(row[instrument_id], name=f"weight {instrument_id}")
                for instrument_id in sorted(instrument_by_id)
            }
            if math.fsum(checked_weights.values()) > 1.0 + 1e-12:
                raise ValueError("long-only target weights must sum to at most one")
        else:
            checked_weights = {}
        for instrument_id in sorted(instrument_by_id):
            reference_close = period_bars[instrument_id].close
            instrument = instrument_by_id[instrument_id]
            target_weight: float | None
            if weights:
                target_weight = checked_weights[instrument_id]
                raw_quantity = initial_cash * Decimal(str(target_weight)) / reference_close
                lots = (raw_quantity / instrument.lot_size).to_integral_value(rounding=ROUND_FLOOR)
                quantity = int(lots) * instrument.lot_size
            else:
                target_weight = None
                quantity = quantity_value(row[instrument_id], name=f"quantity {instrument_id}")
                if quantity % instrument.lot_size:
                    raise ValueError(f"target quantity for {instrument_id} is not lot aligned")
            decisions.append(
                TargetDecision(
                    after_bar_sequence=anchor,
                    decision_at=decision_at,
                    instrument_id=instrument_id,
                    quantity=quantity,
                    reference_close=reference_close,
                    target_weight=target_weight,
                )
            )
    return tuple(decisions)


def _scenario_dictionary(scenario: TradingEngineScenario) -> dict[str, object]:
    schedule: list[dict[str, object]] = []
    grouped: dict[int, list[TargetDecision]] = {}
    for decision in scenario.decisions:
        grouped.setdefault(decision.after_bar_sequence, []).append(decision)
    for sequence, decisions in grouped.items():
        schedule.append(
            {
                "after_bar_sequence": str(sequence),
                "intents": [
                    {
                        "type": "target_position",
                        "instrument_id": item.instrument_id,
                        "quantity": str(item.quantity),
                    }
                    for item in decisions
                ],
            }
        )
    return {
        "schema_version": scenario.schema_version,
        "run_id": scenario.run_id,
        "base_currency": scenario.base_currency,
        "initial_cash": decimal_string(scenario.initial_cash),
        "instruments": [
            {
                "instrument_id": item.instrument_id,
                "symbol": item.symbol,
                "quote_currency": item.quote_currency,
                "tick_size": decimal_string(cast("Decimal", item.tick_size)),
                "lot_size": str(item.lot_size),
            }
            for item in scenario.instruments
        ],
        "risk": {
            "max_order_quantity": str(scenario.risk.max_order_quantity),
            "max_position": str(scenario.risk.max_position),
        },
        "execution": {
            "participation_bps": scenario.execution.participation_bps,
            "fixed_fee": decimal_string(cast("Decimal", scenario.execution.fixed_fee)),
            "fee_bps": scenario.execution.fee_bps,
        },
        "max_internal_events": scenario.max_internal_events,
        "schedule": schedule,
        "bars": [
            {
                "source_sequence": str(item.source_sequence),
                "instrument_id": item.instrument_id,
                "start_at": _timestamp_string(item.start_at),
                "end_at": _timestamp_string(item.end_at),
                "available_at": _timestamp_string(item.available_at),
                "received_at": _timestamp_string(item.received_at),
                "open": decimal_string(item.open),
                "high": decimal_string(item.high),
                "low": decimal_string(item.low),
                "close": decimal_string(item.close),
                "volume": None if item.volume is None else str(item.volume),
            }
            for item in scenario.bars
        ],
    }


def _instrument_from_json(value: object) -> ExecutionInstrument:
    item = exact_fields(
        value,
        {"instrument_id", "symbol", "quote_currency", "tick_size", "lot_size"},
        name="instrument",
    )
    return ExecutionInstrument(
        instrument_id=item["instrument_id"],
        symbol=item["symbol"],
        quote_currency=item["quote_currency"],
        tick_size=item["tick_size"],
        lot_size=quantity_value(item["lot_size"], name="lot_size", positive=True),
    )


def _risk_from_json(value: object) -> RiskPolicy:
    item = exact_fields(value, {"max_order_quantity", "max_position"}, name="risk")
    return RiskPolicy(
        max_order_quantity=quantity_value(
            item["max_order_quantity"], name="max_order_quantity", positive=True
        ),
        max_position=quantity_value(item["max_position"], name="max_position", positive=True),
    )


def _execution_from_json(value: object) -> ExecutionPolicy:
    item = exact_fields(value, {"participation_bps", "fixed_fee", "fee_bps"}, name="execution")
    return ExecutionPolicy(
        participation_bps=_integer(item["participation_bps"], name="participation_bps"),
        fixed_fee=item["fixed_fee"],
        fee_bps=_integer(item["fee_bps"], name="fee_bps"),
    )


def _bar_from_json(value: object) -> ScenarioBar:
    item = exact_fields(
        value,
        {
            "source_sequence",
            "instrument_id",
            "start_at",
            "end_at",
            "available_at",
            "received_at",
            "open",
            "high",
            "low",
            "close",
            "volume",
        },
        name="bar",
    )
    end_at = _timestamp(item["end_at"], name="end_at")
    return ScenarioBar(
        source_sequence=quantity_value(item["source_sequence"], name="source_sequence"),
        instrument_id=identifier(item["instrument_id"], name="instrument_id"),
        source_timestamp=end_at,
        start_at=_timestamp(item["start_at"], name="start_at"),
        end_at=end_at,
        available_at=_timestamp(item["available_at"], name="available_at"),
        received_at=_timestamp(item["received_at"], name="received_at"),
        open=decimal_value(item["open"], name="open", positive=True),
        high=decimal_value(item["high"], name="high", positive=True),
        low=decimal_value(item["low"], name="low", positive=True),
        close=decimal_value(item["close"], name="close", positive=True),
        volume=None if item["volume"] is None else quantity_value(item["volume"], name="volume"),
    )


def _decisions_from_json(
    value: object,
    bars: tuple[ScenarioBar, ...],
    instruments: tuple[ExecutionInstrument, ...],
) -> tuple[TargetDecision, ...]:
    schedules = _array(value, name="schedule")
    bars_by_sequence = {item.source_sequence: item for item in bars}
    instrument_ids = {item.instrument_id for item in instruments}
    decisions: list[TargetDecision] = []
    for raw_schedule in schedules:
        schedule = exact_fields(
            raw_schedule,
            {"after_bar_sequence", "intents"},
            name="schedule item",
        )
        sequence = quantity_value(
            schedule["after_bar_sequence"],
            name="after_bar_sequence",
        )
        anchor = bars_by_sequence.get(sequence)
        intents = _array(schedule["intents"], name="intents")
        if intents and anchor is None:
            raise ValueError("scheduled intents refer to a missing bar source sequence")
        for raw_intent in intents:
            if not isinstance(raw_intent, dict):
                raise ValueError("intent must be a JSON object")
            intent_object = cast("dict[str, object]", raw_intent)
            intent_type = intent_object.get("type")
            if intent_type != "target_position":
                raise ValueError(
                    "the Persistra integration supports target_position intents only"
                )
            intent = exact_fields(
                intent_object,
                {"type", "instrument_id", "quantity"},
                name="target_position intent",
            )
            instrument_id = identifier(intent["instrument_id"], name="instrument_id")
            if instrument_id not in instrument_ids:
                raise ValueError("target_position refers to an unknown instrument")
            eligible_bars = [
                item
                for item in bars
                if item.source_sequence <= sequence and item.instrument_id == instrument_id
            ]
            if not eligible_bars or anchor is None:
                raise ValueError("target_position has no causal reference bar")
            reference = max(eligible_bars, key=lambda item: item.source_sequence)
            decisions.append(
                TargetDecision(
                    after_bar_sequence=sequence,
                    decision_at=anchor.received_at,
                    instrument_id=instrument_id,
                    quantity=quantity_value(intent["quantity"], name="quantity"),
                    reference_close=reference.close,
                )
            )
    return tuple(decisions)


def _require_unique_instruments(instruments: Sequence[ExecutionInstrument]) -> None:
    identities = [item.instrument_id for item in instruments]
    if len(set(identities)) != len(identities):
        raise ValueError("execution instrument identifiers must be unique")


def _weight(value: object, *, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be numeric")
    if isinstance(value, (Decimal, int, float, str)):
        try:
            result = float(value)
        except ValueError as error:
            raise TypeError(f"{name} must be numeric") from error
    else:
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if result < 0:
        raise ValueError("the initial execution profile is long-only")
    return result


def _optional_quantity(value: object, *, name: str) -> int | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return quantity_value(value, name=name)


def _timestamp(value: object, *, name: str) -> pd.Timestamp:
    try:
        result = pd.Timestamp(cast("Any", value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an RFC3339 timestamp") from error
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    result = result.tz_convert("UTC")
    if result.nanosecond % 1_000:
        raise ValueError(f"{name} must not exceed microsecond precision")
    return result


def _timestamp_string(value: pd.Timestamp) -> str:
    return value.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _array(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return cast("list[object]", value)


def _integer(value: object, *, name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a JSON integer")
    if value < 0 or (positive and value == 0):
        requirement = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be {requirement}")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result
