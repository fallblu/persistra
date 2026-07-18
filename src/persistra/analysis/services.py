"""Initial immutable performance metric computation."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.analysis.models import (
    AnalysisArtifactId,
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
        self, run: RunHandle, *, metric_set: str = "persistra.standard@1"
    ) -> MetricsHandle:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("metric computation requires research_write mode")
        if metric_set not in {
            "persistra.standard@1",
            "persistra.standard.phase4@1",
        }:
            raise AnalysisUnavailableError("metric set is unavailable")
        summary = run.summary()
        execution = scoped_content_id(
            {
                "schema": "persistra.analysis.metrics_execution@1",
                "metric_set": metric_set,
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
            run.fills(),
            run.costs(),
            run.targets(),
        )
        output = scoped_content_id(
            {
                "schema": "persistra.analysis.metrics_output@1",
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
    fills: pd.DataFrame,
    costs: pd.DataFrame,
    targets: pd.DataFrame,
) -> tuple[MetricResult, ...]:
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
    sharpe: float | None = None
    if deviation is not None and deviation != 0.0 and factor is not None:
        sharpe = statistics.mean(computed) / deviation * math.sqrt(factor)
    downside = [min(value, 0.0) for value in computed]
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
            statistics.mean(computed) / downside_deviation * math.sqrt(factor)
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
    hit_rate = (
        sum(value > 0 for value in computed) / count if count else None
    )
    ordered = sorted(computed)
    var_95 = ordered[max(0, math.ceil(count * 0.05) - 1)] if count else None
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
        traded / average_nav
        if average_nav is not None and average_nav > 0
        else None
    )
    total_cost = (
        sum(float(value) for value in costs["amount_usd"]) if not costs.empty else 0.0
    )
    target_total = (
        sum(abs(float(value)) for value in targets["target_quantity"] if pd.notna(value))
        if not targets.empty
        else 0.0
    )
    shortfall_total = (
        sum(abs(float(value)) for value in targets["shortfall_quantity"] if pd.notna(value))
        if not targets.empty
        else 0.0
    )
    capacity_shortfall = (
        shortfall_total / target_total if target_total > 0 else None
    )
    return (
        _metric("persistra.metric.total_return", total, "rate", count),
        _metric("persistra.metric.annualized_return", annual, "rate", count),
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
            warning="analysis.risk_free.assumed_zero",
        ),
        _metric("persistra.metric.max_drawdown", drawdown, "rate", len(equity)),
        _metric(
            "persistra.metric.sortino",
            sortino,
            "ratio",
            count,
            minimum=2,
            warning="analysis.risk_free.assumed_zero",
        ),
        _metric("persistra.metric.calmar", calmar, "ratio", count),
        _metric("persistra.metric.hit_rate", hit_rate, "rate", count),
        _metric("persistra.metric.var_95", var_95, "rate", count),
        _metric("persistra.metric.cvar_95", cvar_95, "rate", count),
        _metric(
            "persistra.metric.skewness", skewness, "ratio", count, minimum=3
        ),
        _metric(
            "persistra.metric.excess_kurtosis",
            excess_kurtosis,
            "ratio",
            count,
            minimum=4,
        ),
        _metric("persistra.metric.turnover", turnover, "ratio", len(fills)),
        _metric(
            "persistra.metric.total_cost",
            total_cost,
            "USD",
            len(costs),
            minimum=0,
        ),
        _metric(
            "persistra.metric.capacity_shortfall",
            capacity_shortfall,
            "rate",
            len(targets),
        ),
    )


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
    __slots__ = ("advanced", "metrics")

    def __init__(self, project: Project) -> None:
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
