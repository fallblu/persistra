"""Bounded SQL and immutable workspace contracts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, Duration, EntityId, QualifiedName
from persistra.errors import SqlQueryError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from persistra.research.features import FeatureMaterializationId
    from persistra.research.models import ResearchDatasetBuildId


class WorkspaceObjectId(EntityId):
    KIND: ClassVar[str] = "workspace_object"


class WorkspaceMaterializationId(EntityId):
    KIND: ClassVar[str] = "workspace_materialization"


class SafetyFindingId(EntityId):
    KIND: ClassVar[str] = "safety_finding"


class InformationClass(StrEnum):
    CAUSAL = "causal"
    OPAQUE = "opaque"
    RETROSPECTIVE = "retrospective"
    LABEL = "label"


class TemporalContractKind(StrEnum):
    DECISION_PANEL = "decision_panel"
    POINT_IN_TIME = "point_in_time"
    PERIOD_PANEL = "period_panel"
    OPAQUE = "opaque"


class LineageCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    OPAQUE = "opaque"


class SqlTemporalClass(StrEnum):
    ROW_LOCAL = "row_local"
    OPAQUE = "opaque"


class SafetyStatus(StrEnum):
    SAFE = "safe"
    UNSAFE = "unsafe"


class SqlDependencyKind(StrEnum):
    RESEARCH_DATASET_BUILD = "research_dataset_build"
    WORKSPACE_MATERIALIZATION = "workspace_materialization"
    FEATURE_MATERIALIZATION = "feature_materialization"
    LABEL_MATERIALIZATION = "label_materialization"


@dataclass(frozen=True, slots=True)
class DatasetBuildSqlRelation:
    research_dataset_build_id: ResearchDatasetBuildId


@dataclass(frozen=True, slots=True)
class WorkspaceSqlRelation:
    workspace_materialization_id: WorkspaceMaterializationId


@dataclass(frozen=True, slots=True)
class FeatureSqlRelation:
    feature_materialization_id: FeatureMaterializationId


SqlRelation = DatasetBuildSqlRelation | WorkspaceSqlRelation | FeatureSqlRelation


@dataclass(frozen=True, slots=True)
class SqlReadLimits:
    max_rows: int = 1_000_000
    max_columns: int = 1_024
    max_dependency_nodes: int = 100_000
    max_findings: int = 1_000_000
    chunk_rows: int = 100_000
    timeout: Duration = field(default_factory=lambda: Duration(300_000_000))

    def __post_init__(self) -> None:
        values = (
            self.max_rows,
            self.max_columns,
            self.max_dependency_nodes,
            self.max_findings,
            self.chunk_rows,
            self.timeout.microseconds,
        )
        if any(value < 1 for value in values):
            raise SqlQueryError("SQL read limits must be positive")


@dataclass(frozen=True, slots=True)
class WorkspaceMaterializationLimits:
    max_output_rows: int = 25_000_000
    max_columns: int = 1_024
    max_dependency_nodes: int = 100_000
    max_findings: int = 1_000_000
    chunk_rows: int = 100_000
    timeout: Duration = field(default_factory=lambda: Duration(300_000_000))

    def __post_init__(self) -> None:
        values = (
            self.max_output_rows,
            self.max_columns,
            self.max_dependency_nodes,
            self.max_findings,
            self.chunk_rows,
            self.timeout.microseconds,
        )
        if any(value < 1 for value in values):
            raise SqlQueryError("workspace limits must be positive")

    def as_read_limits(self) -> SqlReadLimits:
        return SqlReadLimits(
            self.max_output_rows,
            self.max_columns,
            self.max_dependency_nodes,
            self.max_findings,
            self.chunk_rows,
            self.timeout,
        )


@dataclass(frozen=True, slots=True)
class SqlReadContext:
    relations: Mapping[str, SqlRelation]
    primary_decision_relation: str | None = None

    def __post_init__(self) -> None:
        copied = dict(self.relations)
        if not copied:
            raise SqlQueryError("SQL context requires at least one relation")
        if len(copied) > 256:
            raise SqlQueryError("SQL context has too many relations")
        if any(
            re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name) is None
            for name in copied
        ):
            raise SqlQueryError("SQL relation alias is invalid")
        if (
            self.primary_decision_relation is not None
            and self.primary_decision_relation not in copied
        ):
            raise SqlQueryError("primary decision relation is not bound")
        object.__setattr__(self, "relations", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class SqlDependency:
    ordinal: int
    alias: str
    kind: SqlDependencyKind
    dependency_id: EntityId
    dependency_content_id: ContentId
    information_class: InformationClass
    temporal_contract: TemporalContractKind
    lineage_completeness: LineageCompleteness
    safety_status: SafetyStatus
    physical_relation: str = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class SqlQueryAudit:
    query_text_content_id: ContentId
    parameters_content_id: ContentId
    context_content_id: ContentId
    analyzer_content_id: ContentId
    output_schema_content_id: ContentId
    dependency_manifest_content_id: ContentId
    information_class: InformationClass
    temporal_contract: TemporalContractKind
    lineage_completeness: LineageCompleteness
    sql_temporal_class: SqlTemporalClass
    safety_status: SafetyStatus
    structurally_decision_eligible: bool
    row_count: int
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class WorkspaceMaterializationRef:
    workspace_object_id: WorkspaceObjectId
    workspace_materialization_id: WorkspaceMaterializationId
    object_version: int
    execution_content_id: ContentId
    output_schema_content_id: ContentId
    output_manifest_content_id: ContentId
    row_count: int
    information_class: InformationClass
    temporal_contract: TemporalContractKind
    safety_status: SafetyStatus
    structurally_decision_eligible: bool


@dataclass(frozen=True, slots=True)
class WorkspaceRef:
    name: QualifiedName
    version: int | None = None

    def __post_init__(self) -> None:
        if not str(self.name).startswith("workspace."):
            raise SqlQueryError("workspace names must begin with 'workspace.'")
        if self.version is not None and self.version < 1:
            raise SqlQueryError("workspace version must be positive")
