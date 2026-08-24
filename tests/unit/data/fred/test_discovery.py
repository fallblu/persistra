"""Tests for FRED discovery and release-context metadata."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from persistra.data import FredClient
from persistra.errors import CacheError, ResponseError
from persistra.model import CacheStatus, SchemaDiagnostic

FIXTURES = Path(__file__).parents[3] / "fixtures" / "fred"


class Response:
    """Minimal Requests response double."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.status_code = 200
        self.content = json.dumps(payload).encode()
        self.headers = {"Content-Type": "application/json"}


class Session:
    """Queued synchronous session double."""

    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = list(payloads)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: float) -> Response:
        assert timeout == 30
        self.calls.append((url, dict(params)))
        return Response(self.payloads.pop(0))


def fixture(name: str) -> dict[str, Any]:
    """Load one JSON provider fixture."""
    return dict(json.loads((FIXTURES / name).read_text(encoding="utf-8")))


def client(tmp_path: Path, names: list[str]) -> tuple[FredClient, Session]:
    """Create one fixture-backed client and its session."""
    session = Session([fixture(name) for name in names])
    return FredClient("secret", cache_directory=tmp_path, session=session), session


def test_search_paginates_and_preserves_source_metadata(tmp_path: Path) -> None:
    api, session = client(tmp_path, ["search_page_1.json", "search_page_2.json"])

    result = api.discovery.search(
        " real gdp ",
        tag_names=("usa", "quarterly"),
        exclude_tag_names=("discontinued",),
        realtime_start=date(2025, 1, 1),
    )

    assert result.query == "real gdp"
    assert [item.provider_series for item in result.series] == ["GDPC1", "GDPCA"]
    assert result.series[0].observation_start == date(1947, 1, 1)
    assert result.series[0].last_updated == datetime(2025, 1, 30, 13, 55, 1, tzinfo=UTC)
    assert result.series[1].notes is None
    assert result.metadata.operation == "series_search"
    assert result.metadata.request_parameters["tag_names"] == "usa;quarterly"
    assert session.calls[0][0].endswith("/series/search")
    assert session.calls[1][1]["offset"] == 1
    assert "api_key" not in result.metadata.request_parameters


def test_search_caps_provider_result_window_with_diagnostic(tmp_path: Path) -> None:
    template = fixture("search_page_1.json")
    row = dict(template["seriess"][0])
    payloads: list[dict[str, Any]] = []
    for offset in range(0, 5_000, 1_000):
        payload = dict(template)
        payload.update(
            {
                "count": 32_333,
                "offset": offset,
                "seriess": [
                    {**row, "id": f"SERIES_{position}"}
                    for position in range(offset, offset + 1_000)
                ],
            }
        )
        payloads.append(payload)
    session = Session(payloads)
    api = FredClient("secret", cache_directory=tmp_path, session=session)

    result = api.discovery.search("real gross domestic product")

    assert len(result.series) == 5_000
    assert [call[1]["offset"] for call in session.calls] == [0, 1_000, 2_000, 3_000, 4_000]
    assert result.metadata.diagnostics == (
        SchemaDiagnostic(
            "count",
            "provider count exceeds the 5000-item pagination maximum; results were capped",
        ),
    )


def test_categories_and_release_remain_separate_from_observations(tmp_path: Path) -> None:
    api, session = client(tmp_path, ["series_categories.json", "series_release.json"])

    categories = api.discovery.categories("GDPC1")
    release = api.discovery.release("GDPC1", realtime_end="2025-01-01")

    assert [item.category_id for item in categories.categories] == [106, 32992]
    assert categories.categories[0].notes == "Accounts"
    assert release.release.release_id == 53
    assert release.release.press_release
    assert release.release.realtime_start == date(2025, 1, 1)
    assert categories.metadata.operation == "series_categories"
    assert release.metadata.operation == "series_release"
    assert session.calls[0][0].endswith("/series/categories")
    assert session.calls[1][0].endswith("/series/release")


def test_tags_paginate_in_stable_name_order_and_replay_offline(tmp_path: Path) -> None:
    api, session = client(
        tmp_path, ["series_tags_page_1.json", "series_tags_page_2.json"]
    )

    refreshed = api.discovery.tags("GDPC1", refresh=True)
    offline = api.discovery.tags("GDPC1", offline=True)

    assert [item.name for item in refreshed.tags] == ["gdp", "usa"]
    assert refreshed.tags[0].created_at == datetime(2012, 2, 27, 16, 18, 19, tzinfo=UTC)
    assert refreshed.metadata.cache_status is CacheStatus.REFRESHED
    assert offline.tags == refreshed.tags
    assert offline.metadata.cache_status is CacheStatus.OFFLINE
    assert len(session.calls) == 2

    uncached, _ = client(tmp_path / "missing", [])
    with pytest.raises(CacheError, match="offline cache miss"):
        uncached.discovery.tags("GDPC1", offline=True)


def test_discovery_validation_and_schema_diagnostics(tmp_path: Path) -> None:
    api, _ = client(tmp_path, [])
    with pytest.raises(ValueError, match="query must not be empty"):
        api.discovery.search(" ")
    with pytest.raises(ValueError, match="requires tag_names"):
        api.discovery.search("gdp", exclude_tag_names=("discontinued",))
    with pytest.raises(ValueError, match="must not follow"):
        api.discovery.categories(
            "GDP", realtime_start="2025-02-01", realtime_end="2025-01-01"
        )

    changed = fixture("series_categories.json")
    changed["new_provider_field"] = True
    strict = FredClient(
        "secret",
        cache_directory=tmp_path / "strict",
        session=Session([changed]),
        strict_schema=True,
    )
    with pytest.raises(ResponseError, match="unknown provider fields"):
        strict.discovery.categories("GDPC1")
