"""Strictly import and reconcile Trading Engine audit journals."""

from __future__ import annotations

import hashlib
import json
import re
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
    metric_name,
    quantity_value,
    rfc3339_string,
)
from persistra.integrations.trading_engine.model import (
    CancelOrderIntent,
    EmitMetricIntent,
    ExecutionReplayResult,
    JournalEvent,
    RunCompletion,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetWeightsIntent,
    TradingEngineScenario,
)
from persistra.integrations.trading_engine.scenario import (
    scenario_from_json,
    scenario_to_json,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from decimal import Decimal

_HASH = re.compile(r"[0-9a-f]{64}")
_EVENT_FIELDS = {"engine_sequence", "run_id", "recorded_at", "event_type", "payload"}
_VALUATION_FIELDS = {
    "cash",
    "market_value",
    "cost_basis",
    "realized_pnl",
    "unrealized_pnl",
    "equity",
    "total_fees",
}
_NONNEGATIVE_VALUATION_FIELDS = {
    "cash",
    "market_value",
    "cost_basis",
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
    "eligible_after_slice_sequence",
    "filled_quantity",
    "filled_notional",
    "status",
    "rejection_reason",
}
_BAR_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
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
    "decision_slice_sequence": "Int64",
    "basis": "string",
    "instrument_id": "string",
    "weight": "Float64",
    "weight_micros": "Int64",
    "quantity": "Int64",
    "reference_price": "Float64",
    "reference_price_micros": "Int64",
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
    "eligible_after_slice_sequence": "Int64",
    "filled_quantity": "Int64",
    "filled_notional": "float64",
    "filled_notional_micros": "Int64",
    "status": "string",
    "rejection_reason": "string",
}
_CANCELLATION_DTYPES = {**_ORDER_DTYPES, "reason": "string"}
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
    "slice_sequence": "Int64",
}
_REJECTION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "event_type": "string",
    "order_id": "string",
    "instrument_id": "string",
    "reason": "string",
}
_CASH_LIMIT_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "order_id": "string",
    "instrument_id": "string",
    "requested_quantity": "Int64",
    "affordable_quantity": "Int64",
    "price": "float64",
    "price_micros": "Int64",
}
_VALUATION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
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
    scenario_sha256: str | None = None,
) -> ExecutionReplayResult:
    """Read one complete JSON Lines journal into normalized, reconciled frames."""
    journal_path = Path(path).expanduser()
    resolved_scenario, resolved_hash = _resolve_scenario(scenario)
    expected_hash = _optional_hash(scenario_sha256, name="scenario_sha256")
    if expected_hash is None:
        expected_hash = resolved_hash
    elif resolved_hash is not None and expected_hash != resolved_hash:
        raise ValueError("provided scenario_sha256 differs from the scenario artifact")
    lines = journal_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("audit journal must not be empty")
    if any(not line for line in lines):
        raise ValueError("audit journal must not contain blank records")

    bar_rows: list[dict[str, object]] = []
    target_rows: list[dict[str, object]] = []
    scheduled_outcomes: list[dict[str, object]] = []
    order_rows: list[dict[str, object]] = []
    fill_rows: list[dict[str, object]] = []
    cancellation_rows: list[dict[str, object]] = []
    rejection_rows: list[dict[str, object]] = []
    cash_limit_rows: list[dict[str, object]] = []
    valuation_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    events: list[JournalEvent] = []
    completion: RunCompletion | None = None
    run_id: str | None = None
    journal_hash: str | None = None
    previous_recorded_at: pd.Timestamp | None = None
    previous_slice_sequence = 0
    current_slice_sequence: int | None = None
    current_slice_recorded_at: pd.Timestamp | None = None

    for line_number, line in enumerate(lines, start=1):
        raw = _json_record(line, line_number=line_number)
        event = exact_fields(raw, _EVENT_FIELDS, name=f"journal record {line_number}")
        engine_sequence = quantity_value(
            event["engine_sequence"], name="engine_sequence", positive=True
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
        payload = event["payload"]
        if completion is not None:
            raise ValueError("run_completed must be the terminal journal record")
        if line_number == 1 and event_type != "run_started":
            raise ValueError("run_started must be the first journal record")
        if line_number > 1 and event_type == "run_started":
            raise ValueError("the journal must contain exactly one run_started record")

        if event_type == "run_started":
            item = exact_fields(payload, {"scenario_sha256"}, name="run_started payload")
            journal_hash = _hash(item["scenario_sha256"], name="scenario_sha256")
            if expected_hash is not None and journal_hash != expected_hash:
                raise ValueError("run_started scenario_sha256 differs from the scenario artifact")
        elif event_type == "market_slice_received":
            if current_slice_sequence is not None:
                raise ValueError("each market slice must end with valuation")
            rows = _slice_rows(payload, engine_sequence=engine_sequence, recorded_at=recorded_at)
            sequence = cast("int", rows[0]["slice_sequence"])
            if sequence <= previous_slice_sequence:
                raise ValueError("slice_sequence must increase globally")
            if cast("pd.Timestamp", rows[0]["received_at"]) != recorded_at:
                raise ValueError("market slice receipt must equal its audit recorded_at")
            previous_slice_sequence = sequence
            current_slice_sequence = sequence
            current_slice_recorded_at = recorded_at
            bar_rows.extend(rows)
        elif event_type == "run_completed":
            if current_slice_sequence is not None:
                raise ValueError("run_completed must follow the current slice valuation")
            completion = _completion(
                payload, engine_sequence=engine_sequence, recorded_at=recorded_at
            )
            if journal_hash is None or completion.scenario_sha256 != journal_hash:
                raise ValueError("terminal scenario_sha256 must match run_started")
        else:
            if current_slice_sequence is None or current_slice_recorded_at is None:
                raise ValueError("nonterminal journal events require an open market slice")
            if recorded_at != current_slice_recorded_at:
                raise ValueError("each slice event must use the market slice receipt clock")
            if event_type == "target_portfolio_requested":
                rows = _target_rows(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    decision_slice_sequence=current_slice_sequence,
                )
                target_rows.extend(rows)
                scheduled_outcomes.append(
                    {
                        "event_type": event_type,
                        "decision_slice_sequence": current_slice_sequence,
                        "engine_sequence": engine_sequence,
                        "targets": rows,
                    }
                )
            elif event_type in {"order_accepted", "order_rejected"}:
                order = _order_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    event_type=event_type,
                )
                if event_type == "order_accepted" and order["status"] != "working":
                    raise ValueError("order_accepted must contain working status")
                if event_type == "order_rejected" and order["status"] != "rejected":
                    raise ValueError("order_rejected must contain rejected status")
                if order["filled_quantity"] != 0 or order["filled_notional_micros"] != 0:
                    raise ValueError("submitted order snapshots must start with zero fill state")
                if order["created_sequence"] != engine_sequence:
                    raise ValueError("submitted order created_sequence must equal engine_sequence")
                if order["eligible_after_slice_sequence"] != current_slice_sequence:
                    raise ValueError("submitted order eligibility must equal the current slice")
                order_rows.append(order)
                if order["origin"] == "direct":
                    scheduled_outcomes.append(
                        {
                            "event_type": event_type,
                            "decision_slice_sequence": current_slice_sequence,
                            "engine_sequence": engine_sequence,
                            "order": order,
                        }
                    )
                if event_type == "order_rejected":
                    rejection_rows.append(_order_rejection_row(order))
            elif event_type == "order_cancelled":
                cancellation = _cancellation_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    slice_sequence=current_slice_sequence,
                )
                cancellation_rows.append(cancellation)
                if cancellation["reason"] == "strategy_requested":
                    scheduled_outcomes.append(
                        {
                            "event_type": event_type,
                            "decision_slice_sequence": current_slice_sequence,
                            "engine_sequence": engine_sequence,
                            "cancellation": cancellation,
                        }
                    )
            elif event_type == "fill_applied":
                fill_rows.append(
                    _fill_row(
                        payload,
                        engine_sequence=engine_sequence,
                        recorded_at=recorded_at,
                    )
                )
            elif event_type == "intent_rejected":
                rejection = _intent_rejection_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
                rejection_rows.append(rejection)
                scheduled_outcomes.append(
                    {
                        "event_type": event_type,
                        "decision_slice_sequence": current_slice_sequence,
                        "engine_sequence": engine_sequence,
                        "rejection": rejection,
                    }
                )
            elif event_type == "cash_limited":
                cash_limit_rows.append(
                    _cash_limit_row(
                        payload,
                        engine_sequence=engine_sequence,
                        recorded_at=recorded_at,
                        slice_sequence=current_slice_sequence,
                    )
                )
            elif event_type == "metric_emitted":
                metric = _metric_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
                metric_rows.append(metric)
                scheduled_outcomes.append(
                    {
                        "event_type": event_type,
                        "decision_slice_sequence": current_slice_sequence,
                        "engine_sequence": engine_sequence,
                        "metric": metric,
                    }
                )
            elif event_type == "valuation":
                valuation_rows.append(
                    _valuation_row(
                        payload,
                        engine_sequence=engine_sequence,
                        recorded_at=recorded_at,
                        slice_sequence=current_slice_sequence,
                    )
                )
                current_slice_sequence = None
                current_slice_recorded_at = None
            else:
                raise ValueError(f"unsupported journal event_type: {event_type}")
        events.append(
            JournalEvent(
                engine_sequence=engine_sequence,
                run_id=event_run_id,
                recorded_at=recorded_at,
                event_type=event_type,
                payload=cast("Mapping[str, Any]", _freeze_payload(payload)),
            )
        )

    if run_id is None or journal_hash is None or completion is None:
        raise ValueError("audit journal must start with run_started and end with run_completed")
    _validate_completion(
        completion,
        bars=bar_rows,
        orders=order_rows,
        fills=fill_rows,
        cancellations=cancellation_rows,
        cash_limits=cash_limit_rows,
        valuations=valuation_rows,
        scenario=resolved_scenario,
    )
    if resolved_scenario is not None:
        _validate_scenario_journal(
            resolved_scenario,
            run_id,
            bar_rows,
            scheduled_outcomes,
            order_rows,
            fill_rows,
            cancellation_rows,
            cash_limit_rows,
            valuation_rows,
        )
    initial_cash_micros = (
        None if resolved_scenario is None else decimal_micros(resolved_scenario.initial_cash)
    )
    return ExecutionReplayResult(
        run_id=run_id,
        scenario_sha256=journal_hash,
        bars=_typed_frame(bar_rows, _BAR_DTYPES),
        targets=_typed_frame(target_rows, _TARGET_DTYPES),
        orders=_typed_frame(order_rows, _ORDER_DTYPES),
        fills=_typed_frame(fill_rows, _FILL_DTYPES),
        cancellations=_typed_frame(cancellation_rows, _CANCELLATION_DTYPES),
        rejections=_typed_frame(rejection_rows, _REJECTION_DTYPES),
        cash_limits=_typed_frame(cash_limit_rows, _CASH_LIMIT_DTYPES),
        valuations=_typed_frame(valuation_rows, _VALUATION_DTYPES),
        metrics=_typed_frame(metric_rows, _METRIC_DTYPES),
        events=tuple(events),
        completion=completion,
        base_currency=None if resolved_scenario is None else resolved_scenario.base_currency,
        initial_cash=None if initial_cash_micros is None else initial_cash_micros / MICRO_SCALE,
        initial_cash_micros=initial_cash_micros,
    )


