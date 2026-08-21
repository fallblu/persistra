"""Explicit versioned DuckDB storage for normalized results."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Self, cast

import duckdb
import pandas as pd

from persistra._portable import thaw_portable_mapping
from persistra.errors import StoreError
from persistra.model import (
    BarSet,
    CacheStatus,
    CommoditySpotQuote,
    EntitlementMode,
    ExchangeRateQuote,
    IndexCatalogResult,
    Instrument,
    InstrumentKind,
    InstrumentSearchResult,
    MarketStatusResult,
    OptionChain,
    QuoteSet,
    ResultMetadata,
    SchemaDiagnostic,
    SeriesDefinition,
    SeriesKind,
    SeriesSet,
    TopOfBookSet,
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

STORE_SCHEMA_VERSION = 3

type StoredResult = (
    BarSet
    | QuoteSet
    | TopOfBookSet
    | OptionChain
    | SeriesSet
    | VintageSeriesSet
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
class _DatasetTable:
    name: str
    frame_key: str
    dtypes: dict[str, str]
    row_key: tuple[str, ...]


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
}


class DuckDBStore:
    """A one-process DuckDB store with snapshots and cumulative research datasets."""

    def __init__(self, path: Path, connection: duckdb.DuckDBPyConnection) -> None:
        self.path = path
        self._connection = connection

    @classmethod
    def create(cls, path: str | Path) -> Self:
        """Create a new v4 store at an absent path."""
        target = Path(path)
        if target.exists():
            raise StoreError(f"store already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(target))
        try:
            _create_schema(connection)
        except Exception:
            connection.close()
            target.unlink(missing_ok=True)
            raise
        return cls(target, connection)

    @classmethod
    def open(cls, path: str | Path, *, read_only: bool = False) -> Self:
        """Open an existing v4 store without migrating it."""
        target = Path(path)
        if not target.is_file():
            raise StoreError(f"store does not exist: {target}")
        try:
            connection = duckdb.connect(str(target), read_only=read_only)
        except duckdb.Error as error:
            raise StoreError(f"store is not a valid DuckDB database: {target}") from error
        try:
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None or row[0] != STORE_SCHEMA_VERSION:
                raise StoreError("store schema version is not supported")
        except duckdb.Error as error:
            connection.close()
            raise StoreError("store schema is missing or invalid") from error
        return cls(target, connection)

    def close(self) -> None:
        """Close the explicit DuckDB connection."""
        self._connection.close()

    @property
    def schema_version(self) -> int:
        """Return the validated store schema version."""
        return STORE_SCHEMA_VERSION

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

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
        try:
            self._connection.execute("BEGIN TRANSACTION")
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
        except Exception as error:
            self._connection.execute("ROLLBACK")
            if isinstance(error, StoreError):
                raise
            raise StoreError(f"could not save {family}") from error
        return snapshot_id

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
        start_bound, end_bound = _temporal_bounds(start, end)
        clauses: list[str] = []
        parameters: list[object] = []
        if interval is not None:
            clauses.append('record."interval" = ?')
            parameters.append(interval)
        supplied_bound = start_bound if start_bound is not None else end_bound
        temporal = (
            'record."timestamp"'
            if isinstance(supplied_bound, datetime)
            else 'record."date"'
        )
        if start_bound is not None:
            clauses.append(f"{temporal} >= ?")
            parameters.append(start_bound)
        if end_bound is not None:
            clauses.append(f"{temporal} <= ?")
            parameters.append(end_bound)
        records = self._query_records(
            "bars",
            instrument_id,
            retrieved_before,
            clauses,
            parameters,
        )
        return _frame(records, BAR_DTYPES).sort_values(
            ["instrument_id", "interval", "price_adjustment", "session", "date", "timestamp"]
        ).reset_index(drop=True)

    def query_series(
        self,
        series_id: str,
        *,
        start_label: str | None = None,
        end_label: str | None = None,
        retrieved_before: datetime | None = None,
    ) -> pd.DataFrame:
        """Query cumulative scalar observations with latest-observed row revisions."""
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
        records = self._query_records(
            "series",
            series_id,
            retrieved_before,
            clauses,
            parameters,
        )
        return _frame(records, SERIES_DTYPES).sort_values(
            ["series_id", "frequency", "maturity", "period_label"]
        ).reset_index(drop=True)

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
        if available_on is not None:
            available_from = 'record."available_from"'
            available_through = 'record."available_through"'
            clauses.append(f"{available_from} <= ?")
            clauses.append(f"({available_through} IS NULL OR {available_through} >= ?)")
            parameters.extend((available_on, available_on))
        records = self._query_records(
            "vintage_series",
            series_id,
            retrieved_before,
            clauses,
            parameters,
        )
        return _frame(records, VINTAGE_SERIES_DTYPES).sort_values(
            ["series_id", "frequency", "maturity", "period_label", "available_from"]
        ).reset_index(drop=True)

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
        query += (
            " ORDER BY occurrences.retrieved_at DESC, occurrences.saved_order DESC LIMIT 1"
        )
        row = self._connection.execute(query, parameters).fetchone()
        return (
            None
            if row is None
            else _occurrence_payload(str(row[0]), str(row[1]), str(row[2]))
        )

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

    def _insert_dataset_rows(
        self,
        snapshot_id: str,
        family: str,
        payload: dict[str, Any],
    ) -> None:
        table = _DATASET_TABLES.get(family)
        if table is None:
            return
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
        "diagnostics": [asdict(item) for item in metadata.diagnostics],
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
    result = cast("dict[str, Any]", json.loads(payload))
    result["metadata"] = cast("dict[str, Any]", json.loads(metadata))
    return cast("dict[str, Any]", _restore_retrieved_at(result, retrieved_at))


def _restore_retrieved_at(value: Any, retrieved_at: str) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                retrieved_at
                if key == "retrieved_at"
                else _restore_retrieved_at(item, retrieved_at)
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
