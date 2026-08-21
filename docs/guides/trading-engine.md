# Replay a strategy with Trading Engine

The `persistra.integrations.trading_engine` package connects Persistra research to the
separately installed Trading Engine executable. Persistra builds a deterministic scenario,
starts the executable without a shell, imports its terminal audit journal, verifies accounting
and execution invariants, and analyzes execution. Trading Engine remains responsible for orders,
fills, risk, accounting, target persistence, and event sequencing.

This boundary is for offline execution research. It is not a broker connection or live-trading
interface.

Read [Develop a strategy](strategy-development.md) first when you need warm-up, bounded history,
security filtering, schedules, lifecycle hooks, composite decision stages, or rebalance guards.
This guide focuses on the executable scenario, process, artifact, and journal boundary.

## Prepare the executable

The shorter [Trading Engine setup](../getting-started/trading-engine.md) explains when to add the
runtime and how the two projects divide responsibilities.

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
Persistra's DuckDB tables. Deterministic JSON or JSON Lines scenarios and JSON Lines journals form
the integration boundary. Every scenario document, scenario-stream record, and journal record
carries `contract_version: "3"`. Persistra rejects unversioned files and unsupported versions;
the integration does not reinterpret frozen v2 artifacts.

## Use synchronized executable data

Start with one normalized `BarSet` per execution instrument. The boundary accepts:

- Raw, unadjusted intraday bars
- A common timestamp grid and interval such as `5min`
- One quote currency per instrument and a complete currency-to-base FX vector per slice
- Positive, tick-aligned OHLC prices
- Optional nonnegative fractional volume aligned to the instrument lot
- Signed portfolio weights or explicit fractional, lot-aligned quantities
- Splits and cash dividends applied before matching

Every timestamp becomes one market slice containing exactly one bar per instrument. All bars in
a slice share start, end, availability, and receipt clocks. Missing or offset instrument bars are
rejected rather than replayed with mixed marks.

Daily calendar labels are not accepted. Persistra cannot infer a session close or delivery
instant from a date. Adjusted bars are not executable share-and-cash histories. Supply raw prices
plus explicit split and dividend events instead.

The execution instrument's explicit quote currency supplies the boundary currency when a source
does not report one, as with Alpha Vantage security bars. A nonmissing source currency must match
that quote currency; Persistra rejects contradictory values.

## Define clocks, instruments, risk, and execution

```python
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from persistra.integrations.trading_engine import (
    BarClockPolicy,
    CashBalance,
    ExecutionInstrument,
    ExecutionPolicy,
    RiskPolicy,
    SizingPolicy,
)

instruments = [
    ExecutionInstrument("asset-a", "AAA", "USD", Decimal("0.01"), lot_size="0.001"),
    ExecutionInstrument("asset-b", "BBB", "EUR", Decimal("0.01"), lot_size="0.001"),
]

initial_cash = [
    CashBalance("USD", Decimal("100000")),
    CashBalance("EUR", Decimal("25000")),
]

clock = BarClockPolicy(
    source_timestamp_position="start",
    bar_duration=timedelta(minutes=5),
    availability_delay=timedelta(0),
    receipt_delay=timedelta(0),
)
sizing = SizingPolicy()
risk = RiskPolicy(
    max_order_quantity="10000",
    max_long_position="10000",
    max_short_position="5000",
    max_gross_exposure="250000",
    max_leverage="2",
    initial_margin_bps=5000,
    maintenance_margin_bps=3000,
    short_borrow_bps=100,
)
execution = ExecutionPolicy(
    participation_bps=2_500,
    fixed_fee=Decimal("0.25"),
    fee_bps=5,
    model="completed_bar_v1",
)
```

`source_timestamp_position` says whether the normalized label denotes the start or end of its
bar. A normalized `start` or `end` must agree with the policy; a `provider_label` requires an
application choice grounded in the provider contract. Retrieval time remains provenance and is
never substituted for availability or receipt time.

