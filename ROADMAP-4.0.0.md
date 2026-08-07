# Persistra v4.0.0 roadmap

## 1. Product definition

Persistra v4.0.0 will be a local Python library for primary financial and economic data research.

The release will acquire, normalize, store, analyze, and visualize supported Alpha Vantage data.

The target subscription is the Alpha Vantage plan with 150 API requests each minute.

The primary user is an individual researcher who works with Python and pandas.

The release will favor a small, complete research product over a broad research platform.

### Product questions

The release will help a researcher answer these questions:

- What data does Alpha Vantage provide for one instrument or economic series?
- How do price, volume, spread, return, and volatility change through time?
- How do related instruments or series compare after explicit alignment?
- What does one historical option chain show across strikes and expirations?
- How do implied volatility, Greeks, volume, and open interest vary across a chain?
- How do commodity and economic observations change across their native frequencies?
- How does the United States Treasury yield curve change through time?

### Design principles

- Keep provider transport, normalized data, storage, analysis, and visualization separate.
- Use provider-neutral data contracts and provider-specific acquisition adapters.
- Add small capability protocols instead of a provider plugin framework.
- Preserve source meaning, units, time labels, and missing values.
- Never fill, interpolate, align, classify, or repair data without an explicit request.
- Never infer cross-provider identity.
- Keep large acquisitions lazy and bounded in memory.
- Use established libraries when they reduce complexity.
- Build each checkpoint on a working package.
- Remove obsolete v3 and abandoned v4 paths instead of preserving compatibility.

## 2. Release scope

v4.0.0 will support the primary datasets in this section.

The endpoint list reflects the Alpha Vantage documentation on August 7, 2026.

The implementation will verify the list again before release preparation.

### Security time series

The security family will support global equities and exchange-traded funds.

It will also support mutual funds when Alpha Vantage returns a compatible response.

| Function | Supported behavior |
|---|---|
| TIME_SERIES_INTRADAY | 1, 5, 15, 30, and 60 minute bars |
| TIME_SERIES_DAILY | Raw daily OHLCV bars |
| TIME_SERIES_DAILY_ADJUSTED | Daily bars with adjusted close and corporate actions |
| TIME_SERIES_WEEKLY | Raw weekly OHLCV bars |
| TIME_SERIES_WEEKLY_ADJUSTED | Weekly bars with adjusted close and dividends |
| TIME_SERIES_MONTHLY | Raw monthly OHLCV bars |
| TIME_SERIES_MONTHLY_ADJUSTED | Monthly bars with adjusted close and dividends |

The client will preserve each provider-native frequency.

Local resampling will not replace a native endpoint.

The security client will support provider exchange suffixes.

It will not remove or rewrite those suffixes.

Security intraday acquisition will support:

- Recent compact and full responses
- Historical month requests
- Raw and adjusted price modes
- Regular and extended session coverage
- Historical, delayed, and realtime entitlement modes

The client will not claim that every security type supports every endpoint or mode.

It will report provider capability failures with the operation and symbol.

### Quotes and market reference data

| Function | Supported behavior |
|---|---|
| GLOBAL_QUOTE | One latest quote with an explicit entitlement mode |
| REALTIME_BULK_QUOTES | Realtime quotes for provider-sized symbol batches |
| REALTIME_BULK_BID_ASK_PRICES | Realtime top-of-book data for provider-sized batches |
| SYMBOL_SEARCH | Provider symbol and listing search |
| MARKET_STATUS | Global market open and close status |

Bulk methods will accept more symbols than one provider request allows.

They will divide symbols into deterministic provider-sized requests.

They will preserve the caller order in the combined result.

### Market indices

| Function | Supported behavior |
|---|---|
| INDEX_DATA | Native daily, weekly, and monthly OHLC index data |
| INDEX_CATALOG | The provider index catalog |

The index family will support provider catalog symbols.

Representative tests will cover DJI, SPX, COMP, NDX, VIX, and RUT.

The package will not use exchange-traded fund proxies for indices.

### Historical United States options

| Function | Supported behavior |
|---|---|
| HISTORICAL_OPTIONS | One historical chain for one underlying and observation date |

The options family will support:

- Dates after the provider minimum of January 1, 2008
- The provider default for the prior trading session
- Whole-chain responses
- Contract filters
- Expiration filters
- Provider-supplied implied volatility
- Provider-supplied delta, gamma, theta, vega, and rho
- Bid, ask, mark, last, volume, and open interest

The 150 request plan includes end-of-day options.

It does not include realtime option chains.

Persistra will not use the realtime options endpoint.

The chain result will identify its underlying instrument.

It will not contain an inferred underlying price.

Analysis that needs an underlying price will require one explicitly.

### Foreign exchange

| Function | Supported behavior |
|---|---|
| CURRENCY_EXCHANGE_RATE | One current fiat exchange-rate quote |
| FX_INTRADAY | 1, 5, 15, 30, and 60 minute OHLC bars |
| FX_DAILY | Native daily OHLC bars |
| FX_WEEKLY | Native weekly OHLC bars |
| FX_MONTHLY | Native monthly OHLC bars |

The caller will supply explicit base and quote currencies.

The client will build a canonical pair label such as EUR/USD.

### Digital and crypto currencies

| Function | Supported behavior |
|---|---|
| CURRENCY_EXCHANGE_RATE | One current crypto exchange-rate quote |
| CRYPTO_INTRADAY | 1, 5, 15, 30, and 60 minute OHLCV bars |
| DIGITAL_CURRENCY_DAILY | Native daily market data |
| DIGITAL_CURRENCY_WEEKLY | Native weekly market data |
| DIGITAL_CURRENCY_MONTHLY | Native monthly market data |

The caller will supply an explicit crypto base and market currency.

The client will preserve provider-reported volume units and currencies.

### Commodities

| Function | Supported frequencies or modes |
|---|---|
| GOLD_SILVER_SPOT | Current gold or silver spot quote |
| GOLD_SILVER_HISTORY | Daily, weekly, and monthly |
| WTI | Daily, weekly, and monthly |
| BRENT | Daily, weekly, and monthly |
| NATURAL_GAS | Daily, weekly, and monthly |
| COPPER | Monthly, quarterly, and annual |
| ALUMINUM | Monthly, quarterly, and annual |
| WHEAT | Monthly, quarterly, and annual |
| CORN | Monthly, quarterly, and annual |
| COTTON | Monthly, quarterly, and annual |
| SUGAR | Monthly, quarterly, and annual |
| COFFEE | Monthly, quarterly, and annual |
| ALL_COMMODITIES | Monthly, quarterly, and annual |

