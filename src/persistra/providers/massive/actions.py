from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as pa

from persistra.data.schema import CORPORATE_ACTION_SCHEMA

if TYPE_CHECKING:
    from persistra.data.store import MarketDataWriter


def fetch_splits(client: Any, symbol: str) -> list[dict[str, Any]]:
    """Return split records for one symbol as CORPORATE_ACTION rows (ratio = to/from)."""
    rows: list[dict[str, Any]] = []
    for s in client.list_splits(ticker=symbol):
        ratio = float(s.split_to) / float(s.split_from)
        rows.append(
            {
                "date": pd.Timestamp(s.execution_date).date(),
                "symbol": symbol,
                "action_type": "split",
                "amount": None,
                "ratio": ratio,
            }
        )
    return rows


def fetch_dividends(client: Any, symbol: str) -> list[dict[str, Any]]:
    """Return dividend records for one symbol as CORPORATE_ACTION rows (amount = cash/share)."""
    rows: list[dict[str, Any]] = []
    for d in client.list_dividends(ticker=symbol):
        rows.append(
            {
                "date": pd.Timestamp(d.ex_dividend_date).date(),
                "symbol": symbol,
                "action_type": "dividend",
                "amount": float(d.cash_amount),
                "ratio": None,
            }
        )
    return rows


def ingest_actions(symbols: list[str], store: MarketDataWriter, client: Any) -> None:
    """Fetch splits + dividends for each symbol and merge into the store."""
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        rows.extend(fetch_splits(client, symbol))
        rows.extend(fetch_dividends(client, symbol))
    if not rows:
        return
    df = pd.DataFrame(rows, columns=["date", "symbol", "action_type", "amount", "ratio"])
    table = pa.Table.from_pandas(df, schema=CORPORATE_ACTION_SCHEMA, preserve_index=False)
    store.write_corporate_actions(table)
