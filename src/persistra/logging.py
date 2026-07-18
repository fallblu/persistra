"""Bounded structured logging with deterministic redaction."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import structlog

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.errors import DomainValidationError, PersistraError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from persistra.db.connection import ManagedConnection
    from persistra.simulation import RunRecordId

_SENSITIVE_FRAGMENTS = (
    "authorization",
    "credential",
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "cookie",
)
_PATH_FRAGMENTS = ("path", "directory", "filename", "root", "uri", "url")
_PAYLOAD_FRAGMENTS = ("payload", "frame", "rows", "query", "sql", "locals")
_MAX_CONTEXT_KEYS = 32
_MAX_SEQUENCE_ITEMS = 16
_MAX_STRING_LENGTH = 256


@dataclass(frozen=True, slots=True)
class StructuredLogEntry:
    severity: str
    component: str
    event_name: str
    reason_code: str
    context: Mapping[str, object]

    def __post_init__(self) -> None:
        if (
            self.severity not in {"debug", "info", "warning", "error"}
            or not self.component
            or not self.event_name
            or not self.reason_code
        ):
            raise DomainValidationError("structured log entry is invalid")


def configure_logging(*, json_output: bool = True, level: int = logging.INFO) -> None:
    """Configure deterministic structured logs for command-line workflows."""
    renderer: Any = structlog.processors.JSONRenderer(sort_keys=True)
    if not json_output:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        cache_logger_on_first_use=True,
    )


def safe_log_context(context: Mapping[str, object]) -> dict[str, object]:
    """Return deterministic bounded context with secrets, paths, and payloads removed."""
    return {
        str(key)[:64]: _safe_value(str(key), value, depth=0)
        for key, value in sorted(context.items(), key=lambda item: str(item[0]))[
            :_MAX_CONTEXT_KEYS
        ]
    }


def safe_error(error: BaseException) -> dict[str, object]:
    """Map an exception to safe CLI/log evidence without copying its message."""
    if isinstance(error, PersistraError):
        context = getattr(error, "context", {})
        return {
            "error_type": type(error).__name__,
            "reason_code": error.reason_code,
            "context": safe_log_context(context),
        }
    return {
        "error_type": type(error).__name__,
        "reason_code": "internal.unexpected",
        "context": {},
    }


def persist_run_logs(
    connection: ManagedConnection,
    run_id: RunRecordId,
    occurred_at: datetime,
    entries: Sequence[StructuredLogEntry],
) -> None:
    """Persist an ordered immutable set of safe run lifecycle logs."""
    rows: list[tuple[object, ...]] = []
    for ordinal, entry in enumerate(entries, 1):
        context = safe_log_context(entry.context)
        context_content_id = scoped_content_id(
            {
                "schema": "persistra.results.log_context@1",
                "run_record_id": run_id,
                "log_ordinal": ordinal,
                "context": context,
            }
        )
        rows.append(
            (
                run_id.value,
                ordinal,
                occurred_at,
                entry.severity,
                entry.component,
                entry.event_name,
                entry.reason_code,
                json.dumps(
                    context,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                str(context_content_id),
            )
        )
    if rows:
        connection.executemany(
            "INSERT INTO result_data.logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


def _safe_value(key: str, value: object, *, depth: int) -> object:
    normalized = key.casefold()
    if any(fragment in normalized for fragment in _SENSITIVE_FRAGMENTS):
        return "[REDACTED]"
    if any(fragment in normalized for fragment in _PATH_FRAGMENTS):
        return "[PATH]"
    if any(fragment in normalized for fragment in _PAYLOAD_FRAGMENTS):
        return "[OMITTED]"
    if depth >= 2:
        return "[BOUNDED]"
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value[:_MAX_STRING_LENGTH]
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return {
            str(child_key)[:64]: _safe_value(
                str(child_key), child_value, depth=depth + 1
            )
            for child_key, child_value in sorted(
                mapping.items(), key=lambda item: str(item[0])
            )[:_MAX_CONTEXT_KEYS]
        }
    if isinstance(value, list | tuple):
        sequence = cast("list[object] | tuple[object, ...]", value)
        return [
            _safe_value(key, item, depth=depth + 1)
            for item in sequence[:_MAX_SEQUENCE_ITEMS]
        ]
    return str(value)[:_MAX_STRING_LENGTH]


__all__ = [
    "StructuredLogEntry",
    "configure_logging",
    "persist_run_logs",
    "safe_error",
    "safe_log_context",
]
