"""Result containers for parameter sweeps, walk-forward, and comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from persistra.core.result import Result
from persistra.metrics.perf import benchmark_free_summary
from persistra.viz import styled_figure

# The nine metrics available without a benchmark series.
BENCHMARK_FREE_METRICS: tuple[str, ...] = (
    "ann_return",
    "ann_vol",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "hit_rate",
    "var_95",
    "cvar_95",
)


def result_metrics(result: Result) -> dict[str, float]:
    """Compute the benchmark-free summary metrics for a backtest result."""
    return benchmark_free_summary(result.equity_curve["equity"])


@dataclass
class SweepResult:
    """Output of a parameter sweep (grid / random / bayes)."""

    params: list[dict[str, Any]]
    results: list[Result]

    def summary_dataframe(self) -> pd.DataFrame:
        """Build a tidy DataFrame with one row per sweep run.

        Each row contains all parameter values for that run followed by the
        nine benchmark-free metrics (``BENCHMARK_FREE_METRICS``) and
        the ``run_id`` from the result metadata.  Missing metric values are
        filled with ``NaN``.

        Returns:
            A ``pd.DataFrame`` with columns for every parameter key, each
            metric in ``BENCHMARK_FREE_METRICS``, and ``run_id``.
        """
        rows: list[dict[str, Any]] = []
        for params, result in zip(self.params, self.results, strict=True):
            row: dict[str, Any] = dict(params)
            metrics = result_metrics(result)
            for key in BENCHMARK_FREE_METRICS:
                row[key] = float(metrics.get(key, float("nan")))
            row["run_id"] = result.meta.get("run_id")
            rows.append(row)
        return pd.DataFrame(rows)

    def best(
        self,
        metric: str = "sharpe",
        *,
        maximize: bool = True,
    ) -> tuple[dict[str, Any], Result]:
        """Return the parameter set and result with the best metric value."""
        if not self.results:
            raise ValueError("cannot select best run from an empty sweep")

        summary = self.summary_dataframe()
        if metric not in summary.columns:
            raise KeyError(f"metric {metric!r} not found; available: {list(summary.columns)}")

        scores = summary[metric].astype(float)
        if scores.dropna().empty:
            raise ValueError(f"metric {metric!r} has no finite values")
        index = int(scores.idxmax() if maximize else scores.idxmin())
        return self.params[index], self.results[index]


@dataclass
class WalkForwardResult:
    """Output of walk_forward: one Result per (train_start, test_start, test_end) fold."""

    folds: list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, Result]]

    def test_results(self) -> list[Result]:
        """Return Result objects trimmed to each fold's test window."""
        out: list[Result] = []
        for _train_start, test_start, test_end, result in self.folds:
            eq = result.equity_curve
            trimmed_eq = eq.loc[(eq.index >= test_start) & (eq.index <= test_end)].copy()

            if result.trades.empty:
                trimmed_trades = result.trades.copy()
            else:
                mask = (result.trades["timestamp"] >= test_start) & (
                    result.trades["timestamp"] <= test_end
                )
                trimmed_trades = result.trades[mask].copy()

            if result.positions.empty:
                trimmed_positions = result.positions.copy()
            else:
                mask = (result.positions["bar_time"] >= test_start) & (
                    result.positions["bar_time"] <= test_end
                )
                trimmed_positions = result.positions[mask].copy()

            if result.orders.empty:
                trimmed_orders = result.orders.copy()
            else:
                mask = (result.orders["terminal_timestamp"] >= test_start) & (
                    result.orders["terminal_timestamp"] <= test_end
                )
                trimmed_orders = result.orders[mask].copy()

            if result.diagnostics.empty:
                trimmed_diagnostics = result.diagnostics.copy()
            else:
                mask = (result.diagnostics["bar_time"] >= test_start) & (
                    result.diagnostics["bar_time"] <= test_end
                )
                trimmed_diagnostics = result.diagnostics[mask].copy()

            out.append(
                Result(
                    equity_curve=trimmed_eq,
                    trades=trimmed_trades,
                    positions=trimmed_positions,
                    orders=trimmed_orders,
                    diagnostics=trimmed_diagnostics,
                    meta=dict(result.meta),
                )
            )
        return out

    def stitched_equity_curve(self) -> pd.Series:
        """Chain test-window equity curves end-to-end, rebased so each fold continues
        from where the previous one ended."""
        if not self.folds:
            return pd.Series(dtype="float64")
        pieces: list[pd.Series] = []
        running_equity: float | None = None
        for result in self.test_results():
            eq = result.equity_curve["equity"].astype(float).copy()
            if eq.empty:
                continue
            if running_equity is None:
                running_equity = float(eq.iloc[0])
                pieces.append(eq.copy())
            else:
                rets = eq.pct_change().fillna(0.0)
                rescaled = running_equity * (1.0 + rets).cumprod()
                pieces.append(rescaled)
            running_equity = float(pieces[-1].iloc[-1])
        if not pieces:
            return pd.Series(dtype="float64")
        stitched = pd.concat(pieces)
        stitched = stitched[~stitched.index.duplicated(keep="last")]
        stitched.sort_index(inplace=True)
        stitched.name = "equity"
        return stitched

    def fold_metrics(self) -> pd.DataFrame:
        """Build a tidy DataFrame with one row per walk-forward fold.

        Each row contains the fold's ``train_start``, ``test_start``, and
        ``test_end`` timestamps followed by the nine benchmark-free
        metrics computed on that fold's test-window ``Result`` and the
        ``run_id`` from the result metadata.  Missing metric values are filled
        with ``NaN``.

        Returns:
            A ``pd.DataFrame`` with columns ``train_start``, ``test_start``,
            ``test_end``, each metric in ``BENCHMARK_FREE_METRICS``, and
            ``run_id``.
        """
        rows: list[dict[str, Any]] = []
        for (train_start, test_start, test_end, _), test_result in zip(
            self.folds, self.test_results(), strict=True
        ):
            row: dict[str, Any] = {
                "train_start": pd.Timestamp(train_start),
                "test_start": pd.Timestamp(test_start),
                "test_end": pd.Timestamp(test_end),
            }
            metrics = result_metrics(test_result)
            for key in BENCHMARK_FREE_METRICS:
                row[key] = float(metrics.get(key, float("nan")))
            row["run_id"] = test_result.meta.get("run_id")
            rows.append(row)
        return pd.DataFrame(rows)


