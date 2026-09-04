"""Explicit versioned DuckDB storage for normalized results."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from math import isfinite
from numbers import Real
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Self, cast

import duckdb
import pandas as pd

from persistra._json import strict_json_loads
from persistra._portable import thaw_portable_mapping
from persistra.errors import StoreError
from persistra.model import (
    BarSet,
    CacheStatus,
    Catalog,
    CommoditySpotQuote,
    EntitlementMode,
    ExchangeRateQuote,
    IndexCatalogResult,
    Instrument,
    InstrumentKind,
    InstrumentSearchResult,
    Listing,
    MarketStatusResult,
    OptionChain,
    ProviderSymbol,
    QuoteSet,
    ResultMetadata,
    SchemaDiagnostic,
    SeriesDefinition,
    SeriesKind,
    SeriesSet,
    TopOfBookSet,
    VintageDatesResult,
    VintageSeriesSet,
)
from persistra.model._frames import (
    BAR_DTYPES,
    OPTION_CONTRACT_DTYPES,
    OPTION_OBSERVATION_DTYPES,
    QUOTE_DTYPES,
    SERIES_DTYPES,
    TOP_OF_BOOK_DTYPES,
    VINTAGE_SERIES_DTYPES,
    typed_frame,
)
from persistra.model.reference import INDEX_CATALOG_DTYPES, MARKET_STATUS_DTYPES, SEARCH_DTYPES

STORE_SCHEMA_VERSION = 2

type StoredResult = (
    BarSet
    | QuoteSet
    | TopOfBookSet
    | OptionChain
    | SeriesSet
    | VintageSeriesSet
    | VintageDatesResult
    | ExchangeRateQuote
    | CommoditySpotQuote
    | InstrumentSearchResult
    | MarketStatusResult
    | IndexCatalogResult
)


@dataclass(frozen=True, slots=True)
class StoredDataset:
    """Summary of one stored result family and scope."""

    family: str
    scope_key: str
    snapshot_count: int
    first_seen: datetime
    last_seen: datetime
    latest_snapshot_id: str


@dataclass(frozen=True, slots=True)
class StoredSnapshot:
    """Identity and observation bounds for one exact acquisition snapshot."""

    snapshot_id: str
    family: str
    scope_key: str
    content_hash: str
    first_seen: datetime
    last_seen: datetime
    saved_order: int


@dataclass(frozen=True, slots=True)
class MigratedSnapshot:
    """One source snapshot identity mapped to its migrated target identity."""

    source_snapshot_id: str
    target_snapshot_id: str
    occurrence_count: int


@dataclass(frozen=True, slots=True)
class StoreMigration:
    """Durable lineage summary for one non-destructive store migration."""

    source_store_sha256: str
    source_schema_version: int
    target_schema_version: int
    source_snapshot_count: int
    target_snapshot_count: int
    occurrence_count: int
    snapshots: tuple[MigratedSnapshot, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible migration summary."""
        return {
            "source_store_sha256": self.source_store_sha256,
            "source_schema_version": self.source_schema_version,
            "target_schema_version": self.target_schema_version,
            "source_snapshot_count": self.source_snapshot_count,
            "target_snapshot_count": self.target_snapshot_count,
            "occurrence_count": self.occurrence_count,
            "snapshots": [asdict(snapshot) for snapshot in self.snapshots],
        }


def _migrated_snapshot_from_dict(value: object) -> MigratedSnapshot:
    if not isinstance(value, dict):
        raise ValueError("migration snapshot must be an object")
    raw = cast("dict[object, object]", value)
    source_id = raw.get("source_snapshot_id")
    target_id = raw.get("target_snapshot_id")
    count = raw.get("occurrence_count")
    if not isinstance(source_id, str) or not isinstance(target_id, str):
        raise ValueError("migration snapshot identities must be strings")
    if type(count) is not int or count <= 0:
        raise ValueError("migration snapshot occurrence count must be positive")
    return MigratedSnapshot(source_id, target_id, count)


@dataclass(frozen=True, slots=True)
class StoredPage:
    """One bounded, stably ordered page from a cumulative dataset query."""

    frame: pd.DataFrame
    total_count: int
    limit: int
    offset: int
    sort_by: str | None
    descending: bool

    @property
    def has_previous(self) -> bool:
        """Return whether an earlier page exists."""
        return self.offset > 0

    @property
    def has_next(self) -> bool:
        """Return whether a later page exists."""
        return self.offset + len(self.frame) < self.total_count


@dataclass(frozen=True, slots=True)
class StoredOptionSnapshot:
    """One retained option-chain occurrence after public query filters."""

    snapshot_id: str
    retrieved_at: datetime
    chain: OptionChain


@dataclass(frozen=True, slots=True)
class SnapshotRow:
    """One immutable normalized row in a snapshot diff."""

    table: str
    identity: tuple[object, ...]
    values: tuple[tuple[str, object], ...]


@dataclass(frozen=True, slots=True)
class SnapshotValueChange:
    """One changed normalized value or provenance field."""

    table: str
    identity: tuple[object, ...]
    field: str
    before: object
    after: object


@dataclass(frozen=True, slots=True)
class SnapshotDiff:
    """Stable source-content and acquisition-provenance snapshot differences."""

    family: str
    before_snapshot_id: str
    after_snapshot_id: str
    metadata_changes: tuple[SnapshotValueChange, ...]
    schema_diagnostics_before: tuple[SchemaDiagnostic, ...]
    schema_diagnostics_after: tuple[SchemaDiagnostic, ...]
    added_rows: tuple[SnapshotRow, ...]
    removed_rows: tuple[SnapshotRow, ...]
    changed_values: tuple[SnapshotValueChange, ...]

    @property
    def source_changed(self) -> bool:
        """Return whether normalized source content differs."""
        return bool(self.added_rows or self.removed_rows or self.changed_values)

    @property
    def provenance_changed(self) -> bool:
        """Return whether acquisition provenance or diagnostics differ."""
        return bool(
            self.metadata_changes or self.schema_diagnostics_before != self.schema_diagnostics_after
        )


@dataclass(frozen=True, slots=True)
class _DatasetTable:
    name: str
    frame_key: str
    dtypes: dict[str, str]
    row_key: tuple[str, ...]
    snapshot_family: str | None = None


_DATASET_TABLES = {
    "bars": _DatasetTable(
        "bar_rows",
        "frame",
        BAR_DTYPES,
        (
            "instrument_id",
            "interval",
            "price_adjustment",
            "session",
            "date",
            "timestamp",
        ),
    ),
    "series": _DatasetTable(
        "series_rows",
        "frame",
        SERIES_DTYPES,
        ("series_id", "frequency", "maturity", "period_label"),
    ),
    "vintage_series": _DatasetTable(
        "vintage_series_rows",
        "frame",
        VINTAGE_SERIES_DTYPES,
        (
            "series_id",
            "frequency",
            "maturity",
            "period_label",
            "available_from",
        ),
    ),
    "quotes": _DatasetTable(
        "quote_rows",
        "frame",
        QUOTE_DTYPES,
        ("provider", "provider_symbol"),
    ),
    "top_of_book": _DatasetTable(
        "top_of_book_rows",
        "frame",
        TOP_OF_BOOK_DTYPES,
        ("provider", "provider_symbol"),
    ),
    "option_contracts": _DatasetTable(
        "option_contract_rows",
        "contracts",
        OPTION_CONTRACT_DTYPES,
        ("provider", "contract_id"),
        "options",
    ),
    "option_observations": _DatasetTable(
        "option_observation_rows",
        "observations",
        OPTION_OBSERVATION_DTYPES,
        ("provider", "contract_id", "chain_date"),
        "options",
    ),
    "vintage_dates": _DatasetTable(
        "vintage_date_rows",
        "frame",
        {
            "provider_series": "string",
            "vintage_date": "datetime64[ns]",
            "retrieved_at": "datetime64[ns, UTC]",
        },
        ("provider_series", "vintage_date"),
    ),
}

QUOTE_HISTORY_DTYPES: dict[str, str] = {
    "revision_id": "string",
    **{name: dtype for name, dtype in QUOTE_DTYPES.items() if name != "retrieved_at"},
    "first_retrieved_at": "datetime64[ns, UTC]",
    "last_retrieved_at": "datetime64[ns, UTC]",
    "retrieval_count": "Int64",
}

TOP_OF_BOOK_HISTORY_DTYPES: dict[str, str] = {
    "revision_id": "string",
    **{name: dtype for name, dtype in TOP_OF_BOOK_DTYPES.items() if name != "retrieved_at"},
    "first_retrieved_at": "datetime64[ns, UTC]",
    "last_retrieved_at": "datetime64[ns, UTC]",
    "retrieval_count": "Int64",
}


def _remove_claimed_store(target: Path, claim: tuple[int, int], failure: Exception) -> None:
    try:
        current = target.lstat()
    except FileNotFoundError:
        return
    except OSError as cleanup_error:
        failure.add_note(f"store cleanup failed: {cleanup_error!r}")
        return
    if (current.st_dev, current.st_ino) != claim:
        failure.add_note("claimed store path was replaced; replacement was preserved")
        return
    try:
        target.unlink()
    except OSError as cleanup_error:
        failure.add_note(f"store cleanup failed: {cleanup_error!r}")


