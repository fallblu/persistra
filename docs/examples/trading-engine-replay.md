# Trading Engine replay examples

Persistra builds deterministic Trading Engine scenarios, invokes a compatible executable without
a shell, verifies the terminal journal, and returns immutable run artifacts. Trading Engine owns
order, fill, risk, margin, fee, target, and accounting behavior.

## Define executable instruments and policies

```python
from datetime import timedelta
from decimal import Decimal

from persistra.integrations.trading_engine import (
    BarClockPolicy,
    CashBalance,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
)

instruments = (
    ExecutionInstrument("asset-a", "AAA", "USD", "0.01", lot_size="0.001"),
    ExecutionInstrument("asset-b", "BBB", "USD", "0.01", lot_size="0.001"),
)
initial_cash = (CashBalance("USD", "100000"),)
clock_policy = BarClockPolicy(
    source_timestamp_position="start",
    bar_duration=timedelta(minutes=5),
    availability_delay=timedelta(0),
    receipt_delay=timedelta(0),
)
sizing_policy = SizingPolicy()
risk_policy = RiskPolicy(
    max_order_quantity="10000",
    max_long_position="10000",
    max_short_position="5000",
    max_gross_exposure="250000",
    max_leverage="2",
    initial_margin_bps=5000,
    maintenance_margin_bps=3000,
    short_borrow_bps=100,
)
execution_policy = ExecutionPolicy(
    participation_bps=2500,
    fixed_fee=Decimal("0.25"),
    fee_bps=5,
    model="completed_bar_v1",
)
```

The clock policy turns source timestamps into explicit start, end, availability, and receipt
instants. Retrieval time is never substituted for these clocks.

## Build a scheduled-target scenario

Start with one raw, unadjusted intraday `BarSet` per instrument. All instruments must share a
complete timestamp grid:

```python
import pandas as pd

from persistra.integrations.trading_engine import build_scenario

decision_times = pd.DatetimeIndex(
    ["2026-01-02T14:30:00Z", "2026-01-02T15:30:00Z"]
)
targets = pd.DataFrame(
    {
        "asset-a": [0.60, 0.30],
        "asset-b": [0.30, 0.60],
    },
    index=decision_times,
)

scenario = build_scenario(
    [asset_a_bars, asset_b_bars],
    targets,
    instruments=instruments,
    base_currency="USD",
    initial_cash=initial_cash,
    clock_policy=clock_policy,
    sizing_policy=sizing_policy,
    risk=risk_policy,
    execution=execution_policy,
    run_id="scheduled-target-example",
    metadata={"research": {"model": "factor-regression-v1"}},
)
```

The target index must use source bar labels. Persistra binds each target to a completed decision
slice and rejects lookahead timing. Weight targets remain exact signed decimal values until the
engine sizes them from marked equity, close, FX, and lot rules.

Use `target_quantities=` instead when an upstream system owns sizing. Do not supply weights and
quantities together.

## Inspect or write the scenario

```python
from pathlib import Path

from persistra.integrations.trading_engine import (
    scenario_to_json,
    scenario_to_jsonl,
    write_scenario,
    write_scenario_stream,
)

print(scenario_to_json(scenario))
print(scenario_to_jsonl(scenario))
batch_path = write_scenario(scenario, Path("artifacts/example.scenario.json"))
stream_path = write_scenario_stream(
    scenario,
    Path("artifacts/example.scenario.jsonl"),
)
```

The JSON Lines form has a header, one record per market slice, and a required terminal count. It
is the normal handoff for model-based runs. Writes use exclusive creation unless overwrite is
requested explicitly.

## Build an empty-schedule external scenario

An external strategy supplies decisions during replay, so its scenario schedule must be empty:

```python
external_scenario = build_scenario(
    [asset_a_bars, asset_b_bars],
    instruments=instruments,
    base_currency="USD",
    initial_cash=initial_cash,
    clock_policy=clock_policy,
    sizing_policy=sizing_policy,
    risk=risk_policy,
    execution=execution_policy,
    run_id="external-strategy-example",
)

assert external_scenario.schedule == ()
```

