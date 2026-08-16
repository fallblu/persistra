"""Tests for the typed external strategy protocol boundary."""

from __future__ import annotations

import json
import math
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pytest

from persistra.integrations.trading_engine import (
    CancelOrderIntent,
    EmitMetricIntent,
    FillReceivedEvent,
    IntentRejectedEvent,
    MarketSliceClosedEvent,
    OrderUpdatedEvent,
    StrategyArtifact,
    StrategyContext,
    StrategyDecision,
    StrategyIdentity,
    StrategyInitialization,
    StrategyProcess,
    StrategyProtocolError,
    StrategyRunResult,
    SubmitOrderIntent,
    TargetQuantitiesIntent,
    TargetQuantity,
    TargetWeight,
    TargetWeightsIntent,
    read_strategy_transcript,
    serve_strategy,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.integrations.trading_engine import ScenarioIntent, StrategyEvent


class RecordingStrategy:
    """Capture typed callbacks and return every supported intent shape."""

    name = "unit-strategy"
    version: str | None = "1.2.3"

    def __init__(self) -> None:
        self.initialization: StrategyInitialization | None = None
        self.events: list[tuple[StrategyContext, StrategyEvent]] = []
        self.stopped = False

    def initialize(self, initialization: StrategyInitialization) -> None:
        self.initialization = initialization

    def on_event(
        self,
        context: StrategyContext,
        event: StrategyEvent,
    ) -> Sequence[ScenarioIntent]:
        self.events.append((context, event))
        if len(self.events) != 1:
            return ()
        return (
            TargetWeightsIntent((TargetWeight("asset-a", "0.5"),)),
            TargetQuantitiesIntent((TargetQuantity("asset-a", "2"),)),
            SubmitOrderIntent("asset-a", "buy", "1", "limit", "99"),
            CancelOrderIntent("run-order-000000000001"),
            EmitMetricIntent("signal", "2"),
        )

    def shutdown(self) -> None:
        self.stopped = True


def _message(sequence: int, message_type: str, payload: object) -> dict[str, object]:
    return {
        "strategy_protocol_version": "2",
        "strategy_sequence": str(sequence),
        "message_type": message_type,
        "payload": payload,
    }


def _initialization() -> dict[str, object]:
    return {
        "engine_version": "test-engine-1",
        "scenario_contract_version": "3",
        "scenario_sha256": "a" * 64,
        "run_id": "run",
        "base_currency": "USD",
        "initial_cash": [{"currency": "USD", "amount": "10000"}],
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
            "participation_bps": 10000,
            "fixed_fee": "0",
            "fee_bps": 0,
        },
        "metadata": {"experiment": "external"},
    }


def _bar() -> dict[str, object]:
    return {
        "instrument_id": "asset-a",
        "open": "99",
        "high": "102",
        "low": "98",
        "close": "101",
        "volume": "100",
    }


def _market_slice() -> dict[str, object]:
    return {
        "slice_sequence": "1",
        "start_at": "2026-01-02T14:30:00.000000Z",
        "end_at": "2026-01-02T14:35:00.000000Z",
        "available_at": "2026-01-02T14:35:01.000000Z",
        "received_at": "2026-01-02T14:35:02.000000Z",
        "bars": [_bar()],
        "fx_rates": [{"currency": "USD", "rate": "1"}],
        "corporate_actions": [],
    }


def _order() -> dict[str, object]:
    return {
        "order_id": "run-order-000000000001",
        "instrument_id": "asset-a",
        "side": "buy",
        "quantity": "2",
        "order_kind": "market",
        "limit_price": None,
        "origin": "target_rebalance",
        "created_event_id": "run-event-000000000005",
        "updated_event_id": "run-event-000000000005",
        "created_sequence": "5",
        "created_at": "2026-01-02T14:35:02.000000Z",
        "eligible_after_slice_sequence": "1",
        "filled_quantity": "0",
        "filled_notional": "0",
        "status": "working",
        "rejection_reason": None,
    }


def _fill() -> dict[str, object]:
    return {
        "fill_id": "run-fill-000000000001",
        "order_id": "run-order-000000000001",
        "instrument_id": "asset-a",
        "quote_currency": "USD",
        "side": "buy",
        "quantity": "2",
        "price": "101",
        "notional": "202",
        "fee": "0.25",
        "executed_at": "2026-01-02T14:35:00.000000Z",
        "slice_sequence": "1",
    }


