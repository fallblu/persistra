"""Minimal deterministic figure configuration."""

from __future__ import annotations

from dataclasses import dataclass

from persistra.errors import FigureInputError


@dataclass(frozen=True, slots=True)
class FigureConfig:
    title: str = "Portfolio equity"
    width: int = 1000
    height: int = 500
    display_timezone: str = "UTC"

    def __post_init__(self) -> None:
        if not self.title or not 200 <= self.width <= 4000 or not 200 <= self.height <= 4000:
            raise FigureInputError("figure title or dimensions are invalid")
        if self.display_timezone != "UTC":
            raise FigureInputError("phase 4 figures support UTC display only")
