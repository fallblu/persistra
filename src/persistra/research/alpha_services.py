"""Immutable alpha diagnostics over exact feature/label analysis datasets."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.catalog.services import insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    AlphaAnalysisDefinitionError,
    AlphaExecutionError,
    CapabilityUnavailableError,
    ResearchResultLimitError,
)
from persistra.research.alpha import (
    AlphaAnalysisDefinition,
    AlphaAnalysisDefinitionId,
    AlphaAnalysisRef,
    AlphaAnalysisResultId,
    AlphaAnalysisResultRef,
    AlphaMetricKind,
    AlphaMetricResult,
    AnalysisIntent,
    InferenceKind,
    MetricValueState,
    PValueAdjustment,
    ResolvedAlphaAnalysisRef,
)
from persistra.research.models import ResearchDatasetBuildId

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project


@dataclass(frozen=True, slots=True)
class _Summary:
    feature: str
    label: str
    metric: str
    state: MetricValueState
    estimate: float | None
    standard_error: float | None
    statistic: float | None
    p_value: float | None
    adjusted_p_value: float | None
    count: int
    reason: str | None


def _decode_definition(text: str) -> AlphaAnalysisDefinition:
    value = cast("dict[str, Any]", json.loads(text))
    return AlphaAnalysisDefinition(
        QualifiedName(value["name"]),
        int(value["version"]),
        ResearchDatasetBuildId.parse(value["research_dataset_build_id"]),
        tuple(str(item) for item in value["feature_outputs"]),
        tuple(str(item) for item in value["label_outputs"]),
        tuple(AlphaMetricKind(item) for item in value["metrics"]),
        AnalysisIntent(value["intent"]),
        int(value["quantiles"]),
        InferenceKind(value["inference"]),
        PValueAdjustment(value["p_value_adjustment"]),
    )


class AlphaService:
    """Register and execute bounded cross-sectional alpha diagnostics."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: AlphaAnalysisDefinition
    ) -> ResolvedAlphaAnalysisRef:
        self._require_write()
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.alpha.definition", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedAlphaAnalysisRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT d.alpha_analysis_definition_id, v.definition_content_id, "
                "v.definition_json FROM analysis.alpha_definitions d JOIN "
                "analysis.alpha_definition_versions v "
                "USING (alpha_analysis_definition_id) WHERE d.qualified_name = ? "
                "AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise AlphaAnalysisDefinitionError(
                        "alpha definition version conflicts"
                    )
                return ResolvedAlphaAnalysisRef(
                    AlphaAnalysisDefinitionId.parse(existing[0]),
                    definition.version,
                    content_id,
                )
            prior = connection.execute(
                "SELECT d.alpha_analysis_definition_id, "
                "max(v.definition_version) FROM analysis.alpha_definitions d "
                "LEFT JOIN analysis.alpha_definition_versions v "
                "USING (alpha_analysis_definition_id) WHERE d.qualified_name = ? "
                "GROUP BY d.alpha_analysis_definition_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise AlphaAnalysisDefinitionError(
                        "first alpha definition version must be one"
                    )
                definition_id = AlphaAnalysisDefinitionId.new()
                connection.execute(
                    "INSERT INTO analysis.alpha_definitions VALUES (?, ?, ?)",
                    [definition_id.value, str(definition.name), context.recorded_at],
                )
            else:
                definition_id = AlphaAnalysisDefinitionId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise AlphaAnalysisDefinitionError(
                        "alpha definition versions must be contiguous"
                    )
            connection.execute(
                "INSERT INTO analysis.alpha_definition_versions VALUES "
                "(?, ?, ?, ?, ?)",
                [
                    definition_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            insert_event(
                connection,
                event_name="persistra.alpha.definition_registered",
                aggregate_kind="persistra.aggregate.alpha_analysis_definition",
                aggregate_id=definition_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,
                payload={"definition_content_id": content_id},
            )
            return ResolvedAlphaAnalysisRef(
                definition_id, definition.version, content_id
            )

        return self._project.services.transactions.run(
            "alpha_definition_register", operation
        )

    def execute(self, reference: AlphaAnalysisRef) -> AlphaAnalysisResult:
        self._require_write()
        resolved, definition = self._resolve(reference)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        build = connection.execute(
            "SELECT b.output_relation_name, b.output_manifest_content_id, "
            "e.dataset_role, e.information_class FROM "
            "research.research_dataset_builds b JOIN "
            "research.research_dataset_enrichments e "
            "USING (research_dataset_build_id) WHERE research_dataset_build_id = ?",
            [definition.research_dataset_build_id.value],
        ).fetchone()
        if build is None or build[2] != "analysis" or build[3] != "label":
            raise AlphaExecutionError(
                "alpha execution requires a label-classified analysis dataset"
            )
        relation = str(build[0]).replace('"', '""')
        frame = cast(
            "pd.DataFrame",
            connection.execute(
                f'SELECT * FROM research_data."{relation}" '
                "ORDER BY decision_at, instrument_id"
            ).fetchdf(),
        )
        raw, summaries = _compute(definition, frame)
        output_content_id = scoped_content_id(
            {
                "schema": "persistra.alpha.output",
                "raw": tuple(_identity_row(row) for row in raw),
                "summaries": tuple(_identity_summary(item) for item in summaries),
            }
        )
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.alpha.execution",
                "definition": resolved,
                "dataset_manifest": ContentId.parse(build[1]),
                "output": output_content_id,
            }
        )

        def operation(context: TransactionContext) -> AlphaAnalysisResult:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT alpha_analysis_result_id FROM analysis.alpha_results "
                "WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return self.get(AlphaAnalysisResultId.parse(existing[0]))
            result_id = AlphaAnalysisResultId.new()
            active.execute(
                "INSERT INTO analysis.alpha_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    result_id.value,
                    resolved.alpha_analysis_definition_id.value,
                    resolved.version,
                    definition.research_dataset_build_id.value,
                    str(execution_content_id),
                    str(output_content_id),
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO analysis.alpha_metric_results VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        result_id.value,
                        row["feature_name"],
                        row["label_name"],
                        row["metric_kind"],
                        row["decision_at"],
                        row["metric_state"],
                        row["estimate"],
                        row["observation_count"],
                        row["reason_code"],
                    )
                    for row in raw
                ],
            )
            active.executemany(
                "INSERT INTO analysis.alpha_summary_results VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        result_id.value,
                        item.feature,
                        item.label,
                        item.metric,
                        item.state.value,
                        item.estimate,
                        item.standard_error,
                        item.statistic,
                        item.p_value,
                        item.adjusted_p_value,
                        item.count,
                        item.reason,
                    )
                    for item in summaries
                ],
            )
            insert_event(
                active,
                event_name="persistra.alpha.result_completed",
                aggregate_kind="persistra.aggregate.alpha_analysis_result",
                aggregate_id=result_id,
                aggregate_sequence=1,
                recorded_at=context.recorded_at,
                payload={"output_content_id": output_content_id},
            )
            return self.get(result_id)

        return self._project.services.transactions.run("alpha_execute", operation)

    def get(self, result_id: AlphaAnalysisResultId) -> AlphaAnalysisResult:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT alpha_analysis_definition_id, definition_version, "
            "research_dataset_build_id, execution_content_id, output_content_id "
            "FROM analysis.alpha_results WHERE alpha_analysis_result_id = ?",
            [result_id.value],
        ).fetchone()
        if row is None:
            raise AlphaExecutionError("alpha result is unavailable")
        return AlphaAnalysisResult(
            self._project,
            AlphaAnalysisResultRef(
                result_id,
                AlphaAnalysisDefinitionId.parse(row[0]),
                int(row[1]),
                ResearchDatasetBuildId.parse(row[2]),
                ContentId.parse(row[3]),
                ContentId.parse(row[4]),
            ),
        )

    def _resolve(
        self, reference: AlphaAnalysisRef
    ) -> tuple[ResolvedAlphaAnalysisRef, AlphaAnalysisDefinition]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT d.alpha_analysis_definition_id, v.definition_content_id, "
            "v.definition_json FROM analysis.alpha_definitions d JOIN "
            "analysis.alpha_definition_versions v "
            "USING (alpha_analysis_definition_id) WHERE d.qualified_name = ? "
            "AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise AlphaAnalysisDefinitionError("alpha definition is unavailable")
        return (
            ResolvedAlphaAnalysisRef(
                AlphaAnalysisDefinitionId.parse(row[0]),
                reference.version,
                ContentId.parse(row[1]),
            ),
            _decode_definition(row[2]),
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "alpha mutations require research_write mode"
            )


