"""Immutable finance-aware temporal validation plans."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.catalog.services import insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CapabilityUnavailableError,
    ResearchResultLimitError,
    ValidationPlanError,
    ValidationSchemeError,
)
from persistra.research.models import ResearchDatasetBuildId
from persistra.research.validation import (
    DecisionWidth,
    EligibilityPolicy,
    LeakageScope,
    ResolvedValidationSchemeRef,
    ValidationInputSpec,
    ValidationPlanId,
    ValidationPlanRef,
    ValidationRole,
    ValidationSampleState,
    ValidationSchemeDefinition,
    ValidationSchemeId,
    ValidationSchemeKind,
    ValidationSchemeRef,
)

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project


def _decode_definition(text: str) -> ValidationSchemeDefinition:
    value = cast("dict[str, Any]", json.loads(text))
    rolling = value["rolling_train_width"]
    embargo = value["embargo"]
    return ValidationSchemeDefinition(
        QualifiedName(value["name"]),
        int(value["version"]),
        ValidationSchemeKind(value["kind"]),
        DecisionWidth(int(value["minimum_train"]["decisions"])),
        DecisionWidth(int(value["test_width"]["decisions"])),
        DecisionWidth(int(value["step_width"]["decisions"])),
        None if rolling is None else DecisionWidth(int(rolling["decisions"])),
        None if embargo is None else DecisionWidth(int(embargo["decisions"])),
    )


class ValidationService:
    """Register schemes and resolve exact purged memberships."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: ValidationSchemeDefinition
    ) -> ResolvedValidationSchemeRef:
        self._require_write()
        encoded = canonical_bytes(definition)
        content_id = scoped_content_id(
            {"schema": "persistra.validation.scheme_definition", "value": definition}
        )

        def operation(context: TransactionContext) -> ResolvedValidationSchemeRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT s.validation_scheme_id, v.definition_content_id, "
                "v.definition_json FROM analysis.validation_schemes s JOIN "
                "analysis.validation_scheme_versions v USING (validation_scheme_id) "
                "WHERE s.qualified_name = ? AND v.definition_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id) or existing[2] != encoded.decode():
                    raise ValidationSchemeError("validation scheme version conflicts")
                return ResolvedValidationSchemeRef(
                    ValidationSchemeId.parse(existing[0]),
                    definition.version,
                    content_id,
                )
            prior = connection.execute(
                "SELECT s.validation_scheme_id, max(v.definition_version) FROM "
                "analysis.validation_schemes s LEFT JOIN "
                "analysis.validation_scheme_versions v USING (validation_scheme_id) "
                "WHERE s.qualified_name = ? GROUP BY s.validation_scheme_id",
                [str(definition.name)],
            ).fetchone()
            if prior is None:
                if definition.version != 1:
                    raise ValidationSchemeError(
                        "first validation scheme version must be one"
                    )
                scheme_id = ValidationSchemeId.new()
                connection.execute(
                    "INSERT INTO analysis.validation_schemes VALUES (?, ?, ?)",
                    [scheme_id.value, str(definition.name), context.recorded_at],
                )
            else:
                scheme_id = ValidationSchemeId.parse(prior[0])
                if definition.version != int(prior[1]) + 1:
                    raise ValidationSchemeError(
                        "validation scheme versions must be contiguous"
                    )
            connection.execute(
                "INSERT INTO analysis.validation_scheme_versions VALUES "
                "(?, ?, ?, ?, ?)",
                [
                    scheme_id.value,
                    definition.version,
                    str(content_id),
                    encoded.decode(),
                    context.recorded_at,
                ],
            )
            insert_event(
                connection,
                event_name="persistra.validation.scheme_registered",
                aggregate_kind="persistra.aggregate.validation_scheme",
                aggregate_id=scheme_id,
                aggregate_sequence=definition.version,
                recorded_at=context.recorded_at,
                payload={"definition_content_id": content_id},
            )
            return ResolvedValidationSchemeRef(
                scheme_id, definition.version, content_id
            )

        return self._project.services.transactions.run(
            "validation_scheme_register", operation
        )

    def create_plan(
        self, *, scheme: ValidationSchemeRef, input_spec: ValidationInputSpec
    ) -> ValidationPlan:
        self._require_write()
        resolved, definition = self._resolve(scheme)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        build = connection.execute(
            "SELECT b.output_relation_name, b.output_manifest_content_id, "
            "e.dataset_role, e.information_class FROM "
            "research.research_dataset_builds b JOIN "
            "research.research_dataset_enrichments e "
            "USING (research_dataset_build_id) WHERE research_dataset_build_id = ?",
            [input_spec.research_dataset_build_id.value],
        ).fetchone()
        if build is None or build[2] != "analysis" or build[3] != "label":
            raise ValidationPlanError(
                "validation requires an exact label-classified analysis dataset"
            )
        relation = str(build[0]).replace('"', '""')
        frame = cast(
            "pd.DataFrame",
            connection.execute(
                f'SELECT * FROM research_data."{relation}" '
                "ORDER BY decision_at, instrument_id"
            ).fetchdf(),
        )
        memberships = _build_memberships(definition, input_spec, frame)
        if not memberships:
            raise ValidationPlanError("validation scheme produced no folds")
        membership_content_id = scoped_content_id(
            {
                "schema": "persistra.validation.membership",
                "rows": tuple(
                    {
                        **row,
                        "decision_at": pd.Timestamp(
                            cast("Any", row["decision_at"])
                        ).to_pydatetime(),
                        "instrument_id": str(row["instrument_id"]),
                        "label_start_at": (
                            None
                            if pd.isna(cast("Any", row["label_start_at"]))
                            else pd.Timestamp(
                                cast("Any", row["label_start_at"])
                            ).to_pydatetime()
                        ),
                        "label_end_at": (
                            None
                            if pd.isna(cast("Any", row["label_end_at"]))
                            else pd.Timestamp(
                                cast("Any", row["label_end_at"])
                            ).to_pydatetime()
                        ),
                    }
                    for row in memberships
                ),
            }
        )
        execution_content_id = scoped_content_id(
            {
                "schema": "persistra.validation.plan_execution",
                "scheme": resolved,
                "input": input_spec,
                "dataset_manifest": ContentId.parse(build[1]),
                "membership": membership_content_id,
            }
        )
        fold_count = (
            max(int(cast("Any", row["fold_index"])) for row in memberships) + 1
        )
        purged_count = sum(row["reason_code"] == "validation.purged.overlap" for row in memberships)
        embargoed_count = sum(
            row["reason_code"] == "validation.embargo.excluded"
            for row in memberships
        )

        def operation(context: TransactionContext) -> ValidationPlan:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = active.execute(
                "SELECT validation_plan_id FROM analysis.validation_plans "
                "WHERE execution_content_id = ?",
                [str(execution_content_id)],
            ).fetchone()
            if existing is not None:
                return self.get(ValidationPlanId.parse(existing[0]))
            plan_id = ValidationPlanId.new()
            active.execute(
                "INSERT INTO analysis.validation_plans VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    plan_id.value,
                    resolved.validation_scheme_id.value,
                    resolved.version,
                    input_spec.research_dataset_build_id.value,
                    str(execution_content_id),
                    str(membership_content_id),
                    fold_count,
                    len(frame),
                    purged_count,
                    embargoed_count,
                    context.recorded_at,
                ],
            )
            active.executemany(
                "INSERT INTO analysis.validation_membership VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        plan_id.value,
                        row["fold_index"],
                        row["decision_at"],
                        row["instrument_id"],
                        row["validation_role"],
                        row["sample_state"],
                        row["reason_code"],
                        row["label_start_at"],
                        row["label_end_at"],
                    )
                    for row in memberships
                ],
            )
            insert_event(
                active,
                event_name="persistra.validation.plan_completed",
                aggregate_kind="persistra.aggregate.validation_plan",
                aggregate_id=plan_id,
                aggregate_sequence=1,
                recorded_at=context.recorded_at,
                payload={"membership_content_id": membership_content_id},
            )
            return self.get(plan_id)

        return self._project.services.transactions.run(
            "validation_plan_create", operation
        )

    def get(self, plan_id: ValidationPlanId) -> ValidationPlan:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT validation_scheme_id, definition_version, "
            "research_dataset_build_id, execution_content_id, membership_content_id, "
            "fold_count, sample_count, purged_count, embargoed_count FROM "
            "analysis.validation_plans WHERE validation_plan_id = ?",
            [plan_id.value],
        ).fetchone()
        if row is None:
            raise ValidationPlanError("validation plan is unavailable")
        return ValidationPlan(
            self._project,
            ValidationPlanRef(
                plan_id,
                ValidationSchemeId.parse(row[0]),
                int(row[1]),
                ResearchDatasetBuildId.parse(row[2]),
                ContentId.parse(row[3]),
                ContentId.parse(row[4]),
                int(row[5]),
                int(row[6]),
                int(row[7]),
                int(row[8]),
            ),
        )

    def _resolve(
        self, reference: ValidationSchemeRef
    ) -> tuple[ResolvedValidationSchemeRef, ValidationSchemeDefinition]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT s.validation_scheme_id, v.definition_content_id, "
            "v.definition_json FROM analysis.validation_schemes s JOIN "
            "analysis.validation_scheme_versions v USING (validation_scheme_id) "
            "WHERE s.qualified_name = ? AND v.definition_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise ValidationSchemeError("validation scheme is unavailable")
        return (
            ResolvedValidationSchemeRef(
                ValidationSchemeId.parse(row[0]),
                reference.version,
                ContentId.parse(row[1]),
            ),
            _decode_definition(row[2]),
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "validation mutations require research_write mode"
            )


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    _project: Project
    reference: ValidationPlanRef

    def membership(
        self, *, fold_index: int | None = None, max_rows: int = 2_000_000
    ) -> pd.DataFrame:
        if max_rows < 1:
            raise ResearchResultLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        clause = "" if fold_index is None else " AND fold_index = ?"
        parameters: list[object] = [self.reference.validation_plan_id.value]
        if fold_index is not None:
            parameters.append(fold_index)
        parameters.append(max_rows + 1)
        frame = cast(
            "pd.DataFrame",
            connection.execute(
                "SELECT * FROM analysis.validation_membership "
                f"WHERE validation_plan_id = ?{clause} "
                "ORDER BY fold_index, decision_at, instrument_id LIMIT ?",
                parameters,
            ).fetchdf(),
        )
        if len(frame) > max_rows:
            raise ResearchResultLimitError("validation membership exceeds max_rows")
        return frame


