from __future__ import annotations

import exchange_calendars as xcals  # pyright: ignore[reportMissingTypeStubs]
import pandas as pd
import pyarrow as pa

from persistra.core.timeframe import parse_timeframe
from persistra.data.schema import BAR_SCHEMA


def filter_regular_hours(table: pa.Table, timeframe: str, exchange: str = "XNYS") -> pa.Table:
    """Keep only regular-trading-hours bars for intraday timeframes.

    For minute/hour timeframes, retain bars whose tz-naive ET ``bar_time`` falls
    in ``[floor_to_hour(session_open), session_close]`` for that bar's session,
    using the ``exchange`` calendar's per-session schedule (so early-close days
    are truncated correctly). Daily bars and empty tables pass through unchanged.
    """
    _, unit = parse_timeframe(timeframe)
    if unit not in ("m", "h") or table.num_rows == 0:
        return table

    df = table.to_pandas()
    df["bar_time"] = pd.to_datetime(df["bar_time"])

    cal = xcals.get_calendar(exchange)
    tz = cal.tz
    lo = df["bar_time"].min().normalize()
    hi = df["bar_time"].max().normalize()
    sched = cal.schedule.loc[str(lo.date()) : str(hi.date())]

    # Floor the open to the hour so the bar covering the session open (e.g. the
    # 09:00 bar for a 09:30 XNYS open, which carries the opening auction) is kept.
    opens = sched["open"].dt.tz_convert(tz).dt.tz_localize(None).dt.floor("h")
    closes = sched["close"].dt.tz_convert(tz).dt.tz_localize(None)
    sess_index = sched.index
    if isinstance(sess_index, pd.DatetimeIndex) and sess_index.tz is not None:
        sess_index = sess_index.tz_localize(None)

    bounds: dict[pd.Timestamp, tuple[pd.Timestamp, pd.Timestamp]] = {
        pd.Timestamp(d).normalize(): (o, c)
        for d, o, c in zip(sess_index, opens, closes, strict=True)
    }

    def _keep(t: pd.Timestamp) -> bool:
        b = bounds.get(t.normalize())
        return b is not None and b[0] <= t <= b[1]

    out = df[df["bar_time"].map(_keep)].reset_index(drop=True)
    out["transactions"] = out["transactions"].astype("Int64")
    return pa.Table.from_pandas(out, schema=BAR_SCHEMA, preserve_index=False)
