"""Pure Plotly attribution figures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra.viz._core import finish_figure, graph_objects
from persistra.viz.models import FigureConfig
from persistra.viz.themes import resolve_theme

if TYPE_CHECKING:
    from persistra.analysis.advanced_services import TabularAnalysisHandle


def contributions(
    analysis: TabularAnalysisHandle, *, config: FigureConfig | None = None
) -> Any:
    """Plot exact reconciled attribution rows from an immutable analysis."""
    resolved = config or replace(FigureConfig(), title="Attribution contributions")
    frame = analysis.results(max_rows=resolved.limits.max_input_rows)
    frame = frame[frame["category"] == "attribution"]
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    values = [
        None if pd.isna(value) else float(value) for value in frame["estimate"]
    ]
    figure = go.Figure(
        go.Bar(
            x=[str(value) for value in frame["name"]],
            y=values,
            marker={
                "color": [
                    theme.positive
                    if value is not None and value >= 0
                    else theme.negative
                    for value in values
                ],
                "pattern": {"shape": ["" if value is not None else "x" for value in values]},
            },
            name="Contribution",
        )
    )
    reference = analysis.reference
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.attribution.contributions@1",
        sources={
            "analysis_artifact_id": str(reference.analysis_artifact_id),
            "analysis_output_content_id": str(reference.output_content_id),
        },
        counts={"contributions": len(frame)},
        warnings=tuple(
            str(value)
            for value in frame["reason_code"]
            if pd.notna(value) and str(value)
        ),
        xaxis_title="Component",
        yaxis_title="Contribution (USD)",
    )
