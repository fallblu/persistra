# Project roadmap

## Purpose

Persistra will become a point-in-time-aware toolkit for building reproducible quantitative
research datasets and evaluating financial hypotheses without hiding temporal assumptions.
It will remain local-first, usable without cloud infrastructure, and suitable for an
individual researcher working in Python and pandas.

The project should demonstrate two kinds of competence:

- Quantitative research that states a hypothesis, controls temporal leakage, uses meaningful
  baselines, and reports limitations.
- Software engineering that turns those practices into typed, tested, provider-neutral
  components with clear ownership boundaries.

Quantitative research is the primary product direction. Quantitative trading is secondary.
Trading capabilities should grow from validated research workflows instead of determining
the architecture prematurely.

## Current foundation

The current branch already provides a coherent primary-data pipeline:

- Provider-neutral contracts cover market bars, quotes, top of book, historical option
  chains, latest scalar series, vintage-aware scalar histories, and reference results.
- The Alpha Vantage adapter acquires the primary datasets available to the project's
  150-request-per-minute plan.
- The focused FRED and ALFRED adapter acquires source-level economic observations, explicit
  vintages, bounded revision histories, and series vintage dates at native frequencies.
- Raw caching and DuckDB storage keep provider responses separate from normalized snapshots,
  including provider-native `VintageSeriesSet` histories.
- Retrieval-time revisions preserve what Persistra observed, while ALFRED availability
  intervals separately record when source versions applied.
- Explicit transforms align, pivot, as-of match, and resample observations.
- Point-in-time feature panels separate observable inputs from explicit forward-return labels.
  Temporal splits and regime summaries preserve horizons, provenance, coverage, and sample counts.
- Analysis and Matplotlib modules cover core market, options, and economic calculations.
- Five output-free cross-asset notebooks carry predeclared hypotheses from live acquisition
  through baselines, point-in-time comparisons, sensitivity analysis, and critical interpretation.
- Public signatures, normalized schemas, provider diagnostics, and deterministic processing
  have passed a focused release-contract review.
- Synthetic data, strict typing, schema validation, offline tests, redacted live
  certification, and package checks support development without exposing credentials or
  provider data.

The dated [foundation assurance report](foundation-assurance.md) records the completed Alpha
Vantage live certification, controlled edge cases, API review, deterministic checks,
supported Python matrix, and dependency bands. A separate opt-in live test certifies focused
FRED and ALFRED acquisition, caching, and offline replay without emitting source values.

This foundation is stronger as a data library than as a complete research product. Its main
near-term gaps are:

- It does not yet evaluate cross-sectional equity signals or rank competing signal definitions.
- It does not construct portfolios or simulate a rebalanced strategy.

## Guiding principles

### Put temporal correctness before model complexity

Every research input must distinguish the observation period, source availability, retrieval
time, and any later revision. A result is not point-in-time safe merely because it was loaded
with an as-of join.

### Keep research policy visible

Library functions may enforce timing and calculate general diagnostics. The caller must still
choose the universe, hypothesis, feature definition, regime definition, horizon, benchmark,
and missing-data policy.

### Separate observable features from future labels

APIs should make it difficult to place forward returns or revised economic observations in a
feature matrix by accident. Feature availability and label horizons must be explicit.

### Prefer small composable capabilities

Add a provider capability protocol or focused analysis function when it creates a stable
boundary. Do not add an experiment framework, plugin system, or strategy engine merely to
connect a few functions.

### Treat empirical claims as tested outputs

A notebook should report sensitivity, uncertainty, failed hypotheses, and data limitations.
It should not turn descriptive regime differences into claims of prediction or profitability.

### Preserve the local-first operating model

The supported workflow must run on one Linux workstation with local files, DuckDB, and public
or personally licensed APIs. Cloud services must not be required.

## Dependency sequence

The main path to the next release is:

```text
equity signal evaluation
        -> portfolio construction
        -> vectorized backtesting

stable panels + temporal evaluation + conventional baselines
        -> topological-data-analysis replication
        -> out-of-sample TDA experiments
```

Work may proceed in parallel when it does not bypass these dependencies. Release evidence can
advance independently of the longer-term equity, portfolio, backtesting, and TDA paths.

## Before 4.0.0

### Release acceptance

The release is ready when all of the following are true:

- The foundation assurance remains current, or a later certification records any provider or
  entitlement limitation explicitly.
- FRED or ALFRED data pass through acquisition, raw caching, normalization, DuckDB storage,
  point-in-time selection, analysis, and visualization without provider-specific logic leaking
  into downstream layers.
- Tests demonstrate that revised future data cannot affect an earlier point-in-time dataset.
- The output-free cross-asset study suite runs from documented inputs and uses only public APIs.
- The studies contain honest comparisons of latest-revised and vintage-correct research.
- Public schemas, package metadata, changelog, documentation, and built artifacts agree on the
  4.0.0 product boundary.
- The full contribution gate passes, including strict typing, coverage, documentation,
  dependency bands, package installation, and public import checks.

The release does not require equity factor research, portfolio optimization, backtesting, or
TDA. These should not delay a complete point-in-time research product.

## Near-term research expansion

### Develop equity signal evaluation

Build cross-sectional research on the point-in-time feature construction and temporal
evaluation boundary. Begin with price- and volume-derived signals on an explicit fixed
universe. Do not present that universe as a survivorship-free historical market sample.

Useful general capabilities include:

- Cross-sectional ranking, clipping, standardization, and neutralization
- Forward returns at explicit horizons
- Pearson and rank information coefficients with sample counts
- Quantile portfolio summaries, spreads, turnover, and capacity-oriented volume summaries
- Sector or group summaries when trustworthy classifications are available
- Purged or embargoed temporal evaluation when label windows overlap
- Benchmark comparisons and correction for repeated hypothesis searches

