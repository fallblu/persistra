"""Canonical identity serialization and deterministic seed streams."""

from __future__ import annotations

import base64
import json
import unicodedata
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, cast

from persistra.domain.identity import ContentId, EntityId, QualifiedName, SchemaVersion
from persistra.domain.numbers import (
    Currency,
    Money,
    NonNegativeQuantity,
    Price,
    Quantity,
    Rate,
    Unit,
)
from persistra.domain.time import Duration, validate_instant


def _instant_text(value: datetime) -> str:
    instant = validate_instant(value)
    return (
        f"{instant.year:04d}-{instant.month:02d}-{instant.day:02d}T"
        f"{instant.hour:02d}:{instant.minute:02d}:{instant.second:02d}."
        f"{instant.microsecond:06d}Z"
    )


def _decimal_text(value: Decimal, scale: int) -> str:
    return f"{value:.{scale}f}"


def canonical_value(value: Any) -> Any:
    """Convert a supported value into canonical JSON-compatible material."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        raise TypeError("floats are forbidden in canonical identity material")
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, bytes):
        return {"binary_base64url": base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")}
    if isinstance(value, datetime):
        return _instant_text(value)
    if isinstance(value, date):
        return value.isoformat()
    text_types = EntityId | ContentId | QualifiedName | SchemaVersion | Currency | Unit | Duration
    if isinstance(value, text_types):
        return str(value)
    if isinstance(value, Money | Price):
        return {"amount": _decimal_text(value.amount, 12), "currency": value.currency.code}
    if isinstance(value, Quantity | NonNegativeQuantity):
        return _decimal_text(value.value, 12)
    if isinstance(value, Rate):
        return _decimal_text(value.value, 18)
    if isinstance(value, Decimal):
        raise TypeError("bare Decimal requires an owning numeric profile")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        sequence = cast("tuple[Any, ...] | list[Any]", value)
        return [canonical_value(item) for item in sequence]
    if isinstance(value, dict):
        mapping = cast("dict[object, Any]", value)
        if not all(isinstance(key, str) for key in mapping):
            raise TypeError("canonical mapping keys must be strings")
        normalized: dict[str, Any] = {}
        for raw_key, item in mapping.items():
            key = cast("str", raw_key)
            normalized_key = unicodedata.normalize("NFC", key)
            if normalized_key in normalized:
                raise TypeError("mapping keys collide after NFC normalization")
            normalized[normalized_key] = canonical_value(item)
        return normalized
    if isinstance(value, set | frozenset):
        raise TypeError("sets require an explicitly declared canonical ordering")
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: canonical_value(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_bytes(value: Any) -> bytes:
    """Encode supported identity material as canonical UTF-8 JSON."""
    return json.dumps(
        canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def scoped_content_id(value: Any) -> ContentId:
    """Hash canonical structured material in the Persistra identity scope."""
    return ContentId.from_bytes(b"persistra\x00" + canonical_bytes(value))
