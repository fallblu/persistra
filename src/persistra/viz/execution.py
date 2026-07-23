"""This module contains the pure Plotly execution and cost figures."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

import pandas as pd

from persistra.viz._core import finish_figure, graph_objects
from persistra.viz.models import FigureConfig
from persistra.viz.themes import resolve_theme

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


def fills(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot exact synthetic/event fill observations."""
    resolved = config or replace(FigureConfig(), title="Fills")
    frame = run.fills(max_rows=resolved.limits.max_input_rows)
    if len(frame) > resolved.limits.max_points_per_trace:
        from persistra.errors import FigureResourceLimitError

        raise FigureResourceLimitError(
            "fill events cannot be silently reduced; increase the explicit figure limit"
        )
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    sides = [str(value) for value in frame["side"]]
    figure = go.Figure(
        go.Scatter(
            x=frame["execution_at"].tolist(),
            y=[_number(value) for value in frame["fill_price_usd"]],
            mode="markers",
            name="Fills",
            marker={
                "color": [
                    theme.positive if side == "buy" else theme.negative for side in sides
                ],
                "symbol": ["triangle-up" if side == "buy" else "triangle-down" for side in sides],
                "size": 9,
            },
            customdata=[
                [str(instrument), side, str(quantity)]
                for instrument, side, quantity in zip(
                    frame["instrument_id"], frame["side"], frame["quantity"], strict=True
                )
            ],
            hovertemplate=(
                "%{x|%Y-%m-%d %H:%M:%S UTC}<br>Price $%{y:,.4f}"
                "<br>Instrument %{customdata[0]}<br>Side %{customdata[1]}"
                "<br>Quantity %{customdata[2]}<extra></extra>"
            ),
        )
    )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.execution.fills@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"fills": len(frame)},
        warnings=run.fidelity(),
        xaxis_title="Execution instant (UTC)",
        yaxis_title="Fill price (USD)",
    )


def costs(run: RunHandle, *, config: FigureConfig | None = None) -> Any:
    """Plot exact cost-component rows, retaining evidence state."""
    resolved = config or replace(FigureConfig(), title="Execution costs")
    frame = run.costs(max_rows=resolved.limits.max_input_rows)
    go = graph_objects()
    theme = resolve_theme(resolved.theme)
    states = sorted(str(value) for value in frame["state"].unique())
    figure = go.Figure()
    for ordinal, state in enumerate(states):
        subset = frame[frame["state"].astype(str) == state]
        figure.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Bar(
                x=[str(value) for value in subset["component_kind"]],
                y=[_number(value) for value in subset["amount_usd"]],
                name=state,
                marker={
                    "color": theme.categorical[ordinal % len(theme.categorical)],
                    "pattern": {"shape": "" if state == "observed" else "/"},
                },
                hovertemplate="%{x}<br>Cost $%{y:,.4f}<extra></extra>",
            )
        )
    return finish_figure(
        figure,
        config=resolved,
        kind="persistra.figure.execution.costs@1",
        sources={"run_record_id": str(run.id), **run.provenance()},
        counts={"cost_components": len(frame)},
        warnings=run.fidelity(),
        xaxis_title="Cost component",
        yaxis_title="Amount (USD)",
    )


def _number(value: Any) -> float | None:
    return None if pd.isna(value) else float(value)
