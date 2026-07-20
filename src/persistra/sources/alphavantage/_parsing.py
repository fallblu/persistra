"""Shared payload-shape helpers for Alpha Vantage endpoint parsers."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from persistra.domain import ContentId
from persistra.errors import SourceResponseError

if TYPE_CHECKING:
    from persistra.domain import EntityId

MISSING_VALUES = frozenset({"", ".", "None", "null", "-"})


def derived_entity_id[IdT: EntityId](kind: type[IdT], material: str | ContentId) -> IdT:
    """Return the deterministic entity id derived from stable identity material."""
    content = (
        material
        if isinstance(material, ContentId)
        else ContentId.from_bytes(material.encode())
    )
    return kind(UUID(bytes=content.digest[:16]))


def decimal_value(raw: object, description: str) -> Decimal:
    """Parse one decimal field, rejecting non-finite or malformed text."""
    try:
        value = Decimal(str(raw))
    except InvalidOperation as cause:
        raise SourceResponseError(
            f"alpha vantage {description} is not a decimal number"
        ) from cause
    if not value.is_finite():
        raise SourceResponseError(f"alpha vantage {description} is not finite")
    return value


def json_object(value: Any, description: str) -> dict[str, Any]:
    """Require one JSON object, naming the malformed spot otherwise."""
    if not isinstance(value, dict):
        raise SourceResponseError(f"alpha vantage {description} is malformed")
    return cast("dict[str, Any]", value)


def series_payload(payload: dict[str, Any], prefix: str) -> dict[str, Any]:
    """Return the series object stored under the first key with ``prefix``."""
    for key, value in payload.items():
        if key.startswith(prefix):
            return json_object(value, f"series under {prefix!r}")
    raise SourceResponseError(f"alpha vantage payload lacks a {prefix!r} series")


def series_field(row: dict[str, Any], suffix: str, description: str) -> object:
    """Return the first row field whose key ends with ``suffix``."""
    for key, value in row.items():
        if key.endswith(suffix):
            return value
    raise SourceResponseError(f"alpha vantage row lacks the {description} field")
