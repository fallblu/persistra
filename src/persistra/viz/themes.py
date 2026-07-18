"""Installed accessible semantic Plotly themes."""

from __future__ import annotations

from dataclasses import dataclass

from persistra.domain import QualifiedName
from persistra.errors import FigureInputError
from persistra.viz.models import ThemeRef


@dataclass(frozen=True, slots=True)
class Theme:
    reference: ThemeRef
    background: str
    surface: str
    text: str
    muted: str
    grid: str
    positive: str
    negative: str
    neutral: str
    warning: str
    categorical: tuple[str, ...]


DEFAULT_LIGHT = Theme(
    ThemeRef(),
    "#ffffff",
    "#f8fafc",
    "#172033",
    "#475569",
    "#cbd5e1",
    "#047857",
    "#b91c1c",
    "#2563eb",
    "#92400e",
    ("#2563eb", "#b91c1c", "#047857", "#7c3aed", "#b45309", "#0e7490"),
)
DEFAULT_DARK = Theme(
    ThemeRef(name=QualifiedName("persistra.default_dark")),
    "#111827",
    "#1f2937",
    "#f8fafc",
    "#cbd5e1",
    "#475569",
    "#34d399",
    "#f87171",
    "#60a5fa",
    "#fbbf24",
    ("#60a5fa", "#f87171", "#34d399", "#c4b5fd", "#fbbf24", "#22d3ee"),
)

_THEMES = {
    (str(DEFAULT_LIGHT.reference.name), DEFAULT_LIGHT.reference.version): DEFAULT_LIGHT,
    (str(DEFAULT_DARK.reference.name), DEFAULT_DARK.reference.version): DEFAULT_DARK,
}


def resolve_theme(reference: ThemeRef) -> Theme:
    """Resolve an installed theme without accepting executable callbacks."""
    try:
        return _THEMES[(str(reference.name), reference.version)]
    except KeyError as error:
        raise FigureInputError(f"unknown theme: {reference.name}@{reference.version}") from error
