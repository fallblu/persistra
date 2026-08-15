"""Strictly import version 1 trading-engine audit journals."""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.integrations.trading_engine._scalars import (
    MICRO_SCALE,
    decimal_micros,
    decimal_string,
    decimal_value,
    exact_fields,
    identifier,
    quantity_value,
)
from persistra.integrations.trading_engine.model import (
    ExecutionReplayResult,
    JournalEvent,
    RunCompletion,
    TradingEngineScenario,
)
from persistra.integrations.trading_engine.scenario import read_scenario

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from decimal import Decimal

_EVENT_FIELDS = {
    "schema_version",
    "engine_sequence",
    "run_id",
    "recorded_at",
    "event_type",
    "payload",
}
_VALUATION_FIELDS = {
    "cash",
    "market_value",
    "cost_basis",
    "realized_pnl",
    "unrealized_pnl",
    "equity",
    "total_fees",
}
_ORDER_FIELDS = {
    "order_id",
    "instrument_id",
    "side",
    "quantity",
    "order_kind",
    "limit_price",
    "origin",
    "created_at",
    "created_sequence",
    "eligible_after_bar_sequence",
    "filled_quantity",
    "filled_notional",
    "status",
    "rejection_reason",
}
_BAR_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "source_sequence": "Int64",
    "instrument_id": "string",
    "start_at": "datetime64[ns, UTC]",
    "end_at": "datetime64[ns, UTC]",
    "available_at": "datetime64[ns, UTC]",
    "received_at": "datetime64[ns, UTC]",
    "open": "float64",
    "open_micros": "Int64",
    "high": "float64",
    "high_micros": "Int64",
    "low": "float64",
    "low_micros": "Int64",
    "close": "float64",
    "close_micros": "Int64",
    "volume": "Int64",
}
_TARGET_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "decision_bar_sequence": "Int64",
    "instrument_id": "string",
    "quantity": "Int64",
    "target_weight": "Float64",
    "reference_close": "Float64",
    "reference_close_micros": "Int64",
}
_ORDER_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "event_type": "string",
    "order_id": "string",
    "instrument_id": "string",
    "side": "string",
    "quantity": "Int64",
    "order_kind": "string",
    "limit_price": "Float64",
    "limit_price_micros": "Int64",
    "origin": "string",
    "created_at": "datetime64[ns, UTC]",
    "created_sequence": "Int64",
    "eligible_after_bar_sequence": "Int64",
    "filled_quantity": "Int64",
    "filled_notional": "float64",
    "filled_notional_micros": "Int64",
    "status": "string",
    "rejection_reason": "string",
}
_CANCELLATION_DTYPES = {
    **_ORDER_DTYPES,
    "reason": "string",
}
_FILL_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "fill_id": "string",
    "order_id": "string",
    "instrument_id": "string",
    "side": "string",
    "quantity": "Int64",
    "price": "float64",
    "price_micros": "Int64",
    "notional": "float64",
    "notional_micros": "Int64",
    "fee": "float64",
    "fee_micros": "Int64",
    "executed_at": "datetime64[ns, UTC]",
    "bar_sequence": "Int64",
}
_REJECTION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "event_type": "string",
    "order_id": "string",
    "instrument_id": "string",
    "reason": "string",
}
_VALUATION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "cash": "float64",
    "cash_micros": "Int64",
    "market_value": "float64",
    "market_value_micros": "Int64",
    "cost_basis": "float64",
    "cost_basis_micros": "Int64",
    "realized_pnl": "float64",
    "realized_pnl_micros": "Int64",
    "unrealized_pnl": "float64",
    "unrealized_pnl_micros": "Int64",
    "equity": "float64",
    "equity_micros": "Int64",
    "total_fees": "float64",
    "total_fees_micros": "Int64",
}
_METRIC_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "name": "string",
    "value": "string",
}


