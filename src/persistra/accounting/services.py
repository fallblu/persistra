"""This module contains the immutable foundational journal, cash, position, and FIFO lot service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.accounting.models import (
    AccountingBookId,
    AccountingOpening,
    AccrualFacts,
    AccrualKind,
    BookRef,
    BorrowAuthorizationFacts,
    BorrowAuthorizationId,
    CashFlowFacts,
    CurrentPortfolioView,
    CurrentPositionView,
    DividendFacts,
    FillFacts,
    InventoryLotId,
    JournalTransactionId,
    MarginResult,
    MarkFacts,
    ReconciliationResult,
    ReversalFacts,
    SettlementFacts,
    SettlementObligationId,
    SplitFacts,
    TradeFillFacts,
    TransactionKind,
)
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    AccountingInvariantError,
    AccountingRequestError,
    CapabilityUnavailableError,
    ResearchResultLimitError,
)
from persistra.reference import InstrumentId

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project

_QUANTUM = Decimal("0.000000000001")

_CHART = (
    ("general", "cash", "asset", "USD", "debit"),
    ("general", "unsettled_cash", "asset", "USD", "debit"),
    ("general", "capital", "equity", "USD", "credit"),
    ("general", "long_cost", "asset", "USD", "debit"),
    ("general", "inventory_cost", "asset_or_liability", "USD", "debit"),
    ("general", "realized_gain", "income", "USD", "credit"),
    ("general", "commission_expense", "expense", "USD", "debit"),
    ("general", "fee_expense", "expense", "USD", "debit"),
    ("general", "interest_income", "income", "USD", "credit"),
    ("general", "financing_expense", "expense", "USD", "debit"),
    ("general", "borrow_expense", "expense", "USD", "debit"),
    ("general", "dividend_income", "income", "USD", "credit"),
    ("general", "position", "inventory", "instrument", "debit"),
    ("general", "quantity_control", "control", "instrument", "credit"),
    ("memorandum", "modeled_slippage", "cost_attribution", "USD", "debit"),
    ("memorandum", "memorandum_offset", "control", "USD", "credit"),
)


def _q(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


class AccountingService:
    """This class represents the public accounting capability and simulation-owned transition
    kernel."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def create_book(self, opening: AccountingOpening) -> AccountingBook:
        self._require_write()

        def operation(context: TransactionContext) -> AccountingBook:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._create_book(connection, context, opening)

        return self._project.services.transactions.run("accounting_book_create", operation)

    def apply_fill(self, book: AccountingBookId, facts: FillFacts) -> JournalTransactionId:
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._apply_fill(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_fill_apply", operation)

    def apply_split(self, book: AccountingBookId, facts: SplitFacts) -> JournalTransactionId:
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._apply_split(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_split_apply", operation)

    def apply_dividend(
        self, book: AccountingBookId, facts: DividendFacts
    ) -> JournalTransactionId | None:
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId | None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._apply_dividend(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_dividend_apply", operation)

    def apply_cash_flow(
        self, book: AccountingBookId, facts: CashFlowFacts
    ) -> JournalTransactionId:
        """Post a settled external contribution or withdrawal."""
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            fingerprint = scoped_content_id(
                {"schema": "persistra.accounting.cash_flow_facts@1", "facts": facts}
            )
            existing = self._existing_source(
                connection, book, facts.source_content_id, fingerprint
            )
            if existing is not None:
                return existing
            return self._post(
                connection,
                context,
                book,
                facts.source_content_id,
                TransactionKind.CASH_FLOW,
                facts.effective_at,
                [
                    ("general", "cash", "USD", facts.amount_usd, None),
                    ("general", "capital", "USD", -facts.amount_usd, None),
                ],
                source_fingerprint=fingerprint,
            )

        return self._project.services.transactions.run("accounting_cash_flow_apply", operation)

    def apply_trade(
        self, book: AccountingBookId, facts: TradeFillFacts
    ) -> JournalTransactionId:
        """Apply a signed long/short fill and create its settlement obligation."""
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._apply_trade(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_trade_apply", operation)

    def apply_settlement(
        self, book: AccountingBookId, facts: SettlementFacts
    ) -> JournalTransactionId:
        """Reclassify one due trade obligation into settled cash."""
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._apply_settlement(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_settlement_apply", operation)

    def reverse(
        self, book: AccountingBookId, facts: ReversalFacts
    ) -> JournalTransactionId:
        """Append a linked exact compensating transaction when dependencies are satisfied."""
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._reverse(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_transaction_reverse", operation)

    def apply_accrual(
        self, book: AccountingBookId, facts: AccrualFacts
    ) -> JournalTransactionId:
        """Post cash interest, financing, or borrow expense exactly once."""
        self._require_write()

        def operation(context: TransactionContext) -> JournalTransactionId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            fingerprint = scoped_content_id(
                {"schema": "persistra.accounting.accrual_facts@1", "facts": facts}
            )
            existing = self._existing_source(
                connection, book, facts.source_content_id, fingerprint
            )
            if existing is not None:
                return existing
            cash_amount = (
                facts.amount_usd
                if facts.kind is AccrualKind.CASH_INTEREST
                else -facts.amount_usd
            )
            account = {
                AccrualKind.CASH_INTEREST: "interest_income",
                AccrualKind.FINANCING: "financing_expense",
                AccrualKind.BORROW_FEE: "borrow_expense",
            }[facts.kind]
            return self._post(
                connection,
                context,
                book,
                facts.source_content_id,
                TransactionKind.ACCRUAL,
                facts.effective_at,
                [
                    ("general", "cash", "USD", cash_amount, None),
                    ("general", account, "USD", -cash_amount, None),
                ],
                source_fingerprint=fingerprint,
            )

        return self._project.services.transactions.run("accounting_accrual_apply", operation)

    def authorize_borrow(
        self, book: AccountingBookId, facts: BorrowAuthorizationFacts
    ) -> BorrowAuthorizationId:
        """Register effective-dated short inventory without mutating positions."""
        self._require_write()

        def operation(context: TransactionContext) -> BorrowAuthorizationId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            return self._authorize_borrow(connection, context, book, facts)

        return self._project.services.transactions.run("accounting_borrow_authorize", operation)

    def _authorize_borrow(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: BorrowAuthorizationFacts,
    ) -> BorrowAuthorizationId:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.borrow_authorization@1", "facts": facts}
        )
        row = connection.execute(
            "SELECT borrow_authorization_id, authorization_content_id FROM "
            "accounting.borrow_authorizations WHERE accounting_book_id = ? "
            "AND source_content_id = ?",
            [book.value, str(facts.source_content_id)],
        ).fetchone()
        if row is not None:
            if row[1] != str(fingerprint):
                raise AccountingRequestError(
                    "borrow source content ID was reused for different facts"
                )
            return BorrowAuthorizationId.parse(row[0])
        authorization_id = BorrowAuthorizationId.new()
        connection.execute(
            "INSERT INTO accounting.borrow_authorizations VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                authorization_id.value,
                book.value,
                facts.instrument_id.value,
                facts.effective_from,
                facts.effective_until,
                facts.quantity,
                str(facts.source_content_id),
                str(fingerprint),
                context.recorded_at,
            ],
        )
        return authorization_id

    def record_mark(self, book: AccountingBookId, facts: MarkFacts) -> ContentId:
        """Persist one causally available immutable USD mark."""
        self._require_write()

        def operation(context: TransactionContext) -> ContentId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            content_id = scoped_content_id(
                {
                    "schema": "persistra.accounting.valuation_mark@1",
                    "book": book,
                    "facts": facts,
                }
            )
            row = connection.execute(
                "SELECT mark_content_id FROM accounting.valuation_marks "
                "WHERE accounting_book_id = ? AND source_content_id = ?",
                [book.value, str(facts.source_content_id)],
            ).fetchone()
            if row is not None:
                if row[0] != str(content_id):
                    raise AccountingRequestError(
                        "mark source content ID was reused for different facts"
                    )
                return ContentId.parse(row[0])
            connection.execute(
                "INSERT INTO accounting.valuation_marks VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    book.value,
                    facts.instrument_id.value,
                    facts.observed_at,
                    facts.available_at,
                    facts.price_usd,
                    str(facts.source_content_id),
                    str(content_id),
                    context.recorded_at,
                ],
            )
            return content_id

        return self._project.services.transactions.run("accounting_mark_record", operation)

    def current_view(
        self,
        book: AccountingBookId,
        as_of: datetime,
        *,
        maximum_mark_age: timedelta = timedelta(days=5),
    ) -> CurrentPortfolioView:
        """Build a reconciled current portfolio view without stale-mark fallback."""
        if as_of.tzinfo is None or maximum_mark_age <= timedelta(0):
            raise AccountingRequestError("current portfolio view request is invalid")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        latest = connection.execute(
            "SELECT max(effective_at) FROM accounting.journal_transactions "
            "WHERE accounting_book_id = ?",
            [book.value],
        ).fetchone()[0]
        if latest is None:
            raise AccountingRequestError("accounting book is missing")
        if latest > as_of:
            raise AccountingRequestError("current view cannot precede the journal prefix")
        reconciliation = self._reconcile(connection, book)
        positions = self._position_rows(connection, book)
        views: list[CurrentPositionView] = []
        values: list[Decimal] = []
        for instrument_id, quantity in positions:
            row = connection.execute(
                "SELECT observed_at, price_usd FROM accounting.valuation_marks "
                "WHERE accounting_book_id = ? AND instrument_id = ? "
                "AND observed_at <= ? AND available_at <= ? "
                "ORDER BY observed_at DESC, available_at DESC LIMIT 1",
                [book.value, instrument_id, as_of, as_of],
            ).fetchone()
            if row is None:
                views.append(
                    CurrentPositionView(
                        InstrumentId.parse(instrument_id),
                        quantity,
                        None,
                        None,
                        "missing",
                    )
                )
                continue
            price = Decimal(str(row[1]))
            stale = as_of - row[0] > maximum_mark_age
            value = _q(quantity * price)
            views.append(
                CurrentPositionView(
                    InstrumentId.parse(instrument_id),
                    quantity,
                    price,
                    value,
                    "stale" if stale else "complete",
                )
            )
            if not stale:
                values.append(value)
        complete = reconciliation.balanced and all(
            item.mark_state == "complete" for item in views
        )
        economic_cash = _q(self._cash(connection, book) + self._unsettled_cash(connection, book))
        return CurrentPortfolioView(
            book,
            as_of,
            self._cash(connection, book),
            self._unsettled_cash(connection, book),
            tuple(views),
            _q(economic_cash + sum(values, Decimal(0))) if complete else None,
            _q(sum((abs(value) for value in values), Decimal(0))) if complete else None,
            complete,
            reconciliation.journal_content_id,
        )

    def evaluate_margin(
        self, view: CurrentPortfolioView, maintenance_rate: Decimal
    ) -> MarginResult:
        """Evaluate a simple explicit maintenance requirement without side effects."""
        if maintenance_rate < 0 or maintenance_rate > 1:
            raise AccountingRequestError("maintenance margin rate is invalid")
        if not view.complete or view.nav_usd is None or view.gross_exposure_usd is None:
            return MarginResult(None, None, None, False, "unavailable")
        requirement = _q(view.gross_exposure_usd * maintenance_rate)
        excess = _q(view.nav_usd - requirement)
        return MarginResult(view.nav_usd, requirement, excess, excess < 0, "complete")

    def get(self, book: AccountingBookId) -> AccountingBook:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT opening_content_id FROM accounting.books WHERE accounting_book_id = ?",
            [book.value],
        ).fetchone()
        if row is None:
            raise AccountingRequestError("accounting book is missing")
        return AccountingBook(self._project, BookRef(book, ContentId.parse(row[0])))

    def reconcile(self, book: AccountingBookId) -> ReconciliationResult:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        return self._reconcile(connection, book)

    def _create_book(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        opening: AccountingOpening,
    ) -> AccountingBook:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.opening_facts@2", "opening": opening}
        )
        existing = connection.execute(
            "SELECT b.accounting_book_id, t.source_fingerprint FROM accounting.books b "
            "LEFT JOIN accounting.journal_transactions t "
            "ON t.accounting_book_id = b.accounting_book_id "
            "AND t.transaction_kind = 'opening' WHERE b.opening_content_id = ?",
            [str(opening.source_content_id)],
        ).fetchone()
        if existing is not None:
            if existing[1] is not None and existing[1] != str(fingerprint):
                raise AccountingRequestError(
                    "opening source content ID was reused for different facts"
                )
            return self.get(AccountingBookId.parse(existing[0]))
        book_id = AccountingBookId.new()
        connection.execute(
            "INSERT INTO accounting.books VALUES (?, ?, ?, ?)",
            [
                book_id.value,
                str(opening.source_content_id),
                opening.effective_at,
                context.recorded_at,
            ],
        )
        connection.executemany(
            "INSERT INTO accounting.chart_accounts VALUES (?, ?, ?, ?, ?, ?)",
            [(book_id.value, *account) for account in _CHART],
        )
        postings = [
            ("general", "cash", "USD", _q(opening.cash_usd), None),
            ("general", "capital", "USD", _q(-opening.cash_usd), None),
        ]
        self._post(
            connection,
            context,
            book_id,
            opening.source_content_id,
            TransactionKind.OPENING,
            opening.effective_at,
            postings,
            source_fingerprint=fingerprint,
        )
        return self.get(book_id)

    def _apply_trade(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: TradeFillFacts,
    ) -> JournalTransactionId:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.trade_fill_facts@1", "facts": facts}
        )
        existing = self._existing_source(
            connection, book, facts.source_content_id, fingerprint
        )
        if existing is not None:
            return existing
        signed_quantity = _q(facts.signed_quantity)
        current_quantity = self._position(
            connection, book, facts.instrument_id.value
        )
        projected_quantity = _q(current_quantity + signed_quantity)
        if projected_quantity < min(current_quantity, Decimal(0)):
            authorized = connection.execute(
                "SELECT coalesce(sum(quantity), 0) FROM "
                "accounting.borrow_authorizations WHERE accounting_book_id = ? "
                "AND instrument_id = ? AND effective_from <= ? AND effective_until > ?",
                [
                    book.value,
                    facts.instrument_id.value,
                    facts.effective_at,
                    facts.effective_at,
                ],
            ).fetchone()[0]
            if Decimal(str(authorized)) < abs(projected_quantity):
                raise AccountingInvariantError(
                    "short fill exceeds effective borrow authorization"
                )
        trade_cash = _q(-(signed_quantity * facts.price_usd) - facts.fee_usd)
        if trade_cash < 0 and self._cash(connection, book) < -trade_cash:
            raise AccountingInvariantError("trade fill exceeds settled cash")

        remaining = signed_quantity
        inventory_change = Decimal(0)
        lot_events: list[tuple[InventoryLotId, str, Decimal, Decimal]] = []
        for lot_id, lot_quantity, lot_basis in self._open_signed_lots(
            connection, book, facts.instrument_id.value
        ):
            if remaining == 0 or (remaining > 0) == (lot_quantity > 0):
                continue
            relieved = min(abs(remaining), abs(lot_quantity))
            quantity_delta = relieved if remaining > 0 else -relieved
            basis_delta = _q(-(lot_basis * relieved / abs(lot_quantity)))
            inventory_change = _q(inventory_change + basis_delta)
            lot_events.append((lot_id, "relief", quantity_delta, basis_delta))
            remaining = _q(remaining - quantity_delta)

        new_lot: tuple[InventoryLotId, Decimal, Decimal] | None = None
        if remaining:
            new_basis = _q(remaining * facts.price_usd)
            inventory_change = _q(inventory_change + new_basis)
            new_lot = (InventoryLotId.new(), remaining, new_basis)

        postings: list[tuple[str, str, str, Decimal, Any]] = [
            ("general", "unsettled_cash", "USD", trade_cash, None),
            (
                "general",
                "inventory_cost",
                "USD",
                inventory_change,
                facts.instrument_id.value,
            ),
            (
                "general",
                "position",
                str(facts.instrument_id.value),
                signed_quantity,
                facts.instrument_id.value,
            ),
            (
                "general",
                "quantity_control",
                str(facts.instrument_id.value),
                -signed_quantity,
                facts.instrument_id.value,
            ),
        ]
        if facts.fee_usd:
            postings.append(("general", "fee_expense", "USD", facts.fee_usd, None))
        realized = _q(-(trade_cash + inventory_change + facts.fee_usd))
        if realized:
            postings.append(
                (
                    "general",
                    "realized_gain",
                    "USD",
                    realized,
                    facts.instrument_id.value,
                )
            )
        if facts.modeled_cost_usd:
            postings.extend(
                [
                    (
                        "memorandum",
                        "modeled_slippage",
                        "USD",
                        facts.modeled_cost_usd,
                        facts.instrument_id.value,
                    ),
                    (
                        "memorandum",
                        "memorandum_offset",
                        "USD",
                        -facts.modeled_cost_usd,
                        facts.instrument_id.value,
                    ),
                ]
            )
        transaction_id = self._post(
            connection,
            context,
            book,
            facts.source_content_id,
            TransactionKind.BUY if signed_quantity > 0 else TransactionKind.SELL,
            facts.effective_at,
            postings,
            source_fingerprint=fingerprint,
        )
        if new_lot is not None:
            lot_id, quantity, basis = new_lot
            lot_content_id = scoped_content_id(
                {
                    "schema": "persistra.accounting.inventory_lot@2",
                    "book": book,
                    "transaction": transaction_id,
                    "instrument": facts.instrument_id,
                    "quantity": quantity,
                    "basis": basis,
                }
            )
            connection.execute(
                "INSERT INTO accounting.inventory_lots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    lot_id.value,
                    book.value,
                    facts.instrument_id.value,
                    transaction_id.value,
                    facts.effective_at,
                    quantity,
                    basis,
                    str(lot_content_id),
                ],
            )
            lot_events.append((lot_id, "open", quantity, basis))
        self._write_lot_events(connection, transaction_id, lot_events)
        obligation_id = SettlementObligationId.new()
        obligation_content_id = scoped_content_id(
            {
                "schema": "persistra.accounting.settlement_obligation@1",
                "book": book,
                "trade": transaction_id,
                "due_at": facts.settlement_at,
                "quantity": signed_quantity,
                "cash": trade_cash,
            }
        )
        connection.execute(
            "INSERT INTO accounting.settlement_obligations VALUES "
            "(?, ?, ?, ?, ?, ?, ?, 'open', NULL, ?)",
            [
                obligation_id.value,
                book.value,
                transaction_id.value,
                facts.instrument_id.value,
                facts.settlement_at,
                signed_quantity,
                trade_cash,
                str(obligation_content_id),
            ],
        )
        return transaction_id

    def _apply_fill(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: FillFacts,
    ) -> JournalTransactionId:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.fill_facts@2", "facts": facts}
        )
        existing = self._existing_source(
            connection, book, facts.source_content_id, fingerprint
        )
        if existing is not None:
            return existing
        notional = _q(facts.quantity * facts.price_usd)
        postings: list[tuple[str, str, str, Decimal, Any]] = []
        lot_events: list[tuple[InventoryLotId, str, Decimal, Decimal]] = []
        new_lot: tuple[InventoryLotId, Decimal, Decimal] | None = None
        if facts.side == "buy":
            cash = self._cash(connection, book)
            required = notional + facts.commission_usd
            if cash < required:
                raise AccountingInvariantError("buy fill exceeds available cash")
            postings.extend(
                [
                    ("general", "long_cost", "USD", notional, facts.instrument_id.value),
                    ("general", "cash", "USD", -notional, None),
                    (
                        "general",
                        "position",
                        str(facts.instrument_id.value),
                        facts.quantity,
                        facts.instrument_id.value,
                    ),
                    (
                        "general",
                        "quantity_control",
                        str(facts.instrument_id.value),
                        -facts.quantity,
                        facts.instrument_id.value,
                    ),
                ]
            )
            lot_id = InventoryLotId.new()
            new_lot = (lot_id, facts.quantity, notional)
        else:
            available = self._position(connection, book, facts.instrument_id.value)
            if available < facts.quantity:
                raise AccountingInvariantError("sell fill exceeds long position")
            relief = self._fifo_relief(
                connection, book, facts.instrument_id.value, facts.quantity
            )
            basis = sum((item[2] for item in relief), Decimal(0))
            gain = notional - basis
            postings.extend(
                [
                    ("general", "cash", "USD", notional, None),
                    ("general", "long_cost", "USD", -basis, facts.instrument_id.value),
                    ("general", "realized_gain", "USD", -gain, facts.instrument_id.value),
                    (
                        "general",
                        "position",
                        str(facts.instrument_id.value),
                        -facts.quantity,
                        facts.instrument_id.value,
                    ),
                    (
                        "general",
                        "quantity_control",
                        str(facts.instrument_id.value),
                        facts.quantity,
                        facts.instrument_id.value,
                    ),
                ]
            )
            lot_events.extend(
                (item[0], "relief", -item[1], -item[2]) for item in relief
            )
        if facts.commission_usd:
            postings.extend(
                [
                    ("general", "commission_expense", "USD", facts.commission_usd, None),
                    ("general", "cash", "USD", -facts.commission_usd, None),
                ]
            )
        if facts.slippage_usd:
            postings.extend(
                [
                    ("memorandum", "modeled_slippage", "USD", facts.slippage_usd, None),
                    ("memorandum", "memorandum_offset", "USD", -facts.slippage_usd, None),
                ]
            )
        transaction_id = self._post(
            connection,
            context,
            book,
            facts.source_content_id,
            TransactionKind.BUY if facts.side == "buy" else TransactionKind.SELL,
            facts.effective_at,
            postings,
            source_fingerprint=fingerprint,
        )
        if new_lot is not None:
            lot_id, quantity, basis = new_lot
            lot_content_id = scoped_content_id(
                {
                    "schema": "persistra.accounting.inventory_lot@1",
                    "book": book,
                    "transaction": transaction_id,
                    "instrument": facts.instrument_id,
                    "quantity": quantity,
                    "basis": basis,
                }
            )
            connection.execute(
                "INSERT INTO accounting.inventory_lots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    lot_id.value,
                    book.value,
                    facts.instrument_id.value,
                    transaction_id.value,
                    facts.effective_at,
                    quantity,
                    basis,
                    str(lot_content_id),
                ],
            )
            lot_events.append((lot_id, "open", quantity, basis))
        self._write_lot_events(connection, transaction_id, lot_events)
        return transaction_id

    def _apply_split(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: SplitFacts,
    ) -> JournalTransactionId:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.split_facts@2", "facts": facts}
        )
        existing = self._existing_source(
            connection, book, facts.source_content_id, fingerprint
        )
        if existing is not None:
            return existing
        open_lots = self._open_lots(connection, book, facts.instrument_id.value)
        delta = _q(sum((row[1] for row in open_lots), Decimal(0)) * (facts.ratio - 1))
        postings = [
            (
                "general",
                "position",
                str(facts.instrument_id.value),
                delta,
                facts.instrument_id.value,
            ),
            (
                "general",
                "quantity_control",
                str(facts.instrument_id.value),
                -delta,
                facts.instrument_id.value,
            ),
        ]
        transaction_id = self._post(
            connection,
            context,
            book,
            facts.source_content_id,
            TransactionKind.SPLIT,
            facts.effective_at,
            postings,
            source_fingerprint=fingerprint,
        )
        events = [
            (row[0], "split", _q(row[1] * (facts.ratio - 1)), Decimal(0))
            for row in open_lots
        ]
        self._write_lot_events(connection, transaction_id, events)
        return transaction_id

    def _apply_dividend(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: DividendFacts,
    ) -> JournalTransactionId | None:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.dividend_facts@2", "facts": facts}
        )
        existing = self._existing_source(
            connection, book, facts.source_content_id, fingerprint
        )
        if existing is not None:
            return existing
        quantity = self._position(connection, book, facts.instrument_id.value)
        if quantity == 0:
            return None
        amount = _q(quantity * facts.cash_per_share_usd)
        return self._post(
            connection,
            context,
            book,
            facts.source_content_id,
            TransactionKind.DIVIDEND,
            facts.effective_at,
            [
                ("general", "cash", "USD", amount, None),
                (
                    "general",
                    "dividend_income",
                    "USD",
                    -amount,
                    facts.instrument_id.value,
                ),
            ],
            source_fingerprint=fingerprint,
        )

    def _apply_settlement(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: SettlementFacts,
    ) -> JournalTransactionId:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.settlement_facts@1", "facts": facts}
        )
        existing = self._existing_source(
            connection, book, facts.source_content_id, fingerprint
        )
        if existing is not None:
            return existing
        row = connection.execute(
            "SELECT due_at, signed_cash_usd, status FROM "
            "accounting.settlement_obligations WHERE settlement_obligation_id = ? "
            "AND accounting_book_id = ?",
            [facts.settlement_obligation_id.value, book.value],
        ).fetchone()
        if row is None:
            raise AccountingRequestError("settlement obligation is missing")
        if row[2] != "open":
            raise AccountingRequestError("settlement obligation is already settled")
        if facts.effective_at < row[0]:
            raise AccountingRequestError("settlement obligation is not due")
        amount = Decimal(str(row[1]))
        transaction_id = self._post(
            connection,
            context,
            book,
            facts.source_content_id,
            TransactionKind.SETTLEMENT,
            facts.effective_at,
            [
                ("general", "cash", "USD", amount, None),
                ("general", "unsettled_cash", "USD", -amount, None),
            ],
            source_fingerprint=fingerprint,
        )
        connection.execute(
            "UPDATE accounting.settlement_obligations SET status = 'settled', "
            "settled_by_transaction_id = ? WHERE settlement_obligation_id = ?",
            [transaction_id.value, facts.settlement_obligation_id.value],
        )
        return transaction_id

    def _reverse(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: ReversalFacts,
    ) -> JournalTransactionId:
        fingerprint = scoped_content_id(
            {"schema": "persistra.accounting.reversal_facts@1", "facts": facts}
        )
        existing = self._existing_source(
            connection, book, facts.source_content_id, fingerprint
        )
        if existing is not None:
            return existing
        target = connection.execute(
            "SELECT transaction_kind, effective_at FROM accounting.journal_transactions "
            "WHERE journal_transaction_id = ? AND accounting_book_id = ?",
            [facts.transaction_id.value, book.value],
        ).fetchone()
        if target is None:
            raise AccountingRequestError("reversal target is missing")
        if target[0] == TransactionKind.REVERSAL.value:
            raise AccountingRequestError("a reversal cannot be reversed")
        prior = connection.execute(
            "SELECT 1 FROM accounting.journal_transactions "
            "WHERE reversal_of_transaction_id = ?",
            [facts.transaction_id.value],
        ).fetchone()
        if prior is not None:
            raise AccountingRequestError("transaction is already reversed")
        obligation = connection.execute(
            "SELECT status FROM accounting.settlement_obligations "
            "WHERE trade_transaction_id = ? OR settled_by_transaction_id = ?",
            [facts.transaction_id.value, facts.transaction_id.value],
        ).fetchone()
        if obligation is not None:
            raise AccountingRequestError(
                "transaction with settlement dependencies cannot be blindly reversed"
            )
        lot_rows = connection.execute(
            "SELECT e.inventory_lot_id, e.event_kind, e.quantity_delta, "
            "e.basis_delta_usd FROM journal_data.lot_events e "
            "WHERE e.journal_transaction_id = ? ORDER BY e.inventory_lot_id",
            [facts.transaction_id.value],
        ).fetchall()
        for lot_id, _, _, _ in lot_rows:
            dependent = connection.execute(
                "SELECT 1 FROM journal_data.lot_events e "
                "JOIN accounting.journal_transactions t "
                "ON t.journal_transaction_id = e.journal_transaction_id "
                "JOIN accounting.journal_transactions target "
                "ON target.journal_transaction_id = ? "
                "WHERE e.inventory_lot_id = ? AND t.book_sequence > target.book_sequence "
                "LIMIT 1",
                [facts.transaction_id.value, lot_id],
            ).fetchone()
            if dependent is not None:
                raise AccountingRequestError(
                    "correction is blocked by a later lot dependency"
                )
        posting_rows = connection.execute(
            "SELECT posting_book, account_code, commodity, amount, instrument_id "
            "FROM journal_data.journal_postings WHERE journal_transaction_id = ? "
            "ORDER BY posting_ordinal",
            [facts.transaction_id.value],
        ).fetchall()
        postings = [
            (row[0], row[1], row[2], -Decimal(str(row[3])), row[4])
            for row in posting_rows
        ]
        transaction_id = self._post(
            connection,
            context,
            book,
            facts.source_content_id,
            TransactionKind.REVERSAL,
            facts.effective_at,
            postings,
            source_fingerprint=fingerprint,
            reversal_of=facts.transaction_id,
        )
        self._write_lot_events(
            connection,
            transaction_id,
            [
                (
                    InventoryLotId.parse(row[0]),
                    f"reverse_{row[1]}",
                    -Decimal(str(row[2])),
                    -Decimal(str(row[3])),
                )
                for row in lot_rows
            ],
        )
        return transaction_id

    def _post(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        source: ContentId,
        kind: TransactionKind,
        effective_at: datetime,
        postings: list[tuple[str, str, str, Decimal, Any]],
        *,
        source_fingerprint: ContentId | None = None,
        reversal_of: JournalTransactionId | None = None,
    ) -> JournalTransactionId:
        totals: dict[tuple[str, str], Decimal] = {}
        normalized: list[tuple[str, str, str, Decimal, Any]] = []
        for posting in postings:
            posting_book, account, commodity, amount, instrument_id = posting
            chart_row = connection.execute(
                "SELECT commodity_scope FROM accounting.chart_accounts "
                "WHERE accounting_book_id = ? AND posting_book = ? AND account_code = ?",
                [book.value, posting_book, account],
            ).fetchone()
            if chart_row is None:
                raise AccountingInvariantError("journal account is not registered")
            if (chart_row[0] == "USD") != (commodity == "USD"):
                raise AccountingInvariantError(
                    "journal commodity does not match account dimensions"
                )
            quantized = _q(amount)
            normalized.append((posting_book, account, commodity, quantized, instrument_id))
            key = (posting_book, commodity)
            totals[key] = totals.get(key, Decimal(0)) + quantized
        if any(_q(total) != 0 for total in totals.values()):
            raise AccountingInvariantError("journal transaction is not commodity balanced")
        sequence = int(
            connection.execute(
                "SELECT coalesce(max(book_sequence), 0) + 1 FROM "
                "accounting.journal_transactions WHERE accounting_book_id = ?",
                [book.value],
            ).fetchone()[0]
        )
        content_id = scoped_content_id(
            {
                "schema": "persistra.accounting.journal_transaction@1",
                "book": book,
                "sequence": sequence,
                "source": source,
                "kind": kind.value,
                "effective_at": effective_at,
                "postings": normalized,
                "reversal_of": reversal_of,
            }
        )
        transaction_id = JournalTransactionId.new()
        connection.execute(
            "INSERT INTO accounting.journal_transactions "
            "(journal_transaction_id, accounting_book_id, book_sequence, "
            "source_content_id, transaction_kind, effective_at, "
            "transaction_content_id, created_at, source_fingerprint, "
            "reversal_of_transaction_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                transaction_id.value,
                book.value,
                sequence,
                str(source),
                kind.value,
                effective_at,
                str(content_id),
                context.recorded_at,
                None if source_fingerprint is None else str(source_fingerprint),
                None if reversal_of is None else reversal_of.value,
            ],
        )
        rows: list[tuple[Any, ...]] = []
        for ordinal, posting in enumerate(normalized, 1):
            posting_content_id = scoped_content_id(
                {
                    "schema": "persistra.accounting.journal_posting@1",
                    "transaction": transaction_id,
                    "ordinal": ordinal,
                    "posting": posting,
                }
            )
            rows.append(
                (
                    transaction_id.value,
                    ordinal,
                    *posting,
                    str(posting_content_id),
                )
            )
        connection.executemany(
            "INSERT INTO journal_data.journal_postings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        return transaction_id

    def _write_lot_events(
        self,
        connection: ManagedConnection,
        transaction_id: JournalTransactionId,
        events: list[tuple[InventoryLotId, str, Decimal, Decimal]],
    ) -> None:
        for lot_id, kind, quantity, basis in events:
            prior = connection.execute(
                "SELECT event_ordinal FROM journal_data.lot_events "
                "WHERE inventory_lot_id = ? ORDER BY event_ordinal DESC LIMIT 1",
                [lot_id.value],
            ).fetchone()
            ordinal = 1 if prior is None else int(prior[0]) + 1
            content_id = scoped_content_id(
                {
                    "schema": "persistra.accounting.lot_event@1",
                    "lot": lot_id,
                    "ordinal": ordinal,
                    "transaction": transaction_id,
                    "kind": kind,
                    "quantity": quantity,
                    "basis": basis,
                }
            )
            connection.execute(
                "INSERT INTO journal_data.lot_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    lot_id.value,
                    ordinal,
                    transaction_id.value,
                    kind,
                    quantity,
                    basis,
                    str(content_id),
                ],
            )

    def _fifo_relief(
        self,
        connection: ManagedConnection,
        book: AccountingBookId,
        instrument_id: Any,
        quantity: Decimal,
    ) -> list[tuple[InventoryLotId, Decimal, Decimal]]:
        remaining = quantity
        result: list[tuple[InventoryLotId, Decimal, Decimal]] = []
        for lot_id, open_quantity, open_basis in self._open_lots(
            connection, book, instrument_id
        ):
            if remaining <= 0:
                break
            relieved = min(open_quantity, remaining)
            basis = _q(open_basis * relieved / open_quantity)
            result.append((lot_id, relieved, basis))
            remaining -= relieved
        if remaining != 0:
            raise AccountingInvariantError("FIFO lots do not cover sale")
        return result

    def _open_lots(
        self, connection: ManagedConnection, book: AccountingBookId, instrument_id: Any
    ) -> list[tuple[InventoryLotId, Decimal, Decimal]]:
        rows = connection.execute(
            "SELECT l.inventory_lot_id, sum(e.quantity_delta), sum(e.basis_delta_usd) "
            "FROM accounting.inventory_lots l JOIN journal_data.lot_events e "
            "USING (inventory_lot_id) WHERE l.accounting_book_id = ? "
            "AND l.instrument_id = ? GROUP BY l.inventory_lot_id, l.acquired_at "
            "HAVING sum(e.quantity_delta) > 0 ORDER BY l.acquired_at, l.inventory_lot_id",
            [book.value, instrument_id],
        ).fetchall()
        return [
            (InventoryLotId.parse(row[0]), Decimal(str(row[1])), Decimal(str(row[2])))
            for row in rows
        ]

    def _open_signed_lots(
        self, connection: ManagedConnection, book: AccountingBookId, instrument_id: Any
    ) -> list[tuple[InventoryLotId, Decimal, Decimal]]:
        rows = connection.execute(
            "SELECT l.inventory_lot_id, sum(e.quantity_delta), sum(e.basis_delta_usd) "
            "FROM accounting.inventory_lots l JOIN journal_data.lot_events e "
            "USING (inventory_lot_id) WHERE l.accounting_book_id = ? "
            "AND l.instrument_id = ? GROUP BY l.inventory_lot_id, l.acquired_at "
            "HAVING sum(e.quantity_delta) <> 0 ORDER BY l.acquired_at, l.inventory_lot_id",
            [book.value, instrument_id],
        ).fetchall()
        return [
            (InventoryLotId.parse(row[0]), Decimal(str(row[1])), Decimal(str(row[2])))
            for row in rows
        ]

    def _existing_source(
        self,
        connection: ManagedConnection,
        book: AccountingBookId,
        source: ContentId,
        fingerprint: ContentId | None = None,
    ) -> JournalTransactionId | None:
        row = connection.execute(
            "SELECT journal_transaction_id, source_fingerprint FROM "
            "accounting.journal_transactions "
            "WHERE accounting_book_id = ? AND source_content_id = ?",
            [book.value, str(source)],
        ).fetchone()
        if row is None:
            return None
        if fingerprint is not None and row[1] is not None and row[1] != str(fingerprint):
            raise AccountingRequestError(
                "source content ID was reused for different accounting facts"
            )
        return JournalTransactionId.parse(row[0])

    def _cash(self, connection: ManagedConnection, book: AccountingBookId) -> Decimal:
        value = connection.execute(
            "SELECT coalesce(sum(p.amount), 0) FROM journal_data.journal_postings p "
            "JOIN accounting.journal_transactions t USING (journal_transaction_id) "
            "WHERE t.accounting_book_id = ? AND p.posting_book = 'general' "
            "AND p.account_code = 'cash' AND p.commodity = 'USD'",
            [book.value],
        ).fetchone()[0]
        return Decimal(str(value))

    def _unsettled_cash(
        self, connection: ManagedConnection, book: AccountingBookId
    ) -> Decimal:
        value = connection.execute(
            "SELECT coalesce(sum(p.amount), 0) FROM journal_data.journal_postings p "
            "JOIN accounting.journal_transactions t USING (journal_transaction_id) "
            "WHERE t.accounting_book_id = ? AND p.posting_book = 'general' "
            "AND p.account_code = 'unsettled_cash' AND p.commodity = 'USD'",
            [book.value],
        ).fetchone()[0]
        return Decimal(str(value))

    def _position_rows(
        self, connection: ManagedConnection, book: AccountingBookId
    ) -> list[tuple[Any, Decimal]]:
        rows = connection.execute(
            "SELECT p.instrument_id, sum(p.amount) FROM journal_data.journal_postings p "
            "JOIN accounting.journal_transactions t USING (journal_transaction_id) "
            "WHERE t.accounting_book_id = ? AND p.posting_book = 'general' "
            "AND p.account_code = 'position' GROUP BY p.instrument_id "
            "HAVING sum(p.amount) <> 0 ORDER BY p.instrument_id",
            [book.value],
        ).fetchall()
        return [(row[0], Decimal(str(row[1]))) for row in rows]

    def _position(
        self, connection: ManagedConnection, book: AccountingBookId, instrument_id: Any
    ) -> Decimal:
        value = connection.execute(
            "SELECT coalesce(sum(p.amount), 0) FROM journal_data.journal_postings p "
            "JOIN accounting.journal_transactions t USING (journal_transaction_id) "
            "WHERE t.accounting_book_id = ? AND p.posting_book = 'general' "
            "AND p.account_code = 'position' AND p.instrument_id = ?",
            [book.value, instrument_id],
        ).fetchone()[0]
        return Decimal(str(value))

    def _reconcile(
        self, connection: ManagedConnection, book: AccountingBookId
    ) -> ReconciliationResult:
        unbalanced = connection.execute(
            "SELECT t.journal_transaction_id, p.posting_book, p.commodity, sum(p.amount) "
            "FROM accounting.journal_transactions t JOIN journal_data.journal_postings p "
            "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
            "GROUP BY t.journal_transaction_id, p.posting_book, p.commodity "
            "HAVING sum(p.amount) <> 0",
            [book.value],
        ).fetchall()
        sequence_gap = connection.execute(
            "SELECT count(*) <> coalesce(max(book_sequence), 0) FROM "
            "accounting.journal_transactions WHERE accounting_book_id = ?",
            [book.value],
        ).fetchone()[0]
        lot_mismatches = connection.execute(
            "WITH journal_positions AS ("
            "SELECT p.instrument_id, sum(p.amount) AS quantity FROM "
            "journal_data.journal_postings p JOIN accounting.journal_transactions t "
            "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
            "AND p.posting_book = 'general' AND p.account_code = 'position' "
            "GROUP BY p.instrument_id), lot_positions AS ("
            "SELECT l.instrument_id, sum(e.quantity_delta) AS quantity FROM "
            "accounting.inventory_lots l JOIN journal_data.lot_events e "
            "USING (inventory_lot_id) WHERE l.accounting_book_id = ? "
            "GROUP BY l.instrument_id) SELECT count(*) FROM journal_positions j "
            "FULL JOIN lot_positions l USING (instrument_id) "
            "WHERE coalesce(j.quantity, 0) <> coalesce(l.quantity, 0)",
            [book.value, book.value],
        ).fetchone()[0]
        positions = connection.execute(
            "SELECT count(*) FROM (SELECT p.instrument_id FROM journal_data.journal_postings p "
            "JOIN accounting.journal_transactions t USING (journal_transaction_id) "
            "WHERE t.accounting_book_id = ? AND p.account_code = 'position' "
            "GROUP BY p.instrument_id HAVING sum(p.amount) <> 0)",
            [book.value],
        ).fetchone()[0]
        lots = connection.execute(
            "SELECT count(*) FROM (SELECT l.inventory_lot_id FROM accounting.inventory_lots l "
            "JOIN journal_data.lot_events e USING (inventory_lot_id) "
            "WHERE l.accounting_book_id = ? GROUP BY l.inventory_lot_id "
            "HAVING sum(e.quantity_delta) <> 0)",
            [book.value],
        ).fetchone()[0]
        prefix = connection.execute(
            "SELECT book_sequence, transaction_content_id FROM "
            "accounting.journal_transactions WHERE accounting_book_id = ? "
            "ORDER BY book_sequence",
            [book.value],
        ).fetchall()
        root = scoped_content_id(
            {
                "schema": "persistra.accounting.journal_prefix@1",
                "book": book,
                "transactions": prefix,
            }
        )
        return ReconciliationResult(
            not unbalanced and not sequence_gap and int(lot_mismatches) == 0,
            self._cash(connection, book),
            int(positions),
            int(lots),
            root,
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("accounting writes require research_write mode")


@dataclass(frozen=True, slots=True)
class AccountingBook:
    _project: Project
    reference: BookRef

    def cash(self) -> Decimal:
        return self._project.services.accounting._cash(  # pyright: ignore[reportPrivateUsage]
            self._project._primary_connection(),  # pyright: ignore[reportPrivateUsage]
            self.reference.accounting_book_id,
        )

    def unsettled_cash(self) -> Decimal:
        return self._project.services.accounting._unsettled_cash(  # pyright: ignore[reportPrivateUsage]
            self._project._primary_connection(),  # pyright: ignore[reportPrivateUsage]
            self.reference.accounting_book_id,
        )

    def settlements(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT settlement_obligation_id, trade_transaction_id, instrument_id, "
            "due_at, signed_quantity, signed_cash_usd, status, "
            "settled_by_transaction_id FROM accounting.settlement_obligations "
            "WHERE accounting_book_id = ? ORDER BY due_at, settlement_obligation_id "
            "LIMIT ?",
            [self.reference.accounting_book_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("accounting settlements exceed max_rows")
        for column in (
            "settlement_obligation_id",
            "trade_transaction_id",
            "instrument_id",
            "settled_by_transaction_id",
        ):
            frame[column] = frame[column].astype("string")
        frame["due_at"] = pd.to_datetime(frame["due_at"], utc=True)
        return frame

    def positions(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT p.instrument_id, sum(p.amount) AS quantity FROM "
            "journal_data.journal_postings p JOIN accounting.journal_transactions t "
            "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
            "AND p.account_code = 'position' GROUP BY p.instrument_id "
            "HAVING sum(p.amount) <> 0 ORDER BY p.instrument_id LIMIT ?",
            [self.reference.accounting_book_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("accounting positions exceed max_rows")
        frame["instrument_id"] = frame["instrument_id"].astype("string")
        return frame

    def lots(self, *, max_rows: int = 100_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT l.inventory_lot_id, l.instrument_id, l.acquired_at, "
            "sum(e.quantity_delta) AS open_quantity, "
            "sum(e.basis_delta_usd) AS remaining_basis_usd FROM "
            "accounting.inventory_lots l JOIN journal_data.lot_events e "
            "USING (inventory_lot_id) WHERE l.accounting_book_id = ? "
            "GROUP BY l.inventory_lot_id, l.instrument_id, l.acquired_at "
            "HAVING sum(e.quantity_delta) <> 0 "
            "ORDER BY l.acquired_at, l.inventory_lot_id LIMIT ?",
            [self.reference.accounting_book_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("accounting lots exceed max_rows")
        for column in ("inventory_lot_id", "instrument_id"):
            frame[column] = frame[column].astype("string")
        frame["acquired_at"] = pd.to_datetime(frame["acquired_at"], utc=True)
        return frame

    def journal(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT t.book_sequence, t.transaction_kind, t.effective_at, "
            "t.source_content_id, p.posting_ordinal, p.posting_book, p.account_code, "
            "p.commodity, p.amount, p.instrument_id FROM "
            "accounting.journal_transactions t JOIN journal_data.journal_postings p "
            "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
            "ORDER BY t.book_sequence, p.posting_ordinal LIMIT ?",
            [self.reference.accounting_book_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("journal rows exceed max_rows")
        frame["effective_at"] = pd.to_datetime(frame["effective_at"], utc=True)
        for column in ("source_content_id", "instrument_id"):
            frame[column] = frame[column].astype("string")
        return frame

    def reconcile(self) -> ReconciliationResult:
        return self._project.services.accounting.reconcile(
            self.reference.accounting_book_id
        )

    def rebuild(self) -> ReconciliationResult:
        """Replay authoritative journal projections and verify their invariants."""
        return self.reconcile()
