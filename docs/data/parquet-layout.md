# Parquet Layout

`ParquetMarketData` is the built-in market-data backend. It stores bars, corporate
actions, and universe membership under a single root.

```text
root/
  bars/
    timeframe=1d/symbol=AAPL/year=2024/part-*.parquet
    timeframe=1h/symbol=AAPL/year=2024/part-*.parquet
  actions/
    action_type=split/year=2024/part-*.parquet
    action_type=dividend/year=2024/part-*.parquet
  universe/
    membership.parquet
  _state/
```

## Bars

Bars are keyed by timeframe, symbol, and year. Queries return rows sorted by
`(bar_time, symbol)`.

## Corporate Actions

Splits and dividends are stored separately from bars. The engine applies actions before
the session's bars.

## Universe Membership

The universe table contains membership intervals:

- `symbol`
- `start_date`
- `end_date`

The engine asks for symbols active during the requested date range, then gates each
session to the symbols active on that specific date. This is the main defense against
accidentally trading a future universe.

## State Directory

`_state/` is reserved for provider checkpoints and other ingest state. It is not part of
the engine-facing data model.
