"""Explicit local-file imports into normalized result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, cast

import pandas as pd
import pyarrow as _pyarrow  # pyright: ignore[reportMissingTypeStubs]
import pyarrow.parquet as _parquet  # pyright: ignore[reportMissingTypeStubs]

from persistra._portable import freeze_portable_mapping, thaw_portable_mapping
from persistra.errors import DataValidationError
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

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from persistra.data.store import StoredResult

pa: Any = _pyarrow
pq: Any = _parquet


class LocalFamily(StrEnum):
    """Normalized result families accepted by the local adapter."""

    BARS = "bars"
    COMMODITY_SPOT = "commodity_spot"
    EXCHANGE_RATE = "exchange_rate"
    INDEX_CATALOG = "index_catalog"
    MARKET_STATUS = "market_status"
    OPTIONS = "options"
    QUOTES = "quotes"
    SEARCH = "search"
    SERIES = "series"
    TOP_OF_BOOK = "top_of_book"
    VINTAGE_DATES = "vintage_dates"
    VINTAGE_SERIES = "vintage_series"


@dataclass(frozen=True, slots=True)
class LocalImportSpec:
    """Explicit target, source-column mapping, and caller-declared semantics."""

    family: LocalFamily
    columns: Mapping[str, str]
    semantics: Mapping[str, Any]

    def __post_init__(self) -> None:
        columns = dict(self.columns)
        if not columns or any(
            not key.strip() or not value.strip()
            for key, value in columns.items()
        ):
            raise ValueError("columns must map nonempty normalized names to source names")
        if len(set(columns.values())) != len(columns):
            raise ValueError("source columns must be unique")
        object.__setattr__(self, "columns", MappingProxyType(columns))
        object.__setattr__(
            self,
            "semantics",
            freeze_portable_mapping(self.semantics, name="local import semantics"),
        )


@dataclass(frozen=True, slots=True)
class LocalSourceIdentity:
    """Stable identity of the exact local file bytes that were read."""

    path: Path
    size: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class LocalValidationFinding:
    """One structured local-import validation failure."""

    code: str
    message: str


@dataclass(frozen=True, slots=True)
class LocalValidation:
    """Dry local-import validation outcome without a published result."""

    source: LocalSourceIdentity | None
    findings: tuple[LocalValidationFinding, ...]

    @property
    def is_valid(self) -> bool:
        """Return whether the file can construct the requested normalized result."""
        return not self.findings


_FRAME_DTYPES: dict[LocalFamily, Mapping[str, str]] = {
    LocalFamily.BARS: BAR_DTYPES,
    LocalFamily.INDEX_CATALOG: INDEX_CATALOG_DTYPES,
    LocalFamily.MARKET_STATUS: MARKET_STATUS_DTYPES,
    LocalFamily.QUOTES: QUOTE_DTYPES,
    LocalFamily.SEARCH: SEARCH_DTYPES,
    LocalFamily.SERIES: SERIES_DTYPES,
    LocalFamily.TOP_OF_BOOK: TOP_OF_BOOK_DTYPES,
    LocalFamily.VINTAGE_SERIES: VINTAGE_SERIES_DTYPES,
}
_SCALAR_DTYPES: dict[LocalFamily, Mapping[str, str]] = {
    LocalFamily.EXCHANGE_RATE: {
        "instrument_id": "string",
        "provider": "string",
        "base_currency": "string",
        "quote_currency": "string",
        "exchange_rate": "float64",
        "bid": "Float64",
        "ask": "Float64",
        "provider_timestamp": "datetime64[ns, UTC]",
        "provider_timezone": "string",
        "retrieved_at": "datetime64[ns, UTC]",
    },
    LocalFamily.COMMODITY_SPOT: {
        "series_id": "string",
        "provider": "string",
        "metal": "string",
        "value": "float64",
        "unit": "string",
        "provider_timestamp": "datetime64[ns, UTC]",
        "retrieved_at": "datetime64[ns, UTC]",
    },
}


class LocalDataAdapter:
    """Read caller-owned CSV, Arrow IPC, or Parquet files through public contracts."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def validate(self, path: str | Path, spec: LocalImportSpec) -> LocalValidation:
        """Dry-run one import and return structured diagnostics instead of a result."""
        try:
            _result, source = self._prepare(Path(path), spec)
        except FileNotFoundError as error:
            return LocalValidation(None, (LocalValidationFinding("source.missing", str(error)),))
        except OSError as error:
            return LocalValidation(None, (LocalValidationFinding("source.read", str(error)),))
        except (KeyError, TypeError, ValueError, DataValidationError) as error:
            return LocalValidation(None, (LocalValidationFinding("contract.invalid", str(error)),))
        return LocalValidation(source, ())

    def import_file(self, path: str | Path, spec: LocalImportSpec) -> StoredResult:
        """Import one complete local file or raise its normalized contract error."""
        try:
            result, _source = self._prepare(Path(path), spec)
        except DataValidationError:
            raise
        except Exception as error:
            raise DataValidationError(f"local import failed: {error}") from error
        return result

    def _prepare(
        self, path: Path, spec: LocalImportSpec
    ) -> tuple[StoredResult, LocalSourceIdentity]:
        imported_at = self._clock()
        if imported_at.tzinfo is None:
            raise ValueError("local import clock must return a timezone-aware datetime")
        imported_at = imported_at.astimezone(UTC)
        source_frame, source = _read_source(path)
        expected = _expected_columns(spec.family)
        mapped = set(spec.columns)
        required_mapping = expected - {"retrieved_at"}
        if mapped != required_mapping:
            raise DataValidationError(
                f"column mapping differs: missing={sorted(required_mapping - mapped)}, "
                f"extra={sorted(mapped - required_mapping)}"
            )
        missing_source = set(spec.columns.values()).difference(source_frame.columns)
        if missing_source:
            raise DataValidationError(f"source columns are missing: {sorted(missing_source)}")
        metadata = _metadata(spec, source, imported_at)
        result = _construct(source_frame, spec, metadata, imported_at)
        return result, source


