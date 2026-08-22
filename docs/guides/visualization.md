# Build visualizations

Persistra provides focused Matplotlib helpers for normalized data and explicit calculations.
Functions return axes, accept caller-owned axes, and do not modify global `rcParams`.

Install the focused visualization dependencies without the browser inspector:

```console
uv add "persistra[viz]"
```

## Control the figure yourself

```python
import matplotlib.pyplot as plt

from persistra.data import pivot_bars, synthetic
from persistra.viz import plot_series

bars = synthetic.bars("DEMO", periods=60)
prices = pivot_bars([bars], field="close")
prices.columns = ["Demo"]

figure, ax = plt.subplots(figsize=(9, 4))
plot_series(prices, ax=ax, ylabel="Price")
ax.set_title("Synthetic close")
figure.tight_layout()
plt.show()
```

When `ax` is omitted, a helper creates an axes and still returns it.

## Plot general numeric frames

```python
from persistra.analysis import rolling_mean, simple_returns
from persistra.viz import (
    plot_correlation,
    plot_coverage,
    plot_distribution,
    plot_rebased,
    plot_rolling_statistic,
)

returns = simple_returns(prices)
rolling = rolling_mean(returns, window=10)

plot_rebased(prices, base=100)
plot_distribution(returns["Demo"].dropna(), bins=20)
plot_rolling_statistic(rolling, statistic_name="10-day mean")
plot_correlation(returns)
plot_coverage(prices)
```

`plot_rebased`, `plot_correlation`, and `plot_coverage` perform only their named calculation
before plotting. Rolling plots accept already calculated values because window and
missing-data policy belong in analysis code.

Multi-series plots use deterministic line styles and markers in addition to color. Temporal
indexes use concise automatic date labels. `plot_series` rejects inputs when a 100-fold
difference in typical magnitudes would make a shared axis hide smaller series or imply shared
units. Normalize those inputs before plotting or place them on separate caller-owned axes.

Long rebased paths automatically use a log axis when their terminal values differ by at least
10-fold. Set the scale explicitly when the comparison requires a fixed presentation:

```python
plot_rebased(prices, base=100, yscale="linear")
```

Correlation heatmaps annotate each cell with its pairwise complete-observation count. Coverage
plots switch to horizontal bars when descriptive series names would overlap.

## Plot candlesticks and volume

```python
from persistra.viz import plot_candlesticks

axes = plot_candlesticks(bars)
axes.price.set_title("Synthetic OHLC")
axes.price.figure.tight_layout()
```

`plot_candlesticks` returns a `PriceVolumeAxes` object with `price` and `volume` attributes.
Access the shared figure through either axes. Pass existing `price_ax` and `volume_ax` when
integrating the plot into a larger layout.

Candlestick ticks show sampled source dates. Falling candles use hatched bodies and dashed
wicks, so direction does not depend on red and green alone. An adjacent open and previous
close that differ by at least twofold mark a split-sized price discontinuity. The plot labels
that boundary and uses a log price axis automatically. Pass `yscale="linear"` or
`yscale="log"` to make the scale explicit.

## Plot return diagnostics

Calculate each input first:

```python
from persistra.analysis import (
    cumulative_returns,
    drawdowns,
    rolling_volatility,
    simple_returns,
)
from persistra.viz import (
    plot_cumulative_returns,
    plot_drawdowns,
    plot_returns,
    plot_rolling_volatility,
)

returns = simple_returns(prices).dropna()
cumulative = cumulative_returns(returns)
underwater = drawdowns(returns)
volatility = rolling_volatility(
    returns,
    window=20,
    periods_per_year=252,
)

plot_returns(returns)
plot_cumulative_returns(cumulative)
plot_drawdowns(underwater)
plot_rolling_volatility(volatility)
```

The plot name describes the expected input; plot functions do not recalculate return policy.
Related multi-asset plots retain the deterministic line styles and markers used by general
plots. Return plots place small colored ticks below the axis at internal missing observations.

