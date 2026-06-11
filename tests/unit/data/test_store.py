import pandas as pd
import pytest

from persistra.data.schema import BAR_SCHEMA, CORPORATE_ACTION_SCHEMA, UNIVERSE_MEMBERSHIP_SCHEMA
from persistra.data.store import ActionQuery, BarQuery, ParquetMarketData, UniverseQuery
from persistra.data.views import ohlcv, prices


def test_load_bars_round_trips_values(tiny_store):
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2022-01-31")
    table = tiny_store.bars(BarQuery(("AAA",), start, end, "1d"))
    assert table.schema.equals(BAR_SCHEMA)
    df = table.to_pandas().sort_values("bar_time")
    assert df["close"].tolist() == [100.0, 101.0, 102.0, 101.0, 103.0, 104.0]


def test_load_bars_filters_by_time_window(tiny_store):
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2022-01-04")
    df = tiny_store.bars(BarQuery(("AAA",), start, end, "1d")).to_pandas()
    assert len(df) == 2  # only the first two sessions


def test_load_bars_missing_symbol_returns_empty(tiny_store):
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2022-01-31")
    table = tiny_store.bars(BarQuery(("ZZZ",), start, end, "1d"))
    assert table.num_rows == 0
    assert table.schema.equals(BAR_SCHEMA)


def test_daily_partition_key_is_year(tiny_store):
    shard = tiny_store.root / "bars" / "timeframe=1d" / "symbol=AAA" / "year=2022" / "part.parquet"
    assert shard.exists()


def test_universe_range_and_active_universe(tiny_store):
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2022-01-31")
    assert tiny_store.universe(UniverseQuery(start, end)) == ["AAA", "BBB", "CCC"]
    assert tiny_store.active_universe(pd.Timestamp("2022-01-05")) == frozenset(
        {"AAA", "BBB", "CCC"}
    )