def _build_memberships(
    definition: ValidationSchemeDefinition,
    input_spec: ValidationInputSpec,
    frame: pd.DataFrame,
) -> list[dict[str, object]]:
    decisions = sorted(pd.Timestamp(value) for value in frame["decision_at"].unique())
    minimum = definition.minimum_train.decisions
    test_width = definition.test_width.decisions
    step = definition.step_width.decisions
    folds: list[tuple[set[pd.Timestamp], set[pd.Timestamp]]] = []
    test_start = minimum
    while test_start + test_width <= len(decisions):
        train_start = 0
        if definition.kind is ValidationSchemeKind.ROLLING:
            assert definition.rolling_train_width is not None
            train_start = max(0, test_start - definition.rolling_train_width.decisions)
        folds.append(
            (
                set(decisions[train_start:test_start]),
                set(decisions[test_start : test_start + test_width]),
            )
        )
        test_start += step
    output: list[dict[str, object]] = []
    label = input_spec.label_output
    for fold_index, (train_decisions, test_decisions) in enumerate(folds):
        test_rows = frame[
            frame["decision_at"].map(pd.Timestamp).isin(test_decisions)
        ]
        records = cast("list[dict[str, Any]]", frame.to_dict("records"))
        for row in records:
            decision = pd.Timestamp(row["decision_at"])
            state, reason = _sample_state(row, input_spec)
            role = ValidationRole.EXCLUDED
            if state is ValidationSampleState.ELIGIBLE:
                if decision in test_decisions:
                    role = ValidationRole.TEST
                    reason = "validation.role.test"
                elif decision in train_decisions:
                    role = ValidationRole.TRAIN
                    reason = "validation.role.train"
                    if _overlaps_evaluation(row, test_rows, input_spec.leakage_scope, label):
                        role = ValidationRole.EXCLUDED
                        reason = "validation.purged.overlap"
            output.append(
                {
                    "fold_index": fold_index,
                    "decision_at": row["decision_at"],
                    "instrument_id": row["instrument_id"],
                    "validation_role": role.value,
                    "sample_state": state.value,
                    "reason_code": reason,
                    "label_start_at": row.get(f"{label}_label_start_at"),
                    "label_end_at": row.get(f"{label}_label_end_at"),
                }
            )
    return output


