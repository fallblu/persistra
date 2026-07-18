"""Pure normalized-result kernels shared by simulation publication paths."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.db.connection import ManagedConnection
    from persistra.domain import EntityId
    from persistra.simulation import RunRecordId


def event_valuation_rows(
    connection: ManagedConnection,
    *,
    run_id: RunRecordId,
    book_id: EntityId,
    opening_at: datetime,
    opening_cash: Decimal,
    horizon_at: datetime,
    bars: pd.DataFrame,
    journal_content_id: object,
) -> tuple[
    list[tuple[Any, ...]],
    list[tuple[Any, ...]],
    list[tuple[Any, ...]],
    list[tuple[Any, ...]],
]:
    """Value an event book at opening and horizon from causally complete bars."""
    balances = connection.execute(
        "SELECT p.account_code, p.instrument_id, sum(p.amount) FROM "
        "accounting.journal_transactions t JOIN journal_data.journal_postings p "
        "USING (journal_transaction_id) WHERE t.accounting_book_id = ? "
        "AND p.posting_book = 'general' AND p.account_code IN "
        "('cash', 'unsettled_cash', 'position') "
        "GROUP BY p.account_code, p.instrument_id",
        [book_id.value],
    ).fetchall()
    settled_cash = sum(
        (Decimal(str(row[2])) for row in balances if row[0] == "cash"),
        Decimal(0),
    )
    unsettled_cash = sum(
        (Decimal(str(row[2])) for row in balances if row[0] == "unsettled_cash"),
        Decimal(0),
    )
    quantities = {
        str(row[1]): Decimal(str(row[2]))
        for row in balances
        if row[0] == "position" and row[1] is not None and Decimal(str(row[2])) != 0
    }
    marks = _latest_marks(bars, horizon_at)
    market_values = {
        instrument: quantity * marks[instrument]
        for instrument, quantity in quantities.items()
        if instrument in marks
    }
    complete = len(market_values) == len(quantities)
    gross = sum((abs(value) for value in market_values.values()), Decimal(0))
    net = sum(market_values.values(), Decimal(0))
    nav = settled_cash + unsettled_cash + net
    prefix = int(
        connection.execute(
            "SELECT coalesce(max(book_sequence), 0) FROM "
            "accounting.journal_transactions WHERE accounting_book_id = ?",
            [book_id.value],
        ).fetchone()[0]
    )
    source = scoped_content_id(
        {
            "schema": "persistra.results.event_valuation@1",
            "run_record_id": run_id,
            "valued_at": horizon_at,
            "journal_content_id": journal_content_id,
            "settled_cash": settled_cash,
            "unsettled_cash": unsettled_cash,
            "quantities": tuple(sorted(quantities.items())),
            "marks": tuple(sorted(marks.items())),
        }
    )
    opening_source = scoped_content_id(
        {
            "schema": "persistra.results.event_opening@1",
            "run_record_id": run_id,
            "opening_at": opening_at,
            "opening_cash": opening_cash,
        }
    )
    equity = [
        (
            run_id.value,
            1,
            opening_at,
            1,
            opening_cash,
            Decimal(0),
            Decimal(0),
            "complete",
            str(opening_source),
        ),
        (
            run_id.value,
            2,
            horizon_at,
            prefix,
            nav,
            gross,
            net,
            "complete" if complete else "mark_unavailable",
            str(source),
        ),
    ]
    cash = [
        (run_id.value, 1, opening_at, opening_cash, str(opening_source)),
        (run_id.value, 2, horizon_at, settled_cash, str(source)),
    ]
    positions = [
        (
            run_id.value,
            2,
            horizon_at,
            instrument,
            quantity,
            marks[instrument],
            market_values[instrument],
            str(source),
        )
        for instrument, quantity in sorted(quantities.items())
        if instrument in marks
    ]
    returns = [
        (
            run_id.value,
            1,
            opening_at,
            horizon_at,
            opening_cash,
            nav,
            None if opening_cash == 0 else float(nav / opening_cash - 1),
            "computed" if complete and opening_cash != 0 else "unavailable",
            str(source),
        )
    ]
    return equity, returns, positions, cash


def _latest_marks(bars: pd.DataFrame, horizon_at: datetime) -> dict[str, Decimal]:
    eligible = bars[
        pd.to_datetime(bars["interval_end"], utc=True) <= pd.Timestamp(horizon_at)
    ].sort_values(["instrument_id", "interval_end"])
    if eligible.empty:
        return {}
    latest = eligible.groupby("instrument_id", sort=True).tail(1)
    return {
        str(row.instrument_id): Decimal(str(cast("Any", row.close)))
        for row in latest.itertuples(index=False)
        if not pd.isna(cast("Any", row.close))
    }


__all__ = ["event_valuation_rows"]