def _context() -> dict[str, object]:
    return {
        "now": "2026-01-02T14:35:02.000000Z",
        "portfolio": {
            "base_currency": "USD",
            "cash": "10000",
            "net_market_value": "0",
            "long_market_value": "0",
            "short_market_value": "0",
            "gross_exposure": "0",
            "equity": "10000",
            "weights_available": True,
            "cash_weight": "1",
            "cash_balances": [
                {
                    "currency": "USD",
                    "amount": "10000",
                    "fx_rate": "1",
                    "base_value": "10000",
                }
            ],
            "positions": [
                {
                    "instrument_id": "asset-a",
                    "quantity": "0",
                    "mark": "101",
                    "base_market_value": "0",
                    "weight": "0",
                }
            ],
        },
        "working_orders": [_order()],
        "latest_bars": [_bar()],
    }


def _requests() -> list[dict[str, object]]:
    events = [
        {"type": "market_slice_closed", "market_slice": _market_slice()},
        {"type": "order_updated", "order": _order()},
        {"type": "fill_received", "fill": _fill()},
        {"type": "intent_rejected", "reason": "risk limit"},
    ]
    requests = [_message(1, "initialize", _initialization())]
    requests.extend(
        _message(index, "event", {"context": _context(), "event": event})
        for index, event in enumerate(events, start=2)
    )
    requests.append(_message(6, "shutdown", {}))
    return requests


def _serve(
    strategy: RecordingStrategy,
    requests: list[dict[str, object]],
) -> list[dict[str, object]]:
    source = StringIO("".join(f"{json.dumps(item)}\n" for item in requests))
    sink = StringIO()
    serve_strategy(strategy, input_stream=source, output_stream=sink)
    return [cast("dict[str, object]", json.loads(line)) for line in sink.getvalue().splitlines()]


def test_serve_strategy_decodes_typed_events_and_encodes_all_intents() -> None:
    strategy = RecordingStrategy()
    responses = _serve(strategy, _requests())

    assert strategy.initialization is not None
    assert strategy.initialization.run_id == "run"
    assert strategy.initialization.metadata == {"experiment": "external"}
    with pytest.raises(TypeError):
        strategy.initialization.metadata["changed"] = True  # type: ignore[index]
    assert [type(event) for _, event in strategy.events] == [
        MarketSliceClosedEvent,
        OrderUpdatedEvent,
        FillReceivedEvent,
        IntentRejectedEvent,
    ]
    portfolio = strategy.events[0][0].portfolio
    assert portfolio.positions[0].quantity == 0
    assert portfolio.cash_weight == 1
    assert portfolio.position("asset-a").mark == 101
    assert strategy.events[1][0].working_orders[0].order_id == "run-order-000000000001"
    assert isinstance(strategy.events[2][1], FillReceivedEvent)
    assert strategy.events[2][1].fill.fee == Decimal("0.25")
    assert strategy.stopped
    assert [item["message_type"] for item in responses] == [
        "ready",
        "intents",
        "intents",
        "intents",
        "intents",
        "stopped",
    ]
    assert [item["strategy_sequence"] for item in responses] == [str(i) for i in range(1, 7)]
    payload = cast("dict[str, Any]", responses[1]["payload"])
    intents = cast("list[dict[str, object]]", payload["intents"])
    assert [item["type"] for item in intents] == [
        "target_weights",
        "target_quantities",
        "submit_order",
        "cancel_order",
        "emit_metric",
    ]


def _transcript_records() -> list[dict[str, object]]:
    requests = _requests()
    responses = _serve(RecordingStrategy(), requests)
    records: list[dict[str, object]] = []
    for request, response in zip(requests, responses, strict=True):
        records.extend(
            [
                {
                    "strategy_protocol_version": "2",
                    "transcript_sequence": str(len(records) + 1),
                    "direction": "engine_to_strategy",
                    "message": request,
                },
                {
                    "strategy_protocol_version": "2",
                    "transcript_sequence": str(len(records) + 2),
                    "direction": "strategy_to_engine",
                    "message": response,
                },
            ]
        )
    return records


