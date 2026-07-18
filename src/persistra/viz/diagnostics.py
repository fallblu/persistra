"""Structured fidelity and diagnostic figures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from persistra.viz._core import finish_figure, graph_objects
from persistra.viz.models import FigureConfig
from persistra.viz.themes import resolve_theme

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


def fidelity(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Render fidelity findings as a visible, machine-readable table."""
    resolved = config or replace(FigureConfig(), title="Fidelity findings")
    findings = run.fidelity()
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure(
        go.Table(
            header={
                "values": ["Severity", "Finding"],
                "fill_color": theme.surface,
                "align": "left",
            },
            cells={
                "values": [
                    ["warning"] * len(findings),
                    list(findings),
                ],
                "align": "left",
            },
        )
    )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.diagnostics.fidelity@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"findings": len(findings)},
        warnings=findings,
    )
