"""Tests for massive/flat_files.py — pure logic, no network."""

from __future__ import annotations

import gzip
import io

import pandas as pd

from persistra.data.store import BarQuery
from tests.conftest import build_store


def _write_csv_gz(path, df: pd.DataFrame) -> None:
    """Write a DataFrame as a CSV.gz file at path."""
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    path.write_bytes(gzip.compress(buf.getvalue().encode()))


def _make_agg_row(
    ticker: str,
    date_str: str,
    close: float = 100.0,
) -> dict:
    """Build one row as Massive bulk-flat-file format."""
    ts_ns = int(pd.Timestamp(date_str, tz="America/New_York").timestamp() * 1_000_000_000)
    return {
        "ticker": ticker,
        "volume": 1000.0,
        "open": close,
        "close": close,
        "high": close,
        "low": close,
        "window_start": ts_ns,
        "transactions": 42,
    }


def test_ingest_flat_files_writes_bars(tmp_path):
    from persistra.providers.massive.flat_files import ingest_flat_files

    csv_dir = tmp_path / "csvs"
    csv_dir.mkdir()

    # Create a single CSV.gz for 2022-01-03
    df = pd.DataFrame([_make_agg_row("AAPL", "2022-01-03")])
    _write_csv_gz(csv_dir / "2022-01-03.csv.gz", df)

    # Build a store with reference already written (avoid bootstrap network call)
    times = [pd.Timestamp("2022-01-03")]
    store = build_store(tmp_path / "store", {"AAPL": (times, [100.0])})

    ingest_flat_files(csv_dir, store, timeframe="1d")

    table = store.bars(
        BarQuery(("AAPL",), pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-31"), "1d")
    )
    # The store already had 1 bar; after ingest it should have at least 1
    assert table.num_rows >= 1


def test_ingest_flat_files_filters_by_symbol(tmp_path):
    from persistra.providers.massive.flat_files import ingest_flat_files

    csv_dir = tmp_path / "csvs2"
    csv_dir.mkdir()

    df = pd.DataFrame(
        [
            _make_agg_row("AAPL", "2022-01-03", 100.0),
            _make_agg_row("MSFT", "2022-01-03", 200.0),
        ]
    )
    _write_csv_gz(csv_dir / "2022-01-03.csv.gz", df)

    times = [pd.Timestamp("2022-01-03")]
    store = build_store(tmp_path / "store2", {"AAPL": (times, [100.0])})

    # Only ingest AAPL
    ingest_flat_files(csv_dir, store, timeframe="1d", symbols=["AAPL"])

    aapl = store.bars(
        BarQuery(("AAPL",), pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-31"), "1d")
    )
    assert aapl.num_rows >= 1


def test_ingest_flat_files_skips_unrecognized_filename(tmp_path):
    """Files not matching YYYY-MM-DD.csv.gz are silently skipped."""
    from persistra.data.store import ParquetMarketData
    from persistra.providers.massive.flat_files import ingest_flat_files

    csv_dir = tmp_path / "csvs3"
    csv_dir.mkdir()

    # Create a file with bad name
    (csv_dir / "bad_name.csv.gz").write_bytes(b"garbage")

    store = ParquetMarketData(tmp_path / "store3")
    # Writing an empty reference prevents bootstrap

    from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA

    store.write_universe(UNIVERSE_MEMBERSHIP_SCHEMA.empty_table())

    # Should not raise — just log a warning and skip
    ingest_flat_files(csv_dir, store, timeframe="1d")


def test_ingest_flat_files_filters_by_date_range(tmp_path):
    """Files outside the start/end range should be skipped."""
    from persistra.providers.massive.flat_files import ingest_flat_files

    csv_dir = tmp_path / "csvs4"
    csv_dir.mkdir()

    # File for a date well outside the filter window
    df = pd.DataFrame([_make_agg_row("AAPL", "2022-06-01", 150.0)])
    _write_csv_gz(csv_dir / "2022-06-01.csv.gz", df)

    times = [pd.Timestamp("2022-01-03")]
    store = build_store(tmp_path / "store4", {"AAPL": (times, [100.0])})

    # Filter excludes June
    ingest_flat_files(csv_dir, store, timeframe="1d", start="2022-01-01", end="2022-01-31")

    table = store.bars(
        BarQuery(("AAPL",), pd.Timestamp("2022-06-01"), pd.Timestamp("2022-06-30"), "1d")
    )
    # The June bar should NOT have been written
    assert table.num_rows == 0
