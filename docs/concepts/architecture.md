# Architecture

Persistra is organized as a pipeline of small layers with explicit handoff types. The
separation prevents provider transport, normalized semantics, persistence, calculations, and
presentation from becoming one implicit workflow.

## Layer responsibilities

| Layer | Responsibility | Does not do |
|---|---|---|
| Provider adapter | Request, classify, parse, and normalize source responses | Store normalized results or run analysis |
| Model | Validate identity, frames, dtypes, ordering, and provenance | Contact a provider or infer research policy |
| Raw cache | Retain provider bytes for reuse and offline parsing | Provide normalized research queries |
| DuckDB store | Persist validated results and retrieval-time revisions | Acquire, fill, or transform data |
| Transforms | Pivot, align, as-of match, and resample explicitly | Choose unstated missing-data policy |
| Point-in-time research | Select vintages, features, labels, and time splits | Guess availability, fill missing values, or define factors |
| Factor modeling | Fit caller-defined regressions, risk models, forecasts, and attribution | Supply reference factors or hide estimation windows |
| Portfolio research | Construct target weights and simulate portfolio-level rebalances | Model orders, fills, exchange execution, or live trading |
| Strategy lifecycle | Manage bounded history, warm-up, selection, schedules, and decision composition | Expand the scenario catalog or predict fills |
| Trading Engine integration | Build deterministic scenarios, run an explicit executable, and import and analyze audit journals | Implement execution semantics, connect to a broker, or expose internal storage |
| Analysis | Calculate statistics from supplied inputs | Fetch data or produce hidden side effects |
| Visualization | Render supplied observations and calculations | Own global Matplotlib configuration |

A typical workflow follows this direction:

```text
provider or synthetic helper
        -> normalized result object
        -> optional DuckDB persistence
        -> explicit transform
        -> point-in-time features and labels
        -> caller-defined factor model and forecast
        -> constrained target portfolio
        -> strategy lifecycle or precomputed target schedule
        -> Trading Engine scenario and replay
        -> journal and execution analysis
        -> explicit analysis
        -> Matplotlib visualization
```

The raw cache sits beside provider acquisition. It stores transport responses before
normalization and is independent of DuckDB persistence.

## Provider-neutral results

Provider adapters terminate at model objects such as `BarSet`, `OptionChain`, and `SeriesSet`.
Code downstream of that boundary can operate on normalized fields instead of response
envelopes or provider-specific column names.

Provider neutrality does not mean provider equivalence. A provider-scoped symbol creates a
provider-scoped identity. Persistra does not claim that two provider records describe the
same instrument unless the application records an explicit mapping.

## Capability protocols

The data layer exposes small runtime-checkable protocols:

- `BarSource`
- `QuoteSource`
- `OptionChainSource`
- `ScalarSeriesSource`
- `ReferenceSource`

Application code can depend on the capability it needs instead of the complete Alpha Vantage
client:

```python
from persistra.data import BarSource


def acquire_daily(source: BarSource, symbol: str):
    return source.bars(symbol, interval="daily")
```

Provider namespace methods can have richer signatures than a minimal capability protocol.
Use adapters or small application wrappers when a concrete provider requires extra arguments
such as `InstrumentKind`.

## Immutable normalized boundaries

Most identity, metadata, and result classes are frozen dataclasses. Result construction
deep-copies and validates frames, then stores the validated copy. This prevents a caller's
input frame from changing the result after validation.

