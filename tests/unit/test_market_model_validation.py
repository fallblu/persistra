from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from persistra.domain import ContentId, Duration, QualifiedName
from persistra.errors import (
    AdjustmentPolicyError,
    BarSpecError,
    CorporateActionTermsError,
    MarketDataQueryError,
    QuoteConditionError,
    TradeConditionError,
    TradingStatusError,
)
from persistra.market.models import (
    ActionLegKind,
    AdjustmentKnowledgeMode,
    AdjustmentPolicyDefinition,
    AdjustmentPolicyRef,
    AdjustmentPriceMode,
    AdjustmentViewRequest,
    Bar,
    BarAlignment,
    BarIntervalKind,
    BarQuery,
    BarSpecDefinition,
    BarSpecId,
    BarSpecRef,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionLeg,
    CorporateActionObservation,
    CorporateActionQuery,
    CorporateActionStatus,
    MarketObservationScope,
    QuoteObservation,
    QuoteScope,
    QuoteState,
    ResolvedBarSpecRef,
    TradeObservation,
    TradeQuery,
    TradingStatus,
    TradingStatusObservation,
    TradingStatusQuery,
)
from persistra.reference import InstrumentId, ResolvedCalendarRef, SecurityId, VenueId
from persistra.reference.models import CalendarId

_START = datetime(2025, 1, 6, 14, 30, tzinfo=UTC)
_END = _START + timedelta(hours=6, minutes=30)
_CONTEXT = cast("Any", None)


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


def test_bar_spec_and_adjustment_policy_validation() -> None:
    session = BarSpecDefinition(QualifiedName("persistra.bar.session.regular"), 1)
    assert session.interval_kind is BarIntervalKind.SESSION
    with pytest.raises(BarSpecError):
        BarSpecDefinition(QualifiedName("persistra.bar.session.regular"), 0)
    with pytest.raises(BarSpecError):
        BarSpecDefinition(
            QualifiedName("persistra.bar.session.regular"),
            1,
            allow_short_final_interval=True,
        )
    with pytest.raises(BarSpecError):
        BarSpecDefinition(
            QualifiedName("persistra.bar.fixed.minute"),
            1,
            interval_kind=BarIntervalKind.FIXED,
            alignment=BarAlignment.UTC_EPOCH,
            nominal_interval=None,
        )
    BarSpecDefinition(
        QualifiedName("persistra.bar.fixed.minute"),
        1,
        interval_kind=BarIntervalKind.FIXED,
        alignment=BarAlignment.UTC_EPOCH,
        nominal_interval=Duration(60_000_000),
    )

    with pytest.raises(AdjustmentPolicyError):
        AdjustmentPolicyRef(QualifiedName("persistra.adjustment.split"), 0)
    with pytest.raises(AdjustmentPolicyError):
        AdjustmentPolicyDefinition(
            QualifiedName("persistra.adjustment.split"),
            0,
            AdjustmentPriceMode.SPLIT,
            AdjustmentKnowledgeMode.POINT_IN_TIME,
        )
    with pytest.raises(AdjustmentPolicyError):
        AdjustmentPolicyDefinition(
            QualifiedName("persistra.adjustment.tr"),
            1,
            AdjustmentPriceMode.TOTAL_RETURN,
            AdjustmentKnowledgeMode.POINT_IN_TIME,
        )
    with pytest.raises(AdjustmentPolicyError):
        AdjustmentPolicyDefinition(
            QualifiedName("persistra.adjustment.split"),
            1,
            AdjustmentPriceMode.SPLIT,
            AdjustmentKnowledgeMode.POINT_IN_TIME,
            cash_distribution_policy=QualifiedName("persistra.adjustment.cash"),
        )


