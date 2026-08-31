"""Strict JSON decoding for untrusted serialized boundaries."""

from __future__ import annotations

import json
from typing import Any


def strict_json_loads(document: str | bytes | bytearray) -> object:
    """Decode JSON while rejecting duplicate object fields at every depth."""
    return json.loads(document, object_pairs_hook=_unique_object)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result
