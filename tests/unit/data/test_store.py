"""Tests for explicit DuckDB storage."""

from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Self, cast

import duckdb
import pandas as pd
import pytest

import persistra.data.store as store_module
from persistra.data import (
    DuckDBStore,
    SnapshotDiff,
    StoredDataset,
    StoredOptionSnapshot,
    StoredPage,
    StoredSnapshot,
    synthetic,
)
from persistra.data.store import QUOTE_HISTORY_DTYPES, TOP_OF_BOOK_HISTORY_DTYPES
from persistra.errors import DataValidationError, StoreError
from persistra.model import (
    BarSet,
    Catalog,
    CommoditySpotQuote,
    ExchangeRateQuote,
    IndexCatalogResult,
    Instrument,
    InstrumentKind,
    InstrumentSearchResult,
    Listing,
    MarketStatusResult,
    ProviderSymbol,
    QuoteSet,
    SchemaDiagnostic,
    SeriesSet,
    VintageDatesResult,
    VintageSeriesSet,
)
from persistra.model._frames import typed_frame
from persistra.model.reference import INDEX_CATALOG_DTYPES, MARKET_STATUS_DTYPES, SEARCH_DTYPES


class _FaultingConnection:
    def __init__(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        fail_on: str,
        rollback_fails: bool = False,
    ) -> None:
        self.connection = connection
        self.fail_on = fail_on
        self.rollback_fails = rollback_fails
        self.failed = False
        self.closed = False
        self.commands: list[str] = []

    def execute(self, query: str, parameters: object | None = None) -> Any:
        command = query.strip()
        self.commands.append(command)
        if command == "ROLLBACK" and self.rollback_fails:
            raise RuntimeError("injected rollback failure")
        if not self.failed and self.fail_on in command:
            self.failed = True
            raise RuntimeError(f"injected {self.fail_on} failure")
        if parameters is None:
            return self.connection.execute(query)
        return self.connection.execute(query, parameters)

    def executemany(self, query: str, parameters: object) -> Any:
        return self.connection.executemany(query, parameters)

    def close(self) -> None:
        self.closed = True
        self.connection.close()


class _SchemaConnection:
    def __init__(
        self,
        row: tuple[object, ...] | None = None,
        error: duckdb.Error | None = None,
    ) -> None:
        self.row = row
        self.error = error
        self.closed = False

    def execute(self, _query: str) -> Self:
        if self.error is not None:
            raise self.error
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def close(self) -> None:
        self.closed = True


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
        assert opened.schema_version == 1


def test_catalog_persistence_is_referential_idempotent_and_isolated(tmp_path: Path) -> None:
    instrument = Instrument("instrument", InstrumentKind.EQUITY, "Example")
    listing = Listing(
        "listing",
        instrument.instrument_id,
        "EX",
        "New York Stock Exchange",
        "XNYS",
        "USD",
        "America/New_York",
    )
    mapping = ProviderSymbol(
        "provider",
        InstrumentKind.EQUITY,
        "EX",
        instrument.instrument_id,
        listing.listing_id,
    )
    catalog = Catalog()
    catalog.add_instrument(instrument)
    catalog.add_listing(listing)
    catalog.map_provider_symbol(mapping)
    path = tmp_path / "catalog.duckdb"

    with DuckDBStore.create(path) as store:
        assert store.load_catalog().instruments == ()
        store.save_catalog(Catalog())
        store.save_catalog(catalog)
        store.save_catalog(catalog)
        loaded = store.load_catalog()
        assert loaded.instruments == (instrument,)
        assert loaded.listings == (listing,)
        assert loaded.provider_symbols == (mapping,)
        assert loaded.resolve("provider", "equity", "EX") == instrument
        assert loaded.resolve_listing("provider", "equity", "EX") == listing

        conflicting = Catalog()
        conflicting.add_instrument(Instrument("instrument", InstrumentKind.EQUITY, "Other"))
        with pytest.raises(ValueError, match="different instrument"):
            store.save_catalog(conflicting)

    with DuckDBStore.open(path, read_only=True) as store:
        restored = store.load_catalog()
    assert restored.instruments == (instrument,)
    assert restored.listings == (listing,)
    assert restored.provider_symbols == (mapping,)


