"""Alpha Vantage pair-instrument conventions for crypto and FX markets.

Pair instruments extend the standard reference chain with the synthetic
market-convention issuer, the shared OTC venue, and deterministic identities
derived from the pair symbol so repeated registration is idempotent.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from persistra.domain import AssetClass, AvailabilityQuality, ContentId
from persistra.domain.time import validate_instant
from persistra.errors import SourceResponseError
from persistra.market import BarState, DailyBar
from persistra.reference import (
    SYNTHETIC_OTC_VENUE_ID,
    InstrumentDefinition,
    InstrumentId,
    ListingId,
    ListingStatus,
    SecurityId,
    SecurityKind,
    SecurityStatus,
    market_convention_issuer_id,
)
from persistra.sources.alphavantage._parsing import (
    decimal_value,
    json_object,
    series_field,
    series_payload,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from persistra.domain import EntityId
    from persistra.market import ResolvedBarSpecRef
    from persistra.reference import ResolvedCalendarRef


def _derived_id[IdT: EntityId](kind: type[IdT], label: str) -> IdT:
    return kind(UUID(bytes=ContentId.from_bytes(label.encode()).digest[:16]))


def _pair_instrument(
    base: str,
    quote: str,
    *,
    asset_class: AssetClass,
    kind: SecurityKind,
    label: str,
    valid_from: datetime,
    available_at: datetime | None,
) -> InstrumentDefinition:
    pair = f"{base.upper()}{quote.upper()}"
    prefix = f"alphavantage.{label}.{pair}"
    return InstrumentDefinition(
        market_convention_issuer_id(asset_class),
        _derived_id(SecurityId, f"{prefix}.security@1"),
        SYNTHETIC_OTC_VENUE_ID,
        _derived_id(ListingId, f"{prefix}.listing@1"),
        _derived_id(InstrumentId, f"{prefix}.instrument@1"),
        "",
        "UTC",
        kind,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        quote.upper(),
        valid_from,
        available_at=available_at,
        base_currency=base.upper(),
        quote_currency=quote.upper(),
    )


def crypto_pair_instrument(
    base: str,
    quote: str,
    *,
    valid_from: datetime,
    available_at: datetime | None = None,
) -> InstrumentDefinition:
    """Return the canonical crypto pair instrument for ``base``/``quote``."""
    return _pair_instrument(
        base,
        quote,
        asset_class=AssetClass.CRYPTO,
        kind=SecurityKind.CRYPTO_PAIR,
        label="crypto_pair",
        valid_from=valid_from,
        available_at=available_at,
    )


def fx_pair_instrument(
    base: str,
    quote: str,
    *,
    valid_from: datetime,
    available_at: datetime | None = None,
) -> InstrumentDefinition:
    """Return the canonical spot FX pair instrument for ``base``/``quote``."""
    return _pair_instrument(
        base,
        quote,
        asset_class=AssetClass.FX,
        kind=SecurityKind.FX_PAIR,
        label="fx_pair",
        valid_from=valid_from,
        available_at=available_at,
    )


def utc_day_sessions(
    start: date, end: date, *, weekdays_only: bool = False
) -> dict[date, tuple[datetime, datetime]]:
    """Return midnight-to-midnight UTC sessions matching the synthetic calendars.

    ``weekdays_only`` reproduces the FX 24x5 weekday calendar; otherwise every
    day is a session as on the always-open calendar. ``end`` is exclusive.
    """
    sessions: dict[date, tuple[datetime, datetime]] = {}
    current = start
    while current < end:
        if not weekdays_only or current.weekday() < 5:
            open_at = datetime(
                current.year, current.month, current.day, tzinfo=UTC
            )
            sessions[current] = (open_at, open_at + timedelta(days=1))
        current += timedelta(days=1)
    return sessions


def _pair_daily_bars(
    payload: dict[str, Any],
    series_prefix: str,
    *,
    has_volume: bool,
    instrument_id: InstrumentId,
    spec: ResolvedBarSpecRef,
    calendar: ResolvedCalendarRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    available_at: datetime,
    currency: str,
) -> tuple[DailyBar, ...]:
    validate_instant(available_at)
    series = series_payload(payload, series_prefix)
    bars: list[DailyBar] = []
    for raw_date in sorted(series):
        try:
            session_date = date.fromisoformat(raw_date)
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage pair series key is not a date"
            ) from cause
        session = sessions.get(session_date)
        if session is None:
            continue
        open_at, close_at = session
        if close_at > available_at:
            continue
        row = json_object(series[raw_date], f"pair row {raw_date}")
        if has_volume:
            volume = decimal_value(
                series_field(row, "volume", "volume"), "pair volume"
            )
            if volume < 0:
                raise SourceResponseError("alpha vantage pair volume is negative")
            state = BarState.COMPLETE if volume > 0 else BarState.NO_VOLUME
        else:
            volume = Decimal(0)
            state = BarState.NO_VOLUME
        bars.append(
            DailyBar(
                instrument_id,
                spec,
                calendar,
                open_at,
                close_at,
                session_date,
                state,
                currency,
                decimal_value(series_field(row, "1. open", "open"), "pair open"),
                decimal_value(series_field(row, "2. high", "high"), "pair high"),
                decimal_value(series_field(row, "3. low", "low"), "pair low"),
                decimal_value(series_field(row, "4. close", "close"), "pair close"),
                volume,
                None,
                available_at,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(bars)


def _pair_intraday_bars(
    payload: dict[str, Any],
    series_prefix: str,
    *,
    has_volume: bool,
    instrument_id: InstrumentId,
    spec: ResolvedBarSpecRef,
    calendar: ResolvedCalendarRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    interval: timedelta,
    available_at: datetime,
    currency: str,
) -> tuple[DailyBar, ...]:
    validate_instant(available_at)
    if interval <= timedelta(0):
        raise SourceResponseError("alpha vantage pair interval must be positive")
    meta = json_object(payload.get("Meta Data"), "pair intraday metadata")
    timezone_name = str(series_field(meta, "Time Zone", "time zone"))
    try:
        zone = ZoneInfo(timezone_name)
    except (KeyError, ValueError) as cause:
        raise SourceResponseError(
            "alpha vantage pair intraday time zone is unknown"
        ) from cause
    series = series_payload(payload, series_prefix)
    bars: list[DailyBar] = []
    for raw_stamp in sorted(series):
        try:
            local_end = datetime.strptime(raw_stamp, "%Y-%m-%d %H:%M:%S")
        except ValueError as cause:
            raise SourceResponseError(
                "alpha vantage pair intraday key is not a timestamp"
            ) from cause
        interval_end = local_end.replace(tzinfo=zone).astimezone(ZoneInfo("UTC"))
        interval_start = interval_end - interval
        session_date = interval_start.date()
        session = sessions.get(session_date)
        if session is None:
            continue
        open_at, close_at = session
        if interval_start < open_at or interval_end > close_at:
            continue
        if interval_end > available_at:
            continue
        row = json_object(series[raw_stamp], f"pair intraday row {raw_stamp}")
        if has_volume:
            volume = decimal_value(
                series_field(row, "volume", "volume"), "pair volume"
            )
            if volume < 0:
                raise SourceResponseError("alpha vantage pair volume is negative")
            state = BarState.COMPLETE if volume > 0 else BarState.NO_VOLUME
        else:
            volume = Decimal(0)
            state = BarState.NO_VOLUME
        bars.append(
            DailyBar(
                instrument_id,
                spec,
                calendar,
                interval_start,
                interval_end,
                session_date,
                state,
                currency,
                decimal_value(series_field(row, "1. open", "open"), "pair open"),
                decimal_value(series_field(row, "2. high", "high"), "pair high"),
                decimal_value(series_field(row, "3. low", "low"), "pair low"),
                decimal_value(series_field(row, "4. close", "close"), "pair close"),
                volume,
                None,
                available_at,
                availability_quality=AvailabilityQuality.INGESTION_BOUNDED,
            )
        )
    return tuple(bars)


def parse_crypto_daily_bars(
    payload: dict[str, Any],
    *,
    instrument_id: InstrumentId,
    spec: ResolvedBarSpecRef,
    calendar: ResolvedCalendarRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    available_at: datetime,
    currency: str,
) -> tuple[DailyBar, ...]:
    """Parse ``DIGITAL_CURRENCY_DAILY`` into complete 24x7 session bars.

    ``currency`` is the pair's quote (market) currency; volume is reported in
    base units.
    """
    return _pair_daily_bars(
        payload,
        "Time Series (Digital Currency Daily)",
        has_volume=True,
        instrument_id=instrument_id,
        spec=spec,
        calendar=calendar,
        sessions=sessions,
        available_at=available_at,
        currency=currency,
    )


def parse_crypto_intraday_bars(
    payload: dict[str, Any],
    *,
    instrument_id: InstrumentId,
    spec: ResolvedBarSpecRef,
    calendar: ResolvedCalendarRef,
    sessions: Mapping[date, tuple[datetime, datetime]],
    interval: timedelta,
    available_at: datetime,
    currency: str,
) -> tuple[DailyBar, ...]:
    """Parse ``CRYPTO_INTRADAY`` into fixed-grid bars in the quote currency."""
    return _pair_intraday_bars(
        payload,
        "Time Series Crypto (",
        has_volume=True,
        instrument_id=instrument_id,
        spec=spec,
        calendar=calendar,
        sessions=sessions,
        interval=interval,
        available_at=available_at,
        currency=currency,
    )