Commodity series will retain their provider names, units, and native frequencies.

Persistra will not present scalar commodity series as tradeable futures or OHLC bars.

Commodity observations can be negative.

### Economic indicators

| Function | Supported frequencies or dimensions |
|---|---|
| REAL_GDP | Quarterly and annual |
| REAL_GDP_PER_CAPITA | Provider-native annual series |
| TREASURY_YIELD | Daily, weekly, and monthly for all provider maturities |
| FEDERAL_FUNDS_RATE | Daily, weekly, and monthly |
| CPI | Monthly and semiannual |
| INFLATION | Provider-native annual series |
| RETAIL_SALES | Provider-native monthly series |
| DURABLES | Provider-native monthly series |
| UNEMPLOYMENT | Provider-native monthly series |
| NONFARM_PAYROLL | Provider-native monthly series |

Treasury maturities will include:

- 3 months
- 2 years
- 5 years
- 7 years
- 10 years
- 30 years

Economic series will retain their provider units and frequency labels.

The provider supplies latest historical snapshots instead of complete data vintages.

Persistra will not claim vintage completeness or exact release availability.

### Provider and license boundary

v4.0.0 will include one Alpha Vantage adapter.

The normalized model will not depend on Alpha Vantage response names.

The release will target personal research under the 150 request plan.

Users must confirm their entitlements and permitted use.

A paid plan does not establish a right to redistribute provider data.

Realtime United States data requires the provider entitlement process.

Some commodity and economic feeds also carry source terms from FRED, EIA, or IMF.

The documentation will identify those terms.

See the following provider pages:

