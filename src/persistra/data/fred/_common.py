"""Shared FRED request and provenance helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any, cast

from persistra.errors import ResponseError
from persistra.model import CacheStatus, ResultMetadata, SchemaDiagnostic

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from persistra.data.fred.transport import FredTransport, RawResponse

DEFAULT_CACHE_AGE = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class AdapterContext:
    """Configuration shared by the focused FRED namespaces."""

    transport: FredTransport
    strict_schema: bool = False
    cache_ages: Mapping[str, timedelta | None] = field(
        default_factory=lambda: cast("Mapping[str, timedelta | None]", {})
    )

    def json(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        refresh: bool = False,
        offline: bool = False,
    ) -> tuple[dict[str, Any], RawResponse]:
        """Request and decode one JSON object."""
        raw = self.transport.request(
            operation,
            parameters,
            cache_age=self.cache_ages.get(operation, DEFAULT_CACHE_AGE),
            refresh=refresh,
            offline=offline,
        )
        try:
            value = json.loads(raw.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResponseError(f"malformed JSON success body for {operation}") from error
        if not isinstance(value, dict):
            raise ResponseError(f"expected a JSON object for {operation}")
        return cast("dict[str, Any]", value), raw

    def pages(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        item_key: str,
        limit: int,
        maximum_items: int | None = None,
        refresh: bool = False,
        offline: bool = False,
    ) -> tuple[list[Any], tuple[RawResponse, ...], tuple[SchemaDiagnostic, ...]]:
        """Read every offset page and validate the pagination envelope."""
        offset = 0
        items: list[Any] = []
        responses: list[RawResponse] = []
        diagnostics: list[SchemaDiagnostic] = []
        while True:
            payload, raw = self.json(
                operation,
                {**parameters, "limit": limit, "offset": offset},
                refresh=refresh,
                offline=offline,
            )
            responses.append(raw)
            diagnostics.extend(
                unknown_fields(
                    payload,
                    {
                        "realtime_start",
                        "realtime_end",
                        "observation_start",
                        "observation_end",
                        "units",
                        "output_type",
                        "file_type",
                        "order_by",
                        "sort_order",
                        "count",
                        "offset",
                        "limit",
                        item_key,
                    },
                    context=f"{operation} envelope",
                )
            )
            page = payload.get(item_key)
            if not isinstance(page, list):
                raise ResponseError(f"{operation} response has no {item_key} list")
            count = _nonnegative_integer(payload, "count", operation)
            returned_offset = _nonnegative_integer(payload, "offset", operation)
            if returned_offset != offset:
                raise ResponseError(f"{operation} response has an unexpected offset")
            page_items = cast("list[Any]", page)
            target_count = count if maximum_items is None else min(count, maximum_items)
            items.extend(page_items[: target_count - offset])
            if offset == 0 and maximum_items is not None and count > maximum_items:
                diagnostics.append(
                    SchemaDiagnostic(
                        "count",
                        f"provider count exceeds the {maximum_items}-item pagination maximum; "
                        "results were capped",
                    )
                )
            if offset + len(page_items) >= target_count:
                break
            if not page_items:
                raise ResponseError(f"{operation} pagination stopped before count")
            offset += len(page_items)
        return items, tuple(responses), tuple(diagnostics)

    def metadata(
        self,
        operation: str,
        parameters: dict[str, Any],
        responses: Sequence[RawResponse],
        *,
        diagnostics: Sequence[SchemaDiagnostic] = (),
        provider_as_of: datetime | None = None,
    ) -> ResultMetadata:
        """Create one result provenance record from one or more response pages."""
        if not responses:
            raise ValueError("at least one raw response is required")
        unknown = tuple(item for item in diagnostics if item.message.startswith("unknown provider"))
        if self.strict_schema and unknown:
            fields = ", ".join(sorted({item.field for item in unknown}))
            raise ResponseError(f"unknown provider fields for {operation}: {fields}")
        return ResultMetadata(
            provider="fred",
            operation=operation,
            request_parameters=parameters,
            retrieved_at=max(response.retrieved_at for response in responses),
            provider_as_of=provider_as_of,
            cache_status=_cache_status(responses),
            diagnostics=_unique_diagnostics(diagnostics),
        )


def unknown_fields(
    payload: Mapping[str, Any],
    known: set[str],
    *,
    context: str,
) -> tuple[SchemaDiagnostic, ...]:
    """Describe provider fields outside one known FRED schema."""
    return tuple(
        SchemaDiagnostic(field, f"unknown provider field in {context}")
        for field in sorted(set(payload).difference(known))
    )


def _nonnegative_integer(payload: dict[str, Any], field: str, operation: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ResponseError(f"{operation} response has invalid {field}")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ResponseError(f"{operation} response has invalid {field}") from error
    if result < 0:
        raise ResponseError(f"{operation} response has invalid {field}")
    return result


def _cache_status(responses: Sequence[RawResponse]) -> CacheStatus:
    statuses = {response.cache_status for response in responses}
    for status in (
        CacheStatus.OFFLINE,
        CacheStatus.REFRESHED,
        CacheStatus.MISS,
        CacheStatus.HIT,
        CacheStatus.NOT_USED,
    ):
        if status in statuses:
            return status
    return CacheStatus.NOT_USED


def _unique_diagnostics(
    diagnostics: Sequence[SchemaDiagnostic],
) -> tuple[SchemaDiagnostic, ...]:
    return tuple(
        SchemaDiagnostic(field, message)
        for field, message in sorted({(item.field, item.message) for item in diagnostics})
    )
