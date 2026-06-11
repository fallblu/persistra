# Data and Storage

The engine depends on the `MarketData` read protocol. `ParquetMarketData` is the included
implementation and also implements the write protocol used by provider adapters and
fixtures.

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

Provider adapters write canonical Arrow tables into the store. Engine code reads from
the same store through the `MarketData` protocol.

## Adjustments

Stored bars are raw by default. Split and dividend records stay separate so adjustment
choices remain explicit in research code and visualization helpers.

## Survivorship Bias

Universe membership is a first-class input. The engine resolves symbols for the date
range, then asks `active_universe(session)` during processing so a strategy cannot trade
symbols outside their membership interval.
