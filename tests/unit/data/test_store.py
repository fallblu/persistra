from typing import Any, cast

import pandas as pd
import pyarrow.dataset as ds
import pytest

from persistra.data.schema import BAR_SCHEMA, CORPORATE_ACTION_SCHEMA, UNIVERSE_MEMBERSHIP_SCHEMA
from persistra.data.store import ActionQuery, BarQuery, ParquetMarketData, UniverseQuery
from persistra.data.views import actions_df, bars_df, ohlcv, prices


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


def test_load_bars_projects_requested_fields(tiny_store):
    table = tiny_store.bars(
        BarQuery(
            ("AAA",),
            pd.Timestamp("2022-01-03"),
            pd.Timestamp("2022-01-31"),
            "1d",
            fields=("close",),
        )
    )

    assert table.column_names == ["bar_time", "symbol", "close"]
    assert table.num_rows == 6


def test_bar_chunks_concatenate_to_bars(tiny_store):
    query = BarQuery(
        ("AAA", "BBB"),
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-01-31"),
        "1d",
        fields=("close",),
    )

    chunks = list(tiny_store.bar_chunks(query, chunk_days=2))
    chunked = pd.concat([chunk.to_pandas() for chunk in chunks], ignore_index=True)
    eager = tiny_store.bars(query).to_pandas()

    assert len(chunks) > 1
    pd.testing.assert_frame_equal(
        chunked.sort_values(["bar_time", "symbol"]).reset_index(drop=True),
        eager.sort_values(["bar_time", "symbol"]).reset_index(drop=True),
    )


