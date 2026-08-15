# Replay a strategy with Trading Engine

The `persistra.integrations.trading_engine` package connects Persistra research to the
separately installed Trading Engine executable. Persistra builds a versioned scenario, starts
the executable without a shell, imports its terminal audit journal, and analyzes execution.
Trading Engine remains responsible for orders, fills, risk, accounting, and deterministic event
sequencing.

This boundary is for offline execution research. It is not a broker connection or live-trading
interface.

## Prepare the executable

Build Trading Engine in its own repository:

```bash
cd ~/trading-engine
opam switch set .
opam install . --deps-only --with-test --locked
opam exec -- dune build
```

The Persistra runner needs the path to an executable file. A normal Dune build produces:

```text
~/trading-engine/_build/default/bin/main.exe
```

Persistra does not import the OCaml project, read its internal state, or give it access to
Persistra's DuckDB tables. Version 1 JSON and JSON Lines artifacts form the integration boundary.

## Use the supported data profile

Start with one normalized `BarSet` per execution instrument. The initial profile accepts only:

- Raw, unadjusted intraday bars
- UTC timestamps and an interval such as `5min`
- One explicit quote and base currency
- Positive, tick-aligned OHLC prices
- Optional nonnegative whole-unit volume
- Long-only target weights or explicit whole-lot target quantities

Daily calendar labels are not accepted. Persistra cannot infer an exchange session close or a
delivery instant from a date. Adjusted bars are also not executable share-and-cash histories
without split and dividend events.

The bars must carry an explicit currency that matches each `ExecutionInstrument`. Provider data
that omits currency needs an application-owned, validated currency mapping before it enters this
boundary.

## Define the clock and execution metadata

Instrument identity does not contain execution metadata. Supply symbol, quote currency, tick
size, and lot size separately:

```python
from datetime import timedelta
from decimal import Decimal

from persistra.integrations.trading_engine import (
    BarClockPolicy,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
)

instruments = [
    ExecutionInstrument(
        instrument_id="asset-a",
        symbol="AAA",
        quote_currency="USD",
        tick_size=Decimal("0.01"),
        lot_size=1,
    ),
    ExecutionInstrument(
        instrument_id="asset-b",
        symbol="BBB",
        quote_currency="USD",
        tick_size=Decimal("0.01"),
        lot_size=1,
    ),
]

clock = BarClockPolicy(
    source_timestamp_position="start",
    bar_duration=timedelta(minutes=5),
    availability_delay=timedelta(0),
    receipt_delay=timedelta(0),
)
sizing = SizingPolicy()
risk = RiskPolicy(max_order_quantity=10_000, max_position=10_000)
execution = ExecutionPolicy(
    participation_bps=2_500,
    fixed_fee=Decimal("0.25"),
    fee_bps=5,
)
```

`source_timestamp_position` states whether each source timestamp labels the start or end of its
bar. If normalized data already says `start` or `end`, the clock policy must agree. A
`provider_label` requires you to choose from the provider contract. Retrieval time is provenance;
it is never used as availability or receipt time.

The zero delays above are required for contiguous five-minute bars: the completed decision bar
is received exactly when the next bar starts. Positive availability or receipt delays are valid
only when the next bar starts at or after the resulting decision time, such as across a session
gap. Scenario validation rejects a target whose decision time follows its next executable bar
start.

The current `SizingPolicy` uses initial cash and decision close, then rounds down to a complete
lot. It does not resize from changing engine equity. `ExecutionPolicy` records bar-volume
participation and per-fill fees. `RiskPolicy` records the engine's global long-only order and
position caps.

## Build a target-position scenario

Target-weight indexes must be timezone-aware bar timestamps. Their columns must exactly match
the execution instrument IDs. In a multi-asset scenario, every target timestamp needs a
same-period bar for every instrument:

