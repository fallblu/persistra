# Data model

Persistra's model separates identity, observations, and provenance. Exact pandas schemas make
missingness, time, units, and applicability part of the public contract rather than informal
column conventions.

## Identity objects

`Instrument` represents an equity, ETF, mutual fund, index, fiat pair, crypto pair, or
commodity. Pair instruments require both base and quote currencies.

```python
from persistra.model import Instrument, InstrumentKind

pair = Instrument(
    instrument_id="eur-usd",
    kind=InstrumentKind.FIAT_PAIR,
    display_name="EUR/USD",
    base_currency="EUR",
    quote_currency="USD",
)
```

`Listing` contains venue-specific identity such as exchange, MIC, currency, and source
timezone. `ProviderSymbol` connects a provider key to one instrument or listing.

`SeriesDefinition` describes a commodity or economic scalar series with its provider key,
native frequency, unit, geography, seasonal adjustment, and maturity.

`OptionContract` represents provider-scoped option terms. Normalized historical chains store
equivalent terms in their contract frame so many contracts can share one result efficiently.

## Stable provider-scoped IDs

Use the helper functions when a source has no cross-provider canonical mapping:

```python
from persistra.model import (
    InstrumentKind,
    provider_instrument_id,
    provider_series_id,
)

instrument_id = provider_instrument_id(
    "example_provider",
    InstrumentKind.EQUITY,
    "DEMO",
)
series_id = provider_series_id(
    "example_provider",
    "CPI",
    "monthly",
)
```

The functions produce stable opaque IDs from normalized provider scope. They do not establish
equivalence with another source.

## Explicit catalogs

`Catalog` stores application-approved instrument and provider-symbol mappings in memory:

```python
from persistra.model import Catalog, Instrument, InstrumentKind, ProviderSymbol

instrument = Instrument("company-a", InstrumentKind.EQUITY, "Company A")
mapping = ProviderSymbol(
    provider="example_provider",
    kind=InstrumentKind.EQUITY,
    symbol="CMPA",
    instrument_id=instrument.instrument_id,
)

catalog = Catalog()
catalog.add_instrument(instrument)
catalog.map_provider_symbol(mapping)

resolved = catalog.resolve("example_provider", "equity", "CMPA")
assert resolved == instrument
```

Mappings cannot refer to an unknown instrument or replace an existing provider key with a
different identity.

## Result objects

Normalized results carry the pieces a research workflow needs:

| Result | Identity | Observations | Provenance |
|---|---|---|---|
| `BarSet` | `instrument` | `frame` | `metadata` |
| `QuoteSet` | Per-row instrument IDs | `frame` | `metadata` |
| `TopOfBookSet` | Per-row instrument IDs | `frame` | `metadata` |
| `OptionChain` | Underlying scope and contract frame | `observations` | `metadata` |
| `SeriesSet` | `definition` | `frame` | `metadata` |
| `VintageSeriesSet` | `definition` | Versioned `frame` | `metadata` |
| `VintageDatesResult` | Provider series key | Sorted change dates | `metadata` |
| Reference results | Query or provider scope | `frame` | `metadata` |
| Scalar quote results | Scalar identity fields | Dataclass fields | `metadata` |

Every frame validates exact column order, pandas dtypes, sort order, unique keys, and
family-specific numeric constraints. See [Normalized schemas](../reference/schemas.md) for
the complete tables.

## Missing values are meaningful

Nullable pandas dtypes distinguish missing applicability from zero. For example:

- A daily bar's `timestamp` is missing because `date` applies.
- An intraday bar's `date` is missing because `timestamp` applies.
- Volume can be missing for a source that does not report it.
- A missing bid or ask does not mean a price of zero.
- A scalar series can retain a dated missing source observation without interpolation.
- A vintage series distinguishes a source deletion from a reported missing numeric value.

Persistra validates finite observed numeric values. It preserves allowed missing values and
rejects infinities or impossible sign constraints.

## Frame ownership

Result constructors validate a deep copy, but pandas frames remain mutable objects. Do not
add research columns to the frame inside a normalized result. Copy it first:

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO")
derived = bars.frame.copy(deep=True)
derived["range"] = derived["high"] - derived["low"]
```

Use Persistra transforms to produce research frames when one exists for the task.

## Provenance objects

Every acquisition result contains `ResultMetadata`, including:

- provider and operation
- copied, redacted request parameters
- timezone-aware retrieval time
- optional provider as-of time
- entitlement mode
- raw-cache status
- normalized schema version
- nonfatal schema diagnostics

Required provenance never depends on `DataFrame.attrs`, which pandas operations can drop.

Read [Time and provenance](time-provenance.md) for the distinction among calendar labels,
event instants, provider as-of times, and retrieval times.