def read_journal(
    path: str | Path,
    *,
    scenario: TradingEngineScenario | str | Path | None = None,
) -> ExecutionReplayResult:
    """Read one complete version 1 JSON Lines journal into normalized frames."""
    journal_path = Path(path).expanduser()
    resolved_scenario = _resolve_scenario(scenario)
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("audit journal must not be empty")
    if any(not line for line in lines):
        raise ValueError("audit journal must not contain blank records")

    bar_rows: list[dict[str, object]] = []
    target_rows: list[dict[str, object]] = []
    order_rows: list[dict[str, object]] = []
    fill_rows: list[dict[str, object]] = []
    cancellation_rows: list[dict[str, object]] = []
    rejection_rows: list[dict[str, object]] = []
    valuation_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    events: list[JournalEvent] = []
    completion: RunCompletion | None = None
    run_id: str | None = None
    previous_recorded_at: pd.Timestamp | None = None
    latest_bar_sequence: int | None = None
    previous_source_sequence: int | None = None
    current_bar_recorded_at: pd.Timestamp | None = None

    for line_number, line in enumerate(lines, start=1):
        raw = _json_record(line, line_number=line_number)
        event = exact_fields(raw, _EVENT_FIELDS, name=f"journal record {line_number}")
        version = _json_integer(event["schema_version"], name="schema_version", positive=True)
        if version != 1:
            raise ValueError("unsupported journal schema_version")
        engine_sequence = quantity_value(
            event["engine_sequence"],
            name="engine_sequence",
            positive=True,
        )
        if engine_sequence != line_number:
            raise ValueError("engine_sequence must be contiguous and start at one")
        event_run_id = identifier(event["run_id"], name="run_id")
        if run_id is None:
            run_id = event_run_id
        elif event_run_id != run_id:
            raise ValueError("journal run_id must remain constant")
        recorded_at = _timestamp(event["recorded_at"], name="recorded_at")
        if previous_recorded_at is not None and recorded_at < previous_recorded_at:
            raise ValueError("journal recorded_at must not move backward")
        previous_recorded_at = recorded_at
        event_type = identifier(event["event_type"], name="event_type")
        if completion is not None:
            raise ValueError("run_completed must be the terminal journal record")
        if event_type == "bar_received":
            if current_bar_recorded_at is not None:
                raise ValueError("each bar group must end with valuation before the next bar")
        elif event_type == "run_completed":
            if current_bar_recorded_at is not None:
                raise ValueError("run_completed must follow the current bar's valuation")
        else:
            if current_bar_recorded_at is None:
                raise ValueError("nonterminal journal events require an open bar group")
            if recorded_at != current_bar_recorded_at:
                raise ValueError(
                    "each bar-group event recorded_at must equal its bar receipt clock"
                )
        payload = event["payload"]

        if event_type == "bar_received":
            row = _bar_row(payload, engine_sequence=engine_sequence, recorded_at=recorded_at)
            source_sequence = cast("int", row["source_sequence"])
            if previous_source_sequence is not None and source_sequence <= previous_source_sequence:
                raise ValueError("bar source_sequence must increase globally")
            if cast("pd.Timestamp", row["received_at"]) != recorded_at:
                raise ValueError("bar receipt time must equal its audit recorded_at")
            previous_source_sequence = source_sequence
            latest_bar_sequence = source_sequence
            bar_rows.append(row)
            current_bar_recorded_at = recorded_at
        elif event_type == "target_requested":
            if latest_bar_sequence is None:
                raise ValueError("target_requested must follow a received bar")
            target_rows.append(
                _target_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    decision_bar_sequence=latest_bar_sequence,
                )
            )
        elif event_type in {"order_accepted", "order_rejected"}:
            if latest_bar_sequence is None or not bar_rows:
                raise ValueError("submitted orders must follow a received bar")
            order = _order_row(
                payload,
                engine_sequence=engine_sequence,
                recorded_at=recorded_at,
                event_type=event_type,
            )
            if event_type == "order_accepted" and order["status"] == "rejected":
                raise ValueError("order_accepted cannot contain rejected status")
            if event_type == "order_rejected" and order["status"] != "rejected":
                raise ValueError("order_rejected must contain rejected status")
            if order["created_sequence"] != engine_sequence:
                raise ValueError("submitted order created_sequence must equal engine_sequence")
            if order["eligible_after_bar_sequence"] != latest_bar_sequence:
                raise ValueError(
                    "submitted order eligibility must equal the current bar source_sequence"
                )
            if recorded_at != bar_rows[-1]["received_at"]:
                raise ValueError("submitted order recorded_at must equal the current replay clock")
            order_rows.append(order)
            if event_type == "order_rejected":
                rejection_rows.append(_order_rejection_row(order))
        elif event_type == "order_cancelled":
            cancellation_rows.append(
                _cancellation_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
            )
        elif event_type == "fill_applied":
            fill_rows.append(
                _fill_row(payload, engine_sequence=engine_sequence, recorded_at=recorded_at)
            )
        elif event_type == "intent_rejected":
            rejection_rows.append(
                _intent_rejection_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
            )
        elif event_type == "metric_emitted":
            metric_rows.append(
                _metric_row(payload, engine_sequence=engine_sequence, recorded_at=recorded_at)
            )
        elif event_type == "valuation":
            valuation_rows.append(
                _valuation_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
            )
            current_bar_recorded_at = None
        elif event_type == "run_completed":
            completion = _completion(
                payload,
                engine_sequence=engine_sequence,
                recorded_at=recorded_at,
            )
        else:
            raise ValueError(f"unsupported journal event_type: {event_type}")
        events.append(
            JournalEvent(
                engine_sequence=engine_sequence,
                run_id=event_run_id,
                recorded_at=recorded_at,
                event_type=event_type,
                payload=cast("Mapping[str, Any]", _freeze_payload(payload)),
                schema_version=version,
            )
        )

    if run_id is None or completion is None:
        raise ValueError("audit journal must end with one run_completed record")
    _validate_completion(
        completion,
        bars=bar_rows,
        orders=order_rows,
        fills=fill_rows,
        cancellations=cancellation_rows,
        valuations=valuation_rows,
        scenario=resolved_scenario,
    )
    if resolved_scenario is not None:
        _validate_scenario_journal(resolved_scenario, run_id, bar_rows, target_rows)
    _enrich_targets(target_rows, bar_rows, resolved_scenario)
    initial_cash_micros = (
        None if resolved_scenario is None else decimal_micros(resolved_scenario.initial_cash)
    )
    return ExecutionReplayResult(
        run_id=run_id,
        bars=_typed_frame(bar_rows, _BAR_DTYPES),
        targets=_typed_frame(target_rows, _TARGET_DTYPES),
        orders=_typed_frame(order_rows, _ORDER_DTYPES),
        fills=_typed_frame(fill_rows, _FILL_DTYPES),
        cancellations=_typed_frame(cancellation_rows, _CANCELLATION_DTYPES),
        rejections=_typed_frame(rejection_rows, _REJECTION_DTYPES),
        valuations=_typed_frame(valuation_rows, _VALUATION_DTYPES),
        metrics=_typed_frame(metric_rows, _METRIC_DTYPES),
        events=tuple(events),
        completion=completion,
        base_currency=None if resolved_scenario is None else resolved_scenario.base_currency,
        initial_cash=None
        if initial_cash_micros is None
        else initial_cash_micros / MICRO_SCALE,
        initial_cash_micros=initial_cash_micros,
    )


