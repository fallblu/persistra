# Persistra

Persistra is a typed Python library for primary financial data and quantitative research. It
gives you one set of normalized pandas contracts for acquiring, validating, storing,
transforming, researching, simulating, analyzing, and plotting observations.

The library keeps the important boundaries visible:

- Provider adapters acquire data but never write it to storage.
- Result objects keep identity, observations, and provenance separate.
- Raw HTTP caching and normalized DuckDB storage solve different problems.
- Transforms preserve missing values unless you make an explicit alignment or resampling
  choice.
- Point-in-time research records availability, lag, staleness, label horizons, purged and
  embargoed boundaries, cross-sectional sample counts, and reproducibility identities.
- Portfolio research records target constraints, signal and holding timing, cash, leverage,
  turnover, costs, nontradeable assets, and accounting attribution.
- The optional Trading Engine integration uses deterministic files and an explicit subprocess for
  completed-bar execution research while keeping engine semantics outside Persistra.
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
4. Connect [Alpha Vantage](getting-started/alpha-vantage.md) for primary market data or
   [FRED and ALFRED](getting-started/fred.md) for economic observations and revisions.
5. [Replay a strategy with Trading Engine](guides/trading-engine.md) when you need order and fill
   diagnostics beyond the vectorized backtest.

Use the how-to guides when you have a specific task. They cover
[acquisition](guides/acquisition.md), [offline caching](guides/cache-offline.md),
[DuckDB storage](guides/storage.md), [transforms](guides/transforms.md),
[point-in-time datasets](guides/research.md),
[portfolio construction and backtesting](guides/portfolio.md),
[Trading Engine replay](guides/trading-engine.md), [analysis](guides/analysis.md),
[visualization](guides/visualization.md), and
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
| Vintage series | `VintageSeriesSet` | Historical versions with source availability dates |
| Scalar quotes | `ExchangeRateQuote`, `CommoditySpotQuote` | Current point observations |
| Reference data | Reference result classes | Search matches, market status, and index catalogs |

The bundled adapters cover supported Alpha Vantage primary datasets and focused FRED and
ALFRED series acquisition. The portfolio package stops at target weights and a vectorized
portfolio-level simulator. An optional adapter can hand raw intraday bars and target positions
to a separately installed Trading Engine executable and import its audit journal. Persistra does
not implement that engine's execution semantics, broker connectivity, or live trading. It also
does not include a fundamental-data model, provider-calculated technical indicators, news
analytics, or realtime option chains.

## Design promises

Persistra favors explicit research choices over convenience that changes meaning:

- It does not fill, interpolate, or silently repair observations.
- It distinguishes calendar labels from instants.
- It records retrieval time as provenance, not as an event time.
- It requires an explicit staleness limit for as-of alignment.
- It keeps point-in-time features and forward-return labels in separate result types.
- It purges training labels that reach an evaluation period.
- It requires cross-sectional signal, label, group, exposure, and volume panels to use explicit
  aligned date and asset axes.
- It rejects same-period signal use in a backtest without an explicit pretrade availability
  assertion.
- It reconciles simulated asset returns, cash, costs, holdings, and equity.
- It requires a complete terminal audit journal before accepting an external engine replay.
- It requires an explicit timezone and session set for intraday resampling.
- It validates exact column order and pandas dtypes at normalized boundaries.
- It returns caller-owned Matplotlib axes and does not change global style settings.

These rules make examples slightly more deliberate, but they also make research assumptions
reviewable.

## Requirements

Persistra requires Python 3.12 or later. The supported runtime platform is Linux. See the
[installation guide](getting-started/installation.md) for package and contributor setup. The
[release assurance](release-assurance.md) page records provider certification, contract
coverage, reproducibility boundaries, and verification expectations.
