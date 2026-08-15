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

from persistra.integrations.trading_engine import read_journal, scenario_from_json, write_scenario
from persistra.integrations.trading_engine._scalars import decimal_micros

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
            "run_id": "journal-demo",
            "base_currency": "USD",
            "initial_cash": initial_cash,
            "instruments": [
                {
                    "instrument_id": "asset-a",
                    "symbol": "AAA",
                    "quote_currency": "USD",
                    "tick_size": "0.01",
                    "lot_size": "1",
                }
            ],
            "risk": {"max_order_quantity": "1000", "max_position": "1000"},
            "execution": {"participation_bps": 5000, "fixed_fee": "0.25", "fee_bps": 10},
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
        "engine_sequence": str(sequence),
        "run_id": "journal-demo",
        "recorded_at": recorded_at,
        "event_type": event_type,
        "payload": payload,
    }


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
    first_valuation = {
        "cash": "10000",
        "market_value": "0",
        "cost_basis": "0",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "equity": "10000",
        "total_fees": "0",
    }
    final_valuation = {
        "cash": "9393.144",
        "market_value": "612",
        "cost_basis": "606.856",
        "realized_pnl": "0",
        "unrealized_pnl": "5.144",
        "equity": "10005.144",
        "total_fees": "0.856",
    }
    return [
        envelope(
            1,
            "run_started",
            {"scenario_sha256": scenario_hash},
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
    final = {
        "cash": "4944.7",
        "market_value": "5100",
        "cost_basis": "5055.3",
        "realized_pnl": "0",
        "unrealized_pnl": "44.7",
        "equity": "10044.7",
        "total_fees": "5.3",
    }
    records[7]["payload"] = final
    records[8]["payload"]["valuation"] = final
    return records


def scheduled_intent_scenario(tmp_path: Path):
    """Write a scenario exercising every direct scripted-intent outcome."""
    payload = json.loads(scenario_document())
    payload["risk"]["max_position"] = "5"
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
        "rejection_reason": "order would exceed the maximum long position",
    }
    cancelled = {**accepted, "status": "cancelled"}
    valuation = {
        "cash": "10000",
        "market_value": "0",
        "cost_basis": "0",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "equity": "10000",
        "total_fees": "0",
    }
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
        envelope(10, "valuation", valuation, recorded_at=first_time),
        envelope(11, "market_slice_received", slice_payload(2), recorded_at=second_time),
        envelope(12, "valuation", valuation, recorded_at=second_time),
        envelope(
            13,
            "run_completed",
            {
                "scenario_sha256": scenario_hash,
                "valuation": valuation,
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


def write_journal(path: Path, records: list[dict[str, Any]]) -> Path:
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
        "order would exceed the maximum long position",
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
    payload["risk"]["max_position"] = "5"
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
    forged_order["payload"]["rejection_reason"] = "order would exceed the maximum long position"
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

    with pytest.raises(ValueError, match="rejected despite passing runtime risk"):
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
            "quantity": 2,
            "origin": "target_rebalance",
            "created_sequence": 3,
        },
        {
            "engine_sequence": 4,
            "event_type": "order_accepted",
            "order_id": "journal-demo-order-000000000002",
            "quantity": 3,
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
    validate([outcome], orders=orders, fills=[], cancellations=cancellations)

    reversed_ids = deepcopy(cancellations)
    reversed_ids[0]["order_id"], reversed_ids[1]["order_id"] = (
        reversed_ids[1]["order_id"],
        reversed_ids[0]["order_id"],
    )
    for invalid in (cancellations[:1], reversed_ids):
        with pytest.raises(ValueError, match="replace every active target order in order"):
            validate([outcome], orders=orders, fills=[], cancellations=invalid)


def test_read_journal_normalizes_slices_targets_and_exact_values(tmp_path: Path) -> None:
    _scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
    path = write_journal(tmp_path / "journal.jsonl", quantity_records(digest))
    result = read_journal(path, scenario=tmp_path / "scenario.json")

    assert result.run_id == "journal-demo"
    assert result.scenario_sha256 == digest
    assert result.initial_cash_micros == 10_000_000_000
    assert result.bars["slice_sequence"].tolist() == [1, 2]
    assert result.targets.loc[0, "decision_slice_sequence"] == 1
    assert result.targets.loc[0, "basis"] == "quantities"
    assert result.fills.loc[0, "slice_sequence"] == 2
    assert result.fills.loc[0, "fee_micros"] == 856_000
    assert result.valuations["slice_sequence"].tolist() == [1, 2]
    assert result.cash_limits.empty
    assert result.completion.scenario_sha256 == digest
    assert result.events[0].event_type == "run_started"


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
    valuation = {
        "cash": "10000",
        "market_value": "0",
        "cost_basis": "0",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "equity": "10000",
        "total_fees": "0",
    }
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
                "valuation": valuation,
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
    with pytest.raises(ValueError, match="engine-owned sizing"):
        read_journal(
            write_journal(tmp_path / "bad.jsonl", records),
            scenario=tmp_path / "scenario.json",
        )


def test_read_journal_accepts_predicted_weight_target_rejection_without_shifting(
    tmp_path: Path,
) -> None:
    payload = json.loads(scenario_document(basis="weights"))
    payload["risk"]["max_position"] = "10"
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
    initial = {
        "cash": "10000",
        "market_value": "0",
        "cost_basis": "0",
        "realized_pnl": "0",
        "unrealized_pnl": "0",
        "equity": "10000",
        "total_fees": "0",
    }
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
            {"reason": "weight-derived target exceeds the maximum position"},
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
        envelope(7, "valuation", initial, recorded_at=second_time),
        envelope(
            8,
            "run_completed",
            {
                "scenario_sha256": digest,
                "valuation": initial,
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


def test_read_journal_validates_cash_limited_claims(tmp_path: Path) -> None:
    scenario_payload = json.loads(scenario_document(initial_cash="1000"))
    scenario_payload["schedule"][0]["intents"][0]["targets"][0]["quantity"] = "20"
    scenario = scenario_from_json(json.dumps(scenario_payload))
    scenario_path = write_scenario(scenario, tmp_path / "scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    records = quantity_records(digest)
    records[2]["payload"]["targets"][0]["quantity"] = "20"
    records[3]["payload"]["quantity"] = "20"
    records[4]["payload"]["cash"] = "1000"
    records[4]["payload"]["equity"] = "1000"
    records.insert(
        6,
        envelope(
            7,
            "cash_limited",
            {
                "order_id": "journal-demo-order-000000000001",
                "instrument_id": "asset-a",
                "requested_quantity": "20",
                "affordable_quantity": "9",
                "price": "101",
            },
            recorded_at="2026-01-02T14:45:00.000000Z",
        ),
    )
    fill = records[7]["payload"]
    fill.update({"quantity": "9", "notional": "909", "fee": "1.159"})
    final = {
        "cash": "89.841",
        "market_value": "918",
        "cost_basis": "910.159",
        "realized_pnl": "0",
        "unrealized_pnl": "7.841",
        "equity": "1007.841",
        "total_fees": "1.159",
    }
    records[8]["payload"] = final
    records[9]["payload"]["valuation"] = final
    records[9]["payload"]["order_counts"].update({"active": 1, "filled": 0})
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    result = read_journal(
        write_journal(tmp_path / "journal.jsonl", records), scenario=scenario_path
    )
    assert result.cash_limits.loc[0, "affordable_quantity"] == 9

    invalid = deepcopy(records)
    invalid[6]["payload"]["affordable_quantity"] = "8"
    with pytest.raises(ValueError, match="same-slice fill"):
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
    wrong_price[6]["payload"]["price"] = "100"
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
    out_of_order[7]["payload"]["requested_quantity"] = "11"
    for sequence, record in enumerate(out_of_order, start=1):
        record["engine_sequence"] = str(sequence)
    with pytest.raises(ValueError, match="must follow the event"):
        read_journal(
            write_journal(tmp_path / "out-of-order.jsonl", out_of_order),
            scenario=scenario_path,
        )
    not_a_buy = deepcopy(records)
    not_a_buy[3]["payload"]["side"] = "sell"
    not_a_buy[7]["payload"]["side"] = "sell"
    with pytest.raises(ValueError, match="accepted buy order"):
        read_journal(
            write_journal(tmp_path / "not-a-buy.jsonl", not_a_buy),
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
    final = {
        "cash": "9595.346",
        "market_value": "408",
        "cost_basis": "404.654",
        "realized_pnl": "0",
        "unrealized_pnl": "3.346",
        "equity": "10003.346",
        "total_fees": "0.654",
    }
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
    with pytest.raises(ValueError, match="fill state does not reconcile"):
        read_journal(
            write_journal(tmp_path / "bad-fill-state.jsonl", bad_fill_state),
            scenario=scenario_path,
        )
    bad_request_state = deepcopy(records)
    bad_request_state[7]["payload"]["order"]["quantity"] = "5"
    with pytest.raises(ValueError, match="state differs from its accepted order"):
        read_journal(
            write_journal(tmp_path / "bad-request-state.jsonl", bad_request_state),
            scenario=scenario_path,
        )


@pytest.mark.parametrize(
    "field",
    [
        "cash",
        "market_value",
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
    with pytest.raises(ValueError, match="valuation fields do not reconcile"):
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
        records[6]["payload"]["price"] = "101.001"
    else:
        records[2]["payload"]["targets"][0]["reference_price"] = "100"
    with pytest.raises(ValueError, match=message):
        read_journal(
            write_journal(tmp_path / "journal.jsonl", records),
            scenario=tmp_path / "scenario.json",
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


def test_standalone_journal_enforces_target_and_valuation_bounds(tmp_path: Path) -> None:
    digest = "0" * 64
    records = weight_records(digest)
    records[2]["payload"]["targets"][0]["weight"] = "1.000001"
    with pytest.raises(ValueError, match="weight must not exceed one"):
        read_journal(write_journal(tmp_path / "large-weight.jsonl", records))

    records = weight_records(digest)
    records[2]["payload"]["targets"] = [
        {
            "instrument_id": "asset-a",
            "weight": "0.6",
            "quantity": "60",
            "reference_price": "100",
        },
        {
            "instrument_id": "asset-b",
            "weight": "0.5",
            "quantity": "25",
            "reference_price": "200",
        },
    ]
    with pytest.raises(ValueError, match="sum to at most one"):
        read_journal(write_journal(tmp_path / "large-total.jsonl", records))

    for field in ("market_value", "cost_basis", "equity"):
        records = quantity_records(digest)
        records[4]["payload"][field] = "-0.000001"
        with pytest.raises(ValueError, match=f"{field} must be nonnegative"):
            read_journal(write_journal(tmp_path / f"negative-{field}.jsonl", records))
    records = quantity_records(digest)
    records[-1]["payload"]["valuation"]["equity"] = "-0.000001"
    with pytest.raises(ValueError, match="equity must be nonnegative"):
        read_journal(write_journal(tmp_path / "negative-completion.jsonl", records))


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
    payload["risk"]["max_position"] = "5"
    payload["schedule"][0]["intents"][0]["targets"][0]["quantity"] = "4"
    scenario = scenario_from_json(json.dumps(payload))
    scenario_path = write_scenario(scenario, tmp_path / "max-position-scenario.json")
    digest = hashlib.sha256(scenario_path.read_bytes()).hexdigest()
    records = quantity_records(digest)
    records[2]["payload"]["targets"][0]["quantity"] = "4"
    with pytest.raises(ValueError, match="projected max_position"):
        read_journal(
            write_journal(tmp_path / "max-position.jsonl", records),
            scenario=scenario_path,
        )


def test_read_journal_rejects_cancellation_after_a_full_fill(tmp_path: Path) -> None:
    scenario, digest = write_scenario_fixture(tmp_path / "scenario.json")
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
            scenario=scenario,
        )


def test_execution_reconciliation_uses_exact_proportional_sell_basis() -> None:
    payload = json.loads(scenario_document(initial_cash="1000"))
    payload["schedule"] = []
    payload["slices"].append(
        {
            **deepcopy(payload["slices"][-1]),
            "slice_sequence": "3",
            "start_at": "2026-01-02T14:50:00.000000Z",
            "end_at": "2026-01-02T14:55:00.000000Z",
            "available_at": "2026-01-02T14:55:00.000000Z",
            "received_at": "2026-01-02T14:55:00.000000Z",
        }
    )
    scenario = scenario_from_json(json.dumps(payload))

    def micros(value: str) -> int:
        return decimal_micros(Decimal(value))

    bars = [
        {
            "slice_sequence": sequence,
            "instrument_id": "asset-a",
            "close_micros": micros(mark),
            "volume": pd.NA,
        }
        for sequence, mark in enumerate(("110", "110", "90"), start=1)
    ]
    fills = [
        {
            "engine_sequence": 2,
            "order_id": "journal-demo-order-000000000001",
            "slice_sequence": 1,
            "instrument_id": "asset-a",
            "side": "buy",
            "quantity": 3,
            "price_micros": micros("100"),
            "notional_micros": micros("300"),
            "fee_micros": micros("0.55"),
        },
        {
            "engine_sequence": 4,
            "order_id": "journal-demo-order-000000000002",
            "slice_sequence": 2,
            "instrument_id": "asset-a",
            "side": "sell",
            "quantity": 1,
            "price_micros": micros("120"),
            "notional_micros": micros("120"),
            "fee_micros": micros("0.37"),
        },
        {
            "engine_sequence": 6,
            "order_id": "journal-demo-order-000000000003",
            "slice_sequence": 3,
            "instrument_id": "asset-a",
            "side": "sell",
            "quantity": 2,
            "price_micros": micros("90"),
            "notional_micros": micros("180"),
            "fee_micros": micros("0.43"),
        },
    ]
    orders = [
        {
            "engine_sequence": 1,
            "event_type": "order_accepted",
            "order_id": "journal-demo-order-000000000001",
            "instrument_id": "asset-a",
            "side": "buy",
            "quantity": 3,
            "limit_price_micros": pd.NA,
        },
        {
            "engine_sequence": 3,
            "event_type": "order_accepted",
            "order_id": "journal-demo-order-000000000002",
            "instrument_id": "asset-a",
            "side": "sell",
            "quantity": 1,
            "limit_price_micros": pd.NA,
        },
        {
            "engine_sequence": 5,
            "event_type": "order_accepted",
            "order_id": "journal-demo-order-000000000003",
            "instrument_id": "asset-a",
            "side": "sell",
            "quantity": 2,
            "limit_price_micros": pd.NA,
        },
    ]
    valuation_values = [
        ("699.45", "330", "300.55", "0", "29.45", "1029.45", "0.55"),
        (
            "819.08",
            "220",
            "200.366667",
            "19.446667",
            "19.633333",
            "1039.08",
            "0.92",
        ),
        ("998.65", "0", "0", "-1.35", "0", "998.65", "1.35"),
    ]
    names = (
        "cash_micros",
        "market_value_micros",
        "cost_basis_micros",
        "realized_pnl_micros",
        "unrealized_pnl_micros",
        "equity_micros",
        "total_fees_micros",
    )
    valuations = [
        {
            "slice_sequence": sequence,
            **dict(zip(names, (micros(value) for value in values), strict=True)),
        }
        for sequence, values in enumerate(valuation_values, start=1)
    ]
    validate = vars(import_module("persistra.integrations.trading_engine.journal"))[
        "_validate_execution_values"
    ]
    validate(
        scenario,
        bars=bars,
        orders=orders,
        fills=fills,
        cancellations=[],
        cash_limits=[],
        valuations=valuations,
    )

    invalid = deepcopy(valuations)
    invalid[1]["cost_basis_micros"] += 1
    with pytest.raises(ValueError, match="valuation fields do not reconcile"):
        validate(
            scenario,
            bars=bars,
            orders=orders,
            fills=fills,
            cancellations=[],
            cash_limits=[],
            valuations=invalid,
        )