def test_read_strategy_transcript_validates_pairing_identity_and_events(tmp_path: Path) -> None:
    records = _transcript_records()
    path = tmp_path / "strategy.jsonl"
    path.write_text("".join(f"{json.dumps(item)}\n" for item in records), encoding="utf-8")

    transcript = read_strategy_transcript(path, scenario_sha256="a" * 64, run_id="run")

    assert transcript.path == path.resolve()
    assert transcript.identity.name == "unit-strategy"
    assert transcript.identity.version == "1.2.3"
    assert transcript.record_count == 12
    assert transcript.event_count == 4
    assert len(transcript.decisions) == 1
    assert transcript.decisions[0].after_slice_sequence == 1
    assert len(transcript.decisions[0].intents) == 5

    records[3]["direction"] = "engine_to_strategy"
    path.write_text("".join(f"{json.dumps(item)}\n" for item in records), encoding="utf-8")
    with pytest.raises(StrategyProtocolError, match="wrong direction"):
        read_strategy_transcript(path)


def test_transcript_does_not_infer_a_slice_for_events_without_one(tmp_path: Path) -> None:
    records = _transcript_records()
    market_response = cast("dict[str, Any]", records[3]["message"])
    order_response = cast("dict[str, Any]", records[5]["message"])
    market_payload = cast("dict[str, Any]", market_response["payload"])
    order_payload = cast("dict[str, Any]", order_response["payload"])
    order_payload["intents"] = market_payload["intents"]
    market_payload["intents"] = []
    path = tmp_path / "strategy.jsonl"
    path.write_text("".join(f"{json.dumps(item)}\n" for item in records), encoding="utf-8")

    transcript = read_strategy_transcript(path)

    assert len(transcript.decisions) == 1
    assert transcript.decisions[0].after_slice_sequence is None


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("strategy_protocol_version", "1", "unsupported"),
        ("strategy_sequence", "2", "expected strategy sequence"),
        ("message_type", "shutdown", "must be initialize"),
        ("extra", True, "fields differ"),
    ],
)
def test_serve_strategy_rejects_invalid_requests_with_error_response(
    field: str,
    value: object,
    message: str,
) -> None:
    request = _message(1, "initialize", _initialization())
    request[field] = value
    if field == "message_type":
        request["payload"] = {}
    sink = StringIO()
    with pytest.raises(StrategyProtocolError, match=message):
        serve_strategy(
            RecordingStrategy(),
            input_stream=StringIO(f"{json.dumps(request)}\n"),
            output_stream=sink,
        )
    response = json.loads(sink.getvalue())
    assert response["message_type"] == "error"
    assert response["strategy_sequence"] == "1"


def test_serve_strategy_reports_nested_payload_errors_in_band() -> None:
    requests = _requests()[:2]
    event_payload = cast("dict[str, object]", requests[1]["payload"])
    event_payload["unexpected"] = True
    source = StringIO("".join(f"{json.dumps(item)}\n" for item in requests))
    sink = StringIO()

    with pytest.raises(StrategyProtocolError, match="event payload fields differ"):
        serve_strategy(RecordingStrategy(), input_stream=source, output_stream=sink)

    responses = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [response["message_type"] for response in responses] == ["ready", "error"]
    assert responses[-1]["strategy_sequence"] == "2"


def test_serve_strategy_converts_callback_failures_to_protocol_errors() -> None:
    class BrokenStrategy(RecordingStrategy):
        def initialize(self, initialization: StrategyInitialization) -> None:
            raise RuntimeError("configuration rejected")

    sink = StringIO()
    request = _message(1, "initialize", _initialization())
    with pytest.raises(StrategyProtocolError, match="configuration rejected"):
        serve_strategy(
            BrokenStrategy(),
            input_stream=StringIO(f"{json.dumps(request)}\n"),
            output_stream=sink,
        )
    response = json.loads(sink.getvalue())
    assert response["message_type"] == "error"
    assert "RuntimeError" in response["payload"]["message"]


