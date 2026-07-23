"""This module contains the immutable execution, attribution, comparison, and scenario analyses."""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.analysis.models import AnalysisArtifactId, TabularAnalysisRef
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    AnalysisUnavailableError,
    CapabilityUnavailableError,
    ResultQueryLimitError,
)

if TYPE_CHECKING:
    from persistra.analysis.services import MetricService, MetricsHandle
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.results.services import RunHandle


class AdvancedAnalysisService:
    """This class computes normalized execution, attribution, comparison, and scenario artifacts."""

    __slots__ = ("_metrics", "_project")

    def __init__(self, project: Project, metrics: MetricService) -> None:
        self._project = project
        self._metrics = metrics

    def execution(self, run: RunHandle) -> TabularAnalysisHandle:
        fills = run.fills()
        costs = run.costs()
        targets = run.targets()
        filled_notional = sum(
            float(cast("Any", row.quantity))
            * float(cast("Any", row.fill_price_usd))
            for row in fills.itertuples(index=False)
        )
        target_quantity = sum(
            abs(float(value))
            for value in targets["target_quantity"]
            if pd.notna(value)
        )
        shortfall = sum(
            abs(float(value))
            for value in targets["shortfall_quantity"]
            if pd.notna(value)
        )
        rows = (
            ("execution", "fill_count", float(len(fills)), "count", "computed", None),
            ("execution", "filled_notional", filled_notional, "USD", "computed", None),
            (
                "execution",
                "direct_cost",
                sum(
                    float(cast("Any", row.amount_usd))
                    for row in costs.itertuples(index=False)
                    if row.state == "observed"
                ),
                "USD",
                "computed",
                None,
            ),
            (
                "execution",
                "modeled_cost",
                sum(
                    float(cast("Any", row.amount_usd))
                    for row in costs.itertuples(index=False)
                    if row.state == "modeled"
                ),
                "USD",
                "computed",
                None,
            ),
            (
                "capacity",
                "shortfall_rate",
                None if target_quantity == 0 else shortfall / target_quantity,
                "rate",
                "undefined" if target_quantity == 0 else "computed",
                "analysis.target.zero" if target_quantity == 0 else None,
            ),
        )
        return self._publish("execution", (run,), rows)

    def attribution(self, run: RunHandle) -> TabularAnalysisHandle:
        equity = run.equity()
        costs = run.costs()
        pnl = (
            float(equity.iloc[-1]["nav_usd"] - equity.iloc[0]["nav_usd"])
            if len(equity) >= 2
            else None
        )
        total_cost = sum(float(value) for value in costs["amount_usd"])
        rows = (
            (
                "attribution",
                "net_pnl",
                pnl,
                "USD",
                "computed" if pnl is not None else "undefined",
                None if pnl is not None else "analysis.observations.insufficient",
            ),
            ("attribution", "trading_cost", -total_cost, "USD", "computed", None),
            (
                "attribution",
                "gross_before_cost",
                None if pnl is None else pnl + total_cost,
                "USD",
                "computed" if pnl is not None else "undefined",
                None if pnl is not None else "analysis.observations.insufficient",
            ),
            (
                "attribution",
                "reconciliation_residual",
                0.0 if pnl is not None else None,
                "USD",
                "computed" if pnl is not None else "undefined",
                None if pnl is not None else "analysis.observations.insufficient",
            ),
        )
        return self._publish("attribution", (run,), rows)

    def compare(
        self,
        left: RunHandle,
        right: RunHandle,
        *,
        allow_warned: bool = False,
    ) -> TabularAnalysisHandle:
        differences: list[str] = []
        if left.fidelity() != right.fidelity():
            differences.append("fidelity")
        if left.summary().execution_content_id != right.summary().execution_content_id:
            differences.append("execution")
        compatibility = (
            "compatible"
            if not differences
            else "warned"
            if allow_warned
            else "incompatible"
        )
        if compatibility == "incompatible":
            raise AnalysisUnavailableError(
                "comparison is incompatible; pass allow_warned=True to retain warnings"
            )
        left_metrics = {item.metric_name: item for item in self._metrics.compute(left).results()}
        right_metrics = {
            item.metric_name: item for item in self._metrics.compute(right).results()
        }
        rows: list[tuple[str, str, float | None, str, str, str | None]] = []
        for name in sorted(set(left_metrics) & set(right_metrics)):
            left_value = left_metrics[name]
            right_value = right_metrics[name]
            left_estimate = left_value.estimate
            right_estimate = right_value.estimate
            computed = left_estimate is not None and right_estimate is not None
            delta = (
                right_estimate - left_estimate
                if right_estimate is not None and left_estimate is not None
                else None
            )
            rows.append(
                (
                    "comparison_delta",
                    name,
                    delta,
                    left_value.unit,
                    "computed" if computed else "undefined",
                    None if computed else "analysis.metric.unavailable",
                )
            )
        handle = self._publish(
            "comparison",
            (left, right),
            tuple(rows),
            compatibility_state=compatibility,
        )
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        warning = (
            None
            if not differences
            else str(
                scoped_content_id(
                    {
                        "schema": "persistra.analysis.comparison_warning@1",
                        "left": left.summary().result_manifest_content_id,
                        "right": right.summary().result_manifest_content_id,
                        "differences": differences,
                    }
                )
            )
        )
        connection.execute(
            "INSERT OR IGNORE INTO analysis.comparison_decisions VALUES (?, ?, ?, ?, ?, ?)",
            [
                handle.reference.analysis_artifact_id.value,
                left.id.value,
                right.id.value,
                compatibility,
                json.dumps(differences),
                warning,
            ],
        )
        return handle

    def scenarios(
        self, metrics: tuple[MetricsHandle, ...]
    ) -> TabularAnalysisHandle:
        if not metrics:
            raise AnalysisUnavailableError("scenario aggregation requires metrics")
        runs = tuple(
            self._project.services.results.get(  # pyright: ignore[reportUnknownMemberType]
                self._artifact_run_id(item.reference.analysis_artifact_id)
            )
            for item in metrics
        )
        grouped: dict[str, list[float]] = {}
        units: dict[str, str] = {}
        for handle in metrics:
            for result in handle.results():
                if result.estimate is not None:
                    grouped.setdefault(result.metric_name, []).append(result.estimate)
                    units[result.metric_name] = result.unit
        rows: list[tuple[str, str, float | None, str, str, str | None]] = []
        for name, values in sorted(grouped.items()):
            for aggregation, estimate in (
                ("mean", statistics.mean(values)),
                ("minimum", min(values)),
                ("maximum", max(values)),
            ):
                rows.append(
                    (
                        "scenario",
                        f"{name}.{aggregation}",
                        estimate,
                        units[name],
                        "computed",
                        None,
                    )
                )
        return self._publish("scenario", runs, tuple(rows))

    def _artifact_run_id(self, artifact_id: AnalysisArtifactId) -> Any:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT run_record_id FROM analysis.artifacts WHERE analysis_artifact_id = ?",
            [artifact_id.value],
        ).fetchone()
        if row is None:
            raise AnalysisUnavailableError("analysis artifact is missing")
        from persistra.simulation.models import RunRecordId

        return RunRecordId.parse(row[0])

    def _publish(
        self,
        kind: str,
        runs: tuple[RunHandle, ...],
        rows: tuple[tuple[str, str, float | None, str, str, str | None], ...],
        *,
        compatibility_state: str | None = None,
    ) -> TabularAnalysisHandle:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("analysis requires research_write mode")
        execution = scoped_content_id(
            {
                "schema": "persistra.analysis.tabular_execution@1",
                "kind": kind,
                "inputs": tuple(run.summary().result_manifest_content_id for run in runs),
                "compatibility": compatibility_state,
            }
        )
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        existing = connection.execute(
            "SELECT analysis_artifact_id, output_content_id FROM analysis.artifacts "
            "WHERE execution_content_id = ?",
            [str(execution)],
        ).fetchone()
        if existing is not None:
            return TabularAnalysisHandle(
                self._project,
                TabularAnalysisRef(
                    AnalysisArtifactId.parse(existing[0]),
                    kind,
                    execution,
                    ContentId.parse(existing[1]),
                    compatibility_state,
                ),
            )
        output = scoped_content_id(
            {
                "schema": "persistra.analysis.tabular_output@1",
                "execution": execution,
                "rows": rows,
            }
        )

        def operation(context: TransactionContext) -> TabularAnalysisHandle:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            artifact_id = AnalysisArtifactId.new()
            active.execute(
                "INSERT INTO analysis.artifacts VALUES (?, ?, ?, ?, ?, ?)",
                [
                    artifact_id.value,
                    kind,
                    runs[0].id.value,
                    str(execution),
                    str(output),
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO analysis_data.tabular_results VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        artifact_id.value,
                        ordinal,
                        category,
                        name,
                        estimate,
                        state,
                        unit,
                        reason,
                        str(
                            scoped_content_id(
                                {
                                    "schema": "persistra.analysis.tabular_row@1",
                                    "artifact": artifact_id,
                                    "ordinal": ordinal,
                                    "row": row,
                                }
                            )
                        ),
                    )
                    for ordinal, row in enumerate(rows, 1)
                    for category, name, estimate, unit, state, reason in (row,)
                ],
            )
            return TabularAnalysisHandle(
                self._project,
                TabularAnalysisRef(
                    artifact_id,
                    kind,
                    execution,
                    output,
                    compatibility_state,
                ),
            )

        return self._project.services.transactions.run("analysis_tabular_compute", operation)


@dataclass(frozen=True, slots=True)
class TabularAnalysisHandle:
    _project: Project
    reference: TabularAnalysisRef

    def results(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        if max_rows <= 0:
            raise ResultQueryLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT row_ordinal, category, name, estimate, state, unit, "
            "reason_code, source_content_id FROM analysis_data.tabular_results "
            "WHERE analysis_artifact_id = ? ORDER BY row_ordinal LIMIT ?",
            [self.reference.analysis_artifact_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResultQueryLimitError("analysis rows exceed max_rows")
        return frame
