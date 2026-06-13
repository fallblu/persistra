# Massive Ingestion

persistra includes a Massive market-data adapter under `persistra.providers.massive`.

## Configure Access

Set `MASSIVE_API_KEY` in your environment or in a local `.env` file:

```bash
export MASSIVE_API_KEY=...
```

The `.env` file is loaded when `python-dotenv` is installed.

## Build the Sample Dataset

```bash
uv run python scripts/build_sample_data.py
```

The script ingests unadjusted regular-trading-hours bars, corporate actions, and curated
universe membership for the sample symbols.

## Provider Helpers

The public Massive helpers include:

- `make_client`
- `build_point_in_time_universe`
- `build_active_universe`
- `build_universe`
- `ingest_aggregates`
- `ingest_actions`
- `ingest_flat_files`

Use provider helpers to write into `ParquetMarketData`; use `ParquetMarketData` itself
for engine reads.

Prefer `build_point_in_time_universe` for research datasets. It writes listing intervals
from Massive reference metadata so delisted symbols can remain tradable during their
historical membership windows and disappear after delisting. `build_active_universe`
is explicit active-only construction for current-monitoring workflows. The older
`build_universe` helper is kept as a deprecated compatibility wrapper around the
active-only path and can introduce survivorship bias in backtests.

## Local Data

Large market-data roots should live under `data/`, which is ignored by git. Keep
`examples/sample_data` small and reproducible so quickstarts remain fast.
