"""Tests for bounded portfolio evaluation of Monte Carlo paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pandas as pd
import pytest

from persistra.monte_carlo import (
    MonteCarloExperiment,
    PortfolioBacktestEvaluator,
    evaluate_paths,
    run_experiment,
)
from persistra.portfolio import BacktestTiming, backtest_portfolio

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.random import Generator
    from numpy.typing import NDArray


@dataclass(frozen=True)
class ReturnPathModel:
    """Generate small deterministic return paths from stable random streams."""

    @property
    def name(self) -> str:
        return "test_return_paths"

    @property
    def version(self) -> str:
        return "1"

    @property
    def variable_names(self) -> tuple[str, ...]:
        return ("stock", "bond")

    @property
    def output_semantics(self) -> str:
        return "simple_return"

    @property
    def parameters(self) -> Mapping[str, Any]:
        return {}

    def generate(
        self,
        generator: Generator,
        time_steps: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        return generator.normal(0.001, 0.005, size=(len(time_steps), 2))


def _experiment(*, retain_paths: bool) -> MonteCarloExperiment:
    index = pd.date_range("2024-01-02", periods=5, freq="B", name="date")
    return MonteCarloExperiment(
        model=ReturnPathModel(),
        output_index=index,
        time_steps=(1.0,) * len(index),
        path_count=4,
        root_seed=19,
        retain_paths=retain_paths,
    )


def _evaluator() -> PortfolioBacktestEvaluator:
    targets = pd.DataFrame(
        [[0.6, 0.4]],
        index=pd.DatetimeIndex(["2024-01-02"], name="date"),
        columns=["stock", "bond"],
    )
    return PortfolioBacktestEvaluator(
        targets,
        timing=BacktestTiming(execution_lag=0, signal_available_before_trade=True),
        transaction_cost_bps=pd.Series({"stock": 2.0, "bond": 1.0}),
    )


def test_streamed_and_post_run_portfolio_evaluation_match() -> None:
    retained = run_experiment(_experiment(retain_paths=True))
    post_run = evaluate_paths(retained, _evaluator())
    streamed = run_experiment(
        _experiment(retain_paths=False),
        evaluator=_evaluator(),
    )

    pd.testing.assert_frame_equal(post_run.metrics, streamed.metrics)
    assert post_run.evaluator_name == "portfolio_backtest"
    assert post_run.evaluator_parameters["path_kind"] == "returns"
    assert streamed.paths is None


def test_portfolio_metrics_reconcile_with_backtest_result() -> None:
    result = run_experiment(_experiment(retain_paths=True))
    evaluator = _evaluator()
    evaluated = evaluate_paths(result, evaluator)
    expected = backtest_portfolio(
        evaluator.target_weights,
        returns=result.path_frame(0),
        timing=evaluator.timing,
        transaction_cost_bps=evaluator.transaction_cost_bps,
    )

    row = evaluated.metrics.iloc[0]
    assert row["portfolio_terminal_equity"] == pytest.approx(expected.equity.iloc[-1])
    assert row["portfolio_return"] == pytest.approx(expected.equity.iloc[-1] - 1.0)
    assert row["portfolio_maximum_drawdown"] == pytest.approx(-expected.drawdown.min())
    assert row["portfolio_turnover"] == pytest.approx(expected.turnover.sum())
    assert row["portfolio_cost"] == pytest.approx(expected.costs.sum())


@pytest.mark.parametrize("path_kind", ["returns", "prices"])
def test_portfolio_evaluator_accepts_explicit_path_kinds(
    path_kind: Literal["returns", "prices"],
) -> None:
    evaluator = PortfolioBacktestEvaluator(
        _evaluator().target_weights,
        path_kind=path_kind,
    )
    path = np.array([[0.01, 0.02], [0.02, 0.01]])
    if path_kind == "prices":
        path += 1.0

    metrics = evaluator.evaluate(
        path,
        pd.date_range("2024-01-02", periods=2, freq="B"),
        ("stock", "bond"),
    )

    assert tuple(metrics) == evaluator.metric_names


def test_portfolio_evaluator_rejects_invalid_axes_and_inputs() -> None:
    targets = _evaluator().target_weights
    with pytest.raises(TypeError, match="DatetimeIndex"):
        PortfolioBacktestEvaluator(targets.set_axis(pd.RangeIndex(1)))
    with pytest.raises(ValueError, match="target asset axis"):
        PortfolioBacktestEvaluator(targets, transaction_cost_bps=pd.Series({"other": 1.0}))
    with pytest.raises(ValueError, match="nonnegative"):
        PortfolioBacktestEvaluator(targets, transaction_cost_bps=-1.0)

    evaluator = _evaluator()
    with pytest.raises(TypeError, match="DatetimeIndex"):
        evaluator.evaluate(np.zeros((2, 2)), pd.RangeIndex(2), ("stock", "bond"))
    with pytest.raises(ValueError, match="variable axis"):
        evaluator.evaluate(
            np.zeros((2, 2)),
            pd.date_range("2024-01-02", periods=2),
            ("bond", "stock"),
        )
    with pytest.raises(ValueError, match="not retained"):
        evaluate_paths(run_experiment(_experiment(retain_paths=False)), evaluator)