```python
import pandas as pd

from persistra.integrations.trading_engine import build_scenario

# bars_by_asset contains one raw intraday BarSet for asset-a and one for asset-b.
decision_times = pd.DatetimeIndex(
    ["2026-01-02T14:30:00Z", "2026-01-02T15:30:00Z"]
)
target_weights = pd.DataFrame(
    {
        "asset-a": [0.50, 0.25],
        "asset-b": [0.25, 0.50],
    },
    index=decision_times,
)

scenario = build_scenario(
    bars_by_asset,
    target_weights,
    instruments=instruments,
    initial_cash=Decimal("100000"),
    clock_policy=clock,
    sizing_policy=sizing,
    risk=risk,
    execution=execution,
    run_id="intraday-demo",
)
```

Weights must be finite, nonnegative, and sum to at most one on each decision. Pass
`target_quantities=` instead of target weights when quantity sizing happens elsewhere. Explicit
quantities must be nonnegative and lot aligned.

The builder groups same-period bars, assigns a global source sequence, and schedules all target
intents after the complete group. The version 1 Persistra profile writes target-position intents
only. Trading Engine supports more intent types, but Persistra's scenario reader rejects them
because it cannot reconstruct them as `TargetDecision` values.

Use `scenario_to_json` to inspect the stable document, or `write_scenario` when another process
will own the run:

```python
from pathlib import Path

from persistra.integrations.trading_engine import scenario_to_json, write_scenario

print(scenario_to_json(scenario))
scenario_path = write_scenario(
    scenario,
    Path("artifacts/intraday-demo.scenario.json"),
)
```

`write_scenario` uses exclusive creation by default. Pass `overwrite=True` only when replacing a
known scenario artifact intentionally.

## Validate and run through the process boundary

`run_scenario` first invokes the engine's `--validate-only` mode. It starts a second process for
the replay only after validation succeeds:

```python
from pathlib import Path

from persistra.integrations.trading_engine import run_scenario

engine = Path.home() / "trading-engine/_build/default/bin/main.exe"
run = run_scenario(
    scenario,
    executable=engine,
    output_directory=Path("artifacts/intraday-demo"),
    timeout=300,
)

print(run.scenario_path)
print(run.journal_path)
print(run.scenario_sha256)
print(run.journal_sha256)
```

The runner passes an argument vector directly to `subprocess`; it does not use a shell. It
captures standard output and error, requires a successful exit, and refuses an existing journal
path. `TradingEngineProcessError` retains the failed command, stage output, return code, and
journal path when one applies.

Every accepted replay must end with one `run_completed` journal record. A zero exit without a
journal, a partial journal without completion, or a record after completion fails the boundary.
The completion contains the terminal valuation and order-status counts.

## Understand causal order eligibility

Each audit order records both `eligible_after_bar_sequence` and `created_at`. Sequence alone is
not sufficient. Trading Engine can fill the order only from a later source sequence whose bar
start is not earlier than `created_at`.

`created_at` is the replay clock when the engine accepts or rejects the order. For scheduled
targets, that clock comes from the completed decision bar group's receipt time. The matcher keeps
the timestamp check as defense in depth, but both Persistra's scenario contract and Trading Engine
reject a schedule when that decision time follows the next executable bar start. They never
backdate an order or let a later callback retroactively change an opening execution.

## Import and inspect the audit journal

`run.replay` is an `ExecutionReplayResult`. It contains normalized frames for bars, targets,
orders, fills, cancellations, rejections, valuations, and emitted metrics. It also retains the
immutable ordered `JournalEvent` records and typed `RunCompletion`:

```python
replay = run.replay

print(replay.orders[["order_id", "created_at", "status"]])
print(replay.fills[["fill_id", "quantity", "price", "fee"]])
print(replay.valuations[["recorded_at", "equity", "total_fees"]])
print(replay.completion)
```

Price and money columns have convenient floating-point values for pandas analysis and adjacent
exact `*_micros` columns using nullable `Int64`. For example, fills contain both `price` and
`price_micros`, while valuations contain `equity` and `equity_micros`. Quantities and sequences
also use nullable integer dtypes. Use the micro-unit columns for exact reconciliation or artifact
comparison.

Read an existing artifact with its scenario whenever possible:

```python
from persistra.integrations.trading_engine import read_journal

replay = read_journal(run.journal_path, scenario=run.scenario_path)
```

Supplying the target-only scenario validates run identity, bars, decisions, terminal accounting,
and order counts. It also restores initial cash, base currency, and decision reference closes.
The engine's version 1 scenario stores sized quantities, but not Persistra's research target
weights. `run_scenario(scenario, ...)` retains weights when `scenario` is the original in-memory
`TradingEngineScenario`. Reading from `run.scenario_path` returns `NA` target weights. A journal
can be read without a scenario, but all scenario-owned fields are then unavailable.

## Analyze execution and event-time performance

`analyze_execution` reports order lifecycle rates, requested and filled quantities, fill fees,
decision-close and fill-bar-open slippage, bar count to first fill, equity, returns, drawdown, and
performance statistics:

```python
from persistra.integrations.trading_engine import (
    ExecutionAnalysisPolicy,
    analyze_execution,
)

analysis = analyze_execution(
    replay,
    policy=ExecutionAnalysisPolicy(
        periods_per_year=None,
        initial_equity="scenario_initial_cash",
        turnover_denominator="average_equity",
    ),
)

print(analysis.lifecycle_summary)
print(analysis.order_diagnostics)
print(analysis.fill_diagnostics)
print(analysis.performance_summary)
```

Returns are changes between valuation events. These events need not be equally spaced, and a
multi-asset replay can emit more than one valuation at one timestamp. Annualized return,
volatility, Sharpe, and Sortino values therefore remain missing unless you supply an explicit
`periods_per_year`. Short samples and zero denominators also leave the relevant ratios missing.

The default initial-equity source is scenario initial cash. If you imported a journal without a
scenario, choose `initial_equity="first_valuation"` or supply a positive numeric value. Choosing
the first valuation makes its return missing because that observation becomes the baseline.

Positive slippage is adverse for both buys and sells. Analysis separates the decision close to
fill-bar-open move from the fill-bar-open to actual-fill move. A missing linked bar leaves that
reference diagnostic missing instead of inventing a price.

## Compare with the vectorized backtest

Use the `BacktestResult` from the same strategy research as the baseline:

```python
from persistra.integrations.trading_engine import compare_execution

comparison = compare_execution(vectorized_result, analysis)

print(comparison.terminal_summary)
print(comparison.pnl_bridge)
print(comparison.caveat)
```

Persistra's price-input backtest uses close-to-close returns. Trading Engine market orders use a
later eligible bar open, and limit orders use the engine's completed-bar rules. The additive
currency P&L bridge therefore separates:

- The scaled close-to-close research P&L
- Decision-close to fill-bar-open timing
- Fill-bar-open to actual-fill price
- Engine fees
- An exact balancing residual

The residual includes partial fills, unfilled exposure, residual cash, sizing, valuation-grid,
marking, and cost-model differences. It is not pure slippage. The bridge reports reference
coverage so missing price links stay visible.

## Plot the replay diagnostics

The plotting helpers accept the calculated analysis result:

```python
from persistra.viz import (
    plot_execution_diagnostics,
    plot_execution_performance,
)

performance_axes = plot_execution_performance(analysis)
diagnostic_axes = plot_execution_diagnostics(analysis)

performance_axes.equity.figure.tight_layout()
diagnostic_axes.quantities.figure.tight_layout()
```

The performance figure shows event-time equity and drawdown. The diagnostic figure compares
requested and filled order quantity and shows adverse slippage against both explicit price
references.

## Keep the prototype limits visible

The integration does not add exchange calendars, corporate actions, shorts, margin, multiple
currencies, buying-power checks, broker state, or live execution. Market orders use the next
eligible bar open and cancel any unfilled remainder. Limit orders can remain active and use an
optimistic bar-touch rule because completed OHLCV does not contain queue position or intrabar
path.

Keep the scenario and journal hashes with the research artifacts. Re-run the same scenario and
engine version when testing determinism. Treat the journal as an execution audit artifact, not a
crash-safe broker-recovery log.
