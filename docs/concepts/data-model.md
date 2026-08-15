# Data model

Persistra's model separates identity, observations, and provenance. Exact pandas schemas make
missingness, time, units, and applicability part of the public contract rather than informal
column conventions.

## Identity objects

`Instrument` represents an equity, ETF, mutual fund, index, fiat pair, crypto pair, or
commodity. Pair instruments require both base and quote currencies.

```python
from persistra.model import Instrument, InstrumentKind

pair = Instrument(
    instrument_id="eur-usd",
    kind=InstrumentKind.FIAT_PAIR,
    display_name="EUR/USD",
    base_currency="EUR",
    quote_currency="USD",
)
```

`Listing` contains venue-specific identity such as exchange, MIC, currency, and source
timezone. `ProviderSymbol` connects a provider key to one instrument or listing.

`SeriesDefinition` describes a commodity or economic scalar series with its provider key,
native frequency, unit, geography, seasonal adjustment, and maturity.

`OptionContract` represents provider-scoped option terms. Normalized historical chains store
equivalent terms in their contract frame so many contracts can share one result efficiently.

## Stable provider-scoped IDs

Use the helper functions when a source has no cross-provider canonical mapping:

```python
from persistra.model import (
    InstrumentKind,
    provider_instrument_id,
    provider_series_id,
)

instrument_id = provider_instrument_id(
    "example_provider",
    InstrumentKind.EQUITY,
    "DEMO",
)
series_id = provider_series_id(
    "example_provider",
    "CPI",
    "monthly",
)
```

The functions produce stable opaque IDs from normalized provider scope. They do not establish
equivalence with another source.

## Explicit catalogs

`Catalog` stores application-approved instrument and provider-symbol mappings in memory:

```python
from persistra.model import Catalog, Instrument, InstrumentKind, ProviderSymbol

instrument = Instrument("company-a", InstrumentKind.EQUITY, "Company A")
mapping = ProviderSymbol(
    provider="example_provider",
    kind=InstrumentKind.EQUITY,
    symbol="CMPA",
    instrument_id=instrument.instrument_id,
)

catalog = Catalog()
catalog.add_instrument(instrument)
catalog.map_provider_symbol(mapping)

resolved = catalog.resolve("example_provider", "equity", "CMPA")
assert resolved == instrument
```

Mappings cannot refer to an unknown instrument or replace an existing provider key with a
different identity.

## Result objects

Normalized results carry the pieces a research workflow needs:

| Result | Identity | Observations | Provenance |
|---|---|---|---|
| `BarSet` | `instrument` | `frame` | `metadata` |
| `QuoteSet` | Per-row instrument IDs | `frame` | `metadata` |
| `TopOfBookSet` | Per-row instrument IDs | `frame` | `metadata` |
| `OptionChain` | Underlying scope and contract frame | `observations` | `metadata` |
| `SeriesSet` | `definition` | `frame` | `metadata` |
| `VintageSeriesSet` | `definition` | Versioned `frame` | `metadata` |
| `VintageDatesResult` | Provider series key | Sorted change dates | `metadata` |
| Reference results | Query or provider scope | `frame` | `metadata` |
| Scalar quote results | Scalar identity fields | Dataclass fields | `metadata` |

Every frame validates exact column order, pandas dtypes, sort order, unique keys, and
family-specific numeric constraints. See [Normalized schemas](../reference/schemas.md) for
the complete tables.

## Missing values are meaningful

Nullable pandas dtypes distinguish missing applicability from zero. For example:

- A daily bar's `timestamp` is missing because `date` applies.
- An intraday bar's `date` is missing because `timestamp` applies.
- Volume can be missing for a source that does not report it.
- A missing bid or ask does not mean a price of zero.
- A scalar series can retain a dated missing source observation without interpolation.
- A vintage series distinguishes a source deletion from a reported missing numeric value.

Persistra validates finite observed numeric values. It preserves allowed missing values and
rejects infinities or impossible sign constraints.

## Frame ownership