Pandas objects themselves remain mutable. Treat the frame held by a normalized result as
source data and make an explicit copy before a caller-owned edit:

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO")
research_frame = bars.frame.copy(deep=True)
research_frame["dollar_volume"] = research_frame["close"] * research_frame["volume"]
```

The derived column does not belong to the exact `BarSet` contract, so it stays in a separate
research frame.

## Explicit persistence

Provider calls return values only. They do not discover a database or open an implicit
connection. `DuckDBStore.save` is a separate operation, which makes data-retention choices
reviewable and testable.

The raw cache and DuckDB store deliberately retain different representations. Raw payloads
help reproduce parsing and work offline. DuckDB retains exact normalized acquisition snapshots
for typed loads and row-level cumulative datasets for scoped research queries.

## Explicit calculations

General analysis works on ordinary numeric frames. Result-specific analysis accepts a model
object only when it needs normalized structure, such as bar fields, option contract terms, or
top-of-book sides.

Plotting follows the same rule. A function may perform a simple named presentation transform,
but calculations with meaningful policy stay visible in analysis code. For example, callers
calculate returns and annualized rolling volatility before plotting them.

Point-in-time research is a focused boundary beside ordinary transforms and analysis. It
accepts normalized vintage histories and pandas frames. It records caller-selected publication
lag, observation-date field, maximum staleness, label horizon, and temporal split boundaries.
Factor functions then fit caller-defined time-series, rolling, cross-sectional, or Fama-MacBeth
regressions. They do not define or download factors. Factor-risk and portfolio-forecast objects
carry the supplied exposure, premium, covariance, residual, contribution, and `as_of` choices
forward without becoming a general experiment registry or model-training framework.

Portfolio research begins with caller-supplied signals, returns, prices, covariance matrices,
and tradeability. Construction records unconstrained and final weights, cash, exposure, turnover,
covariance risk, and constraint use. Backtesting maps signal observations to explicit decisions
and holding periods. It reconciles beginning holdings, asset and cash returns, trades, linear
costs, ending holdings, and equity. It remains a portfolio-level research model and does not
represent exchange execution.

The strategy lifecycle begins from Trading Engine's fixed initialized catalog and immutable event
context. `BaseStrategy` owns bounded history, global and per-security warm-up, selection and
rebalance schedules, universe changes, and typed hook dispatch. `CompositeStrategy` adds one
alpha-to-target pipeline with replaceable components and inspectable decision traces. Target
helpers complete the fixed catalog under an explicit removal policy. Filled positions, working
orders, and marked portfolio values always come from the engine context.

## External execution-research boundary

The `persistra.integrations.trading_engine` package connects portfolio research to a separate
Trading Engine executable through deterministic files and a subprocess. Persistra owns normalized
bars, target weights or quantities, explicit clock and sizing policies, scenario construction,
artifact hashes, journal import, and analysis. Trading Engine owns causal event sequencing,
orders, risk, fills, exact accounting, valuation, and the normative execution rules.

The scenario boundary accepts synchronized raw intraday bars, explicit per-slice FX marks and
corporate actions, multi-currency cash ledgers, and optional signed portfolio targets.
Model-based runs serialize a versioned JSON Lines stream with a static header, causally adjacent
slice and intent records, and a required terminal count. An empty schedule can instead be paired
with an external strategy process. The engine sends typed initialization and event contexts over
a separate synchronous JSON Lines protocol and records both directions in a transcript. It does
not turn daily calendar labels into event instants or use adjusted prices for share-and-cash
accounting. The engine records each order's replay-clock `created_at`. A later slice is executable
only when its start is not earlier than that creation time.

The runner passes explicit arguments without a shell. It preflights every bundle artifact,
negotiates the versioned contract and selected scenario format through machine-readable engine
capabilities, validates the scenario before replay, stages and reconciles the journal, verifies
embedded scenario identity, and stages a deterministic manifest binding contract, source
revisions and dirty states, scenario format, scenario, journal, and executable hashes. It then
publishes the journal, optional transcript, and manifest as one rollback-safe final group.
External runs also bind the strategy executable, declared strategy inputs, reported identity,
and complete transcript. Journal import requires v3 on every record, deterministic event IDs, a
prior-event causal graph,
`run_started`, complete-slice valuations with per-currency and signed per-instrument attribution,
and a terminal `run_completed` record. It causally reconciles corporate actions, short borrow,
risk-limited fills, margin calls, and liquidation. Normalized frames retain convenient floats
beside exact nullable `*_micros` integers.

Execution performance remains event-time data. Annualized statistics require a caller-supplied
scale. A comparison with `BacktestResult` also keeps the model boundary visible: the vectorized
path is close-to-close, while the engine uses later eligible slice execution. Its additive P&L
bridge labels the balancing partial-execution and model residual instead of calling the complete
gap slippage.

The engine never reads Persistra's DuckDB tables, and Persistra does not import engine internals.
This boundary does not provide broker connectivity or live trading.

## Extend a strategy pipeline

A reusable strategy component should:

1. Declare its observation and per-security history requirements.
2. Consume only completed data and the immutable `StrategyView`.
3. Return one typed forecast, target transformation, or guard decision.
4. Keep estimation, portfolio construction, and execution state separate.
5. Use authoritative filled positions when turnover or target drift matters.
6. Remain testable without starting a subprocess.

Compose those components under one `CompositeStrategy` so a rebalance produces at most one
complete target intent. Use the engine replay to test behavior that depends on orders and fills.

## Extend a provider adapter

A new provider adapter should:

1. Isolate transport and response classification.
2. Translate source identities and observations into existing normalized contracts.
3. Preserve provider fields needed for time, entitlement, units, and provenance.
4. Record safe schema drift or fail malformed required values.
5. Implement only the capability protocols it actually supports.
6. Leave storage, analysis, and plotting to their existing layers.

This design keeps downstream code stable around data meaning rather than provider envelopes.