def test_daily_bar_state_scope_and_price_validation() -> None:
    complete = _bar()
    assert complete.observed_through_at == _END
    partial = _bar(
        state=BarState.PARTIAL,
        observed_through_at=_START + timedelta(hours=1),
        available_at=_START + timedelta(hours=1),
    )
    assert partial.state is BarState.PARTIAL
    no_trade = _bar(
        state=BarState.NO_TRADE,
        open=None,
        high=None,
        low=None,
        close=None,
        volume=Decimal(0),
        trade_count=0,
    )
    assert no_trade.volume == 0
    venue = _bar(
        scope=MarketObservationScope.VENUE,
        venue_id=VenueId.new(),
        aggregation_name=None,
        aggregation_version=None,
        aggregation_content_id=None,
    )
    assert venue.scope is MarketObservationScope.VENUE

    with pytest.raises(MarketDataQueryError):
        _bar(observed_through_at=_END + timedelta(hours=1))
    with pytest.raises(MarketDataQueryError):
        _bar(currency="ZZZ")
    no_volume = _bar(state=BarState.NO_VOLUME, volume=Decimal(0), trade_count=None)
    assert no_volume.state is BarState.NO_VOLUME
    assert no_volume.close == Decimal("11")
    with pytest.raises(MarketDataQueryError):
        _bar(state=BarState.NO_VOLUME, trade_count=None)
    with pytest.raises(MarketDataQueryError):
        _bar(state=BarState.NO_VOLUME, volume=Decimal(0), trade_count=3)
    with pytest.raises(MarketDataQueryError):
        _bar(
            state=BarState.NO_VOLUME,
            volume=Decimal(0),
            trade_count=None,
            vwap=Decimal("10.5"),
        )
    with pytest.raises(MarketDataQueryError):
        _bar(
            state=BarState.NO_VOLUME,
            volume=Decimal(0),
            trade_count=None,
            close=None,
        )
    with pytest.raises(MarketDataQueryError):
        _bar(
            state=BarState.NO_VOLUME,
            volume=Decimal(0),
            trade_count=None,
            low=Decimal("13"),
        )
    with pytest.raises(MarketDataQueryError):
        _bar(
            state=BarState.NO_VOLUME,
            volume=Decimal(0),
            trade_count=None,
            available_at=_END - timedelta(hours=1),
        )
    with pytest.raises(MarketDataQueryError):
        _bar(trade_count=-1, volume=Decimal("-1"))
    with pytest.raises(MarketDataQueryError):
        _bar(scope=MarketObservationScope.VENUE, venue_id=VenueId.new())
    with pytest.raises(MarketDataQueryError):
        _bar(venue_id=VenueId.new())
    with pytest.raises(MarketDataQueryError):
        _bar(state=BarState.NO_TRADE, volume=Decimal(0))
    with pytest.raises(MarketDataQueryError):
        _bar(open=Decimal("-1"))
    with pytest.raises(MarketDataQueryError):
        _bar(trade_count=0)
    with pytest.raises(MarketDataQueryError):
        _bar(vwap=Decimal("-1"))
    with pytest.raises(MarketDataQueryError):
        _bar(notional_amount=Decimal("-1"))
    with pytest.raises(MarketDataQueryError):
        _bar(low=Decimal("10.5"))
    with pytest.raises(MarketDataQueryError):
        _bar(available_at=_START)
    with pytest.raises(MarketDataQueryError):
        _bar(
            state=BarState.PARTIAL,
            observed_through_at=_START + timedelta(hours=2),
            available_at=_START + timedelta(hours=1),
        )


def test_market_query_bounds_validation() -> None:
    instrument = InstrumentId.new()
    spec = BarSpecRef(QualifiedName("persistra.bar.session.regular"), 1)
    with pytest.raises(MarketDataQueryError):
        BarQuery((), spec, _START, _END, _CONTEXT)
    with pytest.raises(MarketDataQueryError):
        BarQuery((instrument, instrument), spec, _START, _END, _CONTEXT)
    with pytest.raises(MarketDataQueryError):
        BarQuery((instrument,), spec, _START, _END, _CONTEXT, max_rows=0)
    venue = VenueId.new()
    with pytest.raises(MarketDataQueryError):
        TradeQuery((instrument,), _START, _END, _CONTEXT, venue_ids=(venue, venue))
    with pytest.raises(MarketDataQueryError):
        TradeQuery((instrument,), _START, _END, _CONTEXT, chunk_rows=0)
    TradingStatusQuery((instrument,), _START, _END, _CONTEXT)
    with pytest.raises(MarketDataQueryError):
        CorporateActionQuery((), _START, _END, _CONTEXT)
    with pytest.raises(MarketDataQueryError):
        CorporateActionQuery(
            (instrument,),
            _START,
            _END,
            _CONTEXT,
            statuses=(
                CorporateActionStatus.ANNOUNCED,
                CorporateActionStatus.ANNOUNCED,
            ),
        )
    with pytest.raises(MarketDataQueryError):
        AdjustmentViewRequest(
            BarQuery((instrument,), spec, _START, _END, _CONTEXT),
            AdjustmentPriceMode.SPLIT,
            _START - timedelta(days=1),
        )