Result constructors validate a deep copy, but pandas frames remain mutable objects. Do not
add research columns to the frame inside a normalized result. Copy it first:

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO")
derived = bars.frame.copy(deep=True)
derived["range"] = derived["high"] - derived["low"]
```

Use Persistra transforms to produce research frames when one exists for the task.

## Provenance objects

Every acquisition result contains `ResultMetadata`, including:

- provider and operation
- copied, redacted request parameters
- timezone-aware retrieval time
- optional provider as-of time
- entitlement mode
- raw-cache status
- normalized schema version
- nonfatal schema diagnostics

Required provenance never depends on `DataFrame.attrs`, which pandas operations can drop.

## Research result objects

Point-in-time research uses separate typed outputs so information sets and future outcomes do
not collapse into one frame:

| Result | Values | Temporal policy or provenance |
|---|---|---|
| `VintageSelection` | Applicable normalized source rows | Knowledge date, publication lag, source identity, and retrieval time |
| `FeaturePanel` | Features indexed by decision date | Per-match source-version provenance and per-feature policies |
| `ForwardReturnLabels` | Future simple returns | Observation-count horizon and actual label end dates |
| `TemporalSplit` | Ordered training and evaluation indexes | Separately recorded purged and embargoed observations |
| `ResearchSummary` | Coverage and regime statistics | Optional volatility annualization scale |
| `InformationCoefficientResult` | Pearson and rank correlations with counts | Forward-label horizon and optional grouping |
| `QuantilePortfolioResult` | Assignments, returns, spreads, counts, turnover, capacity, and summaries | Forward-label horizon and quantile count |
| `GroupSignalResult` | Signal and forward-return statistics by classification | Forward-label horizon |
| `BenchmarkComparison` | Candidate-minus-benchmark paths and summaries | Explicit benchmark name |
| `MultipleTestingResult` | Raw and adjusted p-values with rejection decisions | Correction method and significance level |
| `ResearchManifest` | Dataset, parameter, environment, randomness, execution, and artifact identities | Versioned portable JSON contract |

These objects validate and copy their pandas inputs. Their frames remain mutable pandas
objects after construction, so treat them as returned values rather than immutable storage.

## Portfolio result objects

Portfolio construction and backtesting also keep policy beside calculated paths:

| Result | Values | Recorded policy |
|---|---|---|
| `PortfolioConstructionResult` | Unconstrained and final weights, cash, exposure, turnover, covariance risk, and constraint use | Weighting method, configuration, constraints, and risk control |
| `BacktestResult` | Beginning and ending holdings, returns, equity, drawdown, trades, turnover, costs, attribution, rebalance diagnostics, and benchmark paths | Signal timing, missing-return policy, nontradeable policy, and accounting tolerance |

`PortfolioConstraints`, `PortfolioRiskControl`, `BacktestTiming`, and `BacktestPolicies` are
validated policy objects. They make position, exposure, volatility, turnover, timing, and
missing-data choices reviewable instead of encoding them in unstructured keyword mappings.

## Trading Engine integration results

Execution research uses typed policy and artifact objects around the external process boundary:

| Result | Values | Recorded policy or evidence |
|---|---|---|
| `TradingEngineScenario` | Exact instruments, synchronized market slices, portfolio and direct intents, risk, fees, and initial cash | Clock-derived event times, sizing profile, source identities, arbitrary metadata, and one base currency |
| `EngineRunResult` | Scenario and journal paths, process output, hashes, and imported replay | Explicit executable and completed process artifacts |
| `ExecutionReplayResult` | Bars, targets, orders, fills, cancellations, rejections, cash limits, valuations, metrics, raw events, and completion | Scenario SHA-256 plus optional scenario-owned cash and currency |
| `ExecutionAnalysisResult` | Lifecycle, order, fill, equity, return, drawdown, and performance frames | Initial-equity, annualization, turnover, and slippage-reference policy |
| `ExecutionComparisonResult` | Terminal model comparison and additive currency P&L bridge | Close-to-close baseline, engine execution basis, terminal alignment, and balancing residual method |

`BarClockPolicy`, `SizingPolicy`, `RiskPolicy`, and `ExecutionPolicy` keep scenario assumptions
beside the handoff. `ExecutionAnalysisPolicy` keeps event-time performance choices beside the
calculated output.

Imported price and money fields provide a float column for ordinary pandas analysis and a
matching nullable `Int64` `*_micros` column for exact reconciliation. Quantities and sequences
also retain nullable integer dtypes. `orders.created_at` is the engine replay time used with
slice sequence to establish causal fill eligibility. `RunCompletion` proves that the imported
journal reached its terminal valuation and order counts.

Read [Time and provenance](time-provenance.md) for the distinction among calendar labels,
event instants, provider as-of times, and retrieval times.
