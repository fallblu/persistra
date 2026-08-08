# pyright: reportUnknownMemberType=false
"""Matplotlib plots for observed historical option chains."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from persistra.analysis.options import greek_profile, implied_volatility_smile
from persistra.viz._common import line_style, sampled_positions

if TYPE_CHECKING:
    from datetime import date

    from matplotlib.axes import Axes

    from persistra.model import OptionChain


def plot_option_chain_prices(chain: OptionChain, *, ax: Axes | None = None) -> Axes:
    """Plot observed option marks across strikes by expiration and side."""
    axes = _axes(ax)
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    groups = frame.groupby(["expiration", "option_type"], sort=True)
    for position, (label, group) in enumerate(groups):
        style, marker = _group_style(position, len(group))
        axes.plot(
            group["strike"],
            group["mark"],
            marker=marker,
            linestyle=style,
            label=_group_label(*label),
        )
    axes.set(xlabel="Strike", ylabel="Observed mark")
    _group_legend(axes, groups.ngroups)
    return axes


def plot_option_volume_open_interest(chain: OptionChain, *, ax: Axes | None = None) -> Axes:
    """Plot observed option volume and open interest by strike."""
    axes = _axes(ax)
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    frame = frame.sort_values(["expiration", "strike", "option_type"], kind="stable")
    positions = np.arange(len(frame))
    axes.bar(positions - 0.2, frame["volume"].astype(float), width=0.4, label="Volume")
    axes.bar(
        positions + 0.2,
        frame["open_interest"].astype(float),
        width=0.4,
        label="Open interest",
    )
    ticks = sampled_positions(len(frame), maximum_ticks=6)
    labels = [
        _contract_label(
            frame.iloc[position]["expiration"],
            frame.iloc[position]["strike"],
            frame.iloc[position]["option_type"],
        )
        for position in ticks
    ]
    axes.set_xticks(ticks, labels=labels, rotation=45, ha="right")
    axes.set(xlabel="Contract", ylabel="Count")
    axes.legend()
    return axes


def plot_implied_volatility_smile(
    chain: OptionChain,
    *,
    expiration: date,
    option_type: str | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot observed implied volatility across strikes."""
    axes = _axes(ax)
    frame = implied_volatility_smile(chain, expiration=expiration, option_type=option_type)
    for position, (side, group) in enumerate(frame.groupby("option_type", sort=True)):
        _, marker = line_style(position)
        axes.plot(
            group["strike"],
            group["implied_volatility"],
            marker=marker,
            linestyle="--" if position % 2 == 0 else ":",
            label=str(side).title(),
        )
    axes.set(xlabel="Strike", ylabel="Implied volatility")
    axes.legend()
    return axes


def plot_implied_volatility_surface(chain: OptionChain, *, ax: Axes | None = None) -> Axes:
    """Plot observed implied volatility as a noninterpolated heatmap."""
    axes = _axes(ax)
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    matrix = frame.pivot_table(
        index="expiration", columns="strike", values="implied_volatility", aggfunc="first"
    )
    masked = np.ma.masked_invalid(matrix.to_numpy(dtype=float))
    image = axes.imshow(masked, aspect="auto", interpolation="none", origin="lower")
    strike_ticks = sampled_positions(len(matrix.columns))
    expiration_ticks = sampled_positions(len(matrix.index))
    axes.set_xticks(
        strike_ticks,
        labels=[_format_strike(matrix.columns[position]) for position in strike_ticks],
        rotation=45,
        ha="right",
    )
    axes.set_yticks(
        expiration_ticks,
        labels=[
            pd.Timestamp(matrix.index[position]).date().isoformat()
            for position in expiration_ticks
        ],
    )
    axes.set(xlabel="Strike", ylabel="Expiration")
    axes.figure.colorbar(image, ax=axes, label="Implied volatility")
    return axes


def plot_greek_profile(
    chain: OptionChain,
    greek: str,
    *,
    expiration: date | None = None,
    option_type: str | None = None,
    ax: Axes | None = None,
) -> Axes:
    """Plot one provider-supplied Greek across observed strikes."""
    axes = _axes(ax)
    frame = greek_profile(chain, greek, expiration=expiration, option_type=option_type)
    groups = frame.groupby(["expiration", "option_type"], sort=True)
    for position, (label, group) in enumerate(groups):
        style, marker = _group_style(position, len(group))
        axes.plot(
            group["strike"],
            group[greek],
            marker=marker,
            linestyle=style,
            label=_group_label(*label),
        )
    axes.set(xlabel="Strike", ylabel=greek.title())
    _group_legend(axes, groups.ngroups)
    return axes


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]


def _group_label(expiration: Any, option_type: Any) -> str:
    return f"{pd.Timestamp(expiration).date().isoformat()} {str(option_type).title()}"


def _contract_label(expiration: Any, strike: Any, option_type: Any) -> str:
    side = str(option_type).upper()[0]
    return f"{pd.Timestamp(expiration).date().isoformat()}\n{_format_strike(strike)} {side}"


def _format_strike(value: Any) -> str:
    return f"{float(value):g}"


def _group_style(position: int, observations: int) -> tuple[object, str]:
    style, marker = line_style(position)
    if observations <= 12:
        return "none", marker
    return ((0, (4, 2)) if position % 2 == 0 else style), marker


def _group_legend(axes: Axes, groups: int) -> None:
    axes.legend(ncols=2 if groups > 3 else 1, fontsize="small")
