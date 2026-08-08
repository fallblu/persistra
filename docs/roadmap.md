# 4.0.0 roadmap

This roadmap defines the complete boundary for the future 4.0.0 release. The remaining work
has four workstreams: equity signal research, portfolio construction with vectorized
backtesting, visualizations for the new research capabilities, and a final documentation
review. Work outside these sections is not a 4.0.0 requirement.

Jupyter notebooks, generated figures, live provider data, research caches, and credentials
must remain outside this repository. Notebook-based verification should use a separate WSL
workspace such as `~/research/visualization-gallery/`.

## Expand equity signal research

**Status: Complete.**

### Equity signal evaluation

The public research API now uses aligned date-by-asset panels with explicit fixed-universe
columns. It provides cross-sectional ranking, quantile clipping, standardization, group and
numeric exposure neutralization, explicit forward-return labels, Pearson and rank information
coefficients with sample counts, and time-varying group summaries.

Equal-weight quantile results expose assignments, forward returns, asset counts,
top-minus-bottom spreads, one-way turnover, and capacity-oriented volume summaries. Benchmark
comparisons report pairwise statistics. Bonferroni and Benjamini-Hochberg corrections operate on
explicit repeated-search p-values. Expanding and rolling temporal splits record label-window
purges and observation-count embargoes separately.

Deterministic tests exercise lagged price momentum and volume-trend signals across multiple
periods and fixed-universe slices. They also compare candidate returns with a simple benchmark.
This controlled validation checks calculation and stability behavior without presenting the
universe as a survivorship-free historical market sample. Live data and notebook studies remain
outside the repository.

Fundamental factors from present-day company snapshots remain out of scope. Fundamental research
requires point-in-time filings and a survivorship-aware security universe, with explicit
identity, filing-amendment, taxonomy, and availability semantics. It still requires a separate
design review before entering the 4.0.0 scope.

### Research artifact reproducibility

The versioned JSON research manifest records dataset scopes, normalized schema versions, content
or stored snapshot identities, feature, label, split, and benchmark parameters, Persistra and
direct dependency versions, random seeds, external execution status, and SHA-256 output artifact
identities. Read and write helpers validate the complete portable schema.

The implementation remains a transparent file contract. It does not introduce a managed
experiment database or CLI.

## Add portfolio construction and vectorized backtesting

**Status: Complete.**

### Construct portfolios

The public portfolio API constructs explicit date-by-asset targets with equal and
signal-proportional weighting. It supports long-only and long-short configurations, gross and
net targets, hard gross, net, position, and one-way turnover limits, capped side
redistribution, explicit infeasibility errors and numerical tolerances, and residual cash.
Deterministic daily, weekly, monthly, quarterly, and observation-count schedules select only
dates present in the supplied index.

Supplied date-specific covariance matrices support annualized volatility targets and ceilings.
The result reports achieved volatility, covariance risk contributions, exposures, cash,
turnover, unconstrained signal weights, and constraint utilization. Risk scaling preserves
relative weights and stops at exposure limits. No solver dependency or optimization API was
added; transparent construction meets the current research requirements without it.

### Implement vectorized backtesting

The vectorized simulator rebalances explicit targets over supplied return or price panels. Its
timing policy maps signal observations to decisions and first holding periods with separate
lags. Targets can remain active until the next rebalance or exit after a fixed observation
count. Same-period application requires an explicit assertion that the signal was available
before the assumed trade; the default applies weights one period later.

Strict or zero-return missing-data policies and strict or hold nontradeable policies make each
assumption explicit. The simulator accounts for residual cash, short proceeds, negative cash
under leverage, supplied cash returns, weight drift, one-way turnover, and per-asset linear
transaction costs. Results expose target, beginning, and ending weights, trades, returns,
equity, drawdown, exposures, turnover, asset and cash return attribution, cost attribution, and
rebalance diagnostics. Static weight and changing target benchmarks support explicit static
and naive signal comparisons under the same simulation assumptions.

Result validation reconciles beginning and ending asset weights with cash, asset and cash
contributions with gross returns, costs with net returns, and returns with equity. Unit and
contract tests cover construction, constraints, covariance controls, causal timing, prices and
returns, policies, cash, leverage, costs, fixed holding periods, benchmarks, and accounting.
The implementation remains at portfolio-level research and does not add orders, fills, partial
execution, intraday event loops, exchange latency, order books, broker integration, or live
trading.

