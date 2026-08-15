# Replay a strategy with Trading Engine

The `persistra.integrations.trading_engine` package connects Persistra research to the
separately installed Trading Engine executable. Persistra builds a deterministic scenario,
starts the executable without a shell, imports its terminal audit journal, verifies accounting
and execution invariants, and analyzes execution. Trading Engine remains responsible for orders,
fills, risk, accounting, target persistence, and event sequencing.

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

A normal Dune build produces the executable at:

```text
~/trading-engine/_build/default/bin/main.exe
```

Persistra does not import the OCaml project, read its internal state, or give it access to
Persistra's DuckDB tables. Deterministic JSON scenarios and JSON Lines journals form the
integration boundary. Every scenario and journal record carries `contract_version: "1"`.
Persistra rejects unversioned files and unsupported versions.

## Use synchronized executable data

Start with one normalized `BarSet` per execution instrument. The boundary accepts:

- Raw, unadjusted intraday bars
- A common timestamp grid and interval such as `5min`
- One quote and base currency
- Positive, tick-aligned OHLC prices
- Optional nonnegative whole-unit volume
- Long-only portfolio weights or explicit whole-lot quantities

Every timestamp becomes one market slice containing exactly one bar per instrument. All bars in
a slice share start, end, availability, and receipt clocks. Missing or offset instrument bars are
rejected rather than replayed with mixed marks.

Daily calendar labels are not accepted. Persistra cannot infer a session close or delivery
instant from a date. Adjusted bars are also not executable share-and-cash histories without split
and dividend events.

## Define clocks, instruments, risk, and execution

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
    ExecutionInstrument("asset-a", "AAA", "USD", Decimal("0.01"), lot_size=1),
    ExecutionInstrument("asset-b", "BBB", "USD", Decimal("0.01"), lot_size=1),
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

`source_timestamp_position` says whether the normalized label denotes the start or end of its
bar. A normalized `start` or `end` must agree with the policy; a `provider_label` requires an
application choice grounded in the provider contract. Retrieval time remains provenance and is
never substituted for availability or receipt time.

`SizingPolicy` documents the engine-owned weight conversion: current marked equity, the decision
slice close, and rounding down to a complete lot. The engine retains the requested portfolio and
retries incomplete rebalances on later slices until reached or superseded. It processes sells
before buys, then reduces a buy to the largest affordable lot at its actual execution price,
including fees. Cash cannot become negative.

`ExecutionPolicy` sets per-instrument slice-volume participation and per-fill fees. `RiskPolicy`
sets long-only order and position caps. Both risk limits must be at least each configured lot.

## Build a portfolio scenario

Target indexes must be timezone-aware bar timestamps, and columns must exactly match the
execution instrument IDs:

```python
import pandas as pd

from persistra.integrations.trading_engine import build_scenario

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
    metadata={"research": {"experiment": "momentum-baseline"}},
)
```

Weights remain exact decimal targets in the scenario; Persistra does not turn them into
quantities using initial cash. They must be finite, nonnegative, and sum to at most one per
decision. Pass `target_quantities=` instead when sizing happens elsewhere. Explicit quantities
must be nonnegative, lot aligned, and within the position cap.

The required scenario metadata is arbitrary JSON plus a generated `persistra` section. That
section records clock, sizing, risk, execution, source identities, and the original targets. API
keys are already removed by normalized result metadata.

The typed scenario reader also understands direct `submit_order`, `cancel_order`, and
`emit_metric` intents. `build_scenario` emits complete `target_weights` or `target_quantities`
portfolio intents.

Use `scenario_to_json` to inspect the stable document, or `write_scenario` to create an artifact:

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