def _bar_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
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
        name="bar_received payload",
    )
    start_at = _timestamp(item["start_at"], name="start_at")
    end_at = _timestamp(item["end_at"], name="end_at")
    available_at = _timestamp(item["available_at"], name="available_at")
    received_at = _timestamp(item["received_at"], name="received_at")
    if not start_at < end_at <= available_at <= received_at:
        raise ValueError("bar timestamps must satisfy start < end <= available <= received")
    prices = {
        name: _decimal_payload(item[name], name=name, positive=True)
        for name in ("open", "high", "low", "close")
    }
    if prices["low"] > min(prices["open"], prices["close"]):
        raise ValueError("bar low exceeds open or close")
    if prices["high"] < max(prices["open"], prices["close"]):
        raise ValueError("bar high is below open or close")
    row: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "source_sequence": quantity_value(item["source_sequence"], name="source_sequence"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "start_at": start_at,
        "end_at": end_at,
        "available_at": available_at,
        "received_at": received_at,
        "volume": pd.NA
        if item["volume"] is None
        else quantity_value(item["volume"], name="volume"),
    }
    for name, price in prices.items():
        row[name] = float(price)
        row[f"{name}_micros"] = decimal_micros(price)
    return row


def _target_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    decision_bar_sequence: int,
) -> dict[str, object]:
    item = exact_fields(
        value,
        {"instrument_id", "quantity"},
        name="target_requested payload",
    )
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "decision_bar_sequence": decision_bar_sequence,
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "quantity": quantity_value(item["quantity"], name="quantity"),
        "target_weight": pd.NA,
        "reference_close": pd.NA,
        "reference_close_micros": pd.NA,
    }


