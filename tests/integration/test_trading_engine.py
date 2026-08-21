"""Exercise Persistra against a real Trading Engine executable and its schemas."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pandas as pd
import pytest
from jsonschema import FormatChecker
from jsonschema.validators import validator_for
from referencing import Registry, Resource

from persistra.data import synthetic
from persistra.integrations.trading_engine import (
    BarClockPolicy,
    CashBalance,
    CashDividendAction,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
    SplitAction,
    StrategyProcess,
    analyze_execution,
    build_scenario,
    compare_execution,
    read_journal,
    read_scenario,
    run_scenario,
)
from persistra.model import BarSet
from persistra.portfolio import BacktestTiming, backtest_portfolio, construct_portfolio

if TYPE_CHECKING:
    from collections.abc import Callable

    from jsonschema.protocols import Validator

    from persistra.integrations.trading_engine import (
        ExecutionReplayResult,
        TradingEngineScenario,
    )
    from persistra.portfolio import BacktestResult

_BINARY = os.environ.get("PERSISTRA_TRADING_ENGINE_BINARY")
_CONTRACT_DIRECTORY = os.environ.get("PERSISTRA_TRADING_ENGINE_CONTRACT_DIR")

pytestmark = pytest.mark.skipif(
    not _BINARY or not _CONTRACT_DIRECTORY,
    reason="real Trading Engine integration requires its binary and v3 contract directory",
)


def test_replay_is_deterministic_and_conforms_to_engine_schemas(tmp_path: Path) -> None:
    """Replay a margin-limited target twice and validate every persisted artifact."""
    assert _BINARY is not None
    assert _CONTRACT_DIRECTORY is not None
    binary = Path(_BINARY).resolve(strict=True)
    contract_directory = Path(_CONTRACT_DIRECTORY).resolve(strict=True)
    scenario = _margin_limited_scenario()

    first = run_scenario(
        scenario,
        executable=binary,
        output_directory=tmp_path / "first",
    )
    second = run_scenario(
        scenario,
        executable=binary,
        output_directory=tmp_path / "second",
    )

    assert first.scenario_path.read_bytes() == second.scenario_path.read_bytes()
    assert first.journal_path.read_bytes() == second.journal_path.read_bytes()
    assert first.manifest_path.read_bytes() == second.manifest_path.read_bytes()
    assert first.scenario_sha256 == second.scenario_sha256
    assert first.journal_sha256 == second.journal_sha256
    assert first.executable_sha256 == second.executable_sha256
    assert first.manifest_path.is_file()
    assert second.manifest_path.is_file()

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == scenario.run_id
    assert manifest["contract"] == {"version": "3"}
    assert manifest["execution"] == {"model": "completed_bar_v1"}
    assert manifest["engine"]["version"] == first.capabilities.engine_version
    assert manifest["engine"]["capabilities"] == {
        "engine_version": first.capabilities.engine_version,
        "scenario_contract_versions": list(first.capabilities.scenario_contract_versions),
        "journal_contract_versions": list(first.capabilities.journal_contract_versions),
        "scenario_formats": list(first.capabilities.scenario_formats),
        "journal_formats": list(first.capabilities.journal_formats),
        "execution_models": list(first.capabilities.execution_models),
        "strategy_protocol_versions": list(first.capabilities.strategy_protocol_versions),
    }
    assert manifest["engine"]["executable"] == {
        "name": binary.name,
        "sha256": first.executable_sha256,
    }
    assert set(manifest["engine"]["vcs"]) == {"revision", "dirty"}
    assert set(manifest["persistra"]["vcs"]) == {"revision", "dirty"}
    assert manifest["artifacts"] == {
        "scenario": {
            "path": first.scenario_path.name,
            "sha256": first.scenario_sha256,
            "format": "jsonl",
        },
        "journal": {
            "path": first.journal_path.name,
            "sha256": first.journal_sha256,
        },
    }

    scenario_schema_path = contract_directory / "scenario.schema.json"
    stream_validator = _validator(
        contract_directory / "scenario-stream.schema.json",
        references=(scenario_schema_path,),
    )
    journal_validator = _validator(contract_directory / "journal.schema.json")
    scenario_records = [
        json.loads(line) for line in first.scenario_path.read_text(encoding="utf-8").splitlines()
    ]
    assert scenario_records[0]["record_type"] == "scenario_header"
    assert scenario_records[-1]["record_type"] == "scenario_end"
    assert manifest["scenario_metadata"] == scenario_records[0]["payload"]["metadata"]
    for record in scenario_records:
        assert record["contract_version"] == "3"
        stream_validator.validate(record)
    records = [
        json.loads(line) for line in first.journal_path.read_text(encoding="utf-8").splitlines()
    ]
    assert records
    for record in records:
        assert record["contract_version"] == "3"
        journal_validator.validate(record)

    event_types = {event.event_type for event in first.replay.events}
    assert {"run_started", "margin_limited", "run_completed"} <= event_types
    assert not first.replay.margin_limits.empty
    assert first.replay.execution_model == "completed_bar_v1"
    assert first.replay.completion.scenario_sha256 == first.scenario_sha256
    assert first.replay.completion.execution_model == "completed_bar_v1"
    events_by_id = {event.event_id: event for event in first.replay.events}
    assert list(events_by_id) == [
        f"{scenario.run_id}-event-{sequence:012d}"
        for sequence in range(1, len(first.replay.events) + 1)
    ]
    for event in first.replay.events:
        assert event.causation_ids == tuple(sorted(event.causation_ids))
        assert all(
            events_by_id[cause].engine_sequence < event.engine_sequence
            for cause in event.causation_ids
        )
    assert set(first.replay.orders["created_event_id"]) <= set(events_by_id)

    assert not first.replay.positions.empty
    terminal_sequence = int(first.replay.valuations.iloc[-1]["slice_sequence"])
    terminal_positions = first.replay.positions.loc[
        first.replay.positions["slice_sequence"] == terminal_sequence
    ]
    for position_name, completion_name in (
        ("market_value", "net_market_value"),
        ("cost_basis", "cost_basis"),
        ("realized_pnl", "realized_pnl"),
        ("unrealized_pnl", "unrealized_pnl"),
        ("total_fees", "total_fees"),
    ):
        assert int(terminal_positions[f"base_{position_name}_micros"].sum()) == getattr(
            first.replay.completion, f"{completion_name}_micros"
        )


def test_external_strategy_protocol_replays_and_conforms_to_schemas(tmp_path: Path) -> None:
    """Host a Persistra strategy through the real engine and validate its transcript."""
    assert _BINARY is not None
    assert _CONTRACT_DIRECTORY is not None
    binary = Path(_BINARY).resolve(strict=True)
    contract_directory = Path(_CONTRACT_DIRECTORY).resolve(strict=True)
    strategy_directory = contract_directory.parent / "strategy" / "v3"
    strategy_script = Path(__file__).parents[1] / "fixtures" / "external_strategy.py"
    bars = _fixed_bars("EXTERNAL", (100, 103), currency="EUR")
    instrument_id = bars.instrument.instrument_id
    labels = pd.DatetimeIndex(bars.frame["timestamp"])
    fx_rates = pd.DataFrame(
        {"EUR": [1.10, 1.20], "USD": [1, 1]},
        index=labels,
    )
    scenario = build_scenario(
        [bars],
        instruments=[ExecutionInstrument(instrument_id, "EXTERNAL", "EUR", "0.01")],
        base_currency="USD",
        initial_cash=[CashBalance("EUR", 0), CashBalance("USD", 10_000)],
        fx_rates=fx_rates,
        clock_policy=_demo_clock(),
        sizing_policy=SizingPolicy(),
        risk=_risk(),
        execution=ExecutionPolicy(participation_bps=10_000, fixed_fee="0"),
        run_id="external-strategy-integration",
    )

    run = run_scenario(
        scenario,
        executable=binary,
        output_directory=tmp_path / "external-strategy",
        strategy=StrategyProcess(
            command=(sys.executable, strategy_script, "--fixture-mode"),
            artifacts=(strategy_script,),
            response_timeout=10,
        ),
    )

    assert run.strategy is not None
    assert run.strategy.identity.name == "persistra-fixture"
    assert run.strategy.identity.version == "1"
    assert run.strategy.event_count == 5
    assert run.replay.fills[["quantity", "price"]].values.tolist() == [[2.0, 103.0]]
    assert run.replay.metrics[["name", "value"]].values.tolist() == [["external_signal", "2"]]
    assert run.replay.positions.loc[
        run.replay.positions["slice_sequence"] == 2,
        "quantity",
    ].tolist() == [2.0]
    transcript_records = [
        json.loads(line)
        for line in run.strategy.transcript_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(transcript_records) == 14
    assert transcript_records[0]["message"]["message_type"] == "initialize"
    assert transcript_records[-1]["message"]["message_type"] == "stopped"
    fill_request = next(
        record["message"]
        for record in transcript_records
        if record["direction"] == "engine_to_strategy"
        and record["message"]["message_type"] == "event"
        and record["message"]["payload"]["event"]["type"] == "fill_received"
    )
    assert fill_request["strategy_protocol_version"] == "3"
    fill_context = fill_request["payload"]["context"]
    assert pd.Timestamp(fill_context["now"]) == scenario.slices[1].received_at
    assert Decimal(fill_context["latest_bars"][0]["close"]) == Decimal("103")
    marked_portfolio = fill_context["portfolio"]
    assert marked_portfolio["weights_available"] is True
    assert marked_portfolio["positions"][0]["quantity"] == "2"
    assert Decimal(marked_portfolio["positions"][0]["mark"]) == Decimal("103")
    assert Decimal(marked_portfolio["positions"][0]["base_market_value"]) == Decimal("247.2")
    assert marked_portfolio["positions"][0]["weight"] is not None
    eur_cash = next(
        balance for balance in marked_portfolio["cash_balances"] if balance["currency"] == "EUR"
    )
    assert Decimal(eur_cash["fx_rate"]) == Decimal("1.2")
    scenario_schema_path = contract_directory / "scenario.schema.json"
    journal_schema_path = contract_directory / "journal.schema.json"
    message_schema_path = strategy_directory / "message.schema.json"
    transcript_validator = _validator(
        strategy_directory / "transcript.schema.json",
        references=(scenario_schema_path, journal_schema_path, message_schema_path),
    )
    for record in transcript_records:
        transcript_validator.validate(record)


def test_engine_owned_v3_conformance_corpus_is_accepted() -> None:
    """Consume the engine's canonical scenario and journal without copied fixtures."""
    assert _CONTRACT_DIRECTORY is not None
    contract_directory = Path(_CONTRACT_DIRECTORY).resolve(strict=True)
    scenario_path = contract_directory / "fixtures/demo.scenario.json"
    journal_path = contract_directory / "fixtures/demo.journal.jsonl"

    scenario = read_scenario(scenario_path)
    replay = read_journal(journal_path, scenario=scenario_path)

    assert scenario.contract_version == "3"
    assert replay.contract_version == "3"
    assert replay.run_id == "demo"
    assert replay.execution_model == "completed_bar_v1"
    assert replay.completion.equity_micros == 10_004_768_120
    assert {event.contract_version for event in replay.events} == {"3"}
    assert replay.positions.loc[replay.positions["slice_sequence"] == 4, "quantity"].tolist() == [
        2.5
    ]


