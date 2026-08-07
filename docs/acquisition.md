# Alpha Vantage acquisition

Alpha Vantage acquisition will cover the primary dataset boundary in the
[4.0 roadmap](roadmap.md). It will exclude fundamentals, ownership, provider analytics,
alternative data, and real-time option chains.

The client will read `PERSISTRA_ALPHAVANTAGE_API_KEY`. Shared transport already provides
atomic raw caching, offline reads, proactive rate control, typed errors, and bounded retries.
Normal tests and notebooks remain offline.

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env(requests_per_minute=150)
bars = client.securities.bars("IBM", kind=InstrumentKind.EQUITY, interval="daily")
```

The client currently covers security bars, latest and bulk quotes, top-of-book snapshots,
symbol search, market status, index bars, and the index catalog. Historical endpoint calls
reuse fresh raw responses for 24 hours. Live observations use the network by default.
