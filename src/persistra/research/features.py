"""Managed phase-4 return and momentum feature contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.errors import FeatureDefinitionError

if TYPE_CHECKING:
    from persistra.research.models import ResearchDatasetBuildId


class FeatureDefinitionId(EntityId):
    KIND: ClassVar[str] = "feature_definition"


class FeatureMaterializationId(EntityId):
    KIND: ClassVar[str] = "feature_materialization"


class FeatureKind(StrEnum):
    SIMPLE_RETURN = "simple_return"
    MOMENTUM = "momentum"


class FeatureValueState(StrEnum):
    COMPUTED = "computed"
    INPUT_MISSING = "input_missing"
    INSUFFICIENT_HISTORY = "insufficient_history"
    INVALID_NUMERIC = "invalid_numeric"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    name: QualifiedName
    version: int
    kind: FeatureKind
    input_name: str
    lookback: int
    skip: int = 0

    def __post_init__(self) -> None:
        if self.version < 1:
            raise FeatureDefinitionError("feature version must be positive")
        if not self.input_name or not self.input_name.isidentifier():
            raise FeatureDefinitionError("feature input name is invalid")
        if self.lookback < 1 or self.skip < 0:
            raise FeatureDefinitionError("feature lookback and skip are invalid")
        if self.kind is FeatureKind.SIMPLE_RETURN and self.skip != 0:
            raise FeatureDefinitionError("simple return does not accept a skip")
        if self.kind is FeatureKind.MOMENTUM and self.lookback <= self.skip:
            raise FeatureDefinitionError("momentum requires lookback greater than skip")


@dataclass(frozen=True, slots=True)
class FeatureRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResolvedFeatureRef:
    feature_definition_id: FeatureDefinitionId
    version: int
    definition_content_id: ContentId


@dataclass(frozen=True, slots=True)
class FeatureMaterializationRef:
    feature_materialization_id: FeatureMaterializationId
    feature_definition_id: FeatureDefinitionId
    definition_version: int
    research_dataset_build_id: ResearchDatasetBuildId
    execution_content_id: ContentId
    output_manifest_content_id: ContentId
    row_count: int
    computed_count: int
