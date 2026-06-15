# Data and Storage

The engine depends on the `MarketData` read protocol. `ParquetMarketData` is the included
implementation and also implements the write protocol used by fixtures and external
provider packages.

## Read Contract

`MarketData` exposes:

- `bars(BarQuery)`
- `corporate_actions(ActionQuery)`
- `universe(UniverseQuery)`
- `active_universe(date)`

The engine uses those methods to load history, apply corporate actions, and gate the
tradable universe point in time.

## Write Contract

`MarketDataWriter` exposes:

- `write_bars(table, timeframe)`
- `write_corporate_actions(table)`
- `write_universe(table)`

External provider packages write canonical Arrow tables into the store. Engine code
reads from the same store through the `MarketData` protocol.

## Adjustments

Stored bars are raw. `ParquetMarketData.bars()` and `BarQuery` return the
canonical stored OHLCV rows and reject adjusted bar requests. Split and dividend
records stay separate so adjustment choices remain explicit in research code
and visualization helpers.

Adjusted data is a view-layer feature. Helpers such as `prices()`, `panel()`,
`ohlcv()`, `returns()`, benchmark helpers, and plotting helpers accept
`AdjustmentPolicy.RAW`, `AdjustmentPolicy.SPLIT`, or the matching strings
`"raw"` and `"split"`. `returns()` and `log_returns()` default to split-adjusted
prices.

Split adjustment applies only to price-like fields: `open`, `high`, `low`,
`close`, and `vwap`. Volume, transactions, and other non-price fields remain
unadjusted.

## Survivorship Bias

Universe membership is a first-class input. The engine resolves symbols for the date
range, then asks `active_universe(session)` during processing so a strategy cannot trade
symbols outside their membership interval.

For research, universe rows should be point-in-time: listed symbols need accurate
`start_date` values and delisted symbols need bounded `end_date` values. Building a
universe from only today's active tickers introduces survivorship bias because symbols
that were tradable historically but are now inactive disappear from the backtest.
Use active-only universe construction only for explicitly current-only workflows.
