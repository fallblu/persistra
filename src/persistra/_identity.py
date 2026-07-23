"""This module contains the internal normalization for numeric execution identity material."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from persistra.domain import (
    ContentId,
    Currency,
    Duration,
    EntityId,
    Money,
    NonNegativeQuantity,
    Price,
    QualifiedName,
    Quantity,
    Rate,
    SchemaVersion,
    Unit,
)
from persistra.domain.serialization import canonical_bytes, scoped_content_id

_CANONICAL_DOMAIN_TYPES = (
    EntityId,
    ContentId,
    QualifiedName,
    SchemaVersion,
    Currency,
    Unit,
    Duration,
    Money,
    Price,
    Quantity,
    NonNegativeQuantity,
    Rate,
)


def identity_material(value: Any) -> Any:
    """Normalize bare numeric values before canonical identity serialization."""
    if isinstance(value, float):
        return format(value, ".17g")
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, _CANONICAL_DOMAIN_TYPES):
        return value
    if isinstance(value, tuple | list):
        sequence = cast("tuple[Any, ...] | list[Any]", value)
        return tuple(identity_material(item) for item in sequence)
    if isinstance(value, dict):
        mapping = cast("dict[Any, Any]", value)
        return {str(key): identity_material(item) for key, item in mapping.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: identity_material(getattr(value, field.name))
            for field in fields(value)
        }
    return value


def identity_bytes(value: Any) -> bytes:
    return canonical_bytes(identity_material(value))


def scoped_identity_content_id(value: Any) -> ContentId:
    return scoped_content_id(identity_material(value))
