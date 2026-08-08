# Build visualizations

Persistra provides focused Matplotlib helpers for normalized data and explicit calculations.
Functions return axes, accept caller-owned axes, and do not modify global `rcParams`.

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
indexes use concise automatic date labels. `plot_series` warns when a 100-fold difference in
typical magnitudes makes a shared axis likely to hide smaller series or imply shared units.
Normalize those inputs before plotting or place them on separate caller-owned axes.

Use a log axis when long rebased paths diverge enough to compress smaller paths:

```python
plot_rebased(prices, base=100, yscale="log")
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