def _slice_rows(
    value: object, *, engine_sequence: int, recorded_at: pd.Timestamp
) -> list[dict[str, object]]:
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
        name="market_slice_received payload",
    )
    slice_sequence = quantity_value(item["slice_sequence"], name="slice_sequence", positive=True)
    start_at = _timestamp(item["start_at"], name="start_at")
    end_at = _timestamp(item["end_at"], name="end_at")
    available_at = _timestamp(item["available_at"], name="available_at")
    received_at = _timestamp(item["received_at"], name="received_at")
    if not start_at < end_at <= available_at <= received_at:
        raise ValueError("slice timestamps must satisfy start < end <= available <= received")
    bars = _array(item["bars"], name="bars")
    if not bars:
        raise ValueError("a market slice must contain at least one bar")
    rows = [
        _bar_row(
            bar,
            engine_sequence=engine_sequence,
            recorded_at=recorded_at,
            slice_sequence=slice_sequence,
            start_at=start_at,
            end_at=end_at,
            available_at=available_at,
            received_at=received_at,
        )
        for bar in bars
    ]
    identities = [cast("str", row["instrument_id"]) for row in rows]
    if len(identities) != len(set(identities)):
        raise ValueError("a market slice must contain each instrument exactly once")
    return rows


def _bar_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
    start_at: pd.Timestamp,
    end_at: pd.Timestamp,
    available_at: pd.Timestamp,
    received_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(
        value,
        {"instrument_id", "open", "high", "low", "close", "volume"},
        name="market slice bar",
    )
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
        "slice_sequence": slice_sequence,
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


