from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pandas as pd
import pytest

from persistra.domain import QualifiedName
from persistra.errors import FigureInputError, FigureResourceLimitError
from persistra.viz import execution, performance
from persistra.viz.models import (
    FigureConfig,
    FigureLimits,
    ReductionKind,
    ThemeRef,
    VisualReductionPolicy,
)
from persistra.viz.themes import resolve_theme

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


class _StubRun:
    id = "run-stub"

    def __init__(self, returns: pd.DataFrame, fills: pd.DataFrame | None = None) -> None:
        self._returns = returns
        self._fills = pd.DataFrame() if fills is None else fills

    def returns(self, *, max_rows: int) -> pd.DataFrame:
        return self._returns.head(max_rows)

    def fills(self, *, max_rows: int) -> pd.DataFrame:
        return self._fills.head(max_rows)

    def provenance(self) -> dict[str, str]:
        return {"execution_content_id": "stub"}

    def fidelity(self) -> tuple[str, ...]:
        return ()


def _returns_frame(count: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "interval_end": pd.date_range("2026-01-01", periods=count, freq="D", tz="UTC"),
            "return_value": [0.01 * (index % 5 - 2) for index in range(count)],
            "state": ["computed" if index % 7 else "unavailable" for index in range(count)],
        }
    )


def test_return_distribution_renders_computed_returns_without_reduction() -> None:
    run = cast("RunHandle", _StubRun(_returns_frame(20)))
    figure = performance.return_distribution(run)
    metadata = figure.layout.meta
    assert metadata["figure_kind"] == "persistra.figure.performance.return_distribution@1"
    assert metadata["reduction"]["original_count"] == metadata["reduction"]["rendered_count"]
    assert metadata["counts"] == {"returns": 20}


def test_return_distribution_applies_the_declared_reduction_when_over_limit() -> None:
    run = cast("RunHandle", _StubRun(_returns_frame(60)))
    config = FigureConfig(
        reduction=VisualReductionPolicy.every_nth(2),
        limits=FigureLimits(max_points_per_trace=40),
    )
    figure = performance.return_distribution(run, config=config)
    metadata = figure.layout.meta
    assert metadata["reduction"]["policy"] == "every_nth"
    assert metadata["reduction"]["rendered_count"] <= 40


def test_fills_figure_refuses_silent_reduction_over_the_trace_limit() -> None:
    frame = pd.DataFrame({"side": ["buy"] * 6})
    run = cast("RunHandle", _StubRun(_returns_frame(1), fills=frame))
    config = FigureConfig(limits=FigureLimits(max_points_per_trace=5))
    with pytest.raises(FigureResourceLimitError):
        execution.fills(run, config=config)


def test_unknown_theme_reference_is_rejected() -> None:
    with pytest.raises(FigureInputError):
        resolve_theme(ThemeRef(QualifiedName("persistra.unknown_theme"), 1))


def test_no_reduction_policy_rejects_a_parameter() -> None:
    with pytest.raises(FigureInputError):
        VisualReductionPolicy(ReductionKind.NONE, 4)