The scenario still defines every market slice and execution policy. The strategy protocol owns
only the intents that follow those slices.

## Declare the strategy process

```python
import sys

from persistra.integrations.trading_engine import StrategyProcess

strategy_file = Path("strategy_service.py").resolve()
model_file = Path("model.json").resolve()
strategy_process = StrategyProcess(
    command=(sys.executable, strategy_file, "--model", model_file),
    artifacts=(strategy_file, model_file),
    response_timeout=30,
)
```

Command arguments retain exact boundaries; no shell expansion occurs. Declare every source,
model, configuration, and data file that can change behavior. Persistra hashes them before the
run, checks them again afterward, and records them in the manifest.

## Run and retain an artifact bundle

```python
from persistra.integrations.trading_engine import run_scenario

engine = Path.home() / "trading-engine/_build/default/bin/main.exe"
run = run_scenario(
    external_scenario,
    executable=engine,
    output_directory=Path("artifacts/external-strategy-example"),
    strategy=strategy_process,
    timeout=300,
)

assert run.strategy is not None
print(run.scenario_path)
print(run.journal_path)
print(run.manifest_path)
print(run.strategy.transcript_path)
```

The runner checks advertised capabilities, scenario validation, exact hashes, process status,
terminal journal completion, transcript sequence, accounting reconciliation, and unchanged
inputs. It publishes the final artifact group only after all checks pass.

## Read an existing scenario or journal

```python
from persistra.integrations.trading_engine import (
    read_journal,
    read_scenario,
    read_scenario_stream,
)

loaded_batch = read_scenario(batch_path)
loaded_stream = read_scenario_stream(stream_path)
replay = read_journal(run.journal_path, scenario=external_scenario)

assert loaded_batch.run_id == loaded_stream.run_id
print(replay.completion)
```

Pass the originating scenario when importing a journal. Persistra then reconciles market slices,
intents, orders, fills, valuations, corporate actions, and completion identity against it.

## Read the strategy transcript

```python
from persistra.integrations.trading_engine import read_strategy_transcript

transcript = read_strategy_transcript(
    run.strategy.transcript_path,
    scenario_sha256=run.scenario_sha256,
)

print(transcript.identity)
print(len(transcript.decisions))
```

The transcript records every request and response. It does not replace the journal: the
transcript proves what the process requested, while the journal proves what the engine applied.

## Analyze order and fill behavior

```python
from persistra.integrations.trading_engine import (
    ExecutionAnalysisPolicy,
    analyze_execution,
)

analysis = analyze_execution(
    replay,
    policy=ExecutionAnalysisPolicy(periods_per_year=252),
)

print(analysis.lifecycle_summary)
print(analysis.order_diagnostics)
print(analysis.fill_diagnostics)
print(analysis.performance_summary)
```

Positive slippage is adverse for buys and sells. Decision-close movement and eligible-open fill
effects remain separate when their reference bars exist.

## Compare with a vectorized backtest

```python
from persistra.integrations.trading_engine import compare_execution

comparison = compare_execution(vectorized_backtest, analysis)

print(comparison.terminal_summary)
print(comparison.pnl_bridge)
```

The P&L bridge identifies observed fill-price and fee effects. Any remaining difference stays an
explicit residual; Persistra does not label every mismatch as slippage.

## Diagnose process failures

`TradingEngineProcessError` retains the command, return code, captured output, and useful staging
paths. Protocol errors, timeout, malformed output, early EOF, and nonzero strategy exit preserve
partial diagnostics but do not publish a complete bundle. Never accept a journal that lacks the
terminal completion record.

```python
from persistra.integrations.trading_engine import TradingEngineProcessError

try:
    run_scenario(scenario, executable=engine, output_directory=output)
except TradingEngineProcessError as error:
    if error.diagnostic is not None:
        print(error.diagnostic.code, error.diagnostic.context.sequence)
    if error.strategy_rejection is not None:
        evidence = error.strategy_rejection.evidence
        print(evidence.prefix.hex(), evidence.observed_bytes, evidence.truncated)
```

The hexadecimal rendering is for inspection only. Rejected bytes never become a strategy message
or a successful transcript exchange.
