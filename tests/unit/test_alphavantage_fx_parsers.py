from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from persistra.domain import AvailabilityQuality, ContentId
from persistra.errors import SourceResponseError
from persistra.market import BarSpecId, BarState, QuoteScope, QuoteState, ResolvedBarSpecRef
from persistra.reference import SYNTHETIC_OTC_VENUE_ID, InstrumentId, ResolvedCalendarRef
from persistra.reference.models import CalendarId
from persistra.sources.alphavantage.pairs import (
    parse_currency_exchange_rate,
    parse_fx_daily_bars,
    parse_fx_intraday_bars,
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
_SESSIONS = utc_day_sessions(date(2026, 1, 4), date(2026, 1, 11), weekdays_only=True)


def _fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        loaded: Any = json.load(handle)
    assert isinstance(loaded, dict)
    return cast("dict[str, Any]", loaded)


def test_fx_daily_bars_are_volume_less_and_skip_weekends() -> None:
    bars = parse_fx_daily_bars(
        _fixture("fx_daily.json"),
        instrument_id=_INSTRUMENT,
        spec=_SPEC,
        calendar=_CALENDAR,
        sessions=_SESSIONS,
        available_at=_AVAILABLE,
        currency="USD",
    )
    assert [bar.session_date for bar in bars] == [
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
    ]
    assert all(bar.session_date.weekday() < 5 for bar in bars)
    first = bars[0]
    assert first.state is BarState.NO_VOLUME
    assert first.volume == Decimal(0)
    assert first.currency == "USD"
    assert first.close == Decimal("1.0829")
    assert first.availability_quality is AvailabilityQuality.INGESTION_BOUNDED


def test_fx_intraday_bars_use_utc_fixed_grid_without_volume() -> None:
    bars = parse_fx_intraday_bars(
        _fixture("fx_intraday.json"),
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
    assert first.state is BarState.NO_VOLUME
    assert first.volume == Decimal(0)


def test_fx_intraday_bar_ending_at_midnight_closes_the_prior_session() -> None:
    payload = {
        "Meta Data": {"6. Time Zone": "UTC"},
        "Time Series FX (5min)": {
            "2026-01-09 00:00:00": {
                "1. open": "1.0800",
                "2. high": "1.0810",
                "3. low": "1.0790",
                "4. close": "1.0805",
            }
        },
    }
    bars = parse_fx_intraday_bars(
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


def test_currency_exchange_rate_becomes_an_indicative_quote() -> None:
    observation = parse_currency_exchange_rate(
        _fixture("currency_exchange_rate.json"),
        instrument_id=_INSTRUMENT,
        available_at=_AVAILABLE,
    )
    assert observation.instrument_id == _INSTRUMENT
    assert observation.event_at == datetime(2026, 1, 9, 21, 55, 1, tzinfo=UTC)
    assert observation.available_at == _AVAILABLE
    assert observation.state is QuoteState.ACTIVE
    assert observation.scope is QuoteScope.VENUE_TOP
    assert observation.venue_id == SYNTHETIC_OTC_VENUE_ID
    assert observation.currency == "USD"
    assert observation.bid_price == Decimal("1.08740000")
    assert observation.ask_price == Decimal("1.08760000")
    assert observation.bid_size == Decimal(0)
    assert observation.ask_size == Decimal(0)
    assert observation.indicative
    assert observation.availability_quality is AvailabilityQuality.INGESTION_BOUNDED


def test_fx_parsers_reject_malformed_payloads() -> None:
    with pytest.raises(SourceResponseError):
        parse_fx_daily_bars(
            {"Meta Data": {}},
            instrument_id=_INSTRUMENT,
            spec=_SPEC,
            calendar=_CALENDAR,
            sessions=_SESSIONS,
            available_at=_AVAILABLE,
            currency="USD",
        )
    with pytest.raises(SourceResponseError):
        parse_currency_exchange_rate(
            {"Realtime Currency Exchange Rate": []},
            instrument_id=_INSTRUMENT,
            available_at=_AVAILABLE,
        )
    bad_zone = _fixture("currency_exchange_rate.json")
    bad_zone["Realtime Currency Exchange Rate"]["7. Time Zone"] = "Not/AZone"
    with pytest.raises(SourceResponseError):
        parse_currency_exchange_rate(
            bad_zone, instrument_id=_INSTRUMENT, available_at=_AVAILABLE
        )
    bad_stamp = _fixture("currency_exchange_rate.json")
    bad_stamp["Realtime Currency Exchange Rate"]["6. Last Refreshed"] = "yesterday"
    with pytest.raises(SourceResponseError):
        parse_currency_exchange_rate(
            bad_stamp, instrument_id=_INSTRUMENT, available_at=_AVAILABLE
        )
