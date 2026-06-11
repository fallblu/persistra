from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from persistra.viz._style import color_for, styled_figure

if TYPE_CHECKING:
    from persistra.core.result import Result


def trades_on_price(result: Result, prices: pd.DataFrame, symbol: str) -> go.Figure:
    """Plot one symbol's price with buy/sell markers from the trade log.

    Buys (positive quantity) render as up-triangles, sells as down-triangles.
    """
    fig = styled_figure(title=f"Trades — {symbol}", xaxis_title="Date", yaxis_title="Price")
    if symbol in prices.columns:
        s = prices[symbol].astype(float).dropna()
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=symbol, line=dict(color=color_for(0))))
    trades = result.trades
    if not trades.empty:
        sym_trades = trades[trades["symbol"] == symbol]
        buys = sym_trades[sym_trades["quantity"] > 0]
        sells = sym_trades[sym_trades["quantity"] < 0]
        if not buys.empty:
            fig.add_trace(
                go.Scatter(
                    x=pd.to_datetime(buys["timestamp"]),
                    y=buys["fill_price"].astype(float),
                    mode="markers",
                    name="Buy",
                    marker=dict(symbol="triangle-up", size=10, color="#2ca02c"),
                )
            )
        if not sells.empty:
            fig.add_trace(
                go.Scatter(
                    x=pd.to_datetime(sells["timestamp"]),
                    y=sells["fill_price"].astype(float),
                    mode="markers",
                    name="Sell",
                    marker=dict(symbol="triangle-down", size=10, color="#d62728"),
                )
            )
    return fig


def weights_plot(result: Result, symbols: list[str] | None = None, top_k: int = 10) -> go.Figure:
    """Per-symbol target-weight evolution from the position log.

    Without ``symbols``, plots the ``top_k`` symbols by peak absolute weight.
    """
    fig = styled_figure(title="Target weights", xaxis_title="Date", yaxis_title="Weight")
    positions = result.positions
    if positions.empty:
        return fig
    wide = positions.pivot_table(index="bar_time", columns="symbol", values="weight").fillna(0.0)
    if symbols is not None:
        cols = [s for s in symbols if s in wide.columns]
    else:
        ranked = wide.abs().max().sort_values(ascending=False)
        cols = list(ranked.head(top_k).index)
    for i, col in enumerate(cols):
        s = wide[col]
        fig.add_trace(
            go.Scatter(x=s.index, y=s.values, name=str(col), line=dict(color=color_for(i)))
        )
    return fig


def signal_plot(result: Result, name: str, symbol: str | None = None) -> go.Figure:
    """Plot a recorded diagnostic over time.

    Raises ``KeyError`` (naming the available diagnostics) when ``name`` was not
    recorded. ``symbol`` restricts a per-symbol diagnostic to one column.
    """
    wide = result.diagnostic(name)  # raises KeyError with available names
    fig = styled_figure(title=name, xaxis_title="Date", yaxis_title=name)
    cols = [symbol] if symbol is not None else list(wide.columns)
    for i, col in enumerate(cols):
        if col not in wide.columns:
            continue
        s = wide[col].dropna()
        fig.add_trace(
            go.Scatter(x=s.index, y=s.values, name=str(col), line=dict(color=color_for(i)))
        )
    return fig


def price_with_signal(
    result: Result,
    prices: pd.DataFrame,
    symbol: str,
    name: str,
) -> go.Figure:
    """Two stacked, shared-x panels: price + trades (top), driving signal (bottom)."""
    wide = result.diagnostic(name)  # raises KeyError if not recorded
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.65, 0.35])

    if symbol in prices.columns:
        s = prices[symbol].astype(float).dropna()
        fig.add_trace(
            go.Scatter(x=s.index, y=s.values, name=symbol, line=dict(color=color_for(0))),
            row=1,
            col=1,
        )
    trades = result.trades
    if not trades.empty:
        sym_trades = trades[trades["symbol"] == symbol]
        for label, mask, marker, col_hex in (
            ("Buy", sym_trades["quantity"] > 0, "triangle-up", "#2ca02c"),
            ("Sell", sym_trades["quantity"] < 0, "triangle-down", "#d62728"),
        ):
            sub = sym_trades[mask]
            if not sub.empty:
                fig.add_trace(
                    go.Scatter(
                        x=pd.to_datetime(sub["timestamp"]),
                        y=sub["fill_price"].astype(float),
                        mode="markers",
                        name=label,
                        marker=dict(symbol=marker, size=10, color=col_hex),
                    ),
                    row=1,
                    col=1,
                )

    sig_col = symbol if symbol in wide.columns else (wide.columns[0] if len(wide.columns) else None)
    if sig_col is not None:
        sig = wide[sig_col].dropna()
        fig.add_trace(
            go.Scatter(
                x=sig.index,
                y=sig.values,
                name=f"{name} ({sig_col})",
                line=dict(color=color_for(1)),
            ),
            row=2,
            col=1,
        )
    fig.update_layout(
        title=f"{symbol} — price & {name}",
        template="plotly_white",
        height=600,
        width=1000,
    )
    return fig
