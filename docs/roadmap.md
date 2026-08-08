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

Portfolio work depends on credible signal evaluation. It should support research questions,
not emulate an exchange.

### Construct portfolios

Start with explicit target weights and transparent methods:

- Equal weighting and signal-proportional weighting
- Gross, net, position, and turnover constraints
- Volatility targeting and simple covariance-based risk controls
- Long-only and long-short configurations
- Cash as an explicit residual
- Deterministic rebalance schedules

Add optimization only with clear infeasibility behavior, numerical tolerances, and benchmark
comparisons. Select an established solver library after checking its current Python support,
license, failure modes, and installation cost.

### Implement vectorized backtesting

Implement a simple rebalance-to-target-weight simulator over supplied returns or prices. Keep
the scope at portfolio-level research:

- Explicit signal observation, decision, and holding periods
- Lagged weight application
- Configurable linear transaction costs and turnover
- Missing-price and nontradeable-asset policies
- Cash and leverage accounting
- Returns, equity, drawdown, exposures, turnover, and cost attribution
- Comparison with static and naive signal benchmarks

Reject same-period signal use unless the input contract proves that the signal was available
before the assumed trade. Reconcile results from holdings, returns, cash, and costs.

Do not add orders, fills, partial execution, intraday event loops, exchange latency, order
books, broker integration, or live trading.

## Add research and portfolio visualizations

Build plotting capabilities on the completed signal research, portfolio construction, and
backtesting APIs. Review the existing built-in visualizations before adding helpers, reuse their
conventions where they remain appropriate, and fill other notable gaps discovered during that
review. Do not duplicate a general helper when composition or a small extension provides an
honest presentation.

### Visualize signal research

Support the main diagnostics needed to evaluate cross-sectional signals. Include plot families
for:

- Cross-sectional signal distributions, ranks, and group comparisons
- Information coefficients through time, rolling summaries, and horizon comparisons
- Quantile forward returns, cumulative quantile performance, and top-minus-bottom spreads
- Quantile counts, turnover, and capacity-oriented volume summaries
- Stability comparisons across periods, universes, temporal splits, and benchmarks

Make sample counts and missing coverage visible when they affect interpretation. Keep horizons,
quantile definitions, benchmark choices, and aggregation methods explicit.

### Visualize portfolio construction and backtests

Support inspection of both portfolio decisions and simulated outcomes. Include plot families
for:

- Target and realized weights, cash, gross and net exposure, and constraint utilization
- Portfolio and benchmark returns, cumulative performance, and drawdowns
- Rolling volatility, risk contributions, and other implemented risk controls
- Turnover, transaction costs, and cost attribution through time
- Asset, group, and signal attribution when the underlying result exposes those components
- Rebalance diagnostics, including nontradeable assets and differences between target and
  realized holdings

Visualizations must preserve the timing and accounting semantics of the underlying result. They
must not imply execution detail that the vectorized simulator does not model.

### Extend and verify the visualization gallery

Update `~/research/visualization-gallery/` as each new helper is implemented. Add every new
public plotting helper to the gallery coverage matrix and exercise it with multiple materially
different cases. Use live provider data where appropriate and controlled research inputs where
they make timing, constraints, costs, or attribution easier to verify.

Review every new case for correct visual encoding, labels, units, scales, missing-data behavior,
accessibility, layout, and caller-owned axes. Record the data scope, parameters, Persistra
commit, and dependency versions needed to reproduce it. Track problems through correction and
re-run affected cases after implementation. Add automated unit, contract, and regression tests
for behavior that does not require visual judgment. Keep gallery notebooks, provider data,
rendered figures, caches, and credentials outside this repository.

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
