# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false
"""Plotly figures for normalized market observations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from persistra.viz._common import (
    comparison_yscale,
    figure,
    finish_figure,
    plot_wide_series,
    sampled_positions,
    series_style,
    temporal_values,
)
from persistra.viz.general import plot_series

if TYPE_CHECKING:
    from persistra.model import BarSet


def plot_candlesticks(
    bars: BarSet,
    *,
    yscale: Literal["auto", "linear", "log"] = "auto",
) -> go.Figure:
    """Plot OHLC candles with volume and discontinuity-aware scaling."""
    frame = bars.frame
    discontinuities = _price_discontinuities(frame)
    positions = np.arange(len(frame))
    rising = frame["close"].ge(frame["open"])
    colors = np.where(rising, "#2ca02c", "#d62728")
    patterns = np.where(rising, "", "/")
    result = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.72, 0.28],
        subplot_titles=("Price", "Volume"),
    )
    result.add_trace(
        go.Candlestick(
            x=positions,
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name="OHLC",
            increasing={"line": {"color": "#2ca02c"}, "fillcolor": "#ffffff"},
            decreasing={"line": {"color": "#d62728"}, "fillcolor": "#d62728"},
            hovertemplate=(
                "Open %{open}<br>High %{high}<br>Low %{low}<br>Close %{close}<extra></extra>"
            ),
        ),
        row=1,
        col=1,
    )
    result.add_trace(
        go.Bar(
            x=positions,
            y=frame["volume"].to_numpy(dtype=float, na_value=np.nan),
            name="Volume",
            marker={"color": colors, "pattern": {"shape": patterns}},
            hovertemplate="Volume %{y}<extra></extra>",
        ),
        row=2,
        col=1,
    )
    temporal = pd.to_datetime(
        frame["date"].where(frame["date"].notna(), frame["timestamp"]), utc=True
    )
    tick_positions = sampled_positions(len(frame), maximum_ticks=6)
    include_time = frame["timestamp"].notna().any()
    labels = [
        temporal.iloc[position].strftime("%Y-%m-%d<br>%H:%M" if include_time else "%Y-%m-%d")
        for position in tick_positions
    ]
    result.update_xaxes(
        tickmode="array",
        tickvals=tick_positions,
        ticktext=labels,
        tickangle=-45,
        rangeslider_visible=False,
        row=2,
        col=1,
    )
    for position, ratio in discontinuities:
        boundary = position - 0.5
        result.add_shape(
            type="line",
            x0=boundary,
            x1=boundary,
            y0=0,
            y1=1,
            xref="x",
            yref="y domain",
            line={"color": "#222222", "dash": "dot"},
        )
        result.add_annotation(
            x=boundary,
            y=0.98,
            xref="x",
            yref="y domain",
            text=f"{ratio:.1f}x price gap",
            textangle=-90,
            showarrow=False,
            xanchor="left",
            yanchor="top",
        )
    resolved_scale = "log" if yscale == "auto" and discontinuities else yscale
    result.update_yaxes(
        title_text="Price",
        type="linear" if resolved_scale == "auto" else resolved_scale,
        row=1,
        col=1,
    )
    result.update_yaxes(title_text="Volume", row=2, col=1)
    result.update_xaxes(title_text="Date", row=2, col=1)
    result.update_layout(
        template="plotly_white",
        hovermode="x unified",
        showlegend=False,
        margin={"l": 70, "r": 30, "t": 70, "b": 80},
    )
    return result


def plot_returns(returns: pd.DataFrame) -> go.Figure:
    """Plot explicit return series."""
    result = plot_series(returns, ylabel="Return")
    _mark_missing_observations(result, returns)
    return result


def plot_cumulative_returns(
    values: pd.DataFrame,
    *,
    yscale: Literal["auto", "linear", "log"] = "auto",
) -> go.Figure:
    """Plot cumulative paths with automatic or explicit axis scaling."""
    growth = values + 1
    resolved_scale = comparison_yscale(growth, yscale)
    if resolved_scale == "log":
        if (growth.dropna() <= 0).any(axis=None):
            raise ValueError("log cumulative growth requires returns greater than -100 percent")
        result = plot_wide_series(growth, ylabel="Growth of 1")
    else:
        result = plot_wide_series(values, ylabel="Cumulative return")
    result.update_yaxes(type=resolved_scale)
    return result


def plot_drawdowns(values: pd.DataFrame) -> go.Figure:
    """Plot already calculated drawdowns."""
    result = plot_series(values, ylabel="Drawdown")
    result.add_hline(y=0, line_color="#222222")
    return result


def plot_rolling_volatility(values: pd.DataFrame) -> go.Figure:
    """Plot already calculated annualized rolling volatility."""
    return plot_series(values, ylabel="Annualized volatility")


def plot_bid_ask_history(history: pd.DataFrame) -> go.Figure:
    """Plot bid and ask history from more than one stored snapshot."""
    _history(history)
    result = figure()
    result.add_trace(
        go.Scatter(
            x=history["observed_at"],
            y=history["bid_price"],
            name="Bid",
            mode="lines",
            connectgaps=False,
            line={"dash": "solid"},
        )
    )
    result.add_trace(
        go.Scatter(
            x=history["observed_at"],
            y=history["ask_price"],
            name="Ask",
            mode="lines",
            connectgaps=False,
            line={"dash": "dash"},
        )
    )
    return finish_figure(result, xlabel="Observed at", ylabel="Price", showlegend=True)


def plot_spread_history(history: pd.DataFrame) -> go.Figure:
    """Plot absolute spread history from more than one stored snapshot."""
    _history(history)
    result = figure()
    result.add_trace(
        go.Scatter(
            x=history["observed_at"],
            y=history["ask_price"] - history["bid_price"],
            name="Spread",
            mode="lines",
            connectgaps=False,
        )
    )
    return finish_figure(
        result,
        xlabel="Observed at",
        ylabel="Absolute spread",
        showlegend=False,
    )


def _history(frame: pd.DataFrame) -> None:
    required = {"observed_at", "bid_price", "ask_price"}
    if len(frame) < 2 or not required.issubset(frame.columns):
        raise ValueError("quote history requires at least two snapshots with bid and ask")


def _price_discontinuities(frame: pd.DataFrame) -> list[tuple[int, float]]:
    """Locate adjacent open-to-previous-close gaps of at least twofold."""
    if len(frame) < 2:
        return []
    opens = frame["open"].to_numpy(dtype=float)
    previous_closes = frame["close"].to_numpy(dtype=float)[:-1]
    ratios = np.maximum(opens[1:] / previous_closes, previous_closes / opens[1:])
    return [
        (position, float(ratios[position - 1]))
        for position in range(1, len(frame))
        if ratios[position - 1] >= 2
    ]


def _mark_missing_observations(result: go.Figure, frame: pd.DataFrame) -> None:
    x_values = temporal_values(frame.index)
    for position, column in enumerate(frame.columns):
        observed = frame[column].notna().to_numpy()
        observed_positions = np.flatnonzero(observed)
        if not observed_positions.size:
            continue
        internal = ~observed
        internal[: observed_positions[0]] = False
        internal[observed_positions[-1] + 1 :] = False
        color = series_style(position)[0]
        for x_value in x_values[internal]:
            result.add_shape(
                type="line",
                x0=x_value,
                x1=x_value,
                y0=0,
                y1=0.035,
                xref="x",
                yref="paper",
                line={"color": color, "width": 2},
            )
