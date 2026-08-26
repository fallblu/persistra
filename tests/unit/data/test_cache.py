"""Tests for the atomic raw response cache."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import persistra.data.cache as cache_module
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
    path.write_bytes(b"\xff")
    assert cache.get("p", "o", {}, now=now, max_age=None) is None
    with pytest.raises(CacheError, match="corrupt"):
        cache.get("p", "o", {}, now=now, max_age=None, offline=True)
    with pytest.raises(ValueError, match="component"):
        cache.get("", "o", {}, now=now, max_age=None)


def test_cache_rejects_every_future_timestamp_without_clock_skew(tmp_path: Path) -> None:
    cache = RawResponseCache(tmp_path)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    current = RawCacheEntry(b"current", "text/plain", now, "p", "current", {})
    cache.put(current)
    assert cache.get("p", "current", {}, now=now, max_age=timedelta(0)) == current

    future = RawCacheEntry(
        b"future",
        "text/plain",
        now + timedelta(microseconds=1),
        "p",
        "future",
        {},
    )
    cache.put(future)
    assert cache.get("p", "future", {}, now=now, max_age=timedelta(days=1)) is None
    with pytest.raises(CacheError, match="future-dated raw cache entry for p future"):
        cache.get("p", "future", {}, now=now, max_age=None, offline=True)


def test_cache_missing_directories_and_read_failures_have_cache_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "missing" / "cache"
    cache = RawResponseCache(root)
    now = datetime(2025, 1, 1, tzinfo=UTC)
    assert cache.get("demo", "request", {}, now=now, max_age=None) is None
    cache.put(RawCacheEntry(b"sensitive-body", "text/plain", now, "demo", "request", {}))
    assert root.is_dir()

    def deny_inspection(_path: Path) -> bool:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "is_file", deny_inspection)
    with pytest.raises(CacheError, match="demo request") as inspected:
        cache.get("demo", "request", {}, now=now, max_age=None)
    assert isinstance(inspected.value.__cause__, PermissionError)
    monkeypatch.undo()

    def deny_read(
        _path: Path, encoding: str | None = None, errors: str | None = None
    ) -> str:
        del encoding, errors
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", deny_read)
    with pytest.raises(CacheError, match="demo request") as caught:
        cache.get("demo", "request", {}, now=now, max_age=None)
    assert isinstance(caught.value.__cause__, PermissionError)
    assert "sensitive-body" not in str(caught.value)


def test_cache_wraps_directory_and_temporary_file_creation_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = RawCacheEntry(
        b"sensitive-body",
        "text/plain",
        datetime(2025, 1, 1, tzinfo=UTC),
        "demo",
        "request",
        {"api_key": "secret"},
    )

    def deny_mkdir(
        _path: Path,
        mode: int = 0o777,
        parents: bool = False,
        exist_ok: bool = False,
    ) -> None:
        del mode, parents, exist_ok
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "mkdir", deny_mkdir)
    with pytest.raises(CacheError, match="demo request") as directory:
        RawResponseCache(tmp_path / "directory").put(entry)
    assert isinstance(directory.value.__cause__, PermissionError)
    assert "secret" not in str(directory.value)
    monkeypatch.undo()

    def deny_temporary(*, prefix: str, dir: str | Path) -> tuple[int, str]:
        del prefix, dir
        raise PermissionError("denied")

    monkeypatch.setattr(cache_module.tempfile, "mkstemp", deny_temporary)
    with pytest.raises(CacheError, match="temporary raw cache entry for demo request") as temporary:
        RawResponseCache(tmp_path / "temporary").put(entry)
    assert isinstance(temporary.value.__cause__, PermissionError)


def test_cache_preserves_publication_failure_when_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = RawCacheEntry(
        b"sensitive-body",
        "text/plain",
        datetime(2025, 1, 1, tzinfo=UTC),
        "demo",
        "request",
        {"api_key": "secret"},
    )

    def deny_replace(_path: Path, _target: Path) -> Path:
        raise PermissionError("publication denied")

    def deny_unlink(_path: Path, missing_ok: bool = False) -> None:
        del missing_ok
        raise PermissionError("cleanup denied")

    monkeypatch.setattr(Path, "replace", deny_replace)
    monkeypatch.setattr(Path, "unlink", deny_unlink)
    with pytest.raises(CacheError, match="publish raw cache entry for demo request") as caught:
        RawResponseCache(tmp_path).put(entry)
    assert isinstance(caught.value.__cause__, PermissionError)
    assert caught.value.__notes__ == [
        "temporary file cleanup failed: PermissionError('cleanup denied')"
    ]
    assert "secret" not in str(caught.value)
    assert "sensitive-body" not in str(caught.value)
