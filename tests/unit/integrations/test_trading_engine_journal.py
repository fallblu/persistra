"""Tests for strict trading-engine journal import."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    read_journal,
    scenario_from_json,
    write_scenario,
)

if TYPE_CHECKING:
    from pathlib import Path


def scenario_document(*, volume: str | None = "100") -> str:
    """Return a one-bar target-position scenario document."""
    return json.dumps(
        {
            "schema_version": 1,
            "run_id": "journal-demo",
            "base_currency": "USD",
            "initial_cash": "10000",
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
            "schedule": [
                {
                    "after_bar_sequence": "1",
                    "intents": [
                        {
                            "type": "target_position",
                            "instrument_id": "asset-a",
                            "quantity": "50",
                        }
                    ],
                }
            ],
            "bars": [
                {
                    "source_sequence": "1",
                    "instrument_id": "asset-a",
                    "start_at": "2026-01-02T14:30:00.000000Z",
                    "end_at": "2026-01-02T14:35:00.000000Z",
                    "available_at": "2026-01-02T14:35:01.000000Z",
                    "received_at": "2026-01-02T14:35:03.000000Z",
                    "open": "99",
                    "high": "101",
                    "low": "98",
                    "close": "100",
                    "volume": volume,
                }
            ],
        }
    )


def journal_records(*, volume: str | None = "100") -> list[dict[str, Any]]:
    """Return one complete journal with a working target order."""
    recorded_at = "2026-01-02T14:35:03.000000Z"
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
        {
            "schema_version": 1,
            "engine_sequence": "1",
            "run_id": "journal-demo",
            "recorded_at": recorded_at,
            "event_type": "bar_received",
            "payload": {
                "source_sequence": "1",
                "instrument_id": "asset-a",
                "start_at": "2026-01-02T14:30:00.000000Z",
                "end_at": "2026-01-02T14:35:00.000000Z",
                "available_at": "2026-01-02T14:35:01.000000Z",
                "received_at": recorded_at,
                "open": "99",
                "high": "101",
                "low": "98",
                "close": "100",
                "volume": volume,
            },
        },
        {
            "schema_version": 1,
            "engine_sequence": "2",
            "run_id": "journal-demo",
            "recorded_at": recorded_at,
            "event_type": "target_requested",
            "payload": {"instrument_id": "asset-a", "quantity": "50"},
        },
        {
            "schema_version": 1,
            "engine_sequence": "3",
            "run_id": "journal-demo",
            "recorded_at": recorded_at,
            "event_type": "order_accepted",
            "payload": {
                "order_id": "journal-demo-order-000000000001",
                "instrument_id": "asset-a",
                "side": "buy",
                "quantity": "50",
                "order_kind": "market",
                "limit_price": None,
                "origin": "target_rebalance",
                "created_at": recorded_at,
                "created_sequence": "3",
                "eligible_after_bar_sequence": "1",
                "filled_quantity": "0",
                "filled_notional": "0",
                "status": "working",
                "rejection_reason": None,
            },
        },
        {
            "schema_version": 1,
            "engine_sequence": "4",
            "run_id": "journal-demo",
            "recorded_at": recorded_at,
            "event_type": "valuation",
            "payload": valuation,
        },
        {
            "schema_version": 1,
            "engine_sequence": "5",
            "run_id": "journal-demo",
            "recorded_at": recorded_at,
            "event_type": "run_completed",
            "payload": {
                "valuation": dict(valuation),
                "order_counts": {
                    "total": 1,
                    "active": 1,
                    "filled": 0,
                    "rejected": 0,
                    "cancelled": 0,
                },
            },
        },
    ]


def write_journal(path: Path, records: list[dict[str, Any]]) -> Path:
    """Write compact JSON Lines test records."""
    path.write_text("".join(f"{json.dumps(item, separators=(',', ':'))}\n" for item in records))
    return path


def records_with_event(event_type: str, payload: object) -> list[dict[str, Any]]:
    """Insert one derived event into the open first-bar group."""
    records = journal_records()
    records.insert(
        3,
        {
            "schema_version": 1,
            "engine_sequence": "4",
            "run_id": "journal-demo",
            "recorded_at": "2026-01-02T14:35:03.000000Z",
            "event_type": event_type,
            "payload": payload,
        },
    )
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    return records


def lifecycle_records() -> list[dict[str, Any]]:
    """Return a valid two-bar limit-fill and cancellation lifecycle."""
    first_bar, target, accepted, first_valuation, completion = journal_records()
    accepted["payload"].update({"order_kind": "limit", "limit_price": "101"})
    second_time = "2026-01-02T14:45:00.000000Z"
    second_bar = deepcopy(first_bar)
    second_bar["recorded_at"] = second_time
    second_bar["payload"].update(
        {
            "source_sequence": "2",
            "start_at": "2026-01-02T14:40:00.000000Z",
            "end_at": second_time,
            "available_at": second_time,
            "received_at": second_time,
            "open": "102",
            "high": "103",
            "low": "100",
            "close": "102",
        }
    )
    fill = {
        "schema_version": 1,
        "engine_sequence": "6",
        "run_id": "journal-demo",
        "recorded_at": second_time,
        "event_type": "fill_applied",
        "payload": {
            "fill_id": "journal-demo-fill-000000000001",
            "order_id": "journal-demo-order-000000000001",
            "instrument_id": "asset-a",
            "side": "buy",
            "quantity": "6",
            "price": "101",
            "notional": "606",
            "fee": "0.856",
            "executed_at": second_time,
            "bar_sequence": "2",
        },
    }
    cancelled = {
        "schema_version": 1,
        "engine_sequence": "7",
        "run_id": "journal-demo",
        "recorded_at": second_time,
        "event_type": "order_cancelled",
        "payload": {
            "order": {
                **accepted["payload"],
                "filled_quantity": "6",
                "filled_notional": "606",
                "status": "cancelled",
            },
            "reason": "strategy_requested",
        },
    }
    second_valuation = deepcopy(first_valuation)
    second_valuation["recorded_at"] = second_time
    completion["recorded_at"] = second_time
    completion["payload"]["order_counts"].update({"active": 0, "cancelled": 1})
    result = [
        first_bar,
        target,
        accepted,
        first_valuation,
        second_bar,
        fill,
        cancelled,
        second_valuation,
        completion,
    ]
    for sequence, record in enumerate(result, start=1):
        record["engine_sequence"] = str(sequence)
    return result


def test_read_journal_normalizes_frames_and_preserves_exact_micros(tmp_path: Path) -> None:
    scenario = scenario_from_json(scenario_document())
    path = write_journal(tmp_path / "journal.jsonl", journal_records())

    result = read_journal(path, scenario=scenario)

    assert result.run_id == "journal-demo"
    assert result.initial_cash == 10_000.0
    assert result.initial_cash_micros == 10_000_000_000
    assert result.base_currency == "USD"
    assert result.bars.loc[0, "open"] == 99.0
    assert result.bars.loc[0, "open_micros"] == 99_000_000
    assert str(result.bars.dtypes["source_sequence"]) == "Int64"
    assert str(result.bars.dtypes["recorded_at"]) == "datetime64[ns, UTC]"
    assert result.targets.loc[0, "decision_bar_sequence"] == 1
    assert result.targets.loc[0, "reference_close"] == 100.0
    assert result.targets.loc[0, "reference_close_micros"] == 100_000_000
    assert pd.isna(result.targets.loc[0, "target_weight"])
    assert result.orders.loc[0, "event_type"] == "order_accepted"
    assert result.orders.loc[0, "created_at"] == pd.Timestamp(
        "2026-01-02T14:35:03Z"
    )
    assert result.fills.empty
    assert result.cancellations.empty
    assert result.rejections.empty
    assert result.completion.active_orders == 1
    assert result.completion.equity_micros == 10_000_000_000
    with pytest.raises(TypeError):
        cast("dict[str, object]", result.events[0].payload)["changed"] = True


def test_scenario_path_round_trip_does_not_claim_research_weight_metadata(
    tmp_path: Path,
) -> None:
    base = scenario_from_json(scenario_document())
    weighted = replace(
        base,
        decisions=(replace(base.decisions[0], target_weight=0.5),),
    )
    journal_path = write_journal(tmp_path / "weighted.jsonl", journal_records())
    scenario_path = write_scenario(weighted, tmp_path / "weighted.json")

    in_memory = read_journal(journal_path, scenario=weighted)
    from_artifact = read_journal(journal_path, scenario=scenario_path)

    assert in_memory.targets.loc[0, "target_weight"] == 0.5
    assert pd.isna(from_artifact.targets.loc[0, "target_weight"])
    assert from_artifact.targets.loc[0, "quantity"] == 50


def test_read_journal_reconciles_a_null_volume_scenario(tmp_path: Path) -> None:
    scenario = scenario_from_json(scenario_document(volume=None))
    path = write_journal(tmp_path / "null-volume.jsonl", journal_records(volume=None))

    result = read_journal(path, scenario=scenario)

    assert pd.isna(result.bars.loc[0, "volume"])


def test_read_journal_rejects_any_scenario_bar_difference(tmp_path: Path) -> None:
    scenario = scenario_from_json(scenario_document())
    records = journal_records()
    records[0]["payload"]["open"] = "98.5"
    path = write_journal(tmp_path / "different-bar.jsonl", records)

    with pytest.raises(ValueError, match="scenario and journal bars differ"):
        read_journal(path, scenario=scenario)


def test_read_journal_rejects_terminal_valuation_and_count_mismatches(tmp_path: Path) -> None:
    records = journal_records()
    records[-1]["payload"]["valuation"]["equity"] = "9999"
    path = write_journal(tmp_path / "valuation-mismatch.jsonl", records)
    with pytest.raises(ValueError, match="must match the final valuation"):
        read_journal(path)

    records = journal_records()
    counts = records[-1]["payload"]["order_counts"]
    counts["active"] = 0
    counts["filled"] = 1
    path = write_journal(tmp_path / "count-mismatch.jsonl", records)
    with pytest.raises(ValueError, match="must match imported order state"):
        read_journal(path)


def test_read_journal_rejects_inconsistent_rejection_fields(tmp_path: Path) -> None:
    records = journal_records()
    order = records[2]
    order["event_type"] = "order_rejected"
    order["payload"]["status"] = "rejected"
    path = write_journal(tmp_path / "rejected.jsonl", records)

    with pytest.raises(ValueError, match="must apply together"):
        read_journal(path)


def test_read_journal_enforces_order_and_fill_causality(tmp_path: Path) -> None:
    records = journal_records()
    records[2]["payload"]["created_at"] = "2026-01-02T14:35:02.000000Z"
    path = write_journal(tmp_path / "bad-submission-clock.jsonl", records)
    with pytest.raises(ValueError, match="must equal audit recorded_at"):
        read_journal(path)

    records = journal_records()
    records.insert(
        3,
        {
            "schema_version": 1,
            "engine_sequence": "4",
            "run_id": "journal-demo",
            "recorded_at": "2026-01-02T14:35:03.000000Z",
            "event_type": "fill_applied",
            "payload": {
                "fill_id": "journal-demo-fill-000000000001",
                "order_id": "journal-demo-order-000000000001",
                "instrument_id": "asset-a",
                "side": "buy",
                "quantity": "50",
                "price": "99",
                "notional": "4950",
                "fee": "0",
                "executed_at": "2026-01-02T14:35:02.000000Z",
                "bar_sequence": "1",
            },
        },
    )
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    records[-1]["payload"]["order_counts"].update({"active": 0, "filled": 1})
    path = write_journal(tmp_path / "fill-before-order.jsonl", records)
    with pytest.raises(ValueError, match="must not precede order created_at"):
        read_journal(path)


def test_read_journal_reconciles_empty_completion_to_initial_cash(tmp_path: Path) -> None:
    scenario_payload = json.loads(scenario_document())
    scenario_payload["schedule"] = []
    scenario_payload["bars"] = []
    scenario = scenario_from_json(json.dumps(scenario_payload))
    completion = journal_records()[-1]
    completion["engine_sequence"] = "1"
    completion["recorded_at"] = "1970-01-01T00:00:00.000000Z"
    completion["payload"]["valuation"]["cash"] = "9999"
    completion["payload"]["valuation"]["equity"] = "9999"
    completion["payload"]["order_counts"].update({"total": 0, "active": 0})
    path = write_journal(tmp_path / "bad-empty-completion.jsonl", [completion])

    with pytest.raises(ValueError, match="reconcile to scenario initial_cash"):
        read_journal(path, scenario=scenario)


def test_read_journal_imports_rejections_metrics_and_limit_orders(tmp_path: Path) -> None:
    records = journal_records()
    order = records[2]
    order["event_type"] = "order_rejected"
    order["payload"].update(
        {
            "order_kind": "limit",
            "limit_price": "99",
            "status": "rejected",
            "rejection_reason": "risk limit",
        }
    )
    records.insert(
        3,
        {
            "schema_version": 1,
            "engine_sequence": "4",
            "run_id": "journal-demo",
            "recorded_at": "2026-01-02T14:35:03.000000Z",
            "event_type": "intent_rejected",
            "payload": {"reason": "unsupported request"},
        },
    )
    records.insert(
        4,
        {
            "schema_version": 1,
            "engine_sequence": "5",
            "run_id": "journal-demo",
            "recorded_at": "2026-01-02T14:35:03.000000Z",
            "event_type": "metric_emitted",
            "payload": {"name": "desired position", "value": "0.5"},
        },
    )
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    records[-1]["payload"]["order_counts"].update(
        {"active": 0, "rejected": 1}
    )
    path = write_journal(tmp_path / "rejections.jsonl", records)

    result = read_journal(path)

    assert result.orders.loc[0, "event_type"] == "order_rejected"
    assert result.orders.loc[0, "limit_price_micros"] == 99_000_000
    assert list(result.rejections["event_type"]) == ["order_rejected", "intent_rejected"]
    assert result.metrics.loc[0, "name"] == "desired position"


def test_read_journal_imports_partial_fill_and_cancellation_lifecycle(tmp_path: Path) -> None:
    lifecycle = lifecycle_records()
    second_time = "2026-01-02T14:45:00.000000Z"
    path = write_journal(tmp_path / "lifecycle.jsonl", lifecycle)

    result = read_journal(path)

    assert result.fills.loc[0, "fee_micros"] == 856_000
    assert result.fills.loc[0, "executed_at"] == pd.Timestamp(second_time)
    assert result.cancellations.loc[0, "reason"] == "strategy_requested"
    assert result.cancellations.loc[0, "filled_quantity"] == 6
    assert result.completion.cancelled_orders == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("notional", "notional must equal price times quantity"),
        ("fill_id", "fill identifiers must be unique"),
        ("valuation_clock", "bar-group event recorded_at must equal"),
    ],
)
def test_read_journal_rejects_corrupt_fill_and_valuation_identity(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = lifecycle_records()
    if mutation == "notional":
        records[5]["payload"]["notional"] = "607"
    elif mutation == "fill_id":
        duplicate = deepcopy(records[5])
        duplicate["payload"].update({"quantity": "1", "notional": "101"})
        records.insert(6, duplicate)
        records[6]["engine_sequence"] = "7"
        records[6]["payload"]["fill_id"] = records[5]["payload"]["fill_id"]
        for sequence, record in enumerate(records, start=1):
            record["engine_sequence"] = str(sequence)
    else:
        records[3]["recorded_at"] = records[4]["recorded_at"]
    path = write_journal(tmp_path / f"{mutation}.jsonl", records)

    with pytest.raises(ValueError, match=message):
        read_journal(path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("created_sequence", "999", "created_sequence must equal"),
        (
            "eligible_after_bar_sequence",
            "0",
            "eligibility must equal the current bar",
        ),
    ],
)
def test_read_journal_rejects_corrupt_submission_anchor(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    records = journal_records()
    records[2]["payload"][field] = value
    path = write_journal(tmp_path / f"{field}.jsonl", records)

    with pytest.raises(ValueError, match=message):
        read_journal(path)


@pytest.mark.parametrize("field", ["notional", "fee"])
def test_read_journal_rejects_negative_execution_amounts(
    tmp_path: Path,
    field: str,
) -> None:
    records = lifecycle_records()
    records[5]["payload"][field] = "-1"
    path = write_journal(tmp_path / f"negative-{field}.jsonl", records)

    with pytest.raises(ValueError, match=rf"{field} must be nonnegative"):
        read_journal(path)

    records = journal_records()
    records[2]["payload"]["filled_notional"] = "-1"
    path = write_journal(tmp_path / "negative-filled-notional.jsonl", records)

    with pytest.raises(ValueError, match="filled_notional must be nonnegative"):
        read_journal(path)


@pytest.mark.parametrize("location", ["valuation", "completion"])
def test_read_journal_rejects_negative_total_fees(
    tmp_path: Path,
    location: str,
) -> None:
    records = journal_records()
    if location == "valuation":
        records[3]["payload"]["total_fees"] = "-1"
    else:
        records[-1]["payload"]["valuation"]["total_fees"] = "-1"
    path = write_journal(tmp_path / f"negative-fees-{location}.jsonl", records)

    with pytest.raises(ValueError, match="total_fees must be nonnegative"):
        read_journal(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("after_valuation", "nonterminal journal events require an open bar group"),
        ("unclosed_bar", "each bar group must end with valuation"),
        ("wrong_clock", "bar-group event recorded_at must equal"),
    ],
)
def test_read_journal_enforces_bar_group_stream_grammar(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = lifecycle_records()
    if mutation == "after_valuation":
        valuation = records.pop(3)
        records.insert(1, valuation)
    elif mutation == "unclosed_bar":
        records.pop(3)
    else:
        wrong_clock = "2026-01-02T14:35:04.000000Z"
        records[1]["recorded_at"] = wrong_clock
        records[2]["recorded_at"] = wrong_clock
        records[2]["payload"]["created_at"] = wrong_clock
        records[3]["recorded_at"] = wrong_clock
    for sequence, record in enumerate(records, start=1):
        record["engine_sequence"] = str(sequence)
    path = write_journal(tmp_path / f"bad-stream-{mutation}.jsonl", records)

    with pytest.raises(ValueError, match=message):
        read_journal(path)


def test_read_journal_reconciles_scenario_decision_clock(tmp_path: Path) -> None:
    scenario = scenario_from_json(scenario_document())
    mismatched = replace(
        scenario,
        decisions=(
            replace(
                scenario.decisions[0],
                decision_at=scenario.decisions[0].decision_at + pd.Timedelta(seconds=1),
            ),
        ),
    )
    path = write_journal(tmp_path / "decision-clock.jsonl", journal_records())

    with pytest.raises(ValueError, match="scenario and journal targets differ"):
        read_journal(path, scenario=mismatched)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("version", "unsupported journal schema_version"),
        ("run_id", "journal run_id must remain constant"),
        ("backward_clock", "journal recorded_at must not move backward"),
        ("after_completion", "run_completed must be the terminal"),
        ("source_sequence", "bar source_sequence must increase globally"),
        ("receipt_clock", "bar receipt time must equal"),
        ("completion_before_valuation", "run_completed must follow"),
        ("low", "bar low exceeds"),
        ("high", "bar high is below"),
        ("counts", "terminal order counts must reconcile"),
        ("reference", "target_requested has no causal reference close"),
    ],
)
def test_read_journal_rejects_additional_stream_corruption(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = lifecycle_records()
    if mutation == "version":
        records[0]["schema_version"] = 2
    elif mutation == "run_id":
        records[1]["run_id"] = "other-run"
    elif mutation == "backward_clock":
        records[4]["recorded_at"] = "2026-01-02T14:35:02.000000Z"
    elif mutation == "after_completion":
        trailing = deepcopy(records[0])
        trailing["engine_sequence"] = str(len(records) + 1)
        trailing["payload"]["source_sequence"] = "3"
        trailing["recorded_at"] = records[-1]["recorded_at"]
        trailing["payload"]["received_at"] = records[-1]["recorded_at"]
        records.append(trailing)
    elif mutation == "source_sequence":
        records[4]["payload"]["source_sequence"] = "1"
    elif mutation == "receipt_clock":
        records[0]["payload"]["received_at"] = "2026-01-02T14:35:04.000000Z"
    elif mutation == "completion_before_valuation":
        records = journal_records()
        records.pop(3)
        records[-1]["engine_sequence"] = "4"
    elif mutation == "low":
        records[0]["payload"]["low"] = "100"
    elif mutation == "high":
        records[0]["payload"]["high"] = "99"
    elif mutation == "counts":
        records[-1]["payload"]["order_counts"]["cancelled"] = 0
    else:
        records[1]["payload"]["instrument_id"] = "asset-b"
    path = write_journal(tmp_path / f"additional-{mutation}.jsonl", records)

    with pytest.raises(ValueError, match=message):
        read_journal(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("accepted_rejected", "order_accepted cannot contain rejected status"),
        ("rejected_working", "order_rejected must contain rejected status"),
        ("market_limit", "market orders require null limit_price"),
        ("reason_type", "rejection_reason must be a string or null"),
        ("future_creation", "created_at must not follow"),
        ("cancellation_status", "order_cancelled must contain cancelled status"),
    ],
)
def test_read_journal_rejects_additional_order_corruption(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = journal_records()
    order = records[2]
    if mutation == "accepted_rejected":
        order["payload"].update({"status": "rejected", "rejection_reason": "risk"})
    elif mutation == "rejected_working":
        order["event_type"] = "order_rejected"
    elif mutation == "market_limit":
        order["payload"]["limit_price"] = "99"
    elif mutation == "reason_type":
        order["payload"]["rejection_reason"] = ["risk"]
    elif mutation == "future_creation":
        order["payload"]["created_at"] = "2026-01-02T14:35:04.000000Z"
    else:
        records = lifecycle_records()
        records[6]["payload"]["order"]["status"] = "working"
    path = write_journal(tmp_path / f"order-{mutation}.jsonl", records)

    with pytest.raises(ValueError, match=message):
        read_journal(path)


@pytest.mark.parametrize(
    ("event_type", "payload", "message"),
    [
        ("metric_emitted", {"name": 1, "value": "x"}, "metric name must be a string"),
        (
            "metric_emitted",
            {"name": " padded", "value": "x"},
            "metric name must be a nonempty trimmed string",
        ),
        ("metric_emitted", {"name": "metric", "value": 1}, "metric value must be a string"),
        ("intent_rejected", {"reason": ""}, "reason must be a nonempty string"),
    ],
)
def test_read_journal_rejects_invalid_auxiliary_events(
    tmp_path: Path,
    event_type: str,
    payload: object,
    message: str,
) -> None:
    path = write_journal(
        tmp_path / f"invalid-{event_type}.jsonl",
        records_with_event(event_type, payload),
    )

    with pytest.raises((TypeError, ValueError), match=message):
        read_journal(path)


def test_read_journal_rejects_scenario_identity_and_bar_count_mismatch(
    tmp_path: Path,
) -> None:
    scenario = scenario_from_json(scenario_document())
    records = journal_records()
    for record in records:
        record["run_id"] = "other-run"
    path = write_journal(tmp_path / "run-id.jsonl", records)
    with pytest.raises(ValueError, match="scenario and journal run_id differ"):
        read_journal(path, scenario=scenario)

    path = write_journal(tmp_path / "bar-count.jsonl", lifecycle_records())
    with pytest.raises(ValueError, match="scenario and journal bar counts differ"):
        read_journal(path, scenario=scenario)


def test_read_journal_rejects_empty_and_invalid_json_documents(tmp_path: Path) -> None:
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="must not be empty"):
        read_journal(empty)

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text("{\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid journal JSON"):
        read_journal(invalid)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_completion", "must end with one run_completed"),
        ("sequence_gap", "engine_sequence must be contiguous"),
        ("blank_record", "must not contain blank records"),
        ("unknown_event", "unsupported journal event_type"),
    ],
)
def test_read_journal_rejects_incomplete_or_malformed_streams(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    records = deepcopy(journal_records())
    path = tmp_path / f"{mutation}.jsonl"
    if mutation == "missing_completion":
        records.pop()
        write_journal(path, records)
    elif mutation == "sequence_gap":
        records[1]["engine_sequence"] = "3"
        write_journal(path, records)
    elif mutation == "unknown_event":
        records[1]["event_type"] = "unknown"
        write_journal(path, records)
    else:
        write_journal(path, records)
        path.write_text(path.read_text() + "\n")

    with pytest.raises(ValueError, match=message):
        read_journal(path)
