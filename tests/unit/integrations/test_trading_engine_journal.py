"""Tests for strict Trading Engine journal import and reconciliation."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from importlib import import_module
from typing import TYPE_CHECKING, Any

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    read_journal,
    scenario_from_json,
    write_scenario,
    write_scenario_stream,
)
from persistra.integrations.trading_engine._scalars import (
    decimal_micros,
    decimal_string,
    decimal_value,
)

if TYPE_CHECKING:
    from pathlib import Path


def scenario_document(*, basis: str = "quantities", initial_cash: str = "10000") -> str:
    """Return a two-slice, one-instrument scenario document."""
    target = (
        {"type": "target_weights", "targets": [{"instrument_id": "asset-a", "weight": "0.5"}]}
        if basis == "weights"
        else {
            "type": "target_quantities",
            "targets": [{"instrument_id": "asset-a", "quantity": "6"}],
        }
    )
    return json.dumps(
        {
            "contract_version": "3",
            "run_id": "journal-demo",
            "base_currency": "USD",
            "initial_cash": [{"currency": "USD", "amount": initial_cash}],
            "instruments": [
                {
                    "instrument_id": "asset-a",
                    "symbol": "AAA",
                    "quote_currency": "USD",
                    "tick_size": "0.01",
                    "lot_size": "1",
                }
            ],
            "risk": {
                "max_order_quantity": "1000",
                "max_long_position": "1000",
                "max_short_position": "1000",
                "max_gross_exposure": "1000000",
                "max_leverage": "2",
                "initial_margin_bps": 5000,
                "maintenance_margin_bps": 2500,
                "short_borrow_bps": 0,
            },
            "execution": {
                "model": "completed_bar_v1",
                "participation_bps": 5000,
                "fixed_fee": "0.25",
                "fee_bps": 10,
            },
            "max_internal_events": 1000,
            "metadata": {},
            "schedule": [{"after_slice_sequence": "1", "intents": [target]}],
            "slices": [
                {
                    "slice_sequence": "1",
                    "start_at": "2026-01-02T14:30:00.000000Z",
                    "end_at": "2026-01-02T14:35:00.000000Z",
                    "available_at": "2026-01-02T14:35:01.000000Z",
                    "received_at": "2026-01-02T14:35:03.000000Z",
                    "bars": [
                        {
                            "instrument_id": "asset-a",
                            "open": "99",
                            "high": "101",
                            "low": "98",
                            "close": "100",
                            "volume": "100",
                        }
                    ],
                    "fx_rates": [{"currency": "USD", "rate": "1"}],
                    "corporate_actions": [],
                },
                {
                    "slice_sequence": "2",
                    "start_at": "2026-01-02T14:40:00.000000Z",
                    "end_at": "2026-01-02T14:45:00.000000Z",
                    "available_at": "2026-01-02T14:45:00.000000Z",
                    "received_at": "2026-01-02T14:45:00.000000Z",
                    "bars": [
                        {
                            "instrument_id": "asset-a",
                            "open": "101",
                            "high": "103",
                            "low": "100",
                            "close": "102",
                            "volume": "100",
                        }
                    ],
                    "fx_rates": [{"currency": "USD", "rate": "1"}],
                    "corporate_actions": [],
                },
            ],
        }
    )


def write_scenario_fixture(path: Path, *, basis: str = "quantities", initial_cash: str = "10000"):
    scenario = scenario_from_json(scenario_document(basis=basis, initial_cash=initial_cash))
    write_scenario(scenario, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return scenario, digest


def envelope(
    sequence: int,
    event_type: str,
    payload: object,
    *,
    recorded_at: str,
) -> dict[str, Any]:
    return {
        "contract_version": "3",
        "engine_sequence": str(sequence),
        "event_id": f"journal-demo-event-{sequence:012d}",
        "causation_ids": [],
        "run_id": "journal-demo",
        "recorded_at": recorded_at,
        "event_type": event_type,
        "payload": payload,
    }


def valuation_payload(
    *,
    mark: str,
    quantity: str,
    cash: str,
    market_value: str,
    cost_basis: str,
    realized_pnl: str,
    unrealized_pnl: str,
    equity: str,
    total_fees: str,
) -> dict[str, Any]:
    market_micros = decimal_micros(decimal_value(market_value, name="market_value"))
    equity_micros = decimal_micros(decimal_value(equity, name="equity"))
    long_micros = max(market_micros, 0)
    short_micros = max(-market_micros, 0)
    gross_micros = long_micros + short_micros
    initial_requirement = (gross_micros * 5000 + 9999) // 10000
    maintenance_requirement = (gross_micros * 2500 + 9999) // 10000

    def money(micros: int) -> str:
        return decimal_string(Decimal(micros) / Decimal(1_000_000))

    position = {
        "instrument_id": "asset-a",
        "quote_currency": "USD",
        "quantity": quantity,
        "mark": mark,
        "fx_rate": "1",
        "market_value": market_value,
        "base_market_value": market_value,
        "cost_basis": cost_basis,
        "base_cost_basis": cost_basis,
        "realized_pnl": realized_pnl,
        "base_realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "base_unrealized_pnl": unrealized_pnl,
        "dividend_pnl": "0",
        "base_dividend_pnl": "0",
        "execution_fees": total_fees,
        "base_execution_fees": total_fees,
        "borrow_fees": "0",
        "base_borrow_fees": "0",
        "total_fees": total_fees,
        "base_total_fees": total_fees,
    }
    return {
        "base_currency": "USD",
        "cash": cash,
        "net_market_value": market_value,
        "long_market_value": money(long_micros),
        "short_market_value": money(short_micros),
        "gross_exposure": money(gross_micros),
        "cost_basis": cost_basis,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
        "equity": equity,
        "dividend_pnl": "0",
        "execution_fees": total_fees,
        "borrow_fees": "0",
        "total_fees": total_fees,
        "cash_balances": [
            {"currency": "USD", "amount": cash, "fx_rate": "1", "base_value": cash}
        ],
        "positions": [position],
        "margin": {
            "initial_requirement": money(initial_requirement),
            "maintenance_requirement": money(maintenance_requirement),
            "initial_excess": money(equity_micros - initial_requirement),
            "maintenance_excess": money(equity_micros - maintenance_requirement),
            "margin_call": equity_micros - maintenance_requirement < 0,
        },
    }


def normalize_audit_graph(records: list[dict[str, Any]]) -> None:
    current_slice_event_id: str | None = None
    order_events: dict[str, str] = {}
    order_updates: dict[str, str] = {}
    previous_event_id: str | None = None
    for record in records:
        sequence = int(record["engine_sequence"])
        event_id = f"journal-demo-event-{sequence:012d}"
        record["event_id"] = event_id
        event_type = record["event_type"]
        payload = record["payload"]
        causes: list[str] = []
        if event_type == "run_started":
            payload.setdefault("execution_model", "completed_bar_v1")
        elif event_type == "market_slice_received":
            current_slice_event_id = event_id
        elif event_type in {"order_accepted", "order_rejected"}:
            payload["created_sequence"] = str(sequence)
            payload["created_event_id"] = event_id
            payload["updated_event_id"] = event_id
            order_events[payload["order_id"]] = event_id
            order_updates[payload["order_id"]] = event_id
            if current_slice_event_id is not None:
                causes.append(current_slice_event_id)
        elif event_type in {"fill_applied", "margin_limited"}:
            causes.append(order_events[payload["order_id"]])
            causes.append(order_updates[payload["order_id"]])
            if current_slice_event_id is not None:
                causes.append(current_slice_event_id)
        elif event_type == "order_cancelled":
            order = payload["order"]
            order["created_event_id"] = order_events[order["order_id"]]
            order["updated_event_id"] = order_updates[order["order_id"]]
            causes.append(order["created_event_id"])
        elif event_type == "valuation":
            if current_slice_event_id is not None:
                causes.append(current_slice_event_id)
            current_slice_event_id = None
        elif event_type == "run_completed":
            payload.setdefault("execution_model", "completed_bar_v1")
            if previous_event_id is not None:
                causes.append(previous_event_id)
        elif current_slice_event_id is not None:
            causes.append(current_slice_event_id)
        record["causation_ids"] = sorted(set(causes))
        previous_event_id = event_id


def slice_payload(sequence: int) -> dict[str, Any]:
    return json.loads(scenario_document())["slices"][sequence - 1]


def quantity_records(scenario_hash: str) -> list[dict[str, Any]]:
    """Return a complete replay with one quantity target and fill."""
    first_time = "2026-01-02T14:35:03.000000Z"
    second_time = "2026-01-02T14:45:00.000000Z"
    order = {
        "order_id": "journal-demo-order-000000000001",
        "instrument_id": "asset-a",
        "side": "buy",
        "quantity": "6",
        "order_kind": "market",
        "limit_price": None,
        "origin": "target_rebalance",
        "created_at": first_time,
        "created_sequence": "4",
        "eligible_after_slice_sequence": "1",
        "filled_quantity": "0",
        "filled_notional": "0",
        "status": "working",
        "rejection_reason": None,
    }
    first_valuation = valuation_payload(
        mark="100",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    final_valuation = valuation_payload(
        mark="102",
        quantity="6",
        cash="9393.144",
        market_value="612",
        cost_basis="606.856",
        realized_pnl="0",
        unrealized_pnl="5.144",
        equity="10005.144",
        total_fees="0.856",
    )
    return [
        envelope(
            1,
            "run_started",
            {
                "scenario_sha256": scenario_hash,
                "execution_model": "completed_bar_v1",
            },
            recorded_at="1970-01-01T00:00:00.000000Z",
        ),
        envelope(2, "market_slice_received", slice_payload(1), recorded_at=first_time),
        envelope(
            3,
            "target_portfolio_requested",
            {
                "basis": "quantities",
                "targets": [
                    {
                        "instrument_id": "asset-a",
                        "weight": None,
                        "quantity": "6",
                        "reference_price": None,
                    }
                ],
            },
            recorded_at=first_time,
        ),
        envelope(4, "order_accepted", order, recorded_at=first_time),
        envelope(5, "valuation", first_valuation, recorded_at=first_time),
        envelope(6, "market_slice_received", slice_payload(2), recorded_at=second_time),
        envelope(
            7,
            "fill_applied",
            {
                "fill_id": "journal-demo-fill-000000000001",
                "order_id": order["order_id"],
                "instrument_id": "asset-a",
                "quote_currency": "USD",
                "side": "buy",
                "quantity": "6",
                "price": "101",
                "notional": "606",
                "fee": "0.856",
                "executed_at": "2026-01-02T14:40:00.000000Z",
                "slice_sequence": "2",
            },
            recorded_at=second_time,
        ),
        envelope(8, "valuation", final_valuation, recorded_at=second_time),
        envelope(
            9,
            "run_completed",
            {
                "scenario_sha256": scenario_hash,
                "execution_model": "completed_bar_v1",
                "valuation": final_valuation,
                "order_counts": {
                    "total": 1,
                    "active": 0,
                    "filled": 1,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
            recorded_at=second_time,
        ),
    ]


def weight_records(scenario_hash: str) -> list[dict[str, Any]]:
    records = quantity_records(scenario_hash)
    records[2]["payload"] = {
        "basis": "weights",
        "targets": [
            {
                "instrument_id": "asset-a",
                "weight": "0.5",
                "quantity": "50",
                "reference_price": "100",
            }
        ],
    }
    order = records[3]["payload"]
    order["quantity"] = "50"
    records[6]["payload"]["quantity"] = "50"
    records[6]["payload"]["notional"] = "5050"
    records[6]["payload"]["fee"] = "5.3"
    final = valuation_payload(
        mark="102",
        quantity="50",
        cash="4944.7",
        market_value="5100",
        cost_basis="5055.3",
        realized_pnl="0",
        unrealized_pnl="44.7",
        equity="10044.7",
        total_fees="5.3",
    )
    records[7]["payload"] = final
    records[8]["payload"]["valuation"] = final
    return records


def scheduled_intent_scenario(tmp_path: Path):
    """Write a scenario exercising every direct scripted-intent outcome."""
    payload = json.loads(scenario_document())
    payload["risk"]["max_long_position"] = "5"
    payload["schedule"][0]["intents"] = [
        {
            "type": "submit_order",
            "instrument_id": "asset-a",
            "side": "buy",
            "quantity": "2",
            "order_kind": "market",
            "limit_price": None,
        },
        {
            "type": "submit_order",
            "instrument_id": "asset-a",
            "side": "buy",
            "quantity": "4",
            "order_kind": "market",
            "limit_price": None,
        },
        {"type": "cancel_order", "order_id": "journal-demo-order-000000000001"},
        {"type": "cancel_order", "order_id": "journal-demo-order-000000000001"},
        {"type": "cancel_order", "order_id": "missing-order"},
        {"type": "emit_metric", "name": "\vsignal\N{NO-BREAK SPACE}", "value": "0.5"},
        {"type": "emit_metric", "name": " padded", "value": "rejected"},
    ]
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "scheduled-intents.json")
    return scenario_path, hashlib.sha256(scenario_path.read_bytes()).hexdigest()


def scheduled_intent_records(scenario_hash: str) -> list[dict[str, Any]]:
    """Return exact happy-path outcomes for ``scheduled_intent_scenario``."""
    first_time = "2026-01-02T14:35:03.000000Z"
    second_time = "2026-01-02T14:45:00.000000Z"
    accepted = {
        "order_id": "journal-demo-order-000000000001",
        "instrument_id": "asset-a",
        "side": "buy",
        "quantity": "2",
        "order_kind": "market",
        "limit_price": None,
        "origin": "direct",
        "created_at": first_time,
        "created_sequence": "3",
        "eligible_after_slice_sequence": "1",
        "filled_quantity": "0",
        "filled_notional": "0",
        "status": "working",
        "rejection_reason": None,
    }
    rejected = {
        **accepted,
        "order_id": "journal-demo-order-000000000002",
        "quantity": "4",
        "created_sequence": "4",
        "status": "rejected",
        "rejection_reason": "position would exceed the maximum long position",
    }
    cancelled = {**accepted, "status": "cancelled"}
    first_valuation = valuation_payload(
        mark="100",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    final_valuation = valuation_payload(
        mark="102",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    return [
        envelope(
            1,
            "run_started",
            {"scenario_sha256": scenario_hash},
            recorded_at="1970-01-01T00:00:00.000000Z",
        ),
        envelope(2, "market_slice_received", slice_payload(1), recorded_at=first_time),
        envelope(3, "order_accepted", accepted, recorded_at=first_time),
        envelope(4, "order_rejected", rejected, recorded_at=first_time),
        envelope(
            5,
            "order_cancelled",
            {"order": cancelled, "reason": "strategy_requested"},
            recorded_at=first_time,
        ),
        envelope(
            6,
            "intent_rejected",
            {"reason": "cannot cancel a terminal order"},
            recorded_at=first_time,
        ),
        envelope(
            7,
            "intent_rejected",
            {"reason": "cannot cancel an unknown order"},
            recorded_at=first_time,
        ),
        envelope(
            8,
            "metric_emitted",
            {"name": "\vsignal\N{NO-BREAK SPACE}", "value": "0.5"},
            recorded_at=first_time,
        ),
        envelope(
            9,
            "intent_rejected",
            {"reason": "metric name must be a nonempty trimmed string"},
            recorded_at=first_time,
        ),
        envelope(10, "valuation", first_valuation, recorded_at=first_time),
        envelope(11, "market_slice_received", slice_payload(2), recorded_at=second_time),
        envelope(12, "valuation", final_valuation, recorded_at=second_time),
        envelope(
            13,
            "run_completed",
            {
                "scenario_sha256": scenario_hash,
                "valuation": final_valuation,
                "order_counts": {
                    "total": 2,
                    "active": 0,
                    "filled": 0,
                    "rejected": 1,
                    "cancelled": 1,
                },
            },
            recorded_at=second_time,
        ),
    ]


def write_journal(
    path: Path,
    records: list[dict[str, Any]],
    *,
    normalize: bool = True,
) -> Path:
    if normalize:
        normalize_audit_graph(records)
    path.write_text("".join(f"{json.dumps(item, separators=(',', ':'))}\n" for item in records))
    return path


def test_scenario_journal_binds_every_scheduled_intent_outcome(tmp_path: Path) -> None:
    scenario_path, digest = scheduled_intent_scenario(tmp_path)
    result = read_journal(
        write_journal(tmp_path / "scheduled-intents.jsonl", scheduled_intent_records(digest)),
        scenario=scenario_path,
    )

    assert result.orders["event_type"].tolist() == ["order_accepted", "order_rejected"]
    assert result.cancellations["reason"].tolist() == ["strategy_requested"]
    assert result.metrics[["name", "value"]].values.tolist() == [
        ["\vsignal\N{NO-BREAK SPACE}", "0.5"]
    ]
    assert result.rejections["reason"].tolist() == [
        "position would exceed the maximum long position",
        "cannot cancel a terminal order",
        "cannot cancel an unknown order",
        "metric name must be a nonempty trimmed string",
    ]


def test_scenario_journal_rejects_missing_replaced_and_mutated_intent_outcomes(
    tmp_path: Path,
) -> None:
    scenario_path, digest = scheduled_intent_scenario(tmp_path)
    records = scheduled_intent_records(digest)

    omitted = deepcopy(records)
    del omitted[7]
    for sequence, record in enumerate(omitted, start=1):
        record["engine_sequence"] = str(sequence)
    with pytest.raises(ValueError, match="scheduled intent outcome counts"):
        read_journal(
            write_journal(tmp_path / "omitted.jsonl", omitted),
            scenario=scenario_path,
        )

    replaced = deepcopy(records)
    replaced[7]["event_type"] = "intent_rejected"
    replaced[7]["payload"] = {"reason": "metric name must be a nonempty trimmed string"}
    with pytest.raises(ValueError, match="valid emit_metric"):
        read_journal(
            write_journal(tmp_path / "replaced.jsonl", replaced),
            scenario=scenario_path,
        )

    mutated = deepcopy(records)
    mutated[2]["payload"]["quantity"] = "3"
    mutated[4]["payload"]["order"]["quantity"] = "3"
    with pytest.raises(ValueError, match="submit_order request differs"):
        read_journal(
            write_journal(tmp_path / "mutated.jsonl", mutated),
            scenario=scenario_path,
        )

    wrong_rejection = deepcopy(records)
    wrong_rejection[5]["payload"]["reason"] = "cannot cancel an unknown order"
    with pytest.raises(ValueError, match="cancel_order rejection reason"):
        read_journal(
            write_journal(tmp_path / "wrong-rejection.jsonl", wrong_rejection),
            scenario=scenario_path,
        )

    wrong_id = deepcopy(records)
    wrong_id[2]["payload"]["order_id"] = "forged-order"
    wrong_id[4]["payload"]["order"]["order_id"] = "forged-order"
    with pytest.raises(ValueError, match="invalid cancel_order"):
        read_journal(
            write_journal(tmp_path / "wrong-id.jsonl", wrong_id),
            scenario=scenario_path,
        )

    _target_scenario, target_digest = write_scenario_fixture(tmp_path / "target-scenario.json")
    wrong_generated_id = quantity_records(target_digest)
    wrong_generated_id[3]["payload"]["order_id"] = "forged-order"
    wrong_generated_id[6]["payload"]["order_id"] = "forged-order"
    with pytest.raises(ValueError, match="deterministic engine sequence"):
        read_journal(
            write_journal(tmp_path / "wrong-generated-id.jsonl", wrong_generated_id),
            scenario=tmp_path / "target-scenario.json",
        )


def test_scenario_journal_rejects_forged_runtime_rejection_for_valid_submission(
    tmp_path: Path,
) -> None:
    payload = json.loads(scenario_document())
    payload["risk"]["max_long_position"] = "5"
    payload["schedule"][0]["intents"] = [
        {
            "type": "submit_order",
            "instrument_id": "asset-a",
            "side": "buy",
            "quantity": "2",
            "order_kind": "market",
            "limit_price": None,
        }
    ]
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "valid-submission.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    source = scheduled_intent_records(digest)
    forged_order = deepcopy(source[2])
    forged_order["event_type"] = "order_rejected"
    forged_order["payload"]["status"] = "rejected"
    forged_order["payload"]["rejection_reason"] = "position would exceed the maximum long position"
    completion = deepcopy(source[-1])
    completion["payload"]["order_counts"] = {
        "total": 1,
        "active": 0,
        "filled": 0,
        "rejected": 1,
        "cancelled": 0,
    }
    records = [source[0], source[1], forged_order, source[9], source[10], source[11], completion]
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)

    with pytest.raises(ValueError, match="order rejection differs from runtime risk"):
        read_journal(
            write_journal(tmp_path / "forged-rejection.jsonl", records),
            scenario=scenario_path,
        )


def test_target_supersession_requires_contiguous_ordered_cancellations() -> None:
    validate = vars(import_module("persistra.integrations.trading_engine.journal"))[
        "_validate_target_replacement_cancellations"
    ]
    orders = [
        {
            "engine_sequence": 3,
            "event_type": "order_accepted",
            "order_id": "journal-demo-order-000000000001",
            "quantity_micros": 2_000_000,
            "filled_quantity_micros": 0,
            "origin": "target_rebalance",
            "created_sequence": 3,
        },
        {
            "engine_sequence": 4,
            "event_type": "order_accepted",
            "order_id": "journal-demo-order-000000000002",
            "quantity_micros": 3_000_000,
            "filled_quantity_micros": 0,
            "origin": "target_rebalance",
            "created_sequence": 4,
        },
    ]
    outcome = {
        "event_type": "target_portfolio_requested",
        "engine_sequence": 10,
    }
    cancellations = [
        {
            "engine_sequence": 11,
            "order_id": "journal-demo-order-000000000001",
            "reason": "target_replaced",
        },
        {
            "engine_sequence": 12,
            "order_id": "journal-demo-order-000000000002",
            "reason": "target_replaced",
        },
    ]
    validate(
        [outcome],
        orders=orders,
        adjustments=[],
        fills=[],
        cancellations=cancellations,
    )

    reversed_ids = deepcopy(cancellations)
    reversed_ids[0]["order_id"], reversed_ids[1]["order_id"] = (
        reversed_ids[1]["order_id"],
        reversed_ids[0]["order_id"],
    )
    for invalid in (cancellations[:1], reversed_ids):
        with pytest.raises(ValueError, match="replace every active target order in order"):
            validate(
                [outcome],
                orders=orders,
                adjustments=[],
                fills=[],
                cancellations=invalid,
            )


def test_read_journal_normalizes_slices_targets_and_exact_values(tmp_path: Path) -> None:
    _scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
    path = write_journal(tmp_path / "journal.jsonl", quantity_records(digest))
    result = read_journal(path, scenario=tmp_path / "scenario.json")

    assert result.run_id == "journal-demo"
    assert result.contract_version == "3"
    assert result.scenario_sha256 == digest
    assert result.initial_equity_micros == 10_000_000_000
    assert result.bars["slice_sequence"].tolist() == [1, 2]
    assert result.targets.loc[0, "decision_slice_sequence"] == 1
    assert result.targets.loc[0, "basis"] == "quantities"
    assert result.fills.loc[0, "slice_sequence"] == 2
    assert result.fills.loc[0, "fee_micros"] == 856_000
    assert result.valuations["slice_sequence"].tolist() == [1, 2]
    assert result.margin_limits.empty
    assert result.completion.scenario_sha256 == digest
    assert result.execution_model == "completed_bar_v1"
    assert result.completion.execution_model == "completed_bar_v1"
    assert result.events[0].event_type == "run_started"
    assert result.events[0].event_id == "journal-demo-event-000000000001"
    assert result.events[0].causation_ids == ()
    assert result.events[6].causation_ids == (
        "journal-demo-event-000000000004",
        "journal-demo-event-000000000006",
    )
    assert {event.contract_version for event in result.events} == {"3"}
    assert result.positions[["slice_sequence", "instrument_id", "quantity"]].values.tolist() == [
        [1, "asset-a", 0],
        [2, "asset-a", 6],
    ]
    assert result.positions.loc[1, "mark_micros"] == 102_000_000
    assert result.positions.loc[1, "cost_basis_micros"] == 606_856_000


def test_scenario_inputs_select_explicit_artifact_digest_semantics(tmp_path: Path) -> None:
    scenario = scenario_from_json(scenario_document())
    batch_path = write_scenario(scenario, tmp_path / "scenario.json")
    stream_path = write_scenario_stream(scenario, tmp_path / "scenario.jsonl")
    batch_digest = hashlib.sha256(batch_path.read_bytes()).hexdigest()
    stream_digest = hashlib.sha256(stream_path.read_bytes()).hexdigest()

    batch = read_journal(
        write_journal(tmp_path / "batch-journal.jsonl", quantity_records(batch_digest)),
        scenario=batch_path,
        scenario_sha256=batch_digest,
    )
    stream = read_journal(
        write_journal(tmp_path / "stream-journal.jsonl", quantity_records(stream_digest)),
        scenario=stream_path,
        scenario_sha256=stream_digest,
    )
    model = read_journal(
        write_journal(tmp_path / "model-journal.jsonl", quantity_records(stream_digest)),
        scenario=scenario,
        scenario_sha256=stream_digest,
    )

    assert batch_digest != stream_digest
    assert batch.scenario_sha256 == batch_digest
    assert stream.scenario_sha256 == model.scenario_sha256 == stream_digest
    with pytest.raises(ValueError, match="provided scenario_sha256 differs"):
        read_journal(
            tmp_path / "model-journal.jsonl",
            scenario=scenario,
            scenario_sha256=batch_digest,
        )


def test_non_target_intent_rejection_does_not_shift_target_and_metric_import(
    tmp_path: Path,
) -> None:
    payload = json.loads(scenario_document())
    payload["schedule"][0]["intents"].insert(
        0, {"type": "cancel_order", "order_id": "missing-order"}
    )
    payload["schedule"][0]["intents"].append(
        {"type": "emit_metric", "name": "daily signal", "value": "0.5"}
    )
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    records = quantity_records(digest)
    first_time = "2026-01-02T14:35:03.000000Z"
    records.insert(
        2,
        envelope(
            3,
            "intent_rejected",
            {"reason": "cannot cancel an unknown order"},
            recorded_at=first_time,
        ),
    )
    records.insert(
        4,
        envelope(
            5,
            "metric_emitted",
            {"name": "daily signal", "value": "0.5"},
            recorded_at=first_time,
        ),
    )
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    records[5]["payload"]["created_sequence"] = "6"

    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records), scenario=scenario_path
    )
    assert result.targets["decision_slice_sequence"].tolist() == [1]
    assert result.rejections["reason"].tolist() == ["cannot cancel an unknown order"]
    assert result.metrics["name"].tolist() == ["daily signal"]


def test_scenario_reconciliation_compares_slice_bars_by_instrument(tmp_path: Path) -> None:
    payload = json.loads(scenario_document())
    payload["schedule"] = []
    payload["instruments"].append(
        {
            "instrument_id": "asset-b",
            "symbol": "BBB",
            "quote_currency": "USD",
            "tick_size": "0.01",
            "lot_size": "1",
        }
    )
    for market_slice in payload["slices"]:
        first = market_slice["bars"][0]
        market_slice["bars"].insert(
            0,
            {
                "instrument_id": "asset-b",
                "open": str(Decimal(first["open"]) * 2),
                "high": str(Decimal(first["high"]) * 2),
                "low": str(Decimal(first["low"]) * 2),
                "close": str(Decimal(first["close"]) * 2),
                "volume": first["volume"],
            },
        )
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    final_valuation: dict[str, Any] | None = None
    records: list[dict[str, Any]] = [
        envelope(
            1,
            "run_started",
            {"scenario_sha256": digest},
            recorded_at="1970-01-01T00:00:00.000000Z",
        )
    ]
    for market_slice in payload["slices"]:
        received_at = market_slice["received_at"]
        emitted = deepcopy(market_slice)
        emitted["bars"] = sorted(emitted["bars"], key=lambda item: item["instrument_id"])
        asset_a = next(bar for bar in emitted["bars"] if bar["instrument_id"] == "asset-a")
        asset_b = next(bar for bar in emitted["bars"] if bar["instrument_id"] == "asset-b")
        valuation = valuation_payload(
            mark=asset_a["close"],
            quantity="0",
            cash="10000",
            market_value="0",
            cost_basis="0",
            realized_pnl="0",
            unrealized_pnl="0",
            equity="10000",
            total_fees="0",
        )
        asset_b_position = deepcopy(valuation["positions"][0])
        asset_b_position.update({"instrument_id": "asset-b", "mark": asset_b["close"]})
        valuation["positions"].append(asset_b_position)
        final_valuation = valuation
        records.append(
            envelope(len(records) + 1, "market_slice_received", emitted, recorded_at=received_at)
        )
        records.append(envelope(len(records) + 1, "valuation", valuation, recorded_at=received_at))
    records.append(
        envelope(
            len(records) + 1,
            "run_completed",
            {
                "scenario_sha256": digest,
                "valuation": final_valuation,
                "order_counts": {
                    "total": 0,
                    "active": 0,
                    "filled": 0,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
            recorded_at=payload["slices"][-1]["received_at"],
        )
    )
    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records), scenario=scenario_path
    )
    assert result.bars.groupby("slice_sequence").size().tolist() == [2, 2]


def test_read_journal_reconciles_engine_owned_weight_sizing(tmp_path: Path) -> None:
    _scenario, digest = write_scenario_fixture(tmp_path / "scenario.json", basis="weights")
    records = weight_records(digest)
    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records),
        scenario=tmp_path / "scenario.json",
    )
    assert result.targets.loc[0, "weight"] == 0.5
    assert result.targets.loc[0, "quantity"] == 50

    records[2]["payload"]["targets"][0]["quantity"] = "49"
    with pytest.raises(ValueError, match="engine sizing"):
        read_journal(
            write_journal(tmp_path / "bad.jsonl", records),
            scenario=tmp_path / "scenario.json",
        )


def test_read_journal_accepts_predicted_weight_target_rejection_without_shifting(
    tmp_path: Path,
) -> None:
    payload = json.loads(scenario_document(basis="weights"))
    payload["risk"]["max_long_position"] = "10"
    payload["schedule"].append(
        {
            "after_slice_sequence": "2",
            "intents": [
                {
                    "type": "target_weights",
                    "targets": [{"instrument_id": "asset-a", "weight": "0"}],
                }
            ],
        }
    )
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    initial = valuation_payload(
        mark="100",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    final = valuation_payload(
        mark="102",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    first_time = "2026-01-02T14:35:03.000000Z"
    second_time = "2026-01-02T14:45:00.000000Z"
    records = [
        envelope(
            1,
            "run_started",
            {"scenario_sha256": digest},
            recorded_at="1970-01-01T00:00:00.000000Z",
        ),
        envelope(2, "market_slice_received", slice_payload(1), recorded_at=first_time),
        envelope(
            3,
            "intent_rejected",
            {"reason": "position would exceed the maximum long position"},
            recorded_at=first_time,
        ),
        envelope(4, "valuation", initial, recorded_at=first_time),
        envelope(5, "market_slice_received", slice_payload(2), recorded_at=second_time),
        envelope(
            6,
            "target_portfolio_requested",
            {
                "basis": "weights",
                "targets": [
                    {
                        "instrument_id": "asset-a",
                        "weight": "0",
                        "quantity": "0",
                        "reference_price": "102",
                    }
                ],
            },
            recorded_at=second_time,
        ),
        envelope(7, "valuation", final, recorded_at=second_time),
        envelope(
            8,
            "run_completed",
            {
                "scenario_sha256": digest,
                "valuation": final,
                "order_counts": {
                    "total": 0,
                    "active": 0,
                    "filled": 0,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
            recorded_at=second_time,
        ),
    ]
    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records), scenario=scenario_path
    )
    assert result.targets["decision_slice_sequence"].tolist() == [2]
    assert result.rejections["event_type"].tolist() == ["intent_rejected"]

    false_success = deepcopy(records)
    false_success[2]["event_type"] = "target_portfolio_requested"
    false_success[2]["payload"] = {
        "basis": "weights",
        "targets": [
            {
                "instrument_id": "asset-a",
                "weight": "0.5",
                "quantity": "50",
                "reference_price": "100",
            }
        ],
    }
    with pytest.raises(ValueError, match="target outcome differs"):
        read_journal(
            write_journal(tmp_path / "false-success.jsonl", false_success),
            scenario=scenario_path,
        )


def test_read_journal_validates_margin_limited_claims(tmp_path: Path) -> None:
    scenario_payload = json.loads(scenario_document(initial_cash="1000"))
    scenario_payload["schedule"][0]["intents"][0]["targets"][0]["quantity"] = "20"
    scenario = scenario_from_json(json.dumps(scenario_payload))
    scenario_path = write_scenario(scenario, tmp_path / "scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    records = quantity_records(digest)
    records[2]["payload"]["targets"][0]["quantity"] = "20"
    records[3]["payload"]["quantity"] = "20"
    records[4]["payload"] = valuation_payload(
        mark="100",
        quantity="0",
        cash="1000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="1000",
        total_fees="0",
    )
    records.insert(
        6,
        envelope(
            7,
            "margin_limited",
            {
                "order_id": "journal-demo-order-000000000001",
                "instrument_id": "asset-a",
                "requested_quantity": "20",
                "permitted_quantity": "19",
                "price": "101",
            },
            recorded_at="2026-01-02T14:45:00.000000Z",
        ),
    )
    fill = records[7]["payload"]
    fill.update({"quantity": "19", "notional": "1919", "fee": "2.169"})
    final = valuation_payload(
        mark="102",
        quantity="19",
        cash="-921.169",
        market_value="1938",
        cost_basis="1921.169",
        realized_pnl="0",
        unrealized_pnl="16.831",
        equity="1016.831",
        total_fees="2.169",
    )
    records[8]["payload"] = final
    records[9]["payload"]["valuation"] = final
    records[9]["payload"]["order_counts"].update({"active": 1, "filled": 0})
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records), scenario=scenario_path
    )
    assert result.margin_limits.loc[0, "permitted_quantity"] == 19

    invalid = deepcopy(records)
    invalid[6]["payload"]["permitted_quantity"] = "18"
    with pytest.raises(ValueError, match="risk policy"):
        read_journal(write_journal(tmp_path / "bad.jsonl", invalid), scenario=scenario_path)

    duplicate = deepcopy(records)
    duplicate.insert(7, deepcopy(duplicate[6]))
    for sequence, record in enumerate(duplicate, start=1):
        record["engine_sequence"] = str(sequence)
    with pytest.raises(ValueError, match="at most once per order and slice"):
        read_journal(
            write_journal(tmp_path / "duplicate.jsonl", duplicate),
            scenario=scenario_path,
        )

    wrong_price = deepcopy(records)
    wrong_price[6]["payload"]["price"] = "102"
    with pytest.raises(ValueError, match="audited price"):
        read_journal(
            write_journal(tmp_path / "wrong-price.jsonl", wrong_price),
            scenario=scenario_path,
        )
    over_remaining = deepcopy(records)
    over_remaining[6]["payload"]["requested_quantity"] = "21"
    with pytest.raises(ValueError, match="remaining order"):
        read_journal(
            write_journal(tmp_path / "over-remaining.jsonl", over_remaining),
            scenario=scenario_path,
        )
    out_of_order = deepcopy(records)
    out_of_order[6], out_of_order[7] = out_of_order[7], out_of_order[6]
    for sequence, record in enumerate(out_of_order, start=1):
        record["engine_sequence"] = str(sequence)
    with pytest.raises(ValueError, match="remaining order"):
        read_journal(
            write_journal(tmp_path / "out-of-order.jsonl", out_of_order),
            scenario=scenario_path,
        )
    wrong_side = deepcopy(records)
    wrong_side[7]["payload"]["side"] = "sell"
    with pytest.raises(ValueError, match="fill instrument and side"):
        read_journal(
            write_journal(tmp_path / "wrong-side.jsonl", wrong_side),
            scenario=scenario_path,
        )


def partial_cancellation_records(scenario_hash: str) -> list[dict[str, Any]]:
    """Return a capacity-limited market fill followed by its IOC cancellation."""
    records = quantity_records(scenario_hash)
    accepted = records[3]["payload"]
    fill = records[6]["payload"]
    fill.update({"quantity": "4", "notional": "404", "fee": "0.654"})
    cancelled = deepcopy(accepted)
    cancelled.update(
        {
            "filled_quantity": "4",
            "filled_notional": "404",
            "status": "cancelled",
        }
    )
    records.insert(
        7,
        envelope(
            8,
            "order_cancelled",
            {"order": cancelled, "reason": "market_ioc"},
            recorded_at="2026-01-02T14:45:00.000000Z",
        ),
    )
    final = valuation_payload(
        mark="102",
        quantity="4",
        cash="9595.346",
        market_value="408",
        cost_basis="404.654",
        realized_pnl="0",
        unrealized_pnl="3.346",
        equity="10003.346",
        total_fees="0.654",
    )
    records[8]["payload"] = final
    records[9]["payload"]["valuation"] = final
    records[9]["payload"]["order_counts"] = {
        "total": 1,
        "active": 0,
        "filled": 0,
        "rejected": 0,
        "cancelled": 1,
    }
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    return records


def test_read_journal_reconciles_cancelled_order_snapshot(tmp_path: Path) -> None:
    payload = json.loads(scenario_document())
    payload["execution"]["participation_bps"] = 400
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    records = partial_cancellation_records(digest)

    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records), scenario=scenario_path
    )
    assert result.cancellations.loc[0, "filled_quantity"] == 4
    assert result.cancellations.loc[0, "reason"] == "market_ioc"

    unattached_replacement = deepcopy(records)
    unattached_replacement[7]["payload"]["reason"] = "target_replaced"
    with pytest.raises(ValueError, match="does not follow a portfolio target"):
        read_journal(
            write_journal(tmp_path / "unattached-replacement.jsonl", unattached_replacement),
            scenario=scenario_path,
        )

    bad_fill_state = deepcopy(records)
    bad_fill_state[7]["payload"]["order"]["filled_quantity"] = "3"
    with pytest.raises(ValueError, match="state differs from its latest state"):
        read_journal(
            write_journal(tmp_path / "bad-fill-state.jsonl", bad_fill_state),
            scenario=scenario_path,
        )
    bad_request_state = deepcopy(records)
    bad_request_state[7]["payload"]["order"]["quantity"] = "5"
    with pytest.raises(ValueError, match="state differs from its latest state"):
        read_journal(
            write_journal(tmp_path / "bad-request-state.jsonl", bad_request_state),
            scenario=scenario_path,
        )


@pytest.mark.parametrize(
    "field",
    [
        "cash",
        "net_market_value",
        "cost_basis",
        "realized_pnl",
        "unrealized_pnl",
        "equity",
        "total_fees",
    ],
)
def test_read_journal_reconciles_every_valuation_field(tmp_path: Path, field: str) -> None:
    _scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
    records = quantity_records(digest)
    changed = str(Decimal(records[7]["payload"][field]) + Decimal("0.001"))
    records[7]["payload"][field] = changed
    records[8]["payload"]["valuation"][field] = changed
    with pytest.raises(ValueError, match=r"valuation .*reconcile"):
        read_journal(
            write_journal(tmp_path / "tampered.jsonl", records),
            scenario=tmp_path / "scenario.json",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("first_event", "run_started must be"),
        ("start_hash", "scenario_sha256 differs"),
        ("completion_hash", "must match run_started"),
        ("fee", "fee differs"),
        ("notional", "notional must equal"),
        ("price", "completed-slice model"),
        ("quantity_reference", "reference_price presence"),
    ],
)
def test_read_journal_rejects_tampered_audit_values(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    _scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
    records = quantity_records(digest)
    if mutation == "first_event":
        records[0]["event_type"] = "metric_emitted"
    elif mutation == "start_hash":
        records[0]["payload"]["scenario_sha256"] = "0" * 64
    elif mutation == "completion_hash":
        records[-1]["payload"]["scenario_sha256"] = "0" * 64
    elif mutation == "fee":
        records[6]["payload"]["fee"] = "0"
    elif mutation == "notional":
        records[6]["payload"]["notional"] = "605"
    elif mutation == "price":
        records[6]["payload"].update(
            {"price": "101.01", "notional": "606.06", "fee": "0.85606"}
        )
    else:
        records[2]["payload"]["targets"][0]["reference_price"] = "100"
    with pytest.raises(ValueError, match=message):
        read_journal(
            write_journal(tmp_path / "journal.jsonl", records),
            scenario=tmp_path / "scenario.json",
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("event_id", "event_id must derive"),
        ("duplicate", "must not contain duplicates"),
        ("unknown", "known prior events"),
        ("forward", "forward event"),
        ("cross_run", "another run"),
        ("noncanonical", "canonical event identifier order"),
        ("missing_order_cause", "must cite its order creation event"),
    ],
)
def test_read_journal_rejects_invalid_causal_graphs(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = quantity_records("0" * 64)
    normalize_audit_graph(records)
    if mutation == "event_id":
        records[2]["event_id"] = "forged-event"
    elif mutation == "duplicate":
        records[2]["causation_ids"] = [
            "journal-demo-event-000000000002",
            "journal-demo-event-000000000002",
        ]
    elif mutation == "unknown":
        records[2]["causation_ids"] = ["journal-demo-event-000000000000"]
    elif mutation == "forward":
        records[2]["causation_ids"] = ["journal-demo-event-000000000004"]
    elif mutation == "cross_run":
        records[2]["causation_ids"] = ["another-run-event-000000000001"]
    elif mutation == "noncanonical":
        records[6]["causation_ids"] = [
            "journal-demo-event-000000000006",
            "journal-demo-event-000000000004",
        ]
    else:
        records[6]["causation_ids"] = ["journal-demo-event-000000000006"]
    with pytest.raises(ValueError, match=message):
        read_journal(
            write_journal(tmp_path / f"{mutation}.jsonl", records, normalize=False)
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("sequence", "engine_sequence must be contiguous"),
        ("run_id", "run_id must remain constant"),
        ("clock", "recorded_at must not move backward"),
        ("repeated_start", "exactly one run_started"),
        ("caused_slice", "market_slice_received must not have causal predecessors"),
        ("slice_sequence", "slice_sequence must increase globally"),
        ("receipt", "slice receipt must equal"),
        ("open_completion", "run_completed must follow the current slice valuation"),
        ("outside_slice", "nonterminal journal events require an open market slice"),
        ("event_clock", "slice event must use the market slice receipt clock"),
    ],
)
def test_read_journal_rejects_invalid_event_structure(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = quantity_records("0" * 64)
    normalize_audit_graph(records)
    if mutation == "sequence":
        records[1]["engine_sequence"] = "3"
    elif mutation == "run_id":
        records[1]["run_id"] = "another-run"
        records[1]["event_id"] = "another-run-event-000000000002"
    elif mutation == "clock":
        records[0]["recorded_at"] = "2026-01-02T14:35:04.000000Z"
    elif mutation == "repeated_start":
        records[1]["event_type"] = "run_started"
    elif mutation == "caused_slice":
        records[1]["causation_ids"] = ["journal-demo-event-000000000001"]
    elif mutation == "slice_sequence":
        records[5]["payload"]["slice_sequence"] = "1"
    elif mutation == "receipt":
        records[1]["payload"]["received_at"] = "2026-01-02T14:35:04.000000Z"
    elif mutation == "open_completion":
        del records[7]
        for sequence, record in enumerate(records, start=1):
            record["engine_sequence"] = str(sequence)
        normalize_audit_graph(records)
    elif mutation == "outside_slice":
        records[1]["event_type"] = "metric_emitted"
        records[1]["payload"] = {"name": "metric", "value": "1"}
    else:
        records[2]["recorded_at"] = "2026-01-02T14:35:04.000000Z"
    with pytest.raises(ValueError, match=message):
        read_journal(
            write_journal(
                tmp_path / f"{mutation}.jsonl",
                records,
                normalize=False,
            )
        )


def test_read_journal_rejects_model_and_position_attribution_tampering(
    tmp_path: Path,
) -> None:
    records = quantity_records("0" * 64)
    records[0]["payload"]["execution_model"] = "future_model"
    with pytest.raises(ValueError, match="unsupported execution model"):
        read_journal(write_journal(tmp_path / "model.jsonl", records))

    records = quantity_records("0" * 64)
    records[7]["payload"]["positions"][0]["quantity"] = "5"
    with pytest.raises(ValueError, match="market_value must equal mark times quantity"):
        read_journal(write_journal(tmp_path / "position.jsonl", records))

    records = quantity_records("0" * 64)
    records[-1]["payload"]["valuation"] = deepcopy(
        records[-1]["payload"]["valuation"]
    )
    records[-1]["payload"]["valuation"]["positions"][0]["instrument_id"] = "asset-b"
    with pytest.raises(ValueError, match="run_completed positions differ"):
        read_journal(write_journal(tmp_path / "terminal-position.jsonl", records))

    records = quantity_records("0" * 64)
    normalize_audit_graph(records)
    records[3]["payload"]["created_event_id"] = "journal-demo-event-000000000003"
    with pytest.raises(ValueError, match="created_event_id must equal event_id"):
        read_journal(
            write_journal(tmp_path / "creation.jsonl", records, normalize=False)
        )


def test_read_journal_requires_one_valuation_per_slice_and_terminal_completion(
    tmp_path: Path,
) -> None:
    _scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
    records = quantity_records(digest)
    del records[4]
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    with pytest.raises(ValueError, match="must end with valuation"):
        read_journal(write_journal(tmp_path / "missing.jsonl", records))

    records = quantity_records(digest)
    records.append(deepcopy(records[-1]))
    records[-1]["engine_sequence"] = "10"
    with pytest.raises(ValueError, match="terminal journal record"):
        read_journal(write_journal(tmp_path / "trailing.jsonl", records))


def test_read_journal_rejects_blank_duplicate_and_noncanonical_records(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    with pytest.raises(ValueError, match="must not be empty"):
        read_journal(empty)
    blank = tmp_path / "blank.jsonl"
    blank.write_text("{}\n\n")
    with pytest.raises(ValueError, match="blank records"):
        read_journal(blank)
    duplicate = tmp_path / "duplicate.jsonl"
    duplicate.write_text('{"engine_sequence":"1","engine_sequence":"1"}\n')
    with pytest.raises(ValueError, match="duplicate JSON field"):
        read_journal(duplicate)

    records = quantity_records("0" * 64)
    del records[0]["contract_version"]
    with pytest.raises(ValueError, match="journal record 1 fields differ"):
        read_journal(write_journal(tmp_path / "unversioned.jsonl", records))

    records = quantity_records("0" * 64)
    records[1]["contract_version"] = "4"
    with pytest.raises(ValueError, match="unsupported journal contract_version"):
        read_journal(write_journal(tmp_path / "unsupported.jsonl", records))


@pytest.mark.parametrize(
    "timestamp",
    [
        "1970-01-01 00:00:00Z",
        "1970-01-01T00:00:00.0000001Z",
        "1970-01-01T00:00:00+0000",
        "1970-01-01T00:00:60Z",
    ],
)
def test_journal_parser_requires_exact_rfc3339_timestamps(tmp_path: Path, timestamp: str) -> None:
    records = quantity_records("0" * 64)
    records[0]["recorded_at"] = timestamp
    with pytest.raises(ValueError, match="RFC3339 syntax"):
        read_journal(write_journal(tmp_path / "journal.jsonl", records))


def test_journal_parser_accepts_lowercase_rfc3339_separators(tmp_path: Path) -> None:
    records = quantity_records("0" * 64)
    records[0]["recorded_at"] = "1970-01-01t00:00:00z"
    assert read_journal(write_journal(tmp_path / "journal.jsonl", records)).run_id == "journal-demo"


def test_standalone_journal_accepts_leveraged_targets_and_enforces_unsigned_values(
    tmp_path: Path,
) -> None:
    digest = "0" * 64
    records = weight_records(digest)
    records[2]["payload"]["targets"][0]["weight"] = "1.000001"
    result = read_journal(write_journal(tmp_path / "leveraged-weight.jsonl", records))
    assert result.targets.loc[0, "weight"] == pytest.approx(1.000001)

    for field in (
        "long_market_value",
        "short_market_value",
        "gross_exposure",
        "execution_fees",
        "borrow_fees",
        "total_fees",
    ):
        records = quantity_records(digest)
        records[4]["payload"][field] = "-0.000001"
        with pytest.raises(ValueError, match=f"{field} must be nonnegative"):
            read_journal(write_journal(tmp_path / f"negative-{field}.jsonl", records))


def test_scenario_backed_journal_enforces_order_and_position_risk(tmp_path: Path) -> None:
    payload = json.loads(scenario_document())
    payload["risk"]["max_order_quantity"] = "5"
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "max-order-scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="accepted order exceeds max_order_quantity"):
        read_journal(
            write_journal(tmp_path / "max-order.jsonl", quantity_records(digest)),
            scenario=scenario_path,
        )

    payload = json.loads(scenario_document())
    payload["risk"]["max_long_position"] = "5"
    payload["schedule"][0]["intents"][0]["targets"][0]["quantity"] = "4"
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "max-position-scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    records = quantity_records(digest)
    records[2]["payload"]["targets"][0]["quantity"] = "4"
    with pytest.raises(ValueError, match="maximum long position"):
        read_journal(
            write_journal(tmp_path / "max-position.jsonl", records),
            scenario=scenario_path,
        )


def test_read_journal_rejects_cancellation_after_a_full_fill(tmp_path: Path) -> None:
    scenario_path = tmp_path / "scenario.json"
    _scenario, digest = write_scenario_fixture(scenario_path)
    records = quantity_records(digest)
    cancelled = deepcopy(records[3]["payload"])
    cancelled.update(
        {
            "filled_quantity": "6",
            "filled_notional": "606",
            "status": "cancelled",
        }
    )
    records.insert(
        7,
        envelope(
            8,
            "order_cancelled",
            {"order": cancelled, "reason": "market_ioc"},
            recorded_at="2026-01-02T14:45:00.000000Z",
        ),
    )
    records[-1]["payload"]["order_counts"].update({"filled": 0, "cancelled": 1})
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    with pytest.raises(ValueError, match="only a working order may be cancelled"):
        read_journal(
            write_journal(tmp_path / "journal.jsonl", records),
            scenario=scenario_path,
        )


def test_fill_replay_uses_exact_proportional_sell_basis() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    position = vars(journal)["_PositionState"]()
    cash = {"USD": decimal_micros(Decimal("1000"))}
    positions = {"asset-a": position}

    def apply(*, side: str, quantity: str, notional: str, fee: str) -> None:
        vars(journal)["_apply_fill_state"](
            {
                "instrument_id": "asset-a",
                "quote_currency": "USD",
                "side": side,
                "quantity_micros": decimal_micros(Decimal(quantity)),
                "notional_micros": decimal_micros(Decimal(notional)),
                "fee_micros": decimal_micros(Decimal(fee)),
            },
            cash=cash,
            positions=positions,
        )

    apply(side="buy", quantity="3", notional="300", fee="0.55")
    assert position.cost_basis == decimal_micros(Decimal("300.55"))

    apply(side="sell", quantity="1", notional="120", fee="0.37")
    assert position.quantity == decimal_micros(Decimal("2"))
    assert position.cost_basis == decimal_micros(Decimal("200.366667"))
    assert position.realized_pnl == decimal_micros(Decimal("19.446667"))

    apply(side="sell", quantity="2", notional="180", fee="0.43")
    assert position.quantity == 0
    assert position.cost_basis == 0
    assert position.realized_pnl == decimal_micros(Decimal("-1.35"))
    assert position.execution_fees == decimal_micros(Decimal("1.35"))
    assert cash["USD"] == decimal_micros(Decimal("998.65"))


def test_slice_payload_rejects_malformed_fx_bars_and_actions() -> None:
    parse = vars(import_module("persistra.integrations.trading_engine.journal"))["_slice_rows"]
    base = slice_payload(1)
    split = {
        "type": "split",
        "action_id": "split-a",
        "instrument_id": "asset-a",
        "numerator": 2,
        "denominator": 1,
    }

    cases: list[tuple[dict[str, Any], str]] = []
    value = deepcopy(base)
    value["end_at"] = value["start_at"]
    cases.append((value, "slice timestamps"))
    value = deepcopy(base)
    value["bars"] = []
    cases.append((value, "at least one bar"))
    value = deepcopy(base)
    value["bars"].append(deepcopy(value["bars"][0]))
    cases.append((value, "unique instrument identifier order"))
    value = deepcopy(base)
    value["bars"][0]["low"] = "100.5"
    cases.append((value, "bar low"))
    value = deepcopy(base)
    value["bars"][0]["high"] = "99.5"
    cases.append((value, "bar high"))
    value = deepcopy(base)
    value["fx_rates"] = []
    cases.append((value, "contain FX rates"))
    value = deepcopy(base)
    value["fx_rates"].append(deepcopy(value["fx_rates"][0]))
    cases.append((value, "unique currency order"))
    value = deepcopy(base)
    value["corporate_actions"] = [None]
    cases.append((value, "corporate action must be"))
    value = deepcopy(base)
    value["corporate_actions"] = [{**split, "numerator": 1}]
    cases.append((value, "split ratio"))
    value = deepcopy(base)
    value["corporate_actions"] = [{**split, "type": "merger"}]
    cases.append((value, "unsupported corporate action"))
    value = deepcopy(base)
    value["corporate_actions"] = [split, deepcopy(split)]
    cases.append((value, "unique action identifier order"))

    for payload, message in cases:
        with pytest.raises(ValueError, match=message):
            parse(
                payload,
                engine_sequence=2,
                recorded_at=pd.Timestamp(base["received_at"]),
            )


def test_event_payload_parsers_reject_inconsistent_v3_claims() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    parse_target = vars(journal)["_target_rows"]
    parse_order = vars(journal)["_order_row"]
    parse_cancellation = vars(journal)["_cancellation_row"]
    parse_limit = vars(journal)["_margin_limit_row"]
    parse_borrow = vars(journal)["_borrow_fee_row"]
    now = pd.Timestamp("2026-01-02T14:35:03Z")

    target = quantity_records("0" * 64)[2]["payload"]
    target_cases: list[tuple[dict[str, Any], str]] = []
    value = deepcopy(target)
    value["targets"] = []
    target_cases.append((value, "must not be empty"))
    value = deepcopy(target)
    value["targets"].append(deepcopy(value["targets"][0]))
    target_cases.append((value, "instruments must be unique"))
    value = deepcopy(target)
    value["targets"][0]["weight"] = "0.5"
    target_cases.append((value, "weight presence"))
    value = deepcopy(target)
    value["targets"][0]["reference_price"] = "100"
    target_cases.append((value, "reference_price presence"))
    for payload, message in target_cases:
        with pytest.raises(ValueError, match=message):
            parse_target(
                payload,
                engine_sequence=3,
                recorded_at=now,
                decision_slice_sequence=1,
            )

    records = quantity_records("0" * 64)
    normalize_audit_graph(records)
    order = records[3]["payload"]
    order_cases: list[tuple[dict[str, Any], str]] = []
    value = deepcopy(order)
    value["order_kind"] = "limit"
    order_cases.append((value, "market orders require"))
    value = deepcopy(order)
    value["rejection_reason"] = ""
    order_cases.append((value, "rejection_reason"))
    value = deepcopy(order)
    value["status"] = "rejected"
    order_cases.append((value, "rejected status"))
    value = deepcopy(order)
    value["created_at"] = "2026-01-02T14:35:04Z"
    order_cases.append((value, "must not follow"))
    value = deepcopy(order)
    value["created_at"] = "2026-01-02T14:35:02Z"
    order_cases.append((value, "must equal audit"))
    value = deepcopy(order)
    value["filled_quantity"] = "7"
    order_cases.append((value, "must not exceed"))
    for payload, message in order_cases:
        with pytest.raises(ValueError, match=message):
            parse_order(
                payload,
                engine_sequence=4,
                recorded_at=now,
                event_type="order_accepted",
            )

    active = deepcopy(order)
    active["status"] = "working"
    with pytest.raises(ValueError, match="must contain cancelled status"):
        parse_cancellation(
            {"order": active, "reason": "market_ioc"},
            engine_sequence=8,
            recorded_at=now,
            slice_sequence=2,
        )

    with pytest.raises(ValueError, match="below requested_quantity"):
        parse_limit(
            {
                "order_id": "order-a",
                "instrument_id": "asset-a",
                "requested_quantity": "1",
                "permitted_quantity": "1",
                "price": "100",
            },
            engine_sequence=7,
            recorded_at=now,
            slice_sequence=2,
        )

    borrow = {
        "instrument_id": "asset-a",
        "quote_currency": "USD",
        "short_quantity": "1",
        "reference_price": "100",
        "borrow_bps": 1,
        "period_start": "2026-01-02T14:30:00Z",
        "period_end": "2026-01-02T14:35:00Z",
        "fee": "0.000001",
    }
    value = {**borrow, "borrow_bps": 10_001}
    with pytest.raises(ValueError, match="must not exceed 10000"):
        parse_borrow(value, engine_sequence=7, recorded_at=now, slice_sequence=2)
    value = {**borrow, "period_end": borrow["period_start"]}
    with pytest.raises(ValueError, match="period must be positive"):
        parse_borrow(value, engine_sequence=7, recorded_at=now, slice_sequence=2)

    with pytest.raises(ValueError, match="metric value must be a string"):
        vars(journal)["_metric_row"](
            {"name": "signal", "value": 1},
            engine_sequence=1,
            recorded_at=now,
        )
    with pytest.raises(ValueError, match="rejection reason"):
        vars(journal)["_intent_rejection_row"]({"reason": ""}, engine_sequence=1, recorded_at=now)


def test_valuation_payload_rejects_inconsistent_v3_attribution() -> None:
    parse = vars(import_module("persistra.integrations.trading_engine.journal"))[
        "_valuation_rows"
    ]
    now = pd.Timestamp("2026-01-02T14:45:00Z")
    base = valuation_payload(
        mark="102",
        quantity="6",
        cash="9393.144",
        market_value="612",
        cost_basis="606.856",
        realized_pnl="0",
        unrealized_pnl="5.144",
        equity="10005.144",
        total_fees="0.856",
    )
    cases: list[tuple[dict[str, Any], str]] = []
    value = deepcopy(base)
    value["cash_balances"] = []
    cases.append((value, "cash_balances must not be empty"))
    value = deepcopy(base)
    value["cash_balances"].append(deepcopy(value["cash_balances"][0]))
    cases.append((value, "unique currency order"))
    value = deepcopy(base)
    value["positions"].append(deepcopy(value["positions"][0]))
    cases.append((value, "unique instrument identifier order"))
    value = deepcopy(base)
    value["margin"]["margin_call"] = 1
    cases.append((value, "JSON boolean"))
    value = deepcopy(base)
    value["cash_balances"][0]["base_value"] = "1"
    cases.append((value, "cash base_value"))
    value = deepcopy(base)
    value["positions"][0]["unrealized_pnl"] = "5"
    value["positions"][0]["base_unrealized_pnl"] = "5"
    cases.append((value, "unrealized P&L"))
    value = deepcopy(base)
    value["positions"][0]["total_fees"] = "0"
    value["positions"][0]["base_total_fees"] = "0"
    cases.append((value, "total fees must equal"))
    value = deepcopy(base)
    value["positions"][0]["base_cost_basis"] = "1"
    cases.append((value, "base_cost_basis"))
    value = deepcopy(base)
    value["net_market_value"] = "611"
    cases.append((value, "account aggregates"))
    value = deepcopy(base)
    value["long_market_value"] = "611"
    cases.append((value, "long market value"))
    value = deepcopy(base)
    value["short_market_value"] = "1"
    cases.append((value, "short market value"))
    value = deepcopy(base)
    value["gross_exposure"] = "611"
    cases.append((value, "gross exposure"))
    value = deepcopy(base)
    value["equity"] = "10005"
    cases.append((value, "equity does not reconcile"))
    value = deepcopy(base)
    value["margin"]["initial_excess"] = "1"
    cases.append((value, "initial margin excess"))
    value = deepcopy(base)
    value["margin"]["maintenance_excess"] = "1"
    cases.append((value, "maintenance margin excess"))
    value = deepcopy(base)
    value["margin"]["margin_call"] = True
    cases.append((value, "margin_call differs"))

    for payload, message in cases:
        with pytest.raises(ValueError, match=message):
            parse(
                payload,
                engine_sequence=8,
                recorded_at=now,
                slice_sequence=2,
            )


def test_signed_account_action_borrow_and_risk_guards() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    state_type = vars(journal)["_PositionState"]
    apply_fill = vars(journal)["_apply_fill_state"]

    def micros(value: str) -> int:
        return decimal_micros(Decimal(value))

    cash = {"USD": micros("1000")}

    with pytest.raises(ValueError, match="cross a short position"):
        apply_fill(
            {
                "instrument_id": "asset-a",
                "quote_currency": "USD",
                "side": "buy",
                "quantity_micros": micros("3"),
                "notional_micros": micros("300"),
                "fee_micros": 0,
            },
            cash=dict(cash),
            positions={"asset-a": state_type(quantity=micros("-2"))},
        )
    with pytest.raises(ValueError, match="cross a long position"):
        apply_fill(
            {
                "instrument_id": "asset-a",
                "quote_currency": "USD",
                "side": "sell",
                "quantity_micros": micros("3"),
                "notional_micros": micros("300"),
                "fee_micros": 0,
            },
            cash=dict(cash),
            positions={"asset-a": state_type(quantity=micros("2"))},
        )

    scenario = scenario_from_json(scenario_document())
    instruments = {item.instrument_id: item for item in scenario.instruments}
    apply_action = vars(journal)["_apply_action_state"]
    split = {
        "instrument_id": "asset-a",
        "action_type": "split",
        "previous_quantity_micros": micros("1"),
        "adjusted_quantity_micros": micros("2"),
        "numerator": 2,
        "denominator": 1,
    }
    with pytest.raises(ValueError, match="previous quantity"):
        apply_action(
            split,
            cash=dict(cash),
            positions={"asset-a": state_type()},
            instrument_by_id=instruments,
        )
    with pytest.raises(ValueError, match="exactly representable"):
        apply_action(
            {
                **split,
                "previous_quantity_micros": 1,
                "numerator": 1,
                "denominator": 2,
                "adjusted_quantity_micros": 0,
            },
            cash=dict(cash),
            positions={"asset-a": state_type(quantity=1)},
            instrument_by_id=instruments,
        )
    with pytest.raises(ValueError, match="adjusted quantity"):
        apply_action(
            {**split, "adjusted_quantity_micros": micros("1")},
            cash=dict(cash),
            positions={"asset-a": state_type(quantity=micros("1"))},
            instrument_by_id=instruments,
        )
    dividend = {
        "instrument_id": "asset-a",
        "action_type": "cash_dividend",
        "quantity_micros": micros("1"),
        "amount_per_unit_micros": micros("1"),
        "cash_amount_micros": micros("1"),
    }
    with pytest.raises(ValueError, match="quantity differs"):
        apply_action(
            dividend,
            cash=dict(cash),
            positions={"asset-a": state_type()},
            instrument_by_id=instruments,
        )
    with pytest.raises(ValueError, match="dividend differs"):
        apply_action(
            {**dividend, "cash_amount_micros": 0},
            cash=dict(cash),
            positions={"asset-a": state_type(quantity=micros("1"))},
            instrument_by_id=instruments,
        )

    borrow = {
        "instrument_id": "asset-a",
        "quote_currency": "USD",
        "short_quantity_micros": micros("1"),
        "reference_price_micros": micros("100"),
        "borrow_bps": 0,
        "period_start": pd.Timestamp("2026-01-02T14:30:00Z"),
        "period_end": pd.Timestamp("2026-01-02T14:35:00Z"),
        "slice_sequence": 1,
        "fee_micros": 0,
    }
    bars = {
        (1, "asset-a"): {
            "open_micros": micros("100"),
            "start_at": borrow["period_start"],
            "end_at": borrow["period_end"],
        }
    }
    apply_borrow = vars(journal)["_apply_borrow_fee_state"]
    with pytest.raises(ValueError, match="open short position"):
        apply_borrow(
            borrow,
            scenario=scenario,
            cash=dict(cash),
            positions={"asset-a": state_type()},
            instrument_by_id=instruments,
            bar_by_key=bars,
        )
    for changes, message in (
        ({"quote_currency": "EUR"}, "quote currency"),
        ({"borrow_bps": 1}, "risk policy"),
        ({"reference_price_micros": micros("99")}, "period and reference"),
        ({"fee_micros": 1}, "does not reconcile"),
    ):
        with pytest.raises(ValueError, match=message):
            apply_borrow(
                {**borrow, **changes},
                scenario=scenario,
                cash=dict(cash),
                positions={"asset-a": state_type(quantity=micros("-1"))},
                instrument_by_id=instruments,
                bar_by_key=bars,
            )

    initial_risk = vars(journal)["_initial_risk_error"]
    assert initial_risk(scenario, equity=micros("100"), gross_exposure=micros("1000001")) == (
        "portfolio would exceed maximum gross exposure"
    )
    assert initial_risk(scenario, equity=micros("100"), gross_exposure=micros("250")) == (
        "portfolio would exceed maximum leverage"
    )
    leveraged_payload = json.loads(scenario_document())
    leveraged_payload["risk"]["max_leverage"] = "3"
    leveraged = scenario_from_json(json.dumps(leveraged_payload))
    assert initial_risk(leveraged, equity=micros("100"), gross_exposure=micros("250")) == (
        "portfolio would violate initial margin"
    )
    assert initial_risk(scenario, equity=micros("100"), gross_exposure=micros("100")) is None


def test_journal_rejects_additional_causal_and_lifecycle_tampering(tmp_path: Path) -> None:
    scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
    valid = quantity_records(digest)
    with pytest.raises(ValueError, match="provided scenario_sha256 differs"):
        read_journal(
            write_journal(tmp_path / "hash.jsonl", deepcopy(valid)),
            scenario=scenario,
            scenario_sha256="f" * 64,
        )

    def rejected(name: str, records: list[dict[str, Any]], message: str) -> None:
        with pytest.raises(ValueError, match=message):
            read_journal(write_journal(tmp_path / f"{name}.jsonl", records))

    records = deepcopy(valid)
    records[3]["payload"]["status"] = "partially_filled"
    rejected("accepted-status", records, "order_accepted must contain working")

    records = deepcopy(valid)
    records[3]["event_type"] = "order_rejected"
    records[3]["payload"]["status"] = "working"
    rejected("rejected-status", records, "order_rejected must contain rejected")

    for name, field, value, message in (
        ("initial-fill", "filled_quantity", "1", "start with zero fill state"),
        ("created-sequence", "created_sequence", "99", "created_sequence"),
        ("updated-event", "updated_event_id", "forged-event", "updated_event_id"),
        ("eligibility", "eligible_after_slice_sequence", "2", "eligibility"),
    ):
        records = deepcopy(valid)
        normalize_audit_graph(records)
        records[3]["payload"][field] = value
        if field == "filled_quantity":
            records[3]["payload"]["filled_notional"] = "1"
        with pytest.raises(ValueError, match=message):
            read_journal(write_journal(tmp_path / f"{name}.jsonl", records, normalize=False))

    records = deepcopy(valid)
    records.insert(4, deepcopy(records[3]))
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    rejected("duplicate-order", records, "order identifiers must be unique")

    records = deepcopy(valid)
    normalize_audit_graph(records)
    records[-1]["causation_ids"] = []
    with pytest.raises(ValueError, match="immediately preceding event"):
        read_journal(write_journal(tmp_path / "completion-cause.jsonl", records, normalize=False))

    for event_type, payload, message in (
        (
            "margin_call",
            valuation_payload(
                mark="100",
                quantity="0",
                cash="10000",
                market_value="0",
                cost_basis="0",
                realized_pnl="0",
                unrealized_pnl="0",
                equity="10000",
                total_fees="0",
            ),
            "breached margin snapshot",
        ),
        (
            "margin_restored",
            valuation_payload(
                mark="100",
                quantity="0",
                cash="-1",
                market_value="0",
                cost_basis="0",
                realized_pnl="0",
                unrealized_pnl="0",
                equity="-1",
                total_fees="0",
            ),
            "restored margin snapshot",
        ),
    ):
        records = deepcopy(valid)
        records.insert(2, envelope(3, event_type, payload, recorded_at=records[1]["recorded_at"]))
        for sequence, record in enumerate(records, start=1):
            record["engine_sequence"] = str(sequence)
        rejected(event_type, records, message)

    records = deepcopy(valid)
    normalize_audit_graph(records)
    records[4]["causation_ids"] = []
    with pytest.raises(ValueError, match="valuation must cite"):
        read_journal(write_journal(tmp_path / "valuation-cause.jsonl", records, normalize=False))

    records = deepcopy(valid)
    records[2]["event_type"] = "future_event"
    records[2]["payload"] = {}
    rejected("future-event", records, "unsupported journal event_type")

    records = deepcopy(valid[:-1])
    rejected("incomplete", records, "start with run_started and end with run_completed")


def test_corporate_action_payload_guards_exact_ratios_and_amounts() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    parse = vars(journal)["_action_row"]
    parse_adjustment = vars(journal)["_order_adjustment_row"]
    now = pd.Timestamp("2026-01-02T14:45:00Z")
    split = {
        "type": "split",
        "action_id": "split-a",
        "instrument_id": "asset-a",
        "numerator": 2,
        "denominator": 1,
    }
    dividend = {
        "type": "cash_dividend",
        "action_id": "dividend-a",
        "instrument_id": "asset-a",
        "amount_per_unit": "1",
    }

    with pytest.raises(ValueError, match="must contain a split action"):
        parse(
            {"action": dividend, "previous_quantity": "1", "adjusted_quantity": "2"},
            event_type="split_applied",
            engine_sequence=1,
            recorded_at=now,
            slice_sequence=1,
        )
    with pytest.raises(ValueError, match="split quantities do not reconcile"):
        parse(
            {"action": split, "previous_quantity": "1", "adjusted_quantity": "3"},
            event_type="split_applied",
            engine_sequence=1,
            recorded_at=now,
            slice_sequence=1,
        )
    with pytest.raises(ValueError, match="must contain a dividend action"):
        parse(
            {"action": split, "quantity": "1", "cash_amount": "1"},
            event_type="cash_dividend_applied",
            engine_sequence=1,
            recorded_at=now,
            slice_sequence=1,
        )
    with pytest.raises(ValueError, match="dividend amount does not reconcile"):
        parse(
            {"action": dividend, "quantity": "2", "cash_amount": "1"},
            event_type="cash_dividend_applied",
            engine_sequence=1,
            recorded_at=now,
            slice_sequence=1,
        )
    matches = vars(journal)["_action_declaration_matches"]
    assert not matches(
        {"action_id": "a", "instrument_id": "asset-a", "action_type": "split"},
        {"action_id": "b", "instrument_id": "asset-a", "action_type": "split"},
    )

    records = quantity_records("0" * 64)
    normalize_audit_graph(records)
    adjusted = parse_adjustment(
        {"order": records[3]["payload"], "action_id": "split-a"},
        engine_sequence=4,
        recorded_at=now,
    )
    assert adjusted["action_id"] == "split-a"
    records[3]["payload"]["status"] = "filled"
    with pytest.raises(ValueError, match="must contain an active order"):
        parse_adjustment(
            {"order": records[3]["payload"], "action_id": "split-a"},
            engine_sequence=4,
            recorded_at=now,
        )

    completion = vars(journal)["_completion"]
    with pytest.raises(ValueError, match="order counts must reconcile"):
        completion(
            {
                "scenario_sha256": "0" * 64,
                "execution_model": "completed_bar_v1",
                "valuation": valuation_payload(
                    mark="100",
                    quantity="0",
                    cash="10000",
                    market_value="0",
                    cost_basis="0",
                    realized_pnl="0",
                    unrealized_pnl="0",
                    equity="10000",
                    total_fees="0",
                ),
                "order_counts": {
                    "total": 1,
                    "active": 0,
                    "filled": 0,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
            engine_sequence=1,
            recorded_at=now,
        )


def test_zero_position_corporate_actions_reconcile_end_to_end(tmp_path: Path) -> None:
    payload = json.loads(scenario_document())
    payload["schedule"] = []
    split = {
        "type": "split",
        "action_id": "split-a",
        "instrument_id": "asset-a",
        "numerator": 2,
        "denominator": 1,
    }
    dividend = {
        "type": "cash_dividend",
        "action_id": "dividend-a",
        "instrument_id": "asset-a",
        "amount_per_unit": "1",
    }
    payload["slices"][0]["corporate_actions"] = [split]
    payload["slices"][1]["corporate_actions"] = [dividend]
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "actions.scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    first_time = payload["slices"][0]["received_at"]
    second_time = payload["slices"][1]["received_at"]
    first = valuation_payload(
        mark="100",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    final = valuation_payload(
        mark="102",
        quantity="0",
        cash="10000",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="10000",
        total_fees="0",
    )
    records = [
        envelope(
            1,
            "run_started",
            {"scenario_sha256": digest, "execution_model": "completed_bar_v1"},
            recorded_at="1970-01-01T00:00:00Z",
        ),
        envelope(2, "market_slice_received", payload["slices"][0], recorded_at=first_time),
        envelope(
            3,
            "split_applied",
            {"action": split, "previous_quantity": "0", "adjusted_quantity": "0"},
            recorded_at=first_time,
        ),
        envelope(4, "valuation", first, recorded_at=first_time),
        envelope(5, "market_slice_received", payload["slices"][1], recorded_at=second_time),
        envelope(
            6,
            "cash_dividend_applied",
            {"action": dividend, "quantity": "0", "cash_amount": "0"},
            recorded_at=second_time,
        ),
        envelope(7, "valuation", final, recorded_at=second_time),
        envelope(
            8,
            "run_completed",
            {
                "scenario_sha256": digest,
                "execution_model": "completed_bar_v1",
                "valuation": final,
                "order_counts": {
                    "total": 0,
                    "active": 0,
                    "filled": 0,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
            recorded_at=second_time,
        ),
    ]

    replay = read_journal(
        write_journal(tmp_path / "actions.journal.jsonl", records),
        scenario=scenario_path,
    )
    assert replay.corporate_actions["action_type"].tolist() == [
        "split",
        "cash_dividend",
    ]
    assert replay.corporate_actions["adjusted_quantity"].iloc[0] == 0
    assert replay.corporate_actions["cash_amount"].iloc[1] == 0


def test_standalone_journal_imports_valid_borrow_and_margin_snapshots(tmp_path: Path) -> None:
    records = quantity_records("0" * 64)
    healthy = deepcopy(records[4]["payload"])
    breached = valuation_payload(
        mark="100",
        quantity="0",
        cash="-1",
        market_value="0",
        cost_basis="0",
        realized_pnl="0",
        unrealized_pnl="0",
        equity="-1",
        total_fees="0",
    )
    borrow = {
        "instrument_id": "asset-a",
        "quote_currency": "USD",
        "short_quantity": "1",
        "reference_price": "100",
        "borrow_bps": 100,
        "period_start": "2026-01-02T14:30:00Z",
        "period_end": "2026-01-02T14:35:00Z",
        "fee": "0.000001",
    }
    additions = [
        envelope(3, "borrow_fee_applied", borrow, recorded_at=records[1]["recorded_at"]),
        envelope(4, "margin_call", breached, recorded_at=records[1]["recorded_at"]),
        envelope(5, "margin_restored", healthy, recorded_at=records[1]["recorded_at"]),
    ]
    records[2:2] = additions
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)

    replay = read_journal(write_journal(tmp_path / "snapshots.jsonl", records))
    assert replay.borrow_fees.loc[0, "fee_micros"] == 1
    assert replay.margin_events["event_type"].tolist() == [
        "margin_call",
        "margin_restored",
    ]


def test_signed_account_success_paths_apply_native_ledger_effects() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    state_type = vars(journal)["_PositionState"]
    apply_fill = vars(journal)["_apply_fill_state"]

    def micros(value: str) -> int:
        return decimal_micros(Decimal(value))

    cash = {"USD": micros("1000")}
    position = state_type()
    apply_fill(
        {
            "instrument_id": "asset-a",
            "quote_currency": "USD",
            "side": "sell",
            "quantity_micros": micros("2"),
            "notional_micros": micros("200"),
            "fee_micros": micros("0.25"),
        },
        cash=cash,
        positions={"asset-a": position},
    )
    assert position.quantity == micros("-2")
    assert position.cost_basis == micros("-199.75")
    apply_fill(
        {
            "instrument_id": "asset-a",
            "quote_currency": "USD",
            "side": "buy",
            "quantity_micros": micros("1"),
            "notional_micros": micros("90"),
            "fee_micros": micros("0.25"),
        },
        cash=cash,
        positions={"asset-a": position},
    )
    assert position.quantity == micros("-1")
    assert position.cost_basis == micros("-99.875")
    assert position.realized_pnl == micros("9.625")

    scenario_payload = json.loads(scenario_document())
    scenario_payload["risk"]["short_borrow_bps"] = 10_000
    scenario = scenario_from_json(json.dumps(scenario_payload))
    instruments = {item.instrument_id: item for item in scenario.instruments}
    action_cash = {"USD": 0}
    action_position = state_type(quantity=micros("1"))
    apply_action = vars(journal)["_apply_action_state"]
    apply_action(
        {
            "instrument_id": "asset-a",
            "action_type": "split",
            "previous_quantity_micros": micros("1"),
            "adjusted_quantity_micros": micros("2"),
            "numerator": 2,
            "denominator": 1,
        },
        cash=action_cash,
        positions={"asset-a": action_position},
        instrument_by_id=instruments,
    )
    apply_action(
        {
            "instrument_id": "asset-a",
            "action_type": "cash_dividend",
            "quantity_micros": micros("2"),
            "amount_per_unit_micros": micros("0.5"),
            "cash_amount_micros": micros("1"),
        },
        cash=action_cash,
        positions={"asset-a": action_position},
        instrument_by_id=instruments,
    )
    assert action_cash == {"USD": micros("1")}
    assert action_position.dividend_pnl == micros("1")

    borrow_position = state_type(quantity=micros("-1"))
    period_start = pd.Timestamp("2026-01-02T14:30:00Z")
    period_end = pd.Timestamp("2026-01-02T14:35:00Z")
    vars(journal)["_apply_borrow_fee_state"](
        {
            "instrument_id": "asset-a",
            "quote_currency": "USD",
            "short_quantity_micros": micros("1"),
            "reference_price_micros": micros("100"),
            "borrow_bps": 10_000,
            "period_start": period_start,
            "period_end": period_end,
            "slice_sequence": 1,
            "fee_micros": 952,
        },
        scenario=scenario,
        cash={"USD": 0},
        positions={"asset-a": borrow_position},
        instrument_by_id=instruments,
        bar_by_key={
            (1, "asset-a"): {
                "open_micros": micros("100"),
                "start_at": period_start,
                "end_at": period_end,
            }
        },
    )
    assert borrow_position.realized_pnl == -952
    assert borrow_position.borrow_fees == 952


def test_order_risk_checks_fractional_lots_signed_limits_and_exposure() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    scenario = scenario_from_json(scenario_document())
    state_type = vars(journal)["_PositionState"]
    risk_error = vars(journal)["_order_risk_error"]
    instrument = scenario.instruments[0]
    instruments = {instrument.instrument_id: instrument}
    micros = decimal_micros
    bars = {
        (1, "asset-a"): {
            "open_micros": micros(Decimal("100")),
            "close_micros": micros(Decimal("100")),
        }
    }
    rates = {(1, "USD"): micros(Decimal("1"))}

    def check(
        *,
        side: str,
        quantity: str,
        position: str = "0",
        limit_price: object = pd.NA,
        active_orders: dict[str, dict[str, object]] | None = None,
    ) -> str | None:
        return risk_error(
            {
                "instrument_id": "asset-a",
                "side": side,
                "quantity_micros": micros(Decimal(quantity)),
                "limit_price_micros": limit_price,
            },
            scenario=scenario,
            cash={"USD": micros(Decimal("10000"))},
            positions={"asset-a": state_type(quantity=micros(Decimal(position)))},
            active_orders=active_orders or {},
            instrument_by_id=instruments,
            bar_by_key=bars,
            fx_by_key=rates,
            slice_sequence=1,
        )

    assert check(side="buy", quantity="1001") == (
        "order exceeds the maximum order quantity"
    )
    assert check(side="buy", quantity="0.5") == (
        "order quantity is not aligned to the instrument lot size"
    )
    assert check(
        side="buy",
        quantity="1",
        limit_price=micros(Decimal("100.001")),
    ) == "limit price is not aligned to the instrument tick size"
    assert check(side="sell", quantity="2", position="1") == (
        "one order must not cross a position through zero"
    )
    assert check(side="buy", quantity="2", position="-1") == (
        "one order must not cross a position through zero"
    )
    assert check(side="buy", quantity="1000", position="1") == (
        "position would exceed the maximum long position"
    )
    assert check(side="sell", quantity="1000", position="-1") == (
        "position would exceed the maximum short position"
    )
    assert check(side="sell", quantity="1", position="1100") is None
    assert check(side="buy", quantity="1", position="1100") == (
        "position would exceed the maximum long position"
    )
    assert check(
        side="buy",
        quantity="1",
        position="999",
        active_orders={
            "working": {
                "instrument_id": "asset-a",
                "side": "sell",
                "quantity_micros": micros(Decimal("1")),
                "filled_quantity_micros": 0,
            },
            "other": {
                "instrument_id": "other-asset",
                "side": "buy",
                "quantity_micros": micros(Decimal("1000")),
                "filled_quantity_micros": 0,
            },
        },
    ) is None
    assert check(side="sell", quantity="1", position="10") is None


def test_liquidation_order_validation_enforces_deterministic_shape() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    scenario = scenario_from_json(scenario_document())
    state_type = vars(journal)["_PositionState"]
    validate = vars(journal)["_validate_liquidation_order"]
    instrument = scenario.instruments[0]
    instruments = {instrument.instrument_id: instrument}
    positions = {"asset-a": state_type(quantity=decimal_micros(Decimal("1100")))}
    valid = {
        "instrument_id": "asset-a",
        "side": "sell",
        "quantity_micros": decimal_micros(Decimal("1000")),
        "order_kind": "market",
    }

    validate(
        valid,
        scenario=scenario,
        positions=positions,
        active_orders={},
        instrument_by_id=instruments,
    )
    for changes, message in (
        ({"instrument_id": "asset-z"}, "deterministic instrument order"),
        ({"side": "buy"}, "side must reduce"),
        ({"quantity_micros": decimal_micros(Decimal("999"))}, "bounded market quantity"),
        ({"order_kind": "limit"}, "bounded market quantity"),
    ):
        with pytest.raises(ValueError, match=message):
            validate(
                {**valid, **changes},
                scenario=scenario,
                positions=positions,
                active_orders={},
                instrument_by_id=instruments,
            )

    with pytest.raises(ValueError, match="no uncovered open position"):
        validate(
            valid,
            scenario=scenario,
            positions=positions,
            active_orders={
                "working": {
                    "instrument_id": "asset-a",
                    "origin": "margin_liquidation",
                }
            },
            instrument_by_id=instruments,
        )
    with pytest.raises(ValueError, match="cannot cover one instrument lot"):
        validate(
            valid,
            scenario=scenario,
            positions={"asset-a": state_type(quantity=decimal_micros(Decimal("0.5")))},
            active_orders={},
            instrument_by_id=instruments,
        )

    validate(
        {**valid, "side": "buy"},
        scenario=scenario,
        positions={"asset-a": state_type(quantity=decimal_micros(Decimal("-1100")))},
        active_orders={},
        instrument_by_id=instruments,
    )

    validate_coverage = vars(journal)["_validate_liquidation_coverage"]
    validate_coverage(
        positions=positions,
        active_orders={
            "working": {
                "instrument_id": "asset-a",
                "origin": "margin_liquidation",
            },
            "ordinary": {
                "instrument_id": "asset-a",
                "origin": "direct",
            },
        },
    )
    with pytest.raises(ValueError, match="every open position"):
        validate_coverage(positions=positions, active_orders={})


def test_runtime_path_rejects_liquidation_orders_outside_margin_calls() -> None:
    journal = import_module("persistra.integrations.trading_engine.journal")
    scenario = scenario_from_json(scenario_document())
    validate = vars(journal)["_validate_runtime_path"]
    instrument = scenario.instruments[0]
    micros = decimal_micros
    order = {
        "engine_sequence": 1,
        "event_type": "order_accepted",
        "order_id": "journal-demo-order-000000000001",
        "instrument_id": "asset-a",
        "side": "sell",
        "quantity_micros": micros(Decimal("1")),
        "filled_quantity_micros": 0,
        "limit_price_micros": pd.NA,
        "origin": "margin_liquidation",
        "order_kind": "market",
        "eligible_after_slice_sequence": 1,
    }
    common: dict[str, Any] = {
        "scenario": scenario,
        "instrument_by_id": {instrument.instrument_id: instrument},
        "bar_by_key": {(1, "asset-a"): {"close_micros": micros(Decimal("100"))}},
        "fx_by_key": {(1, "USD"): micros(Decimal("1"))},
        "adjustments": [],
        "fills": [],
        "cancellations": [],
        "actions": [],
        "margin_limits": [],
        "borrow_fees": [],
        "margin_events": [],
        "valuations": [],
        "cash_balances": [],
        "position_attributions": [],
    }

    with pytest.raises(ValueError, match="require an active margin call"):
        validate(orders=[order], **common)
    with pytest.raises(ValueError, match="must be accepted"):
        validate(
            orders=[
                {
                    **order,
                    "event_type": "order_rejected",
                    "quantity_micros": micros(Decimal("1001")),
                    "rejection_reason": "order exceeds the maximum order quantity",
                }
            ],
            **common,
        )