def _read_source(path: Path) -> tuple[pd.DataFrame, LocalSourceIdentity]:
    target = path.resolve()
    before = target.stat()
    if not target.is_file():
        raise OSError(f"local source is not a regular file: {target}")
    suffix = target.suffix.casefold()
    if suffix == ".csv":
        frame = pd.read_csv(target)
    elif suffix == ".arrow":
        value: pd.DataFrame = pa.ipc.open_file(target).read_all().to_pandas()
        frame = value
    elif suffix == ".parquet":
        value = pq.read_table(target).to_pandas()
        frame = value
    else:
        raise ValueError("local source must use a .csv, .arrow, or .parquet suffix")
    digest = sha256()
    with target.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    after = target.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_identity != after_identity:
        raise OSError(f"local source changed during import: {target}")
    return frame, LocalSourceIdentity(target, after.st_size, after.st_mtime_ns, digest.hexdigest())


def _expected_columns(family: LocalFamily) -> set[str]:
    if family is LocalFamily.OPTIONS:
        return set(OPTION_CONTRACT_DTYPES) | set(OPTION_OBSERVATION_DTYPES)
    if family is LocalFamily.VINTAGE_DATES:
        return {"provider_series", "vintage_date"}
    dtypes = _FRAME_DTYPES.get(family) or _SCALAR_DTYPES.get(family)
    if dtypes is None:
        raise ValueError(f"unsupported local family: {family.value}")
    return set(dtypes)


def _metadata(
    spec: LocalImportSpec, source: LocalSourceIdentity, imported_at: datetime
) -> ResultMetadata:
    provider = _semantic_text(spec, "provider")
    parameters = {
        "family": spec.family.value,
        "source": {
            "path": str(source.path),
            "size": source.size,
            "modified_ns": source.modified_ns,
            "sha256": source.sha256,
        },
        "columns": dict(spec.columns),
        "semantics": thaw_portable_mapping(spec.semantics),
    }
    entitlement = EntitlementMode(str(spec.semantics.get("entitlement", "not_applicable")))
    return ResultMetadata(
        provider,
        "local_file_import",
        parameters,
        imported_at,
        entitlement=entitlement,
        cache_status=CacheStatus.NOT_USED,
    )