def _order_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    event_type: str,
) -> dict[str, object]:
    item = exact_fields(value, _ORDER_FIELDS, name=f"{event_type} payload")
    side = _choice(item["side"], {"buy", "sell"}, name="side")
    order_kind = _choice(item["order_kind"], {"market", "limit"}, name="order_kind")
    status = _choice(
        item["status"],
        {"working", "partially_filled", "filled", "cancelled", "rejected"},
        name="status",
    )
    limit_price: Decimal | None
    if item["limit_price"] is None:
        limit_price = None
    else:
        limit_price = _decimal_payload(item["limit_price"], name="limit_price", positive=True)
    if (order_kind == "market") != (limit_price is None):
        raise ValueError("market orders require null limit_price and limits require a price")
    rejection_reason = item["rejection_reason"]
    if rejection_reason is not None and not isinstance(rejection_reason, str):
        raise ValueError("rejection_reason must be a string or null")
    if (status == "rejected") != (rejection_reason is not None):
        raise ValueError("rejected status and rejection_reason must apply together")
    created_at = _timestamp(item["created_at"], name="created_at")
    if created_at > recorded_at:
        raise ValueError("order created_at must not follow audit recorded_at")
    if event_type in {"order_accepted", "order_rejected"} and created_at != recorded_at:
        raise ValueError("submitted order created_at must equal audit recorded_at")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "event_type": event_type,
        "order_id": identifier(item["order_id"], name="order_id"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "side": side,
        "quantity": quantity_value(item["quantity"], name="quantity", positive=True),
        "order_kind": order_kind,
        "limit_price": pd.NA if limit_price is None else float(limit_price),
        "limit_price_micros": pd.NA
        if limit_price is None
        else decimal_micros(limit_price),
        "origin": _choice(item["origin"], {"direct", "target_rebalance"}, name="origin"),
        "created_at": created_at,
        "created_sequence": quantity_value(
            item["created_sequence"], name="created_sequence", positive=True
        ),
        "eligible_after_bar_sequence": quantity_value(
            item["eligible_after_bar_sequence"],
            name="eligible_after_bar_sequence",
        ),
        "filled_quantity": quantity_value(item["filled_quantity"], name="filled_quantity"),
        **_money_pair("filled_notional", item["filled_notional"], nonnegative=True),
        "status": status,
        "rejection_reason": pd.NA if rejection_reason is None else rejection_reason,
    }


def _cancellation_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(value, {"order", "reason"}, name="order_cancelled payload")
    order = _order_row(
        item["order"],
        engine_sequence=engine_sequence,
        recorded_at=recorded_at,
        event_type="order_cancelled",
    )
    if order["status"] != "cancelled":
        raise ValueError("order_cancelled must contain cancelled status")
    order["reason"] = _choice(
        item["reason"],
        {"strategy_requested", "target_replaced", "market_ioc"},
        name="cancellation reason",
    )
    return order


