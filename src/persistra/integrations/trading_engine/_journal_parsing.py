"""Low-level parsing primitives for Trading Engine audit journals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from persistra._json import strict_json_loads

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping


@dataclass(frozen=True, slots=True)
class JournalRecordContext:
    """Location and stable identifiers known for one journal record."""

    line_number: int
    engine_sequence: object | None = None
    event_id: object | None = None
    event_type: object | None = None

    @classmethod
    def from_record(
        cls,
        line_number: int,
        record: Mapping[str, object] | None = None,
    ) -> JournalRecordContext:
        """Build context without validating untrusted record fields."""
        if record is None:
            return cls(line_number=line_number)
        return cls(
            line_number=line_number,
            engine_sequence=record.get("engine_sequence"),
            event_id=record.get("event_id"),
            event_type=record.get("event_type"),
        )

    def describe(self) -> str:
        """Return bounded location text without including payload values."""
        details = [f"line {self.line_number}"]
        if (
            isinstance(self.engine_sequence, int)
            and not isinstance(self.engine_sequence, bool)
        ) or (
            isinstance(self.engine_sequence, str) and self.engine_sequence.isdigit()
        ):
            details.append(f"engine_sequence {self.engine_sequence}")
        if isinstance(self.event_id, str):
            details.append(f"event_id {self.event_id!r}")
        if isinstance(self.event_type, str):
            details.append(f"event_type {self.event_type!r}")
        return ", ".join(details)


class JournalValidationError(ValueError):
    """A journal validation failure with record location context."""

    def __init__(self, message: str, *, context: JournalRecordContext) -> None:
        self.context = context
        super().__init__(f"{context.describe()}: {message}")


@dataclass(slots=True)
class JournalContextTracker:
    """Track the record active while the importer validates it."""

    current: JournalRecordContext | None = None

    def select(
        self,
        line_number: int,
        record: Mapping[str, object] | None = None,
    ) -> None:
        """Select the active record without retaining its payload."""
        self.current = JournalRecordContext.from_record(line_number, record)


def json_record(document: str, *, line_number: int) -> dict[str, object]:
    """Decode one strict JSON object and attach its line on failure."""
    context = JournalRecordContext(line_number=line_number)
    try:
        value = strict_json_loads(document)
    except json.JSONDecodeError as error:
        raise JournalValidationError(
            f"invalid journal JSON: {error.msg}", context=context
        ) from error
    except ValueError as error:
        raise JournalValidationError(str(error), context=context) from error
    if not isinstance(value, dict):
        raise JournalValidationError("journal record must be an object", context=context)
    return cast("dict[str, object]", value)


def iter_json_records(path: str | Path) -> Iterator[tuple[int, dict[str, object]]]:
    """Yield strict JSON Lines records without retaining the file text or line list."""
    journal_path = Path(path)
    with journal_path.open("rb") as stream:
        for line_number, encoded_line in enumerate(stream, start=1):
            if not encoded_line.removesuffix(b"\n").removesuffix(b"\r"):
                context = JournalRecordContext(line_number=line_number)
                raise JournalValidationError(
                    "audit journal must not contain blank records",
                    context=context,
                )
    with journal_path.open("rb") as stream:
        for line_number, encoded_line in enumerate(stream, start=1):
            encoded_document = encoded_line.removesuffix(b"\n").removesuffix(b"\r")
            context = JournalRecordContext(line_number=line_number)
            try:
                document = encoded_document.decode("utf-8")
            except UnicodeDecodeError as error:
                raise JournalValidationError(
                    "audit journal must contain valid UTF-8", context=context
                ) from error
            yield line_number, json_record(document, line_number=line_number)


def array(value: object, *, name: str) -> list[object]:
    """Require a JSON array."""
    if not isinstance(value, list):
        raise ValueError(f"{name} must be an array")
    return cast("list[object]", value)


def freeze_payload(value: object) -> object:
    """Recursively freeze a validated JSON payload."""
    if isinstance(value, dict):
        return MappingProxyType(
            {
                str(key): freeze_payload(item)
                for key, item in cast("dict[object, object]", value).items()
            }
        )
    if isinstance(value, list):
        return tuple(freeze_payload(item) for item in cast("list[object]", value))
    return value


def sha256_value(value: object, *, name: str) -> str:
    """Require a lowercase SHA-256 value."""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest") from error
    if value != value.lower():
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def optional_sha256(value: str | None, *, name: str) -> str | None:
    """Validate an optional SHA-256 value."""
    return None if value is None else sha256_value(value, name=name)