`SizingPolicy` documents the engine-owned weight conversion: current base-currency marked equity,
the decision-slice close and FX rate, and rounding toward zero to a complete lot. The engine
retains the requested signed portfolio and retries incomplete rebalances on later slices until
reached or superseded. A target that changes sign first flattens the existing position.

`ExecutionPolicy` selects the execution model and sets per-instrument slice-volume participation
and per-fill fees. Persistra currently supports `completed_bar_v1`; the runner verifies that the
selected executable advertises that model before writing artifacts. `RiskPolicy` sets order,
long/short position, gross-exposure, leverage, initial/maintenance margin, and short-borrow rules.
All quantity limits must be at least each configured lot.

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
    base_currency="USD",
    initial_cash=initial_cash,
    fx_rates=fx_rates,
    corporate_actions=corporate_actions,
    clock_policy=clock,
    sizing_policy=sizing,
    risk=risk,
    execution=execution,
    run_id="intraday-demo",
    metadata={"research": {"experiment": "momentum-baseline"}},
)
```

Weights remain exact signed decimal targets in the scenario; Persistra does not turn them into
quantities using initial cash. Their gross absolute sum must not exceed `max_leverage`. Pass
`target_quantities=` instead when sizing happens elsewhere. Explicit signed quantities must be
lot aligned and within the configured long or short cap.

`fx_rates` is a timestamp-indexed frame with one column for every scenario currency. The base
currency must equal one at every slice. It may be omitted only for a base-currency-only scenario,
where Persistra supplies that unit rate. `corporate_actions` maps bar timestamps to sequences of
`SplitAction` and `CashDividendAction`; action IDs must be unique across the scenario.

The required scenario metadata is arbitrary JSON plus a generated `persistra` section. That
section records clock, sizing, risk, execution, source identities, and the original targets. API
keys are already removed by normalized result metadata.

The typed scenario reader also understands direct `submit_order`, `cancel_order`, and
`emit_metric` intents. `build_scenario` emits complete `target_weights` or `target_quantities`
portfolio intents. Omit both target inputs to create the empty schedule required by an external
strategy process.

Use `scenario_to_json` to inspect the stable batch document. Use `scenario_to_jsonl` or
`write_scenario_stream` for the bounded-memory engine handoff:

```python
from pathlib import Path

from persistra.integrations.trading_engine import (
    scenario_to_json,
    scenario_to_jsonl,
    write_scenario_stream,
)

print(scenario_to_json(scenario))
print(scenario_to_jsonl(scenario))
scenario_path = write_scenario_stream(
    scenario,
    Path("artifacts/intraday-demo.scenario.jsonl"),
)
```

The stream has one static header, one record per synchronized slice, and a required terminal
slice count. Each slice record carries the intents evaluated after that slice, making the causal
decision boundary adjacent rather than placing all future decisions in a global schedule.
`write_scenario_stream` writes one record at a time and uses exclusive creation by default. Pass
`overwrite=True` only when replacing a known scenario artifact intentionally. `write_scenario`
remains available for an explicit batch JSON artifact.

## Host an external Python strategy

Use the strategy protocol when decisions depend on fills, order updates, rejections, or evolving
engine state instead of a schedule authored before replay. The engine launches the declared
program directly, without a shell. It sends one initialization request, then one event and
complete context at a time. The strategy must answer each request before the engine continues.
Process supervision is not a sandbox: run strategy code with the same trust you give the
invoking user.

For most strategies, subclass `BaseStrategy`. It owns warmup, bounded bar history, fixed-catalog
security selection, separate selection and rebalance schedules, and complete target construction:

```python
from decimal import Decimal

from persistra.integrations.trading_engine import (
    BaseStrategy,
    ObservationSchedule,
    ScenarioIntent,
    StrategyConfiguration,
    StrategyInitialization,
    StrategyView,
    WarmupPolicy,
    serve_strategy,
)


