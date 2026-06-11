from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as pa

from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA

if TYPE_CHECKING:
    from persistra.data.store import MarketDataWriter


def fetch_tickers(client: Any, market: str = "stocks", active: bool = True) -> list[Any]:
    """Return active ticker reference objects across all pages."""
    return list(client.list_tickers(market=market, active=active, limit=1000))


def build_universe(
    store: MarketDataWriter,
    client: Any,
    market: str = "stocks",
    since: str = "2000-01-01",
) -> None:
    """Write a point-in-time universe membership table.

    Each active ticker becomes an open membership row (``end_date`` null) with
    ``start_date`` set to the ``since`` floor (the list-tickers model carries no
    list date).
    """
    floor = pd.Timestamp(since).date()
    rows: list[dict[str, Any]] = []
    for t in fetch_tickers(client, market=market, active=True):
        rows.append({"symbol": str(t.ticker), "start_date": floor, "end_date": None})
    if not rows:
        return
    df = pd.DataFrame(rows, columns=["symbol", "start_date", "end_date"])
    table = pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    store.write_universe(table)
