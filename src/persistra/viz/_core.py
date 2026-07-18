"""Shared deterministic Plotly construction helpers."""

from __future__ import annotations

import json
import math
from typing import Any, Protocol

from persistra.errors import (
    FigureInputError,
    FigureResourceLimitError,
)
from persistra.viz.models import FigureConfig, ReductionKind
from persistra.viz.themes import resolve_theme


class FigureLike(Protocol):
    data: Any

    def update_layout(self, *args: Any, **kwargs: Any) -> Any: ...

    def add_annotation(self, *args: Any, **kwargs: Any) -> Any: ...

    def to_json(self, *args: Any, **kwargs: Any) -> str: ...


def graph_objects() -> Any:
    import plotly.graph_objects as go  # pyright: ignore[reportMissingTypeStubs]

    return go


def reduce_xy(
    x: list[Any],
    y: list[float | None],
    config: FigureConfig,
) -> tuple[list[Any], list[float | None], dict[str, Any]]:
    """Apply the named deterministic visual-only reduction."""
    if len(x) != len(y):
        raise FigureInputError("figure x and y lengths differ")
    original = len(x)
    if original > config.limits.max_input_rows:
        raise FigureResourceLimitError("figure input rows exceed max_input_rows")
    policy = config.reduction
    if original <= config.limits.max_points_per_trace:
        indices = list(range(original))
    elif policy.kind is ReductionKind.NONE:
        raise FigureResourceLimitError(
            "figure points exceed max_points_per_trace; choose an explicit reduction"
        )
    elif policy.kind is ReductionKind.EVERY_NTH:
        assert policy.parameter is not None
        indices = list(range(0, original, policy.parameter))
        if original and original - 1 not in indices:
            indices.append(original - 1)
    else:
        assert policy.parameter is not None
        indices = _envelope_indices(y, policy.parameter)
    if len(indices) > config.limits.max_points_per_trace:
        raise FigureResourceLimitError("reduced points still exceed max_points_per_trace")
    evidence = {
        "policy": policy.kind.value,
        "parameter": policy.parameter,
        "original_count": original,
        "rendered_count": len(indices),
        "warning": (
            None
            if len(indices) == original
            else "Visual reduction applied; financial values were not recomputed."
        ),
    }
    return [x[index] for index in indices], [y[index] for index in indices], evidence


def _envelope_indices(values: list[float | None], buckets: int) -> list[int]:
    count = len(values)
    if not count:
        return []
    resolved_buckets = min(buckets, count)
    selected: set[int] = set()
    for bucket in range(resolved_buckets):
        start = math.floor(bucket * count / resolved_buckets)
        stop = math.floor((bucket + 1) * count / resolved_buckets)
        members = list(range(start, stop))
        selected.add(members[0])
        selected.add(members[-1])
        eligible = [index for index in members if values[index] is not None]
        if eligible:
            selected.add(min(eligible, key=lambda index: (values[index], index)))
            selected.add(max(eligible, key=lambda index: (values[index], -index)))
    return sorted(selected)


def finish_figure(
    figure: FigureLike,
    *,
    config: FigureConfig,
    kind: str,
    sources: dict[str, str],
    counts: dict[str, int],
    reduction: dict[str, Any] | None = None,
    warnings: tuple[str, ...] = (),
    xaxis_title: str | None = None,
    yaxis_title: str | None = None,
) -> FigureLike:
    theme = resolve_theme(config.theme)
    visible_warnings = tuple(item for item in warnings if item)
    if reduction is not None and reduction["warning"] is not None:
        visible_warnings += (str(reduction["warning"]),)
    metadata = {
        "figure_kind": kind,
        **sources,
        "counts": counts,
        "warnings": visible_warnings,
        "reduction": reduction,
        "display_timezone": config.display_timezone,
        "locale": config.locale,
        "theme": f"{config.theme.name}@{config.theme.version}",
    }
    figure.update_layout(
        title=config.title,
        width=config.width,
        height=config.height,
        template="plotly_white",
        paper_bgcolor=theme.background,
        plot_bgcolor=theme.surface,
        font={"color": theme.text},
        xaxis={"title": xaxis_title, "gridcolor": theme.grid},
        yaxis={"title": yaxis_title, "gridcolor": theme.grid},
        showlegend=True,
        uirevision=None,
        transition={"duration": 0},
        meta=metadata,
    )
    if not any(counts.values()):
        figure.add_annotation(
            text="No applicable observations",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
        )
    elif visible_warnings:
        figure.add_annotation(
            text="<br>".join(visible_warnings),
            x=0,
            y=1.12,
            xref="paper",
            yref="paper",
            xanchor="left",
            showarrow=False,
            font={"color": theme.warning},
        )
    emitted = len(figure.to_json().encode("utf-8"))
    if emitted > config.limits.max_figure_json_bytes:
        raise FigureResourceLimitError("figure JSON exceeds max_figure_json_bytes")
    if len(getattr(figure, "data", ())) > config.limits.max_traces:
        raise FigureResourceLimitError("figure traces exceed max_traces")
    json.dumps(metadata, sort_keys=True)
    return figure
