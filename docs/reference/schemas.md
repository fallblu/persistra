# Normalized schemas

Normalized frame contracts require the exact columns, order, and pandas dtypes shown below.
Constructors validate them and copy the frame. Nullable extension dtypes preserve missing
applicability without converting values to ordinary floating-point placeholders.

## Bars

`BarSet.frame` uses this schema:

<!-- frame-contract: bars -->

- Required values: `instrument_id`, `provider`, `provider_symbol`, `interval`,
  `timestamp_position`, `source_timezone`, `session`, `price_adjustment`, `open`, `high`,
  `low`, `close`, `retrieved_at`
- Identity key: `instrument_id`, `interval`, `price_adjustment`, `session`, `date`, `timestamp`
- Sort order: `instrument_id`, `interval`, `price_adjustment`, `session`, `date`, `timestamp`
- Invariant checks: `positive-ohlc`, `nonnegative-activity`,
  `exactly-one-temporal-identity`, `ohlc-bounds`, `instrument-scope`, `metadata-scope`

| Column | pandas dtype | Meaning |
|---|---|---|
| `instrument_id` | `string` | Normalized instrument identity |
| `provider` | `string` | Source provider |
| `provider_symbol` | `string` | Source symbol |
| `interval` | `string` | Native or derived bar interval |
| `date` | `datetime64[ns]` | Calendar label for nonintraday bars |
| `timestamp` | `datetime64[ns, UTC]` | Instant for intraday bars |
| `timestamp_position` | `string` | Meaning of the provider timestamp label |
| `source_timezone` | `string` | Provider or resampling timezone |
| `session` | `string` | Regular, all, or nonapplicable session scope |
| `price_adjustment` | `string` | Raw, adjusted, or nonapplicable price basis |
| `currency` | `string` | Price currency when supplied |
| `open` | `float64` | Positive open |
| `high` | `float64` | Positive high |
| `low` | `float64` | Positive low |
| `close` | `float64` | Positive close |
| `adjusted_close` | `Float64` | Nullable adjusted close |
| `volume` | `Float64` | Nullable nonnegative volume |
| `dividend_amount` | `Float64` | Nullable nonnegative dividend amount |
| `split_coefficient` | `Float64` | Nullable nonnegative split coefficient |
| `provider_as_of` | `datetime64[ns, UTC]` | Optional source as-of instant |
| `retrieved_at` | `datetime64[ns, UTC]` | Retrieval provenance |

Exactly one of `date` and `timestamp` applies per row. Rows sort and deduplicate by instrument,
interval, price adjustment, session, and temporal label. High and low must contain open and
close. Instrument IDs match the enclosing `Instrument`; pair currencies match its quote
currency. Provider and retrieval time match the result metadata.

## Latest quotes

`QuoteSet.frame` uses this schema:

<!-- frame-contract: latest-quotes -->

- Required values: `instrument_id`, `provider`, `provider_symbol`, `price`, `entitlement`,
  `retrieved_at`
- Identity key: `provider`, `provider_symbol`
- Sort order: source order
- Invariant checks: `positive-price`, `finite-quote-fields`, `nonnegative-volume`,
  `metadata-scope`

| Column | pandas dtype |
|---|---|
| `instrument_id` | `string` |
| `provider` | `string` |
| `provider_symbol` | `string` |
| `price` | `float64` |
| `open` | `Float64` |
| `high` | `Float64` |
| `low` | `Float64` |
| `previous_close` | `Float64` |
| `change` | `Float64` |
| `change_percent` | `Float64` |
| `volume` | `Float64` |
| `latest_trading_day` | `datetime64[ns]` |
| `observed_at` | `datetime64[ns, UTC]` |
| `entitlement` | `string` |
| `provider_as_of` | `datetime64[ns, UTC]` |
| `retrieved_at` | `datetime64[ns, UTC]` |

Price is positive. Optional OHLC, previous close, and change fields must be finite when
observed. Volume is nullable and nonnegative. Provider, retrieval time, and entitlement match
the result metadata.

## Top of book

`TopOfBookSet.frame` uses this schema:

<!-- frame-contract: top-of-book -->

- Required values: `instrument_id`, `provider`, `provider_symbol`, `retrieved_at`
- Identity key: `provider`, `provider_symbol`
- Sort order: source order
- Invariant checks: `nonnegative-quotes`, `size-requires-price`, `quote-state-diagnostics`,
  `metadata-scope`

