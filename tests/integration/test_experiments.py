from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra.domain import ContentId, FixedClock
from persistra.experiments import (
    AttemptId,
    CompatibilityField,
    CompatibilityPolicy,
    ObjectiveDirection,
    ParameterDomain,
    RunAssignment,
    RunPlanId,
    ScenarioExecution,
    ScenarioKind,
    ScenarioSpec,
    SearchKind,
    StudyExecutionPolicy,
    StudyRequest,
    WorkerOutcome,
    apply_scenario,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 2, 1, tzinfo=UTC)


def _objective_worker(assignment: RunAssignment) -> WorkerOutcome:
    parameter = Decimal(dict(assignment.parameters)["x"])
    return WorkerOutcome(
        ContentId.from_bytes(
            f"{assignment.execution_content_id}:{parameter}".encode()
        ),
        abs(parameter - Decimal("2")),
        row_count=1,
    )


def _failing_worker(_: RunAssignment) -> WorkerOutcome:
    raise RuntimeError("worker detail must not enter persisted diagnostics")


def _request(environment: bytes = b"environment") -> StudyRequest:
    return StudyRequest(
        "deterministic-study",
        ContentId.from_bytes(b"design"),
        ContentId.from_bytes(environment),
        SearchKind.GRID,
        (
            ParameterDomain("lookback", ("20", "60")),
            ParameterDomain("threshold", ("0.0", "0.1")),
        ),
        (ContentId.from_bytes(b"fold-1"), ContentId.from_bytes(b"fold-2")),
        (
            ScenarioSpec("baseline", ScenarioKind.BASELINE),
            ScenarioSpec(
                "bootstrap",
                ScenarioKind.BOOTSTRAP,
                (
                    ("block_length", "2"),
                    ("count", "3"),
                    ("method", "stationary"),
                ),
                "bootstrap/main",
            ),
        ),
        max_attempts=2,
        compatibility_policy=CompatibilityPolicy(
            "persistra.environment_patch",
            1,
            (CompatibilityField.ENVIRONMENT,),
            "The test treats its synthetic environment difference as nonsemantic.",
        ),
    )


def test_deterministic_hierarchy_attempt_resume_retry_and_reuse(tmp_path: Path) -> None:
    root = Project.init(tmp_path / "project").root
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        study = project.services.experiments.plan(_request())
        plans = study.run_plans()
        assert study.reference.run_plan_count == 16
        assert plans["schedule_ordinal"].tolist() == list(range(1, 17))
        assert len(study.trials()) == 4
        assert len(study.scenarios()) == 2
        assert study.scenarios().loc[1, "derived_seed"] is not None

        first_plan = RunPlanId.parse(plans.iloc[0]["run_plan_id"])
        attempt = project.services.experiments.start_attempt(first_plan)
        checkpoint = ContentId.from_bytes(b"checkpoint")
        interrupted = project.services.experiments.interrupt(
            attempt.attempt_id, checkpoint
        )
        resumed = project.services.experiments.resume(interrupted.attempt_id)
        assert resumed.attempt_id == attempt.attempt_id
        completed = project.services.experiments.complete(
            resumed.attempt_id, ContentId.from_bytes(b"artifact-manifest")
        )
        assert completed.artifact_content_id is not None

        second_plan = RunPlanId.parse(plans.iloc[1]["run_plan_id"])
        failed = project.services.experiments.fail(
            project.services.experiments.start_attempt(second_plan).attempt_id,
            "worker.failed",
        )
        retry = project.services.experiments.start_attempt(failed.run_plan_id)
        assert retry.attempt_ordinal == 2
        project.services.experiments.complete(
            retry.attempt_id, ContentId.from_bytes(b"retry-manifest")
        )
        assert len(study.attempts()) == 3

        repeated = project.services.experiments.plan(_request())
        assert repeated.reference.reused_count == 2
        assert repeated.run_plans()["execution_content_id"].tolist() == (
            plans["execution_content_id"].tolist()
        )
        compatible = project.services.experiments.plan(_request(b"new-environment"))
        assert compatible.reference.reused_count == 2
        assert set(
            compatible.run_plans()
            .query("state == 'reused_compatible'")["compatibility_warning_json"]
            .notna()
        ) == {True}
        finalized = project.services.experiments.finalize(study.reference.study_id)
        assert finalized.reference.study_id == study.reference.study_id

        random_request = StudyRequest(
            "seeded-random",
            ContentId.from_bytes(b"random-design"),
            ContentId.from_bytes(b"environment"),
            SearchKind.RANDOM,
            (
                ParameterDomain("a", ("1", "2", "3")),
                ParameterDomain("b", ("x", "y")),
            ),
            (ContentId.from_bytes(b"fold"),),
            (ScenarioSpec("baseline", ScenarioKind.BASELINE),),
            random_trials=3,
            seed=17,
        )
        random_one = project.services.experiments.plan(random_request)
        random_two = project.services.experiments.plan(random_request)
        assert random_one.trials()["parameters_json"].tolist() == (
            random_two.trials()["parameters_json"].tolist()
        )

        assert AttemptId.parse(str(attempt.attempt_id.value)) == attempt.attempt_id


