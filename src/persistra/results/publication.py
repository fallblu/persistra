"""Pure normalized-result publication helpers shared by simulation engines."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from persistra._identity import scoped_identity_content_id as scoped_content_id

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persistra.db.connection import ManagedConnection
    from persistra.domain import EntityId
    from persistra.simulation import RunRecordId


def publish_accounting_rows(
    connection: ManagedConnection,
    run_id: RunRecordId,
    accounting_book_id: EntityId,
) -> None:
    """Snapshot journal, settlement, lot, borrow, and cash-flow rows."""
    parameters = [run_id.value, accounting_book_id.value]
    connection.execute(
        "INSERT INTO result_data.journal_transactions "
        "SELECT ?, book_sequence, journal_transaction_id, transaction_kind, "
        "effective_at, source_content_id, transaction_content_id FROM "
        "accounting.journal_transactions WHERE accounting_book_id = ? "
        "ORDER BY book_sequence",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.journal_postings "
        "SELECT ?, t.book_sequence, p.posting_ordinal, p.posting_book, "
        "p.account_code, p.commodity, p.amount, p.instrument_id, "
        "p.posting_content_id FROM accounting.journal_transactions t JOIN "
        "journal_data.journal_postings p USING (journal_transaction_id) "
        "WHERE t.accounting_book_id = ? ORDER BY t.book_sequence, p.posting_ordinal",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.settlements "
        "SELECT ?, row_number() OVER (ORDER BY due_at, settlement_obligation_id), "
        "settlement_obligation_id, instrument_id, due_at, signed_quantity, "
        "signed_cash_usd, status, obligation_content_id FROM "
        "accounting.settlement_obligations WHERE accounting_book_id = ? "
        "ORDER BY due_at, settlement_obligation_id",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.lots "
        "SELECT ?, row_number() OVER (ORDER BY acquired_at, inventory_lot_id), "
        "inventory_lot_id, instrument_id, acquired_at, original_quantity, "
        "original_basis_usd, lot_content_id FROM accounting.inventory_lots "
        "WHERE accounting_book_id = ? ORDER BY acquired_at, inventory_lot_id",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.lot_events "
        "SELECT ?, e.inventory_lot_id, e.event_ordinal, e.event_kind, "
        "e.quantity_delta, e.basis_delta_usd, e.event_content_id FROM "
        "journal_data.lot_events e JOIN accounting.inventory_lots l "
        "USING (inventory_lot_id) WHERE l.accounting_book_id = ? "
        "ORDER BY e.inventory_lot_id, e.event_ordinal",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.borrow "
        "SELECT ?, row_number() OVER (ORDER BY effective_from, "
        "borrow_authorization_id), instrument_id, effective_from, effective_until, "
        "quantity, 'authorized', authorization_content_id FROM "
        "accounting.borrow_authorizations WHERE accounting_book_id = ? "
        "ORDER BY effective_from, borrow_authorization_id",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.cash_flows "
        "SELECT ?, row_number() OVER (ORDER BY effective_at, book_sequence), "
        "effective_at, transaction_kind, sum(p.amount), t.transaction_content_id "
        "FROM accounting.journal_transactions t JOIN journal_data.journal_postings p "
        "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
        "AND p.posting_book = 'general' AND p.account_code = 'cash' "
        "AND t.transaction_kind NOT IN ('opening', 'trade', 'settlement') "
        "GROUP BY effective_at, book_sequence, transaction_kind, "
        "t.transaction_content_id HAVING sum(p.amount) != 0 "
        "ORDER BY effective_at, book_sequence",
        parameters,
    )


def publish_vectorized_rows(
    connection: ManagedConnection,
    run_id: RunRecordId,
    simulation_id: EntityId,
    findings: Sequence[str],
) -> None:
    """Normalize engine-specific vectorized rows and quality evidence."""
    parameters = [run_id.value, simulation_id.value]
    connection.execute(
        "INSERT INTO result_data.rebalance_decisions "
        "SELECT ?, row_number() OVER (ORDER BY decision_at), decision_at, "
        "execution_at, state, reason_code, decision_content_id FROM "
        "simulation_data.rebalance_decisions WHERE vectorized_simulation_id = ? "
        "ORDER BY decision_at",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.fills "
        "SELECT ?, fill_ordinal, NULL, decision_at, execution_at, instrument_id, "
        "side, quantity, reference_price_usd, fill_price_usd, commission_usd, "
        "slippage_usd, 0, 0, fill_content_id FROM "
        "simulation_data.synthetic_fills WHERE vectorized_simulation_id = ? "
        "ORDER BY fill_ordinal",
        parameters,
    )
    connection.execute(
        "INSERT INTO result_data.trade_intents "
        "SELECT ?, fill_ordinal, decision_at, instrument_id, "
        "CASE WHEN side = 'buy' THEN quantity ELSE -quantity END, "
        "'executed', NULL, fill_content_id FROM simulation_data.synthetic_fills "
        "WHERE vectorized_simulation_id = ? ORDER BY fill_ordinal",
        parameters,
    )
    publish_exposures(connection, run_id)
    publish_findings(connection, run_id, findings)


def publish_exposures(
    connection: ManagedConnection,
    run_id: RunRecordId,
) -> None:
    connection.execute(
        "INSERT INTO result_data.exposures "
        "SELECT run_record_id, sample_ordinal, valued_at, 'portfolio', 'gross', "
        "gross_exposure_usd, CASE WHEN nav_usd = 0 THEN NULL ELSE "
        "gross_exposure_usd / nav_usd END, state, source_content_id FROM "
        "result_data.equity WHERE run_record_id = ? UNION ALL "
        "SELECT run_record_id, sample_ordinal, valued_at, 'portfolio', 'net', "
        "net_exposure_usd, CASE WHEN nav_usd = 0 THEN NULL ELSE "
        "net_exposure_usd / nav_usd END, state, source_content_id FROM "
        "result_data.equity WHERE run_record_id = ?",
        [run_id.value, run_id.value],
    )


def publish_findings(
    connection: ManagedConnection,
    run_id: RunRecordId,
    findings: Sequence[str],
) -> None:
    rows: list[tuple[object, ...]] = []
    for ordinal, finding in enumerate(dict.fromkeys(findings), 1):
        content_id = scoped_content_id(
            {
                "schema": "persistra.results.quality_finding@1",
                "run_record_id": run_id,
                "ordinal": ordinal,
                "reason_code": finding,
            }
        )
        rows.append(
            (
                run_id.value,
                ordinal,
                "fidelity",
                "warning",
                finding,
                str(content_id),
            )
        )
    if rows:
        connection.executemany(
            "INSERT INTO result_data.quality_findings VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )


def findings_json(findings: Sequence[str]) -> str:
    return json.dumps(tuple(dict.fromkeys(findings)), separators=(",", ":"))


__all__ = [
    "findings_json",
    "publish_accounting_rows",
    "publish_exposures",
    "publish_findings",
    "publish_vectorized_rows",
]
