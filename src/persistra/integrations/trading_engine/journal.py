"""Strictly import and reconcile Trading Engine v3 audit journals."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.integrations.trading_engine._journal_parsing import (
    JournalContextTracker,
    JournalValidationError,
)
from persistra.integrations.trading_engine._journal_parsing import (
    array as _array,
)
from persistra.integrations.trading_engine._journal_parsing import (
    freeze_payload as _freeze_payload,
)
from persistra.integrations.trading_engine._journal_parsing import (
    iter_json_records as _iter_json_records,
)
from persistra.integrations.trading_engine._journal_parsing import (
    optional_sha256 as _optional_hash,
)
from persistra.integrations.trading_engine._journal_parsing import (
    sha256_value as _hash,
)
from persistra.integrations.trading_engine._journal_reconciliation import (
    compare_attribution_rows as _compare_attribution_rows,
)
from persistra.integrations.trading_engine._journal_reconciliation import (
    imported_values_equal as _imported_values_equal,
)
from persistra.integrations.trading_engine._journal_reconciliation import (
    terminal_order_counts as _terminal_order_counts,
)
from persistra.integrations.trading_engine._journal_schema import (
    causation_ids as _causation_ids,
)
from persistra.integrations.trading_engine._journal_schema import (
    choice as _choice,
)
from persistra.integrations.trading_engine._journal_schema import (
    envelope as _journal_envelope,
)
from persistra.integrations.trading_engine._journal_schema import (
    execution_model as _execution_model,
)
from persistra.integrations.trading_engine._journal_schema import (
    json_integer as _json_integer,
)
from persistra.integrations.trading_engine._journal_schema import (
    timestamp as _timestamp,
)
from persistra.integrations.trading_engine._journal_state import (
    PositionState as _PositionState,
)
from persistra.integrations.trading_engine._journal_state import (
    ceil_div as _ceil_div,
)
from persistra.integrations.trading_engine._journal_state import (
    copy_positions as _copy_positions,
)
from persistra.integrations.trading_engine._journal_state import (
    round_toward_zero as _round_toward_zero,
)
from persistra.integrations.trading_engine._journal_state import (
    trunc_div as _trunc_div,
)
from persistra.integrations.trading_engine._scalars import (
    MICRO_SCALE,
    decimal_micros,
    decimal_string,
    decimal_value,
    exact_fields,
    identifier,
    metric_name,
    quantity_value,
)
from persistra.integrations.trading_engine.model import (
    TRADING_ENGINE_CONTRACT_VERSION,
    CancelOrderIntent,
    EmitMetricIntent,
    ExecutionReplayResult,
    JournalEvent,
    RunCompletion,
    ScenarioIntent,
    SplitAction,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetWeightsIntent,
    TradingEngineScenario,
)
from persistra.integrations.trading_engine.scenario import (
    scenario_from_json,
    scenario_from_jsonl,
    scenario_to_jsonl,
)
from persistra.integrations.trading_engine.strategy import (
    StrategyTranscript,
    read_strategy_transcript,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from decimal import Decimal

_ORDER_FIELDS = {
    "order_id",
    "instrument_id",
    "side",
    "quantity",
    "order_kind",
    "limit_price",
    "origin",
    "created_event_id",
    "updated_event_id",
    "created_sequence",
    "created_at",
    "eligible_after_slice_sequence",
    "filled_quantity",
    "filled_notional",
    "status",
    "rejection_reason",
}
_VALUATION_MONEY_FIELD_NAMES = (
    "cash",
    "net_market_value",
    "long_market_value",
    "short_market_value",
    "gross_exposure",
    "cost_basis",
    "realized_pnl",
    "unrealized_pnl",
    "equity",
    "dividend_pnl",
    "execution_fees",
    "borrow_fees",
    "total_fees",
)
_VALUATION_MONEY_FIELDS = set(_VALUATION_MONEY_FIELD_NAMES)
_VALUATION_UNSIGNED_FIELDS = {
    "long_market_value",
    "short_market_value",
    "gross_exposure",
    "execution_fees",
    "borrow_fees",
    "total_fees",
}
_VALUATION_FIELDS = _VALUATION_MONEY_FIELDS | {
    "base_currency",
    "cash_balances",
    "positions",
    "margin",
}
_POSITION_NATIVE_MONEY_FIELD_NAMES = (
    "market_value",
    "cost_basis",
    "realized_pnl",
    "unrealized_pnl",
    "dividend_pnl",
    "execution_fees",
    "borrow_fees",
    "total_fees",
)
_POSITION_NATIVE_MONEY_FIELDS = set(_POSITION_NATIVE_MONEY_FIELD_NAMES)
_POSITION_BASE_MONEY_FIELDS = {f"base_{name}" for name in _POSITION_NATIVE_MONEY_FIELDS}
_POSITION_FIELDS = {
    "instrument_id",
    "quote_currency",
    "quantity",
    "mark",
    "fx_rate",
    *_POSITION_NATIVE_MONEY_FIELDS,
    *_POSITION_BASE_MONEY_FIELDS,
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
    "volume": "Float64",
    "volume_micros": "Int64",
}
_FX_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "currency": "string",
    "rate": "float64",
    "rate_micros": "Int64",
}
_TARGET_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "decision_slice_sequence": "Int64",
    "basis": "string",
    "instrument_id": "string",
    "weight": "Float64",
    "weight_micros": "Int64",
    "quantity": "float64",
    "quantity_micros": "Int64",
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
    "quantity": "float64",
    "quantity_micros": "Int64",
    "order_kind": "string",
    "limit_price": "Float64",
    "limit_price_micros": "Int64",
    "origin": "string",
    "created_event_id": "string",
    "updated_event_id": "string",
    "created_at": "datetime64[ns, UTC]",
    "created_sequence": "Int64",
    "eligible_after_slice_sequence": "Int64",
    "filled_quantity": "float64",
    "filled_quantity_micros": "Int64",
    "filled_notional": "float64",
    "filled_notional_micros": "Int64",
    "status": "string",
    "rejection_reason": "string",
}
_ORDER_ADJUSTMENT_DTYPES = {**_ORDER_DTYPES, "action_id": "string"}
_CANCELLATION_DTYPES = {
    **_ORDER_DTYPES,
    "slice_sequence": "Int64",
    "reason": "string",
}
_FILL_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "fill_id": "string",
    "order_id": "string",
    "instrument_id": "string",
    "quote_currency": "string",
    "side": "string",
    "quantity": "float64",
    "quantity_micros": "Int64",
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
_ACTION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "event_type": "string",
    "action_id": "string",
    "instrument_id": "string",
    "action_type": "string",
    "numerator": "Int64",
    "denominator": "Int64",
    "amount_per_unit": "Float64",
    "amount_per_unit_micros": "Int64",
    "previous_quantity": "Float64",
    "previous_quantity_micros": "Int64",
    "adjusted_quantity": "Float64",
    "adjusted_quantity_micros": "Int64",
    "quantity": "Float64",
    "quantity_micros": "Int64",
    "cash_amount": "Float64",
    "cash_amount_micros": "Int64",
}
_MARGIN_LIMIT_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "order_id": "string",
    "instrument_id": "string",
    "requested_quantity": "float64",
    "requested_quantity_micros": "Int64",
    "permitted_quantity": "float64",
    "permitted_quantity_micros": "Int64",
    "price": "float64",
    "price_micros": "Int64",
}
_BORROW_FEE_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "instrument_id": "string",
    "quote_currency": "string",
    "short_quantity": "float64",
    "short_quantity_micros": "Int64",
    "reference_price": "float64",
    "reference_price_micros": "Int64",
    "borrow_bps": "Int64",
    "period_start": "datetime64[ns, UTC]",
    "period_end": "datetime64[ns, UTC]",
    "fee": "float64",
    "fee_micros": "Int64",
}
_VALUATION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "base_currency": "string",
    **{
        name: dtype
        for field in _VALUATION_MONEY_FIELD_NAMES
        for name, dtype in ((field, "float64"), (f"{field}_micros", "Int64"))
    },
    "initial_requirement": "float64",
    "initial_requirement_micros": "Int64",
    "maintenance_requirement": "float64",
    "maintenance_requirement_micros": "Int64",
    "initial_excess": "float64",
    "initial_excess_micros": "Int64",
    "maintenance_excess": "float64",
    "maintenance_excess_micros": "Int64",
    "margin_call": "boolean",
}
_CASH_BALANCE_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "currency": "string",
    "amount": "float64",
    "amount_micros": "Int64",
    "fx_rate": "float64",
    "fx_rate_micros": "Int64",
    "base_value": "float64",
    "base_value_micros": "Int64",
}
_POSITION_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "slice_sequence": "Int64",
    "instrument_id": "string",
    "quote_currency": "string",
    "quantity": "float64",
    "quantity_micros": "Int64",
    "mark": "float64",
    "mark_micros": "Int64",
    "fx_rate": "float64",
    "fx_rate_micros": "Int64",
    **{
        name: dtype
        for native_field in _POSITION_NATIVE_MONEY_FIELD_NAMES
        for field in (native_field, f"base_{native_field}")
        for name, dtype in ((field, "float64"), (f"{field}_micros", "Int64"))
    },
}
_MARGIN_EVENT_DTYPES = {"event_type": "string", **_VALUATION_DTYPES}
_METRIC_DTYPES = {
    "engine_sequence": "Int64",
    "recorded_at": "datetime64[ns, UTC]",
    "name": "string",
    "value": "string",
}
_INITIAL_CASH_DTYPES = {
    "currency": "string",
    "amount": "float64",
    "amount_micros": "Int64",
    "fx_rate": "Float64",
    "fx_rate_micros": "Int64",
    "base_value": "Float64",
    "base_value_micros": "Int64",
}


def read_journal(
    path: str | Path,
    *,
    scenario: TradingEngineScenario | str | Path | None = None,
    scenario_sha256: str | None = None,
    strategy_transcript: StrategyTranscript | str | Path | None = None,
) -> ExecutionReplayResult:
    """Read one complete journal and reconcile optional external strategy decisions."""
    tracker = JournalContextTracker()
    try:
        return _read_journal(
            path,
            scenario=scenario,
            scenario_sha256=scenario_sha256,
            strategy_transcript=strategy_transcript,
            context_tracker=tracker,
        )
    except JournalValidationError:
        raise
    except ValueError as error:
        if tracker.current is None:
            raise
        raise JournalValidationError(str(error), context=tracker.current) from error


def _read_journal(
    path: str | Path,
    *,
    scenario: TradingEngineScenario | str | Path | None,
    scenario_sha256: str | None,
    strategy_transcript: StrategyTranscript | str | Path | None,
    context_tracker: JournalContextTracker,
) -> ExecutionReplayResult:
    """Import a journal while the public wrapper adds record context."""
    journal_path = Path(path).expanduser()
    resolved_scenario, resolved_hash = _resolve_scenario(scenario)
    expected_hash = _optional_hash(scenario_sha256, name="scenario_sha256")
    if expected_hash is None:
        expected_hash = resolved_hash
    elif resolved_hash is not None and expected_hash != resolved_hash:
        raise ValueError("provided scenario_sha256 differs from the scenario artifact")
    resolved_transcript = _resolve_strategy_transcript(
        strategy_transcript,
        scenario=resolved_scenario,
        scenario_sha256=expected_hash,
    )
    bar_rows: list[dict[str, object]] = []
    fx_rows: list[dict[str, object]] = []
    declared_action_rows: list[dict[str, object]] = []
    target_rows: list[dict[str, object]] = []
    scheduled_outcomes: list[dict[str, object]] = []
    order_rows: list[dict[str, object]] = []
    order_adjustment_rows: list[dict[str, object]] = []
    fill_rows: list[dict[str, object]] = []
    cancellation_rows: list[dict[str, object]] = []
    rejection_rows: list[dict[str, object]] = []
    action_rows: list[dict[str, object]] = []
    margin_limit_rows: list[dict[str, object]] = []
    borrow_fee_rows: list[dict[str, object]] = []
    margin_event_rows: list[dict[str, object]] = []
    valuation_rows: list[dict[str, object]] = []
    cash_balance_rows: list[dict[str, object]] = []
    position_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    events: list[JournalEvent] = []
    completion: RunCompletion | None = None
    completion_valuation: dict[str, object] | None = None
    completion_cash_rows: list[dict[str, object]] = []
    completion_position_rows: list[dict[str, object]] = []
    run_id: str | None = None
    journal_hash: str | None = None
    execution_model: str | None = None
    seen_event_ids: set[str] = set()
    event_type_by_id: dict[str, str] = {}
    previous_event_id: str | None = None
    previous_recorded_at: pd.Timestamp | None = None
    previous_slice_sequence = 0
    current_slice_sequence: int | None = None
    current_slice_recorded_at: pd.Timestamp | None = None
    current_slice_event_id: str | None = None
    current_declared_actions: dict[str, dict[str, object]] = {}
    order_created_events: dict[str, str] = {}
    order_updated_events: dict[str, str] = {}

    record_count = 0
    for line_number, raw in _iter_json_records(journal_path):
        record_count = line_number
        context_tracker.select(line_number)
        context_tracker.select(line_number, raw)
        event = raw
        envelope = _journal_envelope(event, line_number=line_number)
        engine_sequence = envelope.engine_sequence
        if engine_sequence != line_number:
            raise ValueError("engine_sequence must be contiguous and start at one")
        event_run_id = envelope.run_id
        if run_id is None:
            run_id = event_run_id
        elif event_run_id != run_id:
            raise ValueError("journal run_id must remain constant")
        event_id = envelope.event_id
        if event_id != f"{event_run_id}-event-{engine_sequence:012d}":
            raise ValueError("event_id must derive from run_id and engine_sequence")
        if event_id in seen_event_ids:
            raise ValueError("event_id must be unique")
        causation_ids = _causation_ids(
            event["causation_ids"],
            run_id=event_run_id,
            engine_sequence=engine_sequence,
            seen_event_ids=seen_event_ids,
        )
        recorded_at = envelope.recorded_at
        if previous_recorded_at is not None and recorded_at < previous_recorded_at:
            raise ValueError("journal recorded_at must not move backward")
        previous_recorded_at = recorded_at
        event_type = envelope.event_type
        payload = envelope.payload
        if completion is not None:
            raise ValueError("run_completed must be the terminal journal record")
        if line_number == 1 and event_type != "run_started":
            raise ValueError("run_started must be the first journal record")
        if line_number > 1 and event_type == "run_started":
            raise ValueError("the journal must contain exactly one run_started record")

        if event_type == "run_started":
            if causation_ids:
                raise ValueError("run_started must not have causal predecessors")
            item = exact_fields(
                payload,
                {"scenario_sha256", "execution_model"},
                name="run_started payload",
            )
            journal_hash = _hash(item["scenario_sha256"], name="scenario_sha256")
            execution_model = _execution_model(item["execution_model"])
            if expected_hash is not None and journal_hash != expected_hash:
                raise ValueError("run_started scenario_sha256 differs from the scenario artifact")
            if (
                resolved_scenario is not None
                and execution_model != resolved_scenario.execution.model
            ):
                raise ValueError("run_started execution_model differs from the scenario")
        elif event_type == "market_slice_received":
            if causation_ids:
                raise ValueError("market_slice_received must not have causal predecessors")
            if current_slice_sequence is not None:
                raise ValueError("each market slice must end with valuation")
            bars, rates, actions = _slice_rows(
                payload,
                engine_sequence=engine_sequence,
                recorded_at=recorded_at,
            )
            sequence = cast("int", bars[0]["slice_sequence"])
            if sequence <= previous_slice_sequence:
                raise ValueError("slice_sequence must increase globally")
            if cast("pd.Timestamp", bars[0]["received_at"]) != recorded_at:
                raise ValueError("market slice receipt must equal its audit recorded_at")
            previous_slice_sequence = sequence
            current_slice_sequence = sequence
            current_slice_recorded_at = recorded_at
            current_slice_event_id = event_id
            current_declared_actions = {cast("str", item["action_id"]): item for item in actions}
            bar_rows.extend(bars)
            fx_rows.extend(rates)
            declared_action_rows.extend(actions)
        elif event_type == "run_completed":
            if current_slice_sequence is not None:
                raise ValueError("run_completed must follow the current slice valuation")
            if previous_event_id is None or causation_ids != (previous_event_id,):
                raise ValueError("run_completed must cite the immediately preceding event")
            (
                completion,
                completion_valuation,
                completion_cash_rows,
                completion_position_rows,
            ) = _completion(payload, engine_sequence=engine_sequence, recorded_at=recorded_at)
            if journal_hash is None or completion.scenario_sha256 != journal_hash:
                raise ValueError("terminal scenario_sha256 must match run_started")
            if execution_model is None or completion.execution_model != execution_model:
                raise ValueError("terminal execution_model must match run_started")
        else:
            if (
                current_slice_sequence is None
                or current_slice_recorded_at is None
                or current_slice_event_id is None
            ):
                raise ValueError("nonterminal journal events require an open market slice")
            if recorded_at != current_slice_recorded_at:
                raise ValueError("each slice event must use the market slice receipt clock")
            if event_type == "target_portfolio_requested":
                _require_slice_cause(causation_ids, current_slice_event_id, event_type)
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
                if order["filled_quantity_micros"] != 0 or order["filled_notional_micros"] != 0:
                    raise ValueError("submitted order snapshots must start with zero fill state")
                if order["created_sequence"] != engine_sequence:
                    raise ValueError("submitted order created_sequence must equal engine_sequence")
                if order["created_event_id"] != event_id:
                    raise ValueError("submitted order created_event_id must equal event_id")
                if order["updated_event_id"] != event_id:
                    raise ValueError("submitted order updated_event_id must equal event_id")
                if order["eligible_after_slice_sequence"] != current_slice_sequence:
                    raise ValueError("submitted order eligibility must equal the current slice")
                order_id = cast("str", order["order_id"])
                if order_id in order_created_events:
                    raise ValueError("order identifiers must be unique")
                order_created_events[order_id] = event_id
                order_updated_events[order_id] = event_id
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
                _require_order_cause(
                    cancellation,
                    causation_ids=causation_ids,
                    created_events=order_created_events,
                    require_updated=False,
                    updated_events=order_updated_events,
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
            elif event_type == "order_adjusted":
                adjustment = _order_adjustment_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
                order_id = cast("str", adjustment["order_id"])
                created = order_created_events.get(order_id)
                if created is None or created not in causation_ids:
                    raise ValueError("order_adjusted must cite its order creation event")
                action_id = cast("str", adjustment["action_id"])
                action_event = next(
                    (
                        item
                        for item in action_rows
                        if item["action_id"] == action_id and item["event_type"] == "split_applied"
                    ),
                    None,
                )
                if action_event is None:
                    raise ValueError("order_adjusted must refer to a prior split event")
                action_sequence = cast("int", action_event["engine_sequence"])
                action_event_id = f"{event_run_id}-event-{action_sequence:012d}"
                if action_event_id not in causation_ids:
                    raise ValueError("order_adjusted must cite its split event")
                if adjustment["updated_event_id"] != event_id:
                    raise ValueError("order_adjusted updated_event_id must equal event_id")
                order_updated_events[order_id] = event_id
                order_adjustment_rows.append(adjustment)
            elif event_type == "fill_applied":
                fill = _fill_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                )
                _require_order_cause(
                    fill,
                    causation_ids=causation_ids,
                    created_events=order_created_events,
                    require_updated=True,
                    updated_events=order_updated_events,
                )
                _require_slice_cause(causation_ids, current_slice_event_id, event_type)
                fill_rows.append(fill)
            elif event_type in {"split_applied", "cash_dividend_applied"}:
                _require_slice_cause(causation_ids, current_slice_event_id, event_type)
                action = _action_row(
                    payload,
                    event_type=event_type,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    slice_sequence=current_slice_sequence,
                )
                declared = current_declared_actions.get(cast("str", action["action_id"]))
                if declared is None or not _action_declaration_matches(declared, action):
                    raise ValueError("applied corporate action differs from its market slice")
                action_rows.append(action)
            elif event_type == "margin_limited":
                _require_slice_cause(causation_ids, current_slice_event_id, event_type)
                limited = _margin_limit_row(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    slice_sequence=current_slice_sequence,
                )
                _require_order_cause(
                    limited,
                    causation_ids=causation_ids,
                    created_events=order_created_events,
                    require_updated=True,
                    updated_events=order_updated_events,
                )
                margin_limit_rows.append(limited)
            elif event_type == "borrow_fee_applied":
                _require_slice_cause(causation_ids, current_slice_event_id, event_type)
                borrow_fee_rows.append(
                    _borrow_fee_row(
                        payload,
                        engine_sequence=engine_sequence,
                        recorded_at=recorded_at,
                        slice_sequence=current_slice_sequence,
                    )
                )
            elif event_type in {"margin_call", "margin_restored"}:
                _require_slice_cause(causation_ids, current_slice_event_id, event_type)
                valuation, _cash, _positions = _valuation_rows(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    slice_sequence=current_slice_sequence,
                )
                if event_type == "margin_call" and not valuation["margin_call"]:
                    raise ValueError("margin_call must contain a breached margin snapshot")
                if event_type == "margin_restored" and valuation["margin_call"]:
                    raise ValueError("margin_restored must contain a restored margin snapshot")
                margin_event_rows.append(
                    {
                        "event_type": event_type,
                        **valuation,
                        "_cash_rows": _cash,
                        "_position_rows": _positions,
                    }
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
                if causation_ids != (current_slice_event_id,):
                    raise ValueError("valuation must cite its current market slice")
                valuation, cash_rows, positions = _valuation_rows(
                    payload,
                    engine_sequence=engine_sequence,
                    recorded_at=recorded_at,
                    slice_sequence=current_slice_sequence,
                )
                valuation_rows.append(valuation)
                cash_balance_rows.extend(cash_rows)
                position_rows.extend(positions)
                current_slice_sequence = None
                current_slice_recorded_at = None
                current_slice_event_id = None
                current_declared_actions = {}
            else:
                raise ValueError(f"unsupported journal event_type: {event_type}")

        events.append(
            JournalEvent(
                contract_version=TRADING_ENGINE_CONTRACT_VERSION,
                engine_sequence=engine_sequence,
                event_id=event_id,
                causation_ids=causation_ids,
                run_id=event_run_id,
                recorded_at=recorded_at,
                event_type=event_type,
                payload=cast("Mapping[str, Any]", _freeze_payload(payload)),
            )
        )
        seen_event_ids.add(event_id)
        event_type_by_id[event_id] = event_type
        previous_event_id = event_id

    if record_count == 0:
        raise ValueError("audit journal must not be empty")
    if (
        run_id is None
        or journal_hash is None
        or execution_model is None
        or completion is None
        or completion_valuation is None
    ):
        raise ValueError("audit journal must start with run_started and end with run_completed")
    _validate_completion(
        completion,
        completion_valuation=completion_valuation,
        completion_cash_rows=completion_cash_rows,
        completion_position_rows=completion_position_rows,
        bars=bar_rows,
        orders=order_rows,
        order_adjustments=order_adjustment_rows,
        fills=fill_rows,
        cancellations=cancellation_rows,
        valuations=valuation_rows,
        cash_balances=cash_balance_rows,
        positions=position_rows,
        scenario=resolved_scenario,
    )
    if resolved_scenario is not None:
        _validate_scenario_journal(
            resolved_scenario,
            run_id,
            bars=bar_rows,
            fx_rates=fx_rows,
            declared_actions=declared_action_rows,
            scheduled_outcomes=scheduled_outcomes,
            orders=order_rows,
            order_adjustments=order_adjustment_rows,
            fills=fill_rows,
            cancellations=cancellation_rows,
            actions=action_rows,
            margin_limits=margin_limit_rows,
            borrow_fees=borrow_fee_rows,
            margin_events=margin_event_rows,
            valuations=valuation_rows,
            cash_balances=cash_balance_rows,
            positions=position_rows,
            expected_intents=(
                None
                if resolved_transcript is None
                else tuple(
                    (decision.after_slice_sequence, intent)
                    for decision in resolved_transcript.decisions
                    for intent in decision.intents
                )
            ),
        )
    initial_cash, initial_equity_micros = _initial_cash_frame(
        resolved_scenario,
        fx_rows=fx_rows,
    )
    return ExecutionReplayResult(
        run_id=run_id,
        scenario_sha256=journal_hash,
        execution_model=execution_model,
        bars=_typed_frame(bar_rows, _BAR_DTYPES),
        fx_rates=_typed_frame(fx_rows, _FX_DTYPES),
        targets=_typed_frame(target_rows, _TARGET_DTYPES),
        orders=_typed_frame(order_rows, _ORDER_DTYPES),
        order_adjustments=_typed_frame(order_adjustment_rows, _ORDER_ADJUSTMENT_DTYPES),
        fills=_typed_frame(fill_rows, _FILL_DTYPES),
        cancellations=_typed_frame(cancellation_rows, _CANCELLATION_DTYPES),
        rejections=_typed_frame(rejection_rows, _REJECTION_DTYPES),
        corporate_actions=_typed_frame(action_rows, _ACTION_DTYPES),
        margin_limits=_typed_frame(margin_limit_rows, _MARGIN_LIMIT_DTYPES),
        borrow_fees=_typed_frame(borrow_fee_rows, _BORROW_FEE_DTYPES),
        margin_events=_typed_frame(margin_event_rows, _MARGIN_EVENT_DTYPES),
        valuations=_typed_frame(valuation_rows, _VALUATION_DTYPES),
        cash_balances=_typed_frame(cash_balance_rows, _CASH_BALANCE_DTYPES),
        positions=_typed_frame(position_rows, _POSITION_DTYPES),
        metrics=_typed_frame(metric_rows, _METRIC_DTYPES),
        events=tuple(events),
        completion=completion,
        contract_version=TRADING_ENGINE_CONTRACT_VERSION,
        base_currency=None if resolved_scenario is None else resolved_scenario.base_currency,
        initial_cash_balances=initial_cash,
        initial_equity=(
            None if initial_equity_micros is None else initial_equity_micros / MICRO_SCALE
        ),
        initial_equity_micros=initial_equity_micros,
    )


def _require_slice_cause(
    causation_ids: tuple[str, ...],
    slice_event_id: str,
    event_type: str,
) -> None:
    if slice_event_id not in causation_ids:
        raise ValueError(f"{event_type} must cite its current market slice")


def _require_order_cause(
    event: Mapping[str, object],
    *,
    causation_ids: tuple[str, ...],
    created_events: Mapping[str, str],
    updated_events: Mapping[str, str],
    require_updated: bool,
) -> None:
    order_id = cast("str", event["order_id"])
    created = created_events.get(order_id)
    if created is None:
        raise ValueError("order lifecycle event refers to an unknown order")
    if created not in causation_ids:
        raise ValueError("order lifecycle event must cite its order creation event")
    if require_updated:
        updated = updated_events[order_id]
        if updated not in causation_ids:
            raise ValueError("order lifecycle event must cite its latest order state")


def _slice_rows(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    item = exact_fields(
        value,
        {
            "slice_sequence",
            "start_at",
            "end_at",
            "available_at",
            "received_at",
            "bars",
            "fx_rates",
            "corporate_actions",
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
    bar_rows = [
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
    identities = [cast("str", row["instrument_id"]) for row in bar_rows]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("market slice bars must use unique instrument identifier order")
    rates = _array(item["fx_rates"], name="fx_rates")
    if not rates:
        raise ValueError("a market slice must contain FX rates")
    fx_rows = [
        _fx_row(
            rate,
            engine_sequence=engine_sequence,
            recorded_at=recorded_at,
            slice_sequence=slice_sequence,
        )
        for rate in rates
    ]
    currencies = [cast("str", row["currency"]) for row in fx_rows]
    if currencies != sorted(currencies) or len(currencies) != len(set(currencies)):
        raise ValueError("market slice FX rates must use unique currency order")
    actions = [
        _action_declaration_row(
            action,
            engine_sequence=engine_sequence,
            recorded_at=recorded_at,
            slice_sequence=slice_sequence,
        )
        for action in _array(item["corporate_actions"], name="corporate_actions")
    ]
    action_ids = [cast("str", row["action_id"]) for row in actions]
    if action_ids != sorted(action_ids) or len(action_ids) != len(set(action_ids)):
        raise ValueError("market slice corporate actions must use unique action identifier order")
    return bar_rows, fx_rows, actions


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
    volume = (
        None
        if item["volume"] is None
        else _decimal_payload(item["volume"], name="volume", nonnegative=True)
    )
    row: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "start_at": start_at,
        "end_at": end_at,
        "available_at": available_at,
        "received_at": received_at,
        "volume": pd.NA if volume is None else float(volume),
        "volume_micros": pd.NA if volume is None else decimal_micros(volume),
    }
    for name, price in prices.items():
        row[name] = float(price)
        row[f"{name}_micros"] = decimal_micros(price)
    return row


def _fx_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    item = exact_fields(value, {"currency", "rate"}, name="market slice FX rate")
    rate = _decimal_payload(item["rate"], name="rate", positive=True)
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "currency": identifier(item["currency"], name="currency"),
        "rate": float(rate),
        "rate_micros": decimal_micros(rate),
    }


def _action_declaration_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("corporate action must be a JSON object")
    raw = cast("dict[str, object]", value)
    action_type = raw.get("type")
    common: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
    }
    if action_type == "split":
        item = exact_fields(
            raw,
            {"type", "action_id", "instrument_id", "numerator", "denominator"},
            name="split corporate action",
        )
        numerator = quantity_value(item["numerator"], name="numerator", positive=True)
        denominator = quantity_value(item["denominator"], name="denominator", positive=True)
        if numerator == denominator:
            raise ValueError("split ratio must change instrument units")
        return {
            **common,
            "action_id": identifier(item["action_id"], name="action_id"),
            "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
            "action_type": "split",
            "numerator": numerator,
            "denominator": denominator,
            "amount_per_unit_micros": None,
        }
    if action_type == "cash_dividend":
        item = exact_fields(
            raw,
            {"type", "action_id", "instrument_id", "amount_per_unit"},
            name="cash dividend corporate action",
        )
        amount = _decimal_payload(item["amount_per_unit"], name="amount_per_unit", positive=True)
        return {
            **common,
            "action_id": identifier(item["action_id"], name="action_id"),
            "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
            "action_type": "cash_dividend",
            "numerator": None,
            "denominator": None,
            "amount_per_unit_micros": decimal_micros(amount),
        }
    raise ValueError("unsupported corporate action type")


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
            None if target["weight"] is None else _decimal_payload(target["weight"], name="weight")
        )
        if (basis == "weights") != (weight is not None):
            raise ValueError("target weight presence must match portfolio basis")
        reference = (
            None
            if target["reference_price"] is None
            else _decimal_payload(target["reference_price"], name="reference_price", positive=True)
        )
        if (basis == "weights") != (reference is not None):
            raise ValueError("reference_price presence must match portfolio basis")
        quantity = _decimal_payload(target["quantity"], name="quantity")
        rows.append(
            {
                "engine_sequence": engine_sequence,
                "recorded_at": recorded_at,
                "decision_slice_sequence": decision_slice_sequence,
                "basis": basis,
                "instrument_id": instrument_id,
                "weight": pd.NA if weight is None else float(weight),
                "weight_micros": pd.NA if weight is None else decimal_micros(weight),
                "quantity": float(quantity),
                "quantity_micros": decimal_micros(quantity),
                "reference_price": pd.NA if reference is None else float(reference),
                "reference_price_micros": (
                    pd.NA if reference is None else decimal_micros(reference)
                ),
            }
        )
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
    if rejection_reason is not None and (
        not isinstance(rejection_reason, str) or not rejection_reason
    ):
        raise ValueError("rejection_reason must be a nonempty string or null")
    if (status == "rejected") != (rejection_reason is not None):
        raise ValueError("rejected status and rejection_reason must apply together")
    created_at = _timestamp(item["created_at"], name="created_at")
    if created_at > recorded_at:
        raise ValueError("order created_at must not follow audit recorded_at")
    if event_type in {"order_accepted", "order_rejected"} and created_at != recorded_at:
        raise ValueError("submitted order created_at must equal audit recorded_at")
    quantity = _decimal_payload(item["quantity"], name="quantity", positive=True)
    filled_quantity = _decimal_payload(
        item["filled_quantity"], name="filled_quantity", nonnegative=True
    )
    if filled_quantity > quantity:
        raise ValueError("order filled_quantity must not exceed quantity")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "event_type": event_type,
        "order_id": identifier(item["order_id"], name="order_id"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "side": side,
        "quantity": float(quantity),
        "quantity_micros": decimal_micros(quantity),
        "order_kind": order_kind,
        "limit_price": pd.NA if limit_price is None else float(limit_price),
        "limit_price_micros": (pd.NA if limit_price is None else decimal_micros(limit_price)),
        "origin": _choice(
            item["origin"],
            {"direct", "target_rebalance", "margin_liquidation"},
            name="origin",
        ),
        "created_event_id": identifier(item["created_event_id"], name="created_event_id"),
        "updated_event_id": identifier(item["updated_event_id"], name="updated_event_id"),
        "created_at": created_at,
        "created_sequence": quantity_value(
            item["created_sequence"], name="created_sequence", positive=True
        ),
        "eligible_after_slice_sequence": quantity_value(
            item["eligible_after_slice_sequence"],
            name="eligible_after_slice_sequence",
        ),
        "filled_quantity": float(filled_quantity),
        "filled_quantity_micros": decimal_micros(filled_quantity),
        **_money_pair("filled_notional", item["filled_notional"], nonnegative=True),
        "status": status,
        "rejection_reason": pd.NA if rejection_reason is None else rejection_reason,
    }


def _order_adjustment_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> dict[str, object]:
    item = exact_fields(value, {"order", "action_id"}, name="order_adjusted payload")
    order = _order_row(
        item["order"],
        engine_sequence=engine_sequence,
        recorded_at=recorded_at,
        event_type="order_adjusted",
    )
    if order["status"] not in {"working", "partially_filled"}:
        raise ValueError("order_adjusted must contain an active order")
    order["action_id"] = identifier(item["action_id"], name="action_id")
    return order


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
        {"strategy_requested", "target_replaced", "market_ioc", "margin_call"},
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
            "quote_currency",
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
    quantity = _decimal_payload(item["quantity"], name="quantity", positive=True)
    price = _decimal_payload(item["price"], name="price", positive=True)
    row = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "fill_id": identifier(item["fill_id"], name="fill_id"),
        "order_id": identifier(item["order_id"], name="order_id"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "quote_currency": identifier(item["quote_currency"], name="quote_currency"),
        "side": _choice(item["side"], {"buy", "sell"}, name="side"),
        "quantity": float(quantity),
        "quantity_micros": decimal_micros(quantity),
        "price": float(price),
        "price_micros": decimal_micros(price),
        **_money_pair("notional", item["notional"], positive=True),
        **_money_pair("fee", item["fee"], nonnegative=True),
        "executed_at": _timestamp(item["executed_at"], name="executed_at"),
        "slice_sequence": quantity_value(
            item["slice_sequence"], name="slice_sequence", positive=True
        ),
    }
    expected_notional = _trunc_div(
        cast("int", row["price_micros"]) * cast("int", row["quantity_micros"]),
        MICRO_SCALE,
    )
    if row["notional_micros"] != expected_notional:
        raise ValueError("fill notional must equal price times quantity")
    return row


def _action_row(
    value: object,
    *,
    event_type: str,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    common: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "event_type": event_type,
        "numerator": pd.NA,
        "denominator": pd.NA,
        "amount_per_unit": pd.NA,
        "amount_per_unit_micros": pd.NA,
        "previous_quantity": pd.NA,
        "previous_quantity_micros": pd.NA,
        "adjusted_quantity": pd.NA,
        "adjusted_quantity_micros": pd.NA,
        "quantity": pd.NA,
        "quantity_micros": pd.NA,
        "cash_amount": pd.NA,
        "cash_amount_micros": pd.NA,
    }
    if event_type == "split_applied":
        item = exact_fields(
            value,
            {"action", "previous_quantity", "adjusted_quantity"},
            name="split_applied payload",
        )
        declaration = _action_declaration_row(
            item["action"],
            engine_sequence=engine_sequence,
            recorded_at=recorded_at,
            slice_sequence=slice_sequence,
        )
        if declaration["action_type"] != "split":
            raise ValueError("split_applied must contain a split action")
        previous = _decimal_payload(item["previous_quantity"], name="previous_quantity")
        adjusted = _decimal_payload(item["adjusted_quantity"], name="adjusted_quantity")
        numerator = cast("int", declaration["numerator"])
        denominator = cast("int", declaration["denominator"])
        product = decimal_micros(previous) * numerator
        if product % denominator or product // denominator != decimal_micros(adjusted):
            raise ValueError("split quantities do not reconcile to the action ratio")
        return {
            **common,
            "action_id": declaration["action_id"],
            "instrument_id": declaration["instrument_id"],
            "action_type": "split",
            "numerator": numerator,
            "denominator": denominator,
            "previous_quantity": float(previous),
            "previous_quantity_micros": decimal_micros(previous),
            "adjusted_quantity": float(adjusted),
            "adjusted_quantity_micros": decimal_micros(adjusted),
        }
    item = exact_fields(
        value,
        {"action", "quantity", "cash_amount"},
        name="cash_dividend_applied payload",
    )
    declaration = _action_declaration_row(
        item["action"],
        engine_sequence=engine_sequence,
        recorded_at=recorded_at,
        slice_sequence=slice_sequence,
    )
    if declaration["action_type"] != "cash_dividend":
        raise ValueError("cash_dividend_applied must contain a dividend action")
    quantity = _decimal_payload(item["quantity"], name="quantity")
    cash_amount = _decimal_payload(item["cash_amount"], name="cash_amount")
    amount_micros = cast("int", declaration["amount_per_unit_micros"])
    if _trunc_div(amount_micros * decimal_micros(quantity), MICRO_SCALE) != decimal_micros(
        cash_amount
    ):
        raise ValueError("cash dividend amount does not reconcile to position quantity")
    return {
        **common,
        "action_id": declaration["action_id"],
        "instrument_id": declaration["instrument_id"],
        "action_type": "cash_dividend",
        "amount_per_unit": amount_micros / MICRO_SCALE,
        "amount_per_unit_micros": amount_micros,
        "quantity": float(quantity),
        "quantity_micros": decimal_micros(quantity),
        "cash_amount": float(cash_amount),
        "cash_amount_micros": decimal_micros(cash_amount),
    }


def _action_declaration_matches(
    declaration: Mapping[str, object],
    applied: Mapping[str, object],
) -> bool:
    common = {"action_id", "instrument_id", "action_type"}
    if not all(declaration[name] == applied[name] for name in common):
        return False
    if declaration["action_type"] == "split":
        return (
            declaration["numerator"] == applied["numerator"]
            and declaration["denominator"] == applied["denominator"]
        )
    return declaration["amount_per_unit_micros"] == applied["amount_per_unit_micros"]


def _margin_limit_row(
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
            "permitted_quantity",
            "price",
        },
        name="margin_limited payload",
    )
    requested = _decimal_payload(
        item["requested_quantity"], name="requested_quantity", positive=True
    )
    permitted = _decimal_payload(
        item["permitted_quantity"], name="permitted_quantity", nonnegative=True
    )
    if permitted >= requested:
        raise ValueError("margin_limited permitted_quantity must be below requested_quantity")
    price = _decimal_payload(item["price"], name="price", positive=True)
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "order_id": identifier(item["order_id"], name="order_id"),
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "requested_quantity": float(requested),
        "requested_quantity_micros": decimal_micros(requested),
        "permitted_quantity": float(permitted),
        "permitted_quantity_micros": decimal_micros(permitted),
        "price": float(price),
        "price_micros": decimal_micros(price),
    }


def _borrow_fee_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    item = exact_fields(
        value,
        {
            "instrument_id",
            "quote_currency",
            "short_quantity",
            "reference_price",
            "borrow_bps",
            "period_start",
            "period_end",
            "fee",
        },
        name="borrow_fee_applied payload",
    )
    short_quantity = _decimal_payload(item["short_quantity"], name="short_quantity", positive=True)
    reference = _decimal_payload(item["reference_price"], name="reference_price", positive=True)
    borrow_bps = _json_integer(item["borrow_bps"], name="borrow_bps", positive=True)
    if borrow_bps > 10_000:
        raise ValueError("borrow_bps must not exceed 10000")
    period_start = _timestamp(item["period_start"], name="period_start")
    period_end = _timestamp(item["period_end"], name="period_end")
    if period_end <= period_start:
        raise ValueError("borrow fee period must be positive")
    return {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "quote_currency": identifier(item["quote_currency"], name="quote_currency"),
        "short_quantity": float(short_quantity),
        "short_quantity_micros": decimal_micros(short_quantity),
        "reference_price": float(reference),
        "reference_price_micros": decimal_micros(reference),
        "borrow_bps": borrow_bps,
        "period_start": period_start,
        "period_end": period_end,
        **_money_pair("fee", item["fee"], positive=True),
    }


def _valuation_rows(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> tuple[
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    item = exact_fields(value, _VALUATION_FIELDS, name="valuation payload")
    result: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "base_currency": identifier(item["base_currency"], name="base_currency"),
    }
    for name in _VALUATION_MONEY_FIELD_NAMES:
        result.update(
            _money_pair(
                name,
                item[name],
                nonnegative=name in _VALUATION_UNSIGNED_FIELDS,
            )
        )
    cash_rows = [
        _cash_balance_row(
            balance,
            engine_sequence=engine_sequence,
            recorded_at=recorded_at,
            slice_sequence=slice_sequence,
        )
        for balance in _array(item["cash_balances"], name="cash_balances")
    ]
    if not cash_rows:
        raise ValueError("valuation cash_balances must not be empty")
    currencies = [cast("str", row["currency"]) for row in cash_rows]
    if currencies != sorted(currencies) or len(currencies) != len(set(currencies)):
        raise ValueError("valuation cash balances must use unique currency order")
    positions = [
        _position_row(
            position,
            engine_sequence=engine_sequence,
            recorded_at=recorded_at,
            slice_sequence=slice_sequence,
        )
        for position in _array(item["positions"], name="valuation positions")
    ]
    instrument_ids = [cast("str", position["instrument_id"]) for position in positions]
    if instrument_ids != sorted(instrument_ids) or len(instrument_ids) != len(set(instrument_ids)):
        raise ValueError("valuation positions must use unique instrument identifier order")
    margin = exact_fields(
        item["margin"],
        {
            "initial_requirement",
            "maintenance_requirement",
            "initial_excess",
            "maintenance_excess",
            "margin_call",
        },
        name="valuation margin",
    )
    for name in ("initial_requirement", "maintenance_requirement"):
        result.update(_money_pair(name, margin[name], nonnegative=True))
    for name in ("initial_excess", "maintenance_excess"):
        result.update(_money_pair(name, margin[name]))
    if not isinstance(margin["margin_call"], bool):
        raise ValueError("margin_call must be a JSON boolean")
    result["margin_call"] = margin["margin_call"]
    _reconcile_valuation(result, cash_rows=cash_rows, positions=positions)
    return result, cash_rows, positions


def _cash_balance_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    item = exact_fields(
        value,
        {"currency", "amount", "fx_rate", "base_value"},
        name="cash attribution",
    )
    result: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "currency": identifier(item["currency"], name="currency"),
    }
    result.update(_money_pair("amount", item["amount"]))
    rate = _decimal_payload(item["fx_rate"], name="fx_rate", positive=True)
    result["fx_rate"] = float(rate)
    result["fx_rate_micros"] = decimal_micros(rate)
    result.update(_money_pair("base_value", item["base_value"]))
    expected = _trunc_div(
        cast("int", result["amount_micros"]) * result["fx_rate_micros"],
        MICRO_SCALE,
    )
    if result["base_value_micros"] != expected:
        raise ValueError("cash base_value does not reconcile to its FX rate")
    return result


def _position_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
    slice_sequence: int,
) -> dict[str, object]:
    item = exact_fields(value, _POSITION_FIELDS, name="position attribution")
    quantity = _decimal_payload(item["quantity"], name="quantity")
    mark = _decimal_payload(item["mark"], name="mark", positive=True)
    fx_rate = _decimal_payload(item["fx_rate"], name="fx_rate", positive=True)
    result: dict[str, object] = {
        "engine_sequence": engine_sequence,
        "recorded_at": recorded_at,
        "slice_sequence": slice_sequence,
        "instrument_id": identifier(item["instrument_id"], name="instrument_id"),
        "quote_currency": identifier(item["quote_currency"], name="quote_currency"),
        "quantity": float(quantity),
        "quantity_micros": decimal_micros(quantity),
        "mark": float(mark),
        "mark_micros": decimal_micros(mark),
        "fx_rate": float(fx_rate),
        "fx_rate_micros": decimal_micros(fx_rate),
    }
    unsigned = {
        "execution_fees",
        "borrow_fees",
        "total_fees",
        "base_execution_fees",
        "base_borrow_fees",
        "base_total_fees",
    }
    for native_name in _POSITION_NATIVE_MONEY_FIELD_NAMES:
        for name in (native_name, f"base_{native_name}"):
            result.update(_money_pair(name, item[name], nonnegative=name in unsigned))
    expected_market_value = _trunc_div(
        cast("int", result["mark_micros"]) * cast("int", result["quantity_micros"]),
        MICRO_SCALE,
    )
    if result["market_value_micros"] != expected_market_value:
        raise ValueError("position market_value must equal mark times quantity")
    if result["unrealized_pnl_micros"] != (
        cast("int", result["market_value_micros"]) - cast("int", result["cost_basis_micros"])
    ):
        raise ValueError("position unrealized P&L must equal market value minus cost basis")
    if result["total_fees_micros"] != (
        cast("int", result["execution_fees_micros"]) + cast("int", result["borrow_fees_micros"])
    ):
        raise ValueError("position total fees must equal execution plus borrow fees")
    for name in _POSITION_NATIVE_MONEY_FIELD_NAMES:
        expected = _trunc_div(
            cast("int", result[f"{name}_micros"]) * cast("int", result["fx_rate_micros"]),
            MICRO_SCALE,
        )
        if result[f"base_{name}_micros"] != expected:
            raise ValueError(f"position base_{name} does not reconcile to its FX rate")
    return result


def _reconcile_valuation(
    valuation: Mapping[str, object],
    *,
    cash_rows: Sequence[Mapping[str, object]],
    positions: Sequence[Mapping[str, object]],
) -> None:
    if valuation["cash_micros"] != sum(cast("int", row["base_value_micros"]) for row in cash_rows):
        raise ValueError("valuation cash balances do not reconcile to cash")
    aggregate_position_fields = {
        "net_market_value": "base_market_value",
        "cost_basis": "base_cost_basis",
        "realized_pnl": "base_realized_pnl",
        "unrealized_pnl": "base_unrealized_pnl",
        "dividend_pnl": "base_dividend_pnl",
        "execution_fees": "base_execution_fees",
        "borrow_fees": "base_borrow_fees",
        "total_fees": "base_total_fees",
    }
    for aggregate, position_field in aggregate_position_fields.items():
        if valuation[f"{aggregate}_micros"] != sum(
            cast("int", row[f"{position_field}_micros"]) for row in positions
        ):
            raise ValueError("valuation positions do not reconcile to account aggregates")
    long_value = sum(max(cast("int", row["base_market_value_micros"]), 0) for row in positions)
    short_value = sum(max(-cast("int", row["base_market_value_micros"]), 0) for row in positions)
    if valuation["long_market_value_micros"] != long_value:
        raise ValueError("valuation long market value does not reconcile")
    if valuation["short_market_value_micros"] != short_value:
        raise ValueError("valuation short market value does not reconcile")
    if valuation["gross_exposure_micros"] != long_value + short_value:
        raise ValueError("valuation gross exposure does not reconcile")
    if valuation["equity_micros"] != (
        cast("int", valuation["cash_micros"]) + cast("int", valuation["net_market_value_micros"])
    ):
        raise ValueError("valuation equity does not reconcile")
    if valuation["initial_excess_micros"] != (
        cast("int", valuation["equity_micros"])
        - cast("int", valuation["initial_requirement_micros"])
    ):
        raise ValueError("valuation initial margin excess does not reconcile")
    if valuation["maintenance_excess_micros"] != (
        cast("int", valuation["equity_micros"])
        - cast("int", valuation["maintenance_requirement_micros"])
    ):
        raise ValueError("valuation maintenance margin excess does not reconcile")
    if bool(valuation["margin_call"]) != (cast("int", valuation["maintenance_excess_micros"]) < 0):
        raise ValueError("valuation margin_call differs from maintenance excess")


def _metric_row(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
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
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
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


def _completion(
    value: object,
    *,
    engine_sequence: int,
    recorded_at: pd.Timestamp,
) -> tuple[
    RunCompletion,
    dict[str, object],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    item = exact_fields(
        value,
        {"scenario_sha256", "execution_model", "valuation", "order_counts"},
        name="run_completed payload",
    )
    valuation, cash_rows, positions = _valuation_rows(
        item["valuation"],
        engine_sequence=engine_sequence,
        recorded_at=recorded_at,
        slice_sequence=0,
    )
    counts = exact_fields(
        item["order_counts"],
        {"total", "active", "filled", "rejected", "cancelled"},
        name="completion order_counts",
    )
    orders = {name: _json_integer(counts[name], name=f"{name} order count") for name in counts}
    if (
        sum(orders[name] for name in ("active", "filled", "rejected", "cancelled"))
        != orders["total"]
    ):
        raise ValueError("terminal order counts must reconcile to total")
    completion = RunCompletion(
        recorded_at=recorded_at,
        engine_sequence=engine_sequence,
        scenario_sha256=_hash(item["scenario_sha256"], name="scenario_sha256"),
        execution_model=_execution_model(item["execution_model"]),
        cash_micros=cast("int", valuation["cash_micros"]),
        net_market_value_micros=cast("int", valuation["net_market_value_micros"]),
        long_market_value_micros=cast("int", valuation["long_market_value_micros"]),
        short_market_value_micros=cast("int", valuation["short_market_value_micros"]),
        gross_exposure_micros=cast("int", valuation["gross_exposure_micros"]),
        cost_basis_micros=cast("int", valuation["cost_basis_micros"]),
        realized_pnl_micros=cast("int", valuation["realized_pnl_micros"]),
        unrealized_pnl_micros=cast("int", valuation["unrealized_pnl_micros"]),
        equity_micros=cast("int", valuation["equity_micros"]),
        dividend_pnl_micros=cast("int", valuation["dividend_pnl_micros"]),
        execution_fees_micros=cast("int", valuation["execution_fees_micros"]),
        borrow_fees_micros=cast("int", valuation["borrow_fees_micros"]),
        total_fees_micros=cast("int", valuation["total_fees_micros"]),
        total_orders=orders["total"],
        active_orders=orders["active"],
        filled_orders=orders["filled"],
        rejected_orders=orders["rejected"],
        cancelled_orders=orders["cancelled"],
    )
    return completion, valuation, cash_rows, positions


def _validate_scenario_journal(
    scenario: TradingEngineScenario,
    run_id: str,
    *,
    bars: Sequence[dict[str, object]],
    fx_rates: Sequence[dict[str, object]],
    declared_actions: Sequence[dict[str, object]],
    scheduled_outcomes: Sequence[Mapping[str, object]],
    orders: Sequence[dict[str, object]],
    order_adjustments: Sequence[dict[str, object]],
    fills: Sequence[dict[str, object]],
    cancellations: Sequence[dict[str, object]],
    actions: Sequence[dict[str, object]],
    margin_limits: Sequence[dict[str, object]],
    borrow_fees: Sequence[dict[str, object]],
    margin_events: Sequence[dict[str, object]],
    valuations: Sequence[dict[str, object]],
    cash_balances: Sequence[dict[str, object]],
    positions: Sequence[dict[str, object]],
    expected_intents: Sequence[tuple[int | None, ScenarioIntent]] | None,
) -> None:
    if scenario.run_id != run_id:
        raise ValueError("scenario and journal run_id differ")
    _validate_scenario_slices(
        scenario,
        bars=bars,
        fx_rates=fx_rates,
        declared_actions=declared_actions,
    )
    if expected_intents is None:
        expected_intents = [
            (item.after_slice_sequence, intent)
            for item in scenario.schedule
            for intent in item.intents
        ]
    elif scenario.schedule:
        raise ValueError("external strategy validation requires an empty scenario schedule")
    if len(expected_intents) != len(scheduled_outcomes):
        raise ValueError("scenario and journal scheduled intent outcome counts differ")
    bar_by_key = {
        (cast("int", row["slice_sequence"]), cast("str", row["instrument_id"])): row for row in bars
    }
    valuation_by_sequence = {cast("int", row["slice_sequence"]): row for row in valuations}
    for (declared_sequence, intent), outcome in zip(
        expected_intents,
        scheduled_outcomes,
        strict=True,
    ):
        observed_sequence = cast("int", outcome["decision_slice_sequence"])
        if declared_sequence is not None and observed_sequence != declared_sequence:
            raise ValueError("scenario and journal scheduled intent order differs")
        sequence = observed_sequence if declared_sequence is None else declared_sequence
        rejection = outcome.get("rejection")
        if rejection is not None and cast("Mapping[str, object]", rejection)["reason"] == (
            "margin liquidation is in progress"
        ):
            if isinstance(intent, EmitMetricIntent):
                raise ValueError("metrics must remain available during margin liquidation")
            continue
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
                adjustments=order_adjustments,
                fills=fills,
                cancellations=cancellations,
            )
        else:
            _validate_scheduled_metric(intent, outcome)
    _validate_target_replacement_cancellations(
        scheduled_outcomes,
        orders=orders,
        adjustments=order_adjustments,
        fills=fills,
        cancellations=cancellations,
    )
    _validate_execution_values(
        scenario,
        bars=bars,
        fx_rates=fx_rates,
        orders=orders,
        order_adjustments=order_adjustments,
        fills=fills,
        cancellations=cancellations,
        actions=actions,
        margin_limits=margin_limits,
        borrow_fees=borrow_fees,
        margin_events=margin_events,
        valuations=valuations,
        cash_balances=cash_balances,
        position_attributions=positions,
    )


def _validate_scenario_slices(
    scenario: TradingEngineScenario,
    *,
    bars: Sequence[Mapping[str, object]],
    fx_rates: Sequence[Mapping[str, object]],
    declared_actions: Sequence[Mapping[str, object]],
) -> None:
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
        expected_volume = None if expected.volume is None else decimal_micros(expected.volume)
        observed_volume = (
            None if observed["volume_micros"] is pd.NA else cast("int", observed["volume_micros"])
        )
        if (
            market_slice.start_at != observed["start_at"]
            or market_slice.end_at != observed["end_at"]
            or market_slice.available_at != observed["available_at"]
            or market_slice.received_at != observed["received_at"]
            or decimal_micros(expected.open) != observed["open_micros"]
            or decimal_micros(expected.high) != observed["high_micros"]
            or decimal_micros(expected.low) != observed["low_micros"]
            or decimal_micros(expected.close) != observed["close_micros"]
            or expected_volume != observed_volume
        ):
            raise ValueError("scenario and journal market slices differ")
    expected_fx = {
        (market_slice.slice_sequence, mark.currency): decimal_micros(cast("Decimal", mark.rate))
        for market_slice in scenario.slices
        for mark in market_slice.fx_rates
    }
    observed_fx = {
        (cast("int", row["slice_sequence"]), cast("str", row["currency"])): cast(
            "int", row["rate_micros"]
        )
        for row in fx_rates
    }
    if expected_fx != observed_fx:
        raise ValueError("scenario and journal FX marks differ")
    expected_actions: dict[tuple[int, str], tuple[object, ...]] = {}
    for market_slice in scenario.slices:
        for action in market_slice.corporate_actions:
            if isinstance(action, SplitAction):
                value: tuple[object, ...] = (
                    action.instrument_id,
                    "split",
                    action.numerator,
                    action.denominator,
                    None,
                )
            else:
                value = (
                    action.instrument_id,
                    "cash_dividend",
                    None,
                    None,
                    decimal_micros(cast("Decimal", action.amount_per_unit)),
                )
            expected_actions[(market_slice.slice_sequence, action.action_id)] = value
    observed_actions = {
        (cast("int", row["slice_sequence"]), cast("str", row["action_id"])): (
            row["instrument_id"],
            row["action_type"],
            row["numerator"],
            row["denominator"],
            row["amount_per_unit_micros"],
        )
        for row in declared_actions
    }
    if expected_actions != observed_actions:
        raise ValueError("scenario and journal corporate actions differ")


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
    expected_rejection_reason: str | None = None
    if isinstance(intent, TargetWeightsIntent):
        for target in intent.targets:
            reference = cast("int", bar_by_key[(sequence, target.instrument_id)]["close_micros"])
            equity = cast("int", valuation_by_sequence[sequence]["equity_micros"])
            weight = decimal_micros(cast("Decimal", target.weight))
            lot = decimal_micros(
                cast(
                    "Decimal",
                    next(
                        item.lot_size
                        for item in scenario.instruments
                        if item.instrument_id == target.instrument_id
                    ),
                )
            )
            raw = _trunc_div(equity * weight * MICRO_SCALE, MICRO_SCALE * reference)
            quantity = _round_toward_zero(raw, lot)
            derived_quantities[target.instrument_id] = quantity
            if quantity > decimal_micros(cast("Decimal", scenario.risk.max_long_position)):
                expected_rejection_reason = "position would exceed the maximum long position"
            elif quantity < -decimal_micros(cast("Decimal", scenario.risk.max_short_position)):
                expected_rejection_reason = "position would exceed the maximum short position"
    if expected_rejection_reason is not None:
        if outcome["event_type"] != "intent_rejected":
            raise ValueError("journal portfolio target outcome differs from engine sizing")
        rejection = cast("Mapping[str, object]", outcome["rejection"])
        if rejection["reason"] != expected_rejection_reason:
            raise ValueError("journal portfolio target rejection reason differs")
        return
    if outcome["event_type"] != "target_portfolio_requested":
        raise ValueError("journal portfolio target outcome differs from engine sizing")
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
            if observed["quantity_micros"] != derived_quantities[target.instrument_id]:
                raise ValueError("journal target quantity differs from engine sizing")
    else:
        for target in intent.targets:
            observed = observed_by_id[target.instrument_id]
            _validate_target_reference(observed, sequence, target.instrument_id, bar_by_key)
            if observed["basis"] != "quantities" or observed["quantity_micros"] != decimal_micros(
                cast("Decimal", target.quantity)
            ):
                raise ValueError("scenario and journal target quantities differ")


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
        or order["quantity_micros"] != decimal_micros(cast("Decimal", intent.quantity))
        or order["order_kind"] != intent.order_kind
        or not _imported_values_equal(order["limit_price_micros"], expected_limit)
    ):
        raise ValueError("scenario submit_order request differs from the journal")


def _validate_scheduled_cancellation(
    intent: CancelOrderIntent,
    outcome: Mapping[str, object],
    *,
    orders: Sequence[Mapping[str, object]],
    adjustments: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> None:
    outcome_sequence = cast("int", outcome["engine_sequence"])
    status = _order_status_before(
        intent.order_id,
        outcome_sequence,
        orders=orders,
        adjustments=adjustments,
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


def _latest_order_snapshot_before(
    order_id: str,
    engine_sequence: int,
    *,
    orders: Sequence[Mapping[str, object]],
    adjustments: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    snapshots = [
        item
        for item in (*orders, *adjustments)
        if item["order_id"] == order_id and cast("int", item["engine_sequence"]) < engine_sequence
    ]
    return (
        None
        if not snapshots
        else max(snapshots, key=lambda item: cast("int", item["engine_sequence"]))
    )


def _order_status_before(
    order_id: str,
    engine_sequence: int,
    *,
    orders: Sequence[Mapping[str, object]],
    adjustments: Sequence[Mapping[str, object]],
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
    snapshot = _latest_order_snapshot_before(
        order_id,
        engine_sequence,
        orders=orders,
        adjustments=adjustments,
    )
    assert snapshot is not None
    filled = sum(
        cast("int", fill["quantity_micros"])
        for fill in fills
        if fill["order_id"] == order_id and cast("int", fill["engine_sequence"]) < engine_sequence
    )
    return "terminal" if filled >= cast("int", snapshot["quantity_micros"]) else "active"


def _working_orders_before(
    engine_sequence: int,
    *,
    orders: Sequence[Mapping[str, object]],
    adjustments: Sequence[Mapping[str, object]],
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
            adjustments=adjustments,
            fills=fills,
            cancellations=cancellations,
        )
        == "active"
    ]


def _validate_target_replacement_cancellations(
    scheduled_outcomes: Sequence[Mapping[str, object]],
    *,
    orders: Sequence[Mapping[str, object]],
    adjustments: Sequence[Mapping[str, object]],
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
                    adjustments=adjustments,
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


def _validate_execution_values(
    scenario: TradingEngineScenario,
    *,
    bars: Sequence[dict[str, object]],
    fx_rates: Sequence[dict[str, object]],
    orders: Sequence[dict[str, object]],
    order_adjustments: Sequence[dict[str, object]],
    fills: Sequence[dict[str, object]],
    cancellations: Sequence[dict[str, object]],
    actions: Sequence[dict[str, object]],
    margin_limits: Sequence[dict[str, object]],
    borrow_fees: Sequence[dict[str, object]],
    margin_events: Sequence[dict[str, object]],
    valuations: Sequence[dict[str, object]],
    cash_balances: Sequence[dict[str, object]],
    position_attributions: Sequence[dict[str, object]],
) -> None:
    instrument_by_id = {item.instrument_id: item for item in scenario.instruments}
    bar_by_key = {
        (cast("int", item["slice_sequence"]), cast("str", item["instrument_id"])): item
        for item in bars
    }
    fx_by_key = {
        (cast("int", item["slice_sequence"]), cast("str", item["currency"])): cast(
            "int", item["rate_micros"]
        )
        for item in fx_rates
    }
    expected_action_ids = {
        action.action_id
        for market_slice in scenario.slices
        for action in market_slice.corporate_actions
    }
    observed_action_ids = {cast("str", item["action_id"]) for item in actions}
    if observed_action_ids != expected_action_ids or len(actions) != len(observed_action_ids):
        raise ValueError("every scenario corporate action must be applied exactly once")
    _validate_order_and_fill_contracts(
        scenario,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        orders=orders,
        adjustments=order_adjustments,
        fills=fills,
        cancellations=cancellations,
    )
    _validate_participation_capacity(
        scenario,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        fills=fills,
    )
    _validate_runtime_path(
        scenario,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        fx_by_key=fx_by_key,
        orders=orders,
        adjustments=order_adjustments,
        fills=fills,
        cancellations=cancellations,
        actions=actions,
        margin_limits=margin_limits,
        borrow_fees=borrow_fees,
        margin_events=margin_events,
        valuations=valuations,
        cash_balances=cash_balances,
        position_attributions=position_attributions,
    )


def _validate_order_and_fill_contracts(
    scenario: TradingEngineScenario,
    *,
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    orders: Sequence[Mapping[str, object]],
    adjustments: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
) -> None:
    order_by_id = {cast("str", item["order_id"]): item for item in orders}
    if len(order_by_id) != len(orders):
        raise ValueError("order identifiers must be unique")
    for number, order in enumerate(orders, start=1):
        if order["order_id"] != f"{scenario.run_id}-order-{number:012d}":
            raise ValueError("order identifiers must follow the deterministic engine sequence")
        instrument = instrument_by_id.get(cast("str", order["instrument_id"]))
        if instrument is None:
            raise ValueError("order refers to an unknown scenario instrument")
        lot = decimal_micros(cast("Any", instrument).lot_size)
        if cast("int", order["quantity_micros"]) % lot:
            raise ValueError("order quantity is not lot aligned")
        if cast("int", order["quantity_micros"]) > decimal_micros(
            cast("Decimal", scenario.risk.max_order_quantity)
        ):
            qualifier = "accepted " if order["event_type"] == "order_accepted" else ""
            raise ValueError(f"{qualifier}order exceeds max_order_quantity")
        limit = order["limit_price_micros"]
        if limit is not pd.NA and cast("int", limit) % decimal_micros(
            cast("Any", instrument).tick_size
        ):
            raise ValueError("order limit price is not tick aligned")
    adjustment_by_id: dict[str, list[Mapping[str, object]]] = {}
    action_by_id = {
        action.action_id: action
        for market_slice in scenario.slices
        for action in market_slice.corporate_actions
    }
    for adjustment in adjustments:
        order_id = cast("str", adjustment["order_id"])
        previous = _latest_order_snapshot_before(
            order_id,
            cast("int", adjustment["engine_sequence"]),
            orders=orders,
            adjustments=adjustments,
        )
        if previous is None:
            raise ValueError("order adjustment refers to an unknown order")
        action = action_by_id.get(cast("str", adjustment["action_id"]))
        if not isinstance(action, SplitAction):
            raise ValueError("order adjustment must refer to a split action")
        if adjustment["instrument_id"] != action.instrument_id:
            raise ValueError("split-adjusted order instrument differs from its action")
        ratio_fields = ("quantity_micros", "filled_quantity_micros")
        for name in ratio_fields:
            prior = cast("int", previous[name]) * action.numerator
            if prior % action.denominator or prior // action.denominator != adjustment[name]:
                raise ValueError("split-adjusted order quantities do not reconcile")
        if previous["limit_price_micros"] is pd.NA:
            if adjustment["limit_price_micros"] is not pd.NA:
                raise ValueError("split changed a market order into a limit order")
        else:
            prior_limit = cast("int", previous["limit_price_micros"]) * action.denominator
            if (
                prior_limit % action.numerator
                or prior_limit // action.numerator != adjustment["limit_price_micros"]
            ):
                raise ValueError("split-adjusted order limit price does not reconcile")
        immutable = {
            "order_id",
            "instrument_id",
            "side",
            "order_kind",
            "origin",
            "created_event_id",
            "created_at",
            "created_sequence",
            "eligible_after_slice_sequence",
            "filled_notional_micros",
            "rejection_reason",
        }
        if any(not _imported_values_equal(previous[name], adjustment[name]) for name in immutable):
            raise ValueError("split-adjusted order changed immutable state")
        adjustment_by_id.setdefault(order_id, []).append(adjustment)
    fill_ids: set[str] = set()
    next_fill_number = 1
    for fill in fills:
        fill_id = cast("str", fill["fill_id"])
        if fill_id != f"{scenario.run_id}-fill-{next_fill_number:012d}":
            raise ValueError("fill identifiers must follow the deterministic engine sequence")
        next_fill_number += 1
        if fill_id in fill_ids:
            raise ValueError("fill identifiers must be unique")
        fill_ids.add(fill_id)
        order_id = cast("str", fill["order_id"])
        order = _latest_order_snapshot_before(
            order_id,
            cast("int", fill["engine_sequence"]),
            orders=orders,
            adjustments=adjustments,
        )
        if order is None or order_by_id[order_id]["event_type"] != "order_accepted":
            raise ValueError("fill must refer to an accepted imported order")
        if fill["instrument_id"] != order["instrument_id"] or fill["side"] != order["side"]:
            raise ValueError("fill instrument and side must match its order")
        instrument = cast("Any", instrument_by_id[cast("str", fill["instrument_id"])])
        if fill["quote_currency"] != instrument.quote_currency:
            raise ValueError("fill quote currency differs from its instrument")
        quantity = cast("int", fill["quantity_micros"])
        lot = decimal_micros(cast("Decimal", instrument.lot_size))
        if quantity % lot:
            raise ValueError("fill quantity is not lot aligned")
        tick = decimal_micros(cast("Decimal", instrument.tick_size))
        if cast("int", fill["price_micros"]) % tick:
            raise ValueError("fill price is not tick aligned")
        expected_fee = decimal_micros(cast("Decimal", scenario.execution.fixed_fee)) + _ceil_div(
            cast("int", fill["notional_micros"]) * scenario.execution.fee_bps,
            10_000,
        )
        if fill["fee_micros"] != expected_fee:
            raise ValueError("fill fee differs from the scenario execution policy")
        slice_sequence = cast("int", fill["slice_sequence"])
        bar = bar_by_key.get((slice_sequence, cast("str", fill["instrument_id"])))
        if bar is None:
            raise ValueError("fill must refer to an imported market slice")
        if slice_sequence <= cast("int", order["eligible_after_slice_sequence"]):
            raise ValueError("fill slice must follow order eligibility")
        if fill["recorded_at"] != bar["received_at"]:
            raise ValueError("fill must use its market slice receipt clock")
        if order["order_kind"] == "market":
            expected_time = bar["start_at"]
            expected_price = bar["open_micros"]
        else:
            limit = cast("int", order["limit_price_micros"])
            opening = cast("int", bar["open_micros"])
            crosses_open = (order["side"] == "buy" and opening <= limit) or (
                order["side"] == "sell" and opening >= limit
            )
            touches = (order["side"] == "buy" and cast("int", bar["low_micros"]) <= limit) or (
                order["side"] == "sell" and cast("int", bar["high_micros"]) >= limit
            )
            if crosses_open:
                expected_time = bar["start_at"]
                expected_price = opening
            elif touches:
                expected_time = bar["end_at"]
                expected_price = limit
            else:
                raise ValueError("limit fill requires an opening cross or intrabar touch")
        if fill["executed_at"] != expected_time or fill["price_micros"] != expected_price:
            raise ValueError("fill time and price must match the completed-slice model")
    cancelled_ids = [cast("str", item["order_id"]) for item in cancellations]
    if len(cancelled_ids) != len(set(cancelled_ids)):
        raise ValueError("an order may be cancelled at most once")


def _validate_participation_capacity(
    scenario: TradingEngineScenario,
    *,
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
) -> None:
    used_by_key: dict[tuple[int, str], int] = {}
    for fill in fills:
        key = (cast("int", fill["slice_sequence"]), cast("str", fill["instrument_id"]))
        used_by_key[key] = used_by_key.get(key, 0) + cast("int", fill["quantity_micros"])
    for key, used in used_by_key.items():
        bar = bar_by_key[key]
        if bar["volume_micros"] is pd.NA:
            continue
        lot = decimal_micros(cast("Any", instrument_by_id[key[1]]).lot_size)
        capacity = (
            cast("int", bar["volume_micros"]) * scenario.execution.participation_bps // 10_000
        )
        capacity = _round_toward_zero(capacity, lot)
        if used > capacity:
            raise ValueError("fills exceed the scenario slice participation capacity")


def _validate_runtime_path(
    scenario: TradingEngineScenario,
    *,
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fx_by_key: Mapping[tuple[int, str], int],
    orders: Sequence[dict[str, object]],
    adjustments: Sequence[dict[str, object]],
    fills: Sequence[dict[str, object]],
    cancellations: Sequence[dict[str, object]],
    actions: Sequence[dict[str, object]],
    margin_limits: Sequence[dict[str, object]],
    borrow_fees: Sequence[dict[str, object]],
    margin_events: Sequence[dict[str, object]],
    valuations: Sequence[dict[str, object]],
    cash_balances: Sequence[dict[str, object]],
    position_attributions: Sequence[dict[str, object]],
) -> None:
    cash = {
        item.currency: decimal_micros(cast("Decimal", item.amount))
        for item in scenario.initial_cash
    }
    positions = {item.instrument_id: _PositionState() for item in scenario.instruments}
    active_orders: dict[str, dict[str, object]] = {}
    accepted_order_ids = {
        cast("str", item["order_id"]) for item in orders if item["event_type"] == "order_accepted"
    }
    liquidation_pending = False
    pending_margin_cancellations: set[str] = set()
    events: list[tuple[int, str, dict[str, object]]] = []
    for event_type, rows in (
        ("order", orders),
        ("adjustment", adjustments),
        ("fill", fills),
        ("cancellation", cancellations),
        ("action", actions),
        ("margin_limit", margin_limits),
        ("borrow_fee", borrow_fees),
        ("margin_event", margin_events),
        ("valuation", valuations),
    ):
        events.extend((cast("int", item["engine_sequence"]), event_type, item) for item in rows)
    for _engine_sequence, event_type, event in sorted(events, key=lambda item: item[0]):
        sequence = _event_slice_sequence(event)
        if event_type == "action":
            _apply_action_state(
                event,
                cash=cash,
                positions=positions,
                instrument_by_id=instrument_by_id,
            )
        elif event_type == "borrow_fee":
            _apply_borrow_fee_state(
                event,
                scenario=scenario,
                cash=cash,
                positions=positions,
                instrument_by_id=instrument_by_id,
                bar_by_key=bar_by_key,
            )
        elif event_type == "order":
            error = _order_risk_error(
                event,
                scenario=scenario,
                cash=cash,
                positions=positions,
                active_orders=active_orders,
                instrument_by_id=instrument_by_id,
                bar_by_key=bar_by_key,
                fx_by_key=fx_by_key,
                slice_sequence=sequence,
            )
            if event["event_type"] == "order_accepted":
                if error is not None:
                    raise ValueError(f"accepted order failed runtime risk checks: {error}")
                if event["origin"] == "margin_liquidation":
                    if not liquidation_pending:
                        raise ValueError("liquidation orders require an active margin call")
                    _validate_liquidation_order(
                        event,
                        scenario=scenario,
                        positions=positions,
                        active_orders=active_orders,
                        instrument_by_id=instrument_by_id,
                    )
                elif liquidation_pending:
                    raise ValueError("only liquidation orders may be accepted during a margin call")
                if pending_margin_cancellations:
                    raise ValueError("margin-call cancellations must precede liquidation orders")
                active_orders[cast("str", event["order_id"])] = dict(event)
            else:
                if event["origin"] == "margin_liquidation":
                    raise ValueError("deterministic liquidation orders must be accepted")
                reason = event["rejection_reason"]
                if error is None or reason != error:
                    raise ValueError("order rejection differs from runtime risk checks")
        elif event_type == "adjustment":
            order_id = cast("str", event["order_id"])
            current = active_orders.get(order_id)
            if current is None:
                raise ValueError("only an active order may be split-adjusted")
            active_orders[order_id] = dict(event)
        elif event_type == "margin_limit":
            order_id = cast("str", event["order_id"])
            order = active_orders.get(order_id)
            if order is None:
                raise ValueError("margin_limited must refer to a working order")
            remaining = cast("int", order["quantity_micros"]) - cast(
                "int", order["filled_quantity_micros"]
            )
            if cast("int", event["requested_quantity_micros"]) > remaining:
                raise ValueError("margin_limited requested quantity exceeds the remaining order")
            expected = _permitted_fill_quantity(
                event,
                order=order,
                scenario=scenario,
                cash=cash,
                positions=positions,
                instrument_by_id=instrument_by_id,
                bar_by_key=bar_by_key,
                fx_by_key=fx_by_key,
            )
            if event["permitted_quantity_micros"] != expected:
                raise ValueError("margin_limited quantity does not reconcile to risk policy")
        elif event_type == "fill":
            order_id = cast("str", event["order_id"])
            order = active_orders.get(order_id)
            if order is None:
                raise ValueError("fill does not refer to a working accepted order")
            remaining = cast("int", order["quantity_micros"]) - cast(
                "int", order["filled_quantity_micros"]
            )
            quantity = cast("int", event["quantity_micros"])
            if quantity > remaining:
                raise ValueError("fills exceed their working order quantity")
            _apply_fill_state(event, cash=cash, positions=positions)
            order["filled_quantity_micros"] = (
                cast("int", order["filled_quantity_micros"]) + quantity
            )
            order["filled_notional_micros"] = cast("int", order["filled_notional_micros"]) + cast(
                "int", event["notional_micros"]
            )
            if order["filled_quantity_micros"] == order["quantity_micros"]:
                del active_orders[order_id]
        elif event_type == "cancellation":
            order_id = cast("str", event["order_id"])
            current = active_orders.get(order_id)
            if current is None:
                raise ValueError("only a working order may be cancelled")
            comparable = {
                "order_id",
                "instrument_id",
                "side",
                "quantity_micros",
                "order_kind",
                "limit_price_micros",
                "origin",
                "created_event_id",
                "updated_event_id",
                "created_at",
                "created_sequence",
                "eligible_after_slice_sequence",
                "filled_quantity_micros",
                "filled_notional_micros",
                "rejection_reason",
            }
            if any(not _imported_values_equal(current[name], event[name]) for name in comparable):
                raise ValueError("cancelled order state differs from its latest state")
            del active_orders[order_id]
            if event["reason"] == "margin_call":
                if order_id not in pending_margin_cancellations:
                    raise ValueError("margin-call cancellation was not triggered by a margin call")
                pending_margin_cancellations.remove(order_id)
            elif order_id in pending_margin_cancellations:
                raise ValueError("margin-call orders must use the margin_call cancellation reason")
        elif event_type == "margin_event":
            _validate_state_valuation(
                event,
                cash_rows=cast("Sequence[Mapping[str, object]]", event["_cash_rows"]),
                position_rows=cast("Sequence[Mapping[str, object]]", event["_position_rows"]),
                scenario=scenario,
                cash=cash,
                positions=positions,
                instrument_by_id=instrument_by_id,
                bar_by_key=bar_by_key,
                fx_by_key=fx_by_key,
                slice_sequence=sequence,
            )
            if event["event_type"] == "margin_call":
                if liquidation_pending:
                    raise ValueError("a second margin_call occurred before restoration")
                liquidation_pending = True
                pending_margin_cancellations = set(active_orders)
            else:
                if not liquidation_pending:
                    raise ValueError("margin_restored requires an active margin call")
                if pending_margin_cancellations or any(
                    state.quantity != 0 for state in positions.values()
                ):
                    raise ValueError(
                        "margin_restored requires flat positions and no pending cancels"
                    )
                liquidation_pending = False
        else:
            if pending_margin_cancellations:
                raise ValueError("valuation cannot precede all margin-call cancellations")
            if liquidation_pending:
                _validate_liquidation_coverage(
                    positions=positions,
                    active_orders=active_orders,
                )
            valuation_cash = [
                row for row in cash_balances if row["engine_sequence"] == event["engine_sequence"]
            ]
            valuation_positions = [
                row
                for row in position_attributions
                if row["engine_sequence"] == event["engine_sequence"]
            ]
            _validate_state_valuation(
                event,
                cash_rows=valuation_cash,
                position_rows=valuation_positions,
                scenario=scenario,
                cash=cash,
                positions=positions,
                instrument_by_id=instrument_by_id,
                bar_by_key=bar_by_key,
                fx_by_key=fx_by_key,
                slice_sequence=sequence,
            )
    if pending_margin_cancellations:
        raise ValueError("journal ended before margin-call cancellations completed")
    if any(order_id not in accepted_order_ids for order_id in active_orders):
        raise ValueError("runtime state contains an unknown active order")
    _validate_margin_limit_fills(margin_limits, fills=fills)


def _event_slice_sequence(event: Mapping[str, object]) -> int:
    if "slice_sequence" in event:
        return cast("int", event["slice_sequence"])
    return cast("int", event["eligible_after_slice_sequence"])


def _validate_liquidation_order(
    order: Mapping[str, object],
    *,
    scenario: TradingEngineScenario,
    positions: Mapping[str, _PositionState],
    active_orders: Mapping[str, Mapping[str, object]],
    instrument_by_id: Mapping[str, object],
) -> None:
    working_instruments = {
        cast("str", active["instrument_id"])
        for active in active_orders.values()
        if active["origin"] == "margin_liquidation"
    }
    expected_instrument_id = next(
        (
            instrument.instrument_id
            for instrument in sorted(
                scenario.instruments,
                key=lambda configured: configured.instrument_id,
            )
            if positions[instrument.instrument_id].quantity != 0
            and instrument.instrument_id not in working_instruments
        ),
        None,
    )
    if expected_instrument_id is None:
        raise ValueError("liquidation order has no uncovered open position")
    if order["instrument_id"] != expected_instrument_id:
        raise ValueError("liquidation orders must use deterministic instrument order")
    position_quantity = positions[expected_instrument_id].quantity
    expected_side = "sell" if position_quantity > 0 else "buy"
    if order["side"] != expected_side:
        raise ValueError("liquidation order side must reduce the open position")
    instrument = cast("Any", instrument_by_id[expected_instrument_id])
    lot = decimal_micros(cast("Decimal", instrument.lot_size))
    bounded_quantity = min(
        abs(position_quantity),
        decimal_micros(cast("Decimal", scenario.risk.max_order_quantity)),
    )
    expected_quantity = _round_toward_zero(bounded_quantity, lot)
    if expected_quantity == 0:
        raise ValueError("margin liquidation cannot cover one instrument lot")
    if order["quantity_micros"] != expected_quantity or order["order_kind"] != "market":
        raise ValueError("liquidation order must use the bounded market quantity")


def _validate_liquidation_coverage(
    *,
    positions: Mapping[str, _PositionState],
    active_orders: Mapping[str, Mapping[str, object]],
) -> None:
    liquidation_instruments = {
        cast("str", order["instrument_id"])
        for order in active_orders.values()
        if order["origin"] == "margin_liquidation"
    }
    open_instruments = {
        instrument_id for instrument_id, state in positions.items() if state.quantity != 0
    }
    if liquidation_instruments != open_instruments:
        raise ValueError("every open position requires one working liquidation order")


def _apply_action_state(
    event: Mapping[str, object],
    *,
    cash: dict[str, int],
    positions: dict[str, _PositionState],
    instrument_by_id: Mapping[str, object],
) -> None:
    instrument_id = cast("str", event["instrument_id"])
    state = positions[instrument_id]
    if event["action_type"] == "split":
        if event["previous_quantity_micros"] != state.quantity:
            raise ValueError("split previous quantity differs from account state")
        numerator = cast("int", event["numerator"])
        denominator = cast("int", event["denominator"])
        product = state.quantity * numerator
        if product % denominator:
            raise ValueError("split account quantity is not exactly representable")
        state.quantity = product // denominator
        if event["adjusted_quantity_micros"] != state.quantity:
            raise ValueError("split adjusted quantity differs from account state")
        return
    if event["quantity_micros"] != state.quantity:
        raise ValueError("cash dividend quantity differs from account state")
    amount = _trunc_div(
        cast("int", event["amount_per_unit_micros"]) * state.quantity,
        MICRO_SCALE,
    )
    if event["cash_amount_micros"] != amount:
        raise ValueError("cash dividend differs from account state")
    currency = cast("Any", instrument_by_id[instrument_id]).quote_currency
    cash[currency] += amount
    state.realized_pnl += amount
    state.dividend_pnl += amount


def _apply_borrow_fee_state(
    event: Mapping[str, object],
    *,
    scenario: TradingEngineScenario,
    cash: dict[str, int],
    positions: dict[str, _PositionState],
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
) -> None:
    instrument_id = cast("str", event["instrument_id"])
    state = positions[instrument_id]
    if state.quantity >= 0 or event["short_quantity_micros"] != -state.quantity:
        raise ValueError("borrow fee must match an open short position")
    instrument = cast("Any", instrument_by_id[instrument_id])
    if event["quote_currency"] != instrument.quote_currency:
        raise ValueError("borrow fee quote currency differs from its instrument")
    if event["borrow_bps"] != scenario.risk.short_borrow_bps:
        raise ValueError("borrow fee basis points differ from the risk policy")
    sequence = cast("int", event["slice_sequence"])
    bar = bar_by_key[(sequence, instrument_id)]
    if (
        event["reference_price_micros"] != bar["open_micros"]
        or event["period_start"] != bar["start_at"]
        or event["period_end"] != bar["end_at"]
    ):
        raise ValueError("borrow fee period and reference must match its market slice")
    notional = _trunc_div(
        cast("int", event["reference_price_micros"]) * cast("int", event["short_quantity_micros"]),
        MICRO_SCALE,
    )
    duration_picoseconds = (
        cast("pd.Timestamp", event["period_end"]).value
        - cast("pd.Timestamp", event["period_start"]).value
    ) * 1_000
    expected_fee = _ceil_div(
        notional * cast("int", event["borrow_bps"]) * duration_picoseconds,
        10_000 * 365 * 86_400 * 1_000_000_000_000,
    )
    if event["fee_micros"] != expected_fee:
        raise ValueError("borrow fee does not reconcile to quantity, price, and period")
    cash[instrument.quote_currency] -= expected_fee
    state.realized_pnl -= expected_fee
    state.borrow_fees += expected_fee


def _apply_fill_state(
    fill: Mapping[str, object],
    *,
    cash: dict[str, int],
    positions: dict[str, _PositionState],
) -> None:
    instrument_id = cast("str", fill["instrument_id"])
    currency = cast("str", fill["quote_currency"])
    state = positions[instrument_id]
    quantity = cast("int", fill["quantity_micros"])
    notional = cast("int", fill["notional_micros"])
    fee = cast("int", fill["fee_micros"])
    if fill["side"] == "buy":
        projected = state.quantity + quantity
        if state.quantity < 0 < projected:
            raise ValueError("one fill must not cross a short position through zero")
        if state.quantity < 0:
            short_quantity = -state.quantity
            removed_basis = (
                state.cost_basis
                if projected == 0
                else _trunc_div(state.cost_basis * quantity, short_quantity)
            )
            cover_cost = notional + fee
            cash[currency] -= cover_cost
            state.cost_basis -= removed_basis
            state.realized_pnl += -cover_cost - removed_basis
        else:
            acquisition = notional + fee
            cash[currency] -= acquisition
            state.cost_basis += acquisition
    else:
        projected = state.quantity - quantity
        if state.quantity > 0 > projected:
            raise ValueError("one fill must not cross a long position through zero")
        if state.quantity > 0:
            removed_basis = (
                state.cost_basis
                if projected == 0
                else _trunc_div(state.cost_basis * quantity, state.quantity)
            )
            proceeds = notional - fee
            cash[currency] += proceeds
            state.cost_basis -= removed_basis
            state.realized_pnl += proceeds - removed_basis
        else:
            proceeds = notional - fee
            cash[currency] += proceeds
            state.cost_basis -= proceeds
    state.quantity = projected
    state.execution_fees += fee


def _order_risk_error(
    order: Mapping[str, object],
    *,
    scenario: TradingEngineScenario,
    cash: Mapping[str, int],
    positions: Mapping[str, _PositionState],
    active_orders: Mapping[str, Mapping[str, object]],
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fx_by_key: Mapping[tuple[int, str], int],
    slice_sequence: int,
) -> str | None:
    quantity = cast("int", order["quantity_micros"])
    if quantity > decimal_micros(cast("Decimal", scenario.risk.max_order_quantity)):
        return "order exceeds the maximum order quantity"
    instrument_id = cast("str", order["instrument_id"])
    instrument = cast("Any", instrument_by_id[instrument_id])
    lot = decimal_micros(cast("Decimal", instrument.lot_size))
    if quantity % lot:
        return "order quantity is not aligned to the instrument lot size"
    if order["limit_price_micros"] is not pd.NA and cast(
        "int", order["limit_price_micros"]
    ) % decimal_micros(cast("Decimal", instrument.tick_size)):
        return "limit price is not aligned to the instrument tick size"
    projected: dict[str, int] = {}
    for configured_id, state in positions.items():
        pending = state.quantity
        for active in active_orders.values():
            if active["instrument_id"] != configured_id:
                continue
            remaining = cast("int", active["quantity_micros"]) - cast(
                "int", active["filled_quantity_micros"]
            )
            pending += remaining if active["side"] == "buy" else -remaining
        projected[configured_id] = pending
    pending = projected[instrument_id]
    candidate = pending + quantity if order["side"] == "buy" else pending - quantity
    if (pending > 0 > candidate) or (pending < 0 < candidate):
        return "one order must not cross a position through zero"
    projected[instrument_id] = candidate
    if abs(candidate) <= abs(pending):
        return None
    long_limit = decimal_micros(cast("Decimal", scenario.risk.max_long_position))
    short_limit = decimal_micros(cast("Decimal", scenario.risk.max_short_position))
    if candidate > long_limit:
        return "position would exceed the maximum long position"
    if candidate < -short_limit:
        return "position would exceed the maximum short position"
    before = _account_values(
        scenario,
        cash=cash,
        positions=positions,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        fx_by_key=fx_by_key,
        slice_sequence=slice_sequence,
        mark_field="close_micros",
    )
    projected_gross = 0
    for configured_id, projected_quantity in projected.items():
        configured = cast("Any", instrument_by_id[configured_id])
        native = abs(
            _trunc_div(
                cast("int", bar_by_key[(slice_sequence, configured_id)]["close_micros"])
                * projected_quantity,
                MICRO_SCALE,
            )
        )
        projected_gross += _trunc_div(
            native * fx_by_key[(slice_sequence, configured.quote_currency)],
            MICRO_SCALE,
        )
    return _initial_risk_error(
        scenario,
        equity=before["equity"],
        gross_exposure=projected_gross,
    )


def _initial_risk_error(
    scenario: TradingEngineScenario,
    *,
    equity: int,
    gross_exposure: int,
) -> str | None:
    if gross_exposure > decimal_micros(cast("Decimal", scenario.risk.max_gross_exposure)):
        return "portfolio would exceed maximum gross exposure"
    leveraged_equity = _trunc_div(
        equity * decimal_micros(cast("Decimal", scenario.risk.max_leverage)),
        MICRO_SCALE,
    )
    if gross_exposure > leveraged_equity:
        return "portfolio would exceed maximum leverage"
    initial_requirement = _ceil_div(
        gross_exposure * scenario.risk.initial_margin_bps,
        10_000,
    )
    if equity - initial_requirement < 0:
        return "portfolio would violate initial margin"
    return None


def _permitted_fill_quantity(
    limited: Mapping[str, object],
    *,
    order: Mapping[str, object],
    scenario: TradingEngineScenario,
    cash: Mapping[str, int],
    positions: Mapping[str, _PositionState],
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fx_by_key: Mapping[tuple[int, str], int],
) -> int:
    sequence = cast("int", limited["slice_sequence"])
    instrument_id = cast("str", limited["instrument_id"])
    instrument = cast("Any", instrument_by_id[instrument_id])
    lot = decimal_micros(cast("Decimal", instrument.lot_size))
    requested = cast("int", limited["requested_quantity_micros"])
    if requested % lot:
        raise ValueError("margin_limited requested quantity is not lot aligned")
    before = _account_values(
        scenario,
        cash=cash,
        positions=positions,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        fx_by_key=fx_by_key,
        slice_sequence=sequence,
        mark_field="open_micros",
    )

    def allowed(quantity: int) -> bool:
        if quantity == 0:
            return True
        candidate_cash = dict(cash)
        candidate_positions = _copy_positions(positions)
        price = cast("int", limited["price_micros"])
        notional = _trunc_div(price * quantity, MICRO_SCALE)
        fee = decimal_micros(cast("Decimal", scenario.execution.fixed_fee)) + _ceil_div(
            notional * scenario.execution.fee_bps,
            10_000,
        )
        fill = {
            "instrument_id": instrument_id,
            "quote_currency": instrument.quote_currency,
            "side": order["side"],
            "quantity_micros": quantity,
            "notional_micros": notional,
            "fee_micros": fee,
        }
        current_quantity = candidate_positions[instrument_id].quantity
        try:
            _apply_fill_state(
                fill,
                cash=candidate_cash,
                positions=candidate_positions,
            )
        except ValueError:
            return False
        after_quantity = candidate_positions[instrument_id].quantity
        if abs(after_quantity) > abs(current_quantity):
            if after_quantity > decimal_micros(
                cast("Decimal", scenario.risk.max_long_position)
            ) or after_quantity < -decimal_micros(
                cast("Decimal", scenario.risk.max_short_position)
            ):
                return False
        after = _account_values(
            scenario,
            cash=candidate_cash,
            positions=candidate_positions,
            instrument_by_id=instrument_by_id,
            bar_by_key=bar_by_key,
            fx_by_key=fx_by_key,
            slice_sequence=sequence,
            mark_field="open_micros",
        )
        if after["gross_exposure"] <= before["gross_exposure"]:
            return True
        return (
            _initial_risk_error(
                scenario,
                equity=after["equity"],
                gross_exposure=after["gross_exposure"],
            )
            is None
        )

    low = 0
    high = requested // lot
    while low < high:
        middle = low + (high - low + 1) // 2
        if allowed(middle * lot):
            low = middle
        else:
            high = middle - 1
    return low * lot


def _validate_margin_limit_fills(
    margin_limits: Sequence[Mapping[str, object]],
    *,
    fills: Sequence[Mapping[str, object]],
) -> None:
    keys: set[tuple[str, int]] = set()
    for limited in margin_limits:
        key = (
            cast("str", limited["order_id"]),
            cast("int", limited["slice_sequence"]),
        )
        if key in keys:
            raise ValueError("margin_limited must occur at most once per order and slice")
        keys.add(key)
        matching = [
            fill
            for fill in fills
            if fill["order_id"] == key[0] and fill["slice_sequence"] == key[1]
        ]
        permitted = cast("int", limited["permitted_quantity_micros"])
        if sum(cast("int", fill["quantity_micros"]) for fill in matching) != permitted:
            raise ValueError("margin_limited permitted quantity must match its same-slice fill")
        if matching and (
            len(matching) != 1
            or matching[0]["price_micros"] != limited["price_micros"]
            or cast("int", matching[0]["engine_sequence"])
            <= cast("int", limited["engine_sequence"])
        ):
            raise ValueError("margin-limited fill must follow at its audited price")


def _account_values(
    scenario: TradingEngineScenario,
    *,
    cash: Mapping[str, int],
    positions: Mapping[str, _PositionState],
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fx_by_key: Mapping[tuple[int, str], int],
    slice_sequence: int,
    mark_field: str,
) -> dict[str, int]:
    values, _cash_values, _position_values = _account_snapshot(
        scenario,
        cash=cash,
        positions=positions,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        fx_by_key=fx_by_key,
        slice_sequence=slice_sequence,
        mark_field=mark_field,
    )
    return values


def _account_snapshot(
    scenario: TradingEngineScenario,
    *,
    cash: Mapping[str, int],
    positions: Mapping[str, _PositionState],
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fx_by_key: Mapping[tuple[int, str], int],
    slice_sequence: int,
    mark_field: str,
) -> tuple[
    dict[str, int],
    dict[str, dict[str, int]],
    dict[str, dict[str, int | str]],
]:
    del scenario
    cash_values: dict[str, dict[str, int]] = {}
    cash_total = 0
    for currency, amount in sorted(cash.items()):
        rate = fx_by_key[(slice_sequence, currency)]
        base_value = _trunc_div(amount * rate, MICRO_SCALE)
        cash_values[currency] = {
            "amount": amount,
            "fx_rate": rate,
            "base_value": base_value,
        }
        cash_total += base_value
    position_values: dict[str, dict[str, int | str]] = {}
    aggregates = {
        "net_market_value": 0,
        "long_market_value": 0,
        "short_market_value": 0,
        "cost_basis": 0,
        "realized_pnl": 0,
        "unrealized_pnl": 0,
        "dividend_pnl": 0,
        "execution_fees": 0,
        "borrow_fees": 0,
        "total_fees": 0,
    }
    for instrument_id, instrument_value in sorted(instrument_by_id.items()):
        instrument = cast("Any", instrument_value)
        state = positions[instrument_id]
        mark = cast("int", bar_by_key[(slice_sequence, instrument_id)][mark_field])
        rate = fx_by_key[(slice_sequence, instrument.quote_currency)]
        market_value = _trunc_div(mark * state.quantity, MICRO_SCALE)
        unrealized_pnl = market_value - state.cost_basis
        total_fees = state.execution_fees + state.borrow_fees
        native = {
            "market_value": market_value,
            "cost_basis": state.cost_basis,
            "realized_pnl": state.realized_pnl,
            "unrealized_pnl": unrealized_pnl,
            "dividend_pnl": state.dividend_pnl,
            "execution_fees": state.execution_fees,
            "borrow_fees": state.borrow_fees,
            "total_fees": total_fees,
        }
        row: dict[str, int | str] = {
            "quote_currency": instrument.quote_currency,
            "quantity": state.quantity,
            "mark": mark,
            "fx_rate": rate,
            **native,
        }
        for name, value in native.items():
            base_value = _trunc_div(value * rate, MICRO_SCALE)
            row[f"base_{name}"] = base_value
            aggregate_name = "net_market_value" if name == "market_value" else name
            aggregates[aggregate_name] += base_value
        base_market = cast("int", row["base_market_value"])
        if base_market >= 0:
            aggregates["long_market_value"] += base_market
        else:
            aggregates["short_market_value"] += -base_market
        position_values[instrument_id] = row
    aggregates["gross_exposure"] = (
        aggregates["long_market_value"] + aggregates["short_market_value"]
    )
    aggregates["cash"] = cash_total
    aggregates["equity"] = cash_total + aggregates["net_market_value"]
    return aggregates, cash_values, position_values


def _validate_state_valuation(
    valuation: Mapping[str, object],
    *,
    cash_rows: Sequence[Mapping[str, object]],
    position_rows: Sequence[Mapping[str, object]],
    scenario: TradingEngineScenario,
    cash: Mapping[str, int],
    positions: Mapping[str, _PositionState],
    instrument_by_id: Mapping[str, object],
    bar_by_key: Mapping[tuple[int, str], Mapping[str, object]],
    fx_by_key: Mapping[tuple[int, str], int],
    slice_sequence: int,
) -> None:
    expected, expected_cash, expected_positions = _account_snapshot(
        scenario,
        cash=cash,
        positions=positions,
        instrument_by_id=instrument_by_id,
        bar_by_key=bar_by_key,
        fx_by_key=fx_by_key,
        slice_sequence=slice_sequence,
        mark_field="close_micros",
    )
    if valuation["base_currency"] != scenario.base_currency:
        raise ValueError("valuation base currency differs from the scenario")
    for name, amount in expected.items():
        if valuation[f"{name}_micros"] != amount:
            raise ValueError(f"valuation {name} does not reconcile to account state")
    observed_cash = {cast("str", row["currency"]): row for row in cash_rows}
    if set(observed_cash) != set(expected_cash):
        raise ValueError("valuation cash ledgers differ from scenario currencies")
    for currency, values in expected_cash.items():
        row = observed_cash[currency]
        for name, amount in values.items():
            if row[f"{name}_micros"] != amount:
                raise ValueError("cash attribution does not reconcile to account state")
    observed_positions = {cast("str", row["instrument_id"]): row for row in position_rows}
    if set(observed_positions) != set(expected_positions):
        raise ValueError("position attributions must cover every scenario instrument")
    for instrument_id, values in expected_positions.items():
        row = observed_positions[instrument_id]
        for name, amount in values.items():
            if name == "quote_currency":
                if row[name] != amount:
                    raise ValueError("position quote currency differs from account state")
            elif row[f"{name}_micros"] != amount:
                raise ValueError("position attribution does not reconcile to account state")
    initial_requirement = _ceil_div(
        expected["gross_exposure"] * scenario.risk.initial_margin_bps,
        10_000,
    )
    maintenance_requirement = _ceil_div(
        expected["gross_exposure"] * scenario.risk.maintenance_margin_bps,
        10_000,
    )
    margin_expected = {
        "initial_requirement_micros": initial_requirement,
        "maintenance_requirement_micros": maintenance_requirement,
        "initial_excess_micros": expected["equity"] - initial_requirement,
        "maintenance_excess_micros": expected["equity"] - maintenance_requirement,
    }
    if any(valuation[name] != amount for name, amount in margin_expected.items()):
        raise ValueError("valuation margin snapshot differs from the scenario risk policy")
    if bool(valuation["margin_call"]) != (margin_expected["maintenance_excess_micros"] < 0):
        raise ValueError("valuation margin-call state differs from the risk policy")


def _validate_completion(
    completion: RunCompletion,
    *,
    completion_valuation: Mapping[str, object],
    completion_cash_rows: Sequence[Mapping[str, object]],
    completion_position_rows: Sequence[Mapping[str, object]],
    bars: Sequence[Mapping[str, object]],
    orders: Sequence[Mapping[str, object]],
    order_adjustments: Sequence[Mapping[str, object]],
    fills: Sequence[Mapping[str, object]],
    cancellations: Sequence[Mapping[str, object]],
    valuations: Sequence[Mapping[str, object]],
    cash_balances: Sequence[Mapping[str, object]],
    positions: Sequence[Mapping[str, object]],
    scenario: TradingEngineScenario | None,
) -> None:
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
    valuation_fields = {
        "base_currency",
        *{f"{name}_micros" for name in _VALUATION_MONEY_FIELDS},
        "initial_requirement_micros",
        "maintenance_requirement_micros",
        "initial_excess_micros",
        "maintenance_excess_micros",
        "margin_call",
    }
    if valuations:
        final = valuations[-1]
        if any(
            not _imported_values_equal(final[name], completion_valuation[name])
            for name in valuation_fields
        ):
            raise ValueError("run_completed valuation must match the final valuation event")
        final_cash = [
            row for row in cash_balances if row["engine_sequence"] == final["engine_sequence"]
        ]
        final_positions = [
            row for row in positions if row["engine_sequence"] == final["engine_sequence"]
        ]
        _compare_attribution_rows(
            final_cash,
            completion_cash_rows,
            key="currency",
            fields={
                "currency",
                "amount_micros",
                "fx_rate_micros",
                "base_value_micros",
            },
            name="cash balances",
        )
        _compare_attribution_rows(
            final_positions,
            completion_position_rows,
            key="instrument_id",
            fields={
                "instrument_id",
                "quote_currency",
                "quantity_micros",
                "mark_micros",
                "fx_rate_micros",
                *{
                    f"{name}_micros"
                    for name in _POSITION_NATIVE_MONEY_FIELDS | _POSITION_BASE_MONEY_FIELDS
                },
            },
            name="positions",
        )
    else:
        if completion_position_rows:
            raise ValueError("empty-run completion must not contain position attributions")
        if scenario is not None:
            initial = {
                item.currency: decimal_micros(cast("Decimal", item.amount))
                for item in scenario.initial_cash
            }
            if set(initial) != {scenario.base_currency}:
                raise ValueError("empty multi-currency runs cannot be valued without FX marks")
            initial_amount = initial[scenario.base_currency]
            if (
                completion.cash_micros != initial_amount
                or completion.equity_micros != initial_amount
                or any(
                    value != 0
                    for value in (
                        completion.net_market_value_micros,
                        completion.long_market_value_micros,
                        completion.short_market_value_micros,
                        completion.gross_exposure_micros,
                        completion.cost_basis_micros,
                        completion.realized_pnl_micros,
                        completion.unrealized_pnl_micros,
                        completion.dividend_pnl_micros,
                        completion.execution_fees_micros,
                        completion.borrow_fees_micros,
                        completion.total_fees_micros,
                    )
                )
            ):
                raise ValueError("empty-run completion must reconcile to scenario initial cash")
    observed_counts = _terminal_order_counts(
        orders,
        adjustments=order_adjustments,
        fills=fills,
        cancellations=cancellations,
    )
    completion_counts = {
        "total": completion.total_orders,
        "active": completion.active_orders,
        "filled": completion.filled_orders,
        "rejected": completion.rejected_orders,
        "cancelled": completion.cancelled_orders,
    }
    if observed_counts != completion_counts:
        raise ValueError("run_completed order counts must match imported order state")


def _initial_cash_frame(
    scenario: TradingEngineScenario | None,
    *,
    fx_rows: Sequence[Mapping[str, object]],
) -> tuple[pd.DataFrame | None, int | None]:
    if scenario is None:
        return None, None
    first_sequence = scenario.slices[0].slice_sequence if scenario.slices else None
    first_fx = {
        cast("str", row["currency"]): cast("int", row["rate_micros"])
        for row in fx_rows
        if row["slice_sequence"] == first_sequence
    }
    rows: list[dict[str, object]] = []
    initial_equity = 0
    complete = True
    for balance in scenario.initial_cash:
        amount = decimal_micros(cast("Decimal", balance.amount))
        rate = first_fx.get(balance.currency)
        if rate is None and balance.currency == scenario.base_currency:
            rate = MICRO_SCALE
        base_value = None if rate is None else _trunc_div(amount * rate, MICRO_SCALE)
        if base_value is None:
            complete = False
        else:
            initial_equity += base_value
        rows.append(
            {
                "currency": balance.currency,
                "amount": amount / MICRO_SCALE,
                "amount_micros": amount,
                "fx_rate": pd.NA if rate is None else rate / MICRO_SCALE,
                "fx_rate_micros": pd.NA if rate is None else rate,
                "base_value": pd.NA if base_value is None else base_value / MICRO_SCALE,
                "base_value_micros": pd.NA if base_value is None else base_value,
            }
        )
    return _typed_frame(rows, _INITIAL_CASH_DTYPES), initial_equity if complete else None


def _money_pair(
    name: str,
    value: object,
    *,
    positive: bool = False,
    nonnegative: bool = False,
) -> dict[str, object]:
    amount = _decimal_payload(
        value,
        name=name,
        positive=positive,
        nonnegative=nonnegative,
    )
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
) -> tuple[TradingEngineScenario | None, str | None]:
    if scenario is None:
        return None, None
    if isinstance(scenario, TradingEngineScenario):
        document = scenario_to_jsonl(scenario).encode()
        return scenario, hashlib.sha256(document).hexdigest()
    path = Path(scenario).expanduser()
    document = path.read_bytes()
    parser = scenario_from_jsonl if path.suffix == ".jsonl" else scenario_from_json
    return parser(document.decode("utf-8")), hashlib.sha256(document).hexdigest()


def _resolve_strategy_transcript(
    value: StrategyTranscript | str | Path | None,
    *,
    scenario: TradingEngineScenario | None,
    scenario_sha256: str | None,
) -> StrategyTranscript | None:
    if value is None:
        return None
    expected_run_id = None if scenario is None else scenario.run_id
    if isinstance(value, StrategyTranscript):
        transcript = value
    else:
        transcript = read_strategy_transcript(
            value,
            scenario_sha256=scenario_sha256,
            run_id=expected_run_id,
        )
    if scenario_sha256 is not None and transcript.initialization.scenario_sha256 != scenario_sha256:
        raise ValueError("strategy transcript scenario SHA-256 differs from the journal scenario")
    if expected_run_id is not None and transcript.initialization.run_id != expected_run_id:
        raise ValueError("strategy transcript run_id differs from the journal scenario")
    return transcript
