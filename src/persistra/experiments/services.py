"""Deterministic study planning, reuse, attempts, retry, and resume."""

from __future__ import annotations

import importlib.util
import itertools
import json
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from persistra._identity import identity_bytes
from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    CapabilityUnavailableError,
    ExperimentRequestError,
    ExperimentStateError,
    ResearchResultLimitError,
)
from persistra.experiments.models import (
    AttemptId,
    AttemptRef,
    AttemptState,
    ExperimentFoldId,
    ParameterSet,
    RunPlanId,
    ScenarioId,
    SearchKind,
    StudyId,
    StudyRef,
    StudyRequest,
    TrialId,
)

if TYPE_CHECKING:
    import pandas as pd

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project


class ExperimentService:
    """Sole-writer coordinator for immutable experiment plans and outcomes."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def plan(self, request: StudyRequest) -> Study:
        self._require_write()
        parameter_sets = self._parameter_sets(request)
        run_count = len(parameter_sets) * len(request.folds) * len(request.scenarios)
        design_content_id = scoped_content_id(
            {
                "schema": "persistra.experiments.study_design@1",
                "common_design": request.common_design_content_id,
                "search_kind": request.search_kind.value,
                "parameters": parameter_sets,
                "folds": request.folds,
                "scenarios": request.scenarios,
                "seed": request.seed,
            }
        )

        def operation(context: TransactionContext) -> Study:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            study_id = StudyId.new()
            connection.execute(
                "INSERT INTO experiments.studies VALUES "
                "(?, ?, ?, ?, 'planned', ?, ?)",
                [
                    study_id.value,
                    request.name,
                    str(design_content_id),
                    identity_bytes(request).decode(),
                    run_count,
                    context.recorded_at,
                ],
            )
            trials: list[tuple[Any, ...]] = []
            trial_refs: list[tuple[TrialId, ContentId]] = []
            for ordinal, parameters in enumerate(parameter_sets, 1):
                trial_id = TrialId.new()
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.experiments.trial@1",
                        "study_design": design_content_id,
                        "parameters": parameters,
                    }
                )
                trials.append(
                    (
                        study_id.value,
                        trial_id.value,
                        ordinal,
                        json.dumps(dict(parameters.values), sort_keys=True),
                        str(content_id),
                    )
                )
                trial_refs.append((trial_id, content_id))
            connection.executemany(
                "INSERT INTO experiments.trials VALUES (?, ?, ?, ?, ?)", trials
            )
            folds: list[tuple[Any, ...]] = []
            fold_refs: list[tuple[ExperimentFoldId, ContentId]] = []
            for ordinal, membership in enumerate(request.folds, 1):
                fold_id = ExperimentFoldId.new()
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.experiments.fold@1",
                        "study_design": design_content_id,
                        "ordinal": ordinal,
                        "membership": membership,
                    }
                )
                folds.append(
                    (
                        study_id.value,
                        fold_id.value,
                        ordinal,
                        str(membership),
                        str(content_id),
                    )
                )
                fold_refs.append((fold_id, content_id))
            connection.executemany(
                "INSERT INTO experiments.folds VALUES (?, ?, ?, ?, ?)", folds
            )
            scenarios: list[tuple[Any, ...]] = []
            scenario_refs: list[tuple[ScenarioId, ContentId]] = []
            for ordinal, scenario in enumerate(request.scenarios, 1):
                scenario_id = ScenarioId.new()
                content_id = scoped_content_id(
                    {
                        "schema": "persistra.experiments.scenario@1",
                        "study_design": design_content_id,
                        "ordinal": ordinal,
                        "scenario": scenario,
                    }
                )
                derived_seed = (
                    None
                    if scenario.seed_namespace is None
                    else int.from_bytes(
                        scoped_content_id(
                            {
                                "root_seed": request.seed,
                                "namespace": scenario.seed_namespace,
                                "scenario": content_id,
                            }
                        ).digest[:8],
                        "big",
                    )
                    & ((1 << 63) - 1)
                )
                scenarios.append(
                    (
                        study_id.value,
                        scenario_id.value,
                        ordinal,
                        scenario.kind.value,
                        scenario.name,
                        json.dumps(dict(scenario.parameters), sort_keys=True),
                        derived_seed,
                        str(content_id),
                    )
                )
                scenario_refs.append((scenario_id, content_id))
            connection.executemany(
                "INSERT INTO experiments.scenarios VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                scenarios,
            )
            reused = self._write_run_plans(
                connection,
                study_id,
                request,
                trial_refs,
                fold_refs,
                scenario_refs,
            )
            return Study(
                self._project,
                StudyRef(study_id, design_content_id, run_count, reused),
            )

        return self._project.services.transactions.run("experiment_study_plan", operation)

    def get(self, study_id: StudyId) -> Study:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT design_content_id, run_plan_count FROM experiments.studies "
            "WHERE study_id = ?",
            [study_id.value],
        ).fetchone()
        if row is None:
            raise ExperimentRequestError("study is missing")
        reused = connection.execute(
            "SELECT count(*) FROM experiments.run_plans WHERE study_id = ? "
            "AND state IN ('reused_exact', 'reused_compatible')",
            [study_id.value],
        ).fetchone()[0]
        return Study(
            self._project,
            StudyRef(
                study_id,
                ContentId.parse(row[0]),
                int(row[1]),
                int(reused),
            ),
        )

    def list(self, *, max_rows: int = 10_000) -> pd.DataFrame:
        """List immutable studies without exposing repository SQL."""
        if max_rows < 1:
            raise ExperimentRequestError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT study_id, name, design_content_id, state, run_plan_count, "
            "created_at FROM experiments.studies "
            "ORDER BY created_at, study_id LIMIT ?",
            [max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ExperimentRequestError("study rows exceed max_rows")
        return frame

    def start_attempt(self, run_plan_id: RunPlanId) -> AttemptRef:
        self._require_write()

        def operation(context: TransactionContext) -> AttemptRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            row = connection.execute(
                "SELECT r.execution_content_id, r.state, s.request_json FROM "
                "experiments.run_plans r JOIN experiments.studies s USING (study_id) "
                "WHERE r.run_plan_id = ?",
                [run_plan_id.value],
            ).fetchone()
            if row is None:
                raise ExperimentRequestError("run plan is missing")
            if row[1] not in {"planned", "failed", "scheduled"}:
                raise ExperimentStateError("run plan is not attemptable")
            ordinal = int(
                connection.execute(
                    "SELECT count(*) + 1 FROM experiments.attempts WHERE run_plan_id = ?",
                    [run_plan_id.value],
                ).fetchone()[0]
            )
            if ordinal > int(json.loads(row[2])["max_attempts"]):
                raise ExperimentStateError("run plan exhausted its retry policy")
            attempt_id = AttemptId.new()
            connection.execute(
                "INSERT INTO experiments.attempts VALUES "
                "(?, ?, ?, 'running', NULL, NULL, NULL, ?, NULL)",
                [attempt_id.value, run_plan_id.value, ordinal, context.recorded_at],
            )
            connection.execute(
                "UPDATE experiments.run_plans SET state = 'scheduled' "
                "WHERE run_plan_id = ?",
                [run_plan_id.value],
            )
            return AttemptRef(
                attempt_id,
                run_plan_id,
                ordinal,
                AttemptState.RUNNING,
                ContentId.parse(row[0]),
            )

        return self._project.services.transactions.run("experiment_attempt_start", operation)

    def interrupt(self, attempt_id: AttemptId, checkpoint: ContentId) -> AttemptRef:
        return self._set_nonterminal(
            attempt_id, AttemptState.INTERRUPTED, checkpoint=checkpoint
        )

    def resume(self, attempt_id: AttemptId) -> AttemptRef:
        self._require_write()

        def operation(_: TransactionContext) -> AttemptRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            row = self._attempt_row(connection, attempt_id)
            if row[3] != AttemptState.INTERRUPTED.value or row[6] is None:
                raise ExperimentStateError(
                    "only a checkpointed interrupted attempt can resume"
                )
            connection.execute(
                "UPDATE experiments.attempts SET state = 'running' WHERE attempt_id = ?",
                [attempt_id.value],
            )
            return AttemptRef(
                attempt_id,
                RunPlanId.parse(row[1]),
                int(row[2]),
                AttemptState.RUNNING,
                ContentId.parse(row[8]),
            )

        return self._project.services.transactions.run("experiment_attempt_resume", operation)

    def fail(self, attempt_id: AttemptId, failure_code: str) -> AttemptRef:
        if not failure_code:
            raise ExperimentRequestError("attempt failure code is required")
        return self._set_nonterminal(
            attempt_id, AttemptState.FAILED, failure_code=failure_code
        )

    def complete(self, attempt_id: AttemptId, manifest: ContentId) -> AttemptRef:
        self._require_write()

        def operation(context: TransactionContext) -> AttemptRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            row = self._attempt_row(connection, attempt_id)
            if row[3] != AttemptState.RUNNING.value:
                raise ExperimentStateError("only a running attempt can complete")
            execution = ContentId.parse(row[8])
            artifact = scoped_content_id(
                {
                    "schema": "persistra.experiments.artifact@1",
                    "execution": execution,
                    "manifest": manifest,
                }
            )
            connection.execute(
                "INSERT OR IGNORE INTO experiments.artifacts VALUES (?, ?, ?, true, ?)",
                [str(artifact), str(execution), str(manifest), context.recorded_at],
            )
            connection.execute(
                "UPDATE experiments.attempts SET state = 'completed', "
                "artifact_content_id = ?, completed_at = ? WHERE attempt_id = ?",
                [str(artifact), context.recorded_at, attempt_id.value],
            )
            connection.execute(
                "UPDATE experiments.run_plans SET state = 'completed' WHERE run_plan_id = ?",
                [row[1]],
            )
            return AttemptRef(
                attempt_id,
                RunPlanId.parse(row[1]),
                int(row[2]),
                AttemptState.COMPLETED,
                execution,
                artifact,
            )

        return self._project.services.transactions.run("experiment_attempt_complete", operation)

    def finalize(self, study_id: StudyId) -> Study:
        self._require_write()

        def operation(_: TransactionContext) -> Study:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "UPDATE experiments.run_plans SET state = 'not_scheduled' "
                "WHERE study_id = ? AND state IN ('planned', 'scheduled')",
                [study_id.value],
            )
            failures = int(
                connection.execute(
                    "SELECT count(*) FROM experiments.run_plans WHERE study_id = ? "
                    "AND state IN ('failed', 'not_scheduled')",
                    [study_id.value],
                ).fetchone()[0]
            )
            connection.execute(
                "UPDATE experiments.studies SET state = ? WHERE study_id = ?",
                [
                    "completed_with_failures" if failures else "completed",
                    study_id.value,
                ],
            )
            return self.get(study_id)

        return self._project.services.transactions.run("experiment_study_finalize", operation)

    def _write_run_plans(
        self,
        connection: ManagedConnection,
        study_id: StudyId,
        request: StudyRequest,
        trials: list[tuple[TrialId, ContentId]],
        folds: list[tuple[ExperimentFoldId, ContentId]],
        scenarios: list[tuple[ScenarioId, ContentId]],
    ) -> int:
        reused = 0
        ordinal = 0
        for trial, fold, scenario in itertools.product(trials, folds, scenarios):
            ordinal += 1
            run_plan_id = RunPlanId.new()
            design = scoped_content_id(
                {
                    "schema": "persistra.experiments.run_design@1",
                    "common": request.common_design_content_id,
                    "trial": trial[1],
                    "fold": fold[1],
                    "scenario": scenario[1],
                }
            )
            execution = scoped_content_id(
                {
                    "schema": "persistra.experiments.run_execution@1",
                    "design": design,
                    "environment": request.environment_content_id,
                }
            )
            source = connection.execute(
                "SELECT a.artifact_content_id FROM experiments.artifacts a "
                "WHERE a.execution_content_id = ? AND a.verified "
                "ORDER BY a.created_at, a.artifact_content_id LIMIT 1",
                [str(execution)],
            ).fetchone()
            state = "planned"
            artifact: str | None = None
            reuse_kind = "miss"
            source_execution: str | None = None
            differences: list[str] = []
            warning: str | None = None
            if request.allow_exact_reuse and source is not None:
                state = "reused_exact"
                artifact = source[0]
                reuse_kind = "exact"
                source_execution = str(execution)
                reused += 1
            elif "environment" in request.compatibility_keys:
                compatible = connection.execute(
                    "SELECT a.execution_content_id, a.artifact_content_id FROM "
                    "experiments.run_plans r JOIN experiments.artifacts a "
                    "ON a.artifact_content_id = r.reused_artifact_content_id "
                    "OR (r.execution_content_id = a.execution_content_id "
                    "AND r.state = 'completed') "
                    "WHERE r.design_content_id = ? AND a.verified "
                    "ORDER BY a.created_at LIMIT 1",
                    [str(design)],
                ).fetchone()
                if compatible is not None:
                    state = "reused_compatible"
                    source_execution, artifact = compatible
                    reuse_kind = "compatible"
                    differences = ["environment"]
                    warning = str(
                        scoped_content_id(
                            {
                                "schema": "persistra.experiments.compatibility_warning@1",
                                "requested": execution,
                                "source": source_execution,
                                "differences": differences,
                            }
                        )
                    )
                    reused += 1
            connection.execute(
                "INSERT INTO experiments.run_plans VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_plan_id.value,
                    study_id.value,
                    ordinal,
                    trial[0].value,
                    fold[0].value,
                    scenario[0].value,
                    str(design),
                    str(execution),
                    state,
                    artifact,
                    None if warning is None else json.dumps({"warning": warning}),
                ],
            )
            connection.execute(
                "INSERT INTO experiments.reuse_decisions VALUES (?, ?, ?, ?, ?, ?)",
                [
                    run_plan_id.value,
                    reuse_kind,
                    source_execution,
                    artifact,
                    json.dumps(differences),
                    warning,
                ],
            )
        return reused

    @staticmethod
    def _parameter_sets(request: StudyRequest) -> tuple[ParameterSet, ...]:
        if request.search_kind is SearchKind.USER_DEFINED:
            return request.user_suggestions
        grid = tuple(
            ParameterSet(tuple(zip(
                (domain.path for domain in request.parameter_domains),
                values,
                strict=True,
            )))
            for values in itertools.product(
                *(domain.values for domain in request.parameter_domains)
            )
        )
        if request.search_kind is SearchKind.GRID:
            return grid
        if request.search_kind is SearchKind.BAYESIAN:
            if importlib.util.find_spec("optuna") is None:
                raise CapabilityUnavailableError(
                    "Bayesian search requires the 'search' extra"
                )
        rng = random.Random(request.seed)
        candidates = list(grid)
        rng.shuffle(candidates)
        count = min(request.random_trials or len(candidates), len(candidates))
        return tuple(candidates[:count])

    def _set_nonterminal(
        self,
        attempt_id: AttemptId,
        state: AttemptState,
        *,
        failure_code: str | None = None,
        checkpoint: ContentId | None = None,
    ) -> AttemptRef:
        self._require_write()

        def operation(_: TransactionContext) -> AttemptRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            row = self._attempt_row(connection, attempt_id)
            if row[3] != AttemptState.RUNNING.value:
                raise ExperimentStateError("only a running attempt can transition")
            connection.execute(
                "UPDATE experiments.attempts SET state = ?, failure_code = ?, "
                "checkpoint_content_id = ? WHERE attempt_id = ?",
                [
                    state.value,
                    failure_code,
                    None if checkpoint is None else str(checkpoint),
                    attempt_id.value,
                ],
            )
            if state is AttemptState.FAILED:
                connection.execute(
                    "UPDATE experiments.run_plans SET state = 'failed' "
                    "WHERE run_plan_id = ?",
                    [row[1]],
                )
            return AttemptRef(
                attempt_id,
                RunPlanId.parse(row[1]),
                int(row[2]),
                state,
                ContentId.parse(row[8]),
            )

        return self._project.services.transactions.run("experiment_attempt_transition", operation)

    @staticmethod
    def _attempt_row(connection: ManagedConnection, attempt_id: AttemptId) -> Any:
        row = connection.execute(
            "SELECT a.attempt_id, a.run_plan_id, a.attempt_ordinal, a.state, "
            "a.artifact_content_id, a.failure_code, a.checkpoint_content_id, "
            "a.created_at, r.execution_content_id FROM experiments.attempts a "
            "JOIN experiments.run_plans r USING (run_plan_id) WHERE a.attempt_id = ?",
            [attempt_id.value],
        ).fetchone()
        if row is None:
            raise ExperimentRequestError("attempt is missing")
        return row

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("experiments require research_write mode")


@dataclass(frozen=True, slots=True)
class Study:
    _project: Project
    reference: StudyRef

    def run_plans(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame("run_plans", "schedule_ordinal", max_rows)

    def attempts(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            "SELECT a.* FROM experiments.attempts a JOIN experiments.run_plans r "
            "USING (run_plan_id) WHERE r.study_id = ? "
            "ORDER BY r.schedule_ordinal, a.attempt_ordinal LIMIT ?",
            [self.reference.study_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("experiment attempts exceed max_rows")
        return frame

    def trials(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame("trials", "trial_ordinal", max_rows)

    def scenarios(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame("scenarios", "scenario_ordinal", max_rows)

    def _frame(self, table: str, order_by: str, max_rows: int) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = connection.execute(
            f"SELECT * FROM experiments.{table} "
            f"WHERE study_id = ? ORDER BY {order_by} LIMIT ?",
            [self.reference.study_id.value, max_rows + 1],
        ).fetchdf()
        if len(frame) > max_rows:
            raise ResearchResultLimitError("experiment frame exceeds max_rows")
        return frame
