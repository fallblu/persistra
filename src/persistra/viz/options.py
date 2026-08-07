# pyright: reportUnknownMemberType=false
"""Matplotlib plots for observed historical option chains."""

from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

from persistra.analysis.options import greek_profile, implied_volatility_smile

if TYPE_CHECKING:
    from datetime import date

    from matplotlib.axes import Axes

    from persistra.model import OptionChain


def plot_option_chain_prices(chain: OptionChain, *, ax: Axes | None = None) -> Axes:
    """Plot observed option marks across strikes by expiration and side."""
    axes = _axes(ax)
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    for label, group in frame.groupby(["expiration", "option_type"], sort=True):
        axes.plot(group["strike"], group["mark"], marker="o", label=str(label))
    axes.set(xlabel="Strike", ylabel="Observed mark")
    axes.legend()
    return axes


def plot_option_volume_open_interest(chain: OptionChain, *, ax: Axes | None = None) -> Axes:
    """Plot observed option volume and open interest by strike."""
    axes = _axes(ax)
    frame = chain.contracts.merge(chain.observations, on=["contract_id", "provider"])
    positions = np.arange(len(frame))
    axes.bar(positions - 0.2, frame["volume"].astype(float), width=0.4, label="Volume")
    axes.bar(
        positions + 0.2,
        frame["open_interest"].astype(float),
        width=0.4,
        label="Open interest",
    )
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
    for side, group in frame.groupby("option_type", sort=True):
        axes.plot(group["strike"], group["implied_volatility"], marker="o", label=side)
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
    axes.set_xticks(np.arange(len(matrix.columns)), labels=[str(value) for value in matrix.columns])
    axes.set_yticks(
        np.arange(len(matrix.index)), labels=[str(value.date()) for value in matrix.index]
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
    for label, group in frame.groupby(["expiration", "option_type"], sort=True):
        axes.plot(group["strike"], group[greek], marker="o", label=str(label))
    axes.set(xlabel="Strike", ylabel=greek.title())
    axes.legend()
    return axes


def _axes(ax: Axes | None) -> Axes:
    return ax if ax is not None else plt.subplots()[1]