def _target_rows(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    decision_slice_sequence: int,
) -> list[dict[str, object]]:
    item = exact_fields(value, {"basis", "targets"}, name="target_portfolio_requested payload")
    basis = _choice(item["basis"], {"weights", "quantities"}, name="target basis")
    targets = _array(item["targets"], name="targets")
    if not targets:
        raise ValueError("portfolio target must not be empty")
    rows: list[dict[str, object]] = []
    identities: set[str] = set()
    for value_target in targets:
        target = exact_fields(
            value_target,
            {"instrument_id", "weight", "quantity", "reference_price"},
            name="portfolio target",
        )
        instrument_id = identifier(target["instrument_id"], name="instrument_id")
        if instrument_id in identities:
            raise ValueError("portfolio target instruments must be unique")
        identities.add(instrument_id)
        weight = (
            None
            if target["weight"] is None
            else _decimal_payload(target["weight"], name="weight", nonnegative=True)
        )
        if weight is not None and decimal_micros(weight) > MICRO_SCALE:
            raise ValueError("target weight must not exceed one")
        if (basis == "weights") != (weight is not None):
            raise ValueError("target weight presence must match portfolio basis")
        reference = (
            None
            if target["reference_price"] is None
            else _decimal_payload(target["reference_price"], name="reference_price", positive=True)
        )
        if (basis == "weights") != (reference is not None):
            raise ValueError("reference_price presence must match portfolio basis")
        rows.append(
            {
                "engine_sequence": engine_sequence,
                "recorded_at": recorded_at,
                "decision_slice_sequence": decision_slice_sequence,
                "basis": basis,
                "instrument_id": instrument_id,
                "weight": pd.NA if weight is None else float(weight),
                "weight_micros": pd.NA if weight is None else decimal_micros(weight),
                "quantity": quantity_value(target["quantity"], name="quantity"),
                "reference_price": pd.NA if reference is None else float(reference),
                "reference_price_micros": pd.NA if reference is None else decimal_micros(reference),
            }
        )
    if basis == "weights" and sum(cast("int", row["weight_micros"]) for row in rows) > MICRO_SCALE:
        raise ValueError("target weights must sum to at most one")
    return rows


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
    limit_price = (
        None
        if item["limit_price"] is None
        else _decimal_payload(item["limit_price"], name="limit_price", positive=True)
    )
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
        "limit_price_micros": pd.NA if limit_price is None else decimal_micros(limit_price),
        "origin": _choice(item["origin"], {"direct", "target_rebalance"}, name="origin"),
        "created_at": created_at,
        "created_sequence": quantity_value(
            item["created_sequence"], name="created_sequence", positive=True
        ),
        "eligible_after_slice_sequence": quantity_value(
            item["eligible_after_slice_sequence"],
            name="eligible_after_slice_sequence",
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
    slice_sequence: int,
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
    order["slice_sequence"] = slice_sequence
    order["reason"] = _choice(
        item["reason"],
        {"strategy_requested", "target_replaced", "market_ioc"},
        name="cancellation reason",
    )
    return order


def _fill_row(
    value: object, *, engine_sequence: int, recorded_at: pd.Timestamp
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
            "slice_sequence",
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
        "slice_sequence": quantity_value(
            item["slice_sequence"], name="slice_sequence", positive=True
        ),
    }


def _cash_limit_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    item = exact_fields(
        value,
        {
            "order_id",
            "instrument_id",
            "requested_quantity",
            "affordable_quantity",
            "price",
        },
        name="cash_limited payload",
    )
    requested = quantity_value(item["requested_quantity"], name="requested_quantity", positive=True)
    affordable = quantity_value(item["affordable_quantity"], name="affordable_quantity")
    if affordable >= requested:
        raise ValueError("cash_limited affordable_quantity must be below requested_quantity")
    price = _decimal_payload(item["price"], name="price", positive=True)
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "order_id": identifier(item["order_id"], name="order_id"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "requested_quantity": requested,
        "affordable_quantity": affordable,
        "price": float(price),
        "price_micros": decimal_micros(price),
    }


def _valuation_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    item = exact_fields(value, _VALUATION_FIELDS, name="valuation payload")
    result: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
    }
    for name in _VALUATION_FIELDS:
        result.update(
            _money_pair(
                name,
                item[name],
                nonnegative=name in _NONNEGATIVE_VALUATION_FIELDS,
            )
        )
    return result


def _metric_row(
    value: object, *, engine_sequence: int, recorded_at: pd.Timestamp
) -> dict[str, object]:
    item = exact_fields(value, {"name", "value"}, name="metric_emitted payload")
    checked_name = metric_name(item["name"])
    if not isinstance(item["value"], str):
        raise ValueError("metric value must be a string")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "name": checked_name,
        "value": item["value"],
    }


def _intent_rejection_row(
    value: object, *, engine_sequence: int, recorded_at: pd.Timestamp
) -> dict[str, object]:
    item = exact_fields(value, {"reason"}, name="intent_rejected payload")
    reason = item["reason"]
    if not isinstance(reason, str) or not reason:
        raise ValueError("intent rejection reason must be a nonempty string")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "event_type": "intent_rejected",
        "order_id": pd.NA,
        "instrument_id": pd.NA,
        "reason": reason,
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