@dataclass(frozen=True, slots=True)
class AlphaAnalysisResult:
    _project: Project
    reference: AlphaAnalysisResultRef

    def series(self, *, max_rows: int = 2_000_000) -> pd.DataFrame:
        if max_rows < 1:
            raise ResearchResultLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = cast(
            "pd.DataFrame",
            connection.execute(
                "SELECT * FROM analysis.alpha_metric_results "
                "WHERE alpha_analysis_result_id = ? "
                "ORDER BY feature_name, label_name, metric_kind, decision_at LIMIT ?",
                [self.reference.alpha_analysis_result_id.value, max_rows + 1],
            ).fetchdf(),
        )
        if len(frame) > max_rows:
            raise ResearchResultLimitError("alpha series exceed max_rows")
        return frame

    def summaries(self) -> tuple[AlphaMetricResult, ...]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT feature_name, label_name, metric_kind, metric_state, estimate, "
            "observation_count, reason_code FROM analysis.alpha_summary_results "
            "WHERE alpha_analysis_result_id = ? "
            "ORDER BY feature_name, label_name, metric_kind",
            [self.reference.alpha_analysis_result_id.value],
        ).fetchall()
        return tuple(
            AlphaMetricResult(
                row[0],
                row[1],
                row[2],
                MetricValueState(row[3]),
                None if row[4] is None else float(row[4]),
                int(row[5]),
                row[6],
            )
            for row in rows
        )