- [Alpha Vantage API documentation](https://www.alphavantage.co/documentation/)
- [Alpha Vantage premium plans](https://www.alphavantage.co/premium/)
- [Alpha Vantage market data policy](https://www.alphavantage.co/realtime_data_policy/)
- [Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/)

### Supported platform

v4.0.0 will support Linux on CPython 3.12, 3.13, and 3.14.

Other operating systems can work.

They will remain outside the support and CI contract.

## 3. Explicit exclusions

v4.0.0 will not contain:

- Topological data analysis
- TDA dependencies, plots, tests, documentation, or notebooks
- Fundamental data
- Company profiles, statements, earnings, listings, or calendars
- Insider transactions or institutional holdings
- News, transcripts, sentiment, or market rankings
- Alpha Vantage technical indicator endpoints
- Alpha Vantage fixed-window or sliding-window analytics
- Realtime or historical put-call ratio endpoints
- Realtime or historical volume-to-open-interest ratio endpoints
- Realtime option chains
- REALTIME_PUT_CALL_RATIO
- HISTORICAL_PUT_CALL_RATIO
- REALTIME_VOLUME_OPEN_INTEREST_RATIO
- HISTORICAL_VOLUME_OPEN_INTEREST_RATIO
- REALTIME_OPTIONS
- Theoretical option pricing
- Implied-volatility or Greek calculation
- Option strategies, payoff models, or position exposure
- Streaming data or managed polling
- Async APIs
- Automatic concurrent request fan-out
- A second data provider
- Dynamic provider plugins or entry-point discovery
- A public raw Alpha Vantage request method
- Point-in-time or vintage-completeness claims
- Automatic filling or interpolation
- Automatic calendar inference
- Automatic cross-provider instrument matching
- Accounting
- Portfolio construction or rebalancing
- Backtesting or trade execution
- Forecasting
- Optimization
- Machine learning
- CLI commands
- Dashboards
- HTML reports
- Theme systems
- Export frameworks
- v3 compatibility
- Compatibility with the abandoned v4 implementation
- Database migrations from an earlier Persistra schema
- Commercial licensing or redistribution guarantees

### v3 and abandoned v4 end of life

v3.0.2 is the final v3 release.

The prior v4 rewrite on feat/4.0-rewrite is abandoned.

Released history and the abandoned feature branch can remain in Git.

No v3 or abandoned v4 API, database, configuration, or file format will remain supported.

The implementation will start from develop on feat/4.0-data-platform.

It will not copy implementation files from the abandoned branch without a new design review.

## 4. Architecture

The package will use these concern boundaries:

~~~text
src/persistra/
├── __init__.py
├── errors.py
├── py.typed
├── model/
│   ├── __init__.py
│   ├── identity.py
│   ├── market.py
│   ├── options.py
│   ├── reference.py
│   └── series.py
├── data/
│   ├── __init__.py
│   ├── protocols.py
│   ├── cache.py
│   ├── store.py
│   ├── synthetic.py
│   └── alphavantage/
│       ├── __init__.py
│       ├── client.py
│       ├── transport.py
│       ├── securities.py
│       ├── quotes.py
│       ├── indices.py
│       ├── options.py
│       ├── pairs.py
│       ├── commodities.py
│       ├── economics.py
│       └── reference.py
├── analysis/
│   ├── __init__.py
│   ├── general.py
│   ├── market.py
│   ├── options.py
│   └── economics.py
└── viz/
    ├── __init__.py
    ├── general.py
    ├── market.py
    ├── options.py
    └── economics.py
~~~

The exact private module split can change during implementation.

The public concern boundaries cannot change without review.

The architecture will have five layers:

1. Provider transport and raw response classification
2. Provider-specific parsing and normalization
3. Provider-neutral models and DuckDB storage
4. Explicit analysis and transformation functions
5. Matplotlib visualization

No layer will make a network request through a lower data model operation.

No analysis or plot function will call Alpha Vantage.

No acquisition method will write normalized data to DuckDB automatically.

## 5. Public API rules

Package and subpackage initializers will define supported imports.

They will use explicit re-exports and __all__.

Names outside those exports will be implementation details.

The package will ship py.typed.

Public functions and types will use strict type annotations.

Public result containers will use frozen dataclasses where practical.

The contained pandas frames will remain ordinary mutable pandas objects.

Constructors and transformations will copy caller data.

They will not mutate caller frames.

The package version will use importlib.metadata.

A public API snapshot test will detect unreviewed additions, removals, and signature changes.

No public API will preserve v3 or abandoned v4 behavior.

## 6. Identity and catalog model

The catalog will stay small.

It will define only the identity needed for supported data.

### Instrument

InstrumentKind will contain:

- equity
- etf
- mutual_fund
- index
- fiat_pair
- crypto_pair
- commodity

Instrument will contain:

- instrument_id
- kind
- display_name
- base_currency when applicable
- quote_currency when applicable

InstrumentId will be an opaque string.

The public contract will not assign meaning to its text format.

### Listing

Listing will contain:

- listing_id
- instrument_id
- symbol
- exchange when known
- MIC when known
- trading currency when known
- source timezone when known

Persistra will not infer exchange, MIC, currency, or timezone.

Missing reference fields will remain missing.

### Provider symbol

ProviderSymbol will map a provider key to an instrument or listing.

Its identity will use:

- provider
- instrument kind
- provider symbol

The Alpha Vantage adapter can create a deterministic provider-scoped instrument identity.

That automatic identity will not claim equivalence with another provider.

A caller can register an explicit canonical mapping before data is saved.

The store will not merge populated instrument identities.

### Option contract

OptionContract will contain:

- provider contract ID
- underlying instrument ID
- expiration date
- strike
- call or put type

The provider contract ID will remain provider-scoped.

The decomposed terms will support comparison with a future provider.

Persistra will not infer multiplier, exercise style, settlement method, or deliverable terms.

### Series definition

SeriesDefinition will contain:

- series_id
- series kind
- display name
- provider series key
- native frequency
- unit
- geography when supplied
- seasonal adjustment when supplied
- maturity when applicable

SeriesKind will contain commodity and economic.

The client can create deterministic provider-scoped series identities.

Cross-provider series equivalence will require explicit registration.

### Catalog limits

The catalog will not contain:

- Entity precedence
- Automatic symbol matching
- Corporate ownership
- Security master history
- Exchange calendar schedules
- Revision graphs
- Provider plugin registration

## 7. Result metadata and provenance

Every public acquisition result will include ResultMetadata.

ResultMetadata will contain:

- provider
- provider operation
- redacted request parameters
- retrieval time in UTC
- provider as-of time when supplied
- entitlement mode when applicable
- cache status
- normalized schema version
- schema-drift diagnostics

Request parameters will never contain the API key.

Provider as-of time will remain missing when the response does not supply it.

Retrieval time will never stand in for market event time.

Each result will also identify the applicable instrument, series, or request scope.

DataFrame.attrs will not define identity or required provenance.

Serialization and pandas operations can remove attrs.

Required provenance will live in result metadata and stored columns.

## 8. Normalized data contracts

The data layer will use family-specific pandas contracts.

Each frame will have exact columns, order, types, sorting, and uniqueness rules.

Extra normalized columns will fail validation.

Provider parsers can accept unknown source fields under section 13.

### Common numeric policy

The normalized layer will use:

- float64 for required continuous values
- Pandas Float64 for optional continuous values
- Pandas Int64 for optional integral counts
- Pandas string for text identifiers
- Closed string enums for finite vocabularies
- pd.NA for missing or nonapplicable values

Crypto volume can use Float64 because base units can be fractional.

Option volume, open interest, and quoted sizes will use Int64.

All reported numeric values must be finite.

Missing values, nonapplicable values, and numeric zero will remain distinct.

The raw response cache will preserve source text.

Normalized frames will not retain source numeric strings.

### Common temporal policy

UTC-aware timestamps will represent instants.

Timezone-naive datetime64 dates will represent calendar dates.

Intraday bars will preserve the provider timestamp label.

They will also record the provider timezone and timestamp-position meaning.

The Alpha Vantage timestamp position will remain provider_label unless its documentation defines a boundary.

Daily and lower-frequency bars will use provider calendar labels.

Scalar series will retain the provider period label.

Period start and period end will be populated only when the source meaning is known.

All local filters will use inclusive bounds.

A start after an end will raise ValueError.

### BarFrame

BarFrame will contain:

~~~text
instrument_id
provider
provider_symbol
interval
date
timestamp
timestamp_position
source_timezone
session
price_adjustment
currency
open
high
low
close
adjusted_close
volume
dividend_amount
split_coefficient
provider_as_of
retrieved_at
~~~

The date column will apply to daily, weekly, and monthly bars.

The timestamp column will apply to intraday bars.

Exactly one temporal identity column will apply to each row.

Interval will contain one provider-native or explicitly derived interval.

TimestampPosition will contain:

- start
- end
- provider_label
- not_applicable

Session will contain:

- regular
- all
- not_applicable

Session records requested coverage.

It does not classify each bar against an inferred calendar.

PriceAdjustment will contain:

- raw
- adjusted
- not_applicable

Security adjusted daily, weekly, and monthly endpoints retain raw OHLC values.

Their adjusted close remains a separate value.

Security intraday rows record whether the requested OHLC values are adjusted.

FX, crypto, and index bars use not_applicable when adjustment has no source meaning.

Required OHLC values must be positive.

They must satisfy these relationships:

- low is not greater than open
- low is not greater than close
- high is not less than open
- high is not less than close

Applicable volume must be nonnegative.

FX and index volume will remain missing when the provider does not report it.

Corporate-action fields apply only when the endpoint supplies them.

Rows will sort by instrument, interval, adjustment, session, and time.

The same sort columns and time label will define row uniqueness.

### QuoteFrame

QuoteFrame will contain the common fields from GLOBAL_QUOTE and REALTIME_BULK_QUOTES.

It will contain:

~~~text
instrument_id
provider
provider_symbol
price
open
high
low
previous_close
change
change_percent
volume
latest_trading_day
observed_at
entitlement
provider_as_of
retrieved_at
~~~

The frame will preserve provider-reported change fields.

Analysis can calculate local change values from explicit inputs.

The frame will not treat a retrieval time as an observed market timestamp.

Prices must be positive.

Applicable volume must be nonnegative.

### TopOfBookFrame

TopOfBookFrame will contain:

~~~text
instrument_id
provider
provider_symbol
bid_price
bid_size
ask_price
ask_size
observed_at
provider_as_of
retrieved_at
~~~

Applicable prices must be nonnegative.

Applicable sizes must be nonnegative integers.

A locked or crossed provider snapshot will produce a diagnostic.

It will not fail normalization by default.

Midprice and spread will remain analysis outputs.

They will not enter the normalized source frame.

### ExchangeRateQuote

ExchangeRateQuote will be a typed scalar result.

It will contain:

- instrument ID
- provider
- base currency
- quote currency
- exchange rate
- bid when supplied
- ask when supplied
- provider timestamp when supplied
- provider timezone when supplied
- retrieval time

Rates must be positive and finite.

### CommoditySpotQuote

CommoditySpotQuote will be a typed scalar result.

It will contain:

- series ID
- provider
- metal
- value
- unit
- provider timestamp when supplied
- retrieval time

The result will not claim a tradeable instrument or venue.

### OptionChain

OptionChain will contain:

- underlying instrument ID
- provider symbol
- chain observation date
- result metadata
- one OptionContractFrame
- one OptionObservationFrame

An underlying market observation will remain separate from the chain.

It can exist in the bar or quote family.

The Alpha Vantage chain parser will not create or fetch that observation.

OptionContractFrame will contain:

~~~text
contract_id
provider
underlying_instrument_id
provider_symbol
expiration
strike
option_type
~~~

OptionObservationFrame will contain:

~~~text
contract_id
provider
chain_date
last
mark
bid
bid_size
ask
ask_size
volume
open_interest
implied_volatility
delta
gamma
theta
vega
rho
provider_as_of
retrieved_at
~~~

Strike must be positive.

Expiration cannot precede the chain date.

Reported option prices must be nonnegative.

Reported volume, open interest, and sizes must be nonnegative.

Reported implied volatility must be nonnegative.

Reported Greeks must be finite when present.

The validator will not impose pricing-model relationships on source observations.

The validator will report locked or crossed quotes as diagnostics.

It will not repair them.

The chain will not infer an underlying price from another endpoint.

### SeriesFrame

SeriesFrame will contain:

~~~text
series_id
provider
provider_series
series_kind
frequency
period_label
period_start
period_end
value
unit
geography
seasonal_adjustment
maturity
provider_as_of
retrieved_at
~~~

PeriodLabel will preserve the provider label.

Period start and period end can remain missing.

Frequency will use a supported native frequency.

Value must be finite.

The contract will not require positive values.

Rows will sort by series, frequency, maturity, and period label.

That identity will be unique within one normalized result.

### Reference frames

InstrumentSearchResult will normalize:

- provider symbol
- name
- provider type
- region
- market open
- market close
- timezone
- currency
- provider match score

Search results will not establish canonical identity automatically.

IndexCatalogResult will normalize every provider catalog field with stable names.

It can populate provider-scoped index identities.

MarketStatusResult will normalize:

- market type
- region
- primary exchanges
- local open
- local close
- current status
- provider notes
- retrieval time

Local open and close values will remain local wall-clock values.

The result will not infer a calendar.

### Empty and combined results

An empty result will retain its complete schema and dtypes.

Bounds outside available data will return a valid empty result.

Public combination utilities will validate every input.

They will preserve all required identity and provenance columns.

They will reject incompatible schemas.

## 9. Provider-neutral capabilities

The data package will publish small runtime-checkable protocols where useful.

The protocol set will contain:

- BarSource
- QuoteSource
- OptionChainSource
- ScalarSeriesSource
- ReferenceSource

Each protocol will describe normalized capability behavior.

It will not describe provider authentication or endpoint names.

A provider can implement only the protocols it supports.

The protocols will not require:

- Plugin discovery
- Registration hooks
- A common provider configuration object
- A universal request model
- A universal result type

Alpha Vantage-specific parameters will remain on the Alpha Vantage adapter.

The protocol layer will not be a claim that a second provider exists.

## 10. Alpha Vantage public client

The package will provide one configured client:

~~~python
from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env(requests_per_minute=150)
~~~

The client will support:

- Direct API-key construction
- PERSISTRA_ALPHAVANTAGE_API_KEY
- A configurable base URL for tests
- A configurable raw cache directory
- Configurable cache ages by family
- A configurable request timeout
- A 30 second timeout default
- A numeric requests-per-minute limit
- Injectable transport, clock, delay, and random sources
- Strict provider-schema diagnostics for tests

The client will expose typed namespaces.

### Securities namespace

The securities namespace will provide:

~~~text
client.securities.bars(...)
client.securities.iter_intraday_months(...)
~~~

The bars method will accept a symbol, instrument kind, interval, and provider options.

Instrument kind will distinguish equity, ETF, and mutual fund.

The method will not infer that kind from a symbol.

The month iterator will yield one validated BarSet for each request.

It will not concatenate all months.

### Quotes namespace

The quotes namespace will provide:

~~~text
client.quotes.latest(...)
client.quotes.bulk(...)
client.quotes.top_of_book(...)
~~~

The bulk methods will divide inputs into provider-sized requests.

They will execute requests in sequence.

They will return one combined validated result after all requests succeed.

A failed chunk will raise an error with its input symbols.

The method will not return a partial combined frame.

### Indices namespace

The indices namespace will provide:

~~~text
client.indices.bars(...)
client.indices.catalog(...)
~~~

Index bars will accept daily, weekly, or monthly intervals.

### Options namespace

The options namespace will provide:

~~~text
client.options.historical_chain(...)
client.options.iter_historical_chains(...)
~~~

The single-chain method will request one date.

An omitted date will use the provider default.

The iterator will accept explicit start and end dates.

It will issue requests in date order.

The iterator will not use or infer a trading calendar.

It will skip a date only after an unambiguous provider no-data response.

Other provider errors will stop iteration.

Each successful iteration will yield one validated OptionChain.

### Pair namespaces

The pair namespaces will provide:

~~~text
client.fx.rate(...)
client.fx.bars(...)
client.crypto.rate(...)
client.crypto.bars(...)
~~~

Pair methods will use explicit base and quote values.

They will not accept a combined ambiguous symbol.

### Commodity namespace

The commodity namespace will provide:

~~~text
client.commodities.spot(...)
client.commodities.series(...)
~~~

The series method will validate frequency against the selected commodity.

### Economics namespace

The economics namespace will provide:

~~~text
client.economics.series(...)
~~~

The method will validate frequency and maturity against the selected indicator.

### Reference namespace

The reference namespace will provide:

~~~text
client.reference.search(...)
client.reference.market_status(...)
~~~

### Request and result rules

Public methods will use keyword-only arguments after their primary identity arguments.

They will use ordinary parameters instead of public request classes where practical.

The client will not expose a public raw function request.

Each acquisition call will return normalized data and metadata.

It will not write to DuckDB.

It will not start background work.

It will not use asyncio.

It will not perform automatic concurrent fan-out.

## 11. Entitlement and freshness modes

EntitlementMode will contain:

- historical
- delayed
- realtime
- not_applicable

The default will be historical when the endpoint accepts an entitlement parameter.

Realtime or delayed access will require an explicit caller choice.

The adapter will send only provider-supported entitlement parameters.

An unsupported mode will fail before network access.

The 150 request target will not appear as an entitlement enum.

Rate and entitlement will remain separate configuration concepts.

Realtime quote, top-of-book, spot, and market-status calls will use the network by default.

Historical families can use a fresh raw cache entry.

Historical time series, option chains, catalogs, commodities, and economic series will use a 24 hour default cache age.

Delayed and realtime requests will not reuse an online cache entry by default.

Offline mode will prohibit network access.

Offline mode will use the newest matching cache entry regardless of age.

Refresh and offline modes cannot apply together.

## 12. Transport, retry, and rate control

The client will use one shared synchronous Requests session.

Tests can inject another transport.

Alpha Vantage can return error envelopes with HTTP status 200.

The client will classify the body before parsing data.

### Response classification

The adapter will classify:

- Invalid or absent credentials
- Missing entitlement
- Provider rate limits
- Invalid functions or parameters
- Unsupported symbols or no-data results
- Malformed success bodies
- HTTP client failures
- HTTP server failures

Authentication failures will raise AuthenticationError.

Entitlement failures will raise EntitlementError.

Rate-limit failures will raise RateLimitError.

Invalid requests and malformed success bodies will raise ResponseError.

Connection failures and exhausted server responses will raise TransportError.

### Retries

The client will retry:

- Connection failures
- Timeouts
- HTTP 429
- HTTP 5xx
- Provider rate-limit envelopes

Three retries will mean no more than four total attempts.

Every retry will pass through the proactive rate limiter.

Backoff will use bounded exponential delay with jitter.

Authentication, entitlement, invalid request, and malformed body failures will fail immediately.

### Proactive rate control

The client will use a shared thread-safe token limiter.

The default rate will be 150 requests each minute.

The default capacity will smooth requests instead of permitting a 150 request burst.

The caller can configure another positive numeric rate.

Offline and cache-hit operations will not consume request capacity.

The client will not try to maximize the configured rate.

### Logging and secrets

Persistra will log through the standard persistra logger namespace.

The library will not install handlers.

Debug logs can record:

- Provider operation
- Attempt number
- Cache state
- Elapsed time
- Redacted parameter names

Logs and exceptions will not contain:

- API keys
- Full authenticated URLs
- Authentication headers
- Raw response bodies

Tests will inspect logs and exceptions for secret leakage.

## 13. Raw response cache and schema drift

The raw response cache and normalized DuckDB store will remain separate.

The cache will support JSON, CSV, and other provider response bytes.

Each entry will contain:

- Raw response bytes
- Response media type
- Retrieval time in UTC
- Provider operation
- Redacted request parameters
- A cache format version

Cache identity will include every provider parameter that can change the response.

It will exclude the API key.

Atomic publication will prevent partial entries.

A failed refresh will preserve the prior entry.

A corrupt cache entry will count as a miss online.

It will raise CacheError offline.

A network failure will not return stale data automatically.

Every cached response will pass response classification and normalization again.

Cache presence will never establish validity.

### Provider schema drift

Missing or malformed required source fields will fail normalization.

Contradictory source fields will fail normalization.

Unknown extra provider fields will not enter normalized frames automatically.

They will create a schema-drift diagnostic.

The raw cache will preserve their values.

Strict provider-schema mode will turn unknown fields into ResponseError.

Tests and fixture audits will use strict mode.

Normal acquisition will use diagnostic mode.

## 14. DuckDB store

The normalized store will use one local DuckDB database.

The store will use explicit connection objects.

It will not use DuckDB global connections.

The supported write model will use one process.

The store will not promise multi-process writers.

### Public store API

The package will provide DuckDBStore.

Typical use will be explicit:

~~~python
result = client.options.historical_chain("IBM", date="2025-01-17")
store.save(result)
~~~

The store will provide typed save and load operations for each result family.

It will also provide filtered frame queries for research.

Loads will return the same normalized result types as acquisition where practical.

The store will not make network requests.

The client will not call store methods.

### Tables

The schema will include:

- instruments
- listings
- provider_symbols
- series_definitions
- bars
- quotes
- top_of_book
- exchange_rate_quotes
- commodity_spot_quotes
- option_contracts
- option_observations
- series_observations
- market_status_observations
- acquisition_snapshots

Search results and index catalog records can populate provider-scoped reference tables.

They will not create cross-provider mappings.

### Observation identity and revisions

Each observation family will define a semantic source key.

Examples include:

- Instrument, interval, adjustment, session, and time for bars
- Instrument and provider observation time for quotes
- Contract and chain date for option observations
- Series, frequency, maturity, and period label for scalar series

The store will hash normalized source values for each semantic key.

An identical repeated observation will not create another value version.

The store will update its last-seen retrieval time.

A changed observation will create another normalized version.

The first-seen and last-seen times describe Persistra retrieval.

They do not describe provider publication or market availability.

Default queries will return the newest retrieved version for each semantic key.

An explicit retrieved-before filter can reconstruct Persistra-observed state.

Documentation will not call this provider point-in-time data.

### Transactions and schema version

Save operations will validate before opening a write transaction.

A failed save will roll back the complete transaction.

Partial family writes will not remain.

DuckDB constraints and explicit checks will enforce key invariants.

A schema version table will identify the fixed v4 schema.

A mismatch will raise StoreError without modifying the file.

v4.0.0 will not include migration code.

Creating a new store will require an explicit create operation.

Opening a missing store for read will fail without creating a file.

### Query behavior

Store filters will execute in DuckDB.

Loads will return sorted and validated data with exact dtypes.

Dates and timestamps will round-trip exactly.

Missing applicability will round-trip as pd.NA.

Pandas indexes and DataFrame.attrs will not enter storage.

## 15. Data utilities

The data package will provide explicit utilities before statistical analysis.

### Wide frames

pivot_bars will convert selected bar values into a wide frame.

The caller must select a field such as close or adjusted_close.

The function will not choose an adjustment basis.

Columns will identify instrument and source where necessary.

pivot_series will convert compatible scalar series into a wide frame.

It will require compatible frequencies unless the caller resamples first.

### Alignment

Alignment will support:

- intersection
- union

Intersection will keep labels shared by every selected series.

Union will keep every label and preserve gaps.

No alignment function will fill values.

### Resampling

Resampling will require:

- Target frequency
- Aggregation rule
- Timezone or calendar-date rule where needed
- Session inclusion policy for market bars

OHLC resampling will use:

- First value for open
- Maximum value for high
- Minimum value for low
- Last value for close
- Sum for applicable volume

The operation will not claim equality with a provider-native response.

It will mark the output as derived in result metadata.

### As-of alignment

As-of alignment will require an explicit maximum staleness.

It will retain each source observation label.

It will report the matched age.

It will not present monthly economic values as daily observations.

## 16. General analysis

The general analysis layer will work with explicit wide numeric frames.

It will provide:

- coverage_summary
- summary_statistics
- absolute_change
- percentage_change
- log_change
- simple_returns
- log_returns
- rebase
- cumulative_returns
- drawdowns
- rolling_mean
- rolling_standard_deviation
- rolling_volatility
- rolling_zscore
- covariance_matrix
- correlation_matrix

### Change and return meaning

Absolute and percentage changes can apply to general numeric series.

Simple and log returns will apply to price-like levels.

The caller will choose the function.

Persistra will not infer economic meaning from a column name.

Log functions will reject zero or negative levels.

Return functions will not bridge a missing level.

The first valid change or return will remain missing.

### Missing values

Functions will calculate each column independently.

Leading, internal, and trailing gaps will remain visible.

Rolling functions will require complete windows by default.

An internal gap will produce a missing rolling result for its affected window.

Path-dependent functions will reject an internal gap in an observed span.

They can permit leading and trailing gaps.

### Statistical conventions

Annualized functions will require a positive periods_per_year value.

No function will default to 252.

Sample statistics will use ddof=1.

Correlation and covariance will use pairwise complete observations.

Quantiles will use documented pandas conventions.

Infinite inputs will raise AnalysisError.

Statistics with insufficient observations will return NaN.

The documentation will state every minimum observation count.

### Excluded general analysis

The general layer will not provide:

- Regression
- Hypothesis tests
- Stationarity tests
- Forecasting
- Optimization
- Portfolio statistics

## 17. Specialized analysis

### Market analysis

The market analysis module will provide:

- midprice
- absolute_spread
- relative_spread
- bar_range
- true_range
- volume_summary
- realized_volatility
- session_coverage

Midprice and spread functions will accept top-of-book observations.

They will preserve missing bid or ask values.

Realized volatility will require explicit returns and periods_per_year.

Session coverage will describe observed labels.

It will not infer expected exchange bars.

### Commodity analysis

Commodity data will use the general level, change, rebasing, rolling, and correlation functions.

The package will not model commodity futures, contracts, rolls, or term structures.

### Economic analysis

The economic analysis module will provide:

- basis_point_change
- growth_rate
- yield_curve
- yield_curve_history

Basis-point change will apply only after an explicit rate-unit selection.

Growth rate will require an explicit positive lag.

Yield-curve construction will require one observation date and compatible Treasury series.

Yield-curve history will preserve missing maturities.

The module will not interpolate a yield curve.

It will not perform seasonal adjustment, nowcasting, or recession classification.

### Options analysis

The options analysis module will provide:

- Chain filters by expiration, option type, strike, and contract
- days_to_expiration
- moneyness
- log_moneyness
- option_midprice
- option_absolute_spread
- option_relative_spread
- intrinsic_value
- time_value
- chain_summary
- implied_volatility_smile
- implied_volatility_surface
- greek_profile

Moneyness, intrinsic value, and time value will require an explicit underlying price.

The caller can supply a scalar price.

The caller can also select a stored bar and field explicitly.

The function will not select raw or adjusted close automatically.

Implied-volatility surface preparation will organize observed values.

It will not fit, smooth, or interpolate a surface.

Greek profiles will use provider-supplied values.

Persistra will not calculate Greeks.

The options module will not provide:

- Pricing models
- Put-call parity tests
- Strategy construction
- Payoff diagrams
- Position or portfolio Greeks
- Options backtests

## 18. Matplotlib visualization

Matplotlib will be the only visualization backend.

Plot functions will accept caller axes where practical.

They will return the axes they use.

Functions with price and volume panels will return a typed pair of axes.

No function will change global rcParams.

No function will apply a global theme.

### General plots

The public general plot set will include:

- plot_series
- plot_rebased
- plot_distribution
- plot_rolling_statistic
- plot_correlation
- plot_coverage

### Market plots

The public market plot set will include:

- plot_candlesticks
- plot_returns
- plot_cumulative_returns
- plot_drawdowns
- plot_rolling_volatility
- plot_bid_ask_history
- plot_spread_history

Quote-history plots will require more than one stored snapshot.

A single latest quote will not have a dedicated plot.

### Options plots

The public options plot set will include:

- plot_option_chain_prices
- plot_option_volume_open_interest
- plot_implied_volatility_smile
- plot_implied_volatility_surface
- plot_greek_profile

The implied-volatility surface will use a two-dimensional heatmap.

It will not imply interpolation between missing observations.

### Economic and commodity plots

The public plot set will include:

- plot_scalar_series
- plot_series_change
- plot_yield_curve
- plot_yield_curve_history

The general series plots will also support commodity and economic values.

### Visualization limits

The package will not include:

- Plotly
- Interactive controls
- Dashboards
- Reports
- Themes
- Automatic figure collections

## 19. Synthetic data and provider fixtures

The package will provide a synthetic generator for every public normalized contract.

Generators will cover:

- Every instrument kind
- Every bar interval class
- Raw and adjusted security values
- Regular and all-session intraday data
- Quotes and top-of-book snapshots
- FX and crypto exchange rates
- Commodity spot values
- Historical option chains
- Commodity and economic series
- Treasury curves with missing maturities
- Reference search and market status results

Synthetic price paths will contain volatility and volume regimes.

Synthetic option chains will contain several strikes and expirations.

They will preserve valid contract and quote relationships.

Synthetic series will preserve units and native frequency rules.

The repository will commit synthetic provider responses for every supported endpoint.

It will not commit downloaded market or economic data.

Automated tests and notebooks will use only synthetic data and responses.

## 20. Exceptions

The public exception hierarchy will be:

~~~text
PersistraError
├── ProviderError
│   ├── AuthenticationError
│   ├── EntitlementError
│   ├── RateLimitError
│   ├── ResponseError
│   └── TransportError
├── CacheError
├── StoreError
├── DataValidationError
└── AnalysisError
~~~

Programmer errors will use standard exceptions.

Invalid argument values and incompatible modes will use ValueError or TypeError.

Provider exceptions will include the operation and requested identity.

They will never contain API keys or authenticated URLs.

DataValidationError will name each failed normalized rule.

AnalysisError will identify the failed mathematical assumption.

## 21. Dependencies and packaging

Every installation will contain every runtime capability.

v4.0.0 will provide no package extras.

Required runtime dependencies will be:

- NumPy
- pandas
- Matplotlib
- Requests
- platformdirs
- DuckDB

The rewrite will remove:

- Ripser.py
- Persim
- Plotly
- Streamlit
- SciPy
- scikit-learn
- cvxpy
- Optuna
- sqlglot
- Jinja
- exchange-calendars
- pytz
- structlog

The Foundation checkpoint will verify current dependency documentation and types.

Each direct dependency will have a tested lower bound and exclusive upper bound.

The package will import only declared direct dependencies.

Development dependencies will include:

- Ruff
- Pyright
- pytest
- pytest-cov
- Hypothesis
- pandas stubs
- pre-commit

Documentation dependencies will include:

- MkDocs Material
- mkdocstrings
- mkdocs-jupyter
- nbclient
- nbformat
- ipykernel

The project will remove the CLI entry point.

Package metadata will describe primary market and economic data research.

## 22. Documentation

The maintained documentation suite will contain:

- A concise README
- A documentation index
- A getting-started guide
- A data-model and storage guide
- An Alpha Vantage acquisition and entitlement guide
- An analysis and visualization guide
- A generated public API reference
- This roadmap

The acquisition guide will cover:

- API-key configuration
- The 150 request target
- Realtime entitlement
- Cache and offline behavior
- Rate control and retries
- Licensing and source terms
- Manual live certification

The data-model guide will cover:

- Instrument and series identity
- Applicability and missing values
- Temporal labels
- Provenance
- DuckDB storage
- Retrieval-time revision limits

The analysis guide will state every important mathematical assumption.

Documentation will use short, active, plain American English.

The rewrite will remove formal ASD-STE100 claims and dedicated enforcement.

Documentation checks will validate:

- Links
- Python snippets
- Generated API pages
- Strict MkDocs output

### Research notebooks

The repository will contain exactly two maintained notebooks:

1. Cross-asset market, commodity, and economic exploration
2. Historical option-chain exploration

The first notebook will demonstrate:

- Security and pair bars
- An index
- Quotes and top-of-book history
- Commodity and economic series
- DuckDB storage
- Alignment and general analysis
- Representative plots

The second notebook will demonstrate:

- Historical chain acquisition
- Contract filtering
- Explicit underlying-price selection
- Moneyness and spread analysis
- Implied volatility and Greek profiles
- Representative option plots

Automated notebook execution will use synthetic data.

The notebooks will not use credentials or network access.

Live acquisition instructions will use prose or clearly inactive substitution cells.

## 23. Verification contract

The complete gate will include:

- Ruff lint
- Strict Pyright
- pytest
- Combined statement and branch coverage of at least 90 percent
- Documentation validation
- Strict MkDocs build
- Offline notebook execution
- Public API snapshot validation
- Lockfile validation
- Wheel and source-distribution builds
- Clean wheel installation
- Installed-package import smoke tests

CI will run the main gate on Linux with Python 3.12, 3.13, and 3.14.

CI will resolve the lowest-direct and highest dependency bands on Python 3.12.

Both bands must pass.

### Contract tests

Contract tests will cover:

- Exact columns and order
- Exact dtypes
- Sorting and uniqueness
- Every applicability rule
- Empty typed results
- Inclusive bounds
- Nonmutation of inputs
- Provider-scoped identity
- Explicit canonical mappings
- Missing source reference fields
- Metadata and provenance

### Provider tests

Synthetic provider fixtures will cover every included Alpha Vantage function.

Tests will cover:

- Every security frequency
- Every intraday interval
- Raw and adjusted security modes
- Regular and all-session modes
- Historical month iteration
- Historical, delayed, and realtime entitlement parameters
- Single and bulk quote methods
- Bulk chunk boundaries and ordering
- Top-of-book normalization
- Symbol search and market status
- Daily, weekly, and monthly index data
- Index catalog parsing
- Historical option chains
- Option contract and expiration filters
- Historical option date iteration
- Every FX and crypto frequency
- Every commodity and valid frequency
- Every economic indicator
- Every Treasury maturity
- JSON and CSV responses where supported
- Error Message, Note, and Information envelopes
- HTTP 429 and HTTP 5xx
- Invalid credentials and missing entitlements
- Malformed, missing, duplicate, and nonfinite data
- Unknown provider fields in diagnostic and strict modes

### Cache and transport tests

Tests will cover:

- Fresh, stale, refresh, and offline behavior
- Family cache policies
- Cache identity
- Atomic publication
- Corrupt entries
- Validation after cache reads
- Refresh failure preservation
- Four-attempt retry limits
- Backoff and jitter
- Shared rate control
- Bulk request pacing
- Secret redaction

### Store tests

Tests will cover:

- Exact round trips for every normalized family
- Reference mapping
- Identical-observation deduplication
- Changed-observation versioning
- First-seen and last-seen retrieval times
- Latest-version queries
- Retrieved-before queries
- SQL filtering
- Transaction rollback
- Missing-value round trips
- Missing-file behavior
- Schema-version rejection without mutation
- One-process write behavior

### Analysis tests

Tests will use hand-calculated examples and useful Hypothesis invariants.

They will cover:

- Absolute, percentage, and log changes
- Simple and log returns
- Leading, internal, and trailing gaps
- Explicit annualization
- Rolling complete-window behavior
- Covariance and correlation
- Alignment and resampling
- As-of staleness limits
- Market spread and true-range calculations
- Basis-point and growth-rate calculations
- Yield-curve construction
- Option moneyness and value calculations
- Explicit underlying-price requirements
- Option chain summaries
- Observed implied-volatility and Greek preparation

### Visualization tests

Visualization tests will inspect:

- Artists
- Labels
- Axis reuse
- Price and volume panel returns
- Missing-data display behavior
- Unchanged global rcParams

Tests will not depend on pixel snapshots.

### Network isolation and live certification

Normal tests and notebooks will prohibit network access.

An opt-in live smoke suite will use an environment API key.

It will never run in normal CI.

The release checklist will require one manual live pass against the 150 request plan.

The live pass will verify every supported family and required entitlement.

It will not compare exact market values.

It will produce a redacted schema and outcome report.

The report will not contain or commit provider data.

## 24. Implementation checkpoints

Each checkpoint must leave a working package and a green complete gate.

### 1. Governance and clean branch

This checkpoint will:

- Use feat/4.0-data-platform from develop
- Approve this roadmap
- Update contributor and agent instructions
- Define the v4 changelog section
- Define the metadata change plan
- Remove formal controlled-language enforcement

It will not change the package version.

### 2. Foundation and contracts

This checkpoint will:

- Remove tracked v3 implementation paths
- Establish the minimal typed package
- Define the exception hierarchy
- Define catalog identities
- Define every normalized result contract
- Add exact validators
- Add synthetic generators
- Establish public API snapshots
- Verify runtime dependency bands

### 3. Transport and storage foundation

This checkpoint will:

- Add Alpha Vantage transport
- Add response classification
- Add retries and rate control
- Add the raw response cache
- Add schema-drift diagnostics
- Add the fixed DuckDB schema
- Add transactions and schema checks
- Keep acquisition and storage explicit

### 4. Securities and live market slice

This checkpoint will:

- Add every security time-series endpoint
- Add recent and historical intraday acquisition
- Add native daily, weekly, and monthly acquisition
- Add quote and top-of-book endpoints
- Add symbol search and market status
- Add bulk request chunking
- Add persistence
- Add representative analysis and plots

### 5. Indices and currency pairs slice

This checkpoint will:

- Add index data and catalog support
- Add FX exchange rates and bars
- Add crypto exchange rates and bars
- Add native frequency coverage
- Add persistence
- Add representative analysis and plots

### 6. Commodity and economic slice

This checkpoint will:

- Add gold and silver spot quotes
- Add every historical commodity endpoint
- Add every valid commodity frequency
- Add every economic indicator
- Add every Treasury maturity
- Add scalar-series persistence
- Add yield-curve analysis and plots

### 7. Historical options slice

This checkpoint will:

- Add option contract identity
- Add historical chain acquisition
- Add contract and expiration filters
- Add date iteration
- Add chain persistence and versioning
- Add explicit-underlying-price analysis
- Add option plots

### 8. Cross-family analysis

This checkpoint will:

- Complete alignment and resampling
- Complete change and return functions
- Complete rolling statistics
- Complete summaries and matrices
- Complete missing-data rules
- Complete cross-family plots

### 9. Research workflow

This checkpoint will:

- Complete the reduced guide suite
- Complete two offline notebooks
- Complete the generated API reference
- Complete licensing and entitlement documentation
- Remove obsolete documentation paths

### 10. Assurance

This checkpoint will:

- Audit fixtures for every supported endpoint
- Complete the Python version matrix
- Complete dependency-band checks
- Enforce 90 percent coverage
- Validate public API snapshots
- Build distributions
- Test a clean installation
- Document the live certification procedure

Shared private helpers will appear only after concrete uses justify them.

No checkpoint will add temporary compatibility code.

## 25. Release acceptance criteria

v4.0.0 will be ready for release preparation when all these conditions are true:

- No tracked v3 or abandoned v4 implementation remains.
- No TDA code, dependency, test, document, or notebook remains.
- Every normalized contract passes its complete contract tests.
- The minimal catalog supports explicit provider and canonical mappings.
- Every included Alpha Vantage function has a synthetic fixture and parser test.
- Security data supports every included native frequency.
- Realtime quote and top-of-book access uses explicit entitlement behavior.
- Bulk quote methods preserve order and provider limits.
- Index data uses INDEX_DATA instead of a proxy.
- Historical option chains preserve every supported source observation.
- Option analysis requires an explicit underlying price where needed.
- Every commodity endpoint supports every valid native frequency.
- Every economic indicator and Treasury maturity has direct coverage.
- Cache, retry, rate, offline, and redaction tests pass.
- DuckDB round trips and version rules pass for every family.
- General analysis uses explicit change, return, gap, and annualization rules.
- Specialized market, option, and economic analysis passes hand-calculated tests.
- Matplotlib functions preserve caller axes and global style.
- Both notebooks execute without credentials or network access.
- The repository contains no downloaded provider data.
- Linux CI passes on Python 3.12, 3.13, and 3.14.
- Both direct dependency bands pass.
- Combined statement and branch coverage is at least 90 percent.
- The wheel and source distribution build successfully.
- A clean wheel installation passes public import smoke tests.
- The manual 150 plan certification procedure is ready.
- Documentation states all important assumptions, exclusions, entitlements, and source terms.

Humans will control version changes, tags, pushes, publication, and release merges.

This roadmap does not authorize a release action.

## 26. Post-4.0 candidates

Each candidate needs a separate product question and design review.

### Another data provider

A second provider can implement the approved capability protocols.

Its review must define identity mappings, source precedence, and capability differences.

### Realtime options

Realtime chains need a higher provider plan and separate entitlement review.

They also need explicit freshness and snapshot-volume policies.

### Fundamentals and ownership

Fundamentals need report, fact, unit, period, and revision contracts.

Ownership needs transaction and holding identities.

These families will not enter as raw provider-shaped frames.

### Alternative and textual data

News, sentiment, and transcripts need document, text, and attribution contracts.

They also need distinct analysis questions.

### Managed polling or streaming

Continuous acquisition needs scheduling, cancellation, recovery, and retention policies.

It will not grow out of one-shot methods without a new design.

### Option pricing and strategies

Pricing needs rate, dividend, exercise, settlement, and numerical-method policies.

Strategy analysis needs positions, multipliers, transaction costs, and portfolio scope.

### Point-in-time and vintage data

This capability needs reliable publication evidence and revision histories.

Retrieval timestamps alone cannot support the claim.

## 27. Primary references

- [Alpha Vantage API documentation](https://www.alphavantage.co/documentation/)
- [Alpha Vantage premium plans](https://www.alphavantage.co/premium/)
- [Alpha Vantage market data policy](https://www.alphavantage.co/realtime_data_policy/)
- [Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/)
- [DuckDB Python API](https://duckdb.org/docs/stable/clients/python/overview)
- [DuckDB concurrency](https://duckdb.org/docs/stable/connect/concurrency)
- [pandas documentation](https://pandas.pydata.org/docs/)
- [Matplotlib documentation](https://matplotlib.org/stable/)