def test_store_create_rejects_a_competing_atomic_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "claimed.duckdb"
    original_link = store_module.os.link
    injected = False

    def competing_link(source: str | Path, target: str | Path) -> None:
        nonlocal injected
        if Path(target) == path and not injected:
            injected = True
            path.write_bytes(b"competitor")
        original_link(source, target)

    monkeypatch.setattr(store_module.os, "link", competing_link)

    with pytest.raises(StoreError, match="already exists") as caught:
        DuckDBStore.create(path)

    assert isinstance(caught.value.__cause__, FileExistsError)
    assert path.read_bytes() == b"competitor"


def test_store_create_removes_only_its_claim_after_schema_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    owned_path = tmp_path / "owned.duckdb"
    original_schema = store_module._create_schema  # pyright: ignore[reportPrivateUsage]

    def fail_schema(_connection: duckdb.DuckDBPyConnection) -> None:
        raise RuntimeError("injected schema failure")

    monkeypatch.setattr(store_module, "_create_schema", fail_schema)
    with pytest.raises(StoreError, match=str(owned_path)) as caught:
        DuckDBStore.create(owned_path)
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert not owned_path.exists()

    replaced_path = tmp_path / "replaced.duckdb"
    original_connect = store_module.duckdb.connect

    def replace_then_fail(path: str) -> duckdb.DuckDBPyConnection:
        if Path(path) != replaced_path:
            return original_connect(path)
        replaced_path.unlink()
        replaced_path.write_bytes(b"replacement")
        raise RuntimeError("injected schema failure")

    monkeypatch.setattr(store_module, "_create_schema", original_schema)
    monkeypatch.setattr(store_module.duckdb, "connect", replace_then_fail)
    with pytest.raises(StoreError) as replaced:
        DuckDBStore.create(replaced_path)
    assert replaced_path.read_bytes() == b"replacement"
    cause = replaced.value.__cause__
    assert cause is not None
    assert cause.__notes__ == ["claimed store path was replaced; replacement was preserved"]


