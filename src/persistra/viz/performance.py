"""Pure Plotly performance figures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from persistra.errors import VisualizationExtraRequiredError
from persistra.viz.models import FigureConfig

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


def equity(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Return a deterministic equity figure without filesystem or browser side effects."""
    try:
        import plotly.graph_objects as go  # pyright: ignore[reportMissingTypeStubs]
    except ImportError as error:  # pragma: no cover - exercised in isolated install checks
        raise VisualizationExtraRequiredError(
            "equity figures require `pip install persistra[viz]`"
        ) from error
    resolved = config or FigureConfig()
    frame = run.equity()
    figure = go.Figure()
    figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
        go.Scatter(
            x=frame["valued_at"].tolist(),
            y=[float(value) for value in frame["nav_usd"]],
            mode="lines",
            name="NAV",
            line={"color": "#2563eb", "width": 2},
            hovertemplate="%{x|%Y-%m-%d %H:%M:%S UTC}<br>NAV $%{y:,.2f}<extra></extra>",
        )
    )
    figure.update_layout(  # pyright: ignore[reportUnknownMemberType]
        title=resolved.title,
        width=resolved.width,
        height=resolved.height,
        template="plotly_white",
        showlegend=True,
        xaxis_title="Valuation instant (UTC)",
        yaxis_title="NAV (USD)",
        uirevision=None,
        meta={
            "figure_kind": "persistra.figure.performance.equity@1",
            "run_record_id": str(run.id),
            **run.provenance(),
            "point_count": len(frame),
            "display_timezone": resolved.display_timezone,
        },
    )
    return figure
