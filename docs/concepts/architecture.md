# Architecture

Persistra is organized as a pipeline of small layers with explicit handoff types. The
separation prevents provider transport, normalized semantics, persistence, calculations, and
presentation from becoming one implicit workflow.

## Layer responsibilities

| Layer | Responsibility | Does not do |
|---|---|---|
| Provider adapter | Request, classify, parse, and normalize source responses | Store normalized results or run analysis |
| Model | Validate identity, frames, dtypes, ordering, and provenance | Contact a provider or infer research policy |
| Raw cache | Retain provider bytes for reuse and offline parsing | Provide normalized research queries |
| DuckDB store | Persist validated results and retrieval-time revisions | Acquire, fill, or transform data |
| Transforms | Pivot, align, as-of match, and resample explicitly | Choose unstated missing-data policy |
| Analysis | Calculate statistics from supplied inputs | Fetch data or produce hidden side effects |
| Visualization | Render supplied observations and calculations | Own global Matplotlib configuration |

A typical workflow follows this direction:

```text
provider or synthetic helper
        -> normalized result object
        -> optional DuckDB persistence
        -> explicit transform
        -> explicit analysis
        -> Matplotlib visualization
```

The raw cache sits beside provider acquisition. It stores transport responses before
normalization and is independent of DuckDB persistence.

## Provider-neutral results

Provider adapters terminate at model objects such as `BarSet`, `OptionChain`, and `SeriesSet`.
Code downstream of that boundary can operate on normalized fields instead of response
envelopes or provider-specific column names.

Provider neutrality does not mean provider equivalence. A provider-scoped symbol creates a
provider-scoped identity. Persistra does not claim that two provider records describe the
same instrument unless the application records an explicit mapping.

## Capability protocols

The data layer exposes small runtime-checkable protocols:

- `BarSource`
- `QuoteSource`
- `OptionChainSource`
- `ScalarSeriesSource`
- `ReferenceSource`

Application code can depend on the capability it needs instead of the complete Alpha Vantage
client:

```python
from persistra.data import BarSource


def acquire_daily(source: BarSource, symbol: str):
    return source.bars(symbol, interval="daily")
```

Provider namespace methods can have richer signatures than a minimal capability protocol.
Use adapters or small application wrappers when a concrete provider requires extra arguments
such as `InstrumentKind`.

## Immutable normalized boundaries

Most identity, metadata, and result classes are frozen dataclasses. Result construction
deep-copies and validates frames, then stores the validated copy. This prevents a caller's
input frame from changing the result after validation.

Pandas objects themselves remain mutable. Treat the frame held by a normalized result as
source data and make an explicit copy before a caller-owned edit:

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO")
research_frame = bars.frame.copy(deep=True)
research_frame["dollar_volume"] = research_frame["close"] * research_frame["volume"]
```

The derived column does not belong to the exact `BarSet` contract, so it stays in a separate
research frame.

## Explicit persistence

Provider calls return values only. They do not discover a database or open an implicit
connection. `DuckDBStore.save` is a separate operation, which makes data-retention choices
reviewable and testable.

The raw cache and DuckDB store deliberately retain different representations. Raw payloads
help reproduce parsing and work offline; normalized snapshots support typed loads and scoped
queries.

## Explicit calculations

General analysis works on ordinary numeric frames. Result-specific analysis accepts a model
object only when it needs normalized structure, such as bar fields, option contract terms, or
top-of-book sides.

Plotting follows the same rule. A function may perform a simple named presentation transform,
but calculations with meaningful policy stay visible in analysis code. For example, callers
calculate returns and annualized rolling volatility before plotting them.

## Extending the architecture

A new provider adapter should:

1. Isolate transport and response classification.
2. Translate source identities and observations into existing normalized contracts.
3. Preserve provider fields needed for time, entitlement, units, and provenance.
4. Record safe schema drift or fail malformed required values.
5. Implement only the capability protocols it actually supports.
6. Leave storage, analysis, and plotting to their existing layers.

This design keeps downstream code stable around data meaning rather than provider envelopes.
