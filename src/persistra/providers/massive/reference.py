from __future__ import annotations

import datetime as dt
import warnings
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyarrow as pa

from persistra.data.schema import UNIVERSE_MEMBERSHIP_SCHEMA

if TYPE_CHECKING:
    from persistra.data.store import MarketDataWriter


DEFAULT_UNIVERSE_NAME = "default"


def fetch_tickers(
    client: Any,
    market: str = "stocks",
    active: bool | None = True,
    date: str | None = None,
) -> list[Any]:
    """Return ticker reference objects across all pages."""
    kwargs: dict[str, Any] = {"market": market, "active": active, "limit": 1000}
    if date is not None:
        kwargs["date"] = date
    return list(client.list_tickers(**kwargs))


def build_active_universe(
    store: MarketDataWriter,
    client: Any,
    market: str = "stocks",
    since: str = "2000-01-01",
    universe_name: str = DEFAULT_UNIVERSE_NAME,
) -> None:
    """Write active-only universe membership rows."""
    floor = pd.Timestamp(since).date()
    rows = [
        {
            "universe_name": str(universe_name),
            "symbol": str(t.ticker),
            "start_date": floor,
            "end_date": None,
        }
        for t in fetch_tickers(client, market=market, active=True)
    ]
    _write_rows(store, rows)


def build_point_in_time_universe(
    store: MarketDataWriter,
    client: Any,
    market: str = "stocks",
    *,
    universe_name: str = DEFAULT_UNIVERSE_NAME,
    as_of: str | None = None,
    start_floor: str | None = None,
) -> None:
    """Write universe membership intervals from historical reference metadata."""
    rows: list[dict[str, Any]] = []
    floor = _date_or_none(start_floor)
    for ticker in fetch_tickers(client, market=market, active=None, date=as_of):
        details = _ticker_details(client, ticker, as_of)
        symbol = _field(details, "ticker", _field(ticker, "ticker"))
        if symbol is None:
            continue
        start_date = _date_or_none(_field(details, "list_date")) or floor
        end_date = _date_or_none(_field(details, "delisted_utc", _field(ticker, "delisted_utc")))
        rows.append(
            _membership_row(
                universe_name=universe_name,
                symbol=str(symbol),
                start_date=start_date,
                end_date=end_date,
            )
        )
        rows.extend(
            _symbol_change_rows(
                client=client,
                universe_name=universe_name,
                symbol=str(symbol),
                floor=floor,
            )
        )
    _write_rows(store, _dedupe_rows(rows))


def build_universe(
    store: MarketDataWriter,
    client: Any,
    market: str = "stocks",
    since: str = "2000-01-01",
    universe_name: str = DEFAULT_UNIVERSE_NAME,
) -> None:
    """Write active-only universe membership rows.

    Deprecated:
        Use ``build_point_in_time_universe`` for historical research, or
        ``build_active_universe`` for explicitly active-only workflows.
    """
    warnings.warn(
        "build_universe() is active-only and can introduce survivorship bias; "
        "use build_point_in_time_universe() for historical research or "
        "build_active_universe() for explicit active-only workflows.",
        DeprecationWarning,
        stacklevel=2,
    )
    build_active_universe(
        store,
        client,
        market=market,
        since=since,
        universe_name=universe_name,
    )


def _ticker_details(client: Any, ticker: Any, as_of: str | None) -> Any:
    symbol = _field(ticker, "ticker")
    if symbol is None or not hasattr(client, "get_ticker_details"):
        return ticker
    try:
        return client.get_ticker_details(str(symbol), date=as_of)
    except TypeError:
        try:
            return client.get_ticker_details(str(symbol))
        except Exception:
            return ticker
    except Exception:
        return ticker


def _symbol_change_rows(
    *,
    client: Any,
    universe_name: str,
    symbol: str,
    floor: dt.date | None,
) -> list[dict[str, Any]]:
    if not hasattr(client, "get_ticker_events"):
        return []
    try:
        changes = client.get_ticker_events(symbol, types="ticker_change")
    except TypeError:
        try:
            changes = client.get_ticker_events(symbol)
        except Exception:
            return []
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    events = getattr(changes, "events", None) or []
    for event in events:
        previous = _field(_field(event, "ticker_change"), "ticker")
        event_date = _date_or_none(_field(event, "date"))
        if previous is None or event_date is None or str(previous) == symbol:
            continue
        rows.append(
            _membership_row(
                universe_name=universe_name,
                symbol=str(previous),
                start_date=floor,
                end_date=event_date - dt.timedelta(days=1),
            )
        )
    return rows


def _membership_row(
    *,
    universe_name: str,
    symbol: str,
    start_date: dt.date | None,
    end_date: dt.date | None,
) -> dict[str, Any]:
    return {
        "universe_name": str(universe_name),
        "symbol": symbol,
        "start_date": start_date or dt.date(1900, 1, 1),
        "end_date": end_date,
    }


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, dt.date, dt.date | None], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["universe_name"]),
            str(row["symbol"]),
            row["start_date"],
            row["end_date"],
        )
        deduped[key] = row
    return sorted(
        deduped.values(),
        key=lambda row: (
            str(row["universe_name"]),
            str(row["symbol"]),
            row["start_date"],
            row["end_date"] or dt.date.max,
        ),
    )


def _write_rows(store: MarketDataWriter, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    df = pd.DataFrame(
        rows,
        columns=["universe_name", "symbol", "start_date", "end_date"],
    )
    table = pa.Table.from_pandas(df, schema=UNIVERSE_MEMBERSHIP_SCHEMA, preserve_index=False)
    store.write_universe(table)


def _date_or_none(value: Any) -> dt.date | None:
    if value in (None, ""):
        return None
    return pd.Timestamp(value).date()


def _field(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
