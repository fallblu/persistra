"""Tests for built-in Monte Carlo path metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
import pytest

from persistra.monte_carlo import (
    MaximumDrawdown,
    MinimumLevel,
    MonteCarloExperiment,
    PathVolatility,
    TerminalLevel,
    TerminalReturn,
    ThresholdBreach,
    run_experiment,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.random import Generator
    from numpy.typing import NDArray


@dataclass(frozen=True)
class FixedPathModel:
    """Return one fixed two-variable path."""

    path: NDArray[np.float64]

    @property
    def name(self) -> str:
        return "fixed_path"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return "price", "return"

    @property
    def output_semantics(self) -> str:
        return "mixed_test_path"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {}

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        del generator, time_steps
        return self.path.copy()


def fixed_path() -> NDArray[np.float64]:
    """Return levels and simple returns with known outcomes."""
    return np.array(
        [
            [100.0, 0.10],
            [120.0, -0.20],
            [90.0, 0.05],
            [110.0, 0.02],
        ]
    )


def test_built_in_metrics_report_exact_path_outcomes() -> None:
    path = fixed_path()
    index = pd.RangeIndex(4)
    names = ("price", "return")
    metrics = (
        TerminalLevel("price"),
        TerminalReturn("price", initial_level=100.0),
        PathVolatility("return", periods_per_year=12),
        MaximumDrawdown("price"),
        MaximumDrawdown("return", input_kind="simple_return"),
        MinimumLevel("price"),
        ThresholdBreach("price", 95.0),
        ThresholdBreach("price", 115.0, direction="above"),
    )

    outcomes = [metric.evaluate(path, index, names) for metric in metrics]

    assert outcomes[0] == 110.0
    assert outcomes[1] == pytest.approx(0.1)
    assert outcomes[2] == pytest.approx(path[:, 1].std(ddof=1) * np.sqrt(12))
    assert outcomes[3] == pytest.approx(0.25)
    assert outcomes[4] == pytest.approx(0.20)
    assert outcomes[5] == 90.0
    assert outcomes[6:] == [1.0, 1.0]
    assert metrics[1].parameters == {"variable": "price", "initial_level": 100.0}


def test_metrics_integrate_with_runner_summaries_and_manifest() -> None:
    metrics = (
        TerminalLevel("price"),
        TerminalReturn("price", 100.0),
        MaximumDrawdown("price"),
        MinimumLevel("price"),
        ThresholdBreach("price", 95.0),
    )
    result = run_experiment(
        MonteCarloExperiment(
            FixedPathModel(fixed_path()),
            pd.RangeIndex(4),
            (1.0, 1.0, 1.0, 1.0),
            path_count=3,
            root_seed=7,
            metrics=metrics,
            retain_paths=False,
            convergence_checkpoints=(1, 2),
        )
    )

    assert result.paths is None
    assert result.metrics["terminal_level:price"].eq(110.0).all()
    assert result.summary.loc["maximum_drawdown:price", "mean"] == pytest.approx(0.25)
    assert result.convergence.loc[(2, "minimum_level:price"), "mean"] == 90.0
    manifest_metrics = result.manifest["metrics"]
    assert manifest_metrics[0]["name"] == "terminal_level:price"


def test_metrics_reject_invalid_configuration_and_path_semantics() -> None:
    path = fixed_path()
    index = pd.RangeIndex(4)
    names = ("price", "return")
    with pytest.raises(ValueError, match="nonempty"):
        TerminalLevel("")
    with pytest.raises(ValueError, match="positive"):
        TerminalReturn("price", 0)
    with pytest.raises(ValueError, match="input_kind"):
        MaximumDrawdown("price", input_kind="returns")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="direction"):
        ThresholdBreach("price", 1.0, direction="sideways")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="not present"):
        MinimumLevel("missing").evaluate(path, index, names)
    with pytest.raises(ValueError, match="at least two"):
        PathVolatility("return", 12).evaluate(path[:1], index[:1], names)
    invalid_levels = path.copy()
    invalid_levels[1, 0] = 0.0
    with pytest.raises(ValueError, match="positive"):
        MaximumDrawdown("price").evaluate(invalid_levels, index, names)
    invalid_returns = path.copy()
    invalid_returns[1, 1] = -1.1
    with pytest.raises(ValueError, match="less than -1"):
        MaximumDrawdown("return", "simple_return").evaluate(invalid_returns, index, names)