def test_trade_observation_validation() -> None:
    def trade(**overrides: object) -> TradeObservation:
        values: dict[str, Any] = {
            "source_trade_key": "trade-1",
            "instrument_id": InstrumentId.new(),
            "venue_id": VenueId.new(),
            "event_at": _START,
            "available_at": _START,
            "source_sequence": 1,
            "price": Decimal("10"),
            "quantity": Decimal("5"),
        }
        values.update(overrides)
        return TradeObservation(**values)

    assert trade().price_forming
    with pytest.raises(TradeConditionError):
        trade(source_trade_key="")
    with pytest.raises(TradeConditionError):
        trade(source_sequence=-1)
    with pytest.raises(TradeConditionError):
        trade(price=Decimal("0"))
    with pytest.raises(TradeConditionError):
        trade(available_at=_START - timedelta(seconds=1))
    with pytest.raises(TradeConditionError):
        trade(trade_condition_codes=("b", "a"))


def test_quote_observation_validation() -> None:
    def quote(**overrides: object) -> QuoteObservation:
        values: dict[str, Any] = {
            "source_quote_key": "quote-1",
            "instrument_id": InstrumentId.new(),
            "event_at": _START,
            "available_at": _START,
            "source_sequence": 1,
            "state": QuoteState.ACTIVE,
            "scope": QuoteScope.CONSOLIDATED_NBBO,
            "bid_price": Decimal("10"),
            "bid_size": Decimal("100"),
            "ask_price": Decimal("10.1"),
            "ask_size": Decimal("50"),
        }
        values.update(overrides)
        return QuoteObservation(**values)

    assert quote().state is QuoteState.ACTIVE
    assert quote(
        scope=QuoteScope.VENUE_TOP, venue_id=VenueId.new()
    ).scope is QuoteScope.VENUE_TOP
    empty = quote(
        state=QuoteState.EMPTY,
        bid_price=None,
        bid_size=None,
        ask_price=None,
        ask_size=None,
    )
    assert empty.bid_price is None
    with pytest.raises(QuoteConditionError):
        quote(source_quote_key="")
    with pytest.raises(QuoteConditionError):
        quote(source_sequence=-1)
    with pytest.raises(QuoteConditionError):
        quote(currency="ZZZ")
    with pytest.raises(QuoteConditionError):
        quote(bid_size=None)
    with pytest.raises(QuoteConditionError):
        quote(bid_price=Decimal("0"))
    with pytest.raises(QuoteConditionError):
        quote(bid_size=Decimal("-1"))
    with pytest.raises(QuoteConditionError):
        quote(state=QuoteState.EMPTY)
    with pytest.raises(QuoteConditionError):
        quote(bid_price=None, bid_size=None, ask_price=None, ask_size=None)
    with pytest.raises(QuoteConditionError):
        quote(scope=QuoteScope.VENUE_TOP)
    with pytest.raises(QuoteConditionError):
        quote(venue_id=VenueId.new())
    with pytest.raises(QuoteConditionError):
        quote(bid_price=None, bid_size=None, bid_venue_id=VenueId.new())
    with pytest.raises(QuoteConditionError):
        quote(quote_condition_codes=("b", "a"))


def test_trading_status_validation() -> None:
    status = TradingStatusObservation(
        InstrumentId.new(), TradingStatus.HALTED, _START, _START
    )
    assert status.status is TradingStatus.HALTED
    with pytest.raises(TradingStatusError):
        TradingStatusObservation(
            InstrumentId.new(),
            TradingStatus.HALTED,
            _START,
            _START,
            source_sequence=-1,
        )
    with pytest.raises(TradingStatusError):
        TradingStatusObservation(
            InstrumentId.new(),
            TradingStatus.HALTED,
            _START,
            _START,
            expected_resume_at=_START,
        )


