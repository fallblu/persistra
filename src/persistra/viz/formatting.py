from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import plotly.graph_objects as go

METRIC_ROWS: list[tuple[str, str, str]] = [
    ("ann_return", "Annualized return", "{:.2%}"),
    ("ann_vol", "Annualized volatility", "{:.2%}"),
    ("sharpe", "Sharpe ratio", "{:.2f}"),
    ("sortino", "Sortino ratio", "{:.2f}"),
    ("calmar", "Calmar ratio", "{:.2f}"),
    ("max_drawdown", "Max drawdown", "{:.2%}"),
    ("hit_rate", "Hit rate", "{:.2%}"),
    ("var_95", "VaR (95%)", "{:.2%}"),
    ("cvar_95", "CVaR (95%)", "{:.2%}"),
    ("information_ratio", "Information ratio", "{:.2f}"),
]


def fig_to_html(fig: go.Figure) -> str:
    """Serialize a plotly Figure to an HTML div (no plotly.js script tag)."""
    import plotly.io as pio

    return pio.to_html(fig, full_html=False, include_plotlyjs=False)  # type: ignore[arg-type]


def format_metric(value: float, fmt: str) -> str:
    """Format a metric value; returns '—' for NaN."""
    if value != value:
        return "—"
    return fmt.format(value)


__all__ = ["METRIC_ROWS", "fig_to_html", "format_metric"]
