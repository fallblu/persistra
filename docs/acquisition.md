# Alpha Vantage acquisition

Alpha Vantage acquisition covers the primary dataset boundary in the
[4.0 roadmap](roadmap.md). It will exclude fundamentals, ownership, provider analytics,
alternative data, textual data, realtime option chains, and option-ratio endpoints.

The client reads `PERSISTRA_ALPHAVANTAGE_API_KEY`. Shared transport provides
atomic raw caching, offline reads, proactive rate control, typed errors, and bounded retries.
Normal tests and notebooks remain offline.

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env(requests_per_minute=150)
bars = client.securities.bars("IBM", kind=InstrumentKind.EQUITY, interval="daily")
```

The client covers security, index, FX, and crypto bars. It also covers current exchange
rates, latest and bulk quotes, top-of-book snapshots, symbol search, and market status.
Commodity coverage includes the full primary series set plus gold and silver spot.
Economic coverage includes all ten scoped indicators and every supported Treasury maturity.
Historical endpoint calls reuse fresh raw responses for 24 hours. Live observations use the
network by default.

Historical options use `client.options.historical_chain`. The date iterator walks an explicit
inclusive calendar range and skips only unambiguous no-data responses. It does not infer a
trading calendar. Option acquisition never fetches or infers an underlying price.

`client.quotes.latest` accepts historical, delayed, and realtime entitlement modes. Bulk
quotes and top-of-book snapshots are realtime-only provider operations. Their methods do not
accept an entitlement argument, and their metadata records the realtime entitlement.

The public namespaces are `securities`, `quotes`, `indices`, `options`, `fx`, `crypto`,
`commodities`, `economics`, and `reference`. Security bars cover all seven time-series
functions. Index bars use native index data. Pair methods require explicit base and quote
currencies. Commodity and economic methods retain native units and frequencies instead of
presenting scalar series as tradeable OHLC assets.

## Operational behavior

The default limiter is a smooth 150 requests each minute with one in-flight request. Larger
bulk requests are split deterministically and returned in caller order. The client does not
fan out requests concurrently. Retryable throttling and transient failures use bounded
backoff. Authentication, entitlement, invalid-parameter, schema, no-data, offline-cache-miss,
and retry-exhaustion outcomes have distinct exceptions.

Set `offline=True` on an operation to prohibit network access. A cache hit returns its cache
status in metadata. `refresh=True` bypasses a reusable cached response. Cache keys exclude the
API key, and metadata stores only redacted parameters. The raw cache retains the source body
for reproducibility and parser diagnosis; normalized DuckDB storage is explicit and separate.
Pass a `cache_ages` mapping to the client to override the 24-hour historical policy for a
specific provider function. A `None` age writes responses for later offline use but does not
reuse them during normal acquisition. Live observations use that policy by default.

Schema drift is handled at the provider boundary. Unknown source fields are recorded as
diagnostics when a safe parse remains possible. Missing required fields or malformed values
fail normalization. The adapter does not silently repair, fill, interpolate, or reinterpret
source data.

## Entitlements and source terms

The 150-request tier is the target, not an entitlement guarantee. Historical, delayed, and
realtime modes are explicit where the provider accepts them. Realtime United States market
data can require a separate provider entitlement. Users must confirm current plan access and
permitted use before acquiring or redistributing data.

Alpha Vantage terms apply to the adapter. Some commodity and economic series also identify
FRED, EIA, or IMF as upstream sources. Preserve attribution and review those terms for the
selected series. A paid API plan does not itself grant data redistribution rights.

Run live smoke checks only with a dedicated key and explicit opt-in. Their report contains
operation names, redacted outcomes, and schema diagnostics. It never contains credentials or
raw response bodies.

For manual release certification, set the API key, opt-in flag, and the latest-quote
entitlement to test. Use `historical`, `delayed`, or `realtime` for the entitlement value.
The suite also calls the realtime-only bulk quote and top-of-book operations, so the key must
have realtime United States market-data access:

```bash
export PERSISTRA_ALPHAVANTAGE_API_KEY="your-key"
export PERSISTRA_RUN_LIVE=1
export PERSISTRA_ALPHAVANTAGE_LIVE_ENTITLEMENT="historical"
uv run pytest --no-cov -m live -s tests/live
```

The suite calls every supported family at the configured 150-request rate. It prints only
operation names, result types, normalized column names, diagnostic field names, entitlement,
and success status. Review failures against the account entitlement. Do not commit caches,
provider responses, or reports that contain observed values.
