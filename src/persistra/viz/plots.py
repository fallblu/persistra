from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd
import plotly.graph_objects as go

from persistra.metrics.realized import realized_pnl
from persistra.viz._style import styled_figure

if TYPE_CHECKING:
    from persistra.core.result import Result


def _returns_from_equity(equity: pd.Series) -> pd.Series:
    return equity.astype(float).pct_change().dropna()


def equity_curve_plot(result: Result, benchmark: pd.Series | None = None) -> go.Figure:
    """Plot portfolio equity over time, with an optional benchmark overlay.

    Args:
        result: A completed backtest ``Result`` carrying the equity series.
        benchmark: Optional price series for a benchmark asset.  When provided
            it is rescaled to start at the same value as the portfolio equity
            and plotted as a dashed grey line.

    Returns:
        A Plotly figure of cumulative equity against the trading calendar.
    """
    equity = result.equity_curve["equity"].astype(float)
    fig = styled_figure(
        title="Equity curve",
        xaxis_title="Date",
        yaxis_title="Equity",
    )
    fig.add_trace(
        go.Scatter(x=equity.index, y=equity.values, name="Equity", line=dict(color="#1f77b4"))
    )
    if benchmark is not None:
        b = benchmark.astype(float).dropna()
        if not b.empty:
            scaled = b / float(b.iloc[0]) * float(equity.iloc[0])
            fig.add_trace(
                go.Scatter(
                    x=scaled.index,
                    y=scaled.values,
                    name="Benchmark",
                    line=dict(color="#7f7f7f", dash="dash"),
                )
            )
    return fig


def drawdown_plot(result: Result) -> go.Figure:
    """Plot portfolio drawdown (underwater equity) over time.

    Drawdown at each point is computed as the percentage decline from the
    running peak equity up to that date.  The area is filled in red.

    Args:
        result: A completed backtest ``Result`` carrying the equity series.

    Returns:
        A Plotly figure showing the underwater equity curve with a filled
        red area between zero and the current drawdown percentage.
    """
    equity = result.equity_curve["equity"].astype(float)
    drawdown = equity / equity.cummax() - 1.0
    fig = styled_figure(
        title="Underwater plot",
        xaxis_title="Date",
        yaxis_title="Drawdown",
    )
    fig.add_trace(
        go.Scatter(
            x=drawdown.index,
            y=drawdown.values,
            fill="tozeroy",
            name="Drawdown",
            line=dict(color="#d62728"),
            fillcolor="rgba(214,39,40,0.4)",
        )
    )
    fig.update_layout(yaxis_tickformat=".0%")
    return fig


def returns_heatmap(result: Result) -> go.Figure:
    """Plot a year-by-month heatmap of monthly returns.

    Daily returns are compounded within each calendar month.  The resulting
    matrix is displayed as a red-yellow-green heatmap centred on zero, so
    profitable months appear green and losing months appear red.  If the
    equity series is empty the figure is returned with no traces.

    Args:
        result: A completed backtest ``Result`` carrying the equity series.

    Returns:
        A Plotly heatmap figure with years on the y-axis and calendar months
        on the x-axis.
    """
    daily = _returns_from_equity(result.equity_curve["equity"])
    if daily.empty:
        return styled_figure(title="Monthly returns")
    fig = styled_figure(
        title="Monthly returns",
        xaxis_title="Month",
        yaxis_title="Year",
    )
    monthly = (1.0 + daily).resample("ME").prod() - 1.0
    idx = pd.DatetimeIndex(monthly.index)
    matrix = monthly.groupby([idx.year, idx.month]).sum().unstack(level=1)
    month_labels = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    x_labels = [month_labels[int(m) - 1] for m in matrix.columns]
    y_labels = [str(y) for y in matrix.index]
    fig.add_trace(
        go.Heatmap(
            z=matrix.to_numpy(),
            x=x_labels,
            y=y_labels,
            colorscale="RdYlGn",
            zmid=0.0,
            colorbar=dict(tickformat=".0%"),
        )
    )
    return fig


def trade_pnl_histogram(result: Result) -> go.Figure:
    """Plot a histogram of per-trade realised P&L.

    Realised P&L is computed with :func:`persistra.metrics.realized.realized_pnl`.
    A vertical line is drawn at zero to separate winning from losing trades.
    If there are no closed trades the figure is returned with no histogram
    bars.

    Args:
        result: A completed backtest ``Result`` from which trade records are
            extracted.

    Returns:
        A Plotly figure with a 100-bin histogram of realised P&L values.
    """
    pnl = realized_pnl(result)
    fig = styled_figure(
        title="Trade P&L distribution",
        xaxis_title="Realized P&L",
        yaxis_title="Count",
    )
    if not pnl.empty:
        fig.add_trace(go.Histogram(x=pnl.values, nbinsx=100, name="P&L", marker_color="#1f77b4"))
    fig.add_vline(x=0, line_width=1, line_color="black", opacity=0.5)
    return fig


def exposure_plot(result: Result) -> go.Figure:
    """Plot gross and net market exposure over time.

    Both series are read directly from the ``equity_curve`` DataFrame columns
    ``"gross_exposure"`` and ``"net_exposure"``.  A horizontal zero-line is
    added as a reference.

    Args:
        result: A completed backtest ``Result`` whose equity curve contains
            ``gross_exposure`` and ``net_exposure`` columns.

    Returns:
        A Plotly figure with two line traces (gross in green, net in purple)
        showing exposure against the trading calendar.
    """
    df = result.equity_curve
    gross = df["gross_exposure"].astype(float)
    net = df["net_exposure"].astype(float)
    fig = styled_figure(
        title="Exposure",
        xaxis_title="Date",
        yaxis_title="Exposure",
    )
    fig.add_trace(
        go.Scatter(x=gross.index, y=gross.values, name="Gross", line=dict(color="#2ca02c"))
    )
    fig.add_trace(go.Scatter(x=net.index, y=net.values, name="Net", line=dict(color="#9467bd")))
    fig.add_hline(y=0, line_width=1, line_color="black", opacity=0.5)
    return fig
