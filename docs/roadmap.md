# 4.0.0 roadmap

This roadmap defines the complete boundary for the future 4.0.0 release. The release has
three workstreams: a manual overhaul of every built-in visualization, equity signal research,
and portfolio construction with vectorized backtesting. Work outside these sections is not a
4.0.0 requirement.

Jupyter notebooks, generated figures, live provider data, research caches, and credentials
must remain outside this repository. Notebook-based verification should use a separate WSL
workspace such as `~/research/visualization-gallery/`.

## Verify and improve every built-in visualization

Build an extensive external visualization gallery and use it to review the complete public
plotting API against varied live data. Treat the gallery as a manual certification environment,
not as package documentation or an automated test suite.

### Build the external gallery

Organize a collection of Jupyter notebooks by visualization family in the external workspace.
Use the public Persistra API and live Alpha Vantage, FRED, or ALFRED data as appropriate. Keep
provider credentials in environment variables and keep downloaded data and rendered output
outside the repository.

Start with a coverage matrix for every public plotting helper:

- General: `plot_series`, `plot_rebased`, `plot_distribution`,
  `plot_rolling_statistic`, `plot_correlation`, and `plot_coverage`
- Market: `plot_candlesticks`, `plot_returns`, `plot_cumulative_returns`,
  `plot_drawdowns`, `plot_rolling_volatility`, `plot_bid_ask_history`, and
  `plot_spread_history`
- Options: `plot_option_chain_prices`, `plot_option_volume_open_interest`,
  `plot_implied_volatility_smile`, `plot_implied_volatility_surface`, and
  `plot_greek_profile`
- Economics: `plot_scalar_series`, `plot_series_change`, `plot_yield_curve`, and
  `plot_yield_curve_history`

Exercise every helper in multiple materially different cases. Select cases that expose the
dimensions relevant to each plot instead of repeating the same shape with different symbols.
Across the gallery, cover:

- Short and long histories, multiple frequencies, and dense and sparse observations
- Single-series and multi-series inputs with different units, scales, and name lengths
- Calm and volatile periods, positive and negative returns, deep drawdowns, and recoveries
- High- and low-volume instruments, price gaps, irregular observations, and missing values
- Narrow and wide spreads and bid-ask histories with changing liquidity
- Calls and puts, near and distant expirations, narrow and broad strike ranges, thin chains,
  volatility skew, and incomplete strike-expiration grids
- Economic levels, rates, growth series, mixed release frequencies, yield-curve inversions,
  and changing curve shapes
- Default axes and caller-owned axes in small, large, and multi-panel figures

Record enough provenance to reproduce each case: the provider, dataset scope, retrieval time,
query parameters, Persistra commit, and direct dependency versions. Do not record credentials
or copy provider data into the repository.

### Review the gallery

Review every rendered case manually. Evaluate:

- Whether the visual encoding states the data correctly
- Titles, axis labels, units, legends, ticks, date formatting, and time zones
- Scale selection, baselines, ordering, aggregation, and treatment of missing data
- Color contrast, line and marker distinction, and readability without relying on color alone
- Layout, spacing, clipping, density, and legibility across figure sizes
- Consistency across related helpers and predictable behavior with caller-owned axes
- Warnings or failures for inputs that cannot produce an honest visualization

Track every case as accepted or needing work. For each problem, record the input conditions,
expected presentation, observed presentation, and proposed correction.

### Iterate on a visual overhaul branch

Create a dedicated visual overhaul feature branch from `develop`. Implement accepted fixes and
improvements in the library. Add normal unit, contract, or regression tests for behavior that
can be verified automatically; do not add gallery notebooks or screenshot baselines to the
repository.

After each coherent group of changes:

1. Run the complete contribution gate.
2. Re-run every affected external gallery case against the branch.
3. Inspect the updated figures and check related helpers for regressions.
4. Update the external coverage and review records.

Repeat the review and improvement cycle until the complete gallery is accepted. Before release,
regenerate the public plotting inventory from the release candidate and add gallery cases for
any helper introduced or renamed during the overhaul.

## Expand equity signal research

### Develop equity signal evaluation

Build cross-sectional research on the point-in-time feature construction and temporal
evaluation boundary. Begin with price- and volume-derived signals on an explicit fixed
universe. Do not present that universe as a survivorship-free historical market sample.

Add general capabilities for:

- Cross-sectional ranking, clipping, standardization, and neutralization
- Forward returns at explicit horizons
- Pearson and rank information coefficients with sample counts
- Quantile portfolio summaries, spreads, turnover, and capacity-oriented volume summaries
- Sector or group summaries when trustworthy classifications are available
- Purged or embargoed temporal evaluation when label windows overlap
- Benchmark comparisons and correction for repeated hypothesis searches

Validate the capabilities with a small number of economically motivated signals and simple
baselines. Emphasize stability across periods and universes instead of the best aggregate
statistic. Keep this validation outside the repository when it uses live data or notebooks.

Do not build fundamental factors from present-day company snapshots. Fundamental research
requires point-in-time filings and a survivorship-aware security universe, with explicit
identity, filing-amendment, taxonomy, and availability semantics. Complete a separate design
review before adding any such capability to the 4.0.0 scope.

### Improve research artifact reproducibility

Add a lightweight manifest that records:

- Dataset scopes and normalized schema versions
- Content identities or stored snapshot identities
- Feature, label, split, and benchmark parameters
- Library and direct dependency versions
- Random seeds when an algorithm uses randomness
- External research execution status and output artifact checksums

Keep the manifest transparent and portable. Do not introduce a managed experiment database.
Add a CLI only if repeated acquisition or external research execution becomes awkward through
the Python API.

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

## 4.0.0 acceptance criteria

The 4.0.0 release is ready when all of the following are true:

- The external coverage matrix includes every public plotting helper in the release candidate,
  with multiple materially different live-data cases for each helper.
- The complete external visualization gallery has passed manual review, and every accepted fix
  has passed another gallery review after implementation on the visual overhaul branch.
- No gallery notebook, generated figure, live provider dataset, research cache, or credential is
  present in the repository or built distributions.
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
- Public schemas, documentation, package metadata, changelog, and built artifacts agree on the
  4.0.0 boundary.
- The complete contribution gate passes, including lint, strict typing, coverage,
  documentation, package installation, dependency checks, and public import checks.