@pytest.mark.parametrize(
    ("row", "error", "message"),
    [
        (None, duckdb.CatalogException("missing schema"), "missing or invalid"),
        (None, None, "missing or invalid"),
        (("invalid",), None, "missing or invalid"),
        ((99,), None, "not supported"),
    ],
)
def test_store_open_closes_connections_after_schema_validation_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    row: tuple[object, ...] | None,
    error: duckdb.Error | None,
    message: str,
) -> None:
    path = tmp_path / "invalid-schema.duckdb"
    path.touch()
    connection = _SchemaConnection(row, error)

    def connect(_path: str, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        del read_only
        return cast("duckdb.DuckDBPyConnection", connection)

    monkeypatch.setattr(store_module.duckdb, "connect", connect)

    with pytest.raises(StoreError, match=message):
        DuckDBStore.open(path)
    assert connection.closed


@pytest.mark.parametrize(
    ("fail_on", "expects_rollback"),
    [
        ("BEGIN TRANSACTION", False),
        ("SELECT snapshot_id", True),
        ("COMMIT", True),
    ],
)
def test_store_save_preserves_begin_write_and_commit_failures(
    tmp_path: Path, fail_on: str, expects_rollback: bool
) -> None:
    store = DuckDBStore.create(tmp_path / f"{fail_on.split()[0].lower()}.duckdb")
    actual = store._connection  # pyright: ignore[reportPrivateUsage]
    connection = _FaultingConnection(actual, fail_on=fail_on)
    store._connection = cast(  # pyright: ignore[reportPrivateUsage]
        "duckdb.DuckDBPyConnection", connection
    )

    with pytest.raises(StoreError, match="could not save quotes") as caught:
        store.save(synthetic.quotes())

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert ("ROLLBACK" in connection.commands) is expects_rollback
    assert not connection.closed
    assert store.save(synthetic.quotes())
    store.close()


def test_store_save_closes_connection_when_rollback_fails(tmp_path: Path) -> None:
    store = DuckDBStore.create(tmp_path / "rollback.duckdb")
    actual = store._connection  # pyright: ignore[reportPrivateUsage]
    connection = _FaultingConnection(
        actual,
        fail_on="SELECT snapshot_id",
        rollback_fails=True,
    )
    store._connection = cast(  # pyright: ignore[reportPrivateUsage]
        "duckdb.DuckDBPyConnection", connection
    )

    with pytest.raises(StoreError, match="could not save quotes") as caught:
        store.save(synthetic.quotes())

    assert isinstance(caught.value.__cause__, RuntimeError)
    assert caught.value.__notes__ == [
        "rollback failed: RuntimeError('injected rollback failure')",
        "store connection closed after rollback failure",
    ]
    assert connection.closed
    with pytest.raises(duckdb.ConnectionException, match="closed"):
        actual.execute("SELECT 1")


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
        synthetic.vintage_dates(),
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


def test_vintage_dates_round_trip_recurrence_empty_and_cutoff(tmp_path: Path) -> None:
    first = synthetic.vintage_dates()
    later_time = first.metadata.retrieved_at + timedelta(hours=1)
    recurrence = VintageDatesResult(
        first.provider_series,
        first.dates,
        replace(first.metadata, retrieved_at=later_time),
    )
    empty = synthetic.vintage_dates("EMPTY", dates=())
    with DuckDBStore.create(tmp_path / "vintage-dates.duckdb") as store:
        snapshot_id = store.save(first)
        assert store.save(recurrence) == snapshot_id
        empty_id = store.save(empty)
        loaded = store.load_vintage_dates(first.provider_series)
        before = store.load_vintage_dates(
            first.provider_series,
            retrieved_before=first.metadata.retrieved_at,
        )
        queried = store.query_vintage_dates(first.provider_series)
        datasets = {item.scope_key: item for item in store.list_datasets()}
        exact_empty = store.load_snapshot(empty_id)

    assert loaded is not None and loaded.metadata.retrieved_at == later_time
    assert before is not None and before.metadata.retrieved_at == first.metadata.retrieved_at
    assert queried["vintage_date"].dt.date.tolist() == list(first.dates)
    assert queried.dtypes.astype(str).to_dict() == {
        "provider_series": "string",
        "vintage_date": "datetime64[ns]",
        "retrieved_at": "datetime64[ns, UTC]",
    }
    assert datasets[first.provider_series].snapshot_count == 1
    assert isinstance(exact_empty, VintageDatesResult) and exact_empty.dates == ()


def test_quote_and_book_history_report_revisions_recurrence_and_filters(tmp_path: Path) -> None:
    observed_at = synthetic.SYNTHETIC_NOW - timedelta(minutes=5)
    source = synthetic.quotes(("AAA", "BBB"))
    first_frame = source.frame.copy()
    first_frame["observed_at"] = pd.Series(
        [observed_at] * len(first_frame), dtype="datetime64[ns, UTC]"
    )
    first = QuoteSet(first_frame, source.metadata)

    recurrence_time = source.metadata.retrieved_at + timedelta(hours=1)
    recurrence_frame = first.frame.copy()
    recurrence_frame["retrieved_at"] = pd.Series(
        [recurrence_time] * len(recurrence_frame), dtype="datetime64[ns, UTC]"
    )
    recurrence = QuoteSet(
        recurrence_frame,
        replace(first.metadata, retrieved_at=recurrence_time),
    )
    revision_time = source.metadata.retrieved_at + timedelta(hours=2)
    revision_frame = recurrence.frame.iloc[[0]].copy().reset_index(drop=True)
    revision_frame.loc[0, "price"] = cast("float", revision_frame.loc[0, "price"]) + 5
    revision_frame["retrieved_at"] = pd.Series([revision_time], dtype="datetime64[ns, UTC]")
    revision = QuoteSet(
        revision_frame,
        replace(first.metadata, retrieved_at=revision_time),
    )
    with DuckDBStore.create(tmp_path / "quote-history.duckdb") as store:
        store.save(first)
        store.save(recurrence)
        store.save(revision)
        history = store.query_quote_history(provider="synthetic", symbol="AAA")
        cutoff = store.query_quote_history(retrieved_end=recurrence_time)
        none = store.query_quote_history(symbol="MISSING")
        empty_book = store.query_top_of_book_history()

    assert history["price"].tolist() == [100.0, 105.0]
    assert history["retrieval_count"].tolist() == [2, 1]
    assert history["first_retrieved_at"].tolist()[0] == source.metadata.retrieved_at
    assert history["last_retrieved_at"].tolist()[0] == recurrence_time
    assert len(cutoff) == 2
    assert none.empty and none.dtypes.astype(str).to_dict() == QUOTE_HISTORY_DTYPES
    assert empty_book.empty
    assert empty_book.dtypes.astype(str).to_dict() == TOP_OF_BOOK_HISTORY_DTYPES
    with DuckDBStore.open(tmp_path / "quote-history.duckdb", read_only=True) as store:
        with pytest.raises(ValueError, match="timezone-aware"):
            store.query_quote_history(observed_start=datetime(2025, 1, 1))
        with pytest.raises(ValueError, match="must not follow"):
            store.query_quote_history(
                retrieved_start=revision_time,
                retrieved_end=source.metadata.retrieved_at,
            )


def test_option_snapshot_queries_filter_contracts_and_retrievals(tmp_path: Path) -> None:
    first = synthetic.option_chain()
    later_time = first.metadata.retrieved_at + timedelta(hours=1)
    later_observations = first.observations.copy()
    later_observations["retrieved_at"] = pd.Series(
        [later_time] * len(later_observations), dtype="datetime64[ns, UTC]"
    )
    later = type(first)(
        first.underlying_instrument_id,
        first.provider_symbol,
        first.chain_date,
        first.contracts,
        later_observations,
        replace(first.metadata, retrieved_at=later_time),
    )
    expiration = first.contracts["expiration"].dt.date.iloc[0]
    strike = cast("float", first.contracts.loc[0, "strike"])
    option_type = cast("str", first.contracts.loc[0, "option_type"])
    with DuckDBStore.create(tmp_path / "option-history.duckdb") as store:
        store.save(first)
        store.save(later)
        snapshots = store.query_option_snapshots(
            first.underlying_instrument_id,
            expiration=expiration,
            strike=strike,
            option_type=option_type,
        )
        cutoff = store.query_option_snapshots(
            first.underlying_instrument_id,
            retrieved_before=first.metadata.retrieved_at,
        )
        missing = store.query_option_snapshots(first.underlying_instrument_id, strike=999_999)

    assert all(isinstance(item, StoredOptionSnapshot) for item in snapshots)
    assert [item.retrieved_at for item in snapshots] == [first.metadata.retrieved_at, later_time]
    assert all(len(item.chain.contracts) == 1 for item in snapshots)
    assert len(cutoff) == 1
    assert len(missing) == 2 and all(item.chain.contracts.empty for item in missing)


def test_snapshot_diff_separates_content_provenance_and_schema_diagnostics(
    tmp_path: Path,
) -> None:
    first = synthetic.bars(periods=2)
    later_time = first.metadata.retrieved_at + timedelta(hours=1)
    changed_frame = first.frame.copy()
    changed_frame.loc[1, "close"] = cast("float", changed_frame.loc[1, "close"]) + 1
    changed_frame.loc[1, "high"] = max(
        cast("float", changed_frame.loc[1, "high"]),
        cast("float", changed_frame.loc[1, "close"]),
    )
    changed_frame["retrieved_at"] = pd.Series(
        [later_time] * len(changed_frame), dtype="datetime64[ns, UTC]"
    )
    changed = type(first)(
        first.instrument,
        changed_frame,
        replace(
            first.metadata,
            retrieved_at=later_time,
            diagnostics=(
                SchemaDiagnostic(
                    "close",
                    "provider corrected value",
                    action="quarantine",
                    rule="invalid_close",
                    row_identity="2025-01-02",
                    row_count=1,
                    raw_sha256="a" * 64,
                ),
            ),
        ),
    )
    with DuckDBStore.create(tmp_path / "diff.duckdb") as store:
        first_id = store.save(first)
        changed_id = store.save(changed)
        identical = store.diff_snapshots(first_id, first_id)
        difference = store.diff_snapshots(first_id, changed_id)
        with pytest.raises(ValueError, match="same family"):
            store.diff_snapshots(first_id, store.save(synthetic.series(periods=1)))

    assert isinstance(difference, SnapshotDiff)
    assert not identical.source_changed and not identical.provenance_changed
    assert difference.source_changed and difference.provenance_changed
    assert [item.field for item in difference.changed_values] == ["close", "high"]
    assert [item.field for item in difference.metadata_changes] == ["retrieved_at"]
    assert difference.schema_diagnostics_after == changed.metadata.diagnostics


def test_snapshot_diff_covers_identical_and_changed_examples_for_every_family(
    tmp_path: Path,
) -> None:
    first_status = synthetic.market_status()
    changed_status_frame = first_status.frame.copy()
    changed_status_frame.loc[0, "current_status"] = "closed"
    second_status = MarketStatusResult(changed_status_frame, first_status.metadata)
    first_catalog = synthetic.index_catalog()
    changed_catalog_frame = first_catalog.frame.copy()
    changed_catalog_frame.loc[0, "name"] = "Changed index"
    second_catalog = IndexCatalogResult(changed_catalog_frame, first_catalog.metadata)
    pairs = (
        (synthetic.bars("AAA", periods=1), synthetic.bars("BBB", periods=1)),
        (synthetic.quotes(("AAA",)), synthetic.quotes(("BBB",))),
        (synthetic.top_of_book(("AAA",)), synthetic.top_of_book(("BBB",))),
        (synthetic.option_chain("AAA"), synthetic.option_chain("BBB")),
        (synthetic.series("SERIES_A", periods=1), synthetic.series("SERIES_B", periods=1)),
        (
            synthetic.vintage_series("SERIES_A", periods=1),
            synthetic.vintage_series("SERIES_B", periods=1),
        ),
        (synthetic.vintage_dates("SERIES_A"), synthetic.vintage_dates("SERIES_B")),
        (synthetic.exchange_rate("EUR", "USD"), synthetic.exchange_rate("GBP", "USD")),
        (synthetic.commodity_spot("gold"), synthetic.commodity_spot("silver")),
        (synthetic.search("AAA"), synthetic.search("BBB")),
        (first_status, second_status),
        (first_catalog, second_catalog),
    )
    with DuckDBStore.create(tmp_path / "all-family-diffs.duckdb") as store:
        for before, after in pairs:
            before_id = store.save(before)
            after_id = store.save(after)
            identical = store.diff_snapshots(before_id, before_id)
            changed = store.diff_snapshots(before_id, after_id)
            assert not identical.source_changed
            assert changed.source_changed


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


def test_bar_occurrences_preserve_recurrence_and_retrieval_chronology(tmp_path: Path) -> None:
    source = synthetic.bars(periods=2)
    first_seen = source.metadata.retrieved_at

    def observed(retrieved_at: datetime, *, close_delta: float = 0) -> BarSet:
        frame = source.frame.copy()
        frame["retrieved_at"] = pd.Series(
            [retrieved_at] * len(frame),
            dtype="datetime64[ns, UTC]",
        )
        if close_delta:
            close = cast("float", frame.loc[1, "close"]) + close_delta
            frame.loc[1, "close"] = close
            frame.loc[1, "high"] = max(cast("float", frame.loc[1, "high"]), close)
        return BarSet(
            source.instrument,
            frame,
            replace(source.metadata, retrieved_at=retrieved_at),
        )

    second_seen = first_seen + timedelta(hours=2)
    third_seen = first_seen + timedelta(hours=3)
    latest_seen = first_seen + timedelta(hours=4)
    original = observed(first_seen)
    old_changed = observed(first_seen + timedelta(hours=1), close_delta=2)
    changed = observed(second_seen, close_delta=5)
    latest_recurrence = observed(latest_seen)
    out_of_order_recurrence = observed(third_seen)

    with DuckDBStore.create(tmp_path / "occurrences.duckdb") as store:
        original_id = store.save(original)
        changed_id = store.save(changed)
        assert store.save(latest_recurrence) == original_id
        assert store.save(out_of_order_recurrence) == original_id
        assert store.save(latest_recurrence) == original_id
        old_changed_id = store.save(old_changed)

        dataset = store.list_datasets()[0]
        snapshots = store.list_snapshots("bars", source.instrument.instrument_id)
        occurrence_count = store._connection.execute(  # pyright: ignore[reportPrivateUsage]
            "SELECT count(*) FROM acquisition_occurrences"
        ).fetchone()
        latest = store.load_bars(source.instrument.instrument_id)
        at_second = store.load_bars(
            source.instrument.instrument_id,
            retrieved_before=second_seen,
        )
        at_old_change = store.load_bars(
            source.instrument.instrument_id,
            retrieved_before=old_changed.metadata.retrieved_at,
        )
        at_third = store.load_bars(
            source.instrument.instrument_id,
            retrieved_before=third_seen,
        )
        cumulative_latest = store.query_bars(source.instrument.instrument_id)
        cumulative_second = store.query_bars(
            source.instrument.instrument_id,
            retrieved_before=second_seen,
        )
        exact_original = store.load_snapshot(original_id)

    assert occurrence_count == (6,)
    assert dataset.snapshot_count == 3
    assert dataset.first_seen == first_seen
    assert dataset.last_seen == latest_seen
    assert dataset.latest_snapshot_id == original_id
    assert [snapshot.snapshot_id for snapshot in snapshots] == [
        original_id,
        changed_id,
        old_changed_id,
    ]
    assert snapshots[0].first_seen == first_seen
    assert snapshots[0].last_seen == latest_seen
    assert latest is not None and at_old_change is not None
    assert at_second is not None and at_third is not None
    assert latest.frame.loc[1, "close"] == original.frame.loc[1, "close"]
    assert latest.metadata.retrieved_at == latest_seen
    assert at_second.frame.loc[1, "close"] == changed.frame.loc[1, "close"]
    assert at_second.metadata.retrieved_at == second_seen
    assert at_old_change.frame.loc[1, "close"] == old_changed.frame.loc[1, "close"]
    assert at_old_change.metadata.retrieved_at == old_changed.metadata.retrieved_at
    assert at_third.frame.loc[1, "close"] == original.frame.loc[1, "close"]
    assert at_third.metadata.retrieved_at == third_seen
    assert cumulative_latest.loc[1, "close"] == original.frame.loc[1, "close"]
    assert cumulative_latest["retrieved_at"].eq(latest_seen).all()
    assert cumulative_second.loc[1, "close"] == changed.frame.loc[1, "close"]
    assert cumulative_second["retrieved_at"].eq(second_seen).all()
    assert isinstance(exact_original, BarSet)
    assert exact_original.metadata.retrieved_at == first_seen


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
        frame["retrieved_at"] = pd.Series([retrieved_at] * len(frame), dtype="datetime64[ns, UTC]")
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
        revised_frame["retrieved_at"] = pd.Series([revision_time], dtype="datetime64[ns, UTC]")
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
        assert (
            len(
                store.query_bars(
                    source.instrument.instrument_id,
                    interval="5min",
                    start=intraday_start,
                    end=intraday_end,
                )
            )
            == 2
        )
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


def test_bounded_bar_pages_have_exact_totals_and_stable_server_sorting(tmp_path: Path) -> None:
    source = synthetic.bars(periods=2_501)
    with DuckDBStore.create(tmp_path / "paged-bars.duckdb") as store:
        store.save(source)
        first = store.query_bars_page(
            source.instrument.instrument_id,
            limit=128,
            sort_by="close",
            descending=True,
        )
        second = store.query_bars_page(
            source.instrument.instrument_id,
            limit=128,
            offset=128,
            sort_by="close",
            descending=True,
        )
        tail = store.query_bars_page(
            source.instrument.instrument_id,
            limit=128,
            offset=2_500,
            sort_by="close",
            descending=True,
        )
        empty = store.query_bars_page(
            source.instrument.instrument_id,
            limit=128,
            offset=3_000,
        )

    assert isinstance(first, StoredPage)
    assert first.total_count == second.total_count == tail.total_count == 2_501
    assert len(first.frame) == len(second.frame) == 128
    assert len(tail.frame) == 1
    assert not first.has_previous and first.has_next
    assert second.has_previous and second.has_next
    assert tail.has_previous and not tail.has_next
    assert empty.frame.empty and empty.total_count == 2_501
    assert empty.has_previous and not empty.has_next

    observed = pd.concat([first.frame, second.frame], ignore_index=True)
    expected = source.frame.sort_values(
        [
            "close",
            "instrument_id",
            "interval",
            "price_adjustment",
            "session",
            "date",
            "timestamp",
        ],
        ascending=[False, True, True, True, True, True, True],
        na_position="last",
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(observed, expected.iloc[:256].reset_index(drop=True))


def test_bounded_pages_apply_family_filters_before_counting(tmp_path: Path) -> None:
    bars = synthetic.bars(periods=8)
    series = synthetic.series(periods=8)
    vintages = synthetic.vintage_series(periods=4)
    with DuckDBStore.create(tmp_path / "filtered-pages.duckdb") as store:
        store.save(bars)
        store.save(series)
        store.save(vintages)
        bar_page = store.query_bars_page(
            bars.instrument.instrument_id,
            start=date(2025, 1, 3),
            end=date(2025, 1, 6),
            limit=2,
        )
        series_page = store.query_series_page(
            series.definition.series_id,
            start_label="2023-03-01",
            end_label="2023-06-01",
            limit=2,
            offset=2,
            sort_by="value",
            descending=True,
        )
        vintage_page = store.query_vintage_series_page(
            vintages.definition.series_id,
            start_label="2023-02-01",
            available_on=date(2023, 6, 1),
            limit=3,
            sort_by="period_label",
            descending=True,
        )

    assert bar_page.total_count == 4
    assert bar_page.frame["date"].dt.date.tolist() == [date(2025, 1, 3), date(2025, 1, 4)]
    assert series_page.total_count == 4
    assert series_page.frame["value"].is_monotonic_decreasing
    assert vintage_page.total_count == 3
    assert vintage_page.frame["period_label"].tolist() == [
        "2023-04-01",
        "2023-03-01",
        "2023-02-01",
    ]


@pytest.mark.parametrize(
    ("arguments", "error", "message"),
    [
        ({"limit": 0}, ValueError, "limit"),
        ({"limit": 1_001}, ValueError, "limit"),
        ({"limit": True}, ValueError, "limit"),
        ({"offset": -1}, ValueError, "offset"),
        ({"offset": False}, ValueError, "offset"),
        ({"sort_by": "close DESC; DROP TABLE snapshots"}, ValueError, "sort_by"),
        ({"descending": 1}, TypeError, "descending"),
    ],
)
def test_bounded_page_requests_validate_limits_and_sorting(
    tmp_path: Path,
    arguments: dict[str, object],
    error: type[Exception],
    message: str,
) -> None:
    source = synthetic.bars(periods=1)
    with DuckDBStore.create(tmp_path / "invalid-page.duckdb") as store:
        store.save(source)
        with pytest.raises(error, match=message):
            store.query_bars_page(source.instrument.instrument_id, **arguments)  # type: ignore[arg-type]


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


def test_series_round_trip_preserves_explicit_missing_observation(tmp_path: Path) -> None:
    source = synthetic.series(periods=3)
    frame = source.frame.copy()
    frame.loc[1, "value"] = float("nan")
    result = SeriesSet(source.definition, frame, source.metadata)

    with DuckDBStore.create(tmp_path / "missing-series.duckdb") as store:
        snapshot_id = store.save(result)
        loaded = store.load_snapshot(snapshot_id)
        queried = store.query_series(source.definition.series_id)

    assert isinstance(loaded, SeriesSet)
    pd.testing.assert_frame_equal(loaded.frame, result.frame)
    assert queried["period_label"].tolist() == result.frame["period_label"].tolist()
    assert pd.isna(queried.loc[1, "value"])


def test_series_queries_accumulate_partial_acquisitions(tmp_path: Path) -> None:
    source = synthetic.series(periods=4)
    first_seen = source.metadata.retrieved_at

    def partial(rows: slice, retrieved_at: datetime) -> SeriesSet:
        frame = source.frame.iloc[rows].copy().reset_index(drop=True)
        frame["retrieved_at"] = pd.Series([retrieved_at] * len(frame), dtype="datetime64[ns, UTC]")
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
        revision_frame["retrieved_at"] = pd.Series([revision_seen], dtype="datetime64[ns, UTC]")
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
        frame = (
            source.frame[source.frame["period_label"].isin(periods)].copy().reset_index(drop=True)
        )
        frame["retrieved_at"] = pd.Series([retrieved_at] * len(frame), dtype="datetime64[ns, UTC]")
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
