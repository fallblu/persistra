"""This module contains the immutable versioned performance metric computation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import numpy as np
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
    AnalysisInputError,
    AnalysisUnavailableError,
    CapabilityUnavailableError,
)

if TYPE_CHECKING:
    from persistra.analysis.advanced_services import TabularAnalysisHandle
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.results.services import RunHandle
    from persistra.simulation import RunRecordId

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
        if metric_set != "persistra.standard@1":
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
            cash_flows=run.cash_flows(),
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
    *,
    cash_flows: pd.DataFrame | None = None,
) -> tuple[MetricResult, ...]:
    inputs = inputs or MetricInputs()
    eligible = returns.loc[
        (returns["state"] == "computed") & returns["return_value"].notna()
    ]
    series = eligible["return_value"].astype(float).to_numpy()
    count = int(series.size)
    _validate_alignment(inputs, count, len(fills))
    total = float(np.prod(1.0 + series) - 1.0) if count else None
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
    money_weighted = _money_weighted_return(equity, cash_flows)
    factor = count * _YEAR_SECONDS / elapsed if count >= 1 and elapsed > 0 else None
    deviation = float(np.std(series, ddof=1)) if count >= 2 else None
    volatility = deviation * math.sqrt(factor) if deviation is not None and factor else None
    risk_free = (
        np.zeros(count)
        if inputs.risk_free_returns is None
        else np.asarray(inputs.risk_free_returns, dtype=float)
    )
    excess = series - risk_free
    excess_deviation = float(np.std(excess, ddof=1)) if count >= 2 else None
    sharpe: float | None = None
    if (
        excess_deviation is not None
        and excess_deviation != 0.0
        and factor is not None
    ):
        sharpe = float(np.mean(excess)) / excess_deviation * math.sqrt(factor)
    downside = np.minimum(excess, 0.0)
    downside_deviation = (
        float(np.sqrt(np.mean(downside * downside))) if count else None
    )
    sortino: float | None = None
    if (
        downside_deviation is not None
        and downside_deviation != 0.0
        and factor is not None
    ):
        sortino = float(np.mean(excess)) / downside_deviation * math.sqrt(factor)
    index_values = np.concatenate(([1.0], np.cumprod(1.0 + series)))
    peaks = np.maximum.accumulate(index_values)
    depths = index_values / peaks - 1.0
    drawdown = float(depths.min()) if count else None
    calmar: float | None = None
    if annual is not None and drawdown is not None and drawdown != 0.0:
        calmar = annual / abs(drawdown)
    hit_rate = int(np.count_nonzero(series > 0.0)) / count if count else None
    var_95 = float(np.quantile(series, 0.05)) if count >= 20 else None
    cvar_95 = (
        float(np.mean(series[series <= var_95])) if var_95 is not None else None
    )
    mean = float(np.mean(series)) if count else None
    skewness = None
    excess_kurtosis = None
    if mean is not None and deviation is not None and deviation != 0.0 and count >= 3:
        standardized = (series - mean) / deviation
        skewness = (
            count
            / ((count - 1) * (count - 2))
            * float(np.sum(standardized**3))
        )
        if count >= 4:
            excess_kurtosis = (
                count
                * (count + 1)
                / ((count - 1) * (count - 2) * (count - 3))
                * float(np.sum(standardized**4))
                - 3 * (count - 1) ** 2 / ((count - 2) * (count - 3))
            )
    average_nav = (
        float(equity["nav_usd"].astype(float).mean()) if not equity.empty else None
    )
    traded = (
        float(
            (
                fills["quantity"].astype(float)
                * fills["fill_price_usd"].astype(float)
            )
            .abs()
            .sum()
        )
        if not fills.empty
        else 0.0
    )
    turnover = (
        traded / (2 * average_nav) * (_YEAR_SECONDS / elapsed)
        if average_nav is not None and average_nav > 0 and elapsed > 0
        else None
    )
    cost_totals: dict[str, float] = {}
    cost_counts: dict[str, int] = {}
    if not costs.empty:
        amounts = costs["amount_usd"].astype(float)
        grouped = amounts.groupby(costs["component_kind"].astype(str))
        cost_totals = {
            str(kind): float(value) for kind, value in grouped.sum().items()
        }
        cost_counts = {
            str(kind): int(value) for kind, value in grouped.size().items()
        }
    total_cost = sum(cost_totals.values())
    holding_period: float | None = None
    holding_count = 0
    if inputs.closed_lot_holding_periods is not None:
        holding_count = len(inputs.closed_lot_holding_periods)
        lots = np.asarray(
            inputs.closed_lot_holding_periods, dtype=float
        ).reshape(-1, 2)
        total_notional = float(lots[:, 1].sum()) if holding_count else 0.0
        if total_notional > 0:
            holding_period = float((lots[:, 0] * lots[:, 1]).sum()) / total_notional
    participation = np.empty(0)
    if inputs.eligible_volume_by_fill is not None:
        quantities = (
            fills["quantity"].astype(float).abs().to_numpy()
            if not fills.empty
            else np.empty(0)
        )
        participation = quantities / np.asarray(
            inputs.eligible_volume_by_fill, dtype=float
        )
    gains = series[series > 0]
    losses = series[series < 0]
    payoff = (
        float(np.mean(gains)) / abs(float(np.mean(losses)))
        if gains.size and losses.size
        else None
    )
    concentration: float | None = None
    concentration_count = 0
    if not positions.empty:
        absolute = positions["market_value_usd"].astype(float).abs()
        ordinals = positions["sample_ordinal"]
        gross = absolute.groupby(ordinals).transform("sum")
        included = gross > 0
        ratios = (absolute[included] / gross[included]) ** 2
        herfindahl = ratios.groupby(ordinals[included]).sum()
        concentration_count = len(herfindahl)
        if concentration_count:
            concentration = float(herfindahl.mean())
    benchmark = (
        None
        if inputs.benchmark_returns is None
        else np.asarray(inputs.benchmark_returns, dtype=float)
    )
    benchmark_aligned = benchmark is not None
    beta: float | None = None
    alpha: float | None = None
    active_return: float | None = None
    tracking_error: float | None = None
    information_ratio: float | None = None
    if benchmark is not None and factor is not None:
        benchmark_excess = benchmark - risk_free
        active = series - benchmark
        if count >= 2:
            benchmark_variance = float(np.var(benchmark_excess, ddof=1))
            excess_mean = float(np.mean(excess))
            benchmark_excess_mean = float(np.mean(benchmark_excess))
            if benchmark_variance != 0:
                beta = (
                    float(
                        np.sum(
                            (excess - excess_mean)
                            * (benchmark_excess - benchmark_excess_mean)
                        )
                    )
                    / (count - 1)
                    / benchmark_variance
                )
                alpha = (excess_mean - beta * benchmark_excess_mean) * factor
            active_deviation = float(np.std(active, ddof=1))
            tracking_error = active_deviation * math.sqrt(factor)
            if active_deviation != 0:
                information_ratio = (
                    float(np.mean(active)) / active_deviation * math.sqrt(factor)
                )
        active_return = float(np.mean(active)) * factor
    drawdown_duration: float | None = None
    drawdown_reason: str | None = None
    if count and drawdown is not None:
        trough_index = int(np.argmin(depths))
        if depths[trough_index] == 0.0:
            drawdown_duration = 0.0
        else:
            maximum_peak_index = int(np.argmax(index_values[: trough_index + 1]))
            later = np.nonzero(
                index_values[trough_index + 1 :]
                >= index_values[maximum_peak_index]
            )[0]
            if later.size == 0:
                drawdown_reason = "analysis.drawdown.unrecovered"
            else:
                anchor = pd.Timestamp(eligible.iloc[0]["interval_start"])
                ends = [pd.Timestamp(value) for value in eligible["interval_end"]]
                index_times = [anchor, *ends]
                recovery = trough_index + 1 + int(later[0])
                drawdown_duration = (
                    index_times[recovery] - index_times[maximum_peak_index]
                ).total_seconds() / 86_400
    relative_cost = (
        None if average_nav is None or average_nav <= 0 else total_cost / average_nav
    )
    cost_results: list[MetricResult] = [
        _metric("persistra.metric.cost_total", total_cost, "usd", len(costs)),
        _metric(
            "persistra.metric.cost_total_relative",
            relative_cost,
            "rate",
            len(costs),
        ),
    ]
    for kind in sorted(cost_totals):
        cost_results.append(
            _metric(
                f"persistra.metric.cost_total.{kind}",
                cost_totals[kind],
                "usd",
                cost_counts[kind],
            )
        )
        cost_results.append(
            _metric(
                f"persistra.metric.cost_total_relative.{kind}",
                (
                    None
                    if average_nav is None or average_nav <= 0
                    else cost_totals[kind] / average_nav
                ),
                "rate",
                cost_counts[kind],
            )
        )
    results = (
        _metric("persistra.metric.total_return", total, "rate", count),
        _metric("persistra.metric.annualized_return", annual, "rate", count),
        _metric(
            "persistra.metric.money_weighted_return",
            money_weighted,
            "rate",
            len(equity),
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
        _metric("persistra.metric.max_drawdown", drawdown, "rate", count),
        (
            _metric(
                "persistra.metric.drawdown_duration",
                drawdown_duration,
                "days",
                count,
            )
            if drawdown_reason is None
            else _unavailable(
                "persistra.metric.drawdown_duration",
                "days",
                count,
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
            int(min(gains.size, losses.size)),
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
        (
            _metric(
                "persistra.metric.holding_period",
                holding_period,
                "days",
                holding_count,
            )
            if inputs.closed_lot_holding_periods is not None
            else _missing(
                "persistra.metric.holding_period",
                "days",
                0,
                "analysis.closed_lots.missing",
            )
        ),
        _metric(
            "persistra.metric.concentration",
            concentration,
            "ratio",
            concentration_count,
        ),
        *cost_results,
        (
            _metric(
                "persistra.metric.participation_mean",
                float(np.mean(participation)) if participation.size else None,
                "ratio",
                int(participation.size),
            )
            if inputs.eligible_volume_by_fill is not None
            else _missing(
                "persistra.metric.participation_mean",
                "ratio",
                0,
                "analysis.eligible_volume.missing",
            )
        ),
        (
            _metric(
                "persistra.metric.participation_p95",
                float(np.quantile(participation, 0.95))
                if participation.size
                else None,
                "ratio",
                int(participation.size),
            )
            if inputs.eligible_volume_by_fill is not None
            else _missing(
                "persistra.metric.participation_p95",
                "ratio",
                0,
                "analysis.eligible_volume.missing",
            )
        ),
    )
    fixed_names = tuple(
        result.metric_name
        for result in results
        if not result.metric_name.startswith("persistra.metric.cost_total.")
        and not result.metric_name.startswith("persistra.metric.cost_total_relative.")
    )
    if fixed_names != _STANDARD_METRIC_NAMES:
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
    "persistra.metric.cost_total_relative",
    "persistra.metric.participation_mean",
    "persistra.metric.participation_p95",
)


def _validate_alignment(inputs: MetricInputs, count: int, fill_count: int) -> None:
    """Reject a supplied metric input series that has an incorrect length."""
    if inputs.risk_free_returns is not None and len(inputs.risk_free_returns) != count:
        raise AnalysisInputError(
            "risk-free return series does not align with computed returns",
            context={"expected": count, "received": len(inputs.risk_free_returns)},
        )
    if inputs.benchmark_returns is not None and len(inputs.benchmark_returns) != count:
        raise AnalysisInputError(
            "benchmark return series does not align with computed returns",
            context={"expected": count, "received": len(inputs.benchmark_returns)},
        )
    if (
        inputs.eligible_volume_by_fill is not None
        and len(inputs.eligible_volume_by_fill) != fill_count
    ):
        raise AnalysisInputError(
            "eligible volume series does not align with fills",
            context={
                "expected": fill_count,
                "received": len(inputs.eligible_volume_by_fill),
            },
        )


def _money_weighted_return(
    equity: pd.DataFrame, cash_flows: pd.DataFrame | None
) -> float | None:
    if len(equity) < 2:
        return None
    start_at = pd.Timestamp(equity.iloc[0]["valued_at"])
    end_at = pd.Timestamp(equity.iloc[-1]["valued_at"])
    elapsed = (end_at - start_at).total_seconds()
    initial = float(equity.iloc[0]["nav_usd"])
    terminal = float(equity.iloc[-1]["nav_usd"])
    if elapsed <= 0 or initial <= 0 or terminal < 0:
        return None
    dated = [(0.0, -initial), (elapsed / _YEAR_SECONDS, terminal)]
    if cash_flows is not None and not cash_flows.empty:
        for row in cash_flows.itertuples(index=False):
            effective_at = pd.Timestamp(cast("Any", row.effective_at))
            if effective_at <= start_at or effective_at >= end_at:
                continue
            years = (effective_at - start_at).total_seconds() / _YEAR_SECONDS
            dated.append((years, -float(cast("Any", row.amount_usd))))

    flow_years = np.asarray([years for years, _ in dated])
    flow_amounts = np.asarray([amount for _, amount in dated])

    def value(rate: float) -> float:
        return float(np.sum(flow_amounts / (1.0 + rate) ** flow_years))

    lower = -0.999999999
    upper = 1.0
    lower_value = value(lower)
    upper_value = value(upper)
    for _ in range(64):
        if lower_value == 0:
            return lower
        if upper_value == 0:
            return upper
        if lower_value * upper_value < 0:
            break
        upper = upper * 2 + 1
        upper_value = value(upper)
    else:
        return None
    for _ in range(128):
        middle = (lower + upper) / 2
        middle_value = value(middle)
        if abs(middle_value) <= 1e-12 * max(initial, terminal, 1.0):
            return middle
        if lower_value * middle_value <= 0:
            upper = middle
        else:
            lower = middle
            lower_value = middle_value
    return (lower + upper) / 2


def _catalog_order(result: MetricResult) -> tuple[int, str]:
    """Use fixed catalog order. Keep each component row next to its base row."""
    name = result.metric_name
    base = name
    for prefix in (
        "persistra.metric.cost_total_relative.",
        "persistra.metric.cost_total.",
    ):
        if name.startswith(prefix):
            base = prefix[:-1]
            break
    try:
        position = _STANDARD_METRIC_NAMES.index(base)
    except ValueError:
        position = len(_STANDARD_METRIC_NAMES)
    return (position, name)


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
        loaded = tuple(
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
        return tuple(sorted(loaded, key=_catalog_order))

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
        run_record_id: RunRecordId | None = None,
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
