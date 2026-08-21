"""Private helpers for validated portable JSON values."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, cast


def freeze_portable_mapping(
    value: Mapping[str, Any],
    *,
    name: str,
    redact_api_keys: bool = False,
) -> Mapping[str, Any]:
    """Copy and recursively freeze one portable JSON mapping."""
    frozen = _freeze_portable(
        value,
        name=name,
        redact_api_keys=redact_api_keys,
        active_containers=set(),
    )
    return cast("Mapping[str, Any]", frozen)


def thaw_portable_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a mutable JSON-compatible copy of one frozen mapping."""
    return cast("dict[str, Any]", _thaw_portable(value))


def _freeze_portable(
    value: object,
    *,
    name: str,
    redact_api_keys: bool,
    active_containers: set[int],
) -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{name} must contain portable JSON values")
        return value
    if isinstance(value, Mapping):
        mapping = cast("Mapping[object, object]", value)
        container = id(mapping)
        if container in active_containers:
            raise ValueError(f"{name} must contain portable JSON values")
        active_containers.add(container)
        try:
            result: dict[str, object] = {}
            for key, item in mapping.items():
                if not isinstance(key, str):
                    raise ValueError(f"{name} must contain portable JSON values")
                if redact_api_keys and _is_api_key(key):
                    continue
                result[key] = _freeze_portable(
                    item,
                    name=name,
                    redact_api_keys=redact_api_keys,
                    active_containers=active_containers,
                )
            return MappingProxyType(result)
        finally:
            active_containers.remove(container)
    if isinstance(value, list | tuple):
        sequence = cast("Sequence[object]", value)
        container = id(sequence)
        if container in active_containers:
            raise ValueError(f"{name} must contain portable JSON values")
        active_containers.add(container)
        try:
            return tuple(
                _freeze_portable(
                    item,
                    name=name,
                    redact_api_keys=redact_api_keys,
                    active_containers=active_containers,
                )
                for item in sequence
            )
        finally:
            active_containers.remove(container)
    raise ValueError(f"{name} must contain portable JSON values")


def _thaw_portable(value: object) -> object:
    if isinstance(value, Mapping):
        mapping = cast("Mapping[str, object]", value)
        return {key: _thaw_portable(item) for key, item in mapping.items()}
    if isinstance(value, tuple):
        sequence = cast("tuple[object, ...]", value)
        return [_thaw_portable(item) for item in sequence]
    return value


def _is_api_key(key: str) -> bool:
    return key.casefold().replace("_", "") == "apikey"
