"""Immutable experiment hierarchy, search, scenario, and attempt contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from decimal import Decimal
    from pathlib import Path

from persistra.domain import ContentId, EntityId
from persistra.errors import ExperimentRequestError


class StudyId(EntityId):
    KIND: ClassVar[str] = "study"


class TrialId(EntityId):
    KIND: ClassVar[str] = "trial"


class ExperimentFoldId(EntityId):
    KIND: ClassVar[str] = "experiment_fold"


class ScenarioId(EntityId):
    KIND: ClassVar[str] = "scenario"


class RunPlanId(EntityId):
    KIND: ClassVar[str] = "run_plan"


class AttemptId(EntityId):
    KIND: ClassVar[str] = "attempt"


class WorkerAssignmentId(EntityId):
    KIND: ClassVar[str] = "worker_assignment"


class SearchKind(StrEnum):
    GRID = "grid"
    RANDOM = "random"
    USER_DEFINED = "user_defined"
    BAYESIAN = "bayesian"


class ScenarioKind(StrEnum):
    BASELINE = "baseline"
    HISTORICAL_STRESS = "historical_stress"
    HYPOTHETICAL = "hypothetical"
    MONTE_CARLO = "monte_carlo"
    BOOTSTRAP = "bootstrap"


class AttemptState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ObjectiveDirection(StrEnum):
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class CompatibilityField(StrEnum):
    ENVIRONMENT = "environment"


@dataclass(frozen=True, slots=True)
class CompatibilityPolicy:
    """Named/versioned allowlist for warned execution-identity reuse."""

    name: str
    version: int
    allowed_differences: tuple[CompatibilityField, ...]
    rationale: str

    def __post_init__(self) -> None:
        if (
            not self.name
            or self.version < 1
            or not self.allowed_differences
            or len(self.allowed_differences) != len(set(self.allowed_differences))
            or not self.rationale
        ):
            raise ExperimentRequestError("compatibility policy is invalid")


@dataclass(frozen=True, slots=True)
class ParameterDomain:
    path: str
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.path or not self.values or len(self.values) != len(set(self.values)):
            raise ExperimentRequestError("parameter domain is invalid")


@dataclass(frozen=True, slots=True)
class ParameterSet:
    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        paths = [path for path, _ in self.values]
        if not self.values or paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ExperimentRequestError("parameter set is invalid")


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    name: str
    kind: ScenarioKind
    parameters: tuple[tuple[str, str], ...] = ()
    seed_namespace: str | None = None

    def __post_init__(self) -> None:
        paths = [path for path, _ in self.parameters]
        randomized = self.kind in {ScenarioKind.MONTE_CARLO, ScenarioKind.BOOTSTRAP}
        if (
            not self.name
            or paths != sorted(paths)
            or len(paths) != len(set(paths))
            or randomized != (self.seed_namespace is not None)
        ):
            raise ExperimentRequestError("scenario specification is invalid")


@dataclass(frozen=True, slots=True)
class StudyRequest:
    name: str
    common_design_content_id: ContentId
    environment_content_id: ContentId
    search_kind: SearchKind
    parameter_domains: tuple[ParameterDomain, ...]
    folds: tuple[ContentId, ...]
    scenarios: tuple[ScenarioSpec, ...]
    user_suggestions: tuple[ParameterSet, ...] = ()
    random_trials: int = 0
    seed: int = 0
    max_attempts: int = 1
    allow_exact_reuse: bool = True
    compatibility_policy: CompatibilityPolicy | None = None
    objective_direction: ObjectiveDirection | None = None

    def __post_init__(self) -> None:
        domain_paths = [domain.path for domain in self.parameter_domains]
        candidate_count = 1
        for domain in self.parameter_domains:
            candidate_count *= len(domain.values)
        if (
            not self.name
            or not self.folds
            or not self.scenarios
            or not self.parameter_domains
            or domain_paths != sorted(domain_paths)
            or len(domain_paths) != len(set(domain_paths))
            or self.max_attempts <= 0
            or (self.search_kind is SearchKind.RANDOM and self.random_trials <= 0)
            or (
                self.search_kind is SearchKind.BAYESIAN
                and (
                    self.random_trials <= 0
                    or self.random_trials > candidate_count
                    or self.objective_direction is None
                )
            )
            or (
                self.search_kind is not SearchKind.BAYESIAN
                and self.objective_direction is not None
            )
            or (
                self.search_kind is SearchKind.USER_DEFINED
                and not self.user_suggestions
            )
            or (
                self.search_kind is not SearchKind.USER_DEFINED
                and self.user_suggestions
            )
        ):
            raise ExperimentRequestError("study request is invalid")


@dataclass(frozen=True, slots=True)
class StudyRef:
    study_id: StudyId
    design_content_id: ContentId
    run_plan_count: int
    reused_count: int


@dataclass(frozen=True, slots=True)
class AttemptRef:
    attempt_id: AttemptId
    run_plan_id: RunPlanId
    attempt_ordinal: int
    state: AttemptState
    execution_content_id: ContentId
    artifact_content_id: ContentId | None = None


@dataclass(frozen=True, slots=True)
class ScenarioExecution:
    """Resolved scenario input supplied to an experiment worker."""

    kind: ScenarioKind
    name: str
    parameters: tuple[tuple[str, str], ...]
    derived_seed: int | None
    content_id: ContentId


@dataclass(frozen=True, slots=True)
class RunAssignment:
    """Canonical, bounded worker input for one run-plan attempt."""

    worker_assignment_id: WorkerAssignmentId
    attempt_id: AttemptId
    run_plan_id: RunPlanId
    schedule_ordinal: int
    execution_content_id: ContentId
    parameters: tuple[tuple[str, str], ...]
    fold_content_id: ContentId
    scenario: ScenarioExecution
    output_path: Path


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    """A worker's completed semantic outcome before coordinator verification."""

    manifest_content_id: ContentId
    objective: Decimal
    row_count: int = 0

    def __post_init__(self) -> None:
        if not self.objective.is_finite() or self.row_count < 0:
            raise ExperimentRequestError("worker outcome is invalid")


@dataclass(frozen=True, slots=True)
class StudyExecutionPolicy:
    """Bounded deterministic coordinator behavior."""

    workers: int = 1
    max_completed: int | None = None
    max_failed: int | None = None
    objective_threshold: Decimal | None = None

    def __post_init__(self) -> None:
        if (
            self.workers < 1
            or self.workers > 64
            or (self.max_completed is not None and self.max_completed < 1)
            or (self.max_failed is not None and self.max_failed < 1)
            or (
                self.objective_threshold is not None
                and not self.objective_threshold.is_finite()
            )
        ):
            raise ExperimentRequestError("study execution policy is invalid")


@dataclass(frozen=True, slots=True)
class StudyExecutionSummary:
    study_id: StudyId
    planned: int
    completed: int
    failed: int
    reused: int
    cancelled: int
    not_scheduled: int
    terminal_state: str
