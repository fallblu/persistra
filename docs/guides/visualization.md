# Build visualizations

Persistra provides focused Plotly helpers for normalized data and explicit calculations. Every
public plotting function returns one caller-owned Plotly `Figure`. The helpers do not change
Plotly templates, renderers, or other process-wide configuration.

Install the visualization dependencies without the browser inspector:

```console
uv add "persistra[viz]"
```

## Customize the figure

```python
from persistra.data import pivot_bars, synthetic
from persistra.viz import plot_series

bars = synthetic.bars("DEMO", periods=60)
prices = pivot_bars([bars], field="close")
prices.columns = ["Demo"]

figure = plot_series(prices, ylabel="Price")
figure.update_layout(title="Synthetic close", width=900, height=400)
figure.update_traces(line={"width": 2})
```

The returned figure owns its traces and layout. Call `figure.show()` in an interactive
environment. Use Plotly's figure methods to change titles, axes, hover templates, legends, or
dimensions.

This is a breaking composition model. Plot functions no longer accept an `ax` argument or return
separate plotting objects. Composite built-ins, including candlesticks and Trading Engine
diagnostics, return one figure with named subplots.

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

Rolling plots accept already calculated values because window and missing-data policy belong in
analysis code. Multi-series plots combine color with deterministic dash and marker styles.
Missing values remain gaps, and temporal indexes retain their date values for Plotly zoom and
hover inspection.

`plot_series` rejects inputs when a 100-fold difference in typical magnitudes would hide smaller
series or imply shared units. Normalize those inputs before plotting. Rebased paths automatically
use a log axis when positive terminal values differ by at least tenfold. Override that choice:

```python
plot_rebased(prices, base=100, yscale="linear")
```

Correlation heatmaps annotate each cell with its pairwise complete-observation count. Coverage
plots switch to horizontal bars when descriptive series names would overlap.

## Plot candlesticks and volume

```python
from persistra.viz import plot_candlesticks

candlesticks = plot_candlesticks(bars)
candlesticks.update_layout(title="Synthetic OHLC")
```

`plot_candlesticks` returns one figure with linked price and volume subplots. Sampled source
dates label the horizontal axis. Rising and falling observations use different fill treatments
and volume patterns in addition to color.

An adjacent open and previous close that differ by at least twofold mark a split-sized price
discontinuity. The figure labels that boundary and uses a log price axis automatically. Pass
`yscale="linear"` or `yscale="log"` to make the scale explicit.

## Plot return diagnostics

```python
from persistra.analysis import cumulative_returns, drawdowns, rolling_volatility
from persistra.viz import (
    plot_cumulative_returns,
    plot_drawdowns,
    plot_returns,
    plot_rolling_volatility,
)

observed_returns = returns.dropna()
cumulative = cumulative_returns(observed_returns)
underwater = drawdowns(observed_returns)
volatility = rolling_volatility(
    observed_returns,
    window=20,
    periods_per_year=252,
)

plot_returns(observed_returns)
plot_cumulative_returns(cumulative)
plot_drawdowns(underwater)
plot_rolling_volatility(volatility)
```

The plot name describes the expected input; plot functions do not recalculate return policy.
Return plots mark internal missing observations while retaining those values as trace gaps.

For cumulative paths, terminal growth that differs by at least tenfold automatically switches
to growth of one dollar on a log axis. Explicit log mode requires cumulative returns greater
than -100 percent.

## Plot cross-sectional signal research

```python
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

Signal distributions use one explicit cross-section. Supply a group panel to compare box plots.
Information coefficient figures show their forward horizon and pairwise sample-count range.

Quantile return, spread, count, turnover, and capacity figures retain the result's horizon and
quantile definition. `plot_cumulative_quantile_returns` accepts only a one-observation horizon
because longer forward labels overlap and do not define a wealth path.

Use `plot_stability_comparison` for caller-defined period, universe, or temporal-split tables.
Use `plot_benchmark_comparison` for the typed output from `compare_benchmark`.

## Plot portfolio construction and backtests

```python
from persistra.portfolio import backtest_portfolio, construct_portfolio
from persistra.viz import (
    plot_backtest_drawdowns,
    plot_backtest_performance,
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
plot_backtest_performance(result)
plot_backtest_drawdowns(result)
plot_transaction_costs(result)
plot_return_attribution(result)
plot_rebalance_diagnostics(result)
```

Portfolio figures read recorded result fields instead of reconstructing policy. Target,
unconstrained, realized, and ending weights are separate choices. Risk figures fail when the
requested calculation is absent. Backtest path figures include simulated benchmarks by default,
and their titles state decision, execution, and holding timing.

## Plot bid-ask history and options

```python
import pandas as pd

from persistra.viz import (
    plot_bid_ask_history,
    plot_greek_profile,
    plot_implied_volatility_smile,
    plot_implied_volatility_surface,
    plot_option_chain_prices,
    plot_option_volume_open_interest,
    plot_spread_history,
)

book = synthetic.top_of_book(("AAA",))
later = book.frame.copy()
later["observed_at"] += pd.Timedelta(minutes=5)
later["bid_price"] -= 0.05
later["ask_price"] += 0.05
history = pd.concat([book.frame, later], ignore_index=True)
plot_bid_ask_history(history)
plot_spread_history(history)

chain = synthetic.option_chain("DEMO")
expiration = chain.contracts["expiration"].dt.date.min()
plot_option_chain_prices(chain)
plot_option_volume_open_interest(chain)
plot_implied_volatility_smile(chain, expiration=expiration, option_type="call")
plot_implied_volatility_surface(chain)
plot_greek_profile(chain, "delta", expiration=expiration, option_type="call")
```

A single latest top-of-book result is a snapshot, not a history. Collect snapshots explicitly
before plotting them.

The implied-volatility surface is a three-dimensional Plotly surface. Missing
strike-expiration cells remain gaps. Option price and Greek traces use compact dates, option
sides, dash styles, and markers. Volume and open-interest bars label sampled contracts with
expiration, strike, and side.

## Plot economic data

```python
from persistra.analysis import growth_rate, yield_curve, yield_curve_history
from persistra.data import pivot_series
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
yield_history = yield_curve_history(treasuries)

plot_scalar_series(series)
plot_series_change(growth, ylabel="12-month growth")
plot_yield_curve(curve)
plot_yield_curve_history(yield_history)
```

Scalar figures use normalized period starts. Change figures expose sparse observations with
markers. Yield-history heatmaps retain missing cells and sample temporal and maturity labels.

## Display and export

```python
comparison = plot_rebased(prices)
comparison.write_html("comparison.html", include_plotlyjs=True)
```

`write_html` creates a self-contained interactive artifact. `figure.show()` uses the caller's
configured Plotly renderer. Static image export is available through Plotly's separately
installed Kaleido integration:

```py
# Requires a compatible separately installed kaleido package.
comparison.write_image("comparison.png", width=1200, height=600, scale=2)
```

Persistra does not choose a renderer, file format, output directory, or global template.
Configure those in the application or reporting layer.