class MomentumStrategy(BaseStrategy):
    name = "bounded-momentum"
    version: str | None = "1"

    def configure(self, initialization: StrategyInitialization) -> StrategyConfiguration:
        del initialization
        return StrategyConfiguration(
            history_capacity=60,
            warmup=WarmupPolicy(observations=20, security_observations=20),
            selection_schedule=ObservationSchedule(every=5),
            rebalance_schedule=ObservationSchedule(every=5, start_at=20),
            removal_policy="liquidate",
        )

    def on_rebalance(self, view: StrategyView) -> tuple[ScenarioIntent, ...]:
        returns = {}
        for instrument_id in view.universe:
            observations = view.history.observations(instrument_id)
            returns[instrument_id] = observations[-1].bar.close / observations[0].bar.close - 1
        leaders = [instrument_id for instrument_id, value in returns.items() if value > 0]
        weight = (
            (Decimal(1) / len(leaders)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
            if leaders
            else Decimal(0)
        )
        return (view.target_weights({instrument_id: weight for instrument_id in leaders}),)


serve_strategy(MomentumStrategy())
```

Standard output belongs exclusively to protocol messages. Send diagnostics to standard error.
`serve_strategy` validates protocol version, sequence, exact message fields, canonical values,
and the 1 MiB response limit. It converts callback failures into an `error` response and exits
with an exception.

Build an empty-schedule scenario and declare the process when running it:

```python
import sys
from pathlib import Path

from persistra.integrations.trading_engine import (
    StrategyProcess,
    build_scenario,
    run_scenario,
)

strategy_file = Path("external_strategy.py").resolve()
external_scenario = build_scenario(
    bars_by_asset,
    instruments=instruments,
    base_currency="USD",
    initial_cash=initial_cash,
    fx_rates=fx_rates,
    clock_policy=clock,
    sizing_policy=sizing,
    risk=risk,
    execution=execution,
    run_id="external-demo",
)
external_run = run_scenario(
    external_scenario,
    executable=engine,
    output_directory=Path("artifacts/external-demo"),
    strategy=StrategyProcess(
        command=(sys.executable, strategy_file),
        artifacts=(strategy_file,),
        response_timeout=30,
    ),
)

assert external_run.strategy is not None
print(external_run.strategy.identity)
print(external_run.strategy.transcript_path)
```

Declare every configuration, model, or data file that can change strategy behavior in
`artifacts`. Persistra hashes those inputs before replay, checks that they remain unchanged, and
records them in the manifest. Command arguments retain their exact boundaries; no shell parsing
or expansion occurs. The overall `run_scenario` timeout still caps the engine process, while
`response_timeout` caps each initialization, event, shutdown, and exit exchange.

The event context contains the replay clock, an authoritative marked portfolio, working orders,
and the latest available bars. Protocol v3 builds every callback context when the callback is
delivered. Fill and order callbacks therefore use the current slice receipt time, bars, marks,
and FX rates. The engine waits for each callback response and applies its intents before it
continues matching, so a cancellation returned after one fill can stop later fills in the same
slice. The portfolio includes base-currency cash, equity, net, long, short, and gross values.
Each configured position includes its applied quantity, mark, base market value, and realized
weight. Persistra reconciles each realized weight against its marked value and positive equity
using protocol v3's truncation-toward-zero rule at six decimal places. Weights are unavailable
when equity is zero or negative. Events distinguish completed market slices, fills, order
updates, and rejected intents. Responses use the same typed target, order, cancellation, and
metric intents as scheduled scenarios.

`BaseStrategy` ingests a completed slice before calling hooks. It then updates scheduled
selection, applies per-security readiness, reports universe changes, completes global warmup,
and runs a due rebalance. Both observation and elapsed warmup requirements must pass.
Order-changing intents are rejected during warmup, while metric intents remain available.
Selection can only choose IDs from the initialized engine catalog; it does not change the
scenario catalog.

`StrategyHistory` retains at most `history_capacity` bars per security. Observation schedules use
one-based completed-slice counts. Elapsed schedules use market-slice end times. The built-in hooks
cover data, universe changes, warmup completion, scheduled rebalancing, fills, order updates,
rejections, initialization, and shutdown. The low-level `ExternalStrategy` protocol remains
available when an application needs to own every event dispatch decision.

The `StrategyView.target_weights` and `target_quantities` helpers always emit the engine's
required full fixed-catalog target. Missing active securities become zero. For filtered-out
securities, `liquidate` emits zero, `retain` carries the actual filled position forward, and
`error` rejects a nonzero holding. Retained weight targets require the positive-equity realized
weights supplied by protocol v3.

Use `CompositeStrategy` when a strategy separates signal estimation from portfolio construction.
Its alpha models observe every completed slice but cannot emit intents. At each scheduled
rebalance, one forecast combiner feeds one portfolio constructor, target overlays run in order,
and the composite emits at most one complete weight target. Every component declares its history
requirements. The composite raises lifecycle warmup and history capacity to satisfy the largest
requirement. `last_decision` records forecast sources and each target transformation without
changing the Trading Engine protocol. `WeightedForecastCombiner` provides deterministic aligned
forecast blending; custom combiners, constructors, and overlays implement the corresponding
protocols. Rebalance guards see the completed fixed-catalog target and authoritative portfolio
after all overlays. `MinimumTargetChangeGuard` suppresses immaterial changes, while
`OutstandingOrdersGuard` prevents a new portfolio target while orders remain working. Every
guard result appears in the decision trace.

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

The runner preflights the scenario, journal, strategy transcript, staging files, and manifest
before invoking the engine. It first reads `--capabilities` and requires the selected v3 scenario
format, v3 JSON Lines journals, and the completed-bar v1 execution model. External runs also
require strategy protocol v3. Model-based runs produce JSON Lines and pass `--input-format
jsonl`; an explicit `.json` path remains a batch run. The engine validates the stream before
journal creation and then replays one slice-plus-intents record at a time without retaining
scenario or audit history. Persistra requires `run_started` and `run_completed` to repeat the
exact scenario-file SHA-256, requires v3 on every record, reconciles the full journal against the
scenario and optional strategy decisions, and checks that all bound executables and inputs remain
unchanged. It exposes a successful external journal and transcript as one checked artifact group.

The final manifest is deterministic and includes:

- Run ID, relative scenario/journal paths, and scenario format
- Contract version and the complete advertised engine capability document
- Scenario, journal, and executable SHA-256 digests
- For external runs, the strategy identity, executable, declared inputs, transcript, protocol,
  and response timeout
- Persistra and engine versions, VCS revisions, and dirty states
- Python implementation, version, operating system, and architecture
- The complete scenario metadata

VCS revision and dirty state are recorded when the installed source or executable is inside a
Git worktree. They are `null` for a copied executable or installed package whose worktree cannot
be discovered; the executable SHA-256 remains authoritative for those bytes.

The runner refuses to replace any bundle artifact. After successful reconciliation, it stages
the manifest before publishing the journal, optional strategy transcript, and manifest as one
coordinated group. A staging, hash, collision, or publication failure rolls back only files
created by that run, so no incomplete final bundle remains and a raced-in foreign path is never
deleted.

`TradingEngineProcessError` retains the failed command, output, return code, and the most useful
journal and strategy transcript staging paths when they exist. Protocol, timeout, EOF, malformed
response, and nonzero-exit failures keep partial diagnostics and do not publish final artifacts
or a manifest.

## Understand portfolio and order timing

The typed model uses `after_slice_sequence`; the JSON Lines artifact places those intents inside
the named slice record. A target or direct order created after slice `N` can execute only on a
later slice whose start is not earlier than `created_at`. Both parsers reject an order-changing
intent when the decision slice was received after the next executable slice started. The journal
records this boundary as `eligible_after_slice_sequence`.

At each synchronized slice the engine:

1. Applies splits and dividends, adjusting positions, persistent targets, and active orders.
2. Accrues borrow fees on open shorts for the exact slice interval.
3. Matches liquidation orders first, then sells before buys within each origin class, against
   fractional lot-aligned capacity.
4. Emits `margin_limited` when risk permits less than the proposed fill.
5. Evaluates scheduled portfolio targets and direct intents.
6. Assesses maintenance margin and creates deterministic liquidation orders when breached.
7. Emits exactly one complete-slice valuation.

Persistent portfolio targets are superseded atomically by a later portfolio target. Direct
market orders remain immediate-or-cancel requests; target persistence is maintained by the
portfolio planner rather than by keeping a partially filled market order active.

## Import and inspect the journal

`run.replay` contains normalized frames for bars, FX, portfolio targets, orders, fills,
cancellations, rejections, split-driven order adjustments, corporate actions, margin limits,
borrow fees, margin events, valuations, per-currency cash balances, per-instrument positions, and
metrics. It also retains ordered `JournalEvent` values and a typed `RunCompletion`:

```python
replay = run.replay

print(replay.targets[["basis", "instrument_id", "weight", "quantity"]])
print(replay.orders[["order_id", "eligible_after_slice_sequence", "status"]])
print(replay.fills[["fill_id", "slice_sequence", "quantity", "price", "fee"]])
print(replay.margin_limits)
print(replay.corporate_actions)
print(replay.cash_balances[["slice_sequence", "currency", "amount", "base_value"]])
print(
    replay.valuations[
        ["slice_sequence", "equity", "gross_exposure", "maintenance_excess"]
    ]
)
print(
    replay.positions[
        ["slice_sequence", "instrument_id", "quantity", "cost_basis", "unrealized_pnl"]
    ]
)
print(replay.execution_model)
```

Money, price, FX, and quantity columns have convenient floats plus adjacent exact `*_micros`
nullable integers. Sequences use nullable integer dtypes. Use the exact columns for reconciliation
and artifact comparison.

Read retained artifacts with the exact scenario path so the importer verifies the byte identity
the engine received:

```python
from persistra.integrations.trading_engine import read_journal

replay = read_journal(run.journal_path, scenario=run.scenario_path)
```

A `TradingEngineScenario` model instead selects the canonical JSON Lines representation used by
`run_scenario(model, ...)`, so the original model can also reconcile that run. A `.json` or
`.jsonl` path always selects the exact bytes in that artifact. When supplied, `scenario_sha256`
must match the digest for the selected model or path representation.

Scenario-backed import verifies synchronized slice contents, original targets, engine-owned
weight sizing, order, fill, and cancellation state, tick and lot alignment, participation
capacity, fees, corporate actions, split-adjusted orders and targets, signed long/short accounting,
complete FX marks and currency ledgers, borrow accrual, margin-limited fills, and deterministic
margin-call liquidation. It reconstructs native and base position basis, realized and unrealized
P&L, dividends, execution and borrow fees, cash, long/short/net/gross value, equity, and margin;
then verifies terminal order counts and exactly one valuation per slice. Every journal event ID
must derive from the run
and engine sequence. Causation IDs must be unique, canonically ordered references to earlier
events in the same run; fills and cancellations cite their order-creation event, fills also cite
their executable slice, valuations cite their current slice, and completion cites the terminal
valuation. Position rows must cover every scenario instrument and reconcile independently to
fills, marks, and the account aggregates.

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
withholding-tax or merger/spinoff processing, locate availability, variable broker house margin,
interest on cash/debit balances, broker state, or live execution. Limit orders use an optimistic
OHLC touch rule because bars do not contain queue position or an intrabar path. FX is marked once
per synchronized slice; it is not independently executable intrabar market data.

Retain the complete run bundle with research outputs. Treat its journal as an execution audit
artifact, not as a broker-recovery log.
