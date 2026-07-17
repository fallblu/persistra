"""Foundational long-only journal and lot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId
from persistra.errors import AccountingRequestError

if TYPE_CHECKING:
    from datetime import datetime
    from decimal import Decimal

    from persistra.reference import InstrumentId


class AccountingBookId(EntityId):
    KIND: ClassVar[str] = "accounting_book"


class JournalTransactionId(EntityId):
    KIND: ClassVar[str] = "journal_transaction"


class InventoryLotId(EntityId):
    KIND: ClassVar[str] = "inventory_lot"


class JournalBook(StrEnum):
    GENERAL = "general"
    MEMORANDUM = "memorandum"


class TransactionKind(StrEnum):
    OPENING = "opening"
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    SPLIT = "split"


@dataclass(frozen=True, slots=True)
class AccountingOpening:
    effective_at: datetime
    cash_usd: Decimal
    source_content_id: ContentId

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.cash_usd < 0:
            raise AccountingRequestError("accounting opening is invalid")


@dataclass(frozen=True, slots=True)
class BookRef:
    accounting_book_id: AccountingBookId
    opening_content_id: ContentId


@dataclass(frozen=True, slots=True)
class FillFacts:
    source_content_id: ContentId
    instrument_id: InstrumentId
    effective_at: datetime
    side: str
    quantity: Decimal
    price_usd: Decimal
    commission_usd: Decimal
    slippage_usd: Decimal

    def __post_init__(self) -> None:
        if (
            self.effective_at.tzinfo is None
            or self.side not in {"buy", "sell"}
            or self.quantity <= 0
            or self.price_usd <= 0
            or self.commission_usd < 0
            or self.slippage_usd < 0
        ):
            raise AccountingRequestError("fill accounting facts are invalid")


@dataclass(frozen=True, slots=True)
class SplitFacts:
    source_content_id: ContentId
    instrument_id: InstrumentId
    effective_at: datetime
    ratio: Decimal

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.ratio <= 0:
            raise AccountingRequestError("split facts are invalid")


@dataclass(frozen=True, slots=True)
class DividendFacts:
    source_content_id: ContentId
    instrument_id: InstrumentId
    effective_at: datetime
    cash_per_share_usd: Decimal

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.cash_per_share_usd < 0:
            raise AccountingRequestError("dividend facts are invalid")


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    balanced: bool
    cash_usd: Decimal
    position_count: int
    lot_count: int
    journal_content_id: ContentId