def _fill_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(
        value,
        {
            "fill_id",
            "order_id",
            "instrument_id",
            "side",
            "quantity",
            "price",
            "notional",
            "fee",
            "executed_at",
            "bar_sequence",
        },
        name="fill_applied payload",
    )
    price = _decimal_payload(item["price"], name="price", positive=True)
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "fill_id": identifier(item["fill_id"], name="fill_id"),
        "order_id": identifier(item["order_id"], name="order_id"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "side": _choice(item["side"], {"buy", "sell"}, name="side"),
        "quantity": quantity_value(item["quantity"], name="quantity", positive=True),
        "price": float(price),
        "price_micros": decimal_micros(price),
        **_money_pair("notional", item["notional"], nonnegative=True),
        **_money_pair("fee", item["fee"], nonnegative=True),
        "executed_at": _timestamp(item["executed_at"], name="executed_at"),
        "bar_sequence": quantity_value(item["bar_sequence"], name="bar_sequence"),
    }


def _valuation_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(value, _VALUATION_FIELDS, name="valuation payload")
    result: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
    }
    for name in _VALUATION_FIELDS:
        result.update(
            _money_pair(
                name,
                item[name],
                nonnegative=name == "total_fees",
            )
        )
    return result


def _metric_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(value, {"name", "value"}, name="metric_emitted payload")
    metric_name = item["name"]
    if not isinstance(metric_name, str):
        raise TypeError("metric name must be a string")
    if not metric_name or metric_name.strip() != metric_name:
        raise ValueError("metric name must be a nonempty trimmed string")
    if not isinstance(item["value"], str):
        raise ValueError("metric value must be a string")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "name": metric_name,
        "value": item["value"],
    }


def _intent_rejection_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(value, {"reason"}, name="intent_rejected payload")
    if not isinstance(item["reason"], str) or not item["reason"]:
        raise ValueError("intent rejection reason must be a nonempty string")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "event_type": "intent_rejected",
        "order_id": pd.NA,
        "instrument_id": pd.NA,
        "reason": item["reason"],
    }


def _order_rejection_row(order: Mapping[str, object]) -> dict[str, object]:
    return {
        "engine_sequence": order["engine_sequence"],
        "recorded_at": order["recorded_at"],
        "event_type": "order_rejected",
        "order_id": order["order_id"],
        "instrument_id": order["instrument_id"],
        "reason": order["rejection_reason"],
    }