def test_multicurrency_short_corporate_actions_and_borrow_reconcile(tmp_path: Path) -> None:
    """Exercise FX ledgers, signed positions, actions, and borrow fees end to end."""
    assert _BINARY is not None
    run = run_scenario(
        _multicurrency_actions_scenario(),
        executable=Path(_BINARY),
        output_directory=tmp_path / "multicurrency-actions",
    )
    replay = run.replay

    assert set(replay.fx_rates["currency"]) == {"EUR", "USD"}
    assert set(replay.cash_balances["currency"]) == {"EUR", "USD"}
    assert replay.corporate_actions["action_type"].tolist() == [
        "cash_dividend",
        "split",
    ]
    dividend = replay.corporate_actions.iloc[0]
    split = replay.corporate_actions.iloc[1]
    assert dividend["quantity"] == -4
    assert dividend["cash_amount"] == -4
    assert split["previous_quantity"] == -4
    assert split["adjusted_quantity"] == -8
    assert len(replay.borrow_fees) == 2
    assert (replay.borrow_fees["fee_micros"] > 0).all()
    terminal_sequence = int(replay.valuations.iloc[-1]["slice_sequence"])
    terminal: pd.DataFrame = replay.positions.loc[
        replay.positions["slice_sequence"] == terminal_sequence
    ]
    assert terminal["quantity"].tolist() == [-8]
    assert replay.completion.short_market_value_micros > 0