## Add research and portfolio visualizations

**Status: Complete.**

### Visualize signal research

Thirteen public research helpers now cover cross-sectional distributions, ranks, group
comparisons, information coefficients through time and across horizons, quantile returns and
spreads, quantile counts, turnover, capacity, stability, and benchmark comparisons. They return
caller-owned Matplotlib axes and compose with the existing general plotting helpers.

Titles, labels, annotations, and legends keep dates, horizons, statistics, aggregations,
quantiles, benchmarks, sample counts, and coverage explicit where they affect interpretation.
Cumulative quantile performance rejects overlapping forward-return horizons because those labels
do not define a valid wealth path. Missing observations remain gaps rather than being silently
filled.

### Visualize portfolio construction and backtests

Fourteen public portfolio helpers now cover target, unconstrained, realized, and ending weights;
cash; gross and net exposure; constraint utilization; predicted volatility and covariance risk
contributions; returns, cumulative performance, drawdowns, and rolling volatility; turnover and
transaction costs; return and cost attribution; and rebalance diagnostics. Exact asset-to-group
mappings enable group attribution without guessing from partial metadata.

Backtest plots expose decision, execution, and holding policies and retain the simulator's
accounting definitions. Rebalance diagnostics distinguish requested trades, executed trades,
and blocked nontradeable assets. Signal attribution remains absent because the result does not
expose signal-level contributions, and the plots do not imply orders, fills, or intraday
execution that the vectorized simulator does not model.

### Extend and verify the visualization gallery

The external gallery contains three materially different controlled cases for each of the 27 new
helpers, for 81 cases in total. The cases cover baseline, changed-regime, sparse, long-only,
long-short, and blocked-trade conditions in caller-owned, small, large, and panel layouts. Every
case passed manual review after corrections to annotation placement, date formatting, timing
titles, and rebalance axes were re-run.

The gallery records coverage, review decisions, resolved issues, data scope, parameters,
Persistra identity, and dependency versions. Automated tests cover the behavior that does not
require visual judgment. Gallery notebooks, generated figures, provider data, caches, and
credentials remain outside this repository and its built distributions.

## Complete the documentation suite

Perform a final review of the complete documentation suite after the public API is stable.
Ensure that API references, guides, examples, navigation, package metadata, and the changelog
agree with the implemented 4.0.0 behavior. Remove stale descriptions and examples, standardize
terminology, verify cross-references and executable examples, and polish the documentation as a
cohesive introduction to the release rather than a record of its development.

Run the complete contribution gate against the release candidate. Immediately before the
v4.0.0 release, remove this roadmap and every navigation entry or cross-reference that points to
it.

## 4.0.0 acceptance criteria

The 4.0.0 release is ready when all of the following are true:

- Cross-sectional transforms, explicit forward labels, information coefficients, quantile
  summaries, overlapping-label protections, and benchmark comparisons have typed, tested
  public contracts.
- The signal evaluation capabilities have been checked across periods and fixed universes
  against simple baselines without making survivorship-free claims.
- A reproducibility manifest records data identity, research parameters, environment versions,
  randomness, execution status, and artifact checksums.
- Portfolio construction supports the documented weighting methods, constraints, risk controls,
  cash treatment, configurations, and deterministic rebalance schedules.
- The vectorized simulator enforces causal signal timing, applies costs and turnover, handles
  missing or nontradeable assets explicitly, and reconciles all reported results.
- Built-in visualizations cover the implemented signal research, portfolio construction, and
  backtesting workflows, as well as other notable gaps identified during implementation.
- Every new public plotting helper has multiple materially different cases in the external
  visualization gallery, and all cases pass manual review after accepted fixes are implemented.
- No gallery notebook, generated figure, live provider dataset, research cache, or credential is
  present in the repository or built distributions.
- Public schemas, documentation, package metadata, changelog, and built artifacts agree on the
  4.0.0 boundary.
- The documentation suite is current and polished, and this roadmap and all references to it
  have been removed immediately before release.
- The complete contribution gate passes, including lint, strict typing, coverage,
  documentation, package installation, dependency checks, and public import checks.