def _completion(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> RunCompletion:
    item = exact_fields(value, {"valuation", "order_counts"}, name="run_completed payload")
    valuation = exact_fields(item["valuation"], _VALUATION_FIELDS, name="completion valuation")
    counts = exact_fields(
        item["order_counts"],
        {"total", "active", "filled", "rejected", "cancelled"},
        name="completion order_counts",
    )
    money = {
        name: decimal_micros(
            _decimal_payload(
                valuation[name],
                name=name,
                nonnegative=name == "total_fees",
            )
        )
        for name in _VALUATION_FIELDS
    }
    orders = {name: _json_integer(counts[name], name=f"{name} order count") for name in counts}
    if sum(orders[name] for name in ("active", "filled", "rejected", "cancelled")) != orders[
        "total"
    ]:
        raise ValueError("terminal order counts must reconcile to total")
    return RunCompletion(
        recorded_at=recorded_at,
        engine_sequence=engine_sequence,
        cash_micros=money["cash"],
        market_value_micros=money["market_value"],
        cost_basis_micros=money["cost_basis"],
        realized_pnl_micros=money["realized_pnl"],
        unrealized_pnl_micros=money["unrealized_pnl"],
        equity_micros=money["equity"],
        total_fees_micros=money["total_fees"],
        total_orders=orders["total"],
        active_orders=orders["active"],
        filled_orders=orders["filled"],
        rejected_orders=orders["rejected"],
        cancelled_orders=orders["cancelled"],
    )


def _enrich_targets(
    targets: list[dict[str, object]],
    bars: Sequence[dict[str, object]],
    scenario: TradingEngineScenario | None,
) -> None:
    for target in targets:
        anchor = cast("int", target["decision_bar_sequence"])
        instrument_id = cast("str", target["instrument_id"])
        eligible = [
            bar
            for bar in bars
            if cast("int", bar["source_sequence"]) <= anchor
            and bar["instrument_id"] == instrument_id
        ]
        if not eligible:
            raise ValueError("target_requested has no causal reference close")
        reference = max(eligible, key=lambda item: cast("int", item["source_sequence"]))
        target["reference_close"] = reference["close"]
        target["reference_close_micros"] = reference["close_micros"]
    if scenario is not None:
        for target, decision in zip(targets, scenario.decisions, strict=True):
            target["target_weight"] = (
                pd.NA if decision.target_weight is None else decision.target_weight
            )


def _validate_scenario_journal(
    scenario: TradingEngineScenario,
    run_id: str,
    bars: Sequence[dict[str, object]],
    targets: Sequence[dict[str, object]],
) -> None:
    if scenario.run_id != run_id:
        raise ValueError("scenario and journal run_id differ")
    if len(scenario.bars) != len(bars):
        raise ValueError("scenario and journal bar counts differ")
    for expected, observed in zip(scenario.bars, bars, strict=True):
        observed_volume = observed["volume"]
        normalized_volume = (
            None if observed_volume is pd.NA else cast("int", observed_volume)
        )
        if (
            expected.source_sequence != observed["source_sequence"]
            or expected.instrument_id != observed["instrument_id"]
            or expected.start_at != observed["start_at"]
            or expected.end_at != observed["end_at"]
            or expected.available_at != observed["available_at"]
            or expected.received_at != observed["received_at"]
            or decimal_micros(expected.open) != observed["open_micros"]
            or decimal_micros(expected.high) != observed["high_micros"]
            or decimal_micros(expected.low) != observed["low_micros"]
            or decimal_micros(expected.close) != observed["close_micros"]
            or expected.volume != normalized_volume
        ):
            raise ValueError("scenario and journal bars differ")
    if len(scenario.decisions) != len(targets):
        raise ValueError("scenario and journal target counts differ")
    for expected, observed in zip(scenario.decisions, targets, strict=True):
        if (
            expected.instrument_id != observed["instrument_id"]
            or expected.quantity != observed["quantity"]
            or expected.after_bar_sequence != observed["decision_bar_sequence"]
            or expected.decision_at != observed["recorded_at"]
        ):
            raise ValueError("scenario and journal targets differ")


def _validate_completion(
    completion: RunCompletion,
    *,
    bars: Sequence[Mapping[str, object]],
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
    valuations: Sequence[Mapping[str, object]],
    scenario: TradingEngineScenario | None,
) -> None:
    if len(valuations) != len(bars):
        raise ValueError("a complete journal must contain one valuation event per bar")
    for index, (bar, valuation) in enumerate(zip(bars, valuations, strict=True)):
        if valuation["recorded_at"] != bar["received_at"]:
            raise ValueError("each valuation recorded_at must match its bar receipt")
        if cast("int", valuation["engine_sequence"]) <= cast(
            "int", bar["engine_sequence"]
        ):
            raise ValueError("each valuation must follow its bar event")
        if index + 1 < len(bars) and cast("int", valuation["engine_sequence"]) >= cast(
            "int", bars[index + 1]["engine_sequence"]
        ):
            raise ValueError("each valuation must precede the next bar event")
    expected_completion_time = (
        pd.Timestamp("1970-01-01T00:00:00Z")
        if not bars
        else cast("pd.Timestamp", bars[-1]["received_at"])
    )
    if completion.recorded_at != expected_completion_time:
        raise ValueError("run_completed recorded_at must match the terminal replay clock")
    if not bars and scenario is not None:
        expected_cash = decimal_micros(scenario.initial_cash)
        if (
            completion.cash_micros != expected_cash
            or completion.equity_micros != expected_cash
            or any(
                value != 0
                for value in (
                    completion.market_value_micros,
                    completion.cost_basis_micros,
                    completion.realized_pnl_micros,
                    completion.unrealized_pnl_micros,
                    completion.total_fees_micros,
                )
            )
        ):
            raise ValueError("empty-run completion must reconcile to scenario initial_cash")
    if valuations:
        final = valuations[-1]
        completion_values = {
            "cash": completion.cash_micros,
            "market_value": completion.market_value_micros,
            "cost_basis": completion.cost_basis_micros,
            "realized_pnl": completion.realized_pnl_micros,
            "unrealized_pnl": completion.unrealized_pnl_micros,
            "equity": completion.equity_micros,
            "total_fees": completion.total_fees_micros,
        }
        if any(final[f"{name}_micros"] != value for name, value in completion_values.items()):
            raise ValueError("run_completed valuation must match the final valuation event")
    order_by_id = {cast("str", item["order_id"]): item for item in orders}
    if len(order_by_id) != len(orders):
        raise ValueError("order identifiers must be unique")
    cancelled = {cast("str", item["order_id"]) for item in cancellations}
    if len(cancelled) != len(cancellations) or not cancelled.issubset(order_by_id):
        raise ValueError("cancellations must refer once to imported orders")
    filled_by_order: dict[str, int] = {}
    bar_by_sequence = {cast("int", item["source_sequence"]): item for item in bars}
    fill_ids: set[str] = set()
    for fill in fills:
        fill_id = cast("str", fill["fill_id"])
        if fill_id in fill_ids:
            raise ValueError("fill identifiers must be unique")
        fill_ids.add(fill_id)
        order_id = cast("str", fill["order_id"])
        if order_id not in order_by_id:
            raise ValueError("fills must refer to imported orders")
        order = order_by_id[order_id]
        if (
            fill["instrument_id"] != order["instrument_id"]
            or fill["side"] != order["side"]
        ):
            raise ValueError("fill instrument and side must match its order")
        if cast("pd.Timestamp", fill["executed_at"]) < cast(
            "pd.Timestamp", order["created_at"]
        ):
            raise ValueError("fill executed_at must not precede order created_at")
        bar_sequence = cast("int", fill["bar_sequence"])
        fill_bar = bar_by_sequence.get(bar_sequence)
        if fill_bar is None:
            raise ValueError("fill must refer to an imported bar")
        if bar_sequence <= cast("int", order["eligible_after_bar_sequence"]):
            raise ValueError("fill bar must follow order sequence eligibility")
        if fill["instrument_id"] != fill_bar["instrument_id"] or fill["recorded_at"] != fill_bar[
            "received_at"
        ]:
            raise ValueError("fill must use its instrument bar and receipt clock")
        expected_time: object
        expected_price: object
        if order["order_kind"] == "market":
            expected_time = fill_bar["start_at"]
            expected_price = fill_bar["open_micros"]
        else:
            limit = cast("int", order["limit_price_micros"])
            opens = cast("int", fill_bar["open_micros"])
            crosses_open = (order["side"] == "buy" and opens <= limit) or (
                order["side"] == "sell" and opens >= limit
            )
            touches = (
                order["side"] == "buy" and cast("int", fill_bar["low_micros"]) <= limit
            ) or (
                order["side"] == "sell" and cast("int", fill_bar["high_micros"]) >= limit
            )
            if crosses_open:
                expected_time = fill_bar["start_at"]
                expected_price = opens
            elif touches:
                expected_time = fill_bar["end_at"]
                expected_price = limit
            else:
                raise ValueError("limit fill requires an opening cross or intrabar touch")
        if fill["executed_at"] != expected_time or fill["price_micros"] != expected_price:
            raise ValueError("fill time and price must match the completed-bar execution model")
        if cast("int", fill["notional_micros"]) != cast(
            "int", fill["price_micros"]
        ) * cast("int", fill["quantity"]):
            raise ValueError("fill notional must equal price times quantity")
        filled_by_order[order_id] = filled_by_order.get(order_id, 0) + cast(
            "int", fill["quantity"]
        )
    rejected = {
        order_id
        for order_id, order in order_by_id.items()
        if order["event_type"] == "order_rejected"
    }
    filled: set[str] = set()
    for order_id, quantity in filled_by_order.items():
        requested = cast("int", order_by_id[order_id]["quantity"])
        if quantity > requested:
            raise ValueError("fills must not exceed their order quantity")
        if quantity == requested and order_id not in cancelled:
            filled.add(order_id)
    active = set(order_by_id).difference(rejected, cancelled, filled)
    observed_counts = {
        "total": len(order_by_id),
        "active": len(active),
        "filled": len(filled),
        "rejected": len(rejected),
        "cancelled": len(cancelled),
    }
    completion_counts = {
        "total": completion.total_orders,
        "active": completion.active_orders,
        "filled": completion.filled_orders,
        "rejected": completion.rejected_orders,
        "cancelled": completion.cancelled_orders,
    }
    if observed_counts != completion_counts:
        raise ValueError("run_completed order counts must match imported order state")


def _money_pair(
    name: str,
    value: object,
    *,
    nonnegative: bool = False,
) -> dict[str, object]:
    amount = _decimal_payload(value, name=name, nonnegative=nonnegative)
    return {name: float(amount), f"{name}_micros": decimal_micros(amount)}


def _decimal_payload(
    value: object,
    *,
    name: str,
    positive: bool = False,
    nonnegative: bool = False,
) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an exact decimal string")
    result = decimal_value(
        value,
        name=name,
        positive=positive,
        nonnegative=nonnegative,
    )
    if decimal_string(result) != value:
        raise ValueError(f"{name} must use canonical decimal encoding")
    return result


def _choice(value: object, choices: set[str], *, name: str) -> str:
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"unsupported {name}")
    return value


