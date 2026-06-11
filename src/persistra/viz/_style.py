from __future__ import annotations

import plotly.graph_objects as go

# Matches the palette already used ad-hoc in viz/plots.py.
COLORWAY: tuple[str, ...] = (
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
)


def color_for(i: int) -> str:
    """Return the palette color for series index ``i`` (cycles)."""
    return COLORWAY[i % len(COLORWAY)]


def styled_figure(
    *,
    title: str = "",
    xaxis_title: str = "",
    yaxis_title: str = "",
) -> go.Figure:
    """A blank Figure with the shared persistra layout applied."""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        xaxis_title=xaxis_title,
        yaxis_title=yaxis_title,
        colorway=list(COLORWAY),
        template="plotly_white",
        height=750,
        width=1000,
    )
    return fig