For cumulative paths, terminal growth that differs by at least 10-fold automatically switches
to growth of one dollar on a log axis. Set the scale explicitly to override that choice:

```python
plot_cumulative_returns(cumulative, yscale="log")
```

The log mode requires cumulative returns greater than -100 percent.

## Plot cross-sectional signal research

Research plots accept the same explicit panels and typed results returned by
`persistra.research`. Keep the signal date, forward horizon, quantile count, and aggregation
policy visible in the call:

```python
from persistra.data import pivot_bars, synthetic
from persistra.research import (
    forward_returns,
    information_coefficients,
    quantile_portfolios,
    rank_cross_section,
)
from persistra.viz import (
    plot_cumulative_quantile_returns,
    plot_information_coefficients,
    plot_quantile_counts,
    plot_quantile_returns,
    plot_signal_distribution,
    plot_signal_ranks,
)

bars_by_asset = [
    synthetic.bars("AAA", periods=80, seed=1),
    synthetic.bars("BBB", periods=80, seed=2),
    synthetic.bars("CCC", periods=80, seed=3),
]
research_prices = pivot_bars(bars_by_asset, field="close")
research_prices.columns = ["AAA", "BBB", "CCC"]
signals = research_prices.pct_change(5).shift(1)
labels = forward_returns(research_prices, horizon=1)
ic = information_coefficients(signals, labels)
quantiles = quantile_portfolios(signals, labels, quantiles=3)
plot_date = signals.dropna(how="all").index[-1]

plot_signal_distribution(signals, date=plot_date)
plot_signal_ranks(rank_cross_section(signals), date=plot_date)
plot_information_coefficients(ic, statistic="rank", rolling=20)
plot_quantile_returns(quantiles)
plot_cumulative_quantile_returns(quantiles)
plot_quantile_counts(quantiles)
```

Signal distributions use one explicit cross-section. Supply a group panel to compare group
box plots on that date. Rank plots accept already calculated ranks so the ranking method and
direction remain part of the research code.

Information coefficient plots show their forward horizon and pairwise sample-count range.
Use `plot_information_coefficient_horizons` to compare unique horizons. Use
`plot_group_comparison` for a statistic returned by `summarize_groups`.

Quantile return, spread, count, one-way-turnover, and volume-capacity plots retain the result's
horizon and quantile definition. `plot_cumulative_quantile_returns` accepts only a
one-observation horizon. Longer forward labels overlap and do not define a portfolio wealth
path. Use the vectorized backtester when a holding policy is required.

Use `plot_stability_comparison` for caller-defined period, universe, or temporal-split tables.
Pass the statistic name, comparison dimension, and matching counts explicitly. Use
`plot_benchmark_comparison` for the typed output from `compare_benchmark`.

## Plot portfolio construction and backtests

Portfolio plots read the recorded result fields instead of reconstructing portfolio policy:

```python
from persistra.portfolio import backtest_portfolio, construct_portfolio
from persistra.viz import (
    plot_backtest_drawdowns,
    plot_backtest_performance,
    plot_backtest_returns,
    plot_constraint_utilization,
    plot_portfolio_exposures,
    plot_portfolio_weights,
    plot_rebalance_diagnostics,
    plot_return_attribution,
    plot_transaction_costs,
)

construction = construct_portfolio(
    signals.dropna(how="any"),
    weighting="equal",
    configuration="long_only",
)
result = backtest_portfolio(construction, prices=research_prices)

plot_portfolio_weights(construction, kind="target")
plot_constraint_utilization(construction)

plot_portfolio_weights(result, kind="realized")
plot_portfolio_exposures(result)
plot_backtest_returns(result)
plot_backtest_performance(result)
plot_backtest_drawdowns(result)
plot_transaction_costs(result)
plot_return_attribution(result)
plot_rebalance_diagnostics(result)
```

Here, `construction` is a `PortfolioConstructionResult` and `result` is a `BacktestResult`.
Target, unconstrained, realized, and ending weights are separate choices. Cash is shown by
default. Exposure plots retain long, short, gross, net, and residual-cash definitions.

