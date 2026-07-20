from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.domain import AvailabilityQuality, ContentId
from persistra.errors import SourceResponseError
from persistra.market import BarSpecId, BarState, ResolvedBarSpecRef
from persistra.reference import InstrumentId, ResolvedCalendarRef
from persistra.reference.models import CalendarId
from persistra.sources.alphavantage.equity import (
    parse_daily_equity_bars,
    parse_intraday_equity_bars,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "source" / "alphavantage"

_INSTRUMENT = InstrumentId.new()
_SPEC = ResolvedBarSpecRef(BarSpecId.new(), 1, ContentId.from_bytes(b"spec"))
_CALENDAR = ResolvedCalendarRef(
    CalendarId.new(),
    1,
    ContentId.from_bytes(b"calendar"),
    ContentId.from_bytes(b"schedule"),
)
_AVAILABLE = datetime(2026, 1, 10, tzinfo=UTC)

_SESSIONS = {
    day: (
        datetime(2026, 1, day.day, 14, 30, tzinfo=UTC),
        datetime(2026, 1, day.day, 21, 0, tzinfo=UTC),
    )
    for day in (
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    )
}


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_daily_parser_emits_one_complete_bar_per_covered_session() -> None:
    bars = parse_daily_equity_bars(
        _fixture("time_series_daily.json"),
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
    )
    assert [bar.session_date for bar in bars] == sorted(_SESSIONS)
    first = bars[0]
    assert first.state is BarState.COMPLETE
    assert first.open == Decimal("99.0")
    assert first.close == Decimal("100.0")
    assert first.volume == Decimal("80000")
    assert first.currency == "USD"
    assert first.interval_start == _SESSIONS[date(2026, 1, 2)][0]
    assert first.interval_end == _SESSIONS[date(2026, 1, 2)][1]
    assert first.available_at == _AVAILABLE
    assert first.availability_quality is AvailabilityQuality.INGESTION_BOUNDED
    assert first.trade_count is None


def test_daily_parser_reads_raw_fields_from_the_adjusted_variant() -> None:
    payload = {
        "Meta Data": {"2. Symbol": "IBM"},
        "Time Series (Daily)": {
            "2026-01-09": {
                "1. open": "100.0",
                "2. high": "101.0",
                "3. low": "99.0",
                "4. close": "100.5",
                "5. adjusted close": "50.25",
                "6. volume": "1200",
                "7. dividend amount": "0.0000",
                "8. split coefficient": "2.0",
            }
        },
    }
    bars = parse_daily_equity_bars(
        payload,
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
    )
    assert len(bars) == 1
    assert bars[0].close == Decimal("100.5")
    assert bars[0].volume == Decimal("1200")


def test_intraday_bar_ending_at_session_close_keeps_the_local_session_date() -> None:
    payload = {
        "Meta Data": {"6. Time Zone": "US/Eastern"},
        "Time Series (5min)": {
            "2026-01-09 16:00:00": {
                "1. open": "53.1",
                "2. high": "53.2",
                "3. low": "53.0",
                "4. close": "53.1",
                "5. volume": "500",
            },
            "2026-01-10 00:00:00": {
                "1. open": "53.1",
                "2. high": "53.2",
                "3. low": "53.0",
                "4. close": "53.1",
                "5. volume": "500",
            },
        },
    }
    bars = parse_intraday_equity_bars(
        payload,
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        interval=timedelta(minutes=5),
        available_at=_AVAILABLE,
    )
    assert len(bars) == 1
    assert bars[0].session_date == date(2026, 1, 9)
    assert bars[0].interval_end == datetime(2026, 1, 9, 21, 0, tzinfo=UTC)


def test_daily_parser_skips_sessions_not_yet_final() -> None:
    bars = parse_daily_equity_bars(
        _fixture("time_series_daily.json"),
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        available_at=datetime(2026, 1, 9, 12, tzinfo=UTC),
    )
    assert [bar.session_date for bar in bars] == sorted(_SESSIONS)[:-1]


def test_daily_parser_rejects_malformed_payloads() -> None:
    with pytest.raises(SourceResponseError):
        parse_daily_equity_bars(
            {"Meta Data": {}},
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_daily_equity_bars(
            {"Time Series (Daily)": {"not-a-date": {}}},
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_daily_equity_bars(
            {
                "Time Series (Daily)": {
                    "2026-01-06": {
                        "1. open": "x",
                        "2. high": "1",
                        "3. low": "1",
                        "4. close": "1",
                        "5. volume": "1",
                    }
                }
            },
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
        )


def test_intraday_parser_maps_timestamps_to_utc_fixed_grid() -> None:
    bars = parse_intraday_equity_bars(
        _fixture("time_series_intraday.json"),
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        interval=timedelta(minutes=5),
        available_at=_AVAILABLE,
    )
    assert len(bars) == 3
    first = bars[0]
    assert first.interval_start == datetime(2026, 1, 9, 14, 30, tzinfo=UTC)
    assert first.interval_end == datetime(2026, 1, 9, 14, 35, tzinfo=UTC)
    assert first.session_date == date(2026, 1, 9)
    assert first.state is BarState.COMPLETE
    no_volume = bars[2]
    assert no_volume.state is BarState.NO_VOLUME
    assert no_volume.volume == Decimal(0)
    assert no_volume.close == Decimal("53.9")


def test_intraday_parser_rejects_invalid_shapes() -> None:
    payload = _fixture("time_series_intraday.json")
    with pytest.raises(SourceResponseError):
        parse_intraday_equity_bars(
            payload,
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            interval=timedelta(0),
            available_at=_AVAILABLE,
        )
    broken = dict(payload)
    broken["Meta Data"] = {"6. Time Zone": "Not/AZone"}
    with pytest.raises(SourceResponseError):
        parse_intraday_equity_bars(
            broken,
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            interval=timedelta(minutes=5),
            available_at=_AVAILABLE,
        )
    with pytest.raises(SourceResponseError):
        parse_intraday_equity_bars(
            {
                "Meta Data": {"6. Time Zone": "US/Eastern"},
                "Time Series (5min)": {"nope": {}},
            },
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            interval=timedelta(minutes=5),
            available_at=_AVAILABLE,
        )
