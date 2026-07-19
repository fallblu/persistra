from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.domain import AvailabilityQuality, ContentId, QualifiedName
from persistra.errors import SourceResponseError
from persistra.market import (
    BenchmarkKind,
    BenchmarkSeriesKind,
    ResolvedBenchmarkVersionRef,
)
from persistra.market.economic_models import BenchmarkId
from persistra.reference import CalendarRef
from persistra.sources.alphavantage.indices import (
    index_benchmark_definition,
    parse_index_series,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

_AVAILABLE = datetime(2026, 1, 10, tzinfo=UTC)
_BENCHMARK = ResolvedBenchmarkVersionRef(
    BenchmarkId.new(), 1, ContentId.from_bytes(b"benchmark")
)
_SCHEDULE = ContentId.from_bytes(b"schedule")
_CALENDAR = CalendarRef(QualifiedName("persistra.calendar.xnys"), 1)

_SESSIONS = {
    day: (
        datetime(2026, 1, day.day, 14, 30, tzinfo=UTC),
        datetime(2026, 1, day.day, 21, 0, tzinfo=UTC),
    )
    for day in (date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9))
}


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_index_definition_is_a_source_series_benchmark() -> None:
    calendar = _CALENDAR
    definition = index_benchmark_definition("spx_proxy", calendar=calendar)
    assert str(definition.name) == "alphavantage.index.spx_proxy"
    assert definition.kind is BenchmarkKind.SOURCE_SERIES
    assert definition.instrument_id is None
    assert definition.licensing_class == "licensed_no_redistribution"
    with pytest.raises(SourceResponseError):
        index_benchmark_definition("Bad Slug", calendar=calendar)
    with pytest.raises(SourceResponseError):
        index_benchmark_definition(
            "spx_proxy",
            calendar=calendar,
            series_kind=BenchmarkSeriesKind.PERIOD_RETURN,
        )


def test_index_series_parses_levels_at_session_close() -> None:
    observations = parse_index_series(
        _fixture("index_daily.json"),
        benchmark=_BENCHMARK,
        sessions=_SESSIONS,
        calendar_schedule_content_id=_SCHEDULE,
        available_at=_AVAILABLE,
    )
    assert len(observations) == 3
    latest = observations[-1]
    assert latest.series_kind is BenchmarkSeriesKind.PRICE_INDEX
    assert latest.value.value == Decimal("6132.5")
    assert latest.interval_end == _SESSIONS[date(2026, 1, 9)][1]
    assert latest.interval_start is None
    assert latest.session_date == date(2026, 1, 9)
    assert latest.availability_quality is AvailabilityQuality.INGESTION_BOUNDED


def test_index_series_skips_uncovered_and_unfinal_sessions() -> None:
    observations = parse_index_series(
        _fixture("index_daily.json"),
        benchmark=_BENCHMARK,
        sessions=_SESSIONS,
        calendar_schedule_content_id=_SCHEDULE,
        available_at=datetime(2026, 1, 9, 12, tzinfo=UTC),
    )
    assert [item.session_date for item in observations] == [
        date(2026, 1, 7),
        date(2026, 1, 8),
    ]


def test_index_series_rejects_invalid_payloads() -> None:
    with pytest.raises(SourceResponseError):
        parse_index_series(
            {"Meta Data": {}},
            benchmark=_BENCHMARK,
            sessions=_SESSIONS,
            calendar_schedule_content_id=_SCHEDULE,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_index_series(
            {"Time Series (Daily)": {"nope": {}}},
            benchmark=_BENCHMARK,
            sessions=_SESSIONS,
            calendar_schedule_content_id=_SCHEDULE,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_index_series(
            {"Time Series (Daily)": {"2026-01-09": {"4. close": "0"}}},
            benchmark=_BENCHMARK,
            sessions=_SESSIONS,
            calendar_schedule_content_id=_SCHEDULE,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_index_series(
            _fixture("index_daily.json"),
            benchmark=_BENCHMARK,
            sessions=_SESSIONS,
            calendar_schedule_content_id=_SCHEDULE,
            available_at=_AVAILABLE,
            series_kind=BenchmarkSeriesKind.PERIOD_RETURN,
        )
