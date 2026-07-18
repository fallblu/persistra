"""Immutable versioned performance metric computation."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.analysis.models import (
    AnalysisArtifactId,
    MetricInputs,
    MetricResult,
    MetricsRef,
    MetricState,
)
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    AnalysisUnavailableError,
    CapabilityUnavailableError,
)

if TYPE_CHECKING:
    from persistra.analysis.advanced_services import TabularAnalysisHandle
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.results.services import RunHandle

_YEAR_SECONDS = 365.25 * 24 * 60 * 60


class MetricService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def compute(
        self,
        run: RunHandle,
        *,
        metric_set: str = "persistra.standard@1",
        inputs: MetricInputs | None = None,
    ) -> MetricsHandle:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("metric computation requires research_write mode")
        if metric_set not in {
            "persistra.standard@1",
            "persistra.standard.phase4@1",
        }:
            raise AnalysisUnavailableError("metric set is unavailable")
        resolved_inputs = inputs or MetricInputs()
        summary = run.summary()
        execution = scoped_content_id(
            {
                "schema": "persistra.analysis.metrics_execution@2",
                "metric_set": metric_set,
                "inputs": resolved_inputs,
                "run": summary.run_record_id,
                "result_manifest": summary.result_manifest_content_id,
            }
        )
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        existing = connection.execute(
            "SELECT analysis_artifact_id FROM analysis.artifacts "
            "WHERE execution_content_id = ?",
            [str(execution)],
        ).fetchone()
        if existing is not None:
            return self.get(AnalysisArtifactId.parse(existing[0]))
        results = _compute(
            run.equity(),
            run.returns(),
            run.positions(),
            run.fills(),
            run.costs(),
            resolved_inputs,
        )
        output = scoped_content_id(
            {
                "schema": "persistra.analysis.metrics_output@2",
                "execution": execution,
                "results": results,
            }
        )

        def operation(context: TransactionContext) -> MetricsHandle:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            artifact_id = AnalysisArtifactId.new()
            active.execute(
                "INSERT INTO analysis.artifacts VALUES (?, ?, ?, ?, ?, ?)",
                [
                    artifact_id.value,
                    "metrics",
                    run.id.value,
                    str(execution),
                    str(output),
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO analysis_data.metric_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        artifact_id.value,
                        result.metric_name,
                        result.state.value,
                        result.estimate,
                        result.unit,
                        result.observation_count,
                        result.reason_code,
                    )
                    for result in results
                ],
            )
            return MetricsHandle(
                self._project, MetricsRef(artifact_id, execution, output)
            )

        return self._project.services.transactions.run("metrics_compute", operation)

    def get(self, artifact_id: AnalysisArtifactId) -> MetricsHandle:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT execution_content_id, output_content_id FROM analysis.artifacts "
            "WHERE analysis_artifact_id = ? AND artifact_kind = 'metrics'",
            [artifact_id.value],
        ).fetchone()
        if row is None:
            raise AnalysisUnavailableError("metrics artifact is missing")
        return MetricsHandle(
            self._project,
            MetricsRef(artifact_id, ContentId.parse(row[0]), ContentId.parse(row[1])),
        )


def _compute(
    equity: pd.DataFrame,
    returns: pd.DataFrame,
    positions: pd.DataFrame,
    fills: pd.DataFrame,
    costs: pd.DataFrame,
    inputs: MetricInputs | None = None,
) -> tuple[MetricResult, ...]:
    inputs = inputs or MetricInputs()
    computed = [
        float(value)
        for value in returns.loc[returns["state"] == "computed", "return_value"]
        if pd.notna(value)
    ]
    count = len(computed)
    if count:
        total = math.prod(1.0 + value for value in computed) - 1.0
    else:
        total = None
    elapsed = 0.0
    if len(equity) >= 2:
        elapsed = (
            equity.iloc[-1]["valued_at"] - equity.iloc[0]["valued_at"]
        ).total_seconds()
    annual = (
        (1.0 + total) ** (_YEAR_SECONDS / elapsed) - 1.0
        if total is not None and total > -1 and elapsed > 0
        else None
    )
    factor = count * _YEAR_SECONDS / elapsed if count >= 2 and elapsed > 0 else None
    deviation = statistics.stdev(computed) if count >= 2 else None
    volatility = deviation * math.sqrt(factor) if deviation is not None and factor else None
    risk_free = (
        [0.0] * count
        if inputs.risk_free_returns is None
        else list(inputs.risk_free_returns)
    )
    risk_free_aligned = len(risk_free) == count
    excess = (
        [value - risk_free[index] for index, value in enumerate(computed)]
        if risk_free_aligned
        else []
    )
    excess_deviation = statistics.stdev(excess) if len(excess) >= 2 else None
    sharpe: float | None = None
    if (
        excess_deviation is not None
        and excess_deviation != 0.0
        and factor is not None
    ):
        sharpe = statistics.mean(excess) / excess_deviation * math.sqrt(factor)
    downside = [min(value, 0.0) for value in excess]
    downside_deviation = (
        math.sqrt(sum(value * value for value in downside) / count)
        if count
        else None
    )
    sortino: float | None = None
    if (
        downside_deviation is not None
        and downside_deviation != 0.0
        and factor is not None
    ):
        sortino = (
            statistics.mean(excess) / downside_deviation * math.sqrt(factor)
        )
    drawdown: float | None = None
    if not equity.empty:
        navs = [float(value) for value in equity["nav_usd"]]
        peak = navs[0]
        drawdown = 0.0
        for nav in navs:
            peak = max(peak, nav)
            drawdown = min(drawdown, nav / peak - 1.0)
    calmar: float | None = None
    if annual is not None and drawdown is not None and drawdown != 0.0:
        calmar = annual / abs(drawdown)
    hit_rate = sum(value > 0 for value in computed) / count if count else None
    ordered = sorted(computed)
    var_95 = _type7_quantile(ordered, 0.05) if count >= 20 else None
    tail = [value for value in computed if var_95 is not None and value <= var_95]
    cvar_95 = statistics.mean(tail) if tail else None
    mean = statistics.mean(computed) if count else None
    skewness = None
    excess_kurtosis = None
    if mean is not None and deviation is not None and deviation != 0.0 and count >= 3:
        skewness = (
            count
            / ((count - 1) * (count - 2))
            * sum(((value - mean) / deviation) ** 3 for value in computed)
        )
    if mean is not None and deviation is not None and deviation != 0.0 and count >= 4:
        excess_kurtosis = (
            count
            * (count + 1)
            / ((count - 1) * (count - 2) * (count - 3))
            * sum(((value - mean) / deviation) ** 4 for value in computed)
            - 3 * (count - 1) ** 2 / ((count - 2) * (count - 3))
        )
    average_nav = (
        statistics.mean(float(value) for value in equity["nav_usd"])
        if not equity.empty
        else None
    )
    traded = (
        sum(
            float(cast("Any", row.quantity))
            * float(cast("Any", row.fill_price_usd))
            for row in fills.itertuples(index=False)
        )
        if not fills.empty
        else 0.0
    )
    turnover = (
        traded
        / (2 * average_nav)
        * (_YEAR_SECONDS / elapsed)
        if average_nav is not None and average_nav > 0 and elapsed > 0
        else None
    )
    total_cost = (
        sum(float(value) for value in costs["amount_usd"]) if not costs.empty else 0.0
    )
    gains = [value for value in computed if value > 0]
    losses = [value for value in computed if value < 0]
    payoff = (
        statistics.mean(gains) / abs(statistics.mean(losses))
        if gains and losses
        else None
    )
    concentration_values: list[float] = []
    if not positions.empty:
        for _, group in positions.groupby("sample_ordinal", sort=True):
            values = [abs(float(value)) for value in group["market_value_usd"]]
            gross = sum(values)
            if gross > 0:
                concentration_values.append(
                    sum((value / gross) ** 2 for value in values)
                )
    concentration = (
        statistics.mean(concentration_values) if concentration_values else None
    )
    benchmark = (
        None
        if inputs.benchmark_returns is None
        else list(inputs.benchmark_returns)
    )
    benchmark_aligned = benchmark is not None and len(benchmark) == count
    beta: float | None = None
    alpha: float | None = None
    active_return: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    if benchmark_aligned and risk_free_aligned and factor is not None:
        assert benchmark is not None
        benchmark_excess = [
            value - risk_free[index] for index, value in enumerate(benchmark)
        ]
        active = [
            value - benchmark[index] for index, value in enumerate(computed)
        ]
        if count >= 2:
            benchmark_variance = statistics.variance(benchmark_excess)
            if benchmark_variance != 0:
                beta = (
                    sum(
                        (excess[index] - statistics.mean(excess))
                        * (
                            benchmark_excess[index]
                            - statistics.mean(benchmark_excess)
                        )
                        for index in range(count)
                    )
                    / (count - 1)
                    / benchmark_variance
                )
                alpha = (
                    statistics.mean(excess)
                    - beta * statistics.mean(benchmark_excess)
                ) * factor
            active_deviation = statistics.stdev(active)
            tracking_error = active_deviation * math.sqrt(factor)
            if active_deviation != 0:
                information_ratio = (
                    statistics.mean(active) / active_deviation * math.sqrt(factor)
                )
        active_return = statistics.mean(active) * factor
    drawdown_duration: float | None = None
    drawdown_reason: str | None = None
    if not equity.empty and drawdown is not None:
        navs = [float(value) for value in equity["nav_usd"]]
        times = [pd.Timestamp(value) for value in equity["valued_at"]]
        peak_index = 0
        maximum_peak_index = 0
        trough_index = 0
        maximum_depth = 0.0
        for index, nav in enumerate(navs):
            if nav > navs[peak_index]:
                peak_index = index
            depth = nav / navs[peak_index] - 1.0
            if depth < maximum_depth:
                maximum_depth = depth
                maximum_peak_index = peak_index
                trough_index = index
        if maximum_depth == 0.0:
            drawdown_duration = 0.0
        else:
            recovery = next(
                (
                    index
                    for index in range(trough_index + 1, len(navs))
                    if navs[index] >= navs[maximum_peak_index]
                ),
                None,
            )
            if recovery is None:
                drawdown_reason = "analysis.drawdown.unrecovered"
            else:
                drawdown_duration = (
                    times[recovery] - times[maximum_peak_index]
                ).total_seconds() / 86_400
    results = (
        _metric("persistra.metric.total_return", total, "rate", count),
        _metric("persistra.metric.annualized_return", annual, "rate", count),
        _metric(
            "persistra.metric.money_weighted_return",
            annual,
            "rate",
            count,
            warning="analysis.cash_flows.assumed_none",
        ),
        _metric(
            "persistra.metric.annualized_volatility",
            volatility,
            "rate",
            count,
            minimum=2,
        ),
        _metric(
            "persistra.metric.sharpe",
            sharpe,
            "ratio",
            count,
            minimum=2,
            warning=(
                "analysis.risk_free.assumed_zero"
                if inputs.risk_free_returns is None
                else None
            ),
        ),
        _metric("persistra.metric.max_drawdown", drawdown, "rate", len(equity)),
        (
            _metric(
                "persistra.metric.drawdown_duration",
                drawdown_duration,
                "days",
                len(equity),
            )
            if drawdown_reason is None
            else _unavailable(
                "persistra.metric.drawdown_duration",
                "days",
                len(equity),
                MetricState.UNDEFINED,
                drawdown_reason,
            )
        ),
        _metric(
            "persistra.metric.sortino",
            sortino,
            "ratio",
            count,
            minimum=2,
            warning=(
                "analysis.risk_free.assumed_zero"
                if inputs.risk_free_returns is None
                else None
            ),
        ),
        _metric("persistra.metric.calmar", calmar, "ratio", count),
        _metric(
            "persistra.metric.var_historical",
            var_95,
            "rate",
            count,
            minimum=20,
        ),
        _metric(
            "persistra.metric.expected_shortfall",
            cvar_95,
            "rate",
            count,
            minimum=20,
        ),
        _metric(
            "persistra.metric.skewness", skewness, "ratio", count, minimum=3
        ),
        _metric(
            "persistra.metric.kurtosis",
            excess_kurtosis,
            "ratio",
            count,
            minimum=4,
        ),
        _metric("persistra.metric.hit_rate", hit_rate, "ratio", count),
        _metric(
            "persistra.metric.payoff_ratio",
            payoff,
            "ratio",
            min(len(gains), len(losses)),
        ),
        (
            _metric("persistra.metric.beta", beta, "ratio", count, minimum=2)
            if benchmark_aligned
            else _missing(
                "persistra.metric.beta",
                "ratio",
                count,
                "analysis.benchmark.missing_or_unaligned",
            )
        ),
        (
            _metric("persistra.metric.alpha", alpha, "rate", count, minimum=2)
            if benchmark_aligned
            else _missing(
                "persistra.metric.alpha",
                "rate",
                count,
                "analysis.benchmark.missing_or_unaligned",
            )
        ),
        (
            _metric("persistra.metric.active_return", active_return, "rate", count)
            if benchmark_aligned
            else _missing(
                "persistra.metric.active_return",
                "rate",
                count,
                "analysis.benchmark.missing_or_unaligned",
            )
        ),
        (
            _metric(
                "persistra.metric.tracking_error",
                tracking_error,
                "rate",
                count,
                minimum=2,
            )
            if benchmark_aligned
            else _missing(
                "persistra.metric.tracking_error",
                "rate",
                count,
                "analysis.benchmark.missing_or_unaligned",
            )
        ),
        (
            _metric(
                "persistra.metric.information_ratio",
                information_ratio,
                "ratio",
                count,
                minimum=2,
            )
            if benchmark_aligned
            else _missing(
                "persistra.metric.information_ratio",
                "ratio",
                count,
                "analysis.benchmark.missing_or_unaligned",
            )
        ),
        _metric("persistra.metric.turnover", turnover, "rate", len(fills)),
        _missing(
            "persistra.metric.holding_period",
            "days",
            0,
            "analysis.closed_lots.missing",
        ),
        _metric(
            "persistra.metric.concentration",
            concentration,
            "ratio",
            len(concentration_values),
        ),
        _metric(
            "persistra.metric.cost_total",
            total_cost,
            "usd",
            len(costs),
        ),
        _missing(
            "persistra.metric.participation_mean",
            "ratio",
            0,
            "analysis.eligible_volume.missing",
        ),
        _missing(
            "persistra.metric.participation_p95",
            "ratio",
            0,
            "analysis.eligible_volume.missing",
        ),
    )
    if tuple(result.metric_name for result in results) != _STANDARD_METRIC_NAMES:
        raise AssertionError("standard metric registry and execution order diverged")
    return results


_STANDARD_METRIC_NAMES = (
    "persistra.metric.total_return",
    "persistra.metric.annualized_return",
    "persistra.metric.money_weighted_return",
    "persistra.metric.annualized_volatility",
    "persistra.metric.sharpe",
    "persistra.metric.max_drawdown",
    "persistra.metric.drawdown_duration",
    "persistra.metric.sortino",
    "persistra.metric.calmar",
    "persistra.metric.var_historical",
    "persistra.metric.expected_shortfall",
    "persistra.metric.skewness",
    "persistra.metric.kurtosis",
    "persistra.metric.hit_rate",
    "persistra.metric.payoff_ratio",
    "persistra.metric.beta",
    "persistra.metric.alpha",
    "persistra.metric.active_return",
    "persistra.metric.tracking_error",
    "persistra.metric.information_ratio",
    "persistra.metric.turnover",
    "persistra.metric.holding_period",
    "persistra.metric.concentration",
    "persistra.metric.cost_total",
    "persistra.metric.participation_mean",
    "persistra.metric.participation_p95",
)


def _type7_quantile(ordered: list[float], probability: float) -> float:
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _missing(
    name: str,
    unit: str,
    count: int,
    reason: str,
) -> MetricResult:
    return _unavailable(name, unit, count, MetricState.MISSING_INPUT, reason)


def _unavailable(
    name: str,
    unit: str,
    count: int,
    state: MetricState,
    reason: str,
) -> MetricResult:
    return MetricResult(name, state, None, unit, count, reason)


def _metric(
    name: str,
    estimate: float | None,
    unit: str,
    count: int,
    *,
    minimum: int = 1,
    warning: str | None = None,
) -> MetricResult:
    if count < minimum:
        return MetricResult(
            name,
            MetricState.INSUFFICIENT_OBSERVATIONS,
            None,
            unit,
            count,
            "analysis.observations.insufficient",
        )
    if estimate is None or not math.isfinite(estimate):
        return MetricResult(
            name,
            MetricState.UNDEFINED,
            None,
            unit,
            count,
            "analysis.metric.undefined",
        )
    return MetricResult(name, MetricState.COMPUTED, estimate, unit, count, warning)


@dataclass(frozen=True, slots=True)
class MetricsHandle:
    _project: Project
    reference: MetricsRef

    @property
    def id(self) -> AnalysisArtifactId:
        return self.reference.analysis_artifact_id

    def results(self) -> tuple[MetricResult, ...]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT metric_name, state, estimate, unit, observation_count, reason_code "
            "FROM analysis_data.metric_results WHERE analysis_artifact_id = ? "
            "ORDER BY metric_name",
            [self.id.value],
        ).fetchall()
        return tuple(
            MetricResult(
                row[0],
                MetricState(row[1]),
                None if row[2] is None else float(row[2]),
                row[3],
                int(row[4]),
                row[5],
            )
            for row in rows
        )

    def scalar(self, metric_name: str) -> MetricResult:
        matches = [item for item in self.results() if item.metric_name == metric_name]
        if len(matches) != 1:
            raise AnalysisUnavailableError("metric result is unavailable or nonunique")
        return matches[0]


class AnalysisService:
    __slots__ = ("_project", "advanced", "metrics")

    def __init__(self, project: Project) -> None:
        self._project = project
        self.metrics = MetricService(project)
        from persistra.analysis.advanced_services import AdvancedAnalysisService

        self.advanced = AdvancedAnalysisService(project, self.metrics)

    def execution(self, run: RunHandle) -> TabularAnalysisHandle:
        return self.advanced.execution(run)

    def attribution(self, run: RunHandle) -> TabularAnalysisHandle:
        return self.advanced.attribution(run)

    def compare(
        self, left: RunHandle, right: RunHandle, *, allow_warned: bool = False
    ) -> TabularAnalysisHandle:
        return self.advanced.compare(left, right, allow_warned=allow_warned)

    def scenarios(
        self, metrics: tuple[MetricsHandle, ...]
    ) -> TabularAnalysisHandle:
        return self.advanced.scenarios(metrics)

    def list(
        self,
        *,
        run_record_id: Any | None = None,
        max_rows: int = 10_000,
    ) -> pd.DataFrame:
        """List immutable analysis artifacts in canonical creation order."""
        if max_rows < 1:
            raise AnalysisUnavailableError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        where = "" if run_record_id is None else "WHERE run_record_id = ? "
        parameters = (
            [max_rows + 1]
            if run_record_id is None
            else [run_record_id.value, max_rows + 1]
        )
        frame = connection.execute(
            "SELECT analysis_artifact_id, artifact_kind, run_record_id, "
            "execution_content_id, output_content_id, created_at "
            f"FROM analysis.artifacts {where}"
            "ORDER BY created_at, analysis_artifact_id LIMIT ?",
            parameters,
        ).fetchdf()
        if len(frame) > max_rows:
            raise AnalysisUnavailableError("analysis rows exceed max_rows")
        return frame

    def get_tabular(self, artifact_id: AnalysisArtifactId) -> TabularAnalysisHandle:
        """Open an existing immutable non-metric tabular analysis."""
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT artifact_kind, execution_content_id, output_content_id "
            "FROM analysis.artifacts WHERE analysis_artifact_id = ?",
            [artifact_id.value],
        ).fetchone()
        if row is None or row[0] in {"metrics", "report"}:
            raise AnalysisUnavailableError("tabular analysis artifact is missing")
        from persistra.analysis.advanced_services import TabularAnalysisHandle
        from persistra.analysis.models import TabularAnalysisRef

        return TabularAnalysisHandle(
            self._project,
            TabularAnalysisRef(
                artifact_id,
                str(row[0]),
                ContentId.parse(row[1]),
                ContentId.parse(row[2]),
            ),
        )