def _sample_state(
    row: dict[str, Any], input_spec: ValidationInputSpec
) -> tuple[ValidationSampleState, str]:
    label = input_spec.label_output
    if not bool(row.get("research_row_usable", True)):
        return ValidationSampleState.DATASET_UNUSABLE, "validation.dataset.unusable"
    if row.get(f"{label}_state") != "computed":
        return ValidationSampleState.LABEL_NONCOMPUTED, "validation.label.noncomputed"
    start = row.get(f"{label}_label_start_at")
    end = row.get(f"{label}_label_end_at")
    if pd.isna(start) or pd.isna(end):
        return ValidationSampleState.INTERVAL_MISSING, "validation.interval.missing"
    if pd.Timestamp(start) > pd.Timestamp(end):
        return ValidationSampleState.INTERVAL_INVALID, "validation.interval.invalid"
    if input_spec.eligibility_policy is EligibilityPolicy.COMPLETE_CASE and any(
        row.get(f"{feature}_state") != "computed"
        for feature in input_spec.feature_outputs
    ):
        return (
            ValidationSampleState.FEATURE_NONCOMPUTED,
            "validation.feature.noncomputed",
        )
    return ValidationSampleState.ELIGIBLE, "validation.sample.eligible"


def _overlaps_evaluation(
    candidate: dict[str, Any],
    evaluation: pd.DataFrame,
    scope: LeakageScope,
    label: str,
) -> bool:
    start = pd.Timestamp(candidate[f"{label}_label_start_at"])
    end = pd.Timestamp(candidate[f"{label}_label_end_at"])
    selected: pd.DataFrame = evaluation
    if scope is LeakageScope.ENTITY:
        selected = cast(
            "pd.DataFrame",
            evaluation[evaluation["instrument_id"] == candidate["instrument_id"]],
        )
    records = cast("list[dict[str, Any]]", selected.to_dict("records"))
    for row in records:
        other_start = row.get(f"{label}_label_start_at")
        other_end = row.get(f"{label}_label_end_at")
        if pd.isna(other_start) or pd.isna(other_end):
            continue
        if start <= pd.Timestamp(other_end) and pd.Timestamp(other_start) <= end:
            return True
    return False
