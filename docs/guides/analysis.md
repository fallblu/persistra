# Analyze observations

Persistra analysis functions are pure calculations over normalized results or ordinary wide
pandas frames. They never fetch data, mutate their inputs, or silently fill missing values.

## Prepare wide numeric inputs

General analysis functions expect columns of numeric observations:

```python
from persistra.data import pivot_bars, synthetic

first = synthetic.bars("FIRST", periods=60, seed=1)
second = synthetic.bars("SECOND", periods=60, seed=2)
prices = pivot_bars([first, second], field="close")
prices.columns = ["First", "Second"]
```

Nonnumeric columns raise `AnalysisError`. Use normalized result-specific functions when the
calculation needs identity or contract terms.

## Summarize coverage and distributions

```python
from persistra.analysis import coverage_summary, summary_statistics

coverage = coverage_summary(prices)
statistics = summary_statistics(prices)

print(coverage)
print(statistics)
```

Coverage reports observed and missing labels for each column. Summary statistics use sample
standard deviation and pandas linear quantiles.

## Calculate changes and returns

```python
from persistra.analysis import (
    absolute_change,
    log_change,
    log_returns,
    percentage_change,
    simple_returns,
)

differences = absolute_change(prices, periods=1)
fractional_changes = percentage_change(prices, periods=1)
log_differences = log_change(prices, periods=1)
simple = simple_returns(prices, periods=1)
logged = log_returns(prices, periods=1)
```

Percentage changes and simple returns are equivalent calculations with names suited to
different contexts. Log functions require every observed level to be positive. All change
functions require a positive integer lag and refuse to bridge missing levels.

## Rebase and compound

```python
from persistra.analysis import cumulative_returns, drawdowns, rebase

rebased = rebase(prices, base=100)
complete = simple.dropna()
cumulative = cumulative_returns(complete)
underwater = drawdowns(complete)
```

`rebase` uses the first observed positive level in each column. Compounding and drawdown
functions reject internal gaps within an observed span because an unknown return breaks the
path.

## Calculate rolling statistics

```python
from persistra.analysis import (
    rolling_mean,
    rolling_standard_deviation,
    rolling_volatility,
    rolling_zscore,
)

mean = rolling_mean(prices, window=20)
standard_deviation = rolling_standard_deviation(prices, window=20)
zscore = rolling_zscore(prices, window=20)
volatility = rolling_volatility(
    simple,
    window=20,
    periods_per_year=252,
)
```

Rolling functions require a complete window by default. Pass `min_periods` only when a
partial-window estimate is part of the research definition. Standard deviations use
`ddof=1`. Volatility annualization requires a positive explicit scale.

## Calculate covariance and correlation

```python
from persistra.analysis import correlation_matrix, covariance_matrix

covariance = covariance_matrix(simple)
correlation = correlation_matrix(simple)
```

Both calculations use pairwise complete observations. Pairwise sample sizes can therefore
differ across matrix cells when coverage differs.

## Analyze market results

Functions that need normalized bar or quote structure accept result objects:

```python
from persistra.analysis import (
    absolute_spread,
    bar_range,
    midprice,
    relative_spread,
    session_coverage,
    true_range,
    volume_summary,
)

book = synthetic.top_of_book(("AAA", "BBB"))

midpoints = midprice(book)
spreads = absolute_spread(book)
relative = relative_spread(book)
ranges = bar_range(first)
true_ranges = true_range(first)
volume = volume_summary(first)
sessions = session_coverage(first)
```

Spread calculations preserve a missing side. True range uses the previous close only within
the supplied result. Session coverage describes observed labels and does not infer an
exchange calendar.

`realized_volatility` is the market-named wrapper for annualized rolling return volatility:

```python
from persistra.analysis import realized_volatility

realized = realized_volatility(
    simple,
    window=20,
    periods_per_year=252,
)
```

## Analyze economic and rate series

```python
from persistra.analysis import basis_point_change, growth_rate
from persistra.data import pivot_series

cpi = synthetic.series("CPI", periods=36)
levels = pivot_series([cpi])

growth = growth_rate(levels, lag=12)
rate_change = basis_point_change(levels, rate_unit="percent")
```

Growth is fractional. Basis-point conversion requires an explicit `percent` or `decimal`
input unit. Yield-curve helpers preserve missing maturities and do not interpolate; see the
[data and feature examples](../examples/data-and-features.md).

## Analyze historical options

Option functions use contract terms and observations together:

```python
from persistra.analysis import (
    chain_summary,
    days_to_expiration,
    filter_chain,
    implied_volatility_surface,
    moneyness,
)

chain = synthetic.option_chain("DEMO")

filtered = filter_chain(chain, minimum_strike=95, maximum_strike=105)
days = days_to_expiration(filtered)
ratios = moneyness(filtered, underlying_price=102.0)
summary = chain_summary(filtered)
surface = implied_volatility_surface(filtered)
```

Calculations that depend on an underlying price require the caller to supply a positive
value. Implied volatility and Greek helpers prepare provider observations; they do not fit or
calculate those values. See the [data and feature examples](../examples/data-and-features.md)
for acquisition patterns.

## Handle invalid mathematical inputs

Persistra raises `AnalysisError` when data violate a calculation's mathematical assumptions,
such as nonnumeric columns, nonpositive log inputs, or internal compounding gaps. It raises
`ValueError` for invalid explicit parameters such as a nonpositive window.

Catch errors at the boundary where you can add research context:

```python
from persistra.errors import AnalysisError

try:
    logged = log_returns(prices)
except AnalysisError as error:
    raise RuntimeError("price inputs are not valid for log returns") from error
```
