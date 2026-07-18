"""Immutable experiment hierarchy, search, scenario, and attempt contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar

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
    compatibility_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        domain_paths = [domain.path for domain in self.parameter_domains]
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
