"""Immutable decision-input safety and lineage contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.domain import ContentId, EntityId
from persistra.errors import DecisionInputManifestError
from persistra.research.sql_models import (
    InformationClass,
    LineageCompleteness,
    SafetyStatus,
    TemporalContractKind,
)


class DecisionInputManifestId(EntityId):
    KIND: ClassVar[str] = "decision_input_manifest"


@dataclass(frozen=True, slots=True)
class UnsafeDecisionInputOverride:
    """Explicit acknowledgement for eligible opaque/unsafe research inputs."""

    reason: str
    acknowledgement: str = "I acknowledge unsafe decision inputs"

    def __post_init__(self) -> None:
        if (
            not self.reason.strip()
            or self.acknowledgement != "I acknowledge unsafe decision inputs"
        ):
            raise DecisionInputManifestError(
                "unsafe override requires the exact acknowledgement and a reason"
            )

    @property
    def content_id(self) -> ContentId:
        return scoped_content_id(
            {
                "schema": "persistra.portfolio.unsafe_decision_input_override@1",
                "value": self,
            }
        )


@dataclass(frozen=True, slots=True)
class ExternalDecisionInputDeclaration:
    """Evidence declaration for a registered external event-strategy input."""

    source_content_id: ContentId
    information_class: InformationClass
    temporal_contract_kind: TemporalContractKind
    lineage_completeness: LineageCompleteness
    safety_status: SafetyStatus
    structurally_decision_eligible: bool
    licensing_classes: tuple[str, ...]
    conformance_status: str
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.licensing_classes
            or any(not item.strip() for item in self.licensing_classes)
            or self.conformance_status not in {"passed", "failed", "not_applicable"}
            or len(set(self.findings)) != len(self.findings)
        ):
            raise DecisionInputManifestError(
                "external decision-input declaration is invalid"
            )


@dataclass(frozen=True, slots=True)
class DecisionInputManifestRef:
    decision_input_manifest_id: DecisionInputManifestId
    manifest_content_id: ContentId
    source_kind: str
    source_id: str
    source_snapshot_content_ids: tuple[ContentId, ...]
    dependency_manifest_content_ids: tuple[ContentId, ...]
    information_class: InformationClass
    temporal_contract_kind: TemporalContractKind
    lineage_completeness: LineageCompleteness
    safety_status: SafetyStatus
    structurally_decision_eligible: bool
    licensing_classes: tuple[str, ...]
    conformance_status: str
    findings: tuple[str, ...]

    @property
    def is_structurally_forbidden(self) -> bool:
        return (
            self.information_class
            in {InformationClass.LABEL, InformationClass.RETROSPECTIVE}
            or not self.structurally_decision_eligible
        )

    @property
    def requires_unsafe_override(self) -> bool:
        return (
            self.information_class is InformationClass.OPAQUE
            or self.temporal_contract_kind is TemporalContractKind.OPAQUE
            or self.lineage_completeness is not LineageCompleteness.COMPLETE
            or self.safety_status is SafetyStatus.UNSAFE
            or self.conformance_status == "failed"
        )


__all__ = [
    "DecisionInputManifestId",
    "DecisionInputManifestRef",
    "ExternalDecisionInputDeclaration",
    "UnsafeDecisionInputOverride",
]