def test_bar_filter_prunes_irrelevant_fragments(tmp_path):
    from tests.conftest import build_store

    times = list(pd.bdate_range("2021-12-29", periods=6))
    store = build_store(
        tmp_path / "partitioned",
        {
            "AAA": (times, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
            "BBB": (times, [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
        },
    )
    dataset = ds.dataset(store.root / "bars", format="parquet", partitioning="hive")

    all_fragments = list(dataset.get_fragments())
    filtered_fragments = list(
        dataset.get_fragments(
            filter=store._bar_filter(
                "1d",
                frozenset({"AAA"}),
                pd.Timestamp("2022-01-03"),
                pd.Timestamp("2022-01-04"),
            )
        )
    )

    assert len(all_fragments) == 4
    assert len(filtered_fragments) == 1
    assert "symbol=AAA/year=2022" in filtered_fragments[0].path


def test_load_bars_missing_symbol_returns_empty(tiny_store):
    start = pd.Timestamp("2022-01-03")
    end = pd.Timestamp("2022-01-31")
    table = tiny_store.bars(BarQuery(("ZZZ",), start, end, "1d"))
    assert table.num_rows == 0
    assert table.schema.equals(BAR_SCHEMA)


def test_daily_partition_key_is_year(tiny_store):
    shard = tiny_store.root / "bars" / "timeframe=1d" / "symbol=AAA" / "year=2022" / "part.parquet"
    assert shard.exists()


def test_introspection_symbols_and_timeframes_respect_partitions_and_subsets(tiny_store):
    from tests.conftest import bars_table

    hourly_times = list(pd.date_range("2022-01-03 09:30", periods=3, freq="h"))
    tiny_store.write_bars(bars_table("AAA", hourly_times, [100.0, 101.0, 102.0]), "1h")

    assert tiny_store.timeframes() == ["1d", "1h"]
    assert tiny_store.symbols() == ["AAA", "BBB", "CCC"]
    assert tiny_store.symbols(timeframe="1h") == ["AAA"]
    assert tiny_store.symbols(timeframe="5m") == []

    subset = ParquetMarketData(tiny_store.root, symbols=["BBB"], timeframes=["1d", "1h"])
    assert subset.timeframes() == ["1d"]
    assert subset.symbols() == ["BBB"]
    assert subset.symbols(timeframe="1h") == []


def test_date_range_returns_bounds_for_selected_bars(tiny_store):
    assert tiny_store.date_range() == (
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-01-10"),
    )

    subset = ParquetMarketData(tiny_store.root, symbols=["BBB"])
    assert subset.date_range(timeframe="1d", symbols=["AAA"]) == (None, None)
    assert subset.date_range(timeframe="1d", symbols=["AAA", "BBB"]) == (
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-01-10"),
    )
    assert tiny_store.date_range(timeframe="1h") == (None, None)


def test_coverage_returns_per_symbol_timeframe_rows(tiny_store):
    coverage = tiny_store.coverage()

    assert list(coverage.columns) == ["symbol", "timeframe", "first_bar", "last_bar", "rows"]
    assert coverage[["symbol", "timeframe", "rows"]].values.tolist() == [
        ["AAA", "1d", 6],
        ["BBB", "1d", 6],
        ["CCC", "1d", 6],
    ]
    assert coverage["first_bar"].tolist() == [pd.Timestamp("2022-01-03")] * 3
    assert coverage["last_bar"].tolist() == [pd.Timestamp("2022-01-10")] * 3

    subset = ParquetMarketData(tiny_store.root, symbols=["CCC"])
    assert subset.coverage()["symbol"].tolist() == ["CCC"]


def test_empty_store_introspection_is_graceful(tmp_path):
    store = ParquetMarketData(tmp_path / "missing")

    assert store.symbols() == []
    assert store.timeframes() == []
    assert store.date_range() == (None, None)
    assert list(store.coverage().columns) == [
        "symbol",
        "timeframe",
        "first_bar",
        "last_bar",
        "rows",
    ]
    assert store.coverage().empty

    summary = store.describe()
    bars = cast("dict[str, Any]", summary["bars"])
    universe = cast("dict[str, Any]", summary["universe"])
    assert summary["root"] == store.root
    assert bars["rows"] == 0
    assert bars["coverage"].empty
    assert summary["actions"] == {"rows": 0, "action_types": [], "years": []}
    assert universe["rows"] == 0
    assert summary["subsets"] == {"symbols": None, "timeframes": None}


def test_describe_summarizes_bars_actions_universe_and_subsets(tmp_path):
    from tests.conftest import build_store

    times = list(pd.bdate_range("2022-01-03", periods=2))
    store = build_store(
        tmp_path / "describe",
        {
            "AAA": (times, [100.0, 101.0]),
            "BBB": (times, [50.0, 51.0]),
        },
        actions=[
            {
                "date": "2022-01-04",
                "symbol": "AAA",
                "action_type": "split",
                "amount": None,
                "ratio": 2.0,
            },
            {
                "date": "2022-01-05",
                "symbol": "BBB",
                "action_type": "dividend",
                "amount": 0.5,
                "ratio": None,
            },
        ],
    )

    summary = store.describe()
    bars = cast("dict[str, Any]", summary["bars"])
    universe = cast("dict[str, Any]", summary["universe"])
    assert bars["rows"] == 4
    assert bars["symbols"] == ["AAA", "BBB"]
    assert bars["timeframes"] == ["1d"]
    assert bars["first_bar"] == pd.Timestamp("2022-01-03")
    assert bars["last_bar"] == pd.Timestamp("2022-01-04")
    assert summary["actions"] == {
        "rows": 2,
        "action_types": ["dividend", "split"],
        "years": [2022],
    }
    assert universe["rows"] == 2
    assert universe["universe_names"] == ["default"]
    assert summary["subsets"] == {"symbols": None, "timeframes": None}

    subset_summary = ParquetMarketData(store.root, symbols=["BBB"], timeframes=["1d"]).describe()
    subset_bars = cast("dict[str, Any]", subset_summary["bars"])
    subset_actions = cast("dict[str, Any]", subset_summary["actions"])
    subset_universe = cast("dict[str, Any]", subset_summary["universe"])
    assert subset_bars["symbols"] == ["BBB"]
    assert subset_bars["rows"] == 2
    assert subset_actions["rows"] == 1
    assert subset_universe["symbol_count"] == 1
    assert subset_summary["subsets"] == {"symbols": ["BBB"], "timeframes": ["1d"]}


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
            "universe_name": ["default"],
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


def test_named_universe_filters_membership(tmp_path):
    import pyarrow as pa

    from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA
    from persistra.data.store import ParquetMarketData

    store = ParquetMarketData(tmp_path / "named")
    df = pd.DataFrame(
        {
            "universe_name": ["default", "tech", "tech"],
            "symbol": ["AAA", "BBB", "OLD"],
            "start_date": [
                pd.Timestamp("2020-01-01").date(),
                pd.Timestamp("2020-01-01").date(),
                pd.Timestamp("2020-01-01").date(),
            ],
            "end_date": [
                None,
                None,
                pd.Timestamp("2022-01-05").date(),
            ],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    )

    default_query = UniverseQuery(pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-31"))
    assert store.universe(default_query) == ["AAA"]
    assert store.universe(
        UniverseQuery(pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-31"), "tech")
    ) == ["BBB", "OLD"]
    assert store.active_universe(pd.Timestamp("2022-01-05"), "tech") == frozenset({"BBB", "OLD"})
    assert store.active_universe(pd.Timestamp("2022-01-06"), "tech") == frozenset({"BBB"})


def test_old_universe_tables_default_to_default_universe(tmp_path):
    import pyarrow as pa

    from persistra.data.store import ParquetMarketData

    store = ParquetMarketData(tmp_path / "old")
    old_schema = pa.schema(
        [
            pa.field("symbol", pa.utf8(), nullable=False),
            pa.field("start_date", pa.date32(), nullable=False),
            pa.field("end_date", pa.date32(), nullable=True),
        ]
    )
    table = pa.Table.from_pydict(
        {
            "symbol": ["AAA"],
            "start_date": [pd.Timestamp("2020-01-01").date()],
            "end_date": [None],
        },
        schema=old_schema,
    )

    store.write_universe(table)

    reopened = ParquetMarketData(store.root)
    assert reopened.active_universe(pd.Timestamp("2022-01-03")) == frozenset({"AAA"})
    assert reopened.active_universe(pd.Timestamp("2022-01-03"), "custom") == frozenset()


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
            "universe_name": ["default"],
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


def test_corporate_action_chunks_concatenate_to_actions(tmp_path):
    import pyarrow as pa

    store = ParquetMarketData(tmp_path / "ca-chunks")
    df_ca = pd.DataFrame(
        {
            "date": [
                pd.Timestamp("2022-01-04").date(),
                pd.Timestamp("2022-01-07").date(),
            ],
            "symbol": ["AAA", "AAA"],
            "action_type": ["split", "dividend"],
            "amount": [None, 0.5],
            "ratio": [2.0, None],
        }
    )
    store.write_corporate_actions(
        pa.Table.from_pandas(df_ca, schema=CORPORATE_ACTION_SCHEMA, preserve_index=False)
    )
    query = ActionQuery(("AAA",), pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-31"))

    chunks = list(store.corporate_action_chunks(query, chunk_days=3))
    chunked = pd.concat([chunk.to_pandas() for chunk in chunks], ignore_index=True)
    eager = store.corporate_actions(query).to_pandas()

    assert len(chunks) == 2
    pd.testing.assert_frame_equal(
        chunked.sort_values(["date", "symbol", "action_type"]).reset_index(drop=True),
        eager.sort_values(["date", "symbol", "action_type"]).reset_index(drop=True),
    )


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
            "universe_name": ["default", "default"],
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


def test_bars_df_returns_sorted_rows_for_symbols(tiny_store):
    df = tiny_store.bars_df(["BBB", "AAA"], "2022-01-03", "2022-01-04")

    assert list(df.columns) == BAR_SCHEMA.names
    assert df[["bar_time", "symbol"]].values.tolist() == [
        [pd.Timestamp("2022-01-03"), "AAA"],
        [pd.Timestamp("2022-01-03"), "BBB"],
        [pd.Timestamp("2022-01-04"), "AAA"],
        [pd.Timestamp("2022-01-04"), "BBB"],
    ]


def test_bars_df_projects_requested_fields(tiny_store):
    df = bars_df(
        tiny_store,
        ["AAA"],
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-01-31"),
        fields=("close",),
    )

    assert list(df.columns) == ["bar_time", "symbol", "close"]
    assert len(df) == 6


def test_bars_df_empty_preserves_projected_columns(tiny_store):
    df = tiny_store.bars_df(["ZZZ"], "2022-01-03", "2022-01-31", fields=("close",))

    assert df.empty
    assert list(df.columns) == ["bar_time", "symbol", "close"]


def test_bars_df_subset_limits_symbols_and_timeframes(tiny_store):
    symbol_subset = ParquetMarketData(tiny_store.root, symbols=["BBB"])
    symbol_df = symbol_subset.bars_df(["AAA", "BBB"], "2022-01-03", "2022-01-31")

    assert set(symbol_df["symbol"]) == {"BBB"}

    timeframe_subset = ParquetMarketData(tiny_store.root, timeframes=["1h"])
    timeframe_df = timeframe_subset.bars_df(
        ["AAA"],
        "2022-01-03",
        "2022-01-31",
        fields=("close",),
    )

    assert timeframe_df.empty
    assert list(timeframe_df.columns) == ["bar_time", "symbol", "close"]


def test_actions_df_returns_matching_rows(tmp_path):
    import pyarrow as pa

    store = ParquetMarketData(tmp_path / "actions-df")
    store.write_corporate_actions(
        pa.Table.from_pandas(
            pd.DataFrame(
                {
                    "date": [
                        pd.Timestamp("2022-01-04").date(),
                        pd.Timestamp("2022-01-07").date(),
                    ],
                    "symbol": ["AAA", "BBB"],
                    "action_type": ["split", "dividend"],
                    "amount": [None, 0.5],
                    "ratio": [2.0, None],
                }
            ),
            schema=CORPORATE_ACTION_SCHEMA,
            preserve_index=False,
        )
    )

    df = store.actions_df(["AAA", "BBB"], "2022-01-01", "2022-01-31")

    assert list(df.columns) == CORPORATE_ACTION_SCHEMA.names
    assert df["symbol"].tolist() == ["AAA", "BBB"]
    assert df["date"].tolist() == [pd.Timestamp("2022-01-04"), pd.Timestamp("2022-01-07")]


def test_actions_df_empty_preserves_columns(tiny_store):
    df = actions_df(tiny_store, ["AAA"], pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-31"))

    assert df.empty
    assert list(df.columns) == CORPORATE_ACTION_SCHEMA.names


def test_actions_df_subset_limits_symbols(tmp_path):
    import pyarrow as pa

    store = ParquetMarketData(tmp_path / "actions-subset-df")
    store.write_corporate_actions(
        pa.Table.from_pandas(
            pd.DataFrame(
                {
                    "date": [pd.Timestamp("2022-01-04").date()] * 2,
                    "symbol": ["AAA", "BBB"],
                    "action_type": ["split", "split"],
                    "amount": [None, None],
                    "ratio": [2.0, 3.0],
                }
            ),
            schema=CORPORATE_ACTION_SCHEMA,
            preserve_index=False,
        )
    )

    subset = ParquetMarketData(store.root, symbols=["BBB"])
    df = subset.actions_df(["AAA", "BBB"], "2022-01-01", "2022-02-01")

    assert df["symbol"].tolist() == ["BBB"]
    assert df["ratio"].tolist() == [3.0]


def test_universe_df_returns_membership_rows(tiny_store):
    df = tiny_store.universe_df()

    assert list(df.columns) == UNIVERSE_MEMBERSHIP_SCHEMA.names
    assert df["symbol"].tolist() == ["AAA", "BBB", "CCC"]


def test_universe_df_filters_symbols_and_universe_name(tmp_path):
    import pyarrow as pa

    store = ParquetMarketData(tmp_path / "universe-df")
    df = pd.DataFrame(
        {
            "universe_name": ["default", "tech", "tech"],
            "symbol": ["AAA", "BBB", "CCC"],
            "start_date": [pd.Timestamp("2020-01-01").date()] * 3,
            "end_date": [None, None, None],
        }
    )
    store.write_universe(
        pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    )

    subset = ParquetMarketData(store.root, symbols=["BBB", "CCC"])
    result = subset.universe_df(universe_name="tech")

    assert result["symbol"].tolist() == ["BBB", "CCC"]
    assert result["universe_name"].tolist() == ["tech", "tech"]


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


def test_prices_method_matches_free_function(tiny_store):
    expected = prices(
        tiny_store,
        ["AAA", "BBB"],
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-01-11"),
    )
    actual = tiny_store.prices(["AAA", "BBB"], "2022-01-03", "2022-01-11")

    pd.testing.assert_frame_equal(actual, expected)


def test_prices_projects_selected_field(tiny_store):
    px = tiny_store.prices(["AAA"], "2022-01-03", "2022-01-11", field="open")

    assert list(px.columns) == ["AAA"]
    assert px.iloc[0, 0] == 100.0


def test_ohlcv_returns_five_fields_for_one_symbol(tiny_store):
    import pandas as pd

    bars = ohlcv(tiny_store, "AAA", pd.Timestamp("2022-01-03"), pd.Timestamp("2022-01-11"))
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert bars.index.name == "bar_time"
    assert len(bars) == 6


def test_ohlcv_method_matches_free_function(tiny_store):
    expected = ohlcv(
        tiny_store,
        "AAA",
        pd.Timestamp("2022-01-03"),
        pd.Timestamp("2022-01-11"),
    )
    actual = tiny_store.ohlcv("AAA", "2022-01-03", "2022-01-11")

    pd.testing.assert_frame_equal(actual, expected)