def test_margin_call_forces_deterministic_liquidation_and_restoration(tmp_path: Path) -> None:
    """Exercise causal margin-call liquidation against the real engine."""
    assert _BINARY is not None
    run = run_scenario(
        _margin_call_scenario(),
        executable=Path(_BINARY),
        output_directory=tmp_path / "margin-call",
    )
    replay = run.replay

    assert replay.margin_events["event_type"].tolist() == [
        "margin_call",
        "margin_restored",
    ]
    liquidation = replay.orders.loc[replay.orders["origin"] == "margin_liquidation"]
    assert liquidation[["side", "quantity"]].values.tolist() == [["buy", 10]]
    assert replay.positions.loc[replay.positions["slice_sequence"] == 4, "quantity"].tolist() == [0]
    assert replay.completion.active_orders == 0
    assert replay.completion.gross_exposure_micros == 0


def test_quantity_replay_acceptance_case(tmp_path: Path) -> None:
    """Keep the standalone quantity demo's executable outcomes under CI."""
    assert _BINARY is not None
    run = run_scenario(
        _quantity_scenario(),
        executable=Path(_BINARY),
        output_directory=tmp_path / "quantity",
    )
    analysis = analyze_execution(run.replay)

    assert len(run.replay.orders) == 7
    assert len(run.replay.fills) == 7
    assert int(run.replay.fills["quantity"].sum()) == 36
    assert run.replay.completion.total_fees_micros == 5_282_840
    assert run.replay.completion.equity_micros == 9_912_317_160
    assert analysis.lifecycle_summary.loc["engine", "accepted_orders"] == 7


