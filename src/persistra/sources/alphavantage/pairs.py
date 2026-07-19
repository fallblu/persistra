"""Alpha Vantage pair-instrument conventions for crypto and FX markets.

Pair instruments extend the standard reference chain with the synthetic
market-convention issuer, the shared OTC venue, and deterministic identities
derived from the pair symbol so repeated registration is idempotent.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from persistra.domain import AssetClass, ContentId
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

if TYPE_CHECKING:
    from persistra.domain import EntityId


def _derived_id[IdT: EntityId](kind: type[IdT], label: str) -> IdT:
    return kind(UUID(bytes=ContentId.from_bytes(label.encode()).digest[:16]))


def crypto_pair_instrument(
    base: str,
    quote: str,
    *,
    valid_from: datetime,
    available_at: datetime | None = None,
) -> InstrumentDefinition:
    """Return the canonical crypto pair instrument for ``base``/``quote``."""
    pair = f"{base.upper()}{quote.upper()}"
    prefix = f"alphavantage.crypto_pair.{pair}"
    return InstrumentDefinition(
        market_convention_issuer_id(AssetClass.CRYPTO),
        _derived_id(SecurityId, f"{prefix}.security@1"),
        SYNTHETIC_OTC_VENUE_ID,
        _derived_id(ListingId, f"{prefix}.listing@1"),
        _derived_id(InstrumentId, f"{prefix}.instrument@1"),
        "",
        "UTC",
        SecurityKind.CRYPTO_PAIR,
        SecurityStatus.ACTIVE,
        ListingStatus.ACTIVE,
        quote.upper(),
        valid_from,
        available_at=available_at,
        base_currency=base.upper(),
        quote_currency=quote.upper(),
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
