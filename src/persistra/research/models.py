"""Immutable minimal decision-dataset contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, Duration, EntityId, QualifiedName
from persistra.errors import ResearchDatasetDefinitionError
from persistra.market import AdjustmentPriceMode, BarSpecRef
from persistra.reference import (
    CutoffMode,
    PublicCutoffPolicy,
    SessionDecisionSchedule,
    UniverseRef,
)

if TYPE_CHECKING:
    from persistra.reference import UniverseEvaluationId


class ResearchDatasetId(EntityId):
    KIND: ClassVar[str] = "research_dataset"


class ResearchDatasetBuildId(EntityId):
    KIND: ClassVar[str] = "research_dataset_build"


class ResearchDatasetRole(StrEnum):
    DECISION = "decision"
    ANALYSIS = "analysis"


class ResearchInputKind(StrEnum):
    CANONICAL = "canonical"
    WORKSPACE = "workspace"
    FEATURE = "feature"
    LABEL = "label"


class MissingInputAction(StrEnum):
    RETAIN_NULL = "retain_null"
    MARK_UNUSABLE = "mark_unusable"
    DROP_WITH_AUDIT = "drop_with_audit"
    FAIL_BUILD = "fail_build"


@dataclass(frozen=True, slots=True)
class ResearchCutoffSpec:
    mode: CutoffMode
    public_policy: PublicCutoffPolicy

    @classmethod
    def public(
        cls, public_policy: PublicCutoffPolicy | None = None
    ) -> ResearchCutoffSpec:
        return cls(CutoffMode.PUBLIC, public_policy or PublicCutoffPolicy.at_decision())

    @classmethod
    def public_and_project(
        cls, public_policy: PublicCutoffPolicy | None = None
    ) -> ResearchCutoffSpec:
        return cls(
            CutoffMode.PUBLIC_AND_PROJECT,
            public_policy or PublicCutoffPolicy.at_decision(),
        )


@dataclass(frozen=True, slots=True)
class DailyBarInput:
    name: str
    spec: BarSpecRef
    adjustment_mode: AdjustmentPriceMode = AdjustmentPriceMode.RAW
    max_age: Duration = field(default_factory=lambda: Duration(604_800_000_000))
    missing_action: MissingInputAction = MissingInputAction.MARK_UNUSABLE
    kind: ResearchInputKind = ResearchInputKind.CANONICAL

    def __post_init__(self) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", self.name) is None:
            raise ResearchDatasetDefinitionError("research input name is invalid")
        if self.max_age.microseconds == 0:
            raise ResearchDatasetDefinitionError("bar input max_age must be positive")
        if self.kind is not ResearchInputKind.CANONICAL:
            raise ResearchDatasetDefinitionError(
                "phase 3 decision datasets accept canonical inputs only"
            )


@dataclass(frozen=True, slots=True)
class ResearchDatasetDefinition:
    name: QualifiedName
    version: int
    universe: UniverseRef
    decisions: SessionDecisionSchedule
    cutoff: ResearchCutoffSpec
    inputs: tuple[DailyBarInput, ...]
    role: ResearchDatasetRole = ResearchDatasetRole.DECISION

    def __post_init__(self) -> None:
        if self.version < 1:
            raise ResearchDatasetDefinitionError("dataset version must be positive")
        if self.role is not ResearchDatasetRole.DECISION:
            raise ResearchDatasetDefinitionError(
                "phase 3 implements decision-role datasets only"
            )
        if not self.inputs or len({item.name for item in self.inputs}) != len(self.inputs):
            raise ResearchDatasetDefinitionError(
                "dataset inputs must be nonempty with unique names"
            )


@dataclass(frozen=True, slots=True)
class ResearchDatasetRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedResearchDatasetRef:
    research_dataset_id: ResearchDatasetId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class ResearchDatasetBuildRef:
    research_dataset_build_id: ResearchDatasetBuildId
    research_dataset_id: ResearchDatasetId
    definition_version: int
    universe_evaluation_id: UniverseEvaluationId
    execution_content_id: ContentId
    output_manifest_content_id: ContentId
    row_count: int
    usable_count: int

