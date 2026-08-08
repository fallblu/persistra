# Foundation assurance

This page records the manual and automated evidence for the foundation hardening completed
on August 8, 2026. It covers the current Alpha Vantage adapter, normalized contracts,
retrieval-time storage, deterministic processing, supported Python versions, and dependency
bands.

This evidence does not declare 4.0.0 ready for release. The vintage-aware series contract,
FRED and ALFRED adapter, point-in-time research transforms, and flagship study remain separate
release requirements.

## Alpha Vantage certification

The live suite ran against the intended 150-request-per-minute plan with realtime quote
entitlement. It read the API key only from `PERSISTRA_ALPHAVANTAGE_API_KEY`. The suite did not
print the key, request URLs, response bodies, symbols returned by searches, or observation
values.

Each family completed a refreshed network request and an offline parse from the resulting raw
cache entry. A redacted content fingerprint confirmed that both parses produced the same
normalized result after excluding only the expected cache-status difference. A subsequent
security-bar request confirmed an ordinary cache hit against the same fingerprint.

| Family | Provider operation | Normalized result | Observations | Diagnostics | Outcome |
|---|---|---|---:|---|---|
| Security bars | `TIME_SERIES_DAILY` | `BarSet` | 100 | None | Pass |
| Latest quote | `GLOBAL_QUOTE` | `QuoteSet` | 1 | None | Pass |
| Bulk quotes | `REALTIME_BULK_QUOTES` | `QuoteSet` | 1 | None | Pass |
| Top of book | `REALTIME_BULK_BID_ASK_PRICES` | `TopOfBookSet` | 1 | `bid_ask` | Pass |
| Index bars | `INDEX_DATA` | `BarSet` | 1,536 | None | Pass |
| Index catalog | `INDEX_CATALOG` | `IndexCatalogResult` | 317 | None | Pass |
| Historical options | `HISTORICAL_OPTIONS` | `OptionChain` | 2,320 | None | Pass |
| Fiat exchange rate | `CURRENCY_EXCHANGE_RATE` | `ExchangeRateQuote` | 1 | None | Pass |
| Fiat bars | `FX_DAILY` | `BarSet` | 100 | None | Pass |
| Crypto exchange rate | `CURRENCY_EXCHANGE_RATE` | `ExchangeRateQuote` | 1 | None | Pass |
| Crypto bars | `DIGITAL_CURRENCY_DAILY` | `BarSet` | 5,867 | None | Pass |
| Commodity series | `WTI` | `SeriesSet` | 487 | None | Pass |
| Commodity spot | `GOLD_SILVER_SPOT` | `CommoditySpotQuote` | 1 | None | Pass |
| Economic series | `CPI` | `SeriesSet` | 1,362 | None | Pass |
| Symbol search | `SYMBOL_SEARCH` | `InstrumentSearchResult` | 10 | None | Pass |
| Market status | `MARKET_STATUS` | `MarketStatusResult` | 16 | None | Pass |

The top-of-book `bid_ask` diagnostic reported a locked or crossed provider snapshot. This is
a nonfatal market-state diagnostic, not an unknown field or a normalized schema change.

The first live pass also exposed a stable `nominal` field in the gold spot response. The
redacted fixture and parser test now record that field. A second live pass completed without
a commodity-spot schema diagnostic.

Run the certification manually with:

```bash
PERSISTRA_RUN_LIVE=1 \
PERSISTRA_ALPHAVANTAGE_LIVE_ENTITLEMENT=realtime \
uv run pytest --no-cov tests/live/test_alphavantage_live.py -s -vv
```

The test is skipped unless `PERSISTRA_RUN_LIVE=1` is set. Normal CI and the default test gate
remain offline.

## Controlled provider cases

Offline tests exercise behavior that a live provider cannot safely or reliably produce on
demand:

| Case | Verified behavior |
|---|---|
| Cache hit | Reuses a fresh historical response and reports `hit` |
| Refresh | Bypasses reusable content, replaces the raw entry, and reports `refreshed` |
| Offline parse | Prohibits network access, reparses cached bytes, and reports `offline` |
| Offline miss | Raises `TransportError` without a network fallback |
| Malformed payload | Raises a provider-specific typed error without including response data |
| Missing scalar value | Preserves the provider sentinel as an explicit missing observation |
| Omitted bulk symbol | Returns available observations and records the omitted symbol diagnostic |
| Empty result | Returns an exact typed empty result where absence is valid |
| Explicit no data | Raises `NoDataError` where the provider response has unambiguous no-data meaning |
| Unknown field | Records a deterministic diagnostic or fails when `strict_schema=True` |
| Contradictory values | Rejects impossible provider OHLC data before model construction |

Fixtures cover every supported provider operation. The endpoint manifest checks that the 48
family-operation pairs map to all 47 implemented Alpha Vantage functions and that each entry
has a redacted fixture and parser test.

## Contract and API review

Exact normalized frame columns, order, pandas dtypes, sort keys, uniqueness, missingness, and
numeric invariants remain release contracts. Public namespace snapshots cover the supported
imports.

The review removed two redundant construction paths before they became release contracts:

- `ResultMetadata.create` duplicated the validated dataclass constructor.
- `AlphaVantageClient.transport_options` exposed an untyped pass-through to transport
  internals.

`ResultMetadata` now accepts a general mapping, copies it into an immutable view, and removes
API-key parameters without case sensitivity. `AlphaVantageClient.from_env` now publishes the
same explicit typed options as the supported client constructor instead of accepting arbitrary
keyword arguments.

Bulk quote results now identify requested symbols omitted by the provider. Exchange-rate,
commodity-spot, and scalar-series envelopes report unknown fields consistently. Strict schema
mode fails only unknown provider fields; operational diagnostics such as a crossed market or
an omitted observation remain visible without being mislabeled as schema drift.

## Retrieval-time revisions

DuckDB revision selection uses the first time Persistra retrieved normalized content. Tests
cover the exact first-seen boundary, a cutoff before the first observation, repeated identical
content, changed content, loading, and filtered queries.

`retrieved_before` can reconstruct only content that Persistra had already observed. It does
not describe a provider publication time, prove when a value became available to the market,
or supply a revision that Persistra never retrieved. It is not provider-native vintage
coverage.

## Deterministic processing

Repeated parsing, raw-cache replay, normalized storage, loading, and transformation produce
the same content for the same inputs. The hardening tests specifically cover:

- stable ordering of schema diagnostics
- refreshed, cache-hit, and offline fingerprints for every live family
- content-derived DuckDB snapshot reuse and exact revision cutoffs
- repeated resampling with source-derived provenance instead of wall-clock time
- sorted normalized frames and caller-order preservation for bulk results

## Verification matrix

The complete contribution gate passed locally on Linux for every supported Python version:

| Python | Lint | Strict typing | Tests | Coverage | Strict docs | Package and clean install | Lockfile |
|---|---|---|---|---:|---|---|---|
| 3.12.12 | Pass | Pass | 219 pass, 1 live skip | 93.39% | Pass | Pass | Pass |
| 3.13.12 | Pass | Pass | 219 pass, 1 live skip | 93.39% | Pass | Pass | Pass |
| 3.14.3 | Pass | Pass | 219 pass, 1 live skip | 93.39% | Pass | Pass | Pass |

The Python 3.12 dependency bands also passed the complete offline test suite:

| Resolution | Result |
|---|---|
| `lowest-direct` | 219 pass, 1 live skip |
| `highest` | 219 pass, 1 live skip |

The minimum Matplotlib dependency emitted deprecation warnings from its own parser module in
the `lowest-direct` environment. No Persistra warning or failure occurred.

## Version agreement

`CHANGELOG.md` targets 4.0.0 directly and describes the provider-neutral redesign. The source
metadata remains at 3.0.2 because that is the latest released version. Project policy changes
the package version only on a human-controlled release branch; this hardening work does not
authorize a version bump, tag, build publication, or release.
