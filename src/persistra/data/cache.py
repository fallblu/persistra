"""Atomic raw provider response cache."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path

from persistra.errors import CacheError

CACHE_FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class RawCacheEntry:
    """One cached provider response and its raw provenance."""

    body: bytes
    media_type: str
    retrieved_at: datetime
    provider: str
    operation: str
    request_parameters: dict[str, Any]


class RawResponseCache:
    """A versioned, atomic cache of raw provider responses."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or user_cache_path("persistra") / "responses"

    def get(
        self,
        provider: str,
        operation: str,
        parameters: dict[str, Any],
        *,
        now: datetime,
        max_age: timedelta | None,
        offline: bool = False,
    ) -> RawCacheEntry | None:
        """Return a matching fresh entry, or the newest entry offline."""
        path = self._path(provider, operation, parameters)
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["format_version"] != CACHE_FORMAT_VERSION:
                raise ValueError("unsupported cache format")
            entry = RawCacheEntry(
                body=base64.b64decode(document["body"], validate=True),
                media_type=str(document["media_type"]),
                retrieved_at=datetime.fromisoformat(document["retrieved_at"]),
                provider=str(document["provider"]),
                operation=str(document["operation"]),
                request_parameters=dict(document["request_parameters"]),
            )
            if entry.retrieved_at.tzinfo is None:
                raise ValueError("cache time is not timezone-aware")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            if offline:
                raise CacheError(f"corrupt cache entry for {provider} {operation}") from error
            return None
        if offline or (max_age is not None and now - entry.retrieved_at <= max_age):
            return entry
        return None

    def put(self, entry: RawCacheEntry) -> None:
        """Publish one cache entry atomically."""
        if entry.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        parameters = _redact(entry.request_parameters)
        path = self._path(entry.provider, entry.operation, parameters)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "format_version": CACHE_FORMAT_VERSION,
            "body": base64.b64encode(entry.body).decode("ascii"),
            "media_type": entry.media_type,
            "retrieved_at": entry.retrieved_at.astimezone(UTC).isoformat(),
            "provider": entry.provider,
            "operation": entry.operation,
            "request_parameters": parameters,
        }
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(document, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise CacheError(f"could not publish cache entry for {entry.operation}") from error

    def _path(self, provider: str, operation: str, parameters: dict[str, Any]) -> Path:
        identity = json.dumps(
            _redact(parameters), sort_keys=True, separators=(",", ":"), default=str
        )
        digest = sha256(identity.encode()).hexdigest()
        safe_provider = _safe_component(provider)
        safe_operation = _safe_component(operation)
        return self.root / safe_provider / safe_operation / f"{digest}.json"


def _redact(parameters: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in parameters.items() if key.lower() != "apikey"}


def _safe_component(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in "-_" else "_" for character in value
    )
    if not safe:
        raise ValueError("cache path component must not be empty")
    return safe