| Column | pandas dtype |
|---|---|
| `instrument_id` | `string` |
| `provider` | `string` |
| `provider_symbol` | `string` |
| `bid_price` | `Float64` |
| `bid_size` | `Int64` |
| `ask_price` | `Float64` |
| `ask_size` | `Int64` |
| `observed_at` | `datetime64[ns, UTC]` |
| `provider_as_of` | `datetime64[ns, UTC]` |
| `retrieved_at` | `datetime64[ns, UTC]` |

Prices and sizes are nullable and nonnegative. Missing sides remain missing. Provider and
retrieval time match the result metadata.

## Option contracts

`OptionChain.contracts` uses this schema:

<!-- frame-contract: option-contracts -->

- Required values: `contract_id`, `provider`, `underlying_instrument_id`, `provider_symbol`,
  `expiration`, `strike`, `option_type`
- Identity key: `provider`, `contract_id`
- Sort order: `expiration`, `strike`, `option_type`, `contract_id`
- Invariant checks: `positive-strike`, `known-option-type`,
  `expiration-on-or-after-chain-date`, `chain-scope`, `metadata-scope`

| Column | pandas dtype |
|---|---|
| `contract_id` | `string` |
| `provider` | `string` |
| `underlying_instrument_id` | `string` |
| `provider_symbol` | `string` |
| `expiration` | `datetime64[ns]` |
| `strike` | `float64` |
| `option_type` | `string` |

Strikes are positive, option type is `call` or `put`, and expiration cannot precede the chain
date. Contract providers match the result metadata. Underlying IDs and provider symbols match
the enclosing chain. Rows sort by expiration, strike, option type, and contract ID.

## Option observations

`OptionChain.observations` uses this schema:

<!-- frame-contract: option-observations -->

- Required values: `contract_id`, `provider`, `chain_date`, `retrieved_at`
- Identity key: `provider`, `contract_id`, `chain_date`
- Sort order: `provider`, `contract_id`
- Invariant checks: `nonnegative-market-fields`, `finite-greeks`, `size-requires-price`,
  `chain-date-scope`, `contract-membership`, `metadata-scope`, `quote-state-diagnostics`

| Column | pandas dtype |
|---|---|
| `contract_id` | `string` |
| `provider` | `string` |
| `chain_date` | `datetime64[ns]` |
| `last` | `Float64` |
| `mark` | `Float64` |
| `bid` | `Float64` |
| `bid_size` | `Int64` |
| `ask` | `Float64` |
| `ask_size` | `Int64` |
| `volume` | `Int64` |
| `open_interest` | `Int64` |
| `implied_volatility` | `Float64` |
| `delta` | `Float64` |
| `gamma` | `Float64` |
| `theta` | `Float64` |
| `vega` | `Float64` |
| `rho` | `Float64` |
| `provider_as_of` | `datetime64[ns, UTC]` |
| `retrieved_at` | `datetime64[ns, UTC]` |

Observed price, size, activity, and implied-volatility values are nonnegative. Greeks must be
finite when present. Every observation matches contract terms by provider and contract ID.
Observation provider and retrieval time match the result metadata.

## Scalar series

`SeriesSet.frame` uses this schema:

<!-- frame-contract: scalar-series -->

- Required values: `series_id`, `provider`, `provider_series`, `series_kind`, `frequency`,
  `period_label`, `retrieved_at`
- Identity key: `series_id`, `frequency`, `maturity`, `period_label`
- Sort order: `series_id`, `frequency`, `maturity`, `period_label`
- Invariant checks: `finite-values-when-observed`, `definition-scope`, `metadata-scope`

| Column | pandas dtype |
|---|---|
| `series_id` | `string` |
| `provider` | `string` |
| `provider_series` | `string` |
| `series_kind` | `string` |
| `frequency` | `string` |
| `period_label` | `string` |
| `period_start` | `datetime64[ns]` |
| `period_end` | `datetime64[ns]` |
| `value` | `float64` |
| `unit` | `string` |
| `geography` | `string` |
| `seasonal_adjustment` | `string` |
| `maturity` | `string` |
| `provider_as_of` | `datetime64[ns, UTC]` |
| `retrieved_at` | `datetime64[ns, UTC]` |

Observed values must be finite. Every identity and descriptive field matches the enclosing
`SeriesDefinition`, and provider and retrieval time match the result metadata. Period labels
remain source-native.

## Vintage scalar series

