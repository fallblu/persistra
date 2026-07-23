"""This module contains the provenance presentation figures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from persistra.viz._core import finish_figure, graph_objects
from persistra.viz.models import FigureConfig

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


def roots(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Render immutable run roots without exposing local filesystem paths."""
    resolved = config or replace(FigureConfig(), title="Run provenance")
    values = {"run_record_id": str(run.id), **run.provenance()}
    go = graph_objects()
    figure = go.Figure(
        go.Table(
            header={"values": ["Identity", "Value"], "align": "left"},
            cells={"values": [list(values), list(values.values())], "align": "left"},
        )
    )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.provenance.roots@1",
        sources=values,
        counts={"roots": len(values)},
        warnings=run.fidelity(),
    )
