# Handle errors

Persistra uses a small exception hierarchy so callers can distinguish invalid normalized
data, provider failures, cache problems, storage failures, and invalid analysis inputs.

## Catch the narrowest useful exception

All library-specific exceptions inherit from `PersistraError`:

```python
from persistra.errors import PersistraError

try:
    result = run_research_operation()
except PersistraError as error:
    record_failure(error)
```

For application behavior, catch a narrower class whenever the recovery path differs.

## Understand the hierarchy

| Exception | Meaning | Typical response |
|---|---|---|
| `DataValidationError` | A normalized frame violates its exact contract | Reject the result and inspect construction or provider parsing |
| `AuthenticationError` | Provider credentials are missing or invalid | Correct credential configuration |
| `EntitlementError` | The provider account cannot access the operation | Change the request or account access |
| `RateLimitError` | Throttling exhausted bounded retries | Reduce request pressure or retry later |
| `ResponseError` | A provider payload is malformed or contradictory | Record operation context and inspect schema drift |
| `TransportError` | Network or transport retries were exhausted | Retry at the application boundary if appropriate |
| `NoDataError` | The provider explicitly reported no data | Treat absence according to the workflow |
| `CacheError` | Raw-cache access failed or offline content was absent | Fix cache access or populate the entry online |
| `StoreError` | Store creation, opening, encoding, or persistence failed | Preserve the original exception and inspect the database |
| `AnalysisError` | Inputs violate a calculation's assumptions | Correct the dataset or choose another calculation |

Provider-specific exceptions inherit from `ProviderError`, which itself inherits from
`PersistraError`.

## Separate no data from provider failure

```python
from persistra.errors import NoDataError, ProviderError

try:
    chain = client.options.historical_chain("IBM", date="2025-01-18")
except NoDataError:
    chain = None
except ProviderError as error:
    raise RuntimeError("option provider request failed") from error
```

Only treat `NoDataError` as an empty result when that meaning is valid for the task. Do not
convert authentication, entitlement, rate-limit, transport, or schema failures into empty
data.

The historical-chain range iterator already skips unambiguous no-data days. Direct calls do
not hide the exception.

## Handle offline cache misses

```python
from persistra.errors import CacheError
from persistra.model import InstrumentKind

try:
    bars = client.securities.bars(
        "IBM",
        kind=InstrumentKind.EQUITY,
        interval="daily",
        offline=True,
    )
except CacheError as error:
    raise RuntimeError("populate the daily IBM cache before offline use") from error
```

Do not retry the same offline call repeatedly. Either populate the exact cache key during an
authorized online phase or use synthetic data for a network-independent workflow.

## Report schema diagnostics without treating them as errors

Unknown provider fields can be nonfatal when required values still normalize safely:

```python
for diagnostic in bars.metadata.diagnostics:
    print(f"{diagnostic.field}: {diagnostic.message}")
```

Use `strict_schema=True` on `AlphaVantageClient` or `FredClient` when any unknown field should
fail the request. Missing required fields and malformed values fail regardless of this
setting.

## Add context without losing the original failure

Use exception chaining:

```python
from persistra.errors import StoreError

try:
    with DuckDBStore.open("research.duckdb") as store:
        store.save(bars)
except StoreError as error:
    raise RuntimeError("could not update the daily-bar research store") from error
```

Never include API keys, raw response bodies, or licensed observations in user-facing error
messages. Operation names, symbols, intervals, exception types, and redacted diagnostic
fields are usually enough to locate the failure.

## Distinguish parameter errors

Invalid caller parameters often raise standard `ValueError` or `TypeError` before a provider
or store operation begins. Examples include an unsupported interval, a naive
`retrieved_before` value, an invalid option strike range, or a nonpositive analysis window.

Validate dynamic user input near the interface that accepts it. Programming errors in fixed
configuration should normally propagate during development rather than being grouped with
runtime provider failures.
