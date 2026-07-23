"""This module contains the bounded immutable-data dashboard cache."""

from __future__ import annotations

import copy
from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from persistra._identity import scoped_identity_content_id as scoped_content_id

if TYPE_CHECKING:
    from persistra.domain import ContentId


@dataclass(frozen=True, slots=True)
class DashboardCacheKey:
    source_fingerprint: ContentId
    subject_root: ContentId
    page: str
    query_content_id: ContentId
    renderer_version: str = "persistra.dashboard.renderer@1"

    @classmethod
    def build(
        cls,
        *,
        source_fingerprint: ContentId,
        subject_root: ContentId,
        page: str,
        parameters: dict[str, Any],
    ) -> DashboardCacheKey:
        return cls(
            source_fingerprint,
            subject_root,
            page,
            scoped_content_id(
                {
                    "schema": "persistra.dashboard.page_query@1",
                    "page": page,
                    "parameters": parameters,
                }
            ),
        )


class DashboardDataCache:
    """This class represents the LRU cache. It does not keep projects, connections, or
    service handles."""

    __slots__ = ("_entries", "_max_bytes", "_max_entries", "_size")

    def __init__(self, *, max_entries: int, max_bytes: int) -> None:
        self._entries: OrderedDict[DashboardCacheKey, tuple[int, Any]] = OrderedDict()
        self._max_entries = max_entries
        self._max_bytes = max_bytes
        self._size = 0

    def get(self, key: DashboardCacheKey) -> Any | None:
        entry = self._entries.pop(key, None)
        if entry is None:
            return None
        self._entries[key] = entry
        return copy.deepcopy(entry[1])

    def put(self, key: DashboardCacheKey, value: Any, *, byte_count: int) -> None:
        if byte_count > self._max_bytes:
            return
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._size -= previous[0]
        self._entries[key] = (byte_count, copy.deepcopy(value))
        self._size += byte_count
        while len(self._entries) > self._max_entries or self._size > self._max_bytes:
            _discarded_key, (size, _discarded) = self._entries.popitem(last=False)
            self._size -= size

    def clear(self) -> None:
        self._entries.clear()
        self._size = 0