@dataclass
class WalkForwardOptimizationResult:
    """Output of per-fold train-sweep/test-evaluate walk-forward optimization."""

    folds: list[
        tuple[
            pd.Timestamp,
            pd.Timestamp,
            pd.Timestamp,
            dict[str, Any],
            SweepResult,
            Result,
        ]
    ]
    metric: str
    maximize: bool

    def test_results(self) -> list[Result]:
        """Return selected-parameter Result objects trimmed to each test window."""
        wf = WalkForwardResult(
            folds=[
                (train_start, test_start, test_end, result)
                for train_start, test_start, test_end, _params, _sweep, result in self.folds
            ]
        )
        return wf.test_results()

    def selected_params_dataframe(self) -> pd.DataFrame:
        """Return one row per fold with selected parameters and train/test metrics."""
        rows: list[dict[str, Any]] = []
        for (
            train_start,
            test_start,
            test_end,
            params,
            train_sweep,
            _result,
        ), test_result in zip(self.folds, self.test_results(), strict=True):
            train_summary = train_sweep.summary_dataframe()
            selected = _matching_param_rows(train_summary, params)
            if selected.empty:
                _params, best_result = train_sweep.best(self.metric, maximize=self.maximize)
                train_metrics = result_metrics(best_result)
            else:
                train_metrics = selected.iloc[0].to_dict()
            test_metrics = result_metrics(test_result)
            row: dict[str, Any] = {
                "train_start": pd.Timestamp(train_start),
                "test_start": pd.Timestamp(test_start),
                "test_end": pd.Timestamp(test_end),
            }
            for key, value in params.items():
                row[f"param_{key}"] = value
            for key in BENCHMARK_FREE_METRICS:
                row[f"train_{key}"] = float(train_metrics.get(key, float("nan")))
                row[f"test_{key}"] = float(test_metrics.get(key, float("nan")))
            rows.append(row)
        return pd.DataFrame(rows)

    def stitched_equity_curve(self) -> pd.Series:
        """Chain selected test-window equity curves end-to-end."""
        return WalkForwardResult(
            folds=[
                (train_start, test_start, test_end, result)
                for train_start, test_start, test_end, _params, _sweep, result in self.folds
            ]
        ).stitched_equity_curve()


def _matching_param_rows(summary: pd.DataFrame, params: dict[str, Any]) -> pd.DataFrame:
    if summary.empty:
        return summary
    mask = pd.Series(True, index=summary.index)
    for key, value in params.items():
        if key not in summary.columns:
            return summary.iloc[0:0]
        mask &= summary[key] == value
    return summary.loc[mask]


@dataclass
class ComparisonResult:
    """Side-by-side comparison of multiple runs."""

    metrics: pd.DataFrame  # rows = runs, cols = metrics
    _results: list[Result]
    _run_ids: list[str]

    def overlay_equity(self) -> go.Figure:
        """Plotly figure overlaying each run's equity curve."""
        fig = styled_figure(
            title="Equity curves",
            xaxis_title="Date",
            yaxis_title="Equity",
        )
        for run_id, result in zip(self._run_ids, self._results, strict=True):
            eq = result.equity_curve["equity"].astype(float)
            fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name=run_id, mode="lines"))
        return fig

    def metric_bars(self, metric: str = "sharpe") -> go.Figure:
        """Bar chart of one metric across runs."""
        if metric not in self.metrics.columns:
            raise KeyError(
                f"metric {metric!r} not in comparison; available: {list(self.metrics.columns)}"
            )
        col = self.metrics[metric]
        fig = styled_figure(
            title=f"{metric} by run",
            xaxis_title="Run",
            yaxis_title=metric,
        )
        fig.add_trace(go.Bar(x=list(col.index), y=col.to_numpy(), name=metric))
        return fig

    def drawdown_overlay(self) -> go.Figure:
        """Overlay each run's underwater (drawdown) curve."""
        fig = styled_figure(
            title="Drawdown",
            xaxis_title="Date",
            yaxis_title="Drawdown",
        )
        for run_id, result in zip(self._run_ids, self._results, strict=True):
            eq = result.equity_curve["equity"].astype(float)
            dd = eq / eq.cummax() - 1.0
            fig.add_trace(go.Scatter(x=dd.index, y=dd.values, name=run_id, mode="lines"))
        fig.update_layout(yaxis_tickformat=".0%")
        return fig


__all__ = [
    "BENCHMARK_FREE_METRICS",
    "ComparisonResult",
    "SweepResult",
    "WalkForwardOptimizationResult",
    "WalkForwardResult",
    "result_metrics",
]
