"""Pure Plotly portfolio figures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra.viz._core import finish_figure, graph_objects, reduce_xy
from persistra.viz.models import FigureConfig
from persistra.viz.themes import resolve_theme

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


def exposure(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot exact gross and net exposure samples."""
    resolved = config or replace(FigureConfig(), title="Portfolio exposure")
    frame = run.equity(max_rows=resolved.limits.max_input_rows)
    x = frame["valued_at"].tolist()
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure()
    evidence: dict[str, Any] | None = None
    for name, column, color, dash in (
        ("Gross exposure", "gross_exposure_usd", theme.negative, "solid"),
        ("Net exposure", "net_exposure_usd", theme.neutral, "dash"),
    ):
        reduced_x, values, current = reduce_xy(
            x, [_number(value) for value in frame[column]], resolved
        )
        evidence = current
        figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=reduced_x,
                y=values,
                mode="lines",
                name=name,
                line={"color": color, "dash": dash},
                hovertemplate=f"%{{x|%Y-%m-%d %H:%M:%S UTC}}<br>{name} $%{{y:,.2f}}<extra></extra>",
            )
        )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.portfolio.exposure@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"equity": len(frame)},
        reduction=evidence,
        warnings=run.fidelity(),
        xaxis_title="Valuation instant (UTC)",
        yaxis_title="Exposure (USD)",
    )


def positions(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot exact marked position values in canonical instrument order."""
    resolved = config or replace(FigureConfig(), title="Marked positions")
    frame = run.positions(max_rows=resolved.limits.max_input_rows)
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure()
    evidence: dict[str, Any] | None = None
    instruments = sorted(str(value) for value in frame["instrument_id"].unique())
    for ordinal, instrument in enumerate(instruments):
        subset = frame[frame["instrument_id"].astype(str) == instrument]
        x, y, current = reduce_xy(
            subset["valued_at"].tolist(),
            [_number(value) for value in subset["market_value_usd"]],
            resolved,
        )
        evidence = current
        figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=instrument,
                line={
                    "color": theme.categorical[ordinal % len(theme.categorical)],
                    "dash": "solid" if ordinal % 2 == 0 else "dash",
                },
                hovertemplate="%{x|%Y-%m-%d %H:%M:%S UTC}<br>%{y:$,.2f}<extra></extra>",
            )
        )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.portfolio.positions@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"positions": len(frame), "instruments": len(instruments)},
        reduction=evidence,
        warnings=run.fidelity(),
        xaxis_title="Valuation instant (UTC)",
        yaxis_title="Market value (USD)",
    )


def target_shortfall(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Compare exact target, filled, and shortfall quantities."""
    resolved = config or replace(FigureConfig(), title="Target-to-fill shortfall")
    frame = run.targets(max_rows=resolved.limits.max_input_rows)
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    figure = go.Figure()
    for name, column, color, pattern in (
        ("Target", "target_quantity", theme.neutral, ""),
        ("Filled", "filled_quantity", theme.positive, "/"),
        ("Shortfall", "shortfall_quantity", theme.warning, "x"),
    ):
        figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Bar(
                x=[str(value) for value in frame["instrument_id"]],
                y=[_number(value) for value in frame[column]],
                name=name,
                marker={"color": color, "pattern": {"shape": pattern}},
            )
        )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.portfolio.target_shortfall@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"targets": len(frame)},
        warnings=run.fidelity(),
        xaxis_title="Instrument",
        yaxis_title="Quantity",
    )


def _number(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)
