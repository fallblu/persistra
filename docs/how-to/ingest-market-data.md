# Ingest market data

Canonical data enters a managed market database through registered sources, staged
batches, per-record dispositions, and immutable snapshots. Ingestion mutates market
storage, so it requires `MARKET_WRITE` mode against a configured market database.

## Register a source and dataset

```python
from persistra import Project, ProjectMode
from persistra.db import DatabaseName

with Project.open(
    "/path/to/project",
    mode=ProjectMode.MARKET_WRITE,
    writable_market=DatabaseName("primary"),
) as project:
    catalog = project.services.catalog
    ingestion = project.services.ingestion
```

Register the source, dataset, and (optionally) source-precedence policy through
`project.services.catalog`, then submit batches of typed observation records through
`project.services.ingestion`. Every record receives an explicit disposition; failed
records land in quarantine with remediation linkage rather than silently disappearing.

## Validate, revise, and quarantine

- `persistra data validate <project> --market <name> --batch-id <id>` re-runs managed
  validation for a staged batch.
- Revisions and retractions are first-class: corrections create new canonical revisions
  with their own availability instants; they never overwrite published facts.
- `persistra data quarantine <project> --market <name>` lists quarantined records.

## Snapshot

Pinned research reads immutable snapshots, never live tables:

```bash
persistra data snapshot create /path/to/project --market primary
persistra data snapshot list /path/to/project --market primary
```

A snapshot records a content-addressed catalog root. Later ingestion cannot affect
queries pinned to an existing snapshot; composite snapshots combine multiple market
databases into one referenced root.

Provider adapters must pass the conformance kit in `persistra.conformance`
(`standard_provider_suite`) before their data is treated as canonical.

## Alpha Vantage

The bundled Alpha Vantage adapter (`persistra.sources.alphavantage`) ingests
typed-direct: endpoint parsers return canonical domain objects (`Bar`,
`CorporateActionObservation`, `MacroRelease`, ...) that flow through the same typed
services as every other family. The generic batch pipeline is not involved.

```python
from persistra import Project, ProjectMode
from persistra.db import DatabaseName
from persistra.sources.alphavantage import AlphaVantageClient, register_alphavantage

client = AlphaVantageClient()

with Project.open(
    "/path/to/project",
    mode=ProjectMode.MARKET_WRITE,
    writable_market=DatabaseName("primary"),
) as project:
    register_alphavantage(project)
```

- The API key is read from the `PERSISTRA_ALPHAVANTAGE_API_KEY` environment variable
  only; it is never accepted through project configuration and never written to logs.
- The client paces requests with a token bucket (default 75 requests/minute, the
  premium budget) and retries transient failures with bounded backoff.
- Alpha Vantage serves latest snapshots without vintages, so every family ingests
  with `ingestion_bounded` availability quality and `redistributable=False`
  licensing recorded on the source definition.

### Asset-class coverage

The adapter spans several asset classes, each mapped onto an existing typed family:

- **Equities** — `TIME_SERIES_DAILY`/`TIME_SERIES_INTRADAY` ingest raw OHLCV;
  `SPLITS`/`DIVIDENDS` become corporate actions so persistra's adjustment engine
  derives adjusted series. Alpha Vantage's pre-adjusted close is never treated as
  canonical.
- **Macro, rates, commodities** — economic indicators and commodity price series map
  to the macro-series family; `TREASURY_YIELD` and `FEDERAL_FUNDS_RATE` feed the
  risk-free curve family.
- **Indices** — mapped to benchmark source-series. Alpha Vantage index coverage is
  thin; scope ingestion to what the API actually serves.
- **Crypto** — `DIGITAL_CURRENCY_DAILY`/`CRYPTO_INTRADAY` parse into bars on
  `crypto_pair` instruments quoted in the pair's market currency (USD, EUR, ...).
- **Spot FX** — `FX_DAILY`/`FX_INTRADAY` parse into volume-less bars
  (`BarState.NO_VOLUME`) on `fx_pair` instruments; `CURRENCY_EXCHANGE_RATE` becomes
  an indicative top-of-book quote.

Pair instruments (crypto and FX) extend the standard reference chain with a synthetic
market-convention issuer, the shared OTC venue, and base/quote currencies. The
synthetic trading calendars pair with them: `CalendarDefinition.always_open()` (24×7,
crypto) and `CalendarDefinition.fx_24x5()` (24×5 weekdays, FX).

```python
from datetime import UTC, date, datetime

from persistra.reference import CalendarDefinition
from persistra.sources.alphavantage import (
    crypto_pair_instrument,
    fx_pair_instrument,
    utc_day_sessions,
)

valid_from = datetime(2025, 12, 1, tzinfo=UTC)
btc_eur = crypto_pair_instrument("BTC", "EUR", valid_from=valid_from)
eur_usd = fx_pair_instrument("EUR", "USD", valid_from=valid_from)
calendar = CalendarDefinition.always_open(
    coverage_start=date(2025, 12, 20),
    coverage_end=date(2026, 2, 1),
    available_at=valid_from,
)
sessions = utc_day_sessions(date(2026, 1, 1), date(2026, 1, 11))
```

Non-USD market data is fully supported for research; the accounting/results layer
remains single-reporting-currency (USD), so pair instruments are not supported inputs
to the simulation/accounting path.
