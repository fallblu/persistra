from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from persistra.domain import ContentId
from persistra.domain.frames import build_frame
from persistra.errors import (
    CorporateActionTermsError,
    QuoteConditionError,
    TradeConditionError,
)
from persistra.market.frames import BARS_FRAME
from persistra.market.models import (
    ActionLegKind,
    Bar,
    BarSpecId,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionLeg,
    CorporateActionObservation,
    CorporateActionStatus,
    QuoteObservation,
    QuoteScope,
    QuoteState,
    ResolvedBarSpecRef,
    TradeObservation,
)
from persistra.reference import InstrumentId, ResolvedCalendarRef, SecurityId, VenueId
from persistra.reference.models import CalendarId

_START = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
_END = _START + timedelta(hours=6, minutes=30)


def _bar(**overrides: object) -> Bar:
    values: dict[str, Any] = {
        "instrument_id": InstrumentId.new(),
        "spec": ResolvedBarSpecRef(BarSpecId.new(), 1, ContentId.from_bytes(b"spec")),
        "calendar": ResolvedCalendarRef(
            CalendarId.new(),
            1,
            ContentId.from_bytes(b"calendar"),
            ContentId.from_bytes(b"schedule"),
        ),
        "interval_start": _START,
        "interval_end": _END,
        "session_date": date(2025, 1, 6),
        "state": BarState.COMPLETE,
        "currency": "USD",
        "open": Decimal("10"),
        "high": Decimal("12"),
        "low": Decimal("9"),
        "close": Decimal("11"),
        "volume": Decimal("1000"),
        "trade_count": 25,
        "available_at": _END,
    }
    values.update(overrides)
    return Bar(**values)


def _trade(**overrides: object) -> TradeObservation:
    values: dict[str, Any] = {
        "source_trade_key": "trade-1",
        "instrument_id": InstrumentId.new(),
        "venue_id": VenueId.new(),
        "event_at": _START,
        "available_at": _START,
        "source_sequence": 1,
        "price": Decimal("10"),
        "quantity": Decimal("100"),
    }
    values.update(overrides)
    return TradeObservation(**values)


def _quote(**overrides: object) -> QuoteObservation:
    values: dict[str, Any] = {
        "source_quote_key": "quote-1",
        "instrument_id": InstrumentId.new(),
        "event_at": _START,
        "available_at": _START,
        "source_sequence": 1,
        "state": QuoteState.ACTIVE,
        "scope": QuoteScope.CONSOLIDATED_NBBO,
        "bid_price": Decimal("10"),
        "bid_size": Decimal("5"),
        "ask_price": Decimal("11"),
        "ask_size": Decimal("5"),
    }
    values.update(overrides)
    return QuoteObservation(**values)


@pytest.mark.parametrize("currency", ["EUR", "JPY", "GBP"])
def test_bars_accept_registered_non_usd_currencies(currency: str) -> None:
    assert _bar(currency=currency).currency == currency


@pytest.mark.parametrize("currency", ["EUR", "JPY", "GBP"])
def test_trades_accept_registered_non_usd_currencies(currency: str) -> None:
    assert _trade(currency=currency).currency == currency


@pytest.mark.parametrize("currency", ["EUR", "JPY", "GBP"])
def test_quotes_accept_registered_non_usd_currencies(currency: str) -> None:
    assert _quote(currency=currency).currency == currency


def test_unregistered_currencies_still_raise() -> None:
    with pytest.raises(TradeConditionError):
        _trade(currency="ZZZ")
    with pytest.raises(QuoteConditionError):
        _quote(currency="ZZ")


def test_cash_dividend_accepts_non_usd_currency() -> None:
    observation = CorporateActionObservation(
        action_id=CorporateActionId.new(),
        kind=CorporateActionKind.ORDINARY_CASH_DIVIDEND,
        subject_security_id=SecurityId.new(),
        subject_instrument_id=None,
        status=CorporateActionStatus.CONFIRMED,
        available_at=_START,
        ex_at=_START,
        cash_per_subject_unit=Decimal("0.75"),
        currency="EUR",
    )
    assert observation.currency == "EUR"
    with pytest.raises(CorporateActionTermsError):
        CorporateActionObservation(
            action_id=CorporateActionId.new(),
            kind=CorporateActionKind.ORDINARY_CASH_DIVIDEND,
            subject_security_id=SecurityId.new(),
            subject_instrument_id=None,
            status=CorporateActionStatus.CONFIRMED,
            available_at=_START,
            ex_at=_START,
            cash_per_subject_unit=Decimal("0.75"),
            currency="ZZZ",
        )


def test_cash_action_leg_accepts_non_usd_currency() -> None:
    leg = CorporateActionLeg(
        1,
        ActionLegKind.CASH,
        cash_per_subject_unit=Decimal("2"),
        currency="GBP",
    )
    assert leg.currency == "GBP"
    with pytest.raises(CorporateActionTermsError):
        CorporateActionLeg(
            1,
            ActionLegKind.CASH,
            cash_per_subject_unit=Decimal("2"),
            currency=None,
        )


def test_bars_frame_carries_non_usd_currency() -> None:
    bar = _bar(currency="JPY")
    row: dict[str, Any] = {
        "canonical_revision_id": "revision-1",
        "instrument_id": str(bar.instrument_id),
        "bar_spec_id": str(bar.spec.bar_spec_id),
        "bar_spec_version": bar.spec.version,
        "source_id": "source-1",
        "observation_scope": bar.scope.value,
        "venue_id": None,
        "aggregation_name": None if bar.aggregation_name is None else str(bar.aggregation_name),
        "aggregation_version": bar.aggregation_version,
        "aggregation_content_id": (
            None if bar.aggregation_content_id is None else str(bar.aggregation_content_id)
        ),
        "interval_start": bar.interval_start,
        "interval_end": bar.interval_end,
        "observed_through_at": bar.observed_through_at,
        "session_date": bar.session_date,
        "bar_phase": bar.phase.value,
        "calendar_schedule_content_id": (
            None
            if bar.calendar_schedule_content_id is None
            else str(bar.calendar_schedule_content_id)
        ),
        "bar_state": bar.state.value,
        "currency": bar.currency,
        "open": None if bar.open is None else float(bar.open),
        "high": None if bar.high is None else float(bar.high),
        "low": None if bar.low is None else float(bar.low),
        "close": None if bar.close is None else float(bar.close),
        "volume": float(bar.volume),
        "vwap": None,
        "notional_amount": None,
        "trade_count": bar.trade_count,
        "available_at": bar.available_at,
        "availability_quality": bar.availability_quality.value,
        "warning_codes": [],
    }
    frame = build_frame(BARS_FRAME, [row])
    assert list(frame["currency"]) == ["JPY"]
