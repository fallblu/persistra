"""Tests for the atomic raw response cache."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from persistra.data.cache import RawCacheEntry, RawResponseCache
from persistra.errors import CacheError


def test_cache_round_trip_redacts_key_and_honors_age(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    retrieved = datetime(2025, 1, 1, tzinfo=UTC)
    cache.put(
        RawCacheEntry(
            b'{"data": 1}',
            "application/json",
            retrieved,
            "alpha vantage",
            "TIME/SERIES",
            {"symbol": "IBM", "apikey": "secret", "api_key": "also-secret"},
        )
    )
    entry = cache.get(
        "alpha vantage",
        "TIME/SERIES",
        {"symbol": "IBM", "apikey": "different", "api_key": "another"},
        now=retrieved + timedelta(hours=1),
        max_age=timedelta(hours=24),
    )
    assert entry is not None
    assert entry.body == b'{"data": 1}'
    assert entry.request_parameters == {"symbol": "IBM"}
    assert (
        cache.get(
            "alpha vantage",
            "TIME/SERIES",
            {"symbol": "IBM"},
            now=retrieved + timedelta(days=2),
            max_age=timedelta(hours=24),
        )
        is None
    )
    assert (
        cache.get(
            "alpha vantage",
            "TIME/SERIES",
            {"symbol": "IBM"},
            now=retrieved + timedelta(days=2),
            max_age=timedelta(hours=24),
            offline=True,
        )
        is not None
    )


def test_cache_recursively_redacts_one_canonical_parameter_document(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    retrieved = datetime(2025, 1, 1, tzinfo=UTC)
    cache.put(
        RawCacheEntry(
            b"{}",
            "application/json",
            retrieved,
            "demo",
            "request",
            {
                "options": {
                    "api_key": "mapping-secret",
                    "symbol": "AAA",
                    "pages": [{"APIKEY": "sequence-secret", "offset": 0}],
                }
            },
        )
    )

    entry = cache.get(
        "demo",
        "request",
        {
            "options": {
                "api_key": "different-mapping-secret",
                "symbol": "AAA",
                "pages": [{"apikey": "different-sequence-secret", "offset": 0}],
            }
        },
        now=retrieved,
        max_age=timedelta(days=1),
    )

    assert entry is not None
    assert entry.request_parameters == {
        "options": {"symbol": "AAA", "pages": [{"offset": 0}]}
    }
    cache_document = next(tmp_path.rglob("*.json")).read_text(encoding="utf-8")
    assert "secret" not in cache_document
    assert json.loads(cache_document)["request_parameters"] == entry.request_parameters


def test_cache_rejects_nonportable_parameters_before_creating_artifacts(
    tmp_path: Path,
) -> None:
    cache = RawResponseCache(tmp_path)

    with pytest.raises(ValueError, match="portable JSON"):
        cache.put(
            RawCacheEntry(
                b"{}",
                "application/json",
                datetime(2025, 1, 1, tzinfo=UTC),
                "demo",
                "request",
                {"unsupported": object()},
            )
        )

    assert list(tmp_path.iterdir()) == []


def test_cache_miss_corruption_and_validation(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    assert cache.get("p", "o", {}, now=now, max_age=None) is None
    with pytest.raises(ValueError, match="timezone-aware"):
        cache.put(RawCacheEntry(b"x", "text/plain", datetime(2025, 1, 1), "p", "o", {}))
    cache.put(RawCacheEntry(b"x", "text/plain", now, "p", "o", {}))
    path = next(tmp_path.rglob("*.json"))
    path.write_text("not json", encoding="utf-8")
    assert cache.get("p", "o", {}, now=now, max_age=None) is None
    with pytest.raises(CacheError, match="corrupt"):
        cache.get("p", "o", {}, now=now, max_age=None, offline=True)
    with pytest.raises(ValueError, match="component"):
        cache.get("", "o", {}, now=now, max_age=None)
