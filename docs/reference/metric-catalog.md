# Standard metric catalog: `persistra.standard@1`

`project.services.analysis.metrics.compute(run)` calculates only this catalog. The
catalog uses these conventions:

- `r_i` is a calculated subperiod TWR return.
- The ordinal of each `r_i` gives its ascending order.
- `rf_i` is the aligned risk-free return for the same period.
- A declared zero assumption adds the `analysis.risk_free.assumed_zero` warning.
- Excess return is `e_i = r_i - rf_i`.
- `b_i` is a benchmark return from `MetricInputs.benchmark_returns`.
- Benchmark returns use the same intervals as the run returns.
- `N` is the number of calculated returns.
- Sample standard deviation uses `ddof = 1`.
- One year is 365.25 days.
- The annualization factor is `A = N × year_seconds / elapsed_seconds`.
- The equity interval supplies `elapsed_seconds`.

A supplied input series must have correct alignment. Incorrect alignment causes
`AnalysisInputError` (`analysis.inputs.unaligned`) before calculation.

An optional input that is not in the inputs gives an explicit `missing_input` state.
An undefined denominator, insufficient `N`, or invalid base also gives a structured
state. The system does not give a clipped number.

| Metric | Definition | Unit | Min N |
| --- | --- | --- | --- |
| `total_return` | `product(1 + r_i) - 1` | `rate` | 1 |
| `annualized_return` | `(1 + total_return) ** (year / elapsed) - 1` | `rate` | 1 |
| `money_weighted_return` | dated root of initial/final NAV and normalized external cash flows | `rate` | 2 equity rows |
| `annualized_volatility` | `std(r_i) × sqrt(A)` | `rate` | 2 |
| `sharpe` | `mean(e_i) / std(e_i) × sqrt(A)` | `ratio` | 2 |
| `max_drawdown` | `min_t(index_t / peak_t - 1)` on the compounded TWR index. The earliest peak wins ties. | `rate` | 1 |
| `drawdown_duration` | Elapsed days from peak to recovery on the TWR index. The state is `undefined` with `analysis.drawdown.unrecovered` without recovery. | `days` | 1 |
| `sortino` | `mean(e_i) / sqrt(mean(min(e_i, 0)**2)) × sqrt(A)` (full-sample downside, `ddof = 0`, target = risk-free) | `ratio` | 2 |
| `calmar` | `annualized_return / abs(max_drawdown)` | `ratio` | 1 |
| `var_historical` | Hyndman–Fan type-7 5th percentile of `r_i` (raw signed quantile) | `rate` | 20 |
| `expected_shortfall` | mean of `r_i <= var_historical` rows | `rate` | 20 |
| `skewness` | adjusted Fisher–Pearson sample skewness | `ratio` | 3 |
| `kurtosis` | sample excess kurtosis (Fisher) | `ratio` | 4 |
| `hit_rate` | `count(r_i > 0) / N` (zero counts as a miss) | `ratio` | 1 |
| `payoff_ratio` | `mean(gains) / abs(mean(losses))` | `ratio` | 1 for each side |
| `beta` | `cov(e_i, be_i) / var(be_i)` with `be_i = b_i - rf_i` | `ratio` | 2 |
| `alpha` | `(mean(e_i) - beta × mean(be_i)) × A` | `rate` | 2 |
| `active_return` | `mean(r_i - b_i) × A` | `rate` | 1 |
| `tracking_error` | `std(r_i - b_i) × sqrt(A)` | `rate` | 2 |
| `information_ratio` | `mean(r_i - b_i) / std(r_i - b_i) × sqrt(A)` | `ratio` | 2 |
| `turnover` | `sum(abs(fill notional)) / (2 × mean(nav)) × year / elapsed` | `rate` | 1 fill |
| `holding_period` | closed-notional-weighted mean days from lot open to relief | `days` | 1 closed lot |
| `concentration` | mean over valuation instants of `sum((abs(mv) / gross_mv)**2)` (HHI) | `ratio` | 1 |
| `cost_total` | total USD across all cost components | `usd` | 1 cost row |
| `cost_total_relative` | `cost_total / mean(nav)` | `rate` | 1 cost row |
| `cost_total.<component>` | USD total for each `component_kind` (one row for each available component) | `usd` | 1 |
| `cost_total_relative.<component>` | Component total divided by mean NAV | `rate` | 1 |
| `participation_mean` | mean of `abs(fill quantity) / eligible volume` | `ratio` | 1 fill |
| `participation_p95` | type-7 95th percentile of fill participation | `ratio` | 1 fill |

A metric that uses a benchmark reports `missing_input` when the inputs do not contain a benchmark.
It also reports `analysis.benchmark.missing_or_unaligned`.

The `holding_period` and participation metrics report `missing_input` when their
inputs do not contain the applicable data. `MetricsHandle.results()` returns rows in
catalog order. It puts each component cost row next to its base metric.