def _compute(
    definition: AlphaAnalysisDefinition, frame: pd.DataFrame
) -> tuple[list[dict[str, object]], tuple[_Summary, ...]]:
    raw: list[dict[str, object]] = []
    summaries: list[_Summary] = []
    for feature in definition.feature_outputs:
        for label in definition.label_outputs:
            required = {
                feature,
                f"{feature}_state",
                label,
                f"{label}_state",
                "decision_at",
            }
            if not required.issubset(frame.columns):
                raise AlphaExecutionError(
                    f"alpha input {feature!r}/{label!r} is unavailable"
                )
            for metric in definition.metrics:
                values: list[float] = []
                for decision, group in frame.groupby("decision_at", sort=True):
                    result = _decision_metric(
                        group, feature, label, metric, definition.quantiles
                    )
                    raw.append(
                        {
                            "feature_name": feature,
                            "label_name": label,
                            "metric_kind": metric.value,
                            "decision_at": pd.Timestamp(
                                cast("Any", decision)
                            ).to_pydatetime(),
                            "metric_state": result.state.value,
                            "estimate": result.estimate,
                            "observation_count": result.observation_count,
                            "reason_code": result.reason_code,
                        }
                    )
                    if result.estimate is not None:
                        values.append(result.estimate)
                summaries.append(
                    _summarize(
                        feature,
                        label,
                        metric.value,
                        values,
                        definition.inference,
                    )
                )
    adjusted = _adjust(tuple(summaries), definition.p_value_adjustment)
    return raw, adjusted


def _decision_metric(
    group: pd.DataFrame,
    feature: str,
    label: str,
    metric: AlphaMetricKind,
    quantiles: int,
) -> AlphaMetricResult:
    usable = group[
        (group[f"{feature}_state"] == "computed")
        & (group[f"{label}_state"] == "computed")
    ][[feature, label]].dropna()
    count = len(usable)
    if metric is AlphaMetricKind.COVERAGE:
        denominator = len(group)
        estimate = count / denominator if denominator else None
        return AlphaMetricResult(
            feature,
            label,
            metric.value,
            MetricValueState.COMPUTED
            if estimate is not None
            else MetricValueState.EMPTY_MEMBERSHIP,
            estimate,
            count,
            None if estimate is not None else "alpha.membership.empty",
        )
    if count < 2:
        return AlphaMetricResult(
            feature,
            label,
            metric.value,
            MetricValueState.INSUFFICIENT_OBSERVATIONS,
            None,
            count,
            "alpha.observations.insufficient",
        )
    x = pd.to_numeric(usable[feature], errors="coerce")
    y = pd.to_numeric(usable[label], errors="coerce")
    if metric in {AlphaMetricKind.PEARSON_IC, AlphaMetricKind.SPEARMAN_IC}:
        if metric is AlphaMetricKind.SPEARMAN_IC:
            x = x.rank(method="average")
            y = y.rank(method="average")
        if float(x.std(ddof=0)) == 0 or float(y.std(ddof=0)) == 0:
            return AlphaMetricResult(
                feature,
                label,
                metric.value,
                MetricValueState.ZERO_DISPERSION,
                None,
                count,
                "alpha.dispersion.zero",
            )
        estimate = float(x.corr(y))
    else:
        if count < quantiles:
            return AlphaMetricResult(
                feature,
                label,
                metric.value,
                MetricValueState.INSUFFICIENT_OBSERVATIONS,
                None,
                count,
                "alpha.quantile.membership_insufficient",
            )
        buckets = pd.qcut(
            x.rank(method="first"), quantiles, labels=False, duplicates="drop"
        )
        means = y.groupby(buckets).mean()
        if len(means) != quantiles:
            return AlphaMetricResult(
                feature,
                label,
                metric.value,
                MetricValueState.INSUFFICIENT_OBSERVATIONS,
                None,
                count,
                "alpha.quantile.membership_insufficient",
            )
        if metric is AlphaMetricKind.QUANTILE_LABELS:
            estimate = float(means.iloc[-1] - means.iloc[0])
        else:
            estimate = float(
                pd.Series(range(quantiles), dtype="float64").corr(
                    means.reset_index(drop=True)
                )
            )
    if not math.isfinite(estimate):
        return AlphaMetricResult(
            feature,
            label,
            metric.value,
            MetricValueState.INVALID_NUMERIC,
            None,
            count,
            "alpha.numeric.invalid",
        )
    return AlphaMetricResult(
        feature,
        label,
        metric.value,
        MetricValueState.COMPUTED,
        estimate,
        count,
        None,
    )