`plot_predicted_volatility`, `plot_risk_contributions`, and `plot_constraint_utilization` use
the controls recorded during construction. They fail when the requested risk result was not
calculated. `plot_backtest_rolling_volatility` requires an explicit window and annualization
factor.

Backtest return, performance, drawdown, and volatility plots include simulated benchmarks by
default. Titles show the decision lag, execution lag, and holding policy. Return and cost
attribution plots use period contributions that reconcile to gross returns and total costs.
Pass a complete asset-to-group mapping to aggregate either attribution panel. The simulator
does not expose signal attribution, so the plotting API does not invent it.

Rebalance diagnostics compare requested target weights with realized holdings on the first
holding period. They mark assets blocked by the explicit nontradeable policy. These plots do
not imply orders, fills, intraday execution, or other details outside the vectorized simulator.

## Plot bid-ask history

The history helpers expect more than one stored or collected snapshot in one frame:

```python
import pandas as pd

from persistra.data import synthetic
from persistra.viz import plot_bid_ask_history, plot_spread_history

book = synthetic.top_of_book(("AAA",))
later = book.frame.copy()
later["observed_at"] += pd.Timedelta(minutes=5)
later["bid_price"] -= 0.05
later["ask_price"] += 0.05

history = pd.concat([book.frame, later], ignore_index=True)

plot_bid_ask_history(history)
plot_spread_history(history)
```

A single latest `TopOfBookSet` is a snapshot, not a time series. Collect snapshots explicitly
before using a history plot.

## Plot historical options

```python
from persistra.data import synthetic
from persistra.viz import (
    plot_greek_profile,
    plot_implied_volatility_smile,
    plot_implied_volatility_surface,
    plot_option_chain_prices,
    plot_option_volume_open_interest,
)

chain = synthetic.option_chain("DEMO")
expiration = chain.contracts["expiration"].dt.date.min()

plot_option_chain_prices(chain)
plot_option_volume_open_interest(chain)
plot_implied_volatility_smile(
    chain,
    expiration=expiration,
    option_type="call",
)
plot_implied_volatility_surface(chain)
plot_greek_profile(
    chain,
    "delta",
    expiration=expiration,
    option_type="call",
)
```

Surface heatmaps show only observed strike-expiration cells and use no interpolation.
Option price and Greek legends use compact ISO dates and plain-language option sides. Line
patterns and markers distinguish groups without color, and groups with six or fewer observations
use markers only. Volatility smiles use visibly patterned connections instead of implying a
fitted curve.

Volume and open-interest plots label sampled contracts with expiration, strike, and call or put
identity. Surface heatmaps also sample strike and expiration ticks, rotate strike labels, and
retain masked cells for absent contracts.

## Plot economic data

```python
from persistra.analysis import growth_rate, yield_curve, yield_curve_history
from persistra.data import pivot_series, synthetic
from persistra.viz import (
    plot_scalar_series,
    plot_series_change,
    plot_yield_curve,
    plot_yield_curve_history,
)

series = synthetic.series("CPI", periods=24)
levels = pivot_series([series])
growth = growth_rate(levels, lag=12)

treasuries = synthetic.treasury_curve(periods=12)
period_label = treasuries[0].frame["period_label"].iloc[-1]
curve = yield_curve(treasuries, period_label=period_label)
history = yield_curve_history(treasuries)

plot_scalar_series(series)
plot_series_change(growth, ylabel="12-month growth")
plot_yield_curve(curve)
plot_yield_curve_history(history)
```

Scalar series use normalized period starts with concise automatic date ticks. Change plots add
markers at every observation when gaps would otherwise make isolated values disappear. Yield
history heatmaps retain missing-cell masks and sample both temporal and maturity labels to fit
the available axes.

## Save a figure

Use normal Matplotlib output methods:

```python
ax = plot_rebased(prices)
ax.figure.savefig(
    "comparison.png",
    dpi=150,
    bbox_inches="tight",
)
```

Persistra does not choose a file format, output directory, global style, or display backend.
Configure those in your application or reporting layer.