The first factor study should compare a small number of economically motivated signals with
simple baselines. It should emphasize stability across periods and universes instead of the
best aggregate statistic.

Fundamental factors require point-in-time filings and a survivorship-aware security universe.
Do not build them from present-day company snapshots. A later SEC EDGAR adapter is a plausible
local, no-cloud direction, but its identity, filing-amendment, taxonomy, and availability
semantics require a separate design review.

### Extend research artifact reproducibility

The cross-asset studies display an in-memory manifest with data scopes, analysis dates,
features, horizons, thresholds, staleness policies, and dependency versions. They intentionally
retain no provider snapshots or derived outputs, so an old empirical result cannot be recreated
exactly after a provider revision.

Generalize the manifest only when another research workflow demonstrates a need. Potential
extensions include normalized schema versions, feature and split parameters, random seeds for
stochastic algorithms, and content identities for inputs that may be retained and redistributed
safely. Checksums and execution status belong only to artifacts whose terms permit storage.
This should remain a transparent record, not a managed experiment database. A CLI is justified
only if repeated acquisition or notebook execution becomes awkward through the Python API.

## Portfolio construction and vectorized backtesting

Portfolio work depends on credible signal evaluation. It should support research questions,
not emulate an exchange.

### Portfolio construction

Start with explicit target weights and transparent methods:

- Equal weighting and signal-proportional weighting
- Gross, net, position, and turnover constraints
- Volatility targeting and simple covariance-based risk controls
- Long-only and long-short configurations
- Cash as an explicit residual
- Deterministic rebalance schedules

Optimization should arrive only with clear infeasibility behavior, numerical tolerances, and
benchmark comparisons. Select an established solver library after checking its current Python
support, license, failure modes, and installation cost.

### Vectorized backtesting

Implement a simple rebalance-to-target-weight simulator over supplied returns or prices. Keep
the scope at portfolio-level research:

- Explicit signal observation, decision, and holding periods
- Lagged weight application
- Configurable linear transaction costs and turnover
- Missing-price and nontradeable-asset policies
- Cash and leverage accounting
- Returns, equity, drawdown, exposures, turnover, and cost attribution
- Comparison with static and naive signal benchmarks

The simulator must reject same-period signal use unless the input contract proves that the
signal was available before the assumed trade. Results should reconcile from holdings,
returns, cash, and costs.

This horizon excludes orders, fills, partial execution, intraday event loops, exchange
latency, order books, broker integration, and live trading. Those features would create a
different product and are not a current objective.

## Experimental topological research

TDA should begin only after Persistra can build stable panels, enforce causal timing, create
temporal splits, and compare ordinary baselines. It should remain an optional research
capability so specialized dependencies do not burden the base installation.

### Replicate before extending

Begin with a documented reproduction of published persistent-homology work on financial
stress and crash regimes. Useful starting points include
[Landscapes of Crashes](https://arxiv.org/abs/1703.04385) and the
[persistent-homology turbulence index](https://arxiv.org/abs/2203.05603).

The replication should specify:

- Asset universe, return definition, scaling, and missing-data policy
- Sliding-window length and embedding construction
- Filtration, homology dimensions, distance metric, and persistence summary
- Exact causal timestamp assigned to each computed feature
- Conventional volatility, correlation, and drawdown baselines
- Sensitivity to window, normalization, universe, and crisis definitions
- Computational cost and deterministic behavior

Match the published setup before changing it. Report discrepancies rather than tuning them
away.

### Test incremental value

After replication, test whether topological features provide information beyond simpler
statistics. Use locked temporal evaluation, predeclared metrics, and several market regimes.
Separate contemporaneous stress measurement from early warning or return prediction.

A useful result can be negative. Demonstrating that a complex topological statistic adds no
stable value beyond volatility or correlation is still credible quantitative research when
the experiment is well controlled.

Only after these tests should Persistra expose general TDA transforms or connect topological
features to portfolio decisions.

## Long-term possibilities

Consider these directions only when a preceding research workflow demonstrates demand:

- SEC filing and company-facts acquisition with point-in-time amendment handling
- Survivorship-aware universe snapshots and corporate-action-aware total returns
- Additional market-data providers that implement existing capability protocols
- Columnar interchange or Parquet export for datasets too large for notebook workflows
- Performance benchmarks and chunked transformations for larger universes
- Richer covariance, risk-model, and attribution tools
- A small command-line interface for repeatable acquisition and notebook execution

Do not add dynamic provider plugins, distributed execution, managed cloud storage, a web
dashboard, an event-driven backtester, or live trade execution without a new product decision.

## Decision gates

Each gate requires a short design interview before implementation:

| Gate | Decision required | Evidence needed |
|---|---|---|
| Equity factors | Fixed universe or historical membership source; price-only or filing-derived scope | Bias inventory and provider feasibility review |
| Portfolio optimization | Methods, constraints, solver, and failure behavior | Baseline portfolios and numerical edge-case tests |
| Vectorized backtest | Timing convention, costs, missing data, and accounting equations | Hand-calculated fixtures and reconciliation tests |
| TDA | Paper, dependency, reproduction tolerance, and evaluation protocol | Reproduction plan and conventional baseline implementation |

## Measures of progress

Progress is demonstrated by evidence rather than feature count:

- A user can identify what was known, when it was known, and which source version was used.
- A future revision cannot change a past research feature silently.
- A second provider uses the normalized architecture without Alpha Vantage assumptions.
- The research notebook suite can be rerun and can explain both positive and negative findings.
- New analysis functions have explicit statistical conventions and adversarial tests.
- Portfolio results reconcile and make turnover, costs, and timing visible.
- Complex methods beat meaningful simple baselines out of sample or are rejected honestly.