def test_bayesian_execution_workers_progress_and_scenarios(tmp_path: Path) -> None:
    root = Project.init(tmp_path / "project").root
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        request = StudyRequest(
            "objective-study",
            ContentId.from_bytes(b"design"),
            ContentId.from_bytes(b"environment"),
            SearchKind.BAYESIAN,
            (ParameterDomain("x", ("1", "2", "3")),),
            (ContentId.from_bytes(b"fold"),),
            (ScenarioSpec("baseline", ScenarioKind.BASELINE),),
            random_trials=3,
            seed=11,
            objective_direction=ObjectiveDirection.MINIMIZE,
        )
        study = project.services.experiments.plan(request)
        assert study.trials().empty
        summary = project.services.experiments.execute(
            study.reference.study_id,
            _objective_worker,
            policy=StudyExecutionPolicy(workers=2),
        )
        assert summary.completed == 3
        assert summary.failed == 0
        assert study.trials()["parameters_json"].is_unique
        assert set(study.progress()["event_kind"]) >= {
            "study.planned",
            "search.suggestion",
            "attempt.assigned",
            "attempt.handoff_verified",
        }
        connection = project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        assert connection.execute(
            "SELECT objective_decimal FROM experiments.objective_observations "
            "ORDER BY objective_decimal"
        ).fetchall()[0][0] == "0"

        baseline = study.scenarios().iloc[0]
        base_execution = ScenarioExecution(
            ScenarioKind.BASELINE,
            "baseline",
            (),
            None,
            ContentId.parse(str(baseline["scenario_content_id"])),
        )
        assert apply_scenario(
            base_execution, (Decimal("1"), Decimal("2"))
        ) == (Decimal("1"), Decimal("2"))

        bootstrap = ScenarioExecution(
            ScenarioKind.BOOTSTRAP,
            "bootstrap",
            (
                ("block_length", "2"),
                ("count", "5"),
                ("method", "moving"),
            ),
            7,
            ContentId.from_bytes(b"bootstrap"),
        )
        assert apply_scenario(
            bootstrap, (Decimal("1"), Decimal("2"), Decimal("3"))
        ) == apply_scenario(
            bootstrap, (Decimal("1"), Decimal("2"), Decimal("3"))
        )

        historical = ScenarioExecution(
            ScenarioKind.HISTORICAL_STRESS,
            "stress",
            (("start", "1"), ("stop", "3")),
            None,
            ContentId.from_bytes(b"stress"),
        )
        assert apply_scenario(
            historical,
            (Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")),
        ) == (Decimal("2"), Decimal("3"))
        hypothetical = ScenarioExecution(
            ScenarioKind.HYPOTHETICAL,
            "shock",
            (("add", "1"), ("multiply", "2")),
            None,
            ContentId.from_bytes(b"shock"),
        )
        assert apply_scenario(
            hypothetical, (Decimal("1"), Decimal("2"))
        ) == (Decimal("3"), Decimal("5"))
        monte_carlo = ScenarioExecution(
            ScenarioKind.MONTE_CARLO,
            "monte-carlo",
            (
                ("count", "4"),
                ("mean", "0"),
                ("standard_deviation", "1"),
            ),
            9,
            ContentId.from_bytes(b"monte-carlo"),
        )
        assert apply_scenario(
            monte_carlo, (Decimal("1"),)
        ) == apply_scenario(monte_carlo, (Decimal("1"),))


def test_execution_retries_and_cooperative_cancellation(tmp_path: Path) -> None:
    root = Project.init(tmp_path / "project").root
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        request = StudyRequest(
            "failure-study",
            ContentId.from_bytes(b"design"),
            ContentId.from_bytes(b"environment"),
            SearchKind.GRID,
            (ParameterDomain("x", ("1",)),),
            (ContentId.from_bytes(b"fold"),),
            (ScenarioSpec("baseline", ScenarioKind.BASELINE),),
            max_attempts=2,
        )
        failed_study = project.services.experiments.plan(request)
        summary = project.services.experiments.execute(
            failed_study.reference.study_id, _failing_worker
        )
        assert summary.failed == 1
        assert len(failed_study.attempts()) == 2
        assert set(failed_study.attempts()["failure_code"]) == {
            "worker.handoff_failed"
        }

        cancelled_study = project.services.experiments.plan(request)
        project.services.experiments.cancel(
            cancelled_study.reference.study_id, "user.cancelled"
        )
        cancelled = project.services.experiments.execute(
            cancelled_study.reference.study_id, _objective_worker
        )
        assert cancelled.not_scheduled == 1
        assert "study.cancellation_requested" in set(
            cancelled_study.progress()["event_kind"]
        )