def _construct(
    source: pd.DataFrame,
    spec: LocalImportSpec,
    metadata: ResultMetadata,
    imported_at: datetime,
) -> StoredResult:
    family = spec.family
    if family is LocalFamily.OPTIONS:
        contracts = _mapped_frame(source, spec, OPTION_CONTRACT_DTYPES, imported_at)
        contracts = (
            contracts.drop_duplicates()
            .sort_values(["expiration", "strike", "option_type", "contract_id"], kind="stable")
            .reset_index(drop=True)
        )
        observations = _mapped_frame(source, spec, OPTION_OBSERVATION_DTYPES, imported_at)
        observations = observations.sort_values(
            ["provider", "contract_id"], kind="stable"
        ).reset_index(drop=True)
        return OptionChain(
            _semantic_text(spec, "underlying_instrument_id"),
            _semantic_text(spec, "provider_symbol"),
            _semantic_date(spec, "chain_date"),
            contracts,
            observations,
            metadata,
        )
    if family is LocalFamily.VINTAGE_DATES:
        provider_series = _semantic_text(spec, "provider_series")
        values = source[spec.columns["provider_series"]].astype("string")
        if not values.eq(provider_series).all():
            raise DataValidationError("provider_series differs from declared semantics")
        dates = pd.Series(
            source[spec.columns["vintage_date"]], dtype="datetime64[ns]"
        ).dt.date.tolist()
        ordered = tuple(sorted(set(dates)))
        if len(ordered) != len(dates):
            raise DataValidationError("local vintage dates must be unique")
        return VintageDatesResult(provider_series, ordered, metadata)
    dtypes = _FRAME_DTYPES.get(family) or _SCALAR_DTYPES.get(family)
    if dtypes is None:
        raise ValueError(f"unsupported local family: {family.value}")
    frame = _mapped_frame(source, spec, dtypes, imported_at)
    if family is LocalFamily.BARS:
        instrument = Instrument(
            _semantic_text(spec, "instrument_id"),
            InstrumentKind(_semantic_text(spec, "instrument_kind")),
            _semantic_text(spec, "display_name"),
            _semantic_optional_text(spec, "base_currency"),
            _semantic_optional_text(spec, "quote_currency"),
        )
        _declared_column(frame, "price_adjustment", spec)
        _declared_column(frame, "timestamp_position", spec)
        _declared_column(frame, "source_timezone", spec)
        _declared_column(frame, "currency", spec)
        return BarSet(instrument, frame, metadata)
    if family is LocalFamily.QUOTES:
        return QuoteSet(frame, metadata)
    if family is LocalFamily.TOP_OF_BOOK:
        return TopOfBookSet(frame, metadata)
    if family in {LocalFamily.SERIES, LocalFamily.VINTAGE_SERIES}:
        definition = SeriesDefinition(
            _semantic_text(spec, "series_id"),
            SeriesKind(_semantic_text(spec, "series_kind")),
            _semantic_text(spec, "display_name"),
            metadata.provider,
            _semantic_text(spec, "provider_series"),
            _semantic_text(spec, "frequency"),
            _semantic_text(spec, "unit"),
            _semantic_optional_text(spec, "geography"),
            _semantic_optional_text(spec, "seasonal_adjustment"),
            _semantic_optional_text(spec, "maturity"),
        )
        if family is LocalFamily.SERIES:
            return SeriesSet(definition, frame, metadata)
        return VintageSeriesSet(definition, frame, metadata)
    if family is LocalFamily.SEARCH:
        return InstrumentSearchResult(_semantic_text(spec, "query"), frame, metadata)
    if family is LocalFamily.MARKET_STATUS:
        return MarketStatusResult(frame, metadata)
    if family is LocalFamily.INDEX_CATALOG:
        return IndexCatalogResult(frame, metadata)
    if len(frame) != 1:
        raise DataValidationError(f"{family.value} import requires exactly one row")
    row = frame.iloc[0]
    if family is LocalFamily.EXCHANGE_RATE:
        return ExchangeRateQuote(
            str(row["instrument_id"]),
            str(row["provider"]),
            str(row["base_currency"]),
            str(row["quote_currency"]),
            float(row["exchange_rate"]),
            _optional_float(row["bid"]),
            _optional_float(row["ask"]),
            _optional_datetime_value(row["provider_timestamp"]),
            _optional_string(row["provider_timezone"]),
            imported_at,
            metadata,
        )
    return CommoditySpotQuote(
        str(row["series_id"]),
        str(row["provider"]),
        str(row["metal"]),
        float(row["value"]),
        str(row["unit"]),
        _optional_datetime_value(row["provider_timestamp"]),
        imported_at,
        metadata,
    )


def _mapped_frame(
    source: pd.DataFrame,
    spec: LocalImportSpec,
    dtypes: Mapping[str, str],
    imported_at: datetime,
) -> pd.DataFrame:
    data = {
        name: (
            [imported_at] * len(source)
            if name == "retrieved_at"
            else source[spec.columns[name]].tolist()
        )
        for name in dtypes
    }
    return typed_frame(data, dtypes)


def _semantic_text(spec: LocalImportSpec, name: str) -> str:
    value = spec.semantics.get(name)
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"semantic {name} must be nonempty text")
    return value


def _semantic_optional_text(spec: LocalImportSpec, name: str) -> str | None:
    value = spec.semantics.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DataValidationError(f"semantic {name} must be text or null")
    return value


def _semantic_date(spec: LocalImportSpec, name: str) -> date:
    value = _semantic_text(spec, name)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise DataValidationError(f"semantic {name} must use YYYY-MM-DD") from error


def _declared_column(frame: pd.DataFrame, name: str, spec: LocalImportSpec) -> None:
    expected = spec.semantics.get(name)
    observed = set(frame[name].dropna().tolist())
    if observed != ({expected} if expected is not None else set()):
        raise DataValidationError(f"{name} differs from declared semantics")


def _optional_float(value: object) -> float | None:
    return None if pd.isna(cast("Any", value)) else float(cast("Any", value))


def _optional_string(value: object) -> str | None:
    return None if pd.isna(cast("Any", value)) else str(value)


def _optional_datetime_value(value: object) -> datetime | None:
    if pd.isna(cast("Any", value)):
        return None
    timestamp = cast("pd.Timestamp", value)
    return timestamp.to_pydatetime()
