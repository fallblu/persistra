from __future__ import annotations

from typing import TYPE_CHECKING

import exchange_calendars as xcals
import pandas as pd
import plotly.graph_objects as go

from persistra.core.timeframe import parse_timeframe, timeframe_duration
from persistra.viz._style import color_for, styled_figure

if TYPE_CHECKING:
    from sklearn.base import TransformerMixin


def price_plot(prices: pd.DataFrame, *, normalize: bool = False) -> go.Figure:
    """One line per symbol. ``normalize=True`` rebases each series to 100."""
    fig = styled_figure(title="Prices", xaxis_title="Date", yaxis_title="Price")
    data = prices.astype(float)
    if normalize and not data.empty:
        data = data.divide(data.iloc[0]).multiply(100.0)
    for i, col in enumerate(data.columns):
        s = data[col].dropna()
        fig.add_trace(
            go.Scatter(x=s.index, y=s.values, name=str(col), line=dict(color=color_for(i)))
        )
    return fig


def _build_rangebreaks(ohlcv: pd.DataFrame, timeframe: str, exchange: str) -> list[dict]:
    if ohlcv.empty:
        return []

    cal = xcals.get_calendar(exchange)
    start_str = ohlcv.index[0].strftime("%Y-%m-%d")
    end_str = ohlcv.index[-1].strftime("%Y-%m-%d")
    sessions = cal.sessions_in_range(start_str, end_str)

    breaks: list[dict] = [{"bounds": ["sat", "mon"]}]

    all_bdays = pd.bdate_range(start_str, end_str)
    session_dates = {s.date() for s in sessions}
    for d in all_bdays:
        if d.date() not in session_dates:
            breaks.append({"values": [d.strftime("%Y-%m-%d")], "dvalue": 86_400_000})

    _, unit = parse_timeframe(timeframe)
    if unit in ("m", "h") and len(sessions) > 0:
        tz = cal.tz
        sched = cal.schedule.loc[sessions[0] : sessions[-1]]
        first_open = sched["open"].iloc[0]
        first_close = sched["close"].iloc[0]
        open_local = pd.Timestamp(first_open).tz_convert(tz)
        close_local = pd.Timestamp(first_close).tz_convert(tz)
        open_h = open_local.hour + open_local.minute / 60.0
        close_h = close_local.hour + close_local.minute / 60.0
        breaks.append({"bounds": [close_h, open_h], "pattern": "hour"})

    return breaks


def candlestick_plot(
    ohlcv: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    exchange: str = "XNYS",
) -> go.Figure:
    """Candlestick for one symbol's OHLCV frame (indexed by bar_time).

    Non-trading time is excluded from the x-axis using the exchange calendar.
    ``symbol`` is the symbol of the asset in question.
    ``timeframe`` must be a valid timeframe string (e.g. ``"1m"``, ``"1h"``, ``"1d"``).
    ``exchange`` is an ISO MIC code; defaults to ``"XNYS"`` (NYSE).
    """
    fig = styled_figure(title=symbol, xaxis_title="Date", yaxis_title="Price")
    if not ohlcv.empty:
        fig.add_trace(
            go.Candlestick(
                x=ohlcv.index,
                open=ohlcv["open"].astype(float),
                high=ohlcv["high"].astype(float),
                low=ohlcv["low"].astype(float),
                close=ohlcv["close"].astype(float),
                name="OHLC",
                xperiod=int(timeframe_duration(timeframe).total_seconds() * 1000),
                xperiodalignment="start",
            )
        )
    rangebreaks = _build_rangebreaks(ohlcv, timeframe, exchange)
    if rangebreaks:
        fig.update_xaxes(rangebreaks=rangebreaks)
    return fig


def correlation_heatmap(prices: pd.DataFrame) -> go.Figure:
    """Return-correlation matrix as a heatmap."""
    fig = styled_figure(title="Return correlation")
    corr = prices.astype(float).pct_change().corr()
    fig.add_trace(
        go.Heatmap(
            z=corr.to_numpy(),
            x=[str(c) for c in corr.columns],
            y=[str(c) for c in corr.index],
            colorscale="thermal",
            zmid=0.0,
            zmin=-1.0,
            zmax=1.0,
        )
    )
    return fig


def feature_plot(
    prices: pd.DataFrame,
    transformer: TransformerMixin,
    *,
    name: str | None = None,
) -> go.Figure:
    """Run a persistra feature transformer over ``prices`` and plot the result.

    The transformer receives the ``(T, n_symbols)`` price array (its standard
    input contract). Outputs shaped ``(T, n_symbols)`` are plotted as one line
    per symbol aligned to the tail of the price index; other shapes are flattened
    to a single line.
    """
    label = name or type(transformer).__name__
    fig = styled_figure(title=label, xaxis_title="Date", yaxis_title=label)
    data = prices.astype(float)
    out = transformer.fit(data.to_numpy()).transform(data.to_numpy())  # type: ignore[union-attr]
    arr = pd.DataFrame(out)
    if arr.shape[1] == data.shape[1] and not arr.empty:
        arr.columns = data.columns
        # -len(arr) with len(arr)==0 would be -0==0 and select the whole index;
        # the `not arr.empty` guard above rules that out, so the tail slice is safe.
        arr.index = data.index[-len(arr) :]
        for i, col in enumerate(arr.columns):
            s = arr[col].dropna()
            fig.add_trace(
                go.Scatter(x=s.index, y=s.values, name=str(col), line=dict(color=color_for(i)))
            )
    else:
        flat = pd.Series(out.ravel() if hasattr(out, "ravel") else out)
        fig.add_trace(go.Scatter(y=flat.values, name=label, line=dict(color=color_for(0))))
    return fig
