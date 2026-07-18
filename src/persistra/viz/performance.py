"""Pure Plotly performance and risk figures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra.viz._core import finish_figure, graph_objects, reduce_xy
from persistra.viz.models import FigureConfig
from persistra.viz.themes import resolve_theme

if TYPE_CHECKING:
    from persistra.analysis.services import MetricsHandle
    from persistra.results.services import RunHandle


def equity(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot exact NAV samples without recomputing financial values."""
    resolved = config or FigureConfig()
    frame = run.equity(max_rows=resolved.limits.max_input_rows)
    x, y, reduction = reduce_xy(
        frame["valued_at"].tolist(),
        [_number(value) for value in frame["nav_usd"]],
        resolved,
    )
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure()
    figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            name="NAV",
            line={"color": theme.neutral, "width": 2},
            hovertemplate="%{x|%Y-%m-%d %H:%M:%S UTC}<br>NAV $%{y:,.2f}<extra></extra>",
        )
    )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.performance.equity@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"equity": len(frame)},
        reduction=reduction,
        warnings=run.fidelity(),
        xaxis_title="Valuation instant (UTC)",
        yaxis_title="NAV (USD)",
    )


def returns(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot the exact normalized interval returns emitted by the run."""
    resolved = config or replace(FigureConfig(), title="Interval returns")
    frame = run.returns(max_rows=resolved.limits.max_input_rows)
    values = [
        _number(value) if state == "computed" else None
        for value, state in zip(frame["return_value"], frame["state"], strict=True)
    ]
    x, y, reduction = reduce_xy(frame["interval_end"].tolist(), values, resolved)
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    colors = [
        theme.positive if value is not None and value >= 0 else theme.negative
        for value in y
    ]
    figure = go.Figure()
    figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
        go.Bar(
            x=x,
            y=y,
            name="Return",
            marker={"color": colors, "line": {"width": 0}},
            hovertemplate="%{x|%Y-%m-%d %H:%M:%S UTC}<br>Return %{y:.4%}<extra></extra>",
        )
    )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.performance.returns@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"returns": len(frame)},
        reduction=reduction,
        warnings=run.fidelity(),
        xaxis_title="Interval end (UTC)",
        yaxis_title="Return",
    )


def return_distribution(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot a distribution of exact run-return values."""
    resolved = config or replace(FigureConfig(), title="Return distribution")
    frame = run.returns(max_rows=resolved.limits.max_input_rows)
    values = [
        _number(value)
        for value, state in zip(frame["return_value"], frame["state"], strict=True)
        if state == "computed" and pd.notna(value)
    ]
    if len(values) > resolved.limits.max_points_per_trace:
        _, reduced, reduction = reduce_xy(list(range(len(values))), values, resolved)
        values = [value for value in reduced if value is not None]
    else:
        reduction = {
            "policy": resolved.reduction.kind.value,
            "parameter": resolved.reduction.parameter,
            "original_count": len(values),
            "rendered_count": len(values),
            "warning": None,
        }
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure(
        go.Histogram(
            x=values,
            name="Return observations",
            marker={"color": theme.neutral},
            hovertemplate="Return %{x:.4%}<br>Count %{y}<extra></extra>",
        )
    )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.performance.return_distribution@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"returns": len(frame)},
        reduction=reduction,
        warnings=run.fidelity(),
        xaxis_title="Return",
        yaxis_title="Observations",
    )


def metric_summary(
    metrics: MetricsHandle, *, config: FigureConfig | None = None
) -> Any:
    """Render structured metric states as an accessible Plotly table."""
    resolved = config or replace(FigureConfig(), title="Performance and risk metrics")
    rows = metrics.results()
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure(
        go.Table(
            header={
                "values": ["Metric", "State", "Value", "Unit", "Reason"],
                "fill_color": theme.surface,
                "font": {"color": theme.text},
                "align": "left",
            },
            cells={
                "values": [
                    [item.metric_name for item in rows],
                    [item.state.value for item in rows],
                    [
                        "Unavailable" if item.estimate is None else f"{item.estimate:.6f}"
                        for item in rows
                    ],
                    [item.unit for item in rows],
                    [item.reason_code or "" for item in rows],
                ],
                "align": "left",
            },
        )
    )
    reference = metrics.reference
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.performance.metric_summary@1",
        sources={
            "analysis_artifact_id": str(reference.analysis_artifact_id),
            "analysis_output_content_id": str(reference.output_content_id),
        },
        counts={"metrics": len(rows)},
        warnings=tuple(item.reason_code or "" for item in rows if item.reason_code),
    )


def _number(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)
