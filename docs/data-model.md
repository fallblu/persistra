# Data model and storage

Persistra separates identity from observations. Instruments, listings, provider symbols,
option contracts, and scalar series have explicit identities. A provider-scoped identity
does not claim equivalence with another provider.

`Instrument` describes equities, exchange-traded funds, mutual funds, indices, fiat pairs,
crypto pairs, and commodities. `Listing` holds exchange-specific facts only when the source
provides them. `SeriesDefinition` describes commodity and economic scalar series. Option
contracts retain both their provider ID and decomposed terms. A future adapter can implement
the small capability protocols without changing these result contracts.

The normalized result families are:

| Result | Observation contract |
|---|---|
| `BarSet` | OHLCV bars with one applicable date or timestamp label |
| `QuoteSet` | Latest price and session summary observations |
| `TopOfBookSet` | Bid, ask, and applicable sizes |
| `OptionChain` | Contract terms plus historical chain observations |
| `SeriesSet` | Commodity or economic values at provider period labels |
| Scalar quote results | Current exchange-rate or precious-metal observations |
| Reference results | Search, market-status, and index-catalog frames |

Each result contains an exact pandas frame and immutable acquisition metadata. Required
provenance never depends on `DataFrame.attrs`. Calendar dates remain separate from UTC
instants, and missing applicability remains distinct from zero.

Intraday timestamps are UTC-aware instants with the provider timezone and timestamp-position
meaning retained. Daily and lower-frequency values use timezone-naive calendar labels.
Scalar series keep provider period labels; period boundaries remain missing unless known.
All numeric observations must be finite. Nullable pandas types distinguish missing values
from zero.

`ResultMetadata` records the provider operation, redacted request parameters, UTC retrieval
time, optional provider as-of time, entitlement, raw-cache status, schema version, and drift
diagnostics. Retrieval time is provenance. It is never substituted for a market event time.

## Explicit transforms

`pivot_bars` and `pivot_series` create wide frames without filling values. `align` requires an
intersection or union choice. `asof_align` requires a maximum staleness and reports each match
age. `resample_bars` requires a frequency, timezone, and included sessions. These operations
copy inputs and preserve gaps.

## DuckDB revisions

`DuckDBStore` creates or opens one explicit database connection. Acquisition never writes
automatically. Repeated identical source values update their last-seen time. Changed values
create a new retrieval-time revision. A `retrieved_before` query reconstructs only what
Persistra had observed by that time. It does not claim provider point-in-time history.

The store validates a result before saving it. Each family has an explicit save/load path,
and option terms remain separate from observations in the schema. Use the store as a context
manager so its connection closes deterministically. Raw HTTP caching is a separate concern;
deleting a raw cache does not delete normalized research data.

`query_bars` applies interval, inclusive temporal, and retrieval-time filters in DuckDB.
`query_series` applies inclusive period-label and retrieval-time filters there as well. Both
return exact typed frames. They return empty typed frames when the scope has no snapshot.

Database schemas from v3 or the abandoned v4 implementation are unsupported. Create a new
database for this release.