## Validate, replay, and create a run bundle

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
print(run.manifest_path)
print(run.scenario_sha256)
print(run.journal_sha256)
print(run.executable_sha256)
print(run.capabilities.engine_version)
```

The runner preflights the scenario, journal, staging files, and manifest before invoking the
engine. It first reads `--capabilities` and requires v1 JSON scenarios, v1 JSON Lines journals,
and the completed-bar v1 execution model. It then calls `--validate-only` and replays into a
staging journal. Persistra requires `run_started` and `run_completed` to repeat the exact scenario
file SHA-256, requires v1 on every record, reconciles the full journal, checks that the scenario
and executable did not change during the run, and only then atomically exposes the final journal.

The final manifest is deterministic and includes:

- Run ID and relative scenario/journal paths
- Contract version and the complete advertised engine capability document
- Scenario, journal, and executable SHA-256 digests
- Persistra and engine versions, VCS revisions, and dirty states
- Python implementation, version, operating system, and architecture
- The complete scenario metadata

VCS revision and dirty state are recorded when the installed source or executable is inside a
Git worktree. They are `null` for a copied executable or installed package whose worktree cannot
be discovered; the executable SHA-256 remains authoritative for those bytes.

The runner refuses to replace any bundle artifact. `TradingEngineProcessError` retains the
failed command, output, return code, and the most useful journal or staging path when one exists.

## Understand portfolio and order timing

Each schedule entry uses `after_slice_sequence`. A target or direct order created after slice
`N` can execute only on a later slice whose start is not earlier than `created_at`. The journal
records this boundary as `eligible_after_slice_sequence`.

At each synchronized slice the engine:

1. Applies eligible sell fills.
2. Applies eligible buy fills subject to remaining volume and buying power.
3. Emits `cash_limited` when a requested buy must be reduced.
4. Evaluates scheduled portfolio targets and direct intents.
5. Emits exactly one complete-slice valuation.

Persistent portfolio targets are superseded atomically by a later portfolio target. Direct
market orders remain immediate-or-cancel requests; target persistence is maintained by the
portfolio planner rather than by keeping a partially filled market order active.

## Import and inspect the journal

`run.replay` contains normalized frames for bars, portfolio targets, orders, fills,
cancellations, rejections, cash limits, valuations, and metrics. It also retains ordered
`JournalEvent` values and a typed `RunCompletion`:

```python
replay = run.replay

print(replay.targets[["basis", "instrument_id", "weight", "quantity"]])
print(replay.orders[["order_id", "eligible_after_slice_sequence", "status"]])
print(replay.fills[["fill_id", "slice_sequence", "quantity", "price", "fee"]])
print(replay.cash_limits)
print(replay.valuations[["slice_sequence", "equity", "total_fees"]])
```

Money and price columns have convenient floats plus adjacent exact `*_micros` nullable integers.
Quantities and sequences also use nullable integer dtypes. Use the exact columns for
reconciliation and artifact comparison.

Read retained artifacts with the exact scenario path so the importer verifies the byte identity
the engine received:

```python
from persistra.integrations.trading_engine import read_journal

replay = read_journal(run.journal_path, scenario=run.scenario_path)
```

Scenario-backed import verifies synchronized slice contents, original targets, engine-owned
weight sizing, order, fill, and cancellation state, tick and lot alignment, participation
capacity, fees, sell-before-buy ordering, nonnegative cash and positions, and cash-limit event,
price, remaining-order, and same-slice fill claims. It reconstructs exact position cost basis,
realized and unrealized P&L, cash, market value, equity, and total fees; then verifies terminal
order counts and exactly one valuation per slice.

## Analyze and plot execution

```python
from persistra.integrations.trading_engine import (
    ExecutionAnalysisPolicy,
    analyze_execution,
    compare_execution,
)
from persistra.viz import plot_execution_diagnostics, plot_execution_performance

analysis = analyze_execution(
    replay,
    policy=ExecutionAnalysisPolicy(
        periods_per_year=None,
        initial_equity="scenario_initial_cash",
        turnover_denominator="average_equity",
    ),
)
comparison = compare_execution(vectorized_result, analysis)

performance_axes = plot_execution_performance(analysis)
diagnostic_axes = plot_execution_diagnostics(analysis)
```

Execution analysis reports lifecycle rates, requested and filled quantities, fees, slice count to
first fill, decision-close to fill-slice-open timing, fill-price effects, equity, returns, and
drawdown. Returns are changes between complete-slice valuations. Annualized statistics remain
missing unless `periods_per_year` is supplied explicitly.

The vectorized comparison separates close-to-close research P&L, decision-to-fill timing,
fill-price effects, engine fees, and a balancing residual. The residual includes unfilled
exposure, residual cash, rounding, marking, and model differences; it is not pure slippage.

## Keep the remaining limits visible

The integration remains an offline completed-bar model. It does not add exchange calendars,
corporate-action events, shorts, margin, multiple currencies, broker state, or live execution.
Limit orders use an optimistic OHLC touch rule because bars do not contain queue position or an
intrabar path.

Retain the complete run bundle with research outputs. Treat its journal as an execution audit
artifact, not as a broker-recovery log.
