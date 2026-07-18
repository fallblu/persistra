from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from persistra import Project, ProjectMode
from persistra.accounting import (
    AccountingOpening,
    CashFlowFacts,
    ReversalFacts,
    SettlementFacts,
    SettlementObligationId,
    TradeFillFacts,
)
from persistra.domain import ContentId, FixedClock
from persistra.errors import AccountingRequestError
from persistra.reference import InstrumentId

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 1, 5, 12, tzinfo=UTC)


def test_signed_fifo_cross_zero_settlement_and_rebuild(tmp_path: Path) -> None:
    root = Project.init(tmp_path / "project").root
    instrument = InstrumentId.new()
    opened_at = NOW - timedelta(days=5)
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        book = project.services.accounting.create_book(
            AccountingOpening(
                opened_at,
                Decimal("10000"),
                ContentId.from_bytes(b"accounting-opening"),
            )
        )
        book_id = book.reference.accounting_book_id
        fills = (
            TradeFillFacts(
                ContentId.from_bytes(b"short-ten"),
                instrument,
                opened_at + timedelta(minutes=1),
                opened_at + timedelta(days=2),
                Decimal("-10"),
                Decimal("100"),
                Decimal("2"),
                Decimal("3"),
            ),
            TradeFillFacts(
                ContentId.from_bytes(b"cover-four"),
                instrument,
                opened_at + timedelta(minutes=2),
                opened_at + timedelta(days=2),
                Decimal("4"),
                Decimal("80"),
                Decimal("1"),
            ),
            TradeFillFacts(
                ContentId.from_bytes(b"cross-zero"),
                instrument,
                opened_at + timedelta(minutes=3),
                opened_at + timedelta(days=2),
                Decimal("8"),
                Decimal("90"),
            ),
        )
        transaction_ids = [
            project.services.accounting.apply_trade(book_id, fill) for fill in fills
        ]
        assert project.services.accounting.apply_trade(book_id, fills[0]) == (
            transaction_ids[0]
        )
        assert book.cash() == Decimal("10000")
        assert book.unsettled_cash() == Decimal("-43")
        assert book.positions()["quantity"].tolist() == [Decimal("2")]
        open_lots = book.lots()
        assert open_lots["open_quantity"].tolist() == [Decimal("2")]
        assert open_lots["remaining_basis_usd"].tolist() == [Decimal("180")]

        settlements = book.settlements()
        for ordinal, row in settlements.iterrows():
            project.services.accounting.apply_settlement(
                book_id,
                SettlementFacts(
                    ContentId.from_bytes(f"settlement-{ordinal}".encode()),
                    row["due_at"].to_pydatetime(),
                    SettlementObligationId.parse(row["settlement_obligation_id"]),
                ),
            )
        assert book.cash() == Decimal("9957")
        assert book.unsettled_cash() == 0
        assert set(book.settlements()["status"]) == {"settled"}
        reconciliation = book.rebuild()
        assert reconciliation.balanced
        journal = book.journal()
        balances = journal.groupby(
            ["book_sequence", "posting_book", "commodity"], dropna=False
        )["amount"].sum()
        assert (balances == 0).all()


def test_cash_flow_idempotency_conflict_and_linked_reversal(tmp_path: Path) -> None:
    root = Project.init(tmp_path / "project").root
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        book = project.services.accounting.create_book(
            AccountingOpening(
                NOW - timedelta(days=1),
                Decimal("1000"),
                ContentId.from_bytes(b"opening"),
            )
        )
        book_id = book.reference.accounting_book_id
        source = ContentId.from_bytes(b"deposit")
        deposit = CashFlowFacts(source, NOW, Decimal("500"))
        transaction_id = project.services.accounting.apply_cash_flow(book_id, deposit)
        assert project.services.accounting.apply_cash_flow(book_id, deposit) == transaction_id
        with pytest.raises(AccountingRequestError, match="different accounting facts"):
            project.services.accounting.apply_cash_flow(
                book_id, CashFlowFacts(source, NOW, Decimal("501"))
            )
        reversal = ReversalFacts(
            ContentId.from_bytes(b"reverse-deposit"),
            NOW + timedelta(minutes=1),
            transaction_id,
        )
        reversal_id = project.services.accounting.reverse(book_id, reversal)
        assert project.services.accounting.reverse(book_id, reversal) == reversal_id
        assert book.cash() == Decimal("1000")
        with pytest.raises(AccountingRequestError, match="already reversed"):
            project.services.accounting.reverse(
                book_id,
                ReversalFacts(
                    ContentId.from_bytes(b"reverse-again"),
                    NOW + timedelta(minutes=2),
                    transaction_id,
                ),
            )
        assert book.reconcile().balanced
