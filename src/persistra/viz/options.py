# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Plotly figures for observed historical option chains."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from persistra.analysis.options import greek_profile, implied_volatility_smile
from persistra.viz._common import (
    DEFAULT_FIGURE_HEIGHT,
    figure,
    finish_figure,
    sampled_positions,
    series_style,
)

if TYPE_CHECKING:
    from datetime import date

    from persistra.model import OptionChain


def plot_option_chain_prices(chain: OptionChain) -> go.Figure:
    """Plot observed option marks across strikes by expiration and side."""
    result = figure()
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    groups = frame.groupby(["expiration", "option_type"], sort=True)
    for position, (label, group) in enumerate(groups):
        color, dash, marker = _group_style(position, len(group))
        result.add_trace(
            go.Scatter(
                x=group["strike"],
                y=group["mark"],
                mode="markers" if len(group) <= 12 else "lines+markers",
                name=_group_label(*label),
                connectgaps=False,
                line={"color": color, "dash": dash},
                marker={"color": color, "symbol": marker},
            )
        )
    return finish_figure(
        result,
        xlabel="Strike",
        ylabel="Observed mark",
        showlegend=True,
    )


def plot_option_volume_open_interest(chain: OptionChain) -> go.Figure:
    """Plot observed option volume and open interest by strike."""
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    frame = frame.sort_values(["expiration", "strike", "option_type"], kind="stable")
    positions = np.arange(len(frame))
    labels = [
        _contract_label(row["expiration"], row["strike"], row["option_type"])
        for _, row in frame.iterrows()
    ]
    result = figure()
    result.add_trace(
        go.Bar(
            x=positions,
            y=frame["volume"].to_numpy(dtype=float, na_value=np.nan),
            name="Volume",
            offsetgroup="volume",
        )
    )
    result.add_trace(
        go.Bar(
            x=positions,
            y=frame["open_interest"].to_numpy(dtype=float, na_value=np.nan),
            name="Open interest",
            offsetgroup="open-interest",
            marker={"pattern": {"shape": "/"}},
        )
    )
    ticks = sampled_positions(len(frame), maximum_ticks=6)
    result.update_xaxes(
        tickmode="array",
        tickvals=ticks,
        ticktext=[labels[position] for position in ticks],
        tickangle=-45,
    )
    result.update_layout(barmode="group")
    return finish_figure(result, xlabel="Contract", ylabel="Count", showlegend=True)


def plot_implied_volatility_smile(
    chain: OptionChain,
    *,
    expiration: date,
    option_type: str | None = None,
) -> go.Figure:
    """Plot observed implied volatility across strikes."""
    result = figure()
    frame = implied_volatility_smile(chain, expiration=expiration, option_type=option_type)
    for position, (side, group) in enumerate(frame.groupby("option_type", sort=True)):
        color, _, marker = series_style(position)
        result.add_trace(
            go.Scatter(
                x=group["strike"],
                y=group["implied_volatility"],
                mode="lines+markers",
                name=str(side).title(),
                connectgaps=False,
                line={"color": color, "dash": "dash" if position % 2 == 0 else "dot"},
                marker={"color": color, "symbol": marker},
            )
        )
    return finish_figure(
        result,
        xlabel="Strike",
        ylabel="Implied volatility",
        showlegend=True,
    )


def plot_implied_volatility_surface(chain: OptionChain) -> go.Figure:
    """Plot observed implied volatility as a three-dimensional surface."""
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    matrix = frame.pivot_table(
        index="expiration", columns="strike", values="implied_volatility", aggfunc="first"
    )
    expiration_labels = [pd.Timestamp(expiration).date().isoformat() for expiration in matrix.index]
    result = go.Figure(
        data=[
            go.Surface(
                x=np.asarray(matrix.columns, dtype=float),
                y=np.arange(len(matrix.index)),
                z=matrix.to_numpy(dtype=float),
                colorbar={"title": {"text": "Implied volatility"}},
                connectgaps=False,
                hovertemplate=(
                    "Strike %{x}<br>Expiration %{customdata}<br>"
                    "Implied volatility %{z}<extra></extra>"
                ),
                customdata=np.broadcast_to(np.asarray(expiration_labels)[:, None], matrix.shape),
            )
        ]
    )
    expiration_ticks = sampled_positions(len(matrix.index))
    expiration_extent = max(len(matrix.index) - 1, 0)
    expiration_padding = max(0.5, expiration_extent * 0.2)
    result.update_layout(
        template="plotly_white",
        height=DEFAULT_FIGURE_HEIGHT,
        scene={
            "xaxis": {"title": {"text": "Strike"}},
            "yaxis": {
                "title": {"text": "Expiration"},
                "tickmode": "array",
                "tickvals": expiration_ticks,
                "ticktext": [expiration_labels[position] for position in expiration_ticks],
                "tickangle": 0,
                "range": [-expiration_padding, expiration_extent + expiration_padding],
            },
            "zaxis": {"title": {"text": "Implied volatility"}},
        },
        margin={"l": 30, "r": 30, "t": 40, "b": 110},
        showlegend=False,
    )
    return result


def plot_greek_profile(
    chain: OptionChain,
    greek: str,
    *,
    expiration: date | None = None,
    option_type: str | None = None,
) -> go.Figure:
    """Plot one provider-supplied Greek across observed strikes."""
    result = figure()
    frame = greek_profile(chain, greek, expiration=expiration, option_type=option_type)
    groups = frame.groupby(["expiration", "option_type"], sort=True)
    for position, (label, group) in enumerate(groups):
        color, dash, marker = _group_style(position, len(group))
        result.add_trace(
            go.Scatter(
                x=group["strike"],
                y=group[greek],
                mode="markers" if len(group) <= 12 else "lines+markers",
                name=_group_label(*label),
                connectgaps=False,
                line={"color": color, "dash": dash},
                marker={"color": color, "symbol": marker},
            )
        )
    return finish_figure(result, xlabel="Strike", ylabel=greek.title(), showlegend=True)


def _group_label(expiration: Any, option_type: Any) -> str:
    return f"{pd.Timestamp(expiration).date().isoformat()} {str(option_type).title()}"


def _contract_label(expiration: Any, strike: Any, option_type: Any) -> str:
    side = str(option_type).upper()[0]
    return f"{pd.Timestamp(expiration).date().isoformat()}<br>{_format_strike(strike)} {side}"


def _format_strike(value: Any) -> str:
    return f"{float(value):g}"


def _group_style(position: int, observations: int) -> tuple[str, str, str]:
    color, dash, marker = series_style(position)
    if observations <= 12:
        return color, "solid", marker
    return color, "dash" if position % 2 == 0 else dash, marker
