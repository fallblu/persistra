"""Deterministic study planning, reuse, attempts, retry, and resume."""

from __future__ import annotations

import importlib.util
import itertools
import json
import multiprocessing
import random
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import duckdb

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
    CompatibilityField,
    CompatibilityPolicy,
    ExperimentFoldId,
    ObjectiveDirection,
    ParameterDomain,
    ParameterSet,
    RunAssignment,
    RunPlanId,
    ScenarioExecution,
    ScenarioId,
    ScenarioKind,
    ScenarioSpec,
    SearchKind,
    StudyExecutionPolicy,
    StudyExecutionSummary,
    StudyId,
    StudyRef,
    StudyRequest,
    TrialId,
    WorkerAssignmentId,
    WorkerOutcome,
)

if TYPE_CHECKING:
    import pandas as pd

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project

WorkerCallable = Callable[[RunAssignment], WorkerOutcome]
_DEFAULT_EXECUTION_POLICY = StudyExecutionPolicy()


@dataclass(frozen=True, slots=True)
class _WorkerHandoff:
    outcome: WorkerOutcome
    file_sha256: str
    file_size: int


def _run_isolated_worker(
    worker: WorkerCallable, assignment: RunAssignment
) -> _WorkerHandoff:
    """Execute user work and seal its outcome in one isolated DuckDB file."""
    outcome = worker(assignment)
    connection = duckdb.connect(str(assignment.output_path))
    try:
        connection.execute(
            "CREATE TABLE worker_outcome ("
            "attempt_id VARCHAR NOT NULL, execution_content_id VARCHAR NOT NULL, "
            "manifest_content_id VARCHAR NOT NULL, objective_decimal VARCHAR NOT NULL, "
            "row_count BIGINT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO worker_outcome VALUES (?, ?, ?, ?, ?)",
            [
                str(assignment.attempt_id.value),
                str(assignment.execution_content_id),
                str(outcome.manifest_content_id),
                str(outcome.objective),
                outcome.row_count,
            ],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    payload = assignment.output_path.read_bytes()
    return _WorkerHandoff(outcome, sha256(payload).hexdigest(), len(payload))


class ExperimentService:
    """Sole-writer coordinator for immutable experiment plans and outcomes."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def plan(self, request: StudyRequest) -> Study:
        self._require_write()
        parameter_sets = (
            ()
            if request.search_kind is SearchKind.BAYESIAN
            else self._parameter_sets(request)
        )
        if request.search_kind is SearchKind.BAYESIAN:
            self._require_optuna()
        trial_count = (
            request.random_trials
            if request.search_kind is SearchKind.BAYESIAN
            else len(parameter_sets)
        )
        run_count = trial_count * len(request.folds) * len(request.scenarios)
        design_content_id = scoped_content_id(
            {
                "schema": "persistra.experiments.study_design@1",
                "common_design": request.common_design_content_id,
                "search_kind": request.search_kind.value,
                "parameter_domains": request.parameter_domains,
                "parameters": parameter_sets,
                "folds": request.folds,
                "scenarios": request.scenarios,
                "seed": request.seed,
                "objective_direction": request.objective_direction,
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
            if trials:
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
            reused = (
                0
                if request.search_kind is SearchKind.BAYESIAN
                else self._write_run_plans(
                    connection,
                    study_id,
                    request,
                    trial_refs,
                    fold_refs,
                    scenario_refs,
                )
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "study.planned",
                evidence={"run_plan_count": run_count},
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

    def cancel(self, study_id: StudyId, reason_code: str = "user.cancelled") -> None:
        """Persist cooperative cancellation intent for a running coordinator."""
        self._require_write()
        if not reason_code:
            raise ExperimentRequestError("cancellation reason code is required")

        def operation(context: TransactionContext) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "INSERT OR IGNORE INTO experiments.cancellation_intents VALUES (?, ?, ?)",
                [study_id.value, reason_code, context.recorded_at],
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "study.cancellation_requested",
                evidence={"reason_code": reason_code},
            )

        self._project.services.transactions.run("experiment_cancel", operation)

    def execute(
        self,
        study_id: StudyId,
        worker: WorkerCallable,
        *,
        policy: StudyExecutionPolicy = _DEFAULT_EXECUTION_POLICY,
    ) -> StudyExecutionSummary:
        """Execute a study through isolated local workers and verified handoffs."""
        self._require_write()
        request = self._study_request(study_id)
        if policy.objective_threshold is not None and request.objective_direction is None:
            raise ExperimentRequestError(
                "objective threshold requires an objective direction"
            )
        if request.search_kind is SearchKind.BAYESIAN:
            self._execute_bayesian(study_id, request, worker, policy)
        else:
            plan_ids = self._ready_plan_ids(study_id)
            self._execute_plan_ids(study_id, request, plan_ids, worker, policy)
        study = self.finalize(study_id)
        plans = study.run_plans()
        counts = plans["state"].value_counts().to_dict()
        state = str(
            self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            .execute(
                "SELECT state FROM experiments.studies WHERE study_id = ?",
                [study_id.value],
            )
            .fetchone()[0]
        )
        return StudyExecutionSummary(
            study_id,
            study.reference.run_plan_count,
            int(counts.get("completed", 0)),
            int(counts.get("failed", 0)),
            int(counts.get("reused_exact", 0))
            + int(counts.get("reused_compatible", 0)),
            int(counts.get("cancelled", 0)),
            int(counts.get("not_scheduled", 0)),
            state,
        )

    def _execute_bayesian(
        self,
        study_id: StudyId,
        request: StudyRequest,
        worker: WorkerCallable,
        policy: StudyExecutionPolicy,
    ) -> None:
        optuna = self._require_optuna()
        direction = request.objective_direction
        if direction is None:
            raise ExperimentStateError("Bayesian objective direction is missing")
        sampler = optuna.samplers.TPESampler(seed=request.seed, n_startup_trials=1)
        optimizer = optuna.create_study(
            direction=direction.value,
            sampler=sampler,
        )
        seen: set[tuple[tuple[str, str], ...]] = set()

        def next_unique() -> tuple[Any, tuple[tuple[str, str], ...]]:
            maximum = 1
            for domain in request.parameter_domains:
                maximum *= len(domain.values)
            for _ in range(maximum + 1):
                candidate = optimizer.ask()
                values = tuple(
                    (
                        domain.path,
                        str(
                            candidate.suggest_categorical(
                                domain.path, domain.values
                            )
                        ),
                    )
                    for domain in request.parameter_domains
                )
                if values not in seen:
                    seen.add(values)
                    return candidate, values
                optimizer.tell(candidate, state=optuna.trial.TrialState.FAIL)
                fallback = next(
                    (
                        item
                        for item in self._grid_parameter_sets(request)
                        if item.values not in seen
                    ),
                    None,
                )
                if fallback is not None:
                    optimizer.enqueue_trial(dict(fallback.values))
            raise ExperimentStateError("Bayesian search exhausted its parameter space")

        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        existing = connection.execute(
            "SELECT trial_id, parameters_json FROM experiments.trials "
            "WHERE study_id = ? ORDER BY trial_ordinal",
            [study_id.value],
        ).fetchall()
        for trial_id, parameters_json in existing:
            suggestion, values = next_unique()
            expected = dict(values)
            stored = json.loads(parameters_json)
            if expected != stored:
                raise ExperimentStateError("Bayesian optimizer replay diverged")
            objective = self._trial_objective(study_id, str(trial_id))
            if objective is None:
                plan_ids = self._trial_plan_ids(study_id, str(trial_id))
                self._execute_plan_ids(
                    study_id, request, plan_ids, worker, policy
                )
                objective = self._trial_objective(study_id, str(trial_id))
            if objective is None:
                raise ExperimentStateError("Bayesian trial has no eligible objective")
            optimizer.tell(suggestion, float(objective))
        for ordinal in range(len(existing) + 1, request.random_trials + 1):
            if self._cancelled(study_id):
                break
            suggestion, values = next_unique()
            trial_id = self._add_bayesian_trial(
                study_id, request, ordinal, ParameterSet(values)
            )
            plan_ids = self._trial_plan_ids(study_id, str(trial_id.value))
            self._execute_plan_ids(study_id, request, plan_ids, worker, policy)
            objective = self._trial_objective(study_id, str(trial_id.value))
            if objective is None:
                optimizer.tell(suggestion, state=optuna.trial.TrialState.FAIL)
            else:
                optimizer.tell(suggestion, float(objective))
            if self._stop_reached(study_id, request, policy, objective):
                break

    def _execute_plan_ids(
        self,
        study_id: StudyId,
        request: StudyRequest,
        plan_ids: list[RunPlanId],
        worker: WorkerCallable,
        policy: StudyExecutionPolicy,
    ) -> None:
        pending = list(plan_ids)
        while pending and not self._cancelled(study_id):
            batch = pending[: policy.workers]
            pending = pending[policy.workers :]
            assignments = [self._assign(plan_id) for plan_id in batch]
            context = multiprocessing.get_context("spawn")
            with ProcessPoolExecutor(
                max_workers=policy.workers, mp_context=context
            ) as executor:
                futures = {
                    assignment.schedule_ordinal: (
                        assignment,
                        executor.submit(_run_isolated_worker, worker, assignment),
                    )
                    for assignment in assignments
                }
                for schedule_ordinal in sorted(futures):
                    assignment, future = futures[schedule_ordinal]
                    if self._stop_reached(study_id, request, policy, None):
                        self._cancel_assignment(assignment)
                        continue
                    try:
                        handoff = future.result()
                        self._verify_handoff(assignment, handoff)
                        self._accept_handoff(study_id, assignment, handoff)
                    except Exception:
                        self._reject_handoff(study_id, assignment)
                        if self._retry_available(
                            assignment.run_plan_id, request.max_attempts
                        ):
                            pending.insert(0, assignment.run_plan_id)
                    finally:
                        assignment.output_path.unlink(missing_ok=True)
        if pending or self._cancelled(study_id):
            remaining = pending + self._ready_plan_ids(study_id)
            self._mark_not_scheduled(study_id, remaining)

    def _assign(self, run_plan_id: RunPlanId) -> RunAssignment:
        attempt = self.start_attempt(run_plan_id)

        def operation(context: TransactionContext) -> RunAssignment:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            row = connection.execute(
                "SELECT r.schedule_ordinal, t.parameters_json, f.membership_content_id, "
                "s.scenario_kind, s.name, s.parameters_json, s.derived_seed, "
                "s.scenario_content_id FROM experiments.run_plans r "
                "JOIN experiments.trials t USING (study_id, trial_id) "
                "JOIN experiments.folds f USING (study_id, experiment_fold_id) "
                "JOIN experiments.scenarios s USING (study_id, scenario_id) "
                "WHERE r.run_plan_id = ?",
                [run_plan_id.value],
            ).fetchone()
            if row is None:
                raise ExperimentRequestError("run plan is missing")
            assignment_id = WorkerAssignmentId.new()
            output_path = (
                self._project._config.temporary  # pyright: ignore[reportPrivateUsage]
                / f"experiment-{assignment_id.value}.duckdb"
            )
            connection.execute(
                "INSERT INTO experiments.worker_assignments VALUES "
                "(?, ?, 1, ?, 'assigned', NULL, ?, NULL)",
                [
                    assignment_id.value,
                    attempt.attempt_id.value,
                    output_path.name,
                    context.recorded_at,
                ],
            )
            study_id = StudyId.parse(
                str(connection.execute(
                    "SELECT study_id FROM experiments.run_plans WHERE run_plan_id = ?",
                    [run_plan_id.value],
                ).fetchone()[0])
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "attempt.assigned",
                run_plan_id=run_plan_id,
                attempt_id=attempt.attempt_id,
                evidence={"schedule_ordinal": int(row[0])},
            )
            return RunAssignment(
                assignment_id,
                attempt.attempt_id,
                run_plan_id,
                int(row[0]),
                attempt.execution_content_id,
                tuple(sorted(json.loads(row[1]).items())),
                ContentId.parse(row[2]),
                ScenarioExecution(
                    ScenarioKind(row[3]),
                    str(row[4]),
                    tuple(sorted(json.loads(row[5]).items())),
                    None if row[6] is None else int(row[6]),
                    ContentId.parse(row[7]),
                ),
                output_path,
            )

        return self._project.services.transactions.run(
            "experiment_worker_assign", operation
        )

    @staticmethod
    def _verify_handoff(
        assignment: RunAssignment, handoff: _WorkerHandoff
    ) -> None:
        if (
            not assignment.output_path.is_file()
            or assignment.output_path.is_symlink()
        ):
            raise ExperimentStateError("worker handoff file is missing")
        payload = assignment.output_path.read_bytes()
        if len(payload) != handoff.file_size or sha256(payload).hexdigest() != handoff.file_sha256:
            raise ExperimentStateError("worker handoff checksum mismatch")
        connection = duckdb.connect(str(assignment.output_path), read_only=True)
        try:
            tables = connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
            row = connection.execute("SELECT * FROM worker_outcome").fetchone()
            count_row = connection.execute(
                "SELECT count(*) FROM worker_outcome"
            ).fetchone()
        finally:
            connection.close()
        if (
            tables != [("worker_outcome",)]
            or count_row is None
            or int(count_row[0]) != 1
            or row is None
        ):
            raise ExperimentStateError("worker handoff schema is invalid")
        expected = (
            str(assignment.attempt_id.value),
            str(assignment.execution_content_id),
            str(handoff.outcome.manifest_content_id),
            str(handoff.outcome.objective),
            handoff.outcome.row_count,
        )
        if tuple(row) != expected:
            raise ExperimentStateError("worker handoff content mismatch")

    def _accept_handoff(
        self,
        study_id: StudyId,
        assignment: RunAssignment,
        handoff: _WorkerHandoff,
    ) -> None:
        objective_content_id = scoped_content_id(
            {
                "schema": "persistra.experiments.objective@1",
                "run_plan": assignment.run_plan_id,
                "value": str(handoff.outcome.objective),
            }
        )

        def operation(context: TransactionContext) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            handoff_content_id = scoped_content_id(
                {
                    "schema": "persistra.experiments.worker_handoff@1",
                    "attempt": assignment.attempt_id,
                    "file_sha256": handoff.file_sha256,
                    "file_size": handoff.file_size,
                    "outcome": handoff.outcome,
                }
            )
            connection.execute(
                "UPDATE experiments.worker_assignments SET state = 'completed', "
                "handoff_content_id = ?, completed_at = ? "
                "WHERE worker_assignment_id = ? AND state = 'assigned'",
                [
                    str(handoff_content_id),
                    context.recorded_at,
                    assignment.worker_assignment_id.value,
                ],
            )
            connection.execute(
                "INSERT INTO experiments.objective_observations VALUES (?, ?, ?, ?)",
                [
                    assignment.run_plan_id.value,
                    str(handoff.outcome.objective),
                    str(objective_content_id),
                    context.recorded_at,
                ],
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "attempt.handoff_verified",
                run_plan_id=assignment.run_plan_id,
                attempt_id=assignment.attempt_id,
                evidence={"handoff_content_id": str(handoff_content_id)},
            )

        self._project.services.transactions.run(
            "experiment_handoff_accept", operation
        )
        self.complete(
            assignment.attempt_id, handoff.outcome.manifest_content_id
        )

    def _reject_handoff(
        self, study_id: StudyId, assignment: RunAssignment
    ) -> None:
        def operation(context: TransactionContext) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "UPDATE experiments.worker_assignments SET state = 'failed', "
                "completed_at = ? WHERE worker_assignment_id = ?",
                [context.recorded_at, assignment.worker_assignment_id.value],
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "attempt.failed",
                run_plan_id=assignment.run_plan_id,
                attempt_id=assignment.attempt_id,
                evidence={"reason_code": "worker.handoff_failed"},
            )

        self._project.services.transactions.run(
            "experiment_handoff_reject", operation
        )
        self.fail(assignment.attempt_id, "worker.handoff_failed")

    def _cancel_assignment(self, assignment: RunAssignment) -> None:
        def operation(context: TransactionContext) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.execute(
                "UPDATE experiments.worker_assignments SET state = 'cancelled', "
                "completed_at = ? WHERE worker_assignment_id = ?",
                [context.recorded_at, assignment.worker_assignment_id.value],
            )

        self._project.services.transactions.run(
            "experiment_assignment_cancel", operation
        )
        self._set_nonterminal(assignment.attempt_id, AttemptState.CANCELLED)

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
                    "AND state IN ('failed', 'cancelled', 'not_scheduled')",
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

    def _study_request(self, study_id: StudyId) -> StudyRequest:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT request_json FROM experiments.studies WHERE study_id = ?",
            [study_id.value],
        ).fetchone()
        if row is None:
            raise ExperimentRequestError("study is missing")
        value = json.loads(row[0])
        return StudyRequest(
            name=value["name"],
            common_design_content_id=ContentId.parse(
                value["common_design_content_id"]
            ),
            environment_content_id=ContentId.parse(
                value["environment_content_id"]
            ),
            search_kind=SearchKind(value["search_kind"]),
            parameter_domains=tuple(
                ParameterDomain(domain["path"], tuple(domain["values"]))
                for domain in value["parameter_domains"]
            ),
            folds=tuple(ContentId.parse(item) for item in value["folds"]),
            scenarios=tuple(
                ScenarioSpec(
                    scenario["name"],
                    ScenarioKind(scenario["kind"]),
                    tuple(tuple(item) for item in scenario["parameters"]),
                    scenario["seed_namespace"],
                )
                for scenario in value["scenarios"]
            ),
            user_suggestions=tuple(
                ParameterSet(tuple(tuple(item) for item in suggestion["values"]))
                for suggestion in value["user_suggestions"]
            ),
            random_trials=int(value["random_trials"]),
            seed=int(value["seed"]),
            max_attempts=int(value["max_attempts"]),
            allow_exact_reuse=bool(value["allow_exact_reuse"]),
            compatibility_policy=(
                None
                if value["compatibility_policy"] is None
                else CompatibilityPolicy(
                    value["compatibility_policy"]["name"],
                    int(value["compatibility_policy"]["version"]),
                    tuple(
                        CompatibilityField(item)
                        for item in value["compatibility_policy"][
                            "allowed_differences"
                        ]
                    ),
                    value["compatibility_policy"]["rationale"],
                )
            ),
            objective_direction=(
                None
                if value["objective_direction"] is None
                else ObjectiveDirection(value["objective_direction"])
            ),
        )

    def _add_bayesian_trial(
        self,
        study_id: StudyId,
        request: StudyRequest,
        ordinal: int,
        parameters: ParameterSet,
    ) -> TrialId:
        def operation(context: TransactionContext) -> TrialId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            design_id = ContentId.parse(
                connection.execute(
                    "SELECT design_content_id FROM experiments.studies WHERE study_id = ?",
                    [study_id.value],
                ).fetchone()[0]
            )
            trial_id = TrialId.new()
            content_id = scoped_content_id(
                {
                    "schema": "persistra.experiments.trial@1",
                    "study_design": design_id,
                    "parameters": parameters,
                }
            )
            connection.execute(
                "INSERT INTO experiments.trials VALUES (?, ?, ?, ?, ?)",
                [
                    study_id.value,
                    trial_id.value,
                    ordinal,
                    json.dumps(dict(parameters.values), sort_keys=True),
                    str(content_id),
                ],
            )
            folds = [
                (ExperimentFoldId.parse(str(row[0])), ContentId.parse(row[1]))
                for row in connection.execute(
                    "SELECT experiment_fold_id, fold_content_id "
                    "FROM experiments.folds WHERE study_id = ? ORDER BY fold_ordinal",
                    [study_id.value],
                ).fetchall()
            ]
            scenarios = [
                (ScenarioId.parse(str(row[0])), ContentId.parse(row[1]))
                for row in connection.execute(
                    "SELECT scenario_id, scenario_content_id "
                    "FROM experiments.scenarios WHERE study_id = ? "
                    "ORDER BY scenario_ordinal",
                    [study_id.value],
                ).fetchall()
            ]
            self._write_run_plans(
                connection,
                study_id,
                request,
                [(trial_id, content_id)],
                folds,
                scenarios,
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "search.suggestion",
                evidence={
                    "trial_ordinal": ordinal,
                    "trial_content_id": str(content_id),
                },
            )
            return trial_id

        return self._project.services.transactions.run(
            "experiment_bayesian_suggestion", operation
        )

    def _ready_plan_ids(self, study_id: StudyId) -> list[RunPlanId]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        return [
            RunPlanId.parse(str(row[0]))
            for row in connection.execute(
                "SELECT run_plan_id FROM experiments.run_plans "
                "WHERE study_id = ? AND state IN ('planned', 'failed') "
                "ORDER BY schedule_ordinal",
                [study_id.value],
            ).fetchall()
        ]

    def _trial_plan_ids(self, study_id: StudyId, trial_id: str) -> list[RunPlanId]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        return [
            RunPlanId.parse(str(row[0]))
            for row in connection.execute(
                "SELECT run_plan_id FROM experiments.run_plans "
                "WHERE study_id = ? AND trial_id = ? "
                "AND state IN ('planned', 'failed') ORDER BY schedule_ordinal",
                [study_id.value, trial_id],
            ).fetchall()
        ]

    def _trial_objective(
        self, study_id: StudyId, trial_id: str
    ) -> Decimal | None:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT o.objective_decimal FROM experiments.run_plans r "
            "JOIN experiments.objective_observations o USING (run_plan_id) "
            "WHERE r.study_id = ? AND r.trial_id = ? ORDER BY r.schedule_ordinal",
            [study_id.value, trial_id],
        ).fetchall()
        expected = int(
            connection.execute(
                "SELECT count(*) FROM experiments.run_plans "
                "WHERE study_id = ? AND trial_id = ? "
                "AND state NOT IN ('reused_exact', 'reused_compatible')",
                [study_id.value, trial_id],
            ).fetchone()[0]
        )
        if not rows or len(rows) != expected:
            return None
        values = [Decimal(row[0]) for row in rows]
        return sum(values, Decimal()) / len(values)

    def _cancelled(self, study_id: StudyId) -> bool:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        return bool(
            connection.execute(
                "SELECT count(*) FROM experiments.cancellation_intents "
                "WHERE study_id = ?",
                [study_id.value],
            ).fetchone()[0]
        )

    def _retry_available(
        self, run_plan_id: RunPlanId, max_attempts: int
    ) -> bool:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        return (
            int(
                connection.execute(
                    "SELECT count(*) FROM experiments.attempts "
                    "WHERE run_plan_id = ?",
                    [run_plan_id.value],
                ).fetchone()[0]
            )
            < max_attempts
        )

    def _stop_reached(
        self,
        study_id: StudyId,
        request: StudyRequest,
        policy: StudyExecutionPolicy,
        objective: Decimal | None,
    ) -> bool:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        completed, failed = connection.execute(
            "SELECT count(*) FILTER (WHERE state = 'completed'), "
            "count(*) FILTER (WHERE state = 'failed') "
            "FROM experiments.run_plans WHERE study_id = ?",
            [study_id.value],
        ).fetchone()
        if policy.max_completed is not None and int(completed) >= policy.max_completed:
            return True
        if policy.max_failed is not None and int(failed) >= policy.max_failed:
            return True
        threshold = policy.objective_threshold
        if threshold is None or objective is None:
            return False
        if request.objective_direction is ObjectiveDirection.MAXIMIZE:
            return objective >= threshold
        return objective <= threshold

    def _mark_not_scheduled(
        self, study_id: StudyId, run_plan_ids: list[RunPlanId]
    ) -> None:
        unique = tuple(dict.fromkeys(item.value for item in run_plan_ids))
        if not unique:
            return

        def operation(context: TransactionContext) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            connection.executemany(
                "UPDATE experiments.run_plans SET state = 'not_scheduled' "
                "WHERE run_plan_id = ? AND state IN ('planned', 'failed')",
                [(item,) for item in unique],
            )
            self._record_progress(
                connection,
                study_id,
                context.recorded_at,
                "study.stopped",
                evidence={"not_scheduled": len(unique)},
            )

        self._project.services.transactions.run(
            "experiment_not_scheduled", operation
        )

    @staticmethod
    def _record_progress(
        connection: ManagedConnection,
        study_id: StudyId,
        recorded_at: Any,
        event_kind: str,
        *,
        run_plan_id: RunPlanId | None = None,
        attempt_id: AttemptId | None = None,
        evidence: dict[str, Any],
    ) -> None:
        sequence = int(
            connection.execute(
                "SELECT count(*) + 1 FROM experiments.progress_events "
                "WHERE study_id = ?",
                [study_id.value],
            ).fetchone()[0]
        )
        connection.execute(
            "INSERT INTO experiments.progress_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                uuid4(),
                study_id.value,
                sequence,
                event_kind,
                None if run_plan_id is None else run_plan_id.value,
                None if attempt_id is None else attempt_id.value,
                json.dumps(evidence, sort_keys=True),
                recorded_at,
            ],
        )

    @staticmethod
    def _require_optuna() -> Any:
        if importlib.util.find_spec("optuna") is None:
            raise CapabilityUnavailableError(
                "Bayesian search requires the 'search' extra"
            )
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
        return optuna

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
        ordinal = int(
            connection.execute(
                "SELECT coalesce(max(schedule_ordinal), 0) "
                "FROM experiments.run_plans WHERE study_id = ?",
                [study_id.value],
            ).fetchone()[0]
        )
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
            elif (
                request.compatibility_policy is not None
                and CompatibilityField.ENVIRONMENT
                in request.compatibility_policy.allowed_differences
            ):
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
                                "policy": request.compatibility_policy,
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
                "INSERT INTO experiments.reuse_decisions VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    run_plan_id.value,
                    reuse_kind,
                    source_execution,
                    artifact,
                    json.dumps(differences),
                    warning,
                    (
                        None
                        if request.compatibility_policy is None
                        else str(
                            scoped_content_id(
                                {
                                    "schema": "persistra.experiments.compatibility_policy@1",
                                    "policy": request.compatibility_policy,
                                }
                            )
                        )
                    ),
                ],
            )
        return reused

    @staticmethod
    def _parameter_sets(request: StudyRequest) -> tuple[ParameterSet, ...]:
        if request.search_kind is SearchKind.USER_DEFINED:
            return request.user_suggestions
        grid = ExperimentService._grid_parameter_sets(request)
        if request.search_kind is SearchKind.GRID:
            return grid
        if request.search_kind is SearchKind.BAYESIAN:
            raise ExperimentStateError(
                "Bayesian suggestions require objective-driven execution"
            )
        rng = random.Random(request.seed)
        candidates = list(grid)
        rng.shuffle(candidates)
        count = min(request.random_trials or len(candidates), len(candidates))
        return tuple(candidates[:count])

    @staticmethod
    def _grid_parameter_sets(request: StudyRequest) -> tuple[ParameterSet, ...]:
        return tuple(
            ParameterSet(tuple(zip(
                (domain.path for domain in request.parameter_domains),
                values,
                strict=True,
            )))
            for values in itertools.product(
                *(domain.values for domain in request.parameter_domains)
            )
        )

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
            elif state is AttemptState.CANCELLED:
                connection.execute(
                    "UPDATE experiments.run_plans SET state = 'cancelled' "
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

    def progress(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        return self._frame("progress_events", "event_sequence", max_rows)

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
