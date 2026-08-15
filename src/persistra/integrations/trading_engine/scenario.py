"""Build, parse, and serialize deterministic Trading Engine scenarios."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
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
    rfc3339_string,
)
from persistra.integrations.trading_engine.model import (
    BarClockPolicy,
    CancelOrderIntent,
    EmitMetricIntent,
    ExecutionInstrument,
    ExecutionPolicy,
    MarketSlice,
    RiskPolicy,
    ScenarioBar,
    ScenarioIntent,
    ScheduleItem,
    SizingPolicy,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetQuantity,
    TargetWeight,
    TargetWeightsIntent,
    TradingEngineScenario,
)
from persistra.portfolio import PortfolioConstructionResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.model import BarSet

_INTERVAL = re.compile(r"([1-9][0-9]*)min")
_SCENARIO_FIELDS = {
    "run_id",
    "base_currency",
    "initial_cash",
    "instruments",
    "risk",
    "execution",
    "max_internal_events",
    "metadata",
    "schedule",
    "slices",
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
    metadata: Mapping[str, object] | None = None,
) -> TradingEngineScenario:
    """Build a deterministic long-only scenario from raw synchronized intraday bars."""
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
    slices, slice_by_label = _build_slices(
        bars,
        instruments=execution_instruments,
        base_currency=base_currency,
        clock_policy=clock_policy,
    )
    target_frame, weights = _target_frame(targets, target_quantities)
    schedule = _build_schedule(
        target_frame,
        weights=weights,
        slice_by_label=slice_by_label,
        instruments=execution_instruments,
    )
    scenario_metadata = _build_metadata(
        bars,
        clock_policy=clock_policy,
        sizing_policy=sizing_policy,
        risk=risk,
        execution=execution,
        schedule=schedule,
        metadata=metadata,
    )
    return TradingEngineScenario(
        run_id=checked_run_id,
        base_currency=base_currency,
        initial_cash=checked_cash,
        instruments=execution_instruments,
        risk=risk,
        execution=execution,
        max_internal_events=checked_events,
        metadata=scenario_metadata,
        schedule=schedule,
        slices=slices,
    )


def scenario_to_json(scenario: TradingEngineScenario, *, indent: int | None = 2) -> str:
    """Serialize a scenario as stable UTF-8-compatible JSON."""
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
    """Parse one complete Trading Engine scenario JSON document."""
    try:
        raw = json.loads(document, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid scenario JSON: {error.msg}") from error
    payload = exact_fields(raw, _SCENARIO_FIELDS, name="scenario")
    run_id = identifier(payload["run_id"], name="run_id")
    base_currency = identifier(payload["base_currency"], name="base_currency")
    initial_cash = _exact_decimal(payload["initial_cash"], name="initial_cash", nonnegative=True)
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
    metadata = _metadata_from_json(payload["metadata"])
    slices = tuple(_slice_from_json(item) for item in _array(payload["slices"], name="slices"))
    schedule = tuple(
        _schedule_from_json(item) for item in _array(payload["schedule"], name="schedule")
    )
    return TradingEngineScenario(
        run_id=run_id,
        base_currency=base_currency,
        initial_cash=initial_cash,
        instruments=instruments,
        risk=risk,
        execution=execution,
        max_internal_events=max_events,
        metadata=metadata,
        schedule=schedule,
        slices=slices,
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
    """Read and validate one scenario document."""
    return scenario_from_json(Path(path).expanduser().read_text(encoding="utf-8"))


def _build_slices(
    bar_sets: Sequence[BarSet],
    *,
    instruments: tuple[ExecutionInstrument, ...],
    base_currency: str,
    clock_policy: BarClockPolicy,
) -> tuple[tuple[MarketSlice, ...], dict[pd.Timestamp, MarketSlice]]:
    instrument_by_id = {item.instrument_id: item for item in instruments}
    bar_ids = [item.instrument.instrument_id for item in bar_sets]
    if len(set(bar_ids)) != len(bar_ids):
        raise ValueError("bars must contain one BarSet per instrument")
    if set(bar_ids) != set(instrument_by_id):
        raise ValueError("bar and execution instrument identities must match exactly")
    expected_duration = pd.Timedelta(clock_policy.bar_duration)
    pending_by_label: dict[pd.Timestamp, list[_PendingBar]] = {}
    labels_by_instrument: dict[str, set[pd.Timestamp]] = {}
    for bar_set in bar_sets:
        frame = bar_set.frame
        instrument_id = bar_set.instrument.instrument_id
        if frame.empty:
            raise ValueError(f"bars for {instrument_id} must not be empty")
        if set(frame["price_adjustment"].astype(str)) != {"raw"}:
            raise ValueError("execution scenarios require raw, unadjusted bars")
        if set(frame["currency"].astype(str)) != {base_currency}:
            raise ValueError("every bar currency must match the scenario base currency")
        if frame["date"].notna().any() or frame["timestamp"].isna().any():
            raise ValueError("execution scenarios support intraday bars only")
        instrument = instrument_by_id[instrument_id]
        labels: set[pd.Timestamp] = set()
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
            if source_timestamp in labels:
                raise ValueError("each instrument must contain one bar per source timestamp")
            labels.add(source_timestamp)
            if clock_policy.source_timestamp_position == "start":
                start_at = source_timestamp
                end_at = source_timestamp + expected_duration
            else:
                start_at = source_timestamp - expected_duration
                end_at = source_timestamp
            available_at = end_at + pd.Timedelta(clock_policy.availability_delay)
            received_at = available_at + pd.Timedelta(clock_policy.receipt_delay)
            prices = tuple(
                decimal_value(row[name], name=f"bar {name}", positive=True)
                for name in ("open", "high", "low", "close")
            )
            tick = decimal_micros(cast("Decimal", instrument.tick_size))
            for name, price in zip(("open", "high", "low", "close"), prices, strict=True):
                if decimal_micros(price) % tick:
                    raise ValueError(f"bar {name} for {instrument_id} is not tick aligned")
            pending_by_label.setdefault(source_timestamp, []).append(
                (
                    instrument_id,
                    source_timestamp,
                    start_at,
                    end_at,
                    available_at,
                    received_at,
                    prices[0],
                    prices[1],
                    prices[2],
                    prices[3],
                    _optional_quantity(row["volume"], name="bar volume"),
                )
            )
        labels_by_instrument[instrument_id] = labels
    label_sets = list(labels_by_instrument.values())
    if any(labels != label_sets[0] for labels in label_sets[1:]):
        raise ValueError("every market slice requires a bar for every instrument")
    ordered_labels = sorted(
        pending_by_label,
        key=lambda label: (
            pending_by_label[label][0][5],
            pending_by_label[label][0][3],
            label,
        ),
    )
    result: list[MarketSlice] = []
    by_label: dict[pd.Timestamp, MarketSlice] = {}
    previous_end: pd.Timestamp | None = None
    for slice_sequence, label in enumerate(ordered_labels, start=1):
        pending = pending_by_label[label]
        clocks = {(item[2], item[3], item[4], item[5]) for item in pending}
        if len(clocks) != 1:
            raise ValueError("all bars in a market slice must resolve to identical clocks")
        start_at, end_at, available_at, received_at = next(iter(clocks))
        if previous_end is not None and end_at <= previous_end:
            raise ValueError("market slice end_at must increase")
        previous_end = end_at
        scenario_bars = tuple(
            ScenarioBar(
                instrument_id=item[0],
                open=item[6],
                high=item[7],
                low=item[8],
                close=item[9],
                volume=item[10],
            )
            for item in sorted(pending, key=lambda item: item[0])
        )
        market_slice = MarketSlice(
            slice_sequence=slice_sequence,
            start_at=start_at,
            end_at=end_at,
            available_at=available_at,
            received_at=received_at,
            bars=scenario_bars,
        )
        result.append(market_slice)
        by_label[label] = market_slice
    return tuple(result), by_label


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


def _build_schedule(
    target_frame: pd.DataFrame,
    *,
    weights: bool,
    slice_by_label: Mapping[pd.Timestamp, MarketSlice],
    instruments: tuple[ExecutionInstrument, ...],
) -> tuple[ScheduleItem, ...]:
    instrument_by_id = {item.instrument_id: item for item in instruments}
    if set(target_frame.columns) != set(instrument_by_id):
        raise ValueError("target and execution instrument identities must match exactly")
    schedule: list[ScheduleItem] = []
    for label, row in target_frame.iterrows():
        timestamp = _timestamp(label, name="target timestamp")
        market_slice = slice_by_label.get(timestamp)
        if market_slice is None:
            raise ValueError("each target timestamp requires a synchronized market slice")
        if weights:
            intent: ScenarioIntent = TargetWeightsIntent(
                tuple(
                    TargetWeight(
                        instrument_id,
                        _weight(row[instrument_id], name=f"weight {instrument_id}"),
                    )
                    for instrument_id in sorted(instrument_by_id)
                )
            )
        else:
            quantity_targets: list[TargetQuantity] = []
            for instrument_id in sorted(instrument_by_id):
                quantity = quantity_value(row[instrument_id], name=f"quantity {instrument_id}")
                if quantity % instrument_by_id[instrument_id].lot_size:
                    raise ValueError(f"target quantity for {instrument_id} is not lot aligned")
                quantity_targets.append(TargetQuantity(instrument_id, quantity))
            intent = TargetQuantitiesIntent(tuple(quantity_targets))
        schedule.append(ScheduleItem(market_slice.slice_sequence, (intent,)))
    return tuple(schedule)


def _build_metadata(
    bar_sets: Sequence[BarSet],
    *,
    clock_policy: BarClockPolicy,
    sizing_policy: SizingPolicy,
    risk: RiskPolicy,
    execution: ExecutionPolicy,
    schedule: tuple[ScheduleItem, ...],
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    supplied = {} if metadata is None else dict(metadata)
    if "persistra" in supplied:
        raise ValueError("metadata.persistra is reserved for generated provenance")
    normalized = cast("dict[str, object]", _json_value(supplied, name="metadata"))
    sources: list[dict[str, object]] = []
    for bar_set in sorted(bar_sets, key=lambda item: item.instrument.instrument_id):
        source = bar_set.metadata
        sources.append(
            {
                "instrument_id": bar_set.instrument.instrument_id,
                "provider": source.provider,
                "operation": source.operation,
                "request_parameters": _json_value(
                    dict(source.request_parameters), name="request_parameters"
                ),
                "retrieved_at": _datetime_string(source.retrieved_at),
                "provider_as_of": None
                if source.provider_as_of is None
                else _datetime_string(source.provider_as_of),
            }
        )
    normalized["persistra"] = {
        "producer": "persistra",
        "clock_policy": {
            "source_timestamp_position": clock_policy.source_timestamp_position,
            "bar_duration_microseconds": _timedelta_microseconds(clock_policy.bar_duration),
            "availability_delay_microseconds": _timedelta_microseconds(
                clock_policy.availability_delay
            ),
            "receipt_delay_microseconds": _timedelta_microseconds(clock_policy.receipt_delay),
        },
        "sizing_policy": {
            "equity_basis": sizing_policy.equity_basis,
            "reference_price": sizing_policy.reference_price,
            "quantity_rounding": sizing_policy.quantity_rounding,
        },
        "risk_policy": {
            "max_order_quantity": str(risk.max_order_quantity),
            "max_position": str(risk.max_position),
        },
        "execution_policy": {
            "participation_bps": execution.participation_bps,
            "fixed_fee": decimal_string(cast("Decimal", execution.fixed_fee)),
            "fee_bps": execution.fee_bps,
            "target_persistence": "until_reached_or_superseded",
            "rebalance_order": "sells_before_buys",
            "buying_power": "cash_after_fees",
        },
        "source_identities": sources,
        "original_targets": [
            {
                "after_slice_sequence": str(item.after_slice_sequence),
                "intents": [_intent_dictionary(intent) for intent in item.intents],
            }
            for item in schedule
        ],
    }
    return normalized


def _scenario_dictionary(scenario: TradingEngineScenario) -> dict[str, object]:
    return {
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
        "metadata": _json_value(scenario.metadata, name="metadata"),
        "schedule": [
            {
                "after_slice_sequence": str(item.after_slice_sequence),
                "intents": [_intent_dictionary(intent) for intent in item.intents],
            }
            for item in scenario.schedule
        ],
        "slices": [_slice_dictionary(item) for item in scenario.slices],
    }


def _slice_dictionary(market_slice: MarketSlice) -> dict[str, object]:
    return {
        "slice_sequence": str(market_slice.slice_sequence),
        "start_at": _timestamp_string(market_slice.start_at),
        "end_at": _timestamp_string(market_slice.end_at),
        "available_at": _timestamp_string(market_slice.available_at),
        "received_at": _timestamp_string(market_slice.received_at),
        "bars": [
            {
                "instrument_id": bar.instrument_id,
                "open": decimal_string(bar.open),
                "high": decimal_string(bar.high),
                "low": decimal_string(bar.low),
                "close": decimal_string(bar.close),
                "volume": None if bar.volume is None else str(bar.volume),
            }
            for bar in market_slice.bars
        ],
    }


def _intent_dictionary(intent: ScenarioIntent) -> dict[str, object]:
    if isinstance(intent, TargetWeightsIntent):
        return {
            "type": intent.type,
            "targets": [
                {
                    "instrument_id": item.instrument_id,
                    "weight": decimal_string(cast("Decimal", item.weight)),
                }
                for item in intent.targets
            ],
        }
    if isinstance(intent, TargetQuantitiesIntent):
        return {
            "type": intent.type,
            "targets": [
                {"instrument_id": item.instrument_id, "quantity": str(item.quantity)}
                for item in intent.targets
            ],
        }
    if isinstance(intent, SubmitOrderIntent):
        return {
            "type": intent.type,
            "instrument_id": intent.instrument_id,
            "side": intent.side,
            "quantity": str(intent.quantity),
            "order_kind": intent.order_kind,
            "limit_price": None
            if intent.limit_price is None
            else decimal_string(cast("Decimal", intent.limit_price)),
        }
    if isinstance(intent, CancelOrderIntent):
        return {"type": intent.type, "order_id": intent.order_id}
    return {"type": intent.type, "name": intent.name, "value": intent.value}


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
        tick_size=_exact_decimal(item["tick_size"], name="tick_size", positive=True),
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
        fixed_fee=_exact_decimal(item["fixed_fee"], name="fixed_fee", nonnegative=True),
        fee_bps=_integer(item["fee_bps"], name="fee_bps"),
    )


def _metadata_from_json(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")
    raw = cast("dict[object, object]", value)
    return cast("dict[str, object]", _json_value(raw, name="metadata"))


def _slice_from_json(value: object) -> MarketSlice:
    item = exact_fields(
        value,
        {
            "slice_sequence",
            "start_at",
            "end_at",
            "available_at",
            "received_at",
            "bars",
        },
        name="market slice",
    )
    return MarketSlice(
        slice_sequence=quantity_value(item["slice_sequence"], name="slice_sequence", positive=True),
        start_at=_timestamp(item["start_at"], name="start_at"),
        end_at=_timestamp(item["end_at"], name="end_at"),
        available_at=_timestamp(item["available_at"], name="available_at"),
        received_at=_timestamp(item["received_at"], name="received_at"),
        bars=tuple(_bar_from_json(bar) for bar in _array(item["bars"], name="bars")),
    )


def _bar_from_json(value: object) -> ScenarioBar:
    item = exact_fields(
        value,
        {"instrument_id", "open", "high", "low", "close", "volume"},
        name="bar",
    )
    return ScenarioBar(
        instrument_id=identifier(item["instrument_id"], name="instrument_id"),
        open=_exact_decimal(item["open"], name="open", positive=True),
        high=_exact_decimal(item["high"], name="high", positive=True),
        low=_exact_decimal(item["low"], name="low", positive=True),
        close=_exact_decimal(item["close"], name="close", positive=True),
        volume=None if item["volume"] is None else quantity_value(item["volume"], name="volume"),
    )


def _schedule_from_json(value: object) -> ScheduleItem:
    item = exact_fields(value, {"after_slice_sequence", "intents"}, name="schedule item")
    return ScheduleItem(
        after_slice_sequence=quantity_value(
            item["after_slice_sequence"], name="after_slice_sequence", positive=True
        ),
        intents=tuple(
            _intent_from_json(intent) for intent in _array(item["intents"], name="intents")
        ),
    )


def _intent_from_json(value: object) -> ScenarioIntent:
    if not isinstance(value, dict):
        raise ValueError("intent must be a JSON object")
    raw = cast("dict[str, object]", value)
    intent_type = raw.get("type")
    if intent_type == "target_weights":
        item = exact_fields(raw, {"type", "targets"}, name="target_weights intent")
        return TargetWeightsIntent(
            tuple(
                _target_weight_from_json(target)
                for target in _array(item["targets"], name="targets")
            )
        )
    if intent_type == "target_quantities":
        item = exact_fields(raw, {"type", "targets"}, name="target_quantities intent")
        return TargetQuantitiesIntent(
            tuple(
                _target_quantity_from_json(target)
                for target in _array(item["targets"], name="targets")
            )
        )
    if intent_type == "submit_order":
        item = exact_fields(
            raw,
            {"type", "instrument_id", "side", "quantity", "order_kind", "limit_price"},
            name="submit_order intent",
        )
        side = _choice(item["side"], {"buy", "sell"}, name="side")
        order_kind = _choice(item["order_kind"], {"market", "limit"}, name="order_kind")
        return SubmitOrderIntent(
            instrument_id=identifier(item["instrument_id"], name="instrument_id"),
            side=cast("Any", side),
            quantity=quantity_value(item["quantity"], name="quantity", positive=True),
            order_kind=cast("Any", order_kind),
            limit_price=None
            if item["limit_price"] is None
            else _exact_decimal(item["limit_price"], name="limit_price", positive=True),
        )
    if intent_type == "cancel_order":
        item = exact_fields(raw, {"type", "order_id"}, name="cancel_order intent")
        return CancelOrderIntent(identifier(item["order_id"], name="order_id"))
    if intent_type == "emit_metric":
        item = exact_fields(raw, {"type", "name", "value"}, name="emit_metric intent")
        if not isinstance(item["name"], str):
            raise ValueError("metric name must be a string")
        if not isinstance(item["value"], str):
            raise ValueError("metric value must be a string")
        return EmitMetricIntent(
            item["name"],
            item["value"],
        )
    raise ValueError("unsupported intent type")


def _target_weight_from_json(value: object) -> TargetWeight:
    item = exact_fields(value, {"instrument_id", "weight"}, name="target weight")
    return TargetWeight(
        identifier(item["instrument_id"], name="instrument_id"),
        _exact_decimal(item["weight"], name="weight", nonnegative=True),
    )


def _target_quantity_from_json(value: object) -> TargetQuantity:
    item = exact_fields(value, {"instrument_id", "quantity"}, name="target quantity")
    return TargetQuantity(
        identifier(item["instrument_id"], name="instrument_id"),
        quantity_value(item["quantity"], name="quantity"),
    )


def _require_unique_instruments(instruments: Sequence[ExecutionInstrument]) -> None:
    identities = [item.instrument_id for item in instruments]
    if len(set(identities)) != len(identities):
        raise ValueError("execution instrument identifiers must be unique")


def _weight(value: object, *, name: str) -> Decimal:
    if value is pd.NA or value is pd.NaT:
        raise ValueError(f"{name} must be finite")
    try:
        return decimal_value(cast("Any", value), name=name, nonnegative=True)
    except TypeError as error:
        raise TypeError(f"{name} must be numeric") from error


def _optional_quantity(value: object, *, name: str) -> int | None:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return quantity_value(value, name=name)


def _timestamp(value: object, *, name: str) -> pd.Timestamp:
    if isinstance(value, str):
        rfc3339_string(value, name=name)
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


def _datetime_string(value: object) -> str:
    return _timestamp(pd.Timestamp(cast("Any", value)), name="provenance timestamp").strftime(
        "%Y-%m-%dT%H:%M:%S.%fZ"
    )


def _timedelta_microseconds(value: timedelta) -> str:
    return str(value // timedelta(microseconds=1))


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


def _exact_decimal(
    value: object,
    *,
    name: str,
    positive: bool = False,
    nonnegative: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an exact decimal string")
    result = decimal_value(value, name=name, positive=positive, nonnegative=nonnegative)
    if decimal_string(result) != value:
        raise ValueError(f"{name} must use canonical decimal encoding")
    return result


def _choice(value: object, choices: set[str], *, name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"unsupported {name}")
    return value


def _json_value(value: object, *, name: str) -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must contain only finite JSON numbers")
        return value
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        mapping = cast("Mapping[object, object]", value)
        for key, item in mapping.items():
            if not isinstance(key, str):
                raise TypeError(f"{name} keys must be strings")
            result[key] = _json_value(item, name=f"{name}.{key}")
        return result
    if isinstance(value, list | tuple):
        return [_json_value(item, name=name) for item in cast("Sequence[object]", value)]
    raise TypeError(f"{name} must contain JSON-compatible values")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result