def _completion(value: object, *, engine_sequence: int, recorded_at: pd.Timestamp) -> RunCompletion:
    item = exact_fields(
        value,
        {"scenario_sha256", "valuation", "order_counts"},
        name="run_completed payload",
    )
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
                nonnegative=name in _NONNEGATIVE_VALUATION_FIELDS,
            )
        )
        for name in _VALUATION_FIELDS
    }
    orders = {name: _json_integer(counts[name], name=f"{name} order count") for name in counts}
    if (
        sum(orders[name] for name in ("active", "filled", "rejected", "cancelled"))
        != orders["total"]
    ):
        raise ValueError("terminal order counts must reconcile to total")
    return RunCompletion(
        recorded_at=recorded_at,
        engine_sequence=engine_sequence,
        scenario_sha256=_hash(item["scenario_sha256"], name="scenario_sha256"),
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


def _validate_scenario_journal(
    scenario: TradingEngineScenario,
    run_id: str,
    bars: Sequence[dict[str, object]],
    scheduled_outcomes: Sequence[Mapping[str, object]],
    orders: Sequence[dict[str, object]],
    fills: Sequence[dict[str, object]],
    cancellations: Sequence[dict[str, object]],
    cash_limits: Sequence[dict[str, object]],
    valuations: Sequence[dict[str, object]],
) -> None:
    if scenario.run_id != run_id:
        raise ValueError("scenario and journal run_id differ")
    expected_bars = {
        (market_slice.slice_sequence, bar.instrument_id): (market_slice, bar)
        for market_slice in scenario.slices
        for bar in market_slice.bars
    }
    observed_bars = {
        (cast("int", row["slice_sequence"]), cast("str", row["instrument_id"])): row for row in bars
    }
    if set(expected_bars) != set(observed_bars):
        raise ValueError("scenario and journal market slice instruments differ")
    for key, (market_slice, expected) in expected_bars.items():
        observed = observed_bars[key]
        observed_volume = observed["volume"]
        normalized_volume = None if observed_volume is pd.NA else cast("int", observed_volume)
        if (
            market_slice.slice_sequence != observed["slice_sequence"]
            or market_slice.start_at != observed["start_at"]
            or market_slice.end_at != observed["end_at"]
            or market_slice.available_at != observed["available_at"]
            or market_slice.received_at != observed["received_at"]
            or expected.instrument_id != observed["instrument_id"]
            or decimal_micros(expected.open) != observed["open_micros"]
            or decimal_micros(expected.high) != observed["high_micros"]
            or decimal_micros(expected.low) != observed["low_micros"]
            or decimal_micros(expected.close) != observed["close_micros"]
            or expected.volume != normalized_volume
        ):
            raise ValueError("scenario and journal market slices differ")
    expected_intents = [
        (item.after_slice_sequence, intent) for item in scenario.schedule for intent in item.intents
    ]
    if len(expected_intents) != len(scheduled_outcomes):
        raise ValueError("scenario and journal scheduled intent outcome counts differ")
    bar_by_key = observed_bars
    valuation_by_sequence = {cast("int", row["slice_sequence"]): row for row in valuations}
    for (sequence, intent), outcome in zip(expected_intents, scheduled_outcomes, strict=True):
        if outcome["decision_slice_sequence"] != sequence:
            raise ValueError("scenario and journal scheduled intent order differs")
        if isinstance(intent, TargetWeightsIntent | TargetQuantitiesIntent):
            _validate_scheduled_target(
                scenario,
                sequence,
                intent,
                outcome,
                bar_by_key=bar_by_key,
                valuation_by_sequence=valuation_by_sequence,
            )
        elif isinstance(intent, SubmitOrderIntent):
            _validate_scheduled_submission(intent, outcome)
        elif isinstance(intent, CancelOrderIntent):
            _validate_scheduled_cancellation(
                intent,
                outcome,
                orders=orders,
                fills=fills,
                cancellations=cancellations,
            )
        else:
            _validate_scheduled_metric(intent, outcome)
    _validate_target_replacement_cancellations(
        scheduled_outcomes,
        orders=orders,
        fills=fills,
        cancellations=cancellations,
    )
    _validate_scheduled_event_phases(
        scenario,
        scheduled_outcomes,
        orders=orders,
        fills=fills,
        cancellations=cancellations,
        cash_limits=cash_limits,
    )
    _validate_execution_values(
        scenario,
        bars=bars,
        orders=orders,
        fills=fills,
        cancellations=cancellations,
        cash_limits=cash_limits,
        valuations=valuations,
    )


def _validate_scheduled_target(
    scenario: TradingEngineScenario,
    sequence: int,
    intent: TargetWeightsIntent | TargetQuantitiesIntent,
    outcome: Mapping[str, object],
    *,
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    valuation_by_sequence: Mapping[int, Mapping[str, object]],
) -> None:
    derived_quantities: dict[str, int] = {}
    if isinstance(intent, TargetWeightsIntent):
        for target in intent.targets:
            reference = cast("int", bar_by_key[(sequence, target.instrument_id)]["close_micros"])
            equity = cast("int", valuation_by_sequence[sequence]["equity_micros"])
            weight = decimal_micros(cast("Decimal", target.weight))
            lot = next(
                item.lot_size
                for item in scenario.instruments
                if item.instrument_id == target.instrument_id
            )
            quantity = equity * weight // (MICRO_SCALE * reference)
            derived_quantities[target.instrument_id] = quantity - quantity % lot
    expected_rejection = bool(derived_quantities) and any(
        quantity > scenario.risk.max_position for quantity in derived_quantities.values()
    )
    if expected_rejection:
        if outcome["event_type"] != "intent_rejected":
            raise ValueError("journal portfolio target outcome differs from engine-owned sizing")
        rejection = cast("Mapping[str, object]", outcome["rejection"])
        if rejection["reason"] != "weight-derived target exceeds the maximum position":
            raise ValueError("journal portfolio target rejection reason differs")
        return
    if outcome["event_type"] != "target_portfolio_requested":
        raise ValueError("journal portfolio target outcome differs from engine-owned sizing")
    observed_group = cast("Sequence[dict[str, object]]", outcome["targets"])
    observed_by_id = {cast("str", row["instrument_id"]): row for row in observed_group}
    expected_ids = {target.instrument_id for target in intent.targets}
    if set(observed_by_id) != expected_ids:
        raise ValueError("scenario and journal portfolio target instruments differ")
    if isinstance(intent, TargetWeightsIntent):
        for target in intent.targets:
            observed = observed_by_id[target.instrument_id]
            _validate_target_reference(observed, sequence, target.instrument_id, bar_by_key)
            if observed["basis"] != "weights" or observed["weight_micros"] != decimal_micros(
                cast("Decimal", target.weight)
            ):
                raise ValueError("scenario and journal target weights differ")
            if observed["quantity"] != derived_quantities[target.instrument_id]:
                raise ValueError("journal target quantity differs from engine-owned sizing")
    else:
        for target in intent.targets:
            observed = observed_by_id[target.instrument_id]
            _validate_target_reference(observed, sequence, target.instrument_id, bar_by_key)
            if observed["basis"] != "quantities" or observed["quantity"] != target.quantity:
                raise ValueError("scenario and journal target quantities differ")


def _validate_scheduled_submission(
    intent: SubmitOrderIntent,
    outcome: Mapping[str, object],
) -> None:
    if outcome["event_type"] not in {"order_accepted", "order_rejected"}:
        raise ValueError("scenario submit_order outcome differs from the journal")
    order = cast("Mapping[str, object]", outcome["order"])
    expected_limit = (
        pd.NA if intent.limit_price is None else decimal_micros(cast("Decimal", intent.limit_price))
    )
    if (
        order["origin"] != "direct"
        or order["instrument_id"] != intent.instrument_id
        or order["side"] != intent.side
        or order["quantity"] != intent.quantity
        or order["order_kind"] != intent.order_kind
        or not _imported_values_equal(order["limit_price_micros"], expected_limit)
    ):
        raise ValueError("scenario submit_order request differs from the journal")


def _validate_scheduled_cancellation(
    intent: CancelOrderIntent,
    outcome: Mapping[str, object],
    *,
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> None:
    outcome_sequence = cast("int", outcome["engine_sequence"])
    status = _order_status_before(
        intent.order_id,
        outcome_sequence,
        orders=orders,
        fills=fills,
        cancellations=cancellations,
    )
    if status == "active":
        if outcome["event_type"] != "order_cancelled":
            raise ValueError("active cancel_order must emit order_cancelled")
        cancellation = cast("Mapping[str, object]", outcome["cancellation"])
        if (
            cancellation["order_id"] != intent.order_id
            or cancellation["reason"] != "strategy_requested"
        ):
            raise ValueError("scenario cancel_order request differs from the journal")
        return
    expected_reason = (
        "cannot cancel an unknown order"
        if status == "unknown"
        else "cannot cancel a terminal order"
    )
    if outcome["event_type"] != "intent_rejected":
        raise ValueError("invalid cancel_order must emit intent_rejected")
    rejection = cast("Mapping[str, object]", outcome["rejection"])
    if rejection["reason"] != expected_reason:
        raise ValueError("cancel_order rejection reason differs from runtime state")


def _validate_scheduled_metric(
    intent: EmitMetricIntent,
    outcome: Mapping[str, object],
) -> None:
    valid_name = bool(intent.name) and intent.name.strip(" \t\n\r\f") == intent.name
    if valid_name:
        if outcome["event_type"] != "metric_emitted":
            raise ValueError("valid emit_metric must emit metric_emitted")
        metric = cast("Mapping[str, object]", outcome["metric"])
        if metric["name"] != intent.name or metric["value"] != intent.value:
            raise ValueError("scenario emit_metric payload differs from the journal")
        return
    if outcome["event_type"] != "intent_rejected":
        raise ValueError("invalid emit_metric must emit intent_rejected")
    rejection = cast("Mapping[str, object]", outcome["rejection"])
    if rejection["reason"] != "metric name must be a nonempty trimmed string":
        raise ValueError("emit_metric rejection reason differs from runtime validation")


def _order_status_before(
    order_id: str,
    engine_sequence: int,
    *,
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> str:
    submitted = next(
        (
            order
            for order in orders
            if order["order_id"] == order_id
            and cast("int", order["engine_sequence"]) < engine_sequence
        ),
        None,
    )
    if submitted is None:
        return "unknown"
    if submitted["event_type"] == "order_rejected" or any(
        cancellation["order_id"] == order_id
        and cast("int", cancellation["engine_sequence"]) < engine_sequence
        for cancellation in cancellations
    ):
        return "terminal"
    filled = sum(
        cast("int", fill["quantity"])
        for fill in fills
        if fill["order_id"] == order_id and cast("int", fill["engine_sequence"]) < engine_sequence
    )
    return "terminal" if filled >= cast("int", submitted["quantity"]) else "active"


def _working_orders_before(
    engine_sequence: int,
    *,
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> list[Mapping[str, object]]:
    return [
        order
        for order in orders
        if order["event_type"] == "order_accepted"
        and cast("int", order["engine_sequence"]) < engine_sequence
        and _order_status_before(
            cast("str", order["order_id"]),
            engine_sequence,
            orders=orders,
            fills=fills,
            cancellations=cancellations,
        )
        == "active"
    ]


def _validate_target_replacement_cancellations(
    scheduled_outcomes: Sequence[Mapping[str, object]],
    *,
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> None:
    cancellation_by_sequence = {
        cast("int", cancellation["engine_sequence"]): cancellation for cancellation in cancellations
    }
    claimed: set[int] = set()
    for outcome in scheduled_outcomes:
        if outcome["event_type"] != "target_portfolio_requested":
            continue
        request_sequence = cast("int", outcome["engine_sequence"])
        expected = sorted(
            (
                order
                for order in _working_orders_before(
                    request_sequence,
                    orders=orders,
                    fills=fills,
                    cancellations=cancellations,
                )
                if order["origin"] == "target_rebalance"
            ),
            key=lambda order: (
                cast("int", order["created_sequence"]),
                cast("str", order["order_id"]),
            ),
        )
        for offset, order in enumerate(expected, start=1):
            sequence = request_sequence + offset
            cancellation = cancellation_by_sequence.get(sequence)
            if (
                cancellation is None
                or cancellation["reason"] != "target_replaced"
                or cancellation["order_id"] != order["order_id"]
            ):
                raise ValueError(
                    "portfolio target did not replace every active target order in order"
                )
            claimed.add(sequence)
    observed = {
        cast("int", cancellation["engine_sequence"])
        for cancellation in cancellations
        if cancellation["reason"] == "target_replaced"
    }
    if observed != claimed:
        raise ValueError("target_replaced cancellation does not follow a portfolio target")


def _validate_scheduled_event_phases(
    scenario: TradingEngineScenario,
    scheduled_outcomes: Sequence[Mapping[str, object]],
    *,
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
    cash_limits: Sequence[Mapping[str, object]],
) -> None:
    outcomes_by_slice: dict[int, list[Mapping[str, object]]] = {}
    for outcome in scheduled_outcomes:
        outcomes_by_slice.setdefault(cast("int", outcome["decision_slice_sequence"]), []).append(
            outcome
        )
    for scheduled in scenario.schedule:
        if not scheduled.intents:
            continue
        sequence = scheduled.after_slice_sequence
        outcomes = outcomes_by_slice[sequence]
        first_outcome = cast("int", outcomes[0]["engine_sequence"])
        last_scheduled_event = max(cast("int", item["engine_sequence"]) for item in outcomes)
        replacement_sequences = [
            cast("int", item["engine_sequence"])
            for item in cancellations
            if item["slice_sequence"] == sequence and item["reason"] == "target_replaced"
        ]
        if replacement_sequences:
            last_scheduled_event = max(last_scheduled_event, *replacement_sequences)
        execution_sequences = [
            cast("int", item["engine_sequence"])
            for item in fills
            if item["slice_sequence"] == sequence
        ]
        execution_sequences.extend(
            cast("int", item["engine_sequence"])
            for item in cash_limits
            if item["slice_sequence"] == sequence
        )
        execution_sequences.extend(
            cast("int", item["engine_sequence"])
            for item in cancellations
            if item["slice_sequence"] == sequence and item["reason"] == "market_ioc"
        )
        if any(item >= first_outcome for item in execution_sequences):
            raise ValueError("slice execution events must precede scheduled intent outcomes")
        target_orders = sorted(
            (
                order
                for order in orders
                if order["origin"] == "target_rebalance"
                and order["eligible_after_slice_sequence"] == sequence
            ),
            key=lambda order: cast("int", order["engine_sequence"]),
        )
        if any(
            cast("int", order["engine_sequence"]) <= last_scheduled_event for order in target_orders
        ):
            raise ValueError("persistent target orders must follow all scheduled intent outcomes")
        instruments = [cast("str", order["instrument_id"]) for order in target_orders]
        if instruments != sorted(instruments):
            raise ValueError("persistent target orders must use instrument identifier order")


def _validate_target_reference(
    observed: Mapping[str, object],
    sequence: int,
    instrument_id: str,
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
) -> None:
    if observed["decision_slice_sequence"] != sequence:
        raise ValueError("scenario and journal target schedule differ")
    reference = bar_by_key[(sequence, instrument_id)]["close_micros"]
    if (
        observed["reference_price_micros"] is not pd.NA
        and observed["reference_price_micros"] != reference
    ):
        raise ValueError("portfolio target reference price differs from slice close")


def _validate_execution_values(
    scenario: TradingEngineScenario,
    *,
    bars: Sequence[dict[str, object]],
    orders: Sequence[dict[str, object]],
    fills: Sequence[dict[str, object]],
    cancellations: Sequence[dict[str, object]],
    cash_limits: Sequence[dict[str, object]],
    valuations: Sequence[dict[str, object]],
) -> None:
    instrument_by_id = {item.instrument_id: item for item in scenario.instruments}
    order_by_id = {cast("str", item["order_id"]): item for item in orders}
    bar_by_key = {
        (cast("int", item["slice_sequence"]), cast("str", item["instrument_id"])): item
        for item in bars
    }
    for order in orders:
        instrument = instrument_by_id.get(cast("str", order["instrument_id"]))
        if instrument is None:
            raise ValueError("order refers to an unknown scenario instrument")
        if cast("int", order["quantity"]) % instrument.lot_size:
            raise ValueError("order quantity is not lot aligned")
        if cast("int", order["quantity"]) > scenario.risk.max_order_quantity:
            qualifier = "accepted " if order["event_type"] == "order_accepted" else ""
            raise ValueError(f"{qualifier}order exceeds max_order_quantity")
        limit = order["limit_price_micros"]
        if limit is not pd.NA and cast("int", limit) % decimal_micros(
            cast("Decimal", instrument.tick_size)
        ):
            raise ValueError("order limit price is not tick aligned")
    capacity_used: dict[tuple[int, str], int] = {}
    fixed_fee = decimal_micros(cast("Decimal", scenario.execution.fixed_fee))
    for fill in fills:
        instrument = instrument_by_id[cast("str", fill["instrument_id"])]
        quantity = cast("int", fill["quantity"])
        if quantity % instrument.lot_size:
            raise ValueError("fill quantity is not lot aligned")
        tick = decimal_micros(cast("Decimal", instrument.tick_size))
        if cast("int", fill["price_micros"]) % tick:
            raise ValueError("fill price is not tick aligned")
        expected_fee = fixed_fee + _ceil_fraction(
            cast("int", fill["notional_micros"]) * scenario.execution.fee_bps,
            10_000,
        )
        if cast("int", fill["fee_micros"]) != expected_fee:
            raise ValueError("fill fee differs from the scenario execution policy")
        key = (cast("int", fill["slice_sequence"]), cast("str", fill["instrument_id"]))
        capacity_used[key] = capacity_used.get(key, 0) + quantity
    for key, used in capacity_used.items():
        bar = bar_by_key[key]
        if bar["volume"] is pd.NA:
            continue
        instrument = instrument_by_id[key[1]]
        capacity = cast("int", bar["volume"]) * scenario.execution.participation_bps // 10_000
        capacity -= capacity % instrument.lot_size
        if used > capacity:
            raise ValueError("fills exceed the scenario slice participation capacity")
    cash_limit_keys: set[tuple[str, int]] = set()
    for limited in cash_limits:
        cash_limit_key = (
            cast("str", limited["order_id"]),
            cast("int", limited["slice_sequence"]),
        )
        if cash_limit_key in cash_limit_keys:
            raise ValueError("cash_limited must occur at most once per order and slice")
        cash_limit_keys.add(cash_limit_key)
        order = order_by_id.get(cast("str", limited["order_id"]))
        if order is None or order["instrument_id"] != limited["instrument_id"]:
            raise ValueError("cash_limited must refer to an imported matching order")
        if order["event_type"] != "order_accepted" or order["side"] != "buy":
            raise ValueError("cash_limited must refer to an accepted buy order")
        instrument = instrument_by_id[cast("str", limited["instrument_id"])]
        if (
            cast("int", limited["requested_quantity"]) % instrument.lot_size
            or cast("int", limited["affordable_quantity"]) % instrument.lot_size
        ):
            raise ValueError("cash_limited quantities must be lot aligned")
        if cast("int", limited["price_micros"]) % decimal_micros(
            cast("Decimal", instrument.tick_size)
        ):
            raise ValueError("cash_limited price must be tick aligned")
        prior_order_quantity = sum(
            cast("int", fill["quantity"])
            for fill in fills
            if fill["order_id"] == limited["order_id"]
            and cast("int", fill["engine_sequence"]) < cast("int", limited["engine_sequence"])
        )
        remaining_quantity = cast("int", order["quantity"]) - prior_order_quantity
        if cast("int", limited["requested_quantity"]) > remaining_quantity:
            raise ValueError("cash_limited requested quantity exceeds the remaining order")
        matching_fills = [
            fill
            for fill in fills
            if fill["order_id"] == limited["order_id"]
            and fill["slice_sequence"] == limited["slice_sequence"]
        ]
        applied = sum(cast("int", fill["quantity"]) for fill in matching_fills)
        if applied != limited["affordable_quantity"]:
            raise ValueError("cash_limited affordable quantity must match its same-slice fill")
        if matching_fills and (
            len(matching_fills) != 1
            or matching_fills[0]["side"] != "buy"
            or cast("int", matching_fills[0]["engine_sequence"])
            <= cast("int", limited["engine_sequence"])
            or matching_fills[0]["price_micros"] != limited["price_micros"]
        ):
            raise ValueError("cash_limited fill must follow the event at its audited price")
        cash_before = decimal_micros(scenario.initial_cash)
        for prior in fills:
            if cast("int", prior["engine_sequence"]) >= cast("int", limited["engine_sequence"]):
                continue
            prior_notional = cast("int", prior["notional_micros"])
            prior_fee = cast("int", prior["fee_micros"])
            cash_before += (
                prior_notional - prior_fee
                if prior["side"] == "sell"
                else -prior_notional - prior_fee
            )
        expected_affordable = _affordable_quantity(
            cash_before,
            requested=cast("int", limited["requested_quantity"]),
            price_micros=cast("int", limited["price_micros"]),
            lot_size=instrument.lot_size,
            fixed_fee_micros=fixed_fee,
            fee_bps=scenario.execution.fee_bps,
        )
        if limited["affordable_quantity"] != expected_affordable:
            raise ValueError("cash_limited affordable quantity does not reconcile to cash")
    _validate_projected_risk(
        scenario,
        orders=orders,
        fills=fills,
        cancellations=cancellations,
    )
    cash = decimal_micros(scenario.initial_cash)
    fees = 0
    positions = {instrument_id: 0 for instrument_id in instrument_by_id}
    position_basis = {instrument_id: 0 for instrument_id in instrument_by_id}
    realized_pnl = 0
    fills_by_slice: dict[int, list[dict[str, object]]] = {}
    for fill in fills:
        fills_by_slice.setdefault(cast("int", fill["slice_sequence"]), []).append(fill)
    for valuation in valuations:
        sequence = cast("int", valuation["slice_sequence"])
        saw_buy = False
        for fill in sorted(
            fills_by_slice.get(sequence, []),
            key=lambda item: cast("int", item["engine_sequence"]),
        ):
            notional = cast("int", fill["notional_micros"])
            fee = cast("int", fill["fee_micros"])
            quantity = cast("int", fill["quantity"])
            instrument_id = cast("str", fill["instrument_id"])
            if fill["side"] == "buy":
                saw_buy = True
                cash -= notional + fee
                positions[instrument_id] += quantity
                position_basis[instrument_id] += notional + fee
            else:
                if saw_buy:
                    raise ValueError("sell fills must precede buy fills within each slice")
                current_quantity = positions[instrument_id]
                current_basis = position_basis[instrument_id]
                if quantity > current_quantity:
                    raise ValueError("engine positions must not become negative")
                remaining = current_quantity - quantity
                removed_basis = (
                    current_basis
                    if remaining == 0
                    else current_basis * quantity // current_quantity
                )
                cash += notional - fee
                positions[instrument_id] = remaining
                position_basis[instrument_id] -= removed_basis
                realized_pnl += notional - fee - removed_basis
            fees += fee
            if cash < 0:
                raise ValueError("engine cash must not become negative")
        market_value = sum(
            positions[instrument_id]
            * cast("int", bar_by_key[(sequence, instrument_id)]["close_micros"])
            for instrument_id in positions
        )
        cost_basis = sum(position_basis.values())
        unrealized_pnl = market_value - cost_basis
        equity = cash + market_value
        expected = {
            "cash_micros": cash,
            "market_value_micros": market_value,
            "cost_basis_micros": cost_basis,
            "realized_pnl_micros": realized_pnl,
            "unrealized_pnl_micros": unrealized_pnl,
            "equity_micros": equity,
            "total_fees_micros": fees,
        }
        if any(valuation[name] != value for name, value in expected.items()):
            raise ValueError("valuation fields do not reconcile to imported fills and marks")


def _validate_projected_risk(
    scenario: TradingEngineScenario,
    *,
    orders: Sequence[dict[str, object]],
    fills: Sequence[dict[str, object]],
    cancellations: Sequence[dict[str, object]],
) -> None:
    positions = {item.instrument_id: 0 for item in scenario.instruments}
    working: dict[str, tuple[str, str, int]] = {}
    events = [(cast("int", item["engine_sequence"]), "order", item) for item in orders] + [
        (cast("int", item["engine_sequence"]), "fill", item) for item in fills
    ]
    events.extend(
        (cast("int", item["engine_sequence"]), "cancellation", item) for item in cancellations
    )
    next_order_number = 1
    for _sequence, event_type, event in sorted(events, key=lambda item: item[0]):
        if event_type == "order":
            expected_id = f"{scenario.run_id}-order-{next_order_number:012d}"
            next_order_number += 1
            if event["order_id"] != expected_id:
                raise ValueError("order identifiers must follow the deterministic engine sequence")
            order_id = cast("str", event["order_id"])
            instrument_id = cast("str", event["instrument_id"])
            side = cast("str", event["side"])
            quantity = cast("int", event["quantity"])
            pending = sum(
                remaining
                for working_instrument, working_side, remaining in working.values()
                if working_instrument == instrument_id and working_side == side
            )
            rejection_reason: str | None = None
            if side == "buy" and (
                positions[instrument_id] + pending + quantity > scenario.risk.max_position
            ):
                rejection_reason = "order would exceed the maximum long position"
            elif side == "sell" and pending + quantity > positions[instrument_id]:
                rejection_reason = "sell order would exceed the available long position"
            if rejection_reason is None and event["event_type"] != "order_accepted":
                raise ValueError("order was rejected despite passing runtime risk checks")
            if rejection_reason is not None:
                if event["event_type"] == "order_accepted":
                    if side == "buy":
                        raise ValueError("accepted buys exceed projected max_position")
                    raise ValueError("accepted sells exceed the available long position")
                if event["rejection_reason"] != rejection_reason:
                    raise ValueError("order outcome differs from runtime risk checks")
                continue
            working[order_id] = (instrument_id, side, quantity)
        elif event_type == "fill":
            order_id = cast("str", event["order_id"])
            order_state = working.get(order_id)
            if order_state is None:
                raise ValueError("fill does not refer to a working accepted order")
            instrument_id, side, remaining = order_state
            quantity = cast("int", event["quantity"])
            if quantity > remaining:
                raise ValueError("fills exceed their working order quantity")
            positions[instrument_id] += quantity if side == "buy" else -quantity
            if positions[instrument_id] < 0:
                raise ValueError("engine positions must not become negative")
            if positions[instrument_id] > scenario.risk.max_position:
                raise ValueError("engine positions must not exceed max_position")
            remaining -= quantity
            if remaining:
                working[order_id] = (instrument_id, side, remaining)
            else:
                del working[order_id]
        else:
            if working.pop(cast("str", event["order_id"]), None) is None:
                raise ValueError("only a working order may be cancelled")


def _validate_completion(
    completion: RunCompletion,
    *,
    bars: Sequence[Mapping[str, object]],
    orders: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
    cash_limits: Sequence[Mapping[str, object]],
    valuations: Sequence[Mapping[str, object]],
    scenario: TradingEngineScenario | None,
) -> None:
    del cash_limits
    slice_rows: dict[int, Mapping[str, object]] = {}
    for bar in bars:
        slice_rows.setdefault(cast("int", bar["slice_sequence"]), bar)
    if len(valuations) != len(slice_rows):
        raise ValueError("a complete journal must contain one valuation event per market slice")
    for market_slice, valuation in zip(slice_rows.values(), valuations, strict=True):
        if valuation["recorded_at"] != market_slice["received_at"]:
            raise ValueError("each valuation must match its market slice receipt")
        if valuation["slice_sequence"] != market_slice["slice_sequence"]:
            raise ValueError("each valuation must identify its market slice")
        if cast("int", valuation["engine_sequence"]) <= cast(
            "int", market_slice["engine_sequence"]
        ):
            raise ValueError("each valuation must follow its market slice event")
    expected_completion_time = (
        pd.Timestamp("1970-01-01T00:00:00Z")
        if not slice_rows
        else cast("pd.Timestamp", next(reversed(slice_rows.values()))["received_at"])
    )
    if completion.recorded_at != expected_completion_time:
        raise ValueError("run_completed recorded_at must match the terminal replay clock")
    if not slice_rows and scenario is not None:
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
    for cancellation in cancellations:
        order_id = cast("str", cancellation["order_id"])
        accepted = order_by_id[order_id]
        if accepted["event_type"] != "order_accepted":
            raise ValueError("only accepted orders may be cancelled")
        immutable_fields = {
            "order_id",
            "instrument_id",
            "side",
            "quantity",
            "order_kind",
            "limit_price_micros",
            "origin",
            "created_at",
            "created_sequence",
            "eligible_after_slice_sequence",
            "rejection_reason",
        }
        if any(
            not _imported_values_equal(cancellation[name], accepted[name])
            for name in immutable_fields
        ):
            raise ValueError("cancelled order state differs from its accepted order")
        preceding_fills = [
            fill
            for fill in fills
            if fill["order_id"] == order_id
            and cast("int", fill["engine_sequence"]) < cast("int", cancellation["engine_sequence"])
        ]
        if any(
            fill["order_id"] == order_id
            and cast("int", fill["engine_sequence"]) > cast("int", cancellation["engine_sequence"])
            for fill in fills
        ):
            raise ValueError("fills must not follow order cancellation")
        if cancellation["filled_quantity"] != sum(
            cast("int", fill["quantity"]) for fill in preceding_fills
        ) or cancellation["filled_notional_micros"] != sum(
            cast("int", fill["notional_micros"]) for fill in preceding_fills
        ):
            raise ValueError("cancelled order fill state does not reconcile to imported fills")
    filled_by_order: dict[str, int] = {}
    bar_by_key = {
        (cast("int", item["slice_sequence"]), cast("str", item["instrument_id"])): item
        for item in bars
    }
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
        if fill["instrument_id"] != order["instrument_id"] or fill["side"] != order["side"]:
            raise ValueError("fill instrument and side must match its order")
        sequence = cast("int", fill["slice_sequence"])
        fill_bar = bar_by_key.get((sequence, cast("str", fill["instrument_id"])))
        if fill_bar is None:
            raise ValueError("fill must refer to its instrument in an imported market slice")
        if sequence <= cast("int", order["eligible_after_slice_sequence"]):
            raise ValueError("fill slice must follow order eligibility")
        if fill["recorded_at"] != fill_bar["received_at"]:
            raise ValueError("fill must use its market slice receipt clock")
        expected_time: object
        expected_price: object
        if order["order_kind"] == "market":
            expected_time = fill_bar["start_at"]
            expected_price = fill_bar["open_micros"]
        else:
            limit = cast("int", order["limit_price_micros"])
            opening = cast("int", fill_bar["open_micros"])
            crosses_open = (order["side"] == "buy" and opening <= limit) or (
                order["side"] == "sell" and opening >= limit
            )
            touches = (order["side"] == "buy" and cast("int", fill_bar["low_micros"]) <= limit) or (
                order["side"] == "sell" and cast("int", fill_bar["high_micros"]) >= limit
            )
            if crosses_open:
                expected_time = fill_bar["start_at"]
                expected_price = opening
            elif touches:
                expected_time = fill_bar["end_at"]
                expected_price = limit
            else:
                raise ValueError("limit fill requires an opening cross or intrabar touch")
        if fill["executed_at"] != expected_time or fill["price_micros"] != expected_price:
            raise ValueError("fill time and price must match the completed-slice model")
        if cast("int", fill["notional_micros"]) != cast("int", fill["price_micros"]) * cast(
            "int", fill["quantity"]
        ):
            raise ValueError("fill notional must equal price times quantity")
        filled_by_order[order_id] = filled_by_order.get(order_id, 0) + cast("int", fill["quantity"])
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


def _money_pair(name: str, value: object, *, nonnegative: bool = False) -> dict[str, object]:
    amount = _decimal_payload(value, name=name, nonnegative=nonnegative)
    return {name: float(amount), f"{name}_micros": decimal_micros(amount)}


def _imported_values_equal(left: object, right: object) -> bool:
    if left is pd.NA or right is pd.NA:
        return left is pd.NA and right is pd.NA
    return bool(left == right)


def _decimal_payload(
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


def _json_integer(value: object, *, name: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be a JSON integer")
    if value < 0 or (positive and value == 0):
        requirement = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be {requirement}")
    return value


def _timestamp(value: object, *, name: str) -> pd.Timestamp:
    checked = rfc3339_string(value, name=name)
    try:
        result = pd.Timestamp(checked)
    except ValueError as error:
        raise ValueError(f"{name} must be an RFC3339 timestamp") from error
    if pd.isna(result) or result.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    result = result.tz_convert("UTC")
    if result.nanosecond % 1_000:
        raise ValueError(f"{name} must not exceed microsecond precision")
    return result


def _typed_frame(rows: Sequence[Mapping[str, object]], dtypes: Mapping[str, str]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame({name: pd.Series(dtype=dtype) for name, dtype in dtypes.items()})
    result = pd.DataFrame(rows, columns=list(dtypes))
    for name, dtype in dtypes.items():
        result[name] = result[name].astype(pd.api.types.pandas_dtype(dtype))
    return result


def _resolve_scenario(
    scenario: TradingEngineScenario | str | Path | None,
) -> tuple[TradingEngineScenario | None, str | None]:
    if scenario is None:
        return None, None
    if isinstance(scenario, TradingEngineScenario):
        document = scenario_to_json(scenario).encode()
        return scenario, hashlib.sha256(document).hexdigest()
    path = Path(scenario).expanduser()
    document = path.read_bytes()
    return scenario_from_json(document.decode("utf-8")), hashlib.sha256(document).hexdigest()


def _json_record(document: str, *, line_number: int) -> dict[str, object]:
    try:
        raw = json.loads(document, object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid journal JSON on line {line_number}: {error.msg}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"journal record {line_number} must be a JSON object")
    return cast("dict[str, object]", raw)


def _array(value: object, *, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return cast("list[object]", value)


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


def _hash(value: object, *, name: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _optional_hash(value: str | None, *, name: str) -> str | None:
    return None if value is None else _hash(value, name=name)


def _ceil_fraction(numerator: int, denominator: int) -> int:
    return 0 if numerator == 0 else (numerator - 1) // denominator + 1


def _affordable_quantity(
    cash_micros: int,
    *,
    requested: int,
    price_micros: int,
    lot_size: int,
    fixed_fee_micros: int,
    fee_bps: int,
) -> int:
    if cash_micros <= fixed_fee_micros:
        return 0
    quantity = min(requested, (cash_micros - fixed_fee_micros) // price_micros)
    quantity -= quantity % lot_size
    while quantity > 0:
        notional = price_micros * quantity
        fee = fixed_fee_micros + _ceil_fraction(notional * fee_bps, 10_000)
        if notional + fee <= cash_micros:
            return quantity
        quantity -= lot_size
    return 0
