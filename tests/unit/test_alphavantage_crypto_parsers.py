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
from persistra.sources.alphavantage.pairs import (
    parse_crypto_daily_bars,
    parse_crypto_intraday_bars,
    utc_day_sessions,
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
_AVAILABLE = datetime(2026, 1, 10, 6, tzinfo=UTC)
_SESSIONS = utc_day_sessions(date(2026, 1, 4), date(2026, 1, 11))


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_crypto_daily_bars_cover_weekends_in_the_quote_currency() -> None:
    bars = parse_crypto_daily_bars(
        _fixture("digital_currency_daily.json"),
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
        currency="EUR",
    )
    assert [bar.session_date for bar in bars] == [
        date(2026, 1, 4),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    sunday = bars[0]
    assert sunday.session_date.weekday() == 6
    assert sunday.state is BarState.COMPLETE
    assert sunday.currency == "EUR"
    assert sunday.interval_start == datetime(2026, 1, 4, tzinfo=UTC)
    assert sunday.interval_end == datetime(2026, 1, 5, tzinfo=UTC)
    assert sunday.volume == Decimal("1500.00")
    assert sunday.availability_quality is AvailabilityQuality.INGESTION_BOUNDED
    zero_volume = bars[1]
    assert zero_volume.state is BarState.NO_VOLUME
    assert zero_volume.volume == Decimal(0)


def test_crypto_intraday_bars_use_utc_fixed_grid() -> None:
    bars = parse_crypto_intraday_bars(
        _fixture("crypto_intraday.json"),
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        interval=timedelta(minutes=5),
        available_at=_AVAILABLE,
        currency="USD",
    )
    assert len(bars) == 2
    first = bars[0]
    assert first.interval_start == datetime(2026, 1, 9, tzinfo=UTC)
    assert first.interval_end == datetime(2026, 1, 9, 0, 5, tzinfo=UTC)
    assert first.session_date == date(2026, 1, 9)
    assert first.state is BarState.COMPLETE
    assert first.volume == Decimal("12.5")


def test_crypto_intraday_bar_ending_at_midnight_closes_the_prior_session() -> None:
    payload = {
        "Meta Data": {"8. Time Zone": "UTC"},
        "Time Series Crypto (5min)": {
            "2026-01-09 00:00:00": {
                "1. open": "90000.0",
                "2. high": "90100.0",
                "3. low": "89900.0",
                "4. close": "90050.0",
                "5. volume": "3.25",
            }
        },
    }
    bars = parse_crypto_intraday_bars(
        payload,
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        interval=timedelta(minutes=5),
        available_at=_AVAILABLE,
        currency="USD",
    )
    assert len(bars) == 1
    assert bars[0].session_date == date(2026, 1, 8)
    assert bars[0].interval_end == datetime(2026, 1, 9, tzinfo=UTC)


def test_crypto_parsers_reject_malformed_payloads() -> None:
    with pytest.raises(SourceResponseError):
        parse_crypto_daily_bars(
            {"Meta Data": {}},
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
            currency="EUR",
        )
    with pytest.raises(SourceResponseError):
        parse_crypto_daily_bars(
            {"Time Series (Digital Currency Daily)": {"nope": {}}},
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
            currency="EUR",
        )
    with pytest.raises(SourceResponseError):
        parse_crypto_intraday_bars(
            _fixture("crypto_intraday.json"),
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            interval=timedelta(0),
            available_at=_AVAILABLE,
            currency="USD",
        )
