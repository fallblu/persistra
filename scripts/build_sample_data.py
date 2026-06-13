#!/usr/bin/env python3
"""Build the real-data persistra sample dataset from Massive.

Requires ``MASSIVE_API_KEY`` (read from the environment or a local ``.env``).
Ingests unadjusted, regular-trading-hours bars for the sample universe (``1d``
and ``1h``), their corporate actions, and writes a curated reference table
containing only the sample symbols.

Run from the repo root:

    python -m scripts.build_sample_data [--out PATH]

For a clean rebuild, delete the target tree first so stale shards and the ingest
checkpoint do not cause symbols to be skipped::

    rm -rf examples/sample_data && python -m scripts.build_sample_data
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import pandas as pd
import pyarrow as pa

from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA
from persistra.data.store import ParquetMarketData
from persistra.providers.massive.actions import ingest_actions
from persistra.providers.massive.client import make_client
from persistra.providers.massive.ingest_runner import Checkpoint, run_ingest
from scripts.sample_universe import (
    DAILY_END,
    DAILY_START,
    INTRADAY_END,
    INTRADAY_START,
    SAMPLE_SYMBOLS,
)


def _write_curated_reference(store: ParquetMarketData) -> None:
    """Write an open-ended membership row for each sample symbol."""
    # Floor well before DAILY_START so the reference never gates out any bar.
    floor = dt.date(2000, 1, 1)
    df = pd.DataFrame(
        {
            "universe_name": ["default"] * len(SAMPLE_SYMBOLS),
            "symbol": SAMPLE_SYMBOLS,
            "start_date": [floor] * len(SAMPLE_SYMBOLS),
            "end_date": [None] * len(SAMPLE_SYMBOLS),
        }
    )
    store.write_universe(
        pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    )


def build(out: Path) -> ParquetMarketData:
    store = ParquetMarketData(out)
    checkpoint = Checkpoint(store.state_dir / "massive_ingest.json")

    # Bars: unadjusted + regular-hours filtering happen inside fetch_aggregates.
    run_ingest(SAMPLE_SYMBOLS, ["1d"], DAILY_START, DAILY_END, store, checkpoint)
    run_ingest(SAMPLE_SYMBOLS, ["1h"], INTRADAY_START, INTRADAY_END, store, checkpoint)

    # Corporate actions (splits + dividends) for the sample symbols.
    ingest_actions(SAMPLE_SYMBOLS, store, make_client())

    # Curated reference so strategies trade only the sample symbols.
    _write_curated_reference(store)
    return store


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_out = Path(__file__).resolve().parents[1] / "examples" / "sample_data"
    parser.add_argument("--out", type=Path, default=default_out, help="output market-data root")
    args = parser.parse_args()
    build(args.out)
    print(f"sample data written to {args.out}")


if __name__ == "__main__":
    main()
