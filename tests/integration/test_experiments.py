from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from persistra import Project, ProjectMode
from persistra.domain import ContentId, FixedClock
from persistra.experiments import (
    AttemptId,
    ParameterDomain,
    RunPlanId,
    ScenarioKind,
    ScenarioSpec,
    SearchKind,
    StudyRequest,
)

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 2, 1, tzinfo=UTC)


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
                (("blocks", "stationary"),),
                "bootstrap/main",
            ),
        ),
        max_attempts=2,
        compatibility_keys=("environment",),
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
