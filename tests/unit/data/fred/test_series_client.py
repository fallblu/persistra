"""Tests for focused FRED and ALFRED series acquisition."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pytest

from persistra.analysis import coverage_summary
from persistra.data import FredClient, pivot_series
from persistra.data.fred.client import API_KEY_ENV
from persistra.errors import CacheError, DataValidationError, ResponseError
from persistra.model import CacheStatus, SeriesKind

FIXTURES = Path(__file__).parents[3] / "fixtures" / "fred"


class Response:
    """Minimal Requests response double."""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.status_code = status_code
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


def client(tmp_path: Path, payloads: list[dict[str, Any]]) -> tuple[FredClient, Session]:
    """Create a fixture-backed client and its session."""
    session = Session(payloads)
    return FredClient("secret", cache_directory=tmp_path, session=session), session


def test_definition_and_paginated_latest_observations(tmp_path: Path) -> None:
    api, session = client(
        tmp_path,
        [
            fixture("series.json"),
            fixture("observations_page_1.json"),
            fixture("observations_page_2.json"),
        ],
    )

    result = api.series.latest(
        "GDPC1",
        observation_start=date(2024, 4, 1),
        observation_end="2024-10-01",
    )

    assert result.definition.kind is SeriesKind.ECONOMIC
    assert result.definition.frequency == "quarterly"
    assert result.definition.unit == "Billions of Chained 2017 Dollars"
    assert result.frame["period_label"].tolist() == [
        "2024-04-01",
        "2024-07-01",
        "2024-10-01",
    ]
    assert result.frame.loc[[0, 2], "value"].tolist() == [23000.5, 23500.25]
    assert pd.isna(result.frame.loc[1, "value"])
    assert "is_deleted" not in result.frame
    provider_as_of = datetime(2025, 1, 30, 13, 55, 1, tzinfo=UTC)
    assert result.metadata.provider_as_of == provider_as_of
    assert result.frame["provider_as_of"].eq(provider_as_of).all()
    assert result.frame["retrieved_at"].eq(result.metadata.retrieved_at).all()
    assert session.calls[1][1]["offset"] == 0
    assert session.calls[2][1]["offset"] == 1
    assert all(call[1]["api_key"] == "secret" for call in session.calls)
    assert "api_key" not in result.metadata.request_parameters

    wide = pivot_series([result])
    assert wide.index.tolist() == ["2024-04-01", "2024-07-01", "2024-10-01"]
    assert pd.isna(wide.iloc[1, 0])
    coverage = coverage_summary(wide).iloc[0]
    assert (coverage["count"], coverage["missing"], coverage["coverage"]) == (2, 1, 2 / 3)


def test_definition_method_and_environment_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, _ = client(tmp_path, [fixture("series.json")])
    definition = api.series.definition("GDPC1", realtime_start="2025-01-01")
    assert definition.display_name == "Real Gross Domestic Product"

    monkeypatch.delenv(API_KEY_ENV, raising=False)
    with pytest.raises(ValueError, match=API_KEY_ENV):
        FredClient.from_env()
    monkeypatch.setenv(API_KEY_ENV, "configured")
    assert isinstance(FredClient.from_env(cache_directory=tmp_path / "env"), FredClient)


def test_similarly_named_series_keep_distinct_frequency_and_units(tmp_path: Path) -> None:
    quarterly = fixture("series.json")
    monthly = fixture("series.json")
    monthly_item = cast("dict[str, Any]", cast("list[Any]", monthly["seriess"])[0])
    monthly_item.update(
        {
            "id": "GDP_INDEX",
            "title": "Real Gross Domestic Product Index",
            "frequency": "Monthly",
            "frequency_short": "M",
            "units": "Index 2017=100",
            "units_short": "Index 2017=100",
        }
    )
    api, _ = client(tmp_path, [quarterly, monthly])

    first = api.series.definition("GDPC1")
    second = api.series.definition("GDP_INDEX")

    assert first.series_id != second.series_id
    assert (first.frequency, first.unit) == (
        "quarterly",
        "Billions of Chained 2017 Dollars",
    )
    assert (second.frequency, second.unit) == ("monthly", "Index 2017=100")


def test_bounded_revision_history_normalizes_open_end_and_missing_value(tmp_path: Path) -> None:
    api, session = client(tmp_path, [fixture("series.json"), fixture("vintages.json")])

    result = api.series.vintages("GDPC1", realtime_start="2020-01-01")

    assert len(result.frame) == 3
    assert result.frame["available_from"].is_monotonic_increasing
    history = result.frame[result.frame["period_label"] == "2019-10-01"]
    assert pd.isna(history["available_through"].iloc[-1])
    deletion = result.frame[result.frame["period_label"] == "2020-01-01"].iloc[0]
    assert bool(deletion["is_deleted"])
    assert pd.isna(deletion["value"])
    assert session.calls[1][1]["realtime_end"] == "9999-12-31"


def test_revision_history_paginates_without_losing_intervals(tmp_path: Path) -> None:
    source = fixture("vintages.json")
    source_rows = cast("list[Any]", source["observations"])
    first_page = {**source, "offset": 0, "limit": 1, "observations": source_rows[:1]}
    second_page = {**source, "offset": 1, "observations": source_rows[1:]}
    api, session = client(tmp_path, [fixture("series.json"), first_page, second_page])

    result = api.series.vintages("GDPC1", realtime_start="2020-01-01")

    assert len(result.frame) == 3
    assert session.calls[1][1]["offset"] == 0
    assert session.calls[2][1]["offset"] == 1


def test_explicit_vintages_use_native_parameter(tmp_path: Path) -> None:
    payload = fixture("vintages.json")
    api, session = client(tmp_path, [fixture("series.json"), payload])

    api.series.vintages(
        "GDPC1",
        vintage_dates=[date(2020, 2, 27), "2020-01-30"],
        observation_start="2019-10-01",
    )

    assert session.calls[1][1]["vintage_dates"] == "2020-01-30,2020-02-27"
    assert "realtime_start" not in session.calls[1][1]


def test_vintage_dates_paginate_and_retain_provenance(tmp_path: Path) -> None:
    api, session = client(
        tmp_path,
        [fixture("vintage_dates_page_1.json"), fixture("vintage_dates_page_2.json")],
    )

    result = api.series.vintage_dates("GDPC1")

    assert result.provider_series == "GDPC1"
    assert result.dates == (date(2020, 1, 30), date(2020, 2, 27), date(2020, 3, 26))
    assert result.metadata.operation == "series_vintagedates"
    assert session.calls[1][1]["offset"] == 2


def test_offline_replays_every_required_page(tmp_path: Path) -> None:
    api, session = client(
        tmp_path,
        [
            fixture("series.json"),
            fixture("observations_page_1.json"),
            fixture("observations_page_2.json"),
        ],
    )
    refreshed = api.series.latest("GDPC1", refresh=True)
    offline = api.series.latest("GDPC1", offline=True)

    assert len(session.calls) == 3
    assert refreshed.frame.equals(offline.frame)
    assert refreshed.frame["period_label"].tolist() == [
        "2024-04-01",
        "2024-07-01",
        "2024-10-01",
    ]
    assert pd.isna(offline.frame.loc[1, "value"])
    assert refreshed.metadata.cache_status is CacheStatus.REFRESHED
    assert offline.metadata.cache_status is CacheStatus.OFFLINE

    uncached, _ = client(tmp_path / "empty", [])
    with pytest.raises(CacheError, match="offline cache miss"):
        uncached.series.latest("GDPC1", offline=True)


def test_validation_and_schema_drift(tmp_path: Path) -> None:
    api, _ = client(tmp_path, [])
    with pytest.raises(ValueError, match="required"):
        api.series.vintages("GDPC1")
    with pytest.raises(ValueError, match="mutually exclusive"):
        api.series.vintages(
            "GDPC1", realtime_start="2020-01-01", vintage_dates=["2020-01-01"]
        )
    with pytest.raises(ValueError, match="must not follow"):
        api.series.latest(
            "GDPC1", observation_start="2020-02-01", observation_end="2020-01-01"
        )
    with pytest.raises(ValueError, match="unique"):
        api.series.vintages("GDPC1", vintage_dates=["2020-01-01", "2020-01-01"])

    changed = fixture("series.json")
    changed["provider_new_field"] = "value"
    strict = FredClient(
        "secret",
        cache_directory=tmp_path / "strict",
        session=Session([changed]),
        strict_schema=True,
    )
    with pytest.raises(ResponseError, match="unknown provider fields"):
        strict.series.definition("GDPC1")


def test_conflicting_same_day_revisions_are_rejected(tmp_path: Path) -> None:
    payload = fixture("vintages.json")
    observations = cast("list[Any]", payload["observations"])
    conflicting = dict(observations[-1])
    conflicting["value"] = "1.0"
    observations[-1] = conflicting
    api, _ = client(tmp_path, [fixture("series.json"), payload])

    with pytest.raises(DataValidationError, match="conflicting revisions"):
        api.series.vintages("GDPC1", realtime_start="2020-01-01")
