"""FRED series discovery and release-context metadata."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from persistra.data.fred._common import AdapterContext, unknown_fields
from persistra.errors import NoDataError, ResponseError

if TYPE_CHECKING:
    from persistra.model import ResultMetadata

_PAGE_LIMIT = 1_000
_SERIES_SEARCH_MAXIMUM = 5_000

_SERIES_FIELDS = {
    "id",
    "realtime_start",
    "realtime_end",
    "title",
    "observation_start",
    "observation_end",
    "frequency",
    "frequency_short",
    "units",
    "units_short",
    "seasonal_adjustment",
    "seasonal_adjustment_short",
    "last_updated",
    "popularity",
    "group_popularity",
    "notes",
}
_CATEGORY_FIELDS = {"id", "name", "parent_id", "notes"}
_RELEASE_FIELDS = {
    "id",
    "realtime_start",
    "realtime_end",
    "name",
    "press_release",
    "link",
    "notes",
}
_TAG_FIELDS = {"name", "group_id", "notes", "created", "popularity", "series_count"}


@dataclass(frozen=True, slots=True)
class FredSeriesSummary:
    """One source-level series match without canonical identity inference."""

    provider_series: str
    title: str
    observation_start: date
    observation_end: date
    frequency: str
    units: str
    seasonal_adjustment: str | None
    last_updated: datetime | None
    popularity: int
    notes: str | None


@dataclass(frozen=True, slots=True)
class FredSeriesSearchResult:
    """Ordered series matches and their acquisition provenance."""

    query: str
    series: tuple[FredSeriesSummary, ...]
    metadata: ResultMetadata


@dataclass(frozen=True, slots=True)
class FredCategory:
    """One FRED category assigned to a series."""

    category_id: int
    name: str
    parent_id: int
    notes: str | None


@dataclass(frozen=True, slots=True)
class FredSeriesCategoriesResult:
    """Categories assigned to one provider series."""

    provider_series: str
    categories: tuple[FredCategory, ...]
    metadata: ResultMetadata


@dataclass(frozen=True, slots=True)
class FredRelease:
    """The FRED release that owns one series."""

    release_id: int
    name: str
    realtime_start: date
    realtime_end: date
    press_release: bool
    link: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class FredSeriesReleaseResult:
    """Release context for one provider series."""

    provider_series: str
    release: FredRelease
    metadata: ResultMetadata


@dataclass(frozen=True, slots=True)
class FredTag:
    """One source-level tag assigned to a FRED series."""

    name: str
    group_id: str
    notes: str | None
    created_at: datetime
    popularity: int
    series_count: int


@dataclass(frozen=True, slots=True)
class FredSeriesTagsResult:
    """Tags assigned to one provider series."""

    provider_series: str
    tags: tuple[FredTag, ...]
    metadata: ResultMetadata


class DiscoveryNamespace:
    """Focused FRED series search and release-context operations."""

    def __init__(self, context: AdapterContext) -> None:
        self._context = context

    def search(
        self,
        query: str,
        *,
        search_type: Literal["full_text", "series_id"] = "full_text",
        tag_names: tuple[str, ...] = (),
        exclude_tag_names: tuple[str, ...] = (),
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> FredSeriesSearchResult:
        """Find source-level series by text or provider identifier."""
        search_text = _text_argument(query, "query")
        if search_type not in {"full_text", "series_id"}:
            raise ValueError("search_type must be full_text or series_id")
        included = _tag_arguments(tag_names, "tag_names")
        excluded = _tag_arguments(exclude_tag_names, "exclude_tag_names")
        if excluded and not included:
            raise ValueError("exclude_tag_names requires tag_names")
        parameters: dict[str, Any] = {
            "search_text": search_text,
            "search_type": search_type,
            "order_by": "search_rank" if search_type == "full_text" else "series_id",
            "sort_order": "desc" if search_type == "full_text" else "asc",
        }
        _add_bounds(parameters, realtime_start, realtime_end)
        if included:
            parameters["tag_names"] = ";".join(included)
        if excluded:
            parameters["exclude_tag_names"] = ";".join(excluded)
        items, responses, envelope_diagnostics = self._context.pages(
            "series_search",
            parameters,
            item_key="seriess",
            limit=_PAGE_LIMIT,
            maximum_items=_SERIES_SEARCH_MAXIMUM,
            refresh=refresh,
            offline=offline,
        )
        series: list[FredSeriesSummary] = []
        diagnostics = list(envelope_diagnostics)
        for value in items:
            item = _row(value, "series_search", "series")
            diagnostics.extend(unknown_fields(item, _SERIES_FIELDS, context="series search row"))
            series.append(_series_summary(item))
        metadata = self._context.metadata(
            "series_search", parameters, responses, diagnostics=diagnostics
        )
        return FredSeriesSearchResult(search_text, tuple(series), metadata)

    def categories(
        self,
        series_id: str,
        *,
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> FredSeriesCategoriesResult:
        """Return categories assigned to one provider series."""
        provider_series = _text_argument(series_id, "series_id")
        parameters: dict[str, Any] = {"series_id": provider_series}
        _add_bounds(parameters, realtime_start, realtime_end)
        payload, raw = self._context.json(
            "series_categories", parameters, refresh=refresh, offline=offline
        )
        diagnostics = list(
            unknown_fields(payload, {"categories"}, context="series categories envelope")
        )
        values = _rows(payload, "categories", "series_categories")
        categories: list[FredCategory] = []
        for value in values:
            item = _row(value, "series_categories", "category")
            diagnostics.extend(unknown_fields(item, _CATEGORY_FIELDS, context="category row"))
            categories.append(
                FredCategory(
                    _nonnegative_integer(item, "id", "category"),
                    _required_text(item, "name", "category"),
                    _nonnegative_integer(item, "parent_id", "category"),
                    _optional_text(item, "notes", "category"),
                )
            )
        categories.sort(key=lambda item: item.category_id)
        metadata = self._context.metadata(
            "series_categories", parameters, (raw,), diagnostics=diagnostics
        )
        return FredSeriesCategoriesResult(provider_series, tuple(categories), metadata)

    def release(
        self,
        series_id: str,
        *,
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> FredSeriesReleaseResult:
        """Return the release that owns one provider series."""
        provider_series = _text_argument(series_id, "series_id")
        parameters: dict[str, Any] = {"series_id": provider_series}
        _add_bounds(parameters, realtime_start, realtime_end)
        payload, raw = self._context.json(
            "series_release", parameters, refresh=refresh, offline=offline
        )
        diagnostics = list(
            unknown_fields(
                payload,
                {"realtime_start", "realtime_end", "releases"},
                context="series release envelope",
            )
        )
        values = _rows(payload, "releases", "series_release")
        if not values:
            raise NoDataError("no provider release for series")
        if len(values) != 1:
            raise ResponseError("series_release response does not contain one release")
        item = _row(values[0], "series_release", "release")
        diagnostics.extend(unknown_fields(item, _RELEASE_FIELDS, context="release row"))
        press_release = item.get("press_release")
        if not isinstance(press_release, bool):
            raise ResponseError("release has invalid press_release")
        release = FredRelease(
            _nonnegative_integer(item, "id", "release"),
            _required_text(item, "name", "release"),
            _provider_date(_required_text(item, "realtime_start", "release"), "realtime_start"),
            _provider_date(_required_text(item, "realtime_end", "release"), "realtime_end"),
            press_release,
            _optional_text(item, "link", "release"),
            _optional_text(item, "notes", "release"),
        )
        metadata = self._context.metadata(
            "series_release", parameters, (raw,), diagnostics=diagnostics
        )
        return FredSeriesReleaseResult(provider_series, release, metadata)

    def tags(
        self,
        series_id: str,
        *,
        realtime_start: date | str | None = None,
        realtime_end: date | str | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> FredSeriesTagsResult:
        """Return tags assigned to one provider series in stable name order."""
        provider_series = _text_argument(series_id, "series_id")
        parameters: dict[str, Any] = {
            "series_id": provider_series,
            "order_by": "name",
            "sort_order": "asc",
        }
        _add_bounds(parameters, realtime_start, realtime_end)
        items, responses, envelope_diagnostics = self._context.pages(
            "series_tags",
            parameters,
            item_key="tags",
            limit=_PAGE_LIMIT,
            refresh=refresh,
            offline=offline,
        )
        tags: list[FredTag] = []
        diagnostics = list(envelope_diagnostics)
        for value in items:
            item = _row(value, "series_tags", "tag")
            diagnostics.extend(unknown_fields(item, _TAG_FIELDS, context="tag row"))
            tags.append(
                FredTag(
                    _required_text(item, "name", "tag"),
                    _required_text(item, "group_id", "tag"),
                    _optional_text(item, "notes", "tag"),
                    _provider_datetime(
                        _required_text(item, "created", "tag"), "tag created"
                    ),
                    _nonnegative_integer(item, "popularity", "tag"),
                    _nonnegative_integer(item, "series_count", "tag"),
                )
            )
        tags.sort(key=lambda item: (item.name, item.group_id))
        metadata = self._context.metadata(
            "series_tags", parameters, responses, diagnostics=diagnostics
        )
        return FredSeriesTagsResult(provider_series, tuple(tags), metadata)


def _series_summary(item: dict[str, Any]) -> FredSeriesSummary:
    return FredSeriesSummary(
        _required_text(item, "id", "series search row"),
        _required_text(item, "title", "series search row"),
        _provider_date(
            _required_text(item, "observation_start", "series search row"),
            "observation_start",
        ),
        _provider_date(
            _required_text(item, "observation_end", "series search row"),
            "observation_end",
        ),
        _required_text(item, "frequency", "series search row"),
        _required_text(item, "units", "series search row"),
        _optional_text(item, "seasonal_adjustment", "series search row"),
        _optional_datetime(item, "last_updated", "series search row"),
        _nonnegative_integer(item, "popularity", "series search row"),
        _optional_text(item, "notes", "series search row"),
    )


def _add_bounds(
    parameters: dict[str, Any],
    start: date | str | None,
    end: date | str | None,
) -> None:
    start_label = None if start is None else _date_argument(start, "realtime_start")
    end_label = None if end is None else _date_argument(end, "realtime_end")
    if start_label is not None and end_label is not None and start_label > end_label:
        raise ValueError("realtime_start must not follow realtime_end")
    if start_label is not None:
        parameters["realtime_start"] = start_label
    if end_label is not None:
        parameters["realtime_end"] = end_label


def _date_argument(value: date | str, field: str) -> str:
    if isinstance(value, datetime):
        raise TypeError(f"{field} must be a date or ISO date string")
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError(f"{field} must use YYYY-MM-DD") from error


def _tag_arguments(values: tuple[str, ...], field: str) -> tuple[str, ...]:
    normalized = tuple(_text_argument(value, field) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must be unique")
    return normalized


def _text_argument(value: str, field: str) -> str:
    result = value.strip()
    if not result:
        raise ValueError(f"{field} must not be empty")
    return result


def _rows(payload: dict[str, Any], field: str, operation: str) -> list[Any]:
    values = payload.get(field)
    if not isinstance(values, list):
        raise ResponseError(f"{operation} response has no {field} list")
    return cast("list[Any]", values)


def _row(value: Any, operation: str, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResponseError(f"{operation} response has a malformed {label} row")
    return cast("dict[str, Any]", value)


def _required_text(payload: dict[str, Any], field: str, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ResponseError(f"{context} has no {field}")
    return value


def _optional_text(payload: dict[str, Any], field: str, context: str) -> str | None:
    value = payload.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ResponseError(f"{context} has invalid {field}")
    return value


def _nonnegative_integer(payload: dict[str, Any], field: str, context: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ResponseError(f"{context} has invalid {field}")
    try:
        result = int(value)
    except ValueError as error:
        raise ResponseError(f"{context} has invalid {field}") from error
    if result < 0:
        raise ResponseError(f"{context} has invalid {field}")
    return result


def _provider_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ResponseError(f"provider returned invalid {field}") from error


def _provider_datetime(value: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise ResponseError(f"provider returned invalid {field}") from error
    if result.tzinfo is None:
        raise ResponseError(f"provider returned {field} without a UTC offset")
    return result.astimezone(UTC)


def _optional_datetime(
    payload: dict[str, Any], field: str, context: str
) -> datetime | None:
    value = _optional_text(payload, field, context)
    return None if value is None else _provider_datetime(value, field)
