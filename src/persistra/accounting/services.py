"""Immutable foundational journal, cash, position, and FIFO lot service."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.accounting.models import (
    AccountingBookId,
    AccountingOpening,
    BookRef,
    DividendFacts,
    FillFacts,
    InventoryLotId,
    JournalTransactionId,
    ReconciliationResult,
    SplitFacts,
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

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project

_QUANTUM = Decimal("0.000000000001")


def _q(value: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        return value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)


class AccountingService:
    """Public accounting capability and simulation-owned transition kernel."""

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
        existing = connection.execute(
            "SELECT accounting_book_id FROM accounting.books WHERE opening_content_id = ?",
            [str(opening.source_content_id)],
        ).fetchone()
        if existing is not None:
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
        )
        return self.get(book_id)

    def _apply_fill(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        facts: FillFacts,
    ) -> JournalTransactionId:
        existing = self._existing_source(connection, book, facts.source_content_id)
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
        existing = self._existing_source(connection, book, facts.source_content_id)
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
        existing = self._existing_source(connection, book, facts.source_content_id)
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
        )

    def _post(
        self,
        connection: ManagedConnection,
        context: TransactionContext,
        book: AccountingBookId,
        source: ContentId,
        kind: TransactionKind,
        effective_at: datetime,
        postings: list[tuple[str, str, str, Decimal, Any]],
    ) -> JournalTransactionId:
        totals: dict[tuple[str, str], Decimal] = {}
        normalized: list[tuple[str, str, str, Decimal, Any]] = []
        for posting in postings:
            posting_book, account, commodity, amount, instrument_id = posting
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
            }
        )
        transaction_id = JournalTransactionId.new()
        connection.execute(
            "INSERT INTO accounting.journal_transactions VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?)",
            [
                transaction_id.value,
                book.value,
                sequence,
                str(source),
                kind.value,
                effective_at,
                str(content_id),
                context.recorded_at,
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

    def _existing_source(
        self, connection: ManagedConnection, book: AccountingBookId, source: ContentId
    ) -> JournalTransactionId | None:
        row = connection.execute(
            "SELECT journal_transaction_id FROM accounting.journal_transactions "
            "WHERE accounting_book_id = ? AND source_content_id = ?",
            [book.value, str(source)],
        ).fetchone()
        return None if row is None else JournalTransactionId.parse(row[0])

    def _cash(self, connection: ManagedConnection, book: AccountingBookId) -> Decimal:
        value = connection.execute(
            "SELECT coalesce(sum(p.amount), 0) FROM journal_data.journal_postings p "
            "JOIN accounting.journal_transactions t USING (journal_transaction_id) "
            "WHERE t.accounting_book_id = ? AND p.posting_book = 'general' "
            "AND p.account_code = 'cash' AND p.commodity = 'USD'",
            [book.value],
        ).fetchone()[0]
        return Decimal(str(value))

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
            not unbalanced,
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