def test_portfolio_comparison_acceptance_case(tmp_path: Path) -> None:
    """Keep the standalone portfolio demo's execution bridge under CI."""
    assert _BINARY is not None
    scenario, vectorized = _portfolio_comparison_case()
    run = run_scenario(
        scenario,
        executable=Path(_BINARY),
        output_directory=tmp_path / "portfolio",
    )
    comparison = compare_execution(vectorized, analyze_execution(run.replay))

    assert run.replay.completion.equity_micros == 9_987_024_150
    assert comparison.terminal_summary.loc[
        "vectorized_close_to_close", "terminal_equity"
    ] == pytest.approx(10_188.13704436345)
    assert comparison.pnl_bridge.loc["decision_to_fill_slice_open_timing", "pnl"] == pytest.approx(
        -116.61
    )
    assert comparison.pnl_bridge.loc["engine_fees", "pnl"] == pytest.approx(-80.30585)
    assert comparison.pnl_bridge.loc[
        "unfilled_exposure_and_model_residual", "pnl"
    ] == pytest.approx(-4.197044363450516)


def test_replay_rejects_a_journal_changed_after_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never publish or manifest bytes that differ from the imported journal."""
    assert _BINARY is not None
    runner = import_module("persistra.integrations.trading_engine.runner")
    read_journal = cast(
        "Callable[..., ExecutionReplayResult]",
        vars(runner)["read_journal"],
    )

    def read_then_change(path: str | Path, **kwargs: object) -> ExecutionReplayResult:
        replay = read_journal(path, **kwargs)
        Path(path).write_text("changed after reconciliation\n", encoding="utf-8")
        return replay

    monkeypatch.setattr(runner, "read_journal", read_then_change)
    output = tmp_path / "changed-journal"
    with pytest.raises(ValueError, match="changed during reconciliation"):
        run_scenario(
            _margin_limited_scenario(),
            executable=Path(_BINARY),
            output_directory=output,
        )

    assert not (output / "margin-limited-integration.journal.jsonl").exists()
    assert not (output / "margin-limited-integration.manifest.json").exists()


def _margin_limited_scenario() -> TradingEngineScenario:
    bars = _execution_bars()
    instrument_id = bars.instrument.instrument_id
    targets = pd.DataFrame(
        {instrument_id: [1.0]},
        index=pd.DatetimeIndex([bars.frame.loc[0, "timestamp"]]),
    )
    return build_scenario(
        [bars],
        targets,
        instruments=[ExecutionInstrument(instrument_id, "CASH", "USD", "0.01")],
        base_currency="USD",
        initial_cash=[CashBalance("USD", "10000")],
        clock_policy=BarClockPolicy(
            source_timestamp_position="start",
            bar_duration=timedelta(minutes=5),
            availability_delay=timedelta(0),
            receipt_delay=timedelta(0),
        ),
        sizing_policy=SizingPolicy(),
        risk=_risk(max_leverage=1),
        execution=ExecutionPolicy(
            participation_bps=10_000,
            fixed_fee="0.25",
            fee_bps=0,
        ),
        run_id="margin-limited-integration",
    )


def _quantity_scenario() -> TradingEngineScenario:
    bars = _demo_bars("QTY", periods=8, seed=17, volume=12)
    instrument_id = bars.instrument.instrument_id
    targets = pd.DataFrame(
        {instrument_id: [20, 8, 0]},
        index=bars.frame.loc[[0, 3, 5], "timestamp"],
    )
    return build_scenario(
        [bars],
        target_quantities=targets,
        instruments=[ExecutionInstrument(instrument_id, "QTY", "USD", "0.01")],
        base_currency="USD",
        initial_cash=[CashBalance("USD", "10000")],
        clock_policy=_demo_clock(),
        sizing_policy=SizingPolicy(),
        risk=_risk(),
        execution=ExecutionPolicy(
            participation_bps=5_000,
            fixed_fee="0.25",
            fee_bps=10,
        ),
        run_id="quantity-replay",
    )


def _portfolio_comparison_case() -> tuple[TradingEngineScenario, BacktestResult]:
    first = _demo_bars("ALPHA", periods=12, seed=21, volume=100_000)
    second = _demo_bars("BETA", periods=12, seed=34, volume=100_000)
    first_id = first.instrument.instrument_id
    second_id = second.instrument.instrument_id
    timestamps = pd.DatetimeIndex(first.frame["timestamp"])
    signals = pd.DataFrame(
        {
            first_id: np.where(np.arange(len(timestamps) - 1) % 3 == 0, 2.0, 0.5),
            second_id: np.where(np.arange(len(timestamps) - 1) % 3 == 0, 0.5, 2.0),
        },
        index=timestamps[:-1],
    )
    portfolio = construct_portfolio(
        signals,
        weighting="signal_proportional",
        configuration="long_only",
        gross_target=0.80,
    )
    prices = pd.DataFrame(
        {
            first_id: first.frame.set_index("timestamp")["close"],
            second_id: second.frame.set_index("timestamp")["close"],
        },
        index=timestamps,
    )
    vectorized = backtest_portfolio(
        portfolio,
        prices=prices,
        timing=BacktestTiming(decision_lag=0, execution_lag=1),
        transaction_cost_bps=0.0,
        initial_equity=10_000,
    )
    scenario = build_scenario(
        [second, first],
        portfolio,
        instruments=[
            ExecutionInstrument(first_id, "ALPHA", "USD", "0.01"),
            ExecutionInstrument(second_id, "BETA", "USD", "0.01"),
        ],
        base_currency="USD",
        initial_cash=[CashBalance("USD", "10000")],
        clock_policy=_demo_clock(),
        sizing_policy=SizingPolicy(),
        risk=_risk(max_order_quantity=10_000, max_position=10_000),
        execution=ExecutionPolicy(
            participation_bps=10_000,
            fixed_fee="0.25",
            fee_bps=10,
        ),
        run_id="portfolio-comparison",
    )
    return scenario, vectorized


def _multicurrency_actions_scenario() -> TradingEngineScenario:
    bars = _fixed_bars("EURSHORT", (100, 100, 99, 49.5), currency="EUR")
    instrument_id = bars.instrument.instrument_id
    labels = pd.DatetimeIndex(bars.frame["timestamp"])
    targets = pd.DataFrame({instrument_id: [-4]}, index=labels[:1])
    fx_rates = pd.DataFrame(
        {"EUR": [1.10, 1.10, 1.20, 1.20], "USD": [1, 1, 1, 1]},
        index=labels,
    )
    return build_scenario(
        [bars],
        target_quantities=targets,
        instruments=[ExecutionInstrument(instrument_id, "EURSHORT", "EUR", "0.01")],
        base_currency="USD",
        initial_cash=[CashBalance("EUR", 0), CashBalance("USD", 10_000)],
        fx_rates=fx_rates,
        corporate_actions={
            labels[2]: [CashDividendAction("eur-dividend", instrument_id, 1)],
            labels[3]: [SplitAction("eur-split", instrument_id, 2, 1)],
        },
        clock_policy=_demo_clock(),
        sizing_policy=SizingPolicy(),
        risk=_risk(short_borrow_bps=10_000),
        execution=ExecutionPolicy(participation_bps=10_000, fixed_fee="0.25"),
        run_id="multicurrency-actions",
    )


def _margin_call_scenario() -> TradingEngineScenario:
    bars = _fixed_bars("MARGIN", (100, 100, 170, 170))
    instrument_id = bars.instrument.instrument_id
    labels = pd.DatetimeIndex(bars.frame["timestamp"])
    targets = pd.DataFrame({instrument_id: [-10]}, index=labels[:1])
    return build_scenario(
        [bars],
        target_quantities=targets,
        instruments=[ExecutionInstrument(instrument_id, "MARGIN", "USD", "0.01")],
        base_currency="USD",
        initial_cash=[CashBalance("USD", 1_000)],
        clock_policy=_demo_clock(),
        sizing_policy=SizingPolicy(),
        risk=_risk(max_leverage=2),
        execution=ExecutionPolicy(participation_bps=10_000, fixed_fee="0.25"),
        run_id="margin-call",
    )


def _demo_clock() -> BarClockPolicy:
    return BarClockPolicy(
        source_timestamp_position="start",
        bar_duration=timedelta(minutes=5),
        availability_delay=timedelta(seconds=1),
        receipt_delay=timedelta(seconds=2),
    )


def _risk(
    *,
    max_order_quantity: int = 1_000,
    max_position: int = 1_000,
    max_leverage: int = 2,
    short_borrow_bps: int = 0,
) -> RiskPolicy:
    return RiskPolicy(
        max_order_quantity=max_order_quantity,
        max_long_position=max_position,
        max_short_position=max_position,
        max_gross_exposure=10_000_000,
        max_leverage=max_leverage,
        initial_margin_bps=5_000,
        maintenance_margin_bps=2_500,
        short_borrow_bps=short_borrow_bps,
    )


def _demo_bars(symbol: str, *, periods: int, seed: int, volume: int) -> BarSet:
    source = synthetic.bars(
        symbol,
        periods=periods,
        seed=seed,
        interval="5min",
        session="regular",
    )
    frame = source.frame.copy(deep=True)
    frame["open"] = frame["open"].round(2)
    frame["close"] = frame["close"].round(2)
    frame["high"] = (np.maximum(frame["open"].to_numpy(), frame["close"].to_numpy()) + 0.50).round(
        2
    )
    frame["low"] = (np.minimum(frame["open"].to_numpy(), frame["close"].to_numpy()) - 0.50).round(2)
    frame["volume"] = float(volume)
    frame["volume"] = frame["volume"].astype("Float64")
    return BarSet(source.instrument, frame, source.metadata)


def _fixed_bars(
    symbol: str,
    prices: tuple[float, ...],
    *,
    currency: str = "USD",
) -> BarSet:
    source = _demo_bars(symbol, periods=len(prices), seed=53, volume=1_000)
    frame = source.frame.copy(deep=True)
    for column in ("open", "high", "low", "close"):
        frame[column] = pd.Series(prices, dtype="float64")
    frame["currency"] = pd.Series([currency] * len(frame), dtype="string")
    return BarSet(source.instrument, frame, source.metadata)


def _execution_bars() -> BarSet:
    source = synthetic.bars(
        "CASH",
        periods=4,
        seed=41,
        interval="5min",
        session="regular",
    )
    frame = source.frame.copy(deep=True)
    values = {
        "open": (100.0, 101.0, 102.0, 103.0),
        "high": (100.0, 101.0, 102.0, 103.0),
        "low": (100.0, 101.0, 102.0, 103.0),
        "close": (100.0, 101.0, 102.0, 103.0),
        "volume": (1_000.0, 1_000.0, 1_000.0, 1_000.0),
    }
    for column, column_values in values.items():
        frame[column] = column_values
    frame = frame.astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "Float64",
        }
    )
    return BarSet(source.instrument, frame, source.metadata)


def _validator(path: Path, *, references: tuple[Path, ...] = ()) -> Validator:
    schema = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
    validator_type = validator_for(schema)
    validator_type.check_schema(schema)
    registry: Registry[Any] = Registry[Any]()
    for reference_path in references:
        reference = cast(
            "dict[str, Any]",
            json.loads(reference_path.read_text(encoding="utf-8")),
        )
        registry = registry.with_resource(
            cast("str", reference["$id"]),
            Resource.from_contents(reference),
        )
    return validator_type(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    )
