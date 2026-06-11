import pandas as pd
import pyarrow as pa

from persistra.data.schema import BAR_SCHEMA
from persistra.providers.massive.session_filter import filter_regular_hours


def _intraday_table(symbol: str, day: str, hours: range) -> pa.Table:
    times = [pd.Timestamp(f"{day} {h:02d}:00:00") for h in hours]
    df = pd.DataFrame(
        {
            "bar_time": times,
            "symbol": symbol,
            "open": [1.0] * len(times),
            "high": [1.0] * len(times),
            "low": [1.0] * len(times),
            "close": [1.0] * len(times),
            "volume": [1.0] * len(times),
            "vwap": [1.0] * len(times),
            "transactions": pd.array([1] * len(times), dtype="Int64"),
        }
    )
    return pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False)


def _hours(table: pa.Table) -> list[int]:
    bt = pd.to_datetime(table.to_pandas()["bar_time"])
    return sorted(bt.dt.hour.tolist())


def test_keeps_regular_session_hours_xnys():
    # 2024-03-01 is a normal full session (09:30-16:00 ET).
    table = _intraday_table("AAA", "2024-03-01", range(4, 20))  # 04:00..19:00
    out = filter_regular_hours(table, "1h", "XNYS")
    assert _hours(out) == [9, 10, 11, 12, 13, 14, 15, 16]


def test_truncates_early_close_session():
    # 2023-11-24 (day after Thanksgiving) closes early at 13:00 ET.
    table = _intraday_table("AAA", "2023-11-24", range(4, 20))
    out = filter_regular_hours(table, "1h", "XNYS")
    assert _hours(out) == [9, 10, 11, 12, 13]


def test_daily_bars_pass_through_unchanged():
    df = pd.DataFrame(
        {
            "bar_time": [pd.Timestamp("2024-03-01")],
            "symbol": "AAA",
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
            "volume": [1.0],
            "vwap": [1.0],
            "transactions": pd.array([1], dtype="Int64"),
        }
    )
    table = pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False)
    out = filter_regular_hours(table, "1d", "XNYS")
    assert out.num_rows == 1


def test_empty_table_passes_through():
    out = filter_regular_hours(BAR_SCHEMA.empty_table(), "1h", "XNYS")
    assert out.num_rows == 0


def test_keeps_regular_session_minutes_xnys():
    # 30-minute-spaced bars across 04:00..19:30 on a normal XNYS session.
    times = [pd.Timestamp(f"2024-03-01 {h:02d}:{m:02d}:00") for h in range(4, 20) for m in (0, 30)]
    df = pd.DataFrame(
        {
            "bar_time": times,
            "symbol": "AAA",
            "open": [1.0] * len(times),
            "high": [1.0] * len(times),
            "low": [1.0] * len(times),
            "close": [1.0] * len(times),
            "volume": [1.0] * len(times),
            "vwap": [1.0] * len(times),
            "transactions": pd.array([1] * len(times), dtype="Int64"),
        }
    )
    table = pa.Table.from_pandas(df, schema=BAR_SCHEMA, preserve_index=False)
    out = filter_regular_hours(table, "1m", "XNYS")
    kept = pd.to_datetime(out.to_pandas()["bar_time"])
    # Open floored to the hour (09:00) through the 16:00 close are kept.
    assert kept.min() == pd.Timestamp("2024-03-01 09:00:00")
    assert kept.max() == pd.Timestamp("2024-03-01 16:00:00")
    # Pre-market (08:30) and after-hours (16:30) are dropped.
    assert pd.Timestamp("2024-03-01 08:30:00") not in set(kept)
    assert pd.Timestamp("2024-03-01 16:30:00") not in set(kept)
