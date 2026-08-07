"""Tests for explicit DuckDB storage."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd
import pytest

from persistra.data import DuckDBStore, synthetic
from persistra.errors import StoreError
from persistra.model import (
    BarSet,
    CommoditySpotQuote,
    ExchangeRateQuote,
    IndexCatalogResult,
    InstrumentSearchResult,
    MarketStatusResult,
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