class DuckDBStore:
    """A one-process DuckDB store with snapshots and cumulative research datasets."""

    def __init__(self, path: Path, connection: duckdb.DuckDBPyConnection) -> None:
        self.path = path
        self._connection = connection

    @classmethod
    def create(cls, path: str | Path) -> Self:
        """Create a new store with the current supported schema at an absent path."""
        target = Path(path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StoreError(f"could not create store: {target}") from error
        claim: tuple[int, int] | None = None
        connection: duckdb.DuckDBPyConnection | None = None
        try:
            with TemporaryDirectory(
                dir=target.parent, prefix=f".{target.name}."
            ) as staging_directory:
                staged = Path(staging_directory) / "store.duckdb"
                staged_connection = duckdb.connect(str(staged))
                try:
                    _create_schema(staged_connection)
                except Exception as error:
                    try:
                        staged_connection.close()
                    except Exception as close_error:
                        error.add_note(f"connection cleanup failed: {close_error!r}")
                    raise
                staged_connection.close()
                staged_file = staged.lstat()
                try:
                    os.link(staged, target)
                except FileExistsError as error:
                    raise StoreError(f"store already exists: {target}") from error
                claim = staged_file.st_dev, staged_file.st_ino
            connection = duckdb.connect(str(target))
        except StoreError:
            raise
        except Exception as error:
            if connection is not None:
                try:
                    connection.close()
                except Exception as close_error:
                    error.add_note(f"connection cleanup failed: {close_error!r}")
            if claim is not None:
                _remove_claimed_store(target, claim, error)
            raise StoreError(f"could not create store: {target}") from error
        return cls(target, connection)

    @classmethod
    def open(cls, path: str | Path, *, read_only: bool = False) -> Self:
        """Open an existing store after validating its schema without migrating it."""
        target = Path(path)
        if not target.is_file():
            raise StoreError(f"store does not exist: {target}")
        try:
            connection = duckdb.connect(str(target), read_only=read_only)
        except duckdb.Error as error:
            raise StoreError(f"store is not a valid DuckDB database: {target}") from error
        try:
            try:
                row = connection.execute("SELECT version FROM schema_version").fetchone()
            except duckdb.Error as error:
                raise StoreError("store schema is missing or invalid") from error
            if row is None or type(row[0]) is not int:
                raise StoreError("store schema is missing or invalid")
            if row[0] != STORE_SCHEMA_VERSION:
                raise StoreError("store schema version is not supported")
            from persistra.data.verification import (
                _verify_schema,  # pyright: ignore[reportPrivateUsage]
            )

            findings: list[Any] = []
            if not _verify_schema(connection, findings):
                message = getattr(findings[0], "message", "store schema is invalid")
                raise StoreError(f"store schema is missing or invalid: {message}")
        except Exception as error:
            try:
                connection.close()
            except Exception as close_error:
                error.add_note(f"connection cleanup failed: {close_error!r}")
            raise
        return cls(target, connection)

    def close(self) -> None:
        """Close the explicit DuckDB connection."""
        self._connection.close()

    @property
    def schema_version(self) -> int:
        """Return the validated store schema version."""
        return STORE_SCHEMA_VERSION

    def migration_lineage(self) -> StoreMigration | None:
        """Return the durable migration lineage for this store, when present."""
        row = self._connection.execute(
            """
            SELECT
                source_store_sha256,
                source_schema_version,
                target_schema_version,
                source_snapshot_count,
                target_snapshot_count,
                occurrence_count,
                snapshots
            FROM store_migration
            """
        ).fetchone()
        if row is None:
            return None
        raw_snapshots = strict_json_loads(str(row[6]))
        if not isinstance(raw_snapshots, list):
            raise StoreError("store migration lineage is invalid")
        try:
            snapshots = tuple(
                _migrated_snapshot_from_dict(item)
                for item in cast("list[object]", raw_snapshots)
            )
        except (TypeError, ValueError) as error:
            raise StoreError("store migration lineage is invalid") from error
        return StoreMigration(
            source_store_sha256=str(row[0]),
            source_schema_version=int(row[1]),
            target_schema_version=int(row[2]),
            source_snapshot_count=int(row[3]),
            target_snapshot_count=int(row[4]),
            occurrence_count=int(row[5]),
            snapshots=snapshots,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def load_catalog(self) -> Catalog:
        """Load the complete persistent instrument catalog into an isolated value."""
        catalog = Catalog()
        instrument_rows = self._connection.execute(
            """
            SELECT instrument_id, kind, display_name, base_currency, quote_currency
            FROM catalog_instruments
            ORDER BY instrument_id
            """
        ).fetchall()
        for row in instrument_rows:
            catalog.add_instrument(
                Instrument(
                    str(row[0]),
                    InstrumentKind(str(row[1])),
                    str(row[2]),
                    None if row[3] is None else str(row[3]),
                    None if row[4] is None else str(row[4]),
                )
            )
        listing_rows = self._connection.execute(
            """
            SELECT listing_id, instrument_id, symbol, exchange, mic, currency, source_timezone
            FROM catalog_listings
            ORDER BY listing_id
            """
        ).fetchall()
        for row in listing_rows:
            catalog.add_listing(
                Listing(
                    str(row[0]),
                    str(row[1]),
                    str(row[2]),
                    None if row[3] is None else str(row[3]),
                    None if row[4] is None else str(row[4]),
                    None if row[5] is None else str(row[5]),
                    None if row[6] is None else str(row[6]),
                )
            )
        mapping_rows = self._connection.execute(
            """
            SELECT provider, kind, symbol, instrument_id, listing_id
            FROM catalog_provider_symbols
            ORDER BY provider, kind, symbol
            """
        ).fetchall()
        for row in mapping_rows:
            catalog.map_provider_symbol(
                ProviderSymbol(
                    str(row[0]),
                    InstrumentKind(str(row[1])),
                    str(row[2]),
                    str(row[3]),
                    None if row[4] is None else str(row[4]),
                )
            )
        return catalog

    def save_catalog(self, catalog: Catalog) -> None:
        """Merge one explicit catalog into persistent storage atomically."""
        combined = self.load_catalog()
        for instrument in catalog.instruments:
            combined.add_instrument(instrument)
        for listing in catalog.listings:
            combined.add_listing(listing)
        for mapping in catalog.provider_symbols:
            combined.map_provider_symbol(mapping)
        instrument_values = [
            (
                item.instrument_id,
                item.kind.value,
                item.display_name,
                item.base_currency,
                item.quote_currency,
            )
            for item in catalog.instruments
        ]
        listing_values = [
            (
                item.listing_id,
                item.instrument_id,
                item.symbol,
                item.exchange,
                item.mic,
                item.currency,
                item.source_timezone,
            )
            for item in catalog.listings
        ]
        mapping_values = [
            (
                item.provider,
                item.kind.value,
                item.symbol,
                item.instrument_id,
                item.listing_id,
            )
            for item in catalog.provider_symbols
        ]
        transaction_started = False
        try:
            self._connection.execute("BEGIN TRANSACTION")
            transaction_started = True
            if instrument_values:
                self._connection.executemany(
                    """
                    INSERT INTO catalog_instruments
                    (instrument_id, kind, display_name, base_currency, quote_currency)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    instrument_values,
                )
            if listing_values:
                self._connection.executemany(
                    """
                    INSERT INTO catalog_listings
                    (listing_id, instrument_id, symbol, exchange, mic, currency, source_timezone)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    listing_values,
                )
            if mapping_values:
                self._connection.executemany(
                    """
                    INSERT INTO catalog_provider_symbols
                    (provider, kind, symbol, instrument_id, listing_id)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT DO NOTHING
                    """,
                    mapping_values,
                )
            self._connection.execute("COMMIT")
            transaction_started = False
        except Exception as error:
            failure = StoreError("could not save instrument catalog")
            if transaction_started:
                self._rollback_after_save_failure(failure)
            raise failure from error

    def save(self, result: object) -> str:
        """Validate and save one supported normalized result."""
        family, scope_key, payload, retrieved_at = _encode_result(result)
        payload_text = json.dumps(
            _snapshot_payload(payload),
            sort_keys=True,
            separators=(",", ":"),
            default=_json,
        )
        metadata_text = json.dumps(
            payload["metadata"],
            sort_keys=True,
            separators=(",", ":"),
            default=_json,
        )
        content_hash = _source_hash(payload)
        snapshot_id = sha256(f"{family}\x1f{scope_key}\x1f{content_hash}".encode()).hexdigest()
        transaction_started = False
        try:
            self._connection.execute("BEGIN TRANSACTION")
            transaction_started = True
            existing = self._connection.execute(
                """
                SELECT snapshot_id FROM acquisition_snapshots
                WHERE family = ? AND scope_key = ? AND content_hash = ?
                """,
                [family, scope_key, content_hash],
            ).fetchone()
            order_row = self._connection.execute(
                "SELECT coalesce(max(saved_order), 0) + 1 FROM acquisition_occurrences"
            ).fetchone()
            if order_row is None:
                raise StoreError("could not allocate acquisition order")
            saved_order = int(order_row[0])
            if existing is None:
                self._connection.execute(
                    """
                    INSERT INTO acquisition_snapshots
                    (snapshot_id, family, scope_key, content_hash, payload, saved_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        snapshot_id,
                        family,
                        scope_key,
                        content_hash,
                        payload_text,
                        saved_order,
                    ],
                )
                self._insert_dataset_rows(snapshot_id, family, payload)
            else:
                snapshot_id = str(existing[0])
            self._connection.execute(
                """
                INSERT INTO acquisition_occurrences
                (saved_order, snapshot_id, retrieved_at, metadata)
                VALUES (?, ?, ?, ?)
                """,
                [saved_order, snapshot_id, retrieved_at, metadata_text],
            )
            self._connection.execute("COMMIT")
            transaction_started = False
        except Exception as error:
            failure = (
                error if isinstance(error, StoreError) else StoreError(f"could not save {family}")
            )
            if transaction_started:
                self._rollback_after_save_failure(failure)
            if failure is error:
                raise
            raise failure from error
        return snapshot_id

    def _rollback_after_save_failure(self, failure: Exception) -> None:
        try:
            self._connection.execute("ROLLBACK")
        except Exception as rollback_error:
            failure.add_note(f"rollback failed: {rollback_error!r}")
            try:
                self._connection.close()
            except Exception as close_error:
                failure.add_note(
                    f"connection cleanup after rollback failure failed: {close_error!r}"
                )
            else:
                failure.add_note("store connection closed after rollback failure")

    def load_bars(
        self, instrument_id: str, *, retrieved_before: datetime | None = None
    ) -> BarSet | None:
        """Load the latest stored bars for one instrument scope."""
        payload = self._latest("bars", instrument_id, retrieved_before)
        result = None if payload is None else _decode_result("bars", payload)
        return result if isinstance(result, BarSet) else None

    def load_options(
        self,
        underlying_instrument_id: str,
        chain_date: date,
        *,
        retrieved_before: datetime | None = None,
    ) -> OptionChain | None:
        """Load the latest stored historical chain for one date."""
        scope = f"{underlying_instrument_id}|{chain_date.isoformat()}"
        payload = self._latest("options", scope, retrieved_before)
        result = None if payload is None else _decode_result("options", payload)
        return result if isinstance(result, OptionChain) else None

    def load_quotes(
        self, symbols: tuple[str, ...], *, retrieved_before: datetime | None = None
    ) -> QuoteSet | None:
        """Load the latest stored quote batch for an exact symbol scope."""
        payload = self._latest("quotes", ",".join(symbols), retrieved_before)
        result = None if payload is None else _decode_result("quotes", payload)
        return result if isinstance(result, QuoteSet) else None

    def load_top_of_book(
        self, symbols: tuple[str, ...], *, retrieved_before: datetime | None = None
    ) -> TopOfBookSet | None:
        """Load the latest stored book batch for an exact symbol scope."""
        payload = self._latest("top_of_book", ",".join(symbols), retrieved_before)
        result = None if payload is None else _decode_result("top_of_book", payload)
        return result if isinstance(result, TopOfBookSet) else None

    def load_series(
        self, series_id: str, *, retrieved_before: datetime | None = None
    ) -> SeriesSet | None:
        """Load the latest stored scalar series for one identity."""
        payload = self._latest("series", series_id, retrieved_before)
        result = None if payload is None else _decode_result("series", payload)
        return result if isinstance(result, SeriesSet) else None

    def load_vintage_series(
        self, series_id: str, *, retrieved_before: datetime | None = None
    ) -> VintageSeriesSet | None:
        """Load the latest stored revision history for one series identity."""
        payload = self._latest("vintage_series", series_id, retrieved_before)
        result = None if payload is None else _decode_result("vintage_series", payload)
        return result if isinstance(result, VintageSeriesSet) else None

    def load_vintage_dates(
        self, provider_series: str, *, retrieved_before: datetime | None = None
    ) -> VintageDatesResult | None:
        """Load the latest stored FRED vintage-date result for one provider series."""
        payload = self._latest("vintage_dates", provider_series, retrieved_before)
        result = None if payload is None else _decode_result("vintage_dates", payload)
        return result if isinstance(result, VintageDatesResult) else None

    def load_search(self, query: str) -> InstrumentSearchResult | None:
        """Load the latest stored provider search result."""
        payload = self._latest("search", query, None)
        result = None if payload is None else _decode_result("search", payload)
        return result if isinstance(result, InstrumentSearchResult) else None

    def load_market_status(self) -> MarketStatusResult | None:
        """Load the latest stored provider market status."""
        payload = self._latest("market_status", "all", None)
        result = None if payload is None else _decode_result("market_status", payload)
        return result if isinstance(result, MarketStatusResult) else None

    def load_index_catalog(self) -> IndexCatalogResult | None:
        """Load the latest stored provider index catalog."""
        payload = self._latest("index_catalog", "all", None)
        result = None if payload is None else _decode_result("index_catalog", payload)
        return result if isinstance(result, IndexCatalogResult) else None

    def load_exchange_rate(self, instrument_id: str) -> ExchangeRateQuote | None:
        """Load the latest stored exchange-rate quote."""
        payload = self._latest("exchange_rate", instrument_id, None)
        result = None if payload is None else _decode_result("exchange_rate", payload)
        return result if isinstance(result, ExchangeRateQuote) else None

    def load_commodity_spot(self, series_id: str) -> CommoditySpotQuote | None:
        """Load the latest stored commodity spot quote."""
        payload = self._latest("commodity_spot", series_id, None)
        result = None if payload is None else _decode_result("commodity_spot", payload)
        return result if isinstance(result, CommoditySpotQuote) else None

    def latest_payload(self, family: str, scope_key: str) -> dict[str, Any] | None:
        """Return a copy of the latest stored payload for research diagnostics."""
        return self._latest(family, scope_key, None)

    def list_datasets(self) -> tuple[StoredDataset, ...]:
        """List stored family scopes in deterministic order."""
        rows = self._connection.execute(
            """
            WITH ranked AS (
                SELECT
                    snapshots.family,
                    snapshots.scope_key,
                    snapshots.snapshot_id,
                    occurrences.retrieved_at,
                    occurrences.saved_order,
                    row_number() OVER (
                        PARTITION BY snapshots.family, snapshots.scope_key
                        ORDER BY occurrences.retrieved_at DESC, occurrences.saved_order DESC
                    ) AS latest_order
                FROM acquisition_occurrences AS occurrences
                JOIN acquisition_snapshots AS snapshots
                  ON snapshots.snapshot_id = occurrences.snapshot_id
            )
            SELECT
                family,
                scope_key,
                count(DISTINCT snapshot_id) AS snapshot_count,
                cast(min(retrieved_at) AS VARCHAR) AS first_seen,
                cast(max(retrieved_at) AS VARCHAR) AS last_seen,
                max(CASE WHEN latest_order = 1 THEN snapshot_id END) AS latest_snapshot_id
            FROM ranked
            GROUP BY family, scope_key
            ORDER BY family, scope_key
            """
        ).fetchall()
        return tuple(
            StoredDataset(
                family=str(row[0]),
                scope_key=str(row[1]),
                snapshot_count=int(row[2]),
                first_seen=datetime.fromisoformat(str(row[3])),
                last_seen=datetime.fromisoformat(str(row[4])),
                latest_snapshot_id=str(row[5]),
            )
            for row in rows
        )

    def list_snapshots(self, family: str, scope_key: str) -> tuple[StoredSnapshot, ...]:
        """List exact snapshots for one dataset, newest first."""
        rows = self._connection.execute(
            """
            SELECT
                snapshots.snapshot_id,
                snapshots.family,
                snapshots.scope_key,
                snapshots.content_hash,
                cast(min(occurrences.retrieved_at) AS VARCHAR),
                cast(max(occurrences.retrieved_at) AS VARCHAR),
                snapshots.saved_order,
                max(occurrences.saved_order) AS latest_saved_order
            FROM acquisition_snapshots AS snapshots
            JOIN acquisition_occurrences AS occurrences
              ON occurrences.snapshot_id = snapshots.snapshot_id
            WHERE snapshots.family = ? AND snapshots.scope_key = ?
            GROUP BY
                snapshots.snapshot_id,
                snapshots.family,
                snapshots.scope_key,
                snapshots.content_hash,
                snapshots.saved_order
            ORDER BY max(occurrences.retrieved_at) DESC, latest_saved_order DESC
            """,
            [family, scope_key],
        ).fetchall()
        return tuple(
            StoredSnapshot(
                snapshot_id=str(row[0]),
                family=str(row[1]),
                scope_key=str(row[2]),
                content_hash=str(row[3]),
                first_seen=datetime.fromisoformat(str(row[4])),
                last_seen=datetime.fromisoformat(str(row[5])),
                saved_order=int(row[6]),
            )
            for row in rows
        )

    def load_snapshot(self, snapshot_id: str) -> StoredResult | None:
        """Load and validate one exact acquisition snapshot by identity."""
        row = self._connection.execute(
            """
            SELECT
                snapshots.family,
                snapshots.payload,
                occurrences.metadata,
                cast(occurrences.retrieved_at AS VARCHAR)
            FROM acquisition_snapshots AS snapshots
            JOIN acquisition_occurrences AS occurrences
              ON occurrences.snapshot_id = snapshots.snapshot_id
            WHERE snapshots.snapshot_id = ?
            ORDER BY occurrences.retrieved_at, occurrences.saved_order
            LIMIT 1
            """,
            [snapshot_id],
        ).fetchone()
        if row is None:
            return None
        result = _decode_result(
            str(row[0]),
            _occurrence_payload(str(row[1]), str(row[2]), str(row[3])),
        )
        return cast("StoredResult", result)

    def query_bars(
        self,
        instrument_id: str,
        *,
        interval: str | None = None,
        start: date | datetime | None = None,
        end: date | datetime | None = None,
        retrieved_before: datetime | None = None,
    ) -> pd.DataFrame:
        """Query cumulative bars with latest-observed row revisions and inclusive filters."""
        clauses, parameters = _bar_query_filters(interval, start, end)
        records = self._query_records(
            "bars",
            instrument_id,
            retrieved_before,
            clauses,
            parameters,
        )
        return (
            _frame(records, BAR_DTYPES)
            .sort_values(
                ["instrument_id", "interval", "price_adjustment", "session", "date", "timestamp"]
            )
            .reset_index(drop=True)
        )

    def query_bars_page(
        self,
        instrument_id: str,
        *,
        interval: str | None = None,
        start: date | datetime | None = None,
        end: date | datetime | None = None,
        retrieved_before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> StoredPage:
        """Query one bounded cumulative bar page with an exact filtered total."""
        clauses, parameters = _bar_query_filters(interval, start, end)
        records, total = self._query_page_records(
            "bars",
            instrument_id,
            retrieved_before,
            clauses,
            parameters,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            descending=descending,
        )
        return StoredPage(
            _frame(records, BAR_DTYPES),
            total,
            limit,
            offset,
            sort_by,
            descending,
        )

    def query_series(
        self,
        series_id: str,
        *,
        start_label: str | None = None,
        end_label: str | None = None,
        retrieved_before: datetime | None = None,
    ) -> pd.DataFrame:
        """Query cumulative scalar observations with latest-observed row revisions."""
        clauses, parameters = _series_query_filters(start_label, end_label)
        records = self._query_records(
            "series",
            series_id,
            retrieved_before,
            clauses,
            parameters,
        )
        return (
            _frame(records, SERIES_DTYPES)
            .sort_values(["series_id", "frequency", "maturity", "period_label"])
            .reset_index(drop=True)
        )

    def query_series_page(
        self,
        series_id: str,
        *,
        start_label: str | None = None,
        end_label: str | None = None,
        retrieved_before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> StoredPage:
        """Query one bounded cumulative scalar-series page with an exact filtered total."""
        clauses, parameters = _series_query_filters(start_label, end_label)
        records, total = self._query_page_records(
            "series",
            series_id,
            retrieved_before,
            clauses,
            parameters,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            descending=descending,
        )
        return StoredPage(
            _frame(records, SERIES_DTYPES),
            total,
            limit,
            offset,
            sort_by,
            descending,
        )

    def query_vintage_series(
        self,
        series_id: str,
        *,
        start_label: str | None = None,
        end_label: str | None = None,
        available_on: date | None = None,
        retrieved_before: datetime | None = None,
    ) -> pd.DataFrame:
        """Query cumulative provider vintages with latest-observed row revisions."""
        clauses, parameters = _vintage_query_filters(start_label, end_label, available_on)
        records = self._query_records(
            "vintage_series",
            series_id,
            retrieved_before,
            clauses,
            parameters,
        )
        return (
            _frame(records, VINTAGE_SERIES_DTYPES)
            .sort_values(["series_id", "frequency", "maturity", "period_label", "available_from"])
            .reset_index(drop=True)
        )

    def query_vintage_series_page(
        self,
        series_id: str,
        *,
        start_label: str | None = None,
        end_label: str | None = None,
        available_on: date | None = None,
        retrieved_before: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        descending: bool = False,
    ) -> StoredPage:
        """Query one bounded cumulative vintage page with an exact filtered total."""
        clauses, parameters = _vintage_query_filters(start_label, end_label, available_on)
        records, total = self._query_page_records(
            "vintage_series",
            series_id,
            retrieved_before,
            clauses,
            parameters,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            descending=descending,
        )
        return StoredPage(
            _frame(records, VINTAGE_SERIES_DTYPES),
            total,
            limit,
            offset,
            sort_by,
            descending,
        )

    def query_vintage_dates(
        self,
        provider_series: str,
        *,
        retrieved_before: datetime | None = None,
    ) -> pd.DataFrame:
        """Query cumulative release dates through one retrieval-time cutoff."""
        records = self._query_records(
            "vintage_dates",
            provider_series,
            retrieved_before,
            [],
            [],
        )
        dtypes = _DATASET_TABLES["vintage_dates"].dtypes
        return _frame(records, dtypes).sort_values("vintage_date").reset_index(drop=True)

    def query_quote_history(
        self,
        *,
        provider: str | None = None,
        symbol: str | None = None,
        observed_start: datetime | None = None,
        observed_end: datetime | None = None,
        retrieved_start: datetime | None = None,
        retrieved_end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return chronological retained quote revisions and recurrence counts."""
        return self._query_observation_history(
            "quotes",
            provider=provider,
            symbol=symbol,
            observed_start=observed_start,
            observed_end=observed_end,
            retrieved_start=retrieved_start,
            retrieved_end=retrieved_end,
        )

    def query_top_of_book_history(
        self,
        *,
        provider: str | None = None,
        symbol: str | None = None,
        observed_start: datetime | None = None,
        observed_end: datetime | None = None,
        retrieved_start: datetime | None = None,
        retrieved_end: datetime | None = None,
    ) -> pd.DataFrame:
        """Return chronological retained top-of-book revisions and recurrence counts."""
        return self._query_observation_history(
            "top_of_book",
            provider=provider,
            symbol=symbol,
            observed_start=observed_start,
            observed_end=observed_end,
            retrieved_start=retrieved_start,
            retrieved_end=retrieved_end,
        )

    def query_option_snapshots(
        self,
        underlying_instrument_id: str,
        *,
        provider: str | None = None,
        chain_date: date | None = None,
        expiration: date | None = None,
        strike: float | None = None,
        option_type: str | None = None,
        retrieved_before: datetime | None = None,
    ) -> tuple[StoredOptionSnapshot, ...]:
        """Return filtered option-chain occurrences in retrieval order."""
        if retrieved_before is not None and retrieved_before.tzinfo is None:
            raise ValueError("retrieved_before must be timezone-aware")
        if option_type not in {None, "call", "put"}:
            raise ValueError("option_type must be call or put")
        if strike is not None:
            if isinstance(strike, bool) or not isinstance(strike, Real):
                raise TypeError("strike must be a real number")
            if not isfinite(strike) or strike <= 0:
                raise ValueError("strike must be positive and finite")
        query = """
            SELECT snapshots.snapshot_id, snapshots.payload, occurrences.metadata,
                   cast(occurrences.retrieved_at AS VARCHAR), occurrences.saved_order
            FROM acquisition_snapshots AS snapshots
            JOIN acquisition_occurrences AS occurrences
              ON occurrences.snapshot_id = snapshots.snapshot_id
            WHERE snapshots.family = 'options'
              AND starts_with(snapshots.scope_key, ?)
        """
        parameters: list[object] = [f"{underlying_instrument_id}|"]
        if retrieved_before is not None:
            query += " AND occurrences.retrieved_at <= ?"
            parameters.append(retrieved_before)
        query += " ORDER BY occurrences.retrieved_at, occurrences.saved_order"
        rows = self._connection.execute(query, parameters).fetchall()
        snapshots: list[StoredOptionSnapshot] = []
        for row in rows:
            retrieved_at = datetime.fromisoformat(str(row[3]))
            decoded = _decode_result(
                "options",
                _occurrence_payload(str(row[1]), str(row[2]), str(row[3])),
            )
            if not isinstance(decoded, OptionChain):
                continue
            if provider is not None and decoded.metadata.provider != provider:
                continue
            if chain_date is not None and decoded.chain_date != chain_date:
                continue
            contracts = decoded.contracts
            if expiration is not None:
                contracts = contracts.loc[contracts["expiration"].dt.date == expiration]
            if strike is not None:
                contracts = contracts.loc[contracts["strike"] == float(strike)]
            if option_type is not None:
                contracts = contracts.loc[contracts["option_type"] == option_type]
            contracts = contracts.reset_index(drop=True)
            keys = set(contracts[["provider", "contract_id"]].itertuples(index=False, name=None))
            observations = decoded.observations.loc[
                [
                    (row_provider, contract_id) in keys
                    for row_provider, contract_id in decoded.observations[
                        ["provider", "contract_id"]
                    ].itertuples(index=False, name=None)
                ]
            ].reset_index(drop=True)
            filtered = OptionChain(
                decoded.underlying_instrument_id,
                decoded.provider_symbol,
                decoded.chain_date,
                contracts,
                observations,
                decoded.metadata,
            )
            snapshots.append(StoredOptionSnapshot(str(row[0]), retrieved_at, filtered))
        return tuple(snapshots)

    def diff_snapshots(self, before_snapshot_id: str, after_snapshot_id: str) -> SnapshotDiff:
        """Compare two exact snapshots without exposing serialized payloads."""
        before = self._snapshot_for_diff(before_snapshot_id)
        after = self._snapshot_for_diff(after_snapshot_id)
        if before is None:
            raise ValueError(f"snapshot does not exist: {before_snapshot_id}")
        if after is None:
            raise ValueError(f"snapshot does not exist: {after_snapshot_id}")
        before_family, before_result = before
        after_family, after_result = after
        if before_family != after_family:
            raise ValueError("snapshots must belong to the same family")
        before_rows = _diff_rows(before_result)
        after_rows = _diff_rows(after_result)
        before_keys = set(before_rows)
        after_keys = set(after_rows)
        added = tuple(after_rows[key] for key in sorted(after_keys - before_keys, key=repr))
        removed = tuple(before_rows[key] for key in sorted(before_keys - after_keys, key=repr))
        changed: list[SnapshotValueChange] = []
        for key in sorted(before_keys & after_keys, key=repr):
            old = dict(before_rows[key].values)
            new = dict(after_rows[key].values)
            for field in sorted(old.keys() | new.keys()):
                if not _values_equal(old.get(field), new.get(field)):
                    changed.append(
                        SnapshotValueChange(key[0], key[1], field, old.get(field), new.get(field))
                    )
        before_metadata = _metadata_diff_values(before_result.metadata)
        after_metadata = _metadata_diff_values(after_result.metadata)
        metadata_changes = tuple(
            SnapshotValueChange(
                "metadata", (), field, before_metadata.get(field), after_metadata.get(field)
            )
            for field in sorted(before_metadata.keys() | after_metadata.keys())
            if not _values_equal(before_metadata.get(field), after_metadata.get(field))
        )
        return SnapshotDiff(
            before_family,
            before_snapshot_id,
            after_snapshot_id,
            metadata_changes,
            before_result.metadata.diagnostics,
            after_result.metadata.diagnostics,
            added,
            removed,
            tuple(changed),
        )

    def _query_observation_history(
        self,
        family: str,
        *,
        provider: str | None,
        symbol: str | None,
        observed_start: datetime | None,
        observed_end: datetime | None,
        retrieved_start: datetime | None,
        retrieved_end: datetime | None,
    ) -> pd.DataFrame:
        _datetime_bounds(observed_start, observed_end, "observed")
        _datetime_bounds(retrieved_start, retrieved_end, "retrieved")
        table = _DATASET_TABLES[family]
        columns = ", ".join(
            (
                f'cast(rows."{name}" AS VARCHAR)'
                if dtype == "datetime64[ns, UTC]"
                else f'rows."{name}"'
            )
            for name, dtype in table.dtypes.items()
            if name != "retrieved_at"
        )
        query = f"""
            SELECT {columns}, cast(occurrences.retrieved_at AS VARCHAR)
            FROM {table.name} AS rows
            JOIN acquisition_snapshots AS snapshots
              ON snapshots.snapshot_id = rows.snapshot_id
            JOIN acquisition_occurrences AS occurrences
              ON occurrences.snapshot_id = snapshots.snapshot_id
            WHERE snapshots.family = ?
        """
        parameters: list[object] = [family]
        if provider is not None:
            query += ' AND rows."provider" = ?'
            parameters.append(provider)
        if symbol is not None:
            query += ' AND rows."provider_symbol" = ?'
            parameters.append(symbol)
        if observed_start is not None:
            query += ' AND rows."observed_at" >= ?'
            parameters.append(observed_start)
        if observed_end is not None:
            query += ' AND rows."observed_at" <= ?'
            parameters.append(observed_end)
        if retrieved_start is not None:
            query += " AND occurrences.retrieved_at >= ?"
            parameters.append(retrieved_start)
        if retrieved_end is not None:
            query += " AND occurrences.retrieved_at <= ?"
            parameters.append(retrieved_end)
        names = tuple(name for name in table.dtypes if name != "retrieved_at")
        grouped: dict[str, tuple[dict[str, object], set[datetime]]] = {}
        for raw in self._connection.execute(query, parameters).fetchall():
            values = dict(zip(names, raw[:-1], strict=True))
            encoded = json.dumps(values, sort_keys=True, separators=(",", ":"), default=_json)
            revision_id = sha256(f"{family}\x1f{encoded}".encode()).hexdigest()
            retrieved_at = datetime.fromisoformat(str(raw[-1]))
            if revision_id not in grouped:
                grouped[revision_id] = values, set()
            grouped[revision_id][1].add(retrieved_at)
        history_dtypes = QUOTE_HISTORY_DTYPES if family == "quotes" else TOP_OF_BOOK_HISTORY_DTYPES
        records: list[dict[str, object]] = []
        for revision_id, (values, occurrences) in grouped.items():
            records.append(
                {
                    "revision_id": revision_id,
                    **values,
                    "first_retrieved_at": min(occurrences),
                    "last_retrieved_at": max(occurrences),
                    "retrieval_count": len(occurrences),
                }
            )
        frame = _frame(cast("list[dict[str, Any]]", records), history_dtypes)
        return frame.sort_values(
            ["provider", "provider_symbol", "observed_at", "first_retrieved_at"],
            na_position="last",
        ).reset_index(drop=True)

    def _snapshot_for_diff(self, snapshot_id: str) -> tuple[str, StoredResult] | None:
        row = self._connection.execute(
            "SELECT family FROM acquisition_snapshots WHERE snapshot_id = ?",
            [snapshot_id],
        ).fetchone()
        if row is None:
            return None
        result = self.load_snapshot(snapshot_id)
        return None if result is None else (str(row[0]), result)

    def _latest(
        self,
        family: str,
        scope_key: str,
        retrieved_before: datetime | None,
    ) -> dict[str, Any] | None:
        if retrieved_before is not None and retrieved_before.tzinfo is None:
            raise ValueError("retrieved_before must be timezone-aware")
        query = """
            SELECT
                snapshots.payload,
                occurrences.metadata,
                cast(occurrences.retrieved_at AS VARCHAR)
            FROM acquisition_occurrences AS occurrences
            JOIN acquisition_snapshots AS snapshots
              ON snapshots.snapshot_id = occurrences.snapshot_id
            WHERE snapshots.family = ? AND snapshots.scope_key = ?
        """
        parameters: list[object] = [family, scope_key]
        if retrieved_before is not None:
            query += " AND occurrences.retrieved_at <= ?"
            parameters.append(retrieved_before)
        query += " ORDER BY occurrences.retrieved_at DESC, occurrences.saved_order DESC LIMIT 1"
        row = self._connection.execute(query, parameters).fetchone()
        return None if row is None else _occurrence_payload(str(row[0]), str(row[1]), str(row[2]))

    def _query_records(
        self,
        family: str,
        scope_key: str,
        retrieved_before: datetime | None,
        clauses: list[str],
        filter_parameters: list[object],
    ) -> list[dict[str, Any]]:
        table = _DATASET_TABLES[family]
        if retrieved_before is not None and retrieved_before.tzinfo is None:
            raise ValueError("retrieved_before must be timezone-aware")
        snapshot_filter = ""
        parameters: list[object] = [family, scope_key]
        if retrieved_before is not None:
            snapshot_filter = "AND occurrences.retrieved_at <= ?"
            parameters.append(retrieved_before)
        filters = "" if not clauses else " AND " + " AND ".join(clauses)
        partition = ", ".join(f'rows."{field}"' for field in table.row_key)
        columns = ", ".join(
            (
                "cast(record.occurrence_retrieved_at AS VARCHAR)"
                if field == "retrieved_at"
                else f'cast(record."{field}" AS VARCHAR)'
                if dtype == "datetime64[ns, UTC]"
                else f'record."{field}"'
            )
            for field, dtype in table.dtypes.items()
        )
        query = f"""
            WITH ranked AS (
                SELECT
                    rows.*,
                    occurrences.retrieved_at AS occurrence_retrieved_at,
                    row_number() OVER (
                        PARTITION BY {partition}
                        ORDER BY occurrences.retrieved_at DESC, occurrences.saved_order DESC
                    ) AS revision_order
                FROM {table.name} AS rows
                JOIN acquisition_snapshots AS snapshots
                  ON snapshots.snapshot_id = rows.snapshot_id
                JOIN acquisition_occurrences AS occurrences
                  ON occurrences.snapshot_id = snapshots.snapshot_id
                WHERE snapshots.family = ?
                  AND snapshots.scope_key = ?
                  {snapshot_filter}
            )
            SELECT {columns}
            FROM ranked AS record
            WHERE record.revision_order = 1 {filters}
        """
        rows = self._connection.execute(query, [*parameters, *filter_parameters]).fetchall()
        names = tuple(table.dtypes)
        return [dict(zip(names, row, strict=True)) for row in rows]

    def _query_page_records(
        self,
        family: str,
        scope_key: str,
        retrieved_before: datetime | None,
        clauses: list[str],
        filter_parameters: list[object],
        *,
        limit: int,
        offset: int,
        sort_by: str | None,
        descending: bool,
    ) -> tuple[list[dict[str, Any]], int]:
        table = _DATASET_TABLES[family]
        _validate_page_request(table, limit, offset, sort_by, descending)
        if retrieved_before is not None and retrieved_before.tzinfo is None:
            raise ValueError("retrieved_before must be timezone-aware")
        snapshot_filter = ""
        parameters: list[object] = [family, scope_key]
        if retrieved_before is not None:
            snapshot_filter = "AND occurrences.retrieved_at <= ?"
            parameters.append(retrieved_before)
        filters = "" if not clauses else " AND " + " AND ".join(clauses)
        partition = ", ".join(f'rows."{field}"' for field in table.row_key)
        ranked = f"""
            WITH ranked AS (
                SELECT
                    rows.*,
                    occurrences.retrieved_at AS occurrence_retrieved_at,
                    row_number() OVER (
                        PARTITION BY {partition}
                        ORDER BY occurrences.retrieved_at DESC, occurrences.saved_order DESC
                    ) AS revision_order
                FROM {table.name} AS rows
                JOIN acquisition_snapshots AS snapshots
                  ON snapshots.snapshot_id = rows.snapshot_id
                JOIN acquisition_occurrences AS occurrences
                  ON occurrences.snapshot_id = snapshots.snapshot_id
                WHERE snapshots.family = ?
                  AND snapshots.scope_key = ?
                  {snapshot_filter}
            )
        """
        query_parameters = [*parameters, *filter_parameters]
        count_row = self._connection.execute(
            f"""
                {ranked}
                SELECT count(*)
                FROM ranked AS record
                WHERE record.revision_order = 1 {filters}
            """,
            query_parameters,
        ).fetchone()
        if count_row is None:
            raise RuntimeError("paged query did not return a total count")
        total = int(count_row[0])
        columns = ", ".join(
            (
                "cast(record.occurrence_retrieved_at AS VARCHAR)"
                if field == "retrieved_at"
                else f'cast(record."{field}" AS VARCHAR)'
                if dtype == "datetime64[ns, UTC]"
                else f'record."{field}"'
            )
            for field, dtype in table.dtypes.items()
        )
        ordering = _page_ordering(table, sort_by, descending)
        rows = self._connection.execute(
            f"""
                {ranked}
                SELECT {columns}
                FROM ranked AS record
                WHERE record.revision_order = 1 {filters}
                ORDER BY {ordering}
                LIMIT ? OFFSET ?
            """,
            [*query_parameters, limit, offset],
        ).fetchall()
        names = tuple(table.dtypes)
        return [dict(zip(names, row, strict=True)) for row in rows], total

    def _insert_dataset_rows(
        self,
        snapshot_id: str,
        family: str,
        payload: dict[str, Any],
    ) -> None:
        table_families = (
            ("option_contracts", "option_observations") if family == "options" else (family,)
        )
        for table_family in table_families:
            table = _DATASET_TABLES.get(table_family)
            if table is None:
                continue
            records = cast("list[dict[str, Any]]", payload[table.frame_key])
            values: list[tuple[object, ...]] = []
            for record in records:
                row_key = json.dumps(
                    [record[field] for field in table.row_key],
                    separators=(",", ":"),
                    default=_json,
                )
                values.append(
                    (
                        snapshot_id,
                        row_key,
                        *(_database_value(record[field]) for field in table.dtypes),
                    )
                )
            if values:
                columns = ", ".join(f'"{field}"' for field in table.dtypes)
                placeholders = ", ".join("?" for _ in range(len(table.dtypes) + 2))
                self._connection.executemany(
                    f"""
                    INSERT INTO {table.name}
                    (snapshot_id, row_key, {columns})
                    VALUES ({placeholders})
                    """,
                    values,
                )


def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_version VALUES (?)", [STORE_SCHEMA_VERSION])
    connection.execute(
        """
        CREATE TABLE store_migration (
            source_store_sha256 VARCHAR PRIMARY KEY,
            source_schema_version INTEGER NOT NULL,
            target_schema_version INTEGER NOT NULL,
            source_snapshot_count BIGINT NOT NULL,
            target_snapshot_count BIGINT NOT NULL,
            occurrence_count BIGINT NOT NULL,
            snapshots VARCHAR NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_snapshots (
            snapshot_id VARCHAR PRIMARY KEY,
            family VARCHAR NOT NULL,
            scope_key VARCHAR NOT NULL,
            content_hash VARCHAR NOT NULL,
            payload VARCHAR NOT NULL,
            saved_order BIGINT NOT NULL UNIQUE,
            UNIQUE (family, scope_key, content_hash)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE acquisition_occurrences (
            saved_order BIGINT PRIMARY KEY,
            snapshot_id VARCHAR NOT NULL,
            retrieved_at TIMESTAMPTZ NOT NULL,
            metadata VARCHAR NOT NULL,
            FOREIGN KEY (snapshot_id) REFERENCES acquisition_snapshots(snapshot_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog_instruments (
            instrument_id VARCHAR PRIMARY KEY,
            kind VARCHAR NOT NULL,
            display_name VARCHAR NOT NULL,
            base_currency VARCHAR,
            quote_currency VARCHAR
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog_listings (
            listing_id VARCHAR PRIMARY KEY,
            instrument_id VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            exchange VARCHAR,
            mic VARCHAR,
            currency VARCHAR,
            source_timezone VARCHAR,
            FOREIGN KEY (instrument_id) REFERENCES catalog_instruments(instrument_id)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE catalog_provider_symbols (
            provider VARCHAR NOT NULL,
            kind VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            instrument_id VARCHAR NOT NULL,
            listing_id VARCHAR,
            PRIMARY KEY (provider, kind, symbol),
            FOREIGN KEY (instrument_id) REFERENCES catalog_instruments(instrument_id),
            FOREIGN KEY (listing_id) REFERENCES catalog_listings(listing_id)
        )
        """
    )
    for table in _DATASET_TABLES.values():
        fields = ",\n".join(
            f'"{name}" {_duckdb_type(dtype)}' for name, dtype in table.dtypes.items()
        )
        connection.execute(
            f"""
            CREATE TABLE {table.name} (
                snapshot_id VARCHAR NOT NULL,
                row_key VARCHAR NOT NULL,
                {fields},
                PRIMARY KEY (snapshot_id, row_key),
                FOREIGN KEY (snapshot_id) REFERENCES acquisition_snapshots(snapshot_id)
            )
            """
        )


def _encode_result(result: object) -> tuple[str, str, dict[str, Any], datetime]:
    result = _validated_result(result)
    metadata = getattr(result, "metadata", None)
    if not isinstance(metadata, ResultMetadata):
        raise TypeError("result is not a supported normalized acquisition result")
    common = {"metadata": _metadata_to_dict(metadata)}
    if isinstance(result, BarSet):
        payload = {
            **common,
            "instrument": asdict(result.instrument),
            "frame": _records(result.frame),
        }
        return "bars", result.instrument.instrument_id, payload, metadata.retrieved_at
    if isinstance(result, QuoteSet):
        scope = ",".join(result.frame["provider_symbol"].astype(str))
        return "quotes", scope, {**common, "frame": _records(result.frame)}, metadata.retrieved_at
    if isinstance(result, TopOfBookSet):
        scope = ",".join(result.frame["provider_symbol"].astype(str))
        payload = {**common, "frame": _records(result.frame)}
        return "top_of_book", scope, payload, metadata.retrieved_at
    if isinstance(result, OptionChain):
        scope = f"{result.underlying_instrument_id}|{result.chain_date.isoformat()}"
        payload = {
            **common,
            "underlying_instrument_id": result.underlying_instrument_id,
            "provider_symbol": result.provider_symbol,
            "chain_date": result.chain_date,
            "contracts": _records(result.contracts),
            "observations": _records(result.observations),
        }
        return "options", scope, payload, metadata.retrieved_at
    if isinstance(result, SeriesSet):
        payload = {
            **common,
            "definition": asdict(result.definition),
            "frame": _records(result.frame),
        }
        return "series", result.definition.series_id, payload, metadata.retrieved_at
    if isinstance(result, VintageSeriesSet):
        payload = {
            **common,
            "definition": asdict(result.definition),
            "frame": _records(result.frame),
        }
        return "vintage_series", result.definition.series_id, payload, metadata.retrieved_at
    if isinstance(result, VintageDatesResult):
        payload = {
            **common,
            "provider_series": result.provider_series,
            "frame": [
                {
                    "provider_series": result.provider_series,
                    "vintage_date": pd.Timestamp(item),
                    "retrieved_at": metadata.retrieved_at,
                }
                for item in result.dates
            ],
        }
        return "vintage_dates", result.provider_series, payload, metadata.retrieved_at
    if isinstance(result, ExchangeRateQuote):
        payload = {**common, "quote": _exchange_quote_dict(result)}
        return "exchange_rate", result.instrument_id, payload, metadata.retrieved_at
    if isinstance(result, CommoditySpotQuote):
        payload = {**common, "quote": _commodity_quote_dict(result)}
        return "commodity_spot", result.series_id, payload, metadata.retrieved_at
    if isinstance(result, InstrumentSearchResult):
        payload = {**common, "query": result.query, "frame": _records(result.frame)}
        return "search", result.query, payload, metadata.retrieved_at
    if isinstance(result, MarketStatusResult):
        payload = {**common, "frame": _records(result.frame)}
        return "market_status", "all", payload, metadata.retrieved_at
    payload = {**common, "frame": _records(result.frame)}
    return "index_catalog", "all", payload, metadata.retrieved_at


def _validated_result(result: object) -> StoredResult:
    """Revalidate mutable normalized frames at the storage boundary."""
    if isinstance(result, BarSet):
        return BarSet(result.instrument, result.frame, result.metadata)
    if isinstance(result, QuoteSet):
        return QuoteSet(result.frame, result.metadata)
    if isinstance(result, TopOfBookSet):
        return TopOfBookSet(result.frame, result.metadata)
    if isinstance(result, OptionChain):
        return OptionChain(
            result.underlying_instrument_id,
            result.provider_symbol,
            result.chain_date,
            result.contracts,
            result.observations,
            result.metadata,
        )
    if isinstance(result, SeriesSet):
        return SeriesSet(result.definition, result.frame, result.metadata)
    if isinstance(result, VintageSeriesSet):
        return VintageSeriesSet(result.definition, result.frame, result.metadata)
    if isinstance(result, VintageDatesResult):
        return VintageDatesResult(result.provider_series, result.dates, result.metadata)
    if isinstance(result, ExchangeRateQuote):
        return ExchangeRateQuote(
            result.instrument_id,
            result.provider,
            result.base_currency,
            result.quote_currency,
            result.exchange_rate,
            result.bid,
            result.ask,
            result.provider_timestamp,
            result.provider_timezone,
            result.retrieved_at,
            result.metadata,
        )
    if isinstance(result, CommoditySpotQuote):
        return CommoditySpotQuote(
            result.series_id,
            result.provider,
            result.metal,
            result.value,
            result.unit,
            result.provider_timestamp,
            result.retrieved_at,
            result.metadata,
        )
    if isinstance(result, InstrumentSearchResult):
        return InstrumentSearchResult(result.query, result.frame, result.metadata)
    if isinstance(result, MarketStatusResult):
        return MarketStatusResult(result.frame, result.metadata)
    if isinstance(result, IndexCatalogResult):
        return IndexCatalogResult(result.frame, result.metadata)
    raise TypeError("result is not a supported normalized acquisition result")


def _decode_result(family: str, payload: dict[str, Any]) -> object:
    metadata = _metadata_from_dict(payload["metadata"])
    if family == "bars":
        raw = payload["instrument"]
        instrument = Instrument(
            raw["instrument_id"],
            InstrumentKind(raw["kind"]),
            raw["display_name"],
            raw["base_currency"],
            raw["quote_currency"],
        )
        return BarSet(instrument, _frame(payload["frame"], BAR_DTYPES), metadata)
    if family == "quotes":
        return QuoteSet(_frame(payload["frame"], QUOTE_DTYPES), metadata)
    if family == "top_of_book":
        return TopOfBookSet(_frame(payload["frame"], TOP_OF_BOOK_DTYPES), metadata)
    if family == "options":
        return OptionChain(
            payload["underlying_instrument_id"],
            payload["provider_symbol"],
            date.fromisoformat(payload["chain_date"]),
            _frame(payload["contracts"], OPTION_CONTRACT_DTYPES),
            _frame(payload["observations"], OPTION_OBSERVATION_DTYPES),
            metadata,
        )
    if family == "series":
        raw = payload["definition"]
        definition = SeriesDefinition(
            raw["series_id"],
            SeriesKind(raw["kind"]),
            raw["display_name"],
            raw["provider"],
            raw["provider_series"],
            raw["frequency"],
            raw["unit"],
            raw["geography"],
            raw["seasonal_adjustment"],
            raw["maturity"],
        )
        return SeriesSet(definition, _frame(payload["frame"], SERIES_DTYPES), metadata)
    if family == "vintage_series":
        raw = payload["definition"]
        definition = SeriesDefinition(
            raw["series_id"],
            SeriesKind(raw["kind"]),
            raw["display_name"],
            raw["provider"],
            raw["provider_series"],
            raw["frequency"],
            raw["unit"],
            raw["geography"],
            raw["seasonal_adjustment"],
            raw["maturity"],
        )
        return VintageSeriesSet(
            definition,
            _frame(payload["frame"], VINTAGE_SERIES_DTYPES),
            metadata,
        )
    if family == "vintage_dates":
        return VintageDatesResult(
            payload["provider_series"],
            tuple(pd.Timestamp(item["vintage_date"]).date() for item in payload["frame"]),
            metadata,
        )
    if family == "exchange_rate":
        raw = payload["quote"]
        provider_timestamp = raw["provider_timestamp"]
        return ExchangeRateQuote(
            raw["instrument_id"],
            raw["provider"],
            raw["base_currency"],
            raw["quote_currency"],
            float(raw["exchange_rate"]),
            raw["bid"],
            raw["ask"],
            None if provider_timestamp is None else datetime.fromisoformat(provider_timestamp),
            raw["provider_timezone"],
            datetime.fromisoformat(raw["retrieved_at"]),
            metadata,
        )
    if family == "commodity_spot":
        raw = payload["quote"]
        provider_timestamp = raw["provider_timestamp"]
        return CommoditySpotQuote(
            raw["series_id"],
            raw["provider"],
            raw["metal"],
            float(raw["value"]),
            raw["unit"],
            None if provider_timestamp is None else datetime.fromisoformat(provider_timestamp),
            datetime.fromisoformat(raw["retrieved_at"]),
            metadata,
        )
    if family == "search":
        frame = _frame(payload["frame"], SEARCH_DTYPES)
        return InstrumentSearchResult(payload["query"], frame, metadata)
    if family == "market_status":
        return MarketStatusResult(_frame(payload["frame"], MARKET_STATUS_DTYPES), metadata)
    if family == "index_catalog":
        return IndexCatalogResult(_frame(payload["frame"], INDEX_CATALOG_DTYPES), metadata)
    raise StoreError(f"unsupported stored family: {family}")


def _metadata_to_dict(metadata: ResultMetadata) -> dict[str, Any]:
    return {
        "provider": metadata.provider,
        "operation": metadata.operation,
        "request_parameters": thaw_portable_mapping(metadata.request_parameters),
        "retrieved_at": metadata.retrieved_at,
        "provider_as_of": metadata.provider_as_of,
        "entitlement": metadata.entitlement.value,
        "cache_status": metadata.cache_status.value,
        "schema_version": metadata.schema_version,
        "diagnostics": [_diagnostic_to_dict(item) for item in metadata.diagnostics],
    }


def _exchange_quote_dict(result: ExchangeRateQuote) -> dict[str, Any]:
    return {
        "instrument_id": result.instrument_id,
        "provider": result.provider,
        "base_currency": result.base_currency,
        "quote_currency": result.quote_currency,
        "exchange_rate": result.exchange_rate,
        "bid": result.bid,
        "ask": result.ask,
        "provider_timestamp": result.provider_timestamp,
        "provider_timezone": result.provider_timezone,
        "retrieved_at": result.retrieved_at,
    }


def _diagnostic_to_dict(diagnostic: SchemaDiagnostic) -> dict[str, Any]:
    return {
        key: value
        for key, value in asdict(diagnostic).items()
        if value is not None
    }


def _commodity_quote_dict(result: CommoditySpotQuote) -> dict[str, Any]:
    return {
        "series_id": result.series_id,
        "provider": result.provider,
        "metal": result.metal,
        "value": result.value,
        "unit": result.unit,
        "provider_timestamp": result.provider_timestamp,
        "retrieved_at": result.retrieved_at,
    }


def _metadata_from_dict(raw: dict[str, Any]) -> ResultMetadata:
    provider_as_of = raw["provider_as_of"]
    return ResultMetadata(
        provider=raw["provider"],
        operation=raw["operation"],
        request_parameters=dict(raw["request_parameters"]),
        retrieved_at=datetime.fromisoformat(raw["retrieved_at"]),
        provider_as_of=None if provider_as_of is None else datetime.fromisoformat(provider_as_of),
        entitlement=EntitlementMode(raw["entitlement"]),
        cache_status=CacheStatus(raw["cache_status"]),
        schema_version=int(raw["schema_version"]),
        diagnostics=tuple(SchemaDiagnostic(**item) for item in raw["diagnostics"]),
    )


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return cast("list[dict[str, Any]]", frame.to_dict(orient="records"))


def _frame(records: list[dict[str, Any]], dtypes: dict[str, str]) -> pd.DataFrame:
    values = {name: [record.get(name) for record in records] for name in dtypes}
    return typed_frame(values, dtypes)


def _database_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    return value


def _duckdb_type(dtype: str) -> str:
    types = {
        "string": "VARCHAR",
        "datetime64[ns]": "DATE",
        "datetime64[ns, UTC]": "TIMESTAMPTZ",
        "float64": "DOUBLE",
        "Float64": "DOUBLE",
        "bool": "BOOLEAN",
        "Int64": "BIGINT",
    }
    try:
        return types[dtype]
    except KeyError as error:
        raise ValueError(f"unsupported stored dtype: {dtype}") from error


def _temporal_bounds(
    start: date | datetime | None,
    end: date | datetime | None,
) -> tuple[date | datetime | None, date | datetime | None]:
    if start is not None and end is not None:
        if isinstance(start, datetime) != isinstance(end, datetime):
            raise TypeError("start and end must use the same temporal type")
        if start > end:
            raise ValueError("start must not follow end")

    for value in (start, end):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("datetime bounds must be timezone-aware")
    return start, end


def _datetime_bounds(
    start: datetime | None,
    end: datetime | None,
    name: str,
) -> None:
    if start is not None and start.tzinfo is None:
        raise ValueError(f"{name}_start must be timezone-aware")
    if end is not None and end.tzinfo is None:
        raise ValueError(f"{name}_end must be timezone-aware")
    if start is not None and end is not None and start > end:
        raise ValueError(f"{name}_start must not follow {name}_end")


def _diff_rows(result: StoredResult) -> dict[tuple[str, tuple[object, ...]], SnapshotRow]:
    frames: tuple[tuple[str, pd.DataFrame, tuple[str, ...]], ...]
    header: dict[str, Any] | None = None
    if isinstance(result, BarSet):
        frames = (("frame", result.frame, _DATASET_TABLES["bars"].row_key),)
        header = asdict(result.instrument)
    elif isinstance(result, QuoteSet):
        frames = (("frame", result.frame, _DATASET_TABLES["quotes"].row_key),)
    elif isinstance(result, TopOfBookSet):
        frames = (("frame", result.frame, _DATASET_TABLES["top_of_book"].row_key),)
    elif isinstance(result, OptionChain):
        frames = (
            ("contracts", result.contracts, _DATASET_TABLES["option_contracts"].row_key),
            (
                "observations",
                result.observations,
                _DATASET_TABLES["option_observations"].row_key,
            ),
        )
        header = {
            "underlying_instrument_id": result.underlying_instrument_id,
            "provider_symbol": result.provider_symbol,
            "chain_date": result.chain_date,
        }
    elif isinstance(result, SeriesSet):
        frames = (("frame", result.frame, _DATASET_TABLES["series"].row_key),)
        header = asdict(result.definition)
    elif isinstance(result, VintageSeriesSet):
        frames = (("frame", result.frame, _DATASET_TABLES["vintage_series"].row_key),)
        header = asdict(result.definition)
    elif isinstance(result, VintageDatesResult):
        frame = pd.DataFrame(
            {
                "provider_series": [result.provider_series] * len(result.dates),
                "vintage_date": result.dates,
            }
        )
        frames = (("dates", frame, ("provider_series", "vintage_date")),)
        header = {"provider_series": result.provider_series}
    elif isinstance(result, InstrumentSearchResult):
        frames = (("frame", result.frame, ("provider_symbol",)),)
        header = {"query": result.query}
    elif isinstance(result, MarketStatusResult):
        frames = (("frame", result.frame, ("market_type", "region")),)
    elif isinstance(result, IndexCatalogResult):
        frames = (("frame", result.frame, ("provider_symbol",)),)
    else:
        values = {
            field: getattr(result, field)
            for field in (
                (
                    "instrument_id",
                    "provider",
                    "base_currency",
                    "quote_currency",
                    "exchange_rate",
                    "bid",
                    "ask",
                    "provider_timestamp",
                    "provider_timezone",
                    "retrieved_at",
                )
                if isinstance(result, ExchangeRateQuote)
                else (
                    "series_id",
                    "provider",
                    "metal",
                    "value",
                    "unit",
                    "provider_timestamp",
                    "retrieved_at",
                )
            )
        }
        identity_name = "instrument_id" if isinstance(result, ExchangeRateQuote) else "series_id"
        row = _snapshot_row("details", (values[identity_name],), values)
        return {("details", row.identity): row}
    output: dict[tuple[str, tuple[object, ...]], SnapshotRow] = {}
    if header is not None:
        output[("header", ())] = _snapshot_row("header", (), header)
    for table, frame, identity_fields in frames:
        for record in _records(frame):
            identity = tuple(_immutable_value(record[field]) for field in identity_fields)
            row = _snapshot_row(table, identity, record)
            output[(table, identity)] = row
    return output


def _snapshot_row(
    table: str,
    identity: tuple[object, ...],
    values: dict[str, Any],
) -> SnapshotRow:
    return SnapshotRow(
        table,
        identity,
        tuple(
            (name, _immutable_value(value))
            for name, value in values.items()
            if name != "retrieved_at"
        ),
    )


def _metadata_diff_values(metadata: ResultMetadata) -> dict[str, object]:
    values = _metadata_to_dict(metadata)
    values.pop("diagnostics")
    return {name: _immutable_value(value) for name, value in values.items()}


def _immutable_value(value: object) -> object:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, dict):
        mapping = cast("dict[str, object]", value)
        return tuple((key, _immutable_value(item)) for key, item in sorted(mapping.items()))
    if isinstance(value, list | tuple):
        return tuple(
            _immutable_value(item) for item in cast("list[object] | tuple[object, ...]", value)
        )
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    return value


def _values_equal(left: object, right: object) -> bool:
    return _immutable_value(left) == _immutable_value(right)


def _bar_query_filters(
    interval: str | None,
    start: date | datetime | None,
    end: date | datetime | None,
) -> tuple[list[str], list[object]]:
    start_bound, end_bound = _temporal_bounds(start, end)
    clauses: list[str] = []
    parameters: list[object] = []
    if interval is not None:
        clauses.append('record."interval" = ?')
        parameters.append(interval)
    supplied_bound = start_bound if start_bound is not None else end_bound
    temporal = 'record."timestamp"' if isinstance(supplied_bound, datetime) else 'record."date"'
    if start_bound is not None:
        clauses.append(f"{temporal} >= ?")
        parameters.append(start_bound)
    if end_bound is not None:
        clauses.append(f"{temporal} <= ?")
        parameters.append(end_bound)
    return clauses, parameters


def _series_query_filters(
    start_label: str | None,
    end_label: str | None,
) -> tuple[list[str], list[object]]:
    if start_label is not None and end_label is not None and start_label > end_label:
        raise ValueError("start_label must not follow end_label")
    clauses: list[str] = []
    parameters: list[object] = []
    period = 'record."period_label"'
    if start_label is not None:
        clauses.append(f"{period} >= ?")
        parameters.append(start_label)
    if end_label is not None:
        clauses.append(f"{period} <= ?")
        parameters.append(end_label)
    return clauses, parameters


def _vintage_query_filters(
    start_label: str | None,
    end_label: str | None,
    available_on: date | None,
) -> tuple[list[str], list[object]]:
    clauses, parameters = _series_query_filters(start_label, end_label)
    if available_on is not None:
        available_from = 'record."available_from"'
        available_through = 'record."available_through"'
        clauses.append(f"{available_from} <= ?")
        clauses.append(f"({available_through} IS NULL OR {available_through} >= ?)")
        parameters.extend((available_on, available_on))
    return clauses, parameters


def _validate_page_request(
    table: _DatasetTable,
    limit: int,
    offset: int,
    sort_by: str | None,
    descending: bool,
) -> None:
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer between 1 and 1000")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if sort_by is not None and sort_by not in table.dtypes:
        raise ValueError(f"sort_by is not supported for this dataset: {sort_by}")
    if type(descending) is not bool:
        raise TypeError("descending must be a boolean")


def _page_ordering(
    table: _DatasetTable,
    sort_by: str | None,
    descending: bool,
) -> str:
    primary = table.row_key[0] if sort_by is None else sort_by
    fields = (
        table.row_key
        if sort_by is None
        else (sort_by, *(field for field in table.row_key if field != sort_by))
    )
    return ", ".join(
        f'record."{field}" {"DESC" if descending and field == primary else "ASC"} NULLS LAST'
        for field in fields
    )


def _source_hash(payload: dict[str, Any]) -> str:
    source = _without_retrieval(payload)
    encoded = json.dumps(source, sort_keys=True, separators=(",", ":"), default=_json)
    return sha256(encoded.encode()).hexdigest()


def _snapshot_payload(value: Any) -> Any:
    if isinstance(value, dict):
        mapping = cast("dict[str, Any]", value)
        return {
            key: None if key == "retrieved_at" else _snapshot_payload(item)
            for key, item in mapping.items()
            if key != "metadata"
        }
    if isinstance(value, list):
        return [_snapshot_payload(item) for item in cast("list[Any]", value)]
    return value


def _occurrence_payload(
    payload: str,
    metadata: str,
    retrieved_at: str,
) -> dict[str, Any]:
    result = cast("dict[str, Any]", strict_json_loads(payload))
    result["metadata"] = cast("dict[str, Any]", strict_json_loads(metadata))
    return cast("dict[str, Any]", _restore_retrieved_at(result, retrieved_at))


def _restore_retrieved_at(value: Any, retrieved_at: str) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                retrieved_at if key == "retrieved_at" else _restore_retrieved_at(item, retrieved_at)
            )
            for key, item in cast("dict[str, Any]", value).items()
        }
    if isinstance(value, list):
        return [_restore_retrieved_at(item, retrieved_at) for item in cast("list[Any]", value)]
    return value


def _without_retrieval(value: Any) -> Any:
    if isinstance(value, dict):
        mapping = cast("dict[str, Any]", value)
        if "metadata" in mapping:
            mapping = {key: item for key, item in mapping.items() if key != "metadata"}
        return {
            key: _without_retrieval(item)
            for key, item in mapping.items()
            if key not in {"retrieved_at"}
        }
    if isinstance(value, list):
        return [_without_retrieval(item) for item in cast("list[Any]", value)]
    return value


def _json(value: object) -> object:
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    if hasattr(value, "value"):
        return value.value  # type: ignore[union-attr]
    raise TypeError(f"value is not JSON serializable: {type(value).__name__}")
