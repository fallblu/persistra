"""Immutable journal, lot, and settlement contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId
from persistra.errors import AccountingRequestError

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.reference import InstrumentId


class AccountingBookId(EntityId):
    KIND: ClassVar[str] = "accounting_book"


class JournalTransactionId(EntityId):
    KIND: ClassVar[str] = "journal_transaction"


class InventoryLotId(EntityId):
    KIND: ClassVar[str] = "inventory_lot"


class SettlementObligationId(EntityId):
    KIND: ClassVar[str] = "settlement_obligation"


class BorrowAuthorizationId(EntityId):
    KIND: ClassVar[str] = "borrow_authorization"


class JournalBook(StrEnum):
    GENERAL = "general"
    MEMORANDUM = "memorandum"


class TransactionKind(StrEnum):
    OPENING = "opening"
    CASH_FLOW = "cash_flow"
    ACCRUAL = "accrual"
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    SPLIT = "split"
    REVERSAL = "reversal"
    SETTLEMENT = "settlement"


class LotSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class SettlementStatus(StrEnum):
    OPEN = "open"
    SETTLED = "settled"


class AccrualKind(StrEnum):
    CASH_INTEREST = "cash_interest"
    FINANCING = "financing"
    BORROW_FEE = "borrow_fee"


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
class TradeFillFacts:
    """Signed fill facts for long, short, and cross-zero inventory transitions."""

    source_content_id: ContentId
    instrument_id: InstrumentId
    effective_at: datetime
    settlement_at: datetime
    signed_quantity: Decimal
    price_usd: Decimal
    fee_usd: Decimal = Decimal(0)
    modeled_cost_usd: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if (
            self.effective_at.tzinfo is None
            or self.settlement_at.tzinfo is None
            or self.settlement_at < self.effective_at
            or self.signed_quantity == 0
            or self.price_usd <= 0
            or self.fee_usd < 0
            or self.modeled_cost_usd < 0
        ):
            raise AccountingRequestError("trade fill accounting facts are invalid")


@dataclass(frozen=True, slots=True)
class CashFlowFacts:
    source_content_id: ContentId
    effective_at: datetime
    amount_usd: Decimal

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.amount_usd == 0:
            raise AccountingRequestError("cash flow accounting facts are invalid")


@dataclass(frozen=True, slots=True)
class ReversalFacts:
    source_content_id: ContentId
    effective_at: datetime
    transaction_id: JournalTransactionId

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None:
            raise AccountingRequestError("reversal accounting facts are invalid")


@dataclass(frozen=True, slots=True)
class SettlementFacts:
    source_content_id: ContentId
    effective_at: datetime
    settlement_obligation_id: SettlementObligationId

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None:
            raise AccountingRequestError("settlement accounting facts are invalid")


@dataclass(frozen=True, slots=True)
class AccrualFacts:
    source_content_id: ContentId
    effective_at: datetime
    kind: AccrualKind
    amount_usd: Decimal

    def __post_init__(self) -> None:
        if self.effective_at.tzinfo is None or self.amount_usd <= 0:
            raise AccountingRequestError("accrual accounting facts are invalid")


@dataclass(frozen=True, slots=True)
class BorrowAuthorizationFacts:
    source_content_id: ContentId
    instrument_id: InstrumentId
    effective_from: datetime
    effective_until: datetime
    quantity: Decimal

    def __post_init__(self) -> None:
        if (
            self.effective_from.tzinfo is None
            or self.effective_until.tzinfo is None
            or self.effective_until <= self.effective_from
            or self.quantity <= 0
        ):
            raise AccountingRequestError("borrow authorization facts are invalid")


@dataclass(frozen=True, slots=True)
class MarkFacts:
    source_content_id: ContentId
    instrument_id: InstrumentId
    observed_at: datetime
    available_at: datetime
    price_usd: Decimal

    def __post_init__(self) -> None:
        if (
            self.observed_at.tzinfo is None
            or self.available_at.tzinfo is None
            or self.available_at < self.observed_at
            or self.price_usd <= 0
        ):
            raise AccountingRequestError("valuation mark facts are invalid")


@dataclass(frozen=True, slots=True)
class CurrentPositionView:
    instrument_id: InstrumentId
    quantity: Decimal
    mark_price_usd: Decimal | None
    market_value_usd: Decimal | None
    mark_state: str


@dataclass(frozen=True, slots=True)
class CurrentPortfolioView:
    accounting_book_id: AccountingBookId
    as_of: datetime
    settled_cash_usd: Decimal
    unsettled_cash_usd: Decimal
    positions: tuple[CurrentPositionView, ...]
    nav_usd: Decimal | None
    gross_exposure_usd: Decimal | None
    complete: bool
    reconciliation_content_id: ContentId


@dataclass(frozen=True, slots=True)
class MarginResult:
    equity_usd: Decimal | None
    requirement_usd: Decimal | None
    excess_usd: Decimal | None
    breached: bool
    state: str


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
