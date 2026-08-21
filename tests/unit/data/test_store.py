"""Tests for explicit DuckDB storage."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd
import pytest

from persistra.data import DuckDBStore, StoredDataset, StoredSnapshot, synthetic
from persistra.errors import DataValidationError, StoreError
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    IndexCatalogResult,
    InstrumentSearchResult,
    MarketStatusResult,
    SeriesSet,
    VintageSeriesSet,
)
from persistra.model._frames import typed_frame
from persistra.model.reference import INDEX_CATALOG_DTYPES, MARKET_STATUS_DTYPES, SEARCH_DTYPES


def test_store_requires_explicit_create_and_open(tmp_path: Path) -> None:
    path = tmp_path / "data.duckdb"
    with pytest.raises(StoreError, match="does not exist"):
        DuckDBStore.open(path)
    store = DuckDBStore.create(path)
    store.close()
    with pytest.raises(StoreError, match="already exists"):
        DuckDBStore.create(path)
    with DuckDBStore.open(path, read_only=True) as opened:
        assert opened.path == path
        assert opened.schema_version == 2


def test_inspection_lists_datasets_and_snapshots_and_loads_exact_results(
    tmp_path: Path,
) -> None:
    path = tmp_path / "inspection.duckdb"
    bars = synthetic.bars(periods=2)
    changed_frame = bars.frame.copy()
    changed_frame.loc[1, "close"] = cast("float", changed_frame.loc[1, "close"]) + 1
    changed_frame.loc[1, "high"] = max(
        cast("float", changed_frame.loc[1, "high"]),
        cast("float", changed_frame.loc[1, "close"]),
    )
    changed = BarSet(bars.instrument, changed_frame, bars.metadata)

    with DuckDBStore.create(path) as store:
        first_id = store.save(bars)
        second_id = store.save(changed)
        series_id = store.save(synthetic.series(periods=2))

        datasets = store.list_datasets()
        assert [(item.family, item.scope_key) for item in datasets] == [
            ("bars", bars.instrument.instrument_id),
            ("series", synthetic.series(periods=2).definition.series_id),
        ]
        assert datasets[0] == StoredDataset(
            family="bars",
            scope_key=bars.instrument.instrument_id,
            snapshot_count=2,
            first_seen=bars.metadata.retrieved_at,
            last_seen=bars.metadata.retrieved_at,
            latest_snapshot_id=second_id,
        )
        snapshots = store.list_snapshots("bars", bars.instrument.instrument_id)
        assert [item.snapshot_id for item in snapshots] == [second_id, first_id]
        assert isinstance(snapshots[0], StoredSnapshot)
        assert snapshots[0].saved_order > snapshots[1].saved_order
        assert store.list_snapshots("bars", "missing") == ()
        loaded_first = store.load_snapshot(first_id)
        assert isinstance(loaded_first, BarSet)
        pd.testing.assert_frame_equal(loaded_first.frame, bars.frame)
        assert isinstance(store.load_snapshot(series_id), SeriesSet)
        assert store.load_snapshot("missing") is None

    with DuckDBStore.open(path, read_only=True) as store:
        assert len(store.list_datasets()) == 2
        assert isinstance(store.load_snapshot(first_id), BarSet)


def test_inspection_loads_every_supported_family(tmp_path: Path) -> None:
    results = (
        synthetic.bars(periods=1),
        synthetic.quotes(),
        synthetic.top_of_book(),
        synthetic.option_chain(),
        synthetic.series(periods=1),
        synthetic.vintage_series(periods=1),
        synthetic.exchange_rate(),
        synthetic.commodity_spot(),
        synthetic.search(),
        synthetic.market_status(),
        synthetic.index_catalog(),
    )
    with DuckDBStore.create(tmp_path / "families-inspection.duckdb") as store:
        snapshot_ids = [store.save(result) for result in results]
        loaded = tuple(store.load_snapshot(snapshot_id) for snapshot_id in snapshot_ids)
    assert tuple(type(result) for result in loaded) == tuple(type(result) for result in results)


def test_bar_round_trip_deduplication_and_revision_query(tmp_path: Path) -> None:
    path = tmp_path / "data.duckdb"
    original = synthetic.bars(periods=3)
    with DuckDBStore.create(path) as store:
        first_id = store.save(original)
        loaded = store.load_bars(original.instrument.instrument_id)
        assert loaded is not None
        pd.testing.assert_frame_equal(loaded.frame, original.frame)

        later_time = original.metadata.retrieved_at + timedelta(hours=1)
        later_frame = original.frame.copy()
        later_frame["retrieved_at"] = pd.Series(
            [later_time] * len(later_frame), dtype="datetime64[ns, UTC]"
        )
        later = BarSet(
            original.instrument,
            later_frame,
            replace(original.metadata, retrieved_at=later_time),
        )
        assert store.save(later) == first_id

        changed_frame = later.frame.copy()
        close = cast("float", changed_frame.loc[2, "close"]) + 1
        changed_frame.loc[2, "close"] = close
        changed_frame.loc[2, "high"] = max(cast("float", changed_frame.loc[2, "high"]), close)
        changed = BarSet(later.instrument, changed_frame, later.metadata)
        second_id = store.save(changed)
        assert second_id != first_id
        latest = store.load_bars(original.instrument.instrument_id)
        assert latest is not None
        assert latest.frame.loc[2, "close"] == changed.frame.loc[2, "close"]
        before = store.load_bars(
            original.instrument.instrument_id,
            retrieved_before=original.metadata.retrieved_at + timedelta(minutes=30),
        )
        assert before is not None
        pd.testing.assert_frame_equal(before.frame, original.frame)
        exact = store.load_bars(
            original.instrument.instrument_id,
            retrieved_before=original.metadata.retrieved_at,
        )
        assert exact is not None
        pd.testing.assert_frame_equal(exact.frame, original.frame)
        assert (
            store.load_bars(
                original.instrument.instrument_id,
                retrieved_before=original.metadata.retrieved_at - timedelta(microseconds=1),
            )
            is None
        )
        assert store.load_bars("missing") is None
        with pytest.raises(ValueError, match="timezone-aware"):
            store.load_bars(
                original.instrument.instrument_id,
                retrieved_before=datetime(2025, 1, 1),
            )

        queried = store.query_bars(
            original.instrument.instrument_id,
            interval="daily",
            start=date(2025, 1, 2),
            end=date(2025, 1, 3),
            retrieved_before=original.metadata.retrieved_at + timedelta(minutes=30),
        )
        assert queried["date"].dt.date.tolist() == [date(2025, 1, 2), date(2025, 1, 3)]
        assert store.query_bars("missing").empty
        with pytest.raises(ValueError, match="must not follow"):
            store.query_bars(
                original.instrument.instrument_id,
                start=date(2025, 1, 3),
                end=date(2025, 1, 2),
            )


def test_store_round_trip_preserves_nested_metadata_parameters(tmp_path: Path) -> None:
    source = synthetic.bars(periods=1)
    metadata = replace(
        source.metadata,
        request_parameters={
            "symbols": ["AAA"],
            "options": {"region": "US", "api_key": "secret"},
        },
    )
    result = BarSet(source.instrument, source.frame, metadata)

    with DuckDBStore.create(tmp_path / "nested-metadata.duckdb") as store:
        snapshot_id = store.save(result)
        loaded = store.load_snapshot(snapshot_id)

    assert isinstance(loaded, BarSet)
    assert loaded.metadata.request_parameters == {
        "symbols": ("AAA",),
        "options": {"region": "US"},
    }
    with pytest.raises(TypeError):
        loaded.metadata.request_parameters["options"]["region"] = "EU"


def test_bar_queries_accumulate_partial_intervals_and_row_revisions(tmp_path: Path) -> None:
    source = synthetic.bars(periods=4)
    first_seen = source.metadata.retrieved_at

    def partial(rows: slice, retrieved_at: datetime) -> BarSet:
        frame = source.frame.iloc[rows].copy().reset_index(drop=True)
        frame["retrieved_at"] = pd.Series(
            [retrieved_at] * len(frame), dtype="datetime64[ns, UTC]"
        )
        return BarSet(
            source.instrument,
            frame,
            replace(source.metadata, retrieved_at=retrieved_at),
        )

    with DuckDBStore.create(tmp_path / "cumulative-bars.duckdb") as store:
        first = partial(slice(0, 2), first_seen)
        second = partial(slice(2, 4), first_seen + timedelta(hours=1))
        store.save(first)
        store.save(second)
        accumulated = store.query_bars(source.instrument.instrument_id)
        assert accumulated["date"].dt.date.tolist() == [
            date(2025, 1, 1),
            date(2025, 1, 2),
            date(2025, 1, 3),
            date(2025, 1, 4),
        ]

        revision_time = first_seen + timedelta(hours=2)
        revised_frame = first.frame.iloc[[1]].copy().reset_index(drop=True)
        revised_frame["retrieved_at"] = pd.Series(
            [revision_time], dtype="datetime64[ns, UTC]"
        )
        revised_close = cast("float", revised_frame.loc[0, "close"]) + 2
        revised_frame.loc[0, "close"] = revised_close
        revised_frame.loc[0, "high"] = max(
            cast("float", revised_frame.loc[0, "high"]), revised_close
        )
        revision = BarSet(
            source.instrument,
            revised_frame,
            replace(source.metadata, retrieved_at=revision_time),
        )
        store.save(revision)

        latest = store.query_bars(source.instrument.instrument_id)
        assert latest.loc[1, "close"] == revised_close
        before_revision = store.query_bars(
            source.instrument.instrument_id,
            retrieved_before=revision_time - timedelta(microseconds=1),
        )
        assert before_revision.loc[1, "close"] == first.frame.loc[1, "close"]
        exact_snapshot = store.load_bars(source.instrument.instrument_id)
        assert exact_snapshot is not None
        pd.testing.assert_frame_equal(exact_snapshot.frame, revision.frame)

        intraday = synthetic.bars(periods=2, interval="5min")
        intraday_time = first_seen + timedelta(hours=3)
        intraday_frame = intraday.frame.copy()
        intraday_frame["retrieved_at"] = pd.Series(
            [intraday_time] * len(intraday_frame), dtype="datetime64[ns, UTC]"
        )
        store.save(
            BarSet(
                intraday.instrument,
                intraday_frame,
                replace(intraday.metadata, retrieved_at=intraday_time),
            )
        )
        assert len(store.query_bars(source.instrument.instrument_id)) == 6
        assert len(store.query_bars(source.instrument.instrument_id, interval="5min")) == 2
        intraday_start = cast("pd.Timestamp", intraday_frame.loc[0, "timestamp"]).to_pydatetime()
        intraday_end = cast("pd.Timestamp", intraday_frame.loc[1, "timestamp"]).to_pydatetime()
        assert len(
            store.query_bars(
                source.instrument.instrument_id,
                interval="5min",
                start=intraday_start,
                end=intraday_end,
            )
        ) == 2
        with pytest.raises(TypeError, match="same temporal type"):
            store.query_bars(
                source.instrument.instrument_id,
                start=date(2025, 1, 1),
                end=intraday_end,
            )
        with pytest.raises(ValueError, match="timezone-aware"):
            store.query_bars(
                source.instrument.instrument_id,
                start=datetime(2025, 1, 1),
            )


def test_options_and_series_round_trip(tmp_path: Path) -> None:
    with DuckDBStore.create(tmp_path / "families.duckdb") as store:
        chain = synthetic.option_chain(chain_date=date(2025, 1, 17))
        store.save(chain)
        loaded_chain = store.load_options(chain.underlying_instrument_id, chain.chain_date)
        assert loaded_chain is not None
        pd.testing.assert_frame_equal(loaded_chain.contracts, chain.contracts)
        pd.testing.assert_frame_equal(loaded_chain.observations, chain.observations)
        scalar = synthetic.series(periods=4)
        store.save(scalar)
        loaded_series = store.load_series(scalar.definition.series_id)
        assert loaded_series is not None
        pd.testing.assert_frame_equal(loaded_series.frame, scalar.frame)
        assert store.latest_payload("series", scalar.definition.series_id) is not None
        queried = store.query_series(
            scalar.definition.series_id,
            start_label="2023-02-01",
            end_label="2023-03-01",
        )
        assert queried["period_label"].tolist() == ["2023-02-01", "2023-03-01"]
        with pytest.raises(ValueError, match="must not follow"):
            store.query_series(scalar.definition.series_id, start_label="z", end_label="a")


def test_series_queries_accumulate_partial_acquisitions(tmp_path: Path) -> None:
    source = synthetic.series(periods=4)
    first_seen = source.metadata.retrieved_at

    def partial(rows: slice, retrieved_at: datetime) -> SeriesSet:
        frame = source.frame.iloc[rows].copy().reset_index(drop=True)
        frame["retrieved_at"] = pd.Series(
            [retrieved_at] * len(frame), dtype="datetime64[ns, UTC]"
        )
        return SeriesSet(
            source.definition,
            frame,
            replace(source.metadata, retrieved_at=retrieved_at),
        )

    with DuckDBStore.create(tmp_path / "cumulative-series.duckdb") as store:
        store.save(partial(slice(0, 2), first_seen))
        second_seen = first_seen + timedelta(hours=1)
        store.save(partial(slice(2, 4), second_seen))
        assert store.query_series(source.definition.series_id)["period_label"].tolist() == [
            "2023-01-01",
            "2023-02-01",
            "2023-03-01",
            "2023-04-01",
        ]
        before_second = store.query_series(
            source.definition.series_id,
            retrieved_before=second_seen - timedelta(microseconds=1),
        )
        assert before_second["period_label"].tolist() == ["2023-01-01", "2023-02-01"]

        revision_seen = first_seen + timedelta(hours=2)
        revision_frame = source.frame.iloc[[1]].copy().reset_index(drop=True)
        revision_frame.loc[0, "value"] = cast("float", revision_frame.loc[0, "value"]) + 5
        revision_frame["retrieved_at"] = pd.Series(
            [revision_seen], dtype="datetime64[ns, UTC]"
        )
        store.save(
            SeriesSet(
                source.definition,
                revision_frame,
                replace(source.metadata, retrieved_at=revision_seen),
            )
        )
        revised = store.query_series(source.definition.series_id)
        assert revised.loc[1, "value"] == revision_frame.loc[0, "value"]

        same_time_frame = revision_frame.copy()
        same_time_frame.loc[0, "value"] = cast("float", same_time_frame.loc[0, "value"]) + 1
        store.save(
            SeriesSet(
                source.definition,
                same_time_frame,
                replace(source.metadata, retrieved_at=revision_seen),
            )
        )
        latest_same_time = store.query_series(source.definition.series_id)
        assert latest_same_time.loc[1, "value"] == same_time_frame.loc[0, "value"]


def test_vintage_series_round_trip_and_availability_query(tmp_path: Path) -> None:
    source = synthetic.vintage_series(periods=3)
    with DuckDBStore.create(tmp_path / "vintages.duckdb") as store:
        store.save(source)
        loaded = store.load_vintage_series(source.definition.series_id)
        assert loaded is not None
        pd.testing.assert_frame_equal(loaded.frame, source.frame)
        assert store.latest_payload("vintage_series", source.definition.series_id) is not None

        available = store.query_vintage_series(
            source.definition.series_id,
            start_label="2023-01-01",
            end_label="2023-02-01",
            available_on=date(2023, 6, 1),
        )
        assert available["period_label"].tolist() == ["2023-01-01", "2023-02-01"]
        assert available.groupby("period_label").size().eq(1).all()
        assert store.query_vintage_series("missing").empty
        with pytest.raises(ValueError, match="must not follow"):
            store.query_vintage_series(
                source.definition.series_id,
                start_label="z",
                end_label="a",
            )


def test_vintage_queries_accumulate_separate_observation_ranges(tmp_path: Path) -> None:
    source = synthetic.vintage_series(periods=3)
    first_seen = source.metadata.retrieved_at

    def partial(periods: list[str], retrieved_at: datetime) -> VintageSeriesSet:
        frame = source.frame[source.frame["period_label"].isin(periods)].copy().reset_index(
            drop=True
        )
        frame["retrieved_at"] = pd.Series(
            [retrieved_at] * len(frame), dtype="datetime64[ns, UTC]"
        )
        return VintageSeriesSet(
            source.definition,
            frame,
            replace(source.metadata, retrieved_at=retrieved_at),
        )

    with DuckDBStore.create(tmp_path / "cumulative-vintages.duckdb") as store:
        store.save(partial(["2023-01-01"], first_seen))
        second_seen = first_seen + timedelta(hours=1)
        store.save(partial(["2023-02-01", "2023-03-01"], second_seen))
        accumulated = store.query_vintage_series(source.definition.series_id)
        assert accumulated.groupby("period_label").size().to_dict() == {
            "2023-01-01": 2,
            "2023-02-01": 2,
            "2023-03-01": 2,
        }
        before_second = store.query_vintage_series(
            source.definition.series_id,
            retrieved_before=second_seen - timedelta(microseconds=1),
        )
        assert before_second["period_label"].unique().tolist() == ["2023-01-01"]


def test_vintage_availability_filters_apply_after_row_revision_selection(tmp_path: Path) -> None:
    source = synthetic.vintage_series(periods=1)
    first_seen = source.metadata.retrieved_at
    early_frame = source.frame.iloc[[0]].copy().reset_index(drop=True)
    early_frame["available_through"] = pd.NaT
    early = VintageSeriesSet(source.definition, early_frame, source.metadata)

    later_seen = first_seen + timedelta(hours=1)
    later_frame = source.frame.copy()
    later_frame["retrieved_at"] = pd.Series(
        [later_seen] * len(later_frame), dtype="datetime64[ns, UTC]"
    )
    later = VintageSeriesSet(
        source.definition,
        later_frame,
        replace(source.metadata, retrieved_at=later_seen),
    )

    with DuckDBStore.create(tmp_path / "revised-availability.duckdb") as store:
        store.save(early)
        store.save(later)
        before_revision = store.query_vintage_series(
            source.definition.series_id,
            available_on=date(2023, 6, 1),
            retrieved_before=later_seen - timedelta(microseconds=1),
        )
        assert before_revision["value"].tolist() == [100.0]
        current = store.query_vintage_series(
            source.definition.series_id,
            available_on=date(2023, 6, 1),
        )
        assert current["value"].tolist() == [100.25]


def test_snapshot_and_reference_families_round_trip(tmp_path: Path) -> None:
    with DuckDBStore.create(tmp_path / "snapshots.duckdb") as store:
        quotes = synthetic.quotes(("AAA", "BBB"))
        book = synthetic.top_of_book(("AAA", "BBB"))
        store.save(quotes)
        store.save(book)
        loaded_quotes = store.load_quotes(("AAA", "BBB"))
        loaded_book = store.load_top_of_book(("AAA", "BBB"))
        assert loaded_quotes is not None and loaded_book is not None
        pd.testing.assert_frame_equal(loaded_quotes.frame, quotes.frame)
        pd.testing.assert_frame_equal(loaded_book.frame, book.frame)

        metadata = synthetic.metadata("reference")
        search = InstrumentSearchResult(
            "IBM",
            typed_frame(
                {
                    "provider_symbol": ["IBM"],
                    "name": ["International Business Machines"],
                    "provider_type": ["Equity"],
                    "region": ["United States"],
                    "market_open": ["09:30"],
                    "market_close": ["16:00"],
                    "timezone": ["UTC-04"],
                    "currency": ["USD"],
                    "match_score": [1.0],
                },
                SEARCH_DTYPES,
            ),
            metadata,
        )
        status = MarketStatusResult(
            typed_frame(
                {
                    "market_type": ["Equity"],
                    "region": ["United States"],
                    "primary_exchanges": ["NASDAQ, NYSE"],
                    "local_open": ["09:30"],
                    "local_close": ["16:00"],
                    "current_status": ["open"],
                    "notes": [pd.NA],
                    "retrieved_at": [metadata.retrieved_at],
                },
                MARKET_STATUS_DTYPES,
            ),
            metadata,
        )
        catalog = IndexCatalogResult(
            typed_frame(
                {
                    "provider_symbol": ["SPX"],
                    "name": ["S&P 500"],
                    "market": ["United States"],
                    "currency": ["USD"],
                    "provider_type": ["index"],
                },
                INDEX_CATALOG_DTYPES,
            ),
            metadata,
        )
        for result in (search, status, catalog):
            store.save(result)
        assert store.load_search("IBM") is not None
        assert store.load_market_status() is not None
        assert store.load_index_catalog() is not None


def test_scalar_quotes_round_trip(tmp_path: Path) -> None:
    metadata = synthetic.metadata("scalar")
    rate = ExchangeRateQuote(
        "usd-eur",
        "synthetic",
        "USD",
        "EUR",
        0.92,
        0.91,
        0.93,
        metadata.retrieved_at,
        "UTC",
        metadata.retrieved_at,
        metadata,
    )
    spot = CommoditySpotQuote(
        "gold",
        "synthetic",
        "gold",
        2400.0,
        "USD per troy ounce",
        metadata.retrieved_at,
        metadata.retrieved_at,
        metadata,
    )
    with DuckDBStore.create(tmp_path / "scalar.duckdb") as store:
        store.save(rate)
        store.save(spot)
        assert store.load_exchange_rate("usd-eur") == rate
        assert store.load_commodity_spot("gold") == spot


def test_store_revalidates_mutable_results_before_persistence(tmp_path: Path) -> None:
    result = synthetic.quotes(("AAA",))
    result.frame["provider"] = pd.Series(["other"], dtype="string")

    with DuckDBStore.create(tmp_path / "invalid.duckdb") as store:
        with pytest.raises(DataValidationError, match="provider differs from result metadata"):
            store.save(result)
        assert store.list_datasets() == ()


def test_store_rejects_unsupported_results_and_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.duckdb"
    with DuckDBStore.create(path) as store:
        with pytest.raises(TypeError, match="supported"):
            store.save(object())
    connection = duckdb.connect(str(path))
    connection.execute("UPDATE schema_version SET version = 99")
    connection.close()
    with pytest.raises(StoreError, match="not supported"):
        DuckDBStore.open(path)
