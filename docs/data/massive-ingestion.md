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
- `build_universe`
- `ingest_aggregates`
- `ingest_actions`
- `ingest_flat_files`

Use provider helpers to write into `ParquetMarketData`; use `ParquetMarketData` itself
for engine reads.

## Local Data

Large market-data roots should live under `data/`, which is ignored by git. Keep
`examples/sample_data` small and reproducible so quickstarts remain fast.
