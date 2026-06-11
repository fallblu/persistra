# Alpha Vantage Forex Ingestion

persistra includes an Alpha Vantage Forex adapter under
`persistra.providers.alphavantage`.

## Configure Access

Set `ALPHAVANTAGE_API_KEY` in your environment or in a local `.env` file:

```bash
export ALPHAVANTAGE_API_KEY=...
```

The `.env` file is loaded when `python-dotenv` is installed.

## Ingest Forex Bars

```python no-run
from persistra.data.store import ParquetMarketData
from persistra.providers.alphavantage import ingest_fx

store = ParquetMarketData("data/fx")
ingest_fx(
    symbols=["EURUSD", "GBPUSD"],
    timeframes=["1d"],
    store=store,
)
```

FX symbols are stored as compact uppercase pairs such as `EURUSD`. The adapter
supports `1d`, `1m`, `5m`, `15m`, `30m`, and `1h`. By default, ingestion stores
all historical bars returned by Alpha Vantage. Pass `start=` and/or `end=` to
limit the downloaded range.

Alpha Vantage FX endpoints provide OHLC prices but not volume, so stored FX bars
use `volume=0.0`, `vwap=null`, and `transactions=null`.

## Universe Membership

By default, `ingest_fx` writes one open-ended universe membership row per requested
pair so the engine can discover the symbols. With `ParquetMarketData`, writing
universe membership replaces the existing universe table. Pass `write_universe=False`
if you manage universe membership separately.

## Backtesting

Use a weekday calendar for Forex:

```python no-run
from persistra import BuyAndHold, Engine, ParquetMarketData, Portfolio

result = Engine(
    data=ParquetMarketData("data/fx"),
    strategy=BuyAndHold(),
    portfolio=Portfolio(initial_capital=100_000),
    start="2020-01-01",
    end="2024-12-31",
    calendar="24/5",
).run()
```