def test_strategy_process_normalizes_command_and_rejects_unsafe_values(tmp_path: Path) -> None:
    script = tmp_path / "strategy.py"
    process = StrategyProcess(
        command=(Path("python"), script, "--mode=unit"),
        artifacts=(script,),
        response_timeout=2,
    )
    assert process.command == ("python", str(script), "--mode=unit")
    assert process.response_timeout == 2.0
    with pytest.raises(ValueError, match="must not be empty"):
        StrategyProcess(command=())
    with pytest.raises(ValueError, match="positive finite"):
        StrategyProcess(command=("python",), response_timeout=0)
    with pytest.raises(TypeError, match="artifacts must be a tuple"):
        StrategyProcess(command=("python",), artifacts=[script])  # type: ignore[arg-type]


def test_strategy_value_models_reject_invalid_runtime_construction(tmp_path: Path) -> None:
    strategy = RecordingStrategy()
    _serve(strategy, _requests())
    assert strategy.initialization is not None
    initialization = strategy.initialization
    context = strategy.events[0][0]
    order = context.working_orders[0]
    fill_event = strategy.events[2][1]
    assert isinstance(fill_event, FillReceivedEvent)
    fill = fill_event.fill

    assert StrategyIdentity("anonymous", None).version is None
    artifact = StrategyArtifact(tmp_path / "input", "b" * 64)
    result = StrategyRunResult(
        identity=StrategyIdentity("unit", "1"),
        executable=tmp_path / "python",
        executable_sha256="a" * 64,
        artifacts=(artifact,),
        transcript_path=tmp_path / "transcript.jsonl",
        transcript_sha256="c" * 64,
        event_count=0,
        response_timeout=1,
    )
    assert result.response_timeout == 1.0
    with pytest.raises(TypeError, match="result artifacts must be a tuple"):
        replace(result, artifacts=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive finite"):
        replace(result, response_timeout=math.nan)
    with pytest.raises(ValueError, match="positive finite"):
        replace(result, response_timeout=0)
    with pytest.raises(ValueError, match="nonnegative"):
        replace(result, event_count=-1)
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        StrategyArtifact(tmp_path / "input", "invalid")

    frozen = replace(initialization, metadata={"nested": [1, {"ratio": 1.5}]})
    assert frozen.metadata["nested"] == (1, {"ratio": 1.5})
    with pytest.raises(ValueError, match="initial_cash must not be empty"):
        replace(initialization, initial_cash=())
    with pytest.raises(ValueError, match="instruments must not be empty"):
        replace(initialization, instruments=())
    with pytest.raises(TypeError, match="initial_cash must be a tuple"):
        replace(initialization, initial_cash=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="metadata must be a mapping"):
        replace(initialization, metadata=cast("Any", []))
    with pytest.raises(TypeError, match="metadata keys must be strings"):
        replace(initialization, metadata=cast("Any", {1: "invalid"}))
    with pytest.raises(TypeError, match="JSON-compatible"):
        replace(initialization, metadata={"invalid": object()})

    assert replace(order, order_kind="limit", limit_price="99").limit_price == 99
    rejected = replace(order, status="rejected", rejection_reason="risk limit")
    assert rejected.rejection_reason == "risk limit"
    invalid_orders = [
        ({"side": cast("Any", "hold")}, "side must"),
        ({"order_kind": cast("Any", "stop")}, "order_kind"),
        ({"origin": cast("Any", "unknown")}, "origin"),
        ({"status": cast("Any", "unknown")}, "status"),
        ({"filled_quantity": "3"}, "must not exceed"),
        ({"limit_price": "99"}, "limit_price must be null"),
        ({"order_kind": "limit", "limit_price": None}, "limit_price must be null"),
        ({"rejection_reason": "risk"}, "present exactly"),
        ({"status": "rejected"}, "present exactly"),
    ]
    for changes, message in invalid_orders:
        with pytest.raises(ValueError, match=message):
            replace(order, **changes)
    with pytest.raises(TypeError, match="pandas Timestamp"):
        replace(order, created_at=cast("Any", "2026-01-01T00:00:00Z"))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(order, created_at=pd.Timestamp("2026-01-01"))

    with pytest.raises(ValueError, match="side must"):
        replace(fill, side=cast("Any", "hold"))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(fill, executed_at=pd.Timestamp("2026-01-01"))
    with pytest.raises(ValueError, match="cash_balances must not be empty"):
        replace(context.portfolio, cash_balances=())
    with pytest.raises(ValueError, match="positions must not be empty"):
        replace(context.portfolio, positions=())
    with pytest.raises(ValueError, match="weights require positive"):
        replace(context.portfolio, equity="0")
    without_weights = replace(
        context.portfolio,
        cash="0",
        equity="0",
        weights_available=False,
        cash_weight=None,
        cash_balances=(replace(context.portfolio.cash_balances[0], amount="0", base_value="0"),),
        positions=(replace(context.portfolio.positions[0], weight=None),),
    )
    assert not without_weights.weights_available
    with pytest.raises(KeyError, match="missing"):
        context.portfolio.position("missing")
    with pytest.raises(TypeError, match="latest_bars must be a tuple"):
        replace(context, latest_bars=[])  # type: ignore[arg-type]

    decision = StrategyDecision(None, (EmitMetricIntent("signal", "1"),))
    assert decision.after_slice_sequence is None
    with pytest.raises(ValueError, match="must not be empty"):
        StrategyDecision(1, ())
    with pytest.raises(TypeError, match="must be a tuple"):
        StrategyDecision(1, cast("Any", []))


def test_serve_strategy_rejects_callback_results_shutdown_and_large_messages() -> None:
    class InvalidResultStrategy(RecordingStrategy):
        result: object

        def __init__(self, result: object) -> None:
            super().__init__()
            self.result = result

        def on_event(
            self,
            context: StrategyContext,
            event: StrategyEvent,
        ) -> Sequence[ScenarioIntent]:
            del context, event
            return cast("Any", self.result)

    first_event = _requests()[:2]
    for result in ("invalid", [object()]):
        sink = StringIO()
        with pytest.raises(StrategyProtocolError, match="on_event"):
            serve_strategy(
                InvalidResultStrategy(result),
                input_stream=StringIO("".join(f"{json.dumps(item)}\n" for item in first_event)),
                output_stream=sink,
            )
        assert json.loads(sink.getvalue().splitlines()[-1])["message_type"] == "error"

    class BrokenShutdownStrategy(RecordingStrategy):
        def shutdown(self) -> None:
            raise RuntimeError("shutdown failed")

    requests = [_message(1, "initialize", _initialization()), _message(2, "shutdown", {})]
    with pytest.raises(StrategyProtocolError, match="shutdown failed"):
        _serve(BrokenShutdownStrategy(), requests)

    unexpected = [
        _message(1, "initialize", _initialization()),
        _message(2, "initialize", _initialization()),
    ]
    with pytest.raises(StrategyProtocolError, match="event or shutdown"):
        _serve(RecordingStrategy(), unexpected)

    class OversizedStrategy(RecordingStrategy):
        def on_event(
            self,
            context: StrategyContext,
            event: StrategyEvent,
        ) -> Sequence[ScenarioIntent]:
            del context, event
            return (EmitMetricIntent("large", "x" * 1_048_576),)

    with pytest.raises(StrategyProtocolError, match="response exceeds"):
        _serve(OversizedStrategy(), first_event)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        ("", "closed strategy input"),
        ("not-json\n", "invalid strategy protocol JSON"),
        (
            '{"strategy_protocol_version":"2","strategy_protocol_version":"2"}\n',
            "duplicate JSON field",
        ),
        ("é" * 600_000, "maximum message size"),
    ],
)
def test_serve_strategy_rejects_malformed_or_oversized_input(
    document: str,
    message: str,
) -> None:
    with pytest.raises(StrategyProtocolError, match=message):
        serve_strategy(
            RecordingStrategy(),
            input_stream=StringIO(document),
            output_stream=StringIO(),
        )


