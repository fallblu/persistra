# Persistra

Persistra is a typed Python library for primary market and economic data research. It gives
you one set of normalized pandas contracts for acquiring, validating, storing, transforming,
analyzing, and plotting observations.

The library keeps the important boundaries visible:

- Provider adapters acquire data but never write it to storage.
- Result objects keep identity, observations, and provenance separate.
- Raw HTTP caching and normalized DuckDB storage solve different problems.
- Transforms preserve missing values unless you make an explicit alignment or resampling
  choice.
- Analysis functions do not fetch data, and plotting functions do not hide calculations.

You can learn the complete workflow without credentials or network access. The deterministic
synthetic data helpers return the same result types and frame schemas as provider-backed data.

```python
from persistra.analysis import simple_returns
from persistra.data import pivot_bars, synthetic

equity = synthetic.bars("EQUITY", periods=60, seed=1)
index = synthetic.bars("INDEX", periods=60, seed=2)

prices = pivot_bars([equity, index], field="close")
returns = simple_returns(prices)
print(returns.tail())
```

## Choose a path

New users should follow these pages in order:

1. [Install Persistra](getting-started/installation.md).
2. Complete the [offline quickstart](getting-started/quickstart.md).
3. Follow a tutorial for [market](tutorials/market-research.md),
   [historical option](tutorials/options-research.md), or
   [economic](tutorials/economic-research.md) research.
4. [Connect Alpha Vantage](getting-started/alpha-vantage.md) when you are ready to acquire
   provider data.

Use the how-to guides when you have a specific task. They cover
[acquisition](guides/acquisition.md), [offline caching](guides/cache-offline.md),
[DuckDB storage](guides/storage.md), [transforms](guides/transforms.md),
[analysis](guides/analysis.md), [visualization](guides/visualization.md), and
[error handling](guides/errors.md).

For background, read about Persistra's [architecture](concepts/architecture.md),
[data model](concepts/data-model.md), and [time and provenance rules](concepts/time-provenance.md).
The [snippet cookbook](examples/snippets.md) is a quick source of copyable patterns, while the
[API reference](reference/index.md) lists the complete public surface.

## What Persistra covers

Persistra normalizes these result families:

| Family | Result type | Typical observations |
|---|---|---|
| Bars | `BarSet` | OHLCV, adjustment fields, session, and temporal labels |
| Latest quotes | `QuoteSet` | Price, session summary, volume, and entitlement |
| Top of book | `TopOfBookSet` | Bid, ask, sizes, and observation time |
| Historical options | `OptionChain` | Contract terms, prices, activity, volatility, and supplied Greeks |
| Scalar series | `SeriesSet` | Commodity or economic values with native units and periods |
| Scalar quotes | `ExchangeRateQuote`, `CommoditySpotQuote` | Current point observations |
| Reference data | Reference result classes | Search matches, market status, and index catalogs |

The bundled provider adapter covers the supported Alpha Vantage primary datasets. Persistra
does not include a backtesting engine, portfolio accounting, fundamental-data model,
provider-calculated technical indicators, news analytics, or realtime option chains.

## Design promises

Persistra favors explicit research choices over convenience that changes meaning:

- It does not fill, interpolate, or silently repair observations.
- It distinguishes calendar labels from instants.
- It records retrieval time as provenance, not as an event time.
- It requires an explicit staleness limit for as-of alignment.
- It requires an explicit timezone and session set for intraday resampling.
- It validates exact column order and pandas dtypes at normalized boundaries.
- It returns caller-owned Matplotlib axes and does not change global style settings.

These rules make examples slightly more deliberate, but they also make research assumptions
reviewable.

## Requirements

Persistra requires Python 3.12 or later. The supported runtime platform is Linux. See the
[installation guide](getting-started/installation.md) for package and contributor setup.
