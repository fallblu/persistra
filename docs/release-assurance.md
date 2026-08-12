# Release assurance

This page records the manual and automated evidence behind the 4.0.0 boundary. It distinguishes
provider certification from deterministic offline checks and states where the library stops.
Release operators still control version changes, tags, builds, and publication.

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

The redacted gold-spot fixture records the provider's stable `nominal` field. The certified
parser accepts that field without a commodity-spot schema diagnostic.

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
| Extended-hours-only bulk quote | Uses the extended quote, change, and percent when regular-session fields are blank |
| Empty result | Returns an exact typed empty result where absence is valid |
| Explicit no data | Raises `NoDataError` where the provider response has unambiguous no-data meaning |
| Unknown field | Records a deterministic diagnostic or fails when `strict_schema=True` |
| Contradictory values | Rejects impossible provider OHLC data before model construction |

Fixtures cover every supported provider operation. The endpoint manifest checks that the 48
family-operation pairs map to all 47 implemented Alpha Vantage functions and that each entry
has a redacted fixture and parser test.

## FRED and ALFRED validation

The FRED and ALFRED adapter has fixture-backed coverage for series definitions, latest
source-level observations, bounded revision histories, explicit vintage-date pages, pagination,
redaction, refresh, and offline replay. Deterministic synthetic vintage histories exercise the
same normalized `VintageSeriesSet` contract without credentials or network access.

The opt-in FRED suite performs a redacted live request and offline replay when
`PERSISTRA_RUN_LIVE=1` and `PERSISTRA_FRED_API_KEY` are present:

```bash
PERSISTRA_RUN_LIVE=1 uv run pytest --no-cov tests/live/test_fred_live.py -s -vv
```

Normal CI and the default contribution gate skip both live suites.

## Contract and public API review

Exact normalized frame columns, order, pandas dtypes, sort keys, uniqueness, missingness, and
numeric invariants are release contracts. Public namespace snapshots cover the supported
imports. `ResultMetadata` has one validated construction path. It accepts a general mapping,
copies it into an immutable view, and removes API-key parameters without case sensitivity.
`AlphaVantageClient.from_env` publishes the same explicit typed options as the supported client
constructor instead of accepting arbitrary keyword arguments.

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

## Research and simulation boundaries

Point-in-time research tests cover daily vintage availability, explicit publication lag and
staleness, source-version provenance, forward-label horizons, cross-sectional transforms,
pairwise information-coefficient counts, grouped summaries, equal-weight quantiles, turnover,
capacity, benchmark comparisons, repeated-search corrections, purged splits, embargoes, and
portable manifests.

Controlled signal studies use deterministic panels across multiple periods and fixed-universe
slices. They compare simple candidate signals with explicit baselines. This checks calculations
and research slicing; it does not claim a survivorship-free universe or empirical efficacy.

Portfolio tests cover equal and signal-proportional construction, long-only and long-short
configurations, position and exposure limits, covariance risk controls, residual cash, turnover,
deterministic rebalance schedules, causal signal timing, missing returns, nontradeable assets,
linear costs, fixed holding periods, benchmarks, and full accounting reconciliation. The
simulator remains a portfolio-level model, not an order or exchange simulator.

## Reproducibility boundary

Research manifests record normalized dataset scope and schema, content or stored snapshot
identity, feature, label, split, and benchmark parameters, direct runtime dependency versions,
random seeds, execution status, and external artifact checksums. Raw caches and DuckDB snapshots
have separate identities because they answer different reproducibility questions.

Notebooks, provider data, caches, figures, credentials, and generated manifests remain outside
the repository and built distributions. The package records inputs and output identities; it
does not bundle a research workspace or make a run reproducible without retained source data.

## Deterministic processing

Repeated parsing, raw-cache replay, normalized storage, loading, and transformation produce
the same content for the same inputs. The automated suite specifically covers:

- stable ordering of schema diagnostics
- refreshed, cache-hit, and offline fingerprints for every live family
- content-derived DuckDB snapshot reuse, exact snapshot loads, and cumulative row revisions at
  retrieval cutoffs
- repeated resampling with source-derived provenance instead of wall-clock time
- sorted normalized frames and caller-order preservation for bulk results
- repeated portfolio construction, rebalance schedules, and vectorized simulation
- stable JSON research manifests and artifact checksums

## Contribution gate

The release candidate must pass lint, strict typing, the offline test suite with at least 90
percent coverage, documentation structure and executable-example checks, a strict MkDocs build,
wheel and source-distribution checks, a clean wheel import, and lockfile validation. CI runs the
complete gate on Python 3.12, 3.13, and 3.14. The installed-wheel check imports every supported
top-level namespace in an isolated interpreter, verifies the exact distribution version and
typing marker, and confirms that imports resolve inside the clean environment. CI also runs the
complete offline suite against the `lowest-direct` and `highest` dependency resolutions on
Python 3.12.

The release operator should use the commands in `CONTRIBUTING.md` and inspect the resulting CI
matrix. Live provider suites remain separate because they require credentials, network access,
and an entitled account.

## Version agreement

`pyproject.toml`, `uv.lock`, the latest numbered `CHANGELOG.md` entry, built distribution
metadata, this assurance boundary, and the signed `v4.0.0` tag identify version 4.0.0. Automated
checks compare project, lockfile, changelog, assurance, and installed-wheel versions. A
tag-triggered check also requires the exact annotated tag name. The release operator verifies
the tag's signature. Project policy changes the package version only on a human-controlled
release branch. Documentation completion does not authorize a version bump, tag, publication,
or release.

The `v4.0.0` tag records a single-parent documentation commit after the release integration.
That historical topology predates the current rule requiring a release tag on the integration
merge commit. Future releases follow the current rule; the published tag is not rewritten.
