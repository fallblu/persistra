"""This module contains the deterministic, bounded visualization configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from persistra.domain import QualifiedName
from persistra.errors import FigureInputError


@dataclass(frozen=True, slots=True)
class ThemeRef:
    """This class references one installed, immutable semantic theme."""

    name: QualifiedName = field(
        default_factory=lambda: QualifiedName("persistra.default_light")
    )
    version: int = 1

    def __post_init__(self) -> None:
        if self.version < 1:
            raise FigureInputError("theme version must be positive")


class ReductionKind(StrEnum):
    NONE = "none"
    MIN_MAX_ENVELOPE = "min_max_envelope"
    EVERY_NTH = "every_nth"


@dataclass(frozen=True, slots=True)
class VisualReductionPolicy:
    """This class represents the explicit visual-only point reduction."""

    kind: ReductionKind = ReductionKind.NONE
    parameter: int | None = None

    @classmethod
    def none(cls) -> VisualReductionPolicy:
        return cls()

    @classmethod
    def min_max_envelope(cls, buckets: int) -> VisualReductionPolicy:
        return cls(ReductionKind.MIN_MAX_ENVELOPE, buckets)

    @classmethod
    def every_nth(cls, stride: int) -> VisualReductionPolicy:
        return cls(ReductionKind.EVERY_NTH, stride)

    def __post_init__(self) -> None:
        if self.kind is ReductionKind.NONE:
            if self.parameter is not None:
                raise FigureInputError("no-reduction policy cannot have a parameter")
        elif self.parameter is None or self.parameter < 1:
            raise FigureInputError("reduction parameter must be positive")


@dataclass(frozen=True, slots=True)
class FigureLimits:
    """This class represents the unconditional materialization and emitted-figure limits."""

    max_input_rows: int = 2_000_000
    max_points_per_trace: int = 50_000
    max_traces: int = 100
    max_figure_json_bytes: int = 50_000_000

    def __post_init__(self) -> None:
        if min(
            self.max_input_rows,
            self.max_points_per_trace,
            self.max_traces,
            self.max_figure_json_bytes,
        ) < 1:
            raise FigureInputError("figure limits must be positive")


@dataclass(frozen=True, slots=True)
class FigureConfig:
    title: str = "Portfolio equity"
    width: int = 1000
    height: int = 500
    display_timezone: str = "UTC"
    locale: str = "en_US"
    theme: ThemeRef = ThemeRef()
    strict_unavailable: bool = False
    reduction: VisualReductionPolicy = VisualReductionPolicy()
    limits: FigureLimits = FigureLimits()

    def __post_init__(self) -> None:
        if not self.title or not 200 <= self.width <= 4000 or not 200 <= self.height <= 4000:
            raise FigureInputError("figure title or dimensions are invalid")
        if self.display_timezone != "UTC":
            raise FigureInputError("v3 figures support UTC display only")
        if self.locale != "en_US":
            raise FigureInputError("v3 figures support the en_US locale only")