def _summarize(
    feature: str,
    label: str,
    metric: str,
    values: list[float],
    inference: InferenceKind,
) -> _Summary:
    count = len(values)
    if not values:
        return _Summary(
            feature,
            label,
            metric,
            MetricValueState.INSUFFICIENT_OBSERVATIONS,
            None,
            None,
            None,
            None,
            None,
            0,
            "alpha.observations.insufficient",
        )
    estimate = sum(values) / count
    if count < 2 or inference is InferenceKind.NONE:
        return _Summary(
            feature,
            label,
            metric,
            MetricValueState.COMPUTED,
            estimate,
            None,
            None,
            None,
            None,
            count,
            None,
        )
    centered = [value - estimate for value in values]
    lag = min(count - 1, max(1, int(4 * (count / 100) ** (2 / 9))))
    variance = sum(value * value for value in centered) / count
    for offset in range(1, lag + 1):
        covariance = sum(
            centered[index] * centered[index - offset]
            for index in range(offset, count)
        ) / count
        variance += 2 * (1 - offset / (lag + 1)) * covariance
    standard_error = math.sqrt(max(variance, 0.0) / count)
    statistic = estimate / standard_error if standard_error > 0 else None
    p_value = (
        math.erfc(abs(statistic) / math.sqrt(2))
        if statistic is not None
        else None
    )
    return _Summary(
        feature,
        label,
        metric,
        MetricValueState.COMPUTED,
        estimate,
        standard_error,
        statistic,
        p_value,
        None,
        count,
        None,
    )


def _adjust(
    summaries: tuple[_Summary, ...], adjustment: PValueAdjustment
) -> tuple[_Summary, ...]:
    indexed = [
        (index, item.p_value)
        for index, item in enumerate(summaries)
        if item.p_value is not None
    ]
    if adjustment is PValueAdjustment.NONE or not indexed:
        return tuple(
            _replace_summary(item, item.p_value) for item in summaries
        )
    ordered = sorted(indexed, key=lambda pair: pair[1])
    adjusted: dict[int, float] = {}
    total = len(ordered)
    if adjustment is PValueAdjustment.HOLM:
        running = 0.0
        for rank, (index, value) in enumerate(ordered):
            running = max(running, min(1.0, value * (total - rank)))
            adjusted[index] = running
    else:
        running = 1.0
        for reverse_rank in range(total - 1, -1, -1):
            index, value = ordered[reverse_rank]
            running = min(
                running,
                min(1.0, value * total / (reverse_rank + 1)),
            )
            adjusted[index] = running
    return tuple(
        _replace_summary(item, adjusted.get(index))
        for index, item in enumerate(summaries)
    )


def _replace_summary(item: _Summary, adjusted: float | None) -> _Summary:
    return _Summary(
        item.feature,
        item.label,
        item.metric,
        item.state,
        item.estimate,
        item.standard_error,
        item.statistic,
        item.p_value,
        adjusted,
        item.count,
        item.reason,
    )


def _identity_float(value: float | None) -> str | None:
    return None if value is None else value.hex()


def _identity_row(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "estimate": _identity_float(cast("float | None", row["estimate"])),
    }


def _identity_summary(item: _Summary) -> dict[str, object]:
    return {
        "feature": item.feature,
        "label": item.label,
        "metric": item.metric,
        "state": item.state,
        "estimate": _identity_float(item.estimate),
        "standard_error": _identity_float(item.standard_error),
        "statistic": _identity_float(item.statistic),
        "p_value": _identity_float(item.p_value),
        "adjusted_p_value": _identity_float(item.adjusted_p_value),
        "count": item.count,
        "reason": item.reason,
    }