def _action(**overrides: object) -> CorporateActionObservation:
    values: dict[str, Any] = {
        "action_id": CorporateActionId.new(),
        "kind": CorporateActionKind.SPLIT,
        "subject_security_id": SecurityId.new(),
        "subject_instrument_id": InstrumentId.new(),
        "status": CorporateActionStatus.CONFIRMED,
        "available_at": _START,
        "effective_at": _START,
        "share_ratio": Decimal("2"),
    }
    values.update(overrides)
    return CorporateActionObservation(**values)


def test_corporate_action_terms_validation() -> None:
    assert _action().share_ratio == 2
    cancelled = _action(status=CorporateActionStatus.CANCELLED, share_ratio=None)
    assert cancelled.status is CorporateActionStatus.CANCELLED
    dividend = _action(
        kind=CorporateActionKind.ORDINARY_CASH_DIVIDEND,
        share_ratio=None,
        ex_at=_START,
        cash_per_subject_unit=Decimal("0.25"),
        currency="USD",
    )
    assert dividend.cash_per_subject_unit == Decimal("0.25")
    stock = _action(kind=CorporateActionKind.STOCK_DIVIDEND, share_ratio=Decimal("1.1"))
    assert stock.kind is CorporateActionKind.STOCK_DIVIDEND
    lifecycle = _action(kind=CorporateActionKind.DELISTING, share_ratio=None)
    assert lifecycle.kind is CorporateActionKind.DELISTING
    cash_leg = CorporateActionLeg(
        1,
        ActionLegKind.CASH,
        cash_per_subject_unit=Decimal("1"),
        currency="USD",
    )
    merger = _action(
        kind=CorporateActionKind.MERGER, share_ratio=None, legs=(cash_leg,)
    )
    assert merger.legs == (cash_leg,)
    unresolved_leg = CorporateActionLeg(
        1, ActionLegKind.UNRESOLVED, entitlement_code="pending"
    )
    unresolved = _action(
        kind=CorporateActionKind.UNRESOLVED_ENTITLEMENT,
        share_ratio=None,
        legs=(unresolved_leg,),
    )
    assert unresolved.legs == (unresolved_leg,)

    with pytest.raises(CorporateActionTermsError):
        _action(resolution_method="guessed")
    with pytest.raises(CorporateActionTermsError):
        _action(reference_revision_ids=("b", "a"))
    with pytest.raises(CorporateActionTermsError):
        _action(
            kind=CorporateActionKind.MERGER,
            share_ratio=None,
            legs=(cash_leg, cash_leg),
        )
    with pytest.raises(CorporateActionTermsError):
        _action(share_ratio=None)
    with pytest.raises(CorporateActionTermsError):
        _action(
            kind=CorporateActionKind.ORDINARY_CASH_DIVIDEND,
            share_ratio=None,
            ex_at=_START,
            cash_per_subject_unit=Decimal("0"),
            currency="USD",
        )
    with pytest.raises(CorporateActionTermsError):
        _action(kind=CorporateActionKind.STOCK_DIVIDEND, share_ratio=Decimal("1"))
    with pytest.raises(CorporateActionTermsError):
        _action(
            kind=CorporateActionKind.DELISTING,
            share_ratio=None,
            effective_at=None,
        )
    with pytest.raises(CorporateActionTermsError):
        _action(kind=CorporateActionKind.MERGER, share_ratio=None)
    with pytest.raises(CorporateActionTermsError):
        _action(kind=CorporateActionKind.UNRESOLVED_ENTITLEMENT, share_ratio=None)


def test_corporate_action_leg_validation() -> None:
    security_leg = CorporateActionLeg(
        2,
        ActionLegKind.SECURITY,
        target_security_id=SecurityId.new(),
        quantity_per_subject_unit=Decimal("0.5"),
    )
    assert security_leg.quantity_per_subject_unit == Decimal("0.5")
    with pytest.raises(CorporateActionTermsError):
        CorporateActionLeg(0, ActionLegKind.CASH)
    with pytest.raises(CorporateActionTermsError):
        CorporateActionLeg(
            1,
            ActionLegKind.CASH,
            cash_per_subject_unit=Decimal("1"),
            currency="ZZZ",
        )
    with pytest.raises(CorporateActionTermsError):
        CorporateActionLeg(1, ActionLegKind.SECURITY)
    with pytest.raises(CorporateActionTermsError):
        CorporateActionLeg(1, ActionLegKind.UNRESOLVED)
