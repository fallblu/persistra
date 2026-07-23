"""This module contains the opaque, content-derived, and user-facing domain identities."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from abc import ABC
from dataclasses import dataclass
from functools import total_ordering
from typing import ClassVar, Self, cast
from uuid import UUID, uuid4

from persistra.domain.errors import (
    InvalidContentIdError,
    InvalidEntityIdError,
    InvalidQualifiedNameError,
    UnsupportedSchemaVersionError,
)

_UUID_CANONICAL = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_NAME_SEGMENT = re.compile(r"[a-z][a-z0-9_]*")


@total_ordering
@dataclass(frozen=True, slots=True, eq=False, repr=False)
class EntityId(ABC):
    """This class represents the base for strongly typed, opaque RFC 4122 identifiers."""

    _value: UUID
    KIND: ClassVar[str | None] = None

    def __post_init__(self) -> None:
        if self.__class__ is EntityId or self.KIND is None:
            raise TypeError("EntityId is abstract; construct a concrete identifier")
        raw_value = cast("object", self._value)
        if not isinstance(raw_value, UUID) or raw_value.int == 0:
            raise InvalidEntityIdError("identifier must be a nonzero UUID")

    @classmethod
    def new(cls) -> Self:
        """Return a cryptographically random UUIDv4 identifier."""
        return cls(uuid4())

    @classmethod
    def parse(cls, value: object) -> Self:
        """Parse a bare UUID or the wire representation of this concrete type."""
        if isinstance(value, cls):
            return value
        if isinstance(value, EntityId):
            raise InvalidEntityIdError("identifier kind does not match requested type")
        if isinstance(value, UUID):
            return cls(value)
        if not isinstance(value, str):
            raise InvalidEntityIdError("identifier must be UUID or canonical text")
        text = value
        if ":" in text:
            kind, text = text.split(":", 1)
            if kind != cls.KIND:
                raise InvalidEntityIdError("typed identifier kind does not match")
        if _UUID_CANONICAL.fullmatch(text) is None:
            raise InvalidEntityIdError("identifier text is not canonical")
        try:
            parsed = UUID(text)
        except ValueError as error:
            raise InvalidEntityIdError("identifier text is invalid") from error
        return cls(parsed)

    @property
    def value(self) -> UUID:
        """Return the underlying UUID for type-specific database columns."""
        return self._value

    def to_wire(self) -> str:
        """Return the typed canonical representation."""
        return f"{self.KIND}:{self._value}"

    def __str__(self) -> str:
        return self.to_wire()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(kind={self.KIND!r}, value={str(self._value)!r})"

    def __eq__(self, other: object) -> bool:
        return type(self) is type(other) and self._value == cast("EntityId", other).value

    def __lt__(self, other: object) -> bool:
        if type(self) is not type(other):
            raise TypeError("identifiers can only be ordered within one concrete kind")
        assert isinstance(other, EntityId)
        return self._value.int < other._value.int

    def __hash__(self) -> int:
        return hash((type(self), self._value))


class EventId(EntityId):
    """This class represents the opaque identity of an immutable domain event occurrence."""

    KIND: ClassVar[str] = "event"


@dataclass(frozen=True, slots=True)
class ContentId:
    """This class represents the SHA-256 identity of an exact immutable byte sequence."""

    algorithm: str
    digest: bytes

    def __post_init__(self) -> None:
        raw_digest = cast("object", self.digest)
        if self.algorithm != "sha256" or not isinstance(raw_digest, bytes):
            raise InvalidContentIdError("content ID must contain one SHA-256 digest")
        if len(raw_digest) != 32:
            raise InvalidContentIdError("content ID must contain one SHA-256 digest")

    @classmethod
    def from_bytes(cls, value: object) -> Self:
        """Hash exact bytes with SHA-256."""
        if not isinstance(value, bytes):
            raise InvalidContentIdError("content input must be bytes")
        return cls("sha256", hashlib.sha256(value).digest())

    @classmethod
    def parse(cls, value: object) -> Self:
        """Parse ``sha256:<64 lowercase hexadecimal digits>``."""
        if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise InvalidContentIdError("content ID is not canonical SHA-256 text")
        return cls("sha256", bytes.fromhex(value[7:]))

    def to_wire(self) -> str:
        """Return the canonical database and wire representation."""
        return f"sha256:{self.digest.hex()}"

    def __str__(self) -> str:
        return self.to_wire()


@dataclass(frozen=True, slots=True, init=False)
class QualifiedName:
    """This class represents the stable lowercase qualified name for a managed definition."""

    text: str

    def __init__(self, text: object) -> None:
        if not isinstance(text, str):
            raise InvalidQualifiedNameError("qualified name must be text")
        normalized = unicodedata.normalize("NFC", text)
        segments = normalized.split(".")
        valid = (
            1 <= len(normalized) <= 255
            and len(segments) >= 2
            and all(_NAME_SEGMENT.fullmatch(segment) for segment in segments)
            and all(not segment.startswith("_") for segment in segments)
            and not normalized.startswith("persistra._")
            and normalized.isascii()
        )
        if not valid:
            raise InvalidQualifiedNameError("qualified name violates the canonical grammar")
        object.__setattr__(self, "text", normalized)

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True, slots=True, init=False)
class SchemaVersion:
    """This class represents the positive serialized schema contract version."""

    value: int

    def __init__(self, value: object) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 2_147_483_647:
            raise UnsupportedSchemaVersionError("schema version must be a positive 32-bit integer")
        object.__setattr__(self, "value", value)

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)