def _json_integer(value: object, *, name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a JSON integer")
    if value < 0 or (positive and value == 0):
        requirement = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be {requirement}")
    return value


def _timestamp(value: object, *, name: str) -> pd.Timestamp:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be an RFC3339 string")
    try:
        result = pd.Timestamp(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an RFC3339 timestamp") from error
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    result = result.tz_convert("UTC")
    if result.nanosecond % 1_000:
        raise ValueError(f"{name} must not exceed microsecond precision")
    return result


def _typed_frame(
    rows: Sequence[Mapping[str, object]],
    dtypes: Mapping[str, str],
) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame({name: pd.Series(dtype=dtype) for name, dtype in dtypes.items()})
    result = pd.DataFrame(rows, columns=list(dtypes))
    for name, dtype in dtypes.items():
        result[name] = result[name].astype(pd.api.types.pandas_dtype(dtype))
    return result


def _resolve_scenario(
    scenario: TradingEngineScenario | str | Path | None,
) -> TradingEngineScenario | None:
    if scenario is None or isinstance(scenario, TradingEngineScenario):
        return scenario
    return read_scenario(scenario)


def _json_record(document: str, *, line_number: int) -> dict[str, object]:
    try:
        raw = json.loads(document, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid journal JSON on line {line_number}: {error.msg}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"journal record {line_number} must be a JSON object")
    return cast("dict[str, object]", raw)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _freeze_payload(value: object) -> object:
    if isinstance(value, dict):
        frozen = {
            str(key): _freeze_payload(item)
            for key, item in cast("dict[object, object]", value).items()
        }
        return MappingProxyType(frozen)
    if isinstance(value, list):
        return tuple(_freeze_payload(item) for item in cast("list[object]", value))
    return value