def test_membership_window_excludes_before_start(tmp_path):
    import pyarrow as pa

    from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA
    from persistra.data.store import ParquetMarketData

    store = ParquetMarketData(tmp_path / "s")
    df = pd.DataFrame(
        {
            "symbol": ["LATE"],
            "start_date": [pd.Timestamp("2023-01-01").date()],
            "end_date": [None],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    )
    assert store.active_universe(pd.Timestamp("2022-06-01")) == frozenset()
    assert store.active_universe(pd.Timestamp("2023-06-01")) == frozenset({"LATE"})


def test_corporate_actions_round_trip(tmp_path):
    import pyarrow as pa

    store = ParquetMarketData(tmp_path / "ca")
    times = list(pd.bdate_range("2022-01-03", periods=3))

    # Write bars
    df_bars = pd.DataFrame(
        {
            "bar_time": [pd.Timestamp(t) for t in times],
            "symbol": "AAA",
            "open": [100.0, 100.0, 100.0],
            "high": [100.0, 100.0, 100.0],
            "low": [100.0, 100.0, 100.0],
            "close": [100.0, 100.0, 100.0],
            "volume": 1000.0,
            "vwap": [100.0, 100.0, 100.0],
            "transactions": pd.array([100, 100, 100], dtype="Int64"),
        }
    )
    store.write_bars(pa.Table.from_pandas(df_bars, schema=BAR_SCHEMA, preserve_index=False), "1d")

    # Write reference
    df_ref = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "start_date": [pd.Timestamp("2000-01-01").date()],
            "end_date": [None],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(df_ref, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    )

    # Write corporate actions
    df_ca = pd.DataFrame(
        {
            "date": [pd.Timestamp("2022-01-04").date()],
            "symbol": ["AAA"],
            "action_type": ["split"],
            "amount": [None],
            "ratio": [2.0],
        }
    )
    store.write_corporate_actions(
        pa.Table.from_pandas(df_ca, schema=CORPORATE_ACTION_SCHEMA, preserve_index=False)
    )

    table = store.corporate_actions(
        ActionQuery(("AAA",), pd.Timestamp("2022-01-01"), pd.Timestamp("2022-02-01"))
    )
    assert table.num_rows == 1
    assert table.to_pandas().iloc[0]["ratio"] == 2.0


def test_subset_limits_universe_and_active_universe(tiny_store):
    subset = ParquetMarketData(tiny_store.root, symbols=["AAA", "CCC"])
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2022-01-31")

    assert subset.universe(UniverseQuery(start, end)) == ["AAA", "CCC"]
    assert subset.active_universe(pd.Timestamp("2022-01-05")) == frozenset({"AAA", "CCC"})


def test_subset_limits_requested_bar_symbols(tiny_store):
    subset = ParquetMarketData(tiny_store.root, symbols=["BBB"])
    table = subset.bars(
        BarQuery(
            ("AAA", "BBB", "CCC"),
            pd.Timestamp("2022-01-03"),
            pd.Timestamp("2022-01-31"),
            "1d",
        )
    )

    df = table.to_pandas()
    assert set(df["symbol"]) == {"BBB"}


def test_subset_timeframe_exclusion_returns_empty_with_requested_fields(tiny_store):
    subset = ParquetMarketData(tiny_store.root, timeframes=["1h"])
    table = subset.bars(
        BarQuery(
            ("AAA",),
            pd.Timestamp("2022-01-03"),
            pd.Timestamp("2022-01-31"),
            "1d",
            fields=("close",),
        )
    )

    assert table.num_rows == 0
    assert table.column_names == ["bar_time", "symbol", "close"]


def test_subset_limits_corporate_actions(tmp_path):
    import pyarrow as pa

    store = ParquetMarketData(tmp_path / "ca-subset")
    df_ref = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "start_date": [pd.Timestamp("2000-01-01").date()] * 2,
            "end_date": [None, None],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(df_ref, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    )
    df_ca = pd.DataFrame(
        {
            "date": [pd.Timestamp("2022-01-04").date(), pd.Timestamp("2022-01-04").date()],
            "symbol": ["AAA", "BBB"],
            "action_type": ["split", "split"],
            "amount": [None, None],
            "ratio": [2.0, 3.0],
        }
    )
    store.write_corporate_actions(
        pa.Table.from_pandas(df_ca, schema=CORPORATE_ACTION_SCHEMA, preserve_index=False)
    )

    subset = ParquetMarketData(store.root, symbols=["BBB"])
    table = subset.corporate_actions(
        ActionQuery(("AAA", "BBB"), pd.Timestamp("2022-01-01"), pd.Timestamp("2022-02-01"))
    )

    df = table.to_pandas()
    assert df["symbol"].tolist() == ["BBB"]
    assert df["ratio"].tolist() == [3.0]


def test_subset_instances_are_read_only(tiny_store):
    subset = ParquetMarketData(tiny_store.root, symbols=["AAA"])

    with pytest.raises(RuntimeError, match="read-only"):
        subset.write_bars(BAR_SCHEMA.empty_table(), "1d")
    with pytest.raises(RuntimeError, match="read-only"):
        subset.write_corporate_actions(CORPORATE_ACTION_SCHEMA.empty_table())
    with pytest.raises(RuntimeError, match="read-only"):
        subset.write_universe(UNIVERSE_MEMBERSHIP_SCHEMA.empty_table())


def test_prices_returns_bar_time_by_symbol_frame(tiny_store):
    import pandas as pd

    px = prices(tiny_store, ["AAA", "BBB"], pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-11"))
    assert list(px.columns) == ["AAA", "BBB"]
    assert px.index.name == "bar_time"
    assert px.loc[px.index[0], "AAA"] == 100.0


def test_prices_empty_when_no_symbols(tiny_store):
    import pandas as pd

    px = prices(tiny_store, [], pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-11"))
    assert px.empty


def test_ohlcv_returns_five_fields_for_one_symbol(tiny_store):
    import pandas as pd

    bars = ohlcv(tiny_store, "AAA", pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-11"))
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert bars.index.name == "bar_time"
    assert len(bars) == 6