def test_read_strategy_transcript_rejects_lifecycle_and_binding_failures(tmp_path: Path) -> None:
    path = tmp_path / "strategy.jsonl"

    def write(records: list[dict[str, object]]) -> None:
        path.write_text(
            "".join(f"{json.dumps(item)}\n" for item in records),
            encoding="utf-8",
        )

    valid = _transcript_records()
    write(valid)
    with pytest.raises(StrategyProtocolError, match="scenario SHA-256 does not match"):
        read_strategy_transcript(path, scenario_sha256="f" * 64)
    with pytest.raises(StrategyProtocolError, match="run_id does not match"):
        read_strategy_transcript(path, run_id="different")

    cases: list[tuple[list[dict[str, object]], str]] = []
    cases.append(([], "must not be empty"))
    cases.append((deepcopy(valid[:1]), "outstanding request"))
    no_shutdown = deepcopy(valid[:-2])
    cases.append((no_shutdown, "missing shutdown"))

    wrong_version = deepcopy(valid)
    wrong_version[0]["strategy_protocol_version"] = "1"
    cases.append((wrong_version, "transcript protocol version"))
    wrong_record_sequence = deepcopy(valid)
    wrong_record_sequence[0]["transcript_sequence"] = "2"
    cases.append((wrong_record_sequence, "expected transcript sequence"))
    wrong_message_sequence = deepcopy(valid)
    cast("dict[str, Any]", wrong_message_sequence[0]["message"])["strategy_sequence"] = "2"
    cases.append((wrong_message_sequence, "message sequence must be"))
    wrong_first = deepcopy(valid)
    first_message = cast("dict[str, Any]", wrong_first[0]["message"])
    first_message["message_type"] = "shutdown"
    first_message["payload"] = {}
    cases.append((wrong_first, "must start with initialize"))
    unsupported_request = deepcopy(valid)
    unsupported_message = cast("dict[str, Any]", unsupported_request[2]["message"])
    unsupported_message["message_type"] = "unknown"
    unsupported_message["payload"] = {}
    cases.append((unsupported_request, "unsupported engine request"))
    wrong_ready = deepcopy(valid)
    ready_message = cast("dict[str, Any]", wrong_ready[1]["message"])
    ready_message["message_type"] = "intents"
    ready_message["payload"] = {"intents": []}
    cases.append((wrong_ready, "initialize request must be followed by ready"))
    wrong_intents = deepcopy(valid)
    event_response = cast("dict[str, Any]", wrong_intents[3]["message"])
    event_response["message_type"] = "ready"
    event_response["payload"] = {
        "strategy_name": "unit-strategy",
        "strategy_version": "1",
    }
    cases.append((wrong_intents, "event request must be followed by intents"))
    wrong_stopped = deepcopy(valid)
    stopped_message = cast("dict[str, Any]", wrong_stopped[-1]["message"])
    stopped_message["message_type"] = "intents"
    stopped_message["payload"] = {"intents": []}
    cases.append((wrong_stopped, "shutdown request must be followed by stopped"))
    error_response = deepcopy(valid)
    response = cast("dict[str, Any]", error_response[3]["message"])
    response["message_type"] = "error"
    response["payload"] = {"message": "strategy failed"}
    cases.append((error_response, "contains an error response"))
    nonobject_message = deepcopy(valid)
    nonobject_message[0]["message"] = []
    cases.append((nonobject_message, "strategy message must be a JSON object"))

    after_shutdown = deepcopy(valid)
    late_request = deepcopy(cast("dict[str, Any]", valid[2]["message"]))
    late_response = deepcopy(cast("dict[str, Any]", valid[3]["message"]))
    late_request["strategy_sequence"] = "7"
    late_response["strategy_sequence"] = "7"
    after_shutdown.extend(
        [
            {
                "strategy_protocol_version": "2",
                "transcript_sequence": "13",
                "direction": "engine_to_strategy",
                "message": late_request,
            },
            {
                "strategy_protocol_version": "2",
                "transcript_sequence": "14",
                "direction": "strategy_to_engine",
                "message": late_response,
            },
        ]
    )
    cases.append((after_shutdown, "data after shutdown"))

    for records, message in cases:
        write(records)
        with pytest.raises(StrategyProtocolError, match=message):
            read_strategy_transcript(path)


def test_read_strategy_transcript_rejects_invalid_json_and_size(tmp_path: Path) -> None:
    path = tmp_path / "strategy.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(StrategyProtocolError, match="invalid JSON"):
        read_strategy_transcript(path)
    path.write_text('{"duplicate":1,"duplicate":2}\n', encoding="utf-8")
    with pytest.raises(StrategyProtocolError, match="duplicate JSON field"):
        read_strategy_transcript(path)
    path.write_bytes(b"x" * (2_097_152 + 1))
    with pytest.raises(StrategyProtocolError, match="maximum size"):
        read_strategy_transcript(path)
    with pytest.raises(ValueError, match="not a regular file"):
        read_strategy_transcript(tmp_path)
