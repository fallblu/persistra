"""Alpha Vantage equity endpoint parsers producing canonical domain objects.

Parsers are pure: they turn decoded endpoint payloads into typed domain
objects and never talk to the network or a database. Raw OHLCV plus corporate
actions are ingested so persistra's adjustment engine derives adjusted series;
Alpha Vantage's pre-adjusted closes are deliberately not treated as canonical.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast
from zoneinfo import ZoneInfo

from persistra.domain import AvailabilityQuality
from persistra.domain.time import validate_instant
from persistra.errors import SourceResponseError
from persistra.market import (
    Bar,
    BarState,
    CorporateActionId,
    CorporateActionKind,
    CorporateActionObservation,
    CorporateActionStatus,
    TradingStatus,
    TradingStatusObservation,
)
from persistra.reference import ListingStatus
from persistra.sources.alphavantage._parsing import (
    decimal_value,
    derived_entity_id,
    json_object,
    series_field,
    series_payload,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from persistra.market import ResolvedBarSpecRef
    from persistra.reference import InstrumentId, ResolvedCalendarRef, SecurityId


def _bar_state_and_volume(volume: Decimal) -> tuple[BarState, Decimal]:
    if volume < 0:
        raise SourceResponseError("alpha vantage volume is negative")
    if volume == 0:
        return BarState.NO_VOLUME, Decimal(0)
    return BarState.COMPLETE, volume


def parse_daily_equity_bars(
    payload: dict[str, Any],
    *,
    instrument_id: InstrumentId,
    spec: ResolvedBarSpecRef,
    calendar: ResolvedCalendarRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    available_at: datetime,
    currency: str = "USD",
) -> tuple[Bar, ...]:
    """Parse ``TIME_SERIES_DAILY`` (or the adjusted variant) into session bars.

    Only dates present in ``sessions`` are emitted; a session whose close is
    after ``available_at`` is skipped because its bar is not yet final.
    """
    validate_instant(available_at)
    series = series_payload(payload, "Time Series (Daily)")
    bars: list[Bar] = []
    for raw_date in sorted(series):
        try:
            session_date = date.fromisoformat(raw_date)
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage daily series key is not a date"
            ) from cause
        session = sessions.get(session_date)
        if session is None:
            continue
        open_at, close_at = session
        if close_at > available_at:
            continue
        row = json_object(series[raw_date], f"daily row {raw_date}")
        volume = decimal_value(series_field(row, "volume", "volume"), "daily volume")
        state, volume = _bar_state_and_volume(volume)
        bars.append(
            Bar(
                instrument_id,
                spec,
                calendar,
                open_at,
                close_at,
                session_date,
                state,
                currency,
                decimal_value(series_field(row, "1. open", "open"), "daily open"),
                decimal_value(series_field(row, "2. high", "high"), "daily high"),
                decimal_value(series_field(row, "3. low", "low"), "daily low"),
                decimal_value(series_field(row, "4. close", "close"), "daily close"),
                volume,
                None,
                available_at,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(bars)


def parse_intraday_equity_bars(
    payload: dict[str, Any],
    *,
    instrument_id: InstrumentId,
    spec: ResolvedBarSpecRef,
    calendar: ResolvedCalendarRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    interval: timedelta,
    available_at: datetime,
    currency: str = "USD",
) -> tuple[Bar, ...]:
    """Parse ``TIME_SERIES_INTRADAY`` into fixed-grid bars.

    Series timestamps are interpreted as interval ends in the payload's
    reported time zone. Rows outside a provided session's regular phase, and
    rows not yet final at ``available_at``, are skipped.
    """
    validate_instant(available_at)
    if interval <= timedelta(0):
        raise SourceResponseError("alpha vantage intraday interval must be positive")
    meta = json_object(payload.get("Meta Data"), "intraday metadata")
    timezone_name = str(series_field(meta, "Time Zone", "time zone"))
    try:
        zone = ZoneInfo(timezone_name)
    except (KeyError, ValueError) as cause:
        raise SourceResponseError(
            "alpha vantage intraday time zone is unknown"
        ) from cause
    series = series_payload(payload, "Time Series (")
    bars: list[Bar] = []
    for raw_stamp in sorted(series):
        try:
            local_end = datetime.strptime(raw_stamp, "%Y-%m-%d %H:%M:%S")
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage intraday series key is not a timestamp"
            ) from cause
        interval_end = local_end.replace(tzinfo=zone).astimezone(ZoneInfo("UTC"))
        interval_start = interval_end - interval
        # Regular equity sessions never cross local midnight, so the bar's
        # exchange-local end date identifies its session.
        session_date = local_end.date()
        session = sessions.get(session_date)
        if session is None:
            continue
        open_at, close_at = session
        if interval_start < open_at or interval_end > close_at:
            continue
        if interval_end > available_at:
            continue
        row = json_object(series[raw_stamp], f"intraday row {raw_stamp}")
        volume = decimal_value(series_field(row, "volume", "volume"), "intraday volume")
        state, volume = _bar_state_and_volume(volume)
        bars.append(
            Bar(
                instrument_id,
                spec,
                calendar,
                interval_start,
                interval_end,
                session_date,
                state,
                currency,
                decimal_value(series_field(row, "1. open", "open"), "intraday open"),
                decimal_value(series_field(row, "2. high", "high"), "intraday high"),
                decimal_value(series_field(row, "3. low", "low"), "intraday low"),
                decimal_value(series_field(row, "4. close", "close"), "intraday close"),
                volume,
                None,
                available_at,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(bars)


def _action_id(key: str) -> CorporateActionId:
    return derived_entity_id(CorporateActionId, key)


def _effective_instant(
    value: date, sessions: Mapping[date, tuple[datetime, datetime]]
) -> datetime:
    session = sessions.get(value)
    if session is not None:
        return session[0]
    return datetime(value.year, value.month, value.day, tzinfo=ZoneInfo("UTC"))


def _action_rows(payload: dict[str, Any], endpoint: str) -> tuple[str, list[Any]]:
    symbol = str(payload.get("symbol", ""))
    if not symbol:
        raise SourceResponseError(f"alpha vantage {endpoint} payload lacks a symbol")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise SourceResponseError(f"alpha vantage {endpoint} payload lacks data rows")
    return symbol, cast("list[Any]", rows)


def parse_splits(
    payload: dict[str, Any],
    *,
    security_id: SecurityId,
    instrument_id: InstrumentId,
    sessions: Mapping[date, tuple[datetime, datetime]],
    available_at: datetime,
) -> tuple[CorporateActionObservation, ...]:
    """Parse the ``SPLITS`` endpoint into split and reverse-split actions."""
    validate_instant(available_at)
    symbol, rows = _action_rows(payload, "SPLITS")
    actions: list[CorporateActionObservation] = []
    for raw in rows:
        row = json_object(raw, "split row")
        try:
            effective_date = date.fromisoformat(str(row.get("effective_date")))
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage split effective date is invalid"
            ) from cause
        factor = decimal_value(row.get("split_factor"), "split factor")
        if factor <= 0:
            raise SourceResponseError("alpha vantage split factor must be positive")
        if factor == 1:
            continue
        kind = (
            CorporateActionKind.SPLIT
            if factor > 1
            else CorporateActionKind.REVERSE_SPLIT
        )
        key = f"alphavantage:{symbol}:split:{effective_date.isoformat()}"
        actions.append(
            CorporateActionObservation(
                _action_id(key),
                kind,
                security_id,
                instrument_id,
                CorporateActionStatus.COMPLETED,
                available_at,
                effective_at=_effective_instant(effective_date, sessions),
                effective_date=effective_date,
                share_ratio=factor,
                source_action_key=key,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(actions)


def parse_dividends(
    payload: dict[str, Any],
    *,
    security_id: SecurityId,
    instrument_id: InstrumentId,
    sessions: Mapping[date, tuple[datetime, datetime]],
    available_at: datetime,
    currency: str = "USD",
) -> tuple[CorporateActionObservation, ...]:
    """Parse the ``DIVIDENDS`` endpoint into ordinary cash dividend actions."""
    validate_instant(available_at)
    symbol, rows = _action_rows(payload, "DIVIDENDS")
    actions: list[CorporateActionObservation] = []
    for raw in rows:
        row = json_object(raw, "dividend row")
        try:
            ex_date = date.fromisoformat(str(row.get("ex_dividend_date")))
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage dividend ex date is invalid"
            ) from cause
        amount = decimal_value(row.get("amount"), "dividend amount")
        if amount <= 0:
            continue
        payable = row.get("payment_date")
        payable_date: date | None = None
        if isinstance(payable, str) and payable not in {"", "None", "null"}:
            try:
                payable_date = date.fromisoformat(payable)
            except ValueError as cause:
                raise SourceResponseError(
                    "alpha vantage dividend payment date is invalid"
                ) from cause
        key = f"alphavantage:{symbol}:dividend:{ex_date.isoformat()}"
        actions.append(
            CorporateActionObservation(
                _action_id(key),
                CorporateActionKind.ORDINARY_CASH_DIVIDEND,
                security_id,
                instrument_id,
                CorporateActionStatus.COMPLETED,
                available_at,
                ex_at=_effective_instant(ex_date, sessions),
                ex_date=ex_date,
                payable_date=payable_date,
                cash_per_subject_unit=amount,
                currency=currency,
                source_action_key=key,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(actions)


_MARKET_STATUS = {
    "open": TradingStatus.TRADING,
    "closed": TradingStatus.CLOSED,
}


def parse_market_status(
    payload: dict[str, Any],
    *,
    region: str,
    market_type: str,
    instruments: tuple[InstrumentId, ...],
    effective_at: datetime,
    available_at: datetime,
) -> tuple[TradingStatusObservation, ...]:
    """Map one region's ``MARKET_STATUS`` entry onto the given instruments."""
    validate_instant(effective_at)
    validate_instant(available_at)
    markets = payload.get("markets")
    if not isinstance(markets, list):
        raise SourceResponseError("alpha vantage market status payload is malformed")
    for raw in cast("list[Any]", markets):
        market = json_object(raw, "market status row")
        if (
            str(market.get("region", "")) != region
            or str(market.get("market_type", "")) != market_type
        ):
            continue
        status = _MARKET_STATUS.get(
            str(market.get("current_status", "")).lower(), TradingStatus.UNKNOWN
        )
        return tuple(
            TradingStatusObservation(
                instrument_id,
                status,
                effective_at,
                available_at,
                source_status_key=(
                    f"alphavantage:market_status:{market_type}:{region}:"
                    f"{effective_at.isoformat()}"
                ),
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
            for instrument_id in instruments
        )
    raise SourceResponseError(
        f"alpha vantage market status lacks the {region} {market_type} market"
    )


@dataclass(frozen=True, slots=True)
class ListingStatusRecord:
    """One row of the ``LISTING_STATUS`` CSV endpoint."""

    symbol: str
    name: str
    exchange: str
    asset_type: str
    ipo_date: date | None
    delisting_date: date | None
    status: ListingStatus


def _optional_date(raw: str | None) -> date | None:
    text = (raw or "").strip()
    if not text or text.lower() == "null":
        return None
    try:
        return date.fromisoformat(text)
    except ValueError as cause:
        raise SourceResponseError("alpha vantage listing date is invalid") from cause


def parse_listing_status(csv_text: str) -> tuple[ListingStatusRecord, ...]:
    """Parse the ``LISTING_STATUS`` CSV into typed listing records."""
    reader = csv.DictReader(io.StringIO(csv_text))
    records: list[ListingStatusRecord] = []
    for row in reader:
        symbol = (row.get("symbol") or "").strip()
        if not symbol:
            raise SourceResponseError("alpha vantage listing row lacks a symbol")
        raw_status = (row.get("status") or "").strip().lower()
        if raw_status == "active":
            status = ListingStatus.ACTIVE
        elif raw_status == "delisted":
            status = ListingStatus.DELISTED
        else:
            raise SourceResponseError(
                f"alpha vantage listing status {raw_status!r} is unsupported"
            )
        records.append(
            ListingStatusRecord(
                symbol,
                (row.get("name") or "").strip(),
                (row.get("exchange") or "").strip(),
                (row.get("assetType") or "").strip(),
                _optional_date(row.get("ipoDate")),
                _optional_date(row.get("delistingDate")),
                status,
            )
        )
    if not records:
        raise SourceResponseError("alpha vantage listing status CSV has no rows")
    return tuple(records)