`VintageSeriesSet.frame` uses this schema:

<!-- frame-contract: vintage-scalar-series -->

- Required values: `series_id`, `provider`, `provider_series`, `series_kind`, `frequency`,
  `period_label`, `available_from`, `is_deleted`, `retrieved_at`
- Identity key: `series_id`, `frequency`, `maturity`, `period_label`, `available_from`
- Sort order: `series_id`, `frequency`, `maturity`, `period_label`, `available_from`
- Invariant checks: `finite-values-when-observed`, `calendar-date-availability`,
  `nonoverlapping-availability`, `deleted-value-missing`, `definition-scope`, `metadata-scope`

| Column | pandas dtype | Meaning |
|---|---|---|
| `series_id` | `string` | Normalized series identity |
| `provider` | `string` | Source provider |
| `provider_series` | `string` | Source series key |
| `series_kind` | `string` | Commodity or economic family |
| `frequency` | `string` | Provider-native frequency |
| `period_label` | `string` | Source observation label |
| `period_start` | `datetime64[ns]` | Source observation-period start |
| `period_end` | `datetime64[ns]` | Source observation-period end |
| `available_from` | `datetime64[ns]` | First applicable calendar date |
| `available_through` | `datetime64[ns]` | Inclusive last date, or missing when open-ended |
| `value` | `Float64` | Nullable reported value |
| `is_deleted` | `bool` | Whether the source deleted the observation |
| `unit` | `string` | Native unit |
| `geography` | `string` | Optional geographic scope |
| `seasonal_adjustment` | `string` | Optional seasonal adjustment |
| `maturity` | `string` | Optional maturity |
| `retrieved_at` | `datetime64[ns, UTC]` | Retrieval provenance |

Availability fields contain daily calendar labels, not publication timestamps. Intervals
are closed on both ends and cannot overlap for one observation. A missing
`available_through` value marks the final open-ended version. Gaps are allowed. A deleted
version must have a missing value, while a nondeleted missing value preserves explicit source
numeric missingness. Every identity and descriptive field must agree with the enclosing
`SeriesDefinition`, and every retrieval time must agree with the result metadata.

## Symbol search

`InstrumentSearchResult.frame` uses this schema:

<!-- frame-contract: symbol-search -->

- Required values: `provider_symbol`, `name`, `provider_type`, `match_score`
- Identity key: `provider_symbol`, `region`
- Sort order: `match_score`, `provider_symbol`
- Invariant checks: `normalized-finite-match-score`

| Column | pandas dtype |
|---|---|
| `provider_symbol` | `string` |
| `name` | `string` |
| `provider_type` | `string` |
| `region` | `string` |
| `market_open` | `string` |
| `market_close` | `string` |
| `timezone` | `string` |
| `currency` | `string` |
| `match_score` | `float64` |

Match scores must be finite and between zero and one, inclusive. Matches are provider search
output, not canonical identity claims.

## Market status

`MarketStatusResult.frame` uses this schema:

<!-- frame-contract: market-status -->

- Required values: `market_type`, `region`, `current_status`, `retrieved_at`
- Identity key: `market_type`, `region`
- Sort order: `market_type`, `region`
- Invariant checks: `metadata-scope`

| Column | pandas dtype |
|---|---|
| `market_type` | `string` |
| `region` | `string` |
| `primary_exchanges` | `string` |
| `local_open` | `string` |
| `local_close` | `string` |
| `current_status` | `string` |
| `notes` | `string` |
| `retrieved_at` | `datetime64[ns, UTC]` |

Every retrieval time matches the result metadata.

## Index catalog

`IndexCatalogResult.frame` uses this schema:

<!-- frame-contract: index-catalog -->

- Required values: `provider_symbol`, `name`, `provider_type`
- Identity key: `provider_symbol`
- Sort order: `provider_symbol`
- Invariant checks: none

| Column | pandas dtype |
|---|---|
| `provider_symbol` | `string` |
| `name` | `string` |
| `market` | `string` |
| `currency` | `string` |
| `provider_type` | `string` |

The Alpha Vantage catalog leaves market and currency missing when the provider mapping does
not supply them.

## Scalar quote objects

`ExchangeRateQuote` and `CommoditySpotQuote` are dataclasses rather than frame-backed result
families. Their exact fields and types appear in the [model API](model.md). Exchange-rate
values are positive and finite; commodity spot values are finite. Required identity text is
nonblank. Provider and retrieval fields match the result metadata.
