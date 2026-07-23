"""This module contains the decision-input manifest registration, verification, and propagation."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.domain import ContentId
from persistra.errors import (
    DecisionInputManifestError,
    DecisionInputSafetyError,
)
from persistra.portfolio.safety_models import (
    DecisionInputManifestId,
    DecisionInputManifestRef,
    ExternalDecisionInputDeclaration,
    UnsafeDecisionInputOverride,
)
from persistra.research.sql_models import (
    InformationClass,
    LineageCompleteness,
    SafetyStatus,
    TemporalContractKind,
)

if TYPE_CHECKING:
    from datetime import datetime

    from persistra.project import Project
    from persistra.research.models import ResearchDatasetBuildId


class DecisionInputService:
    """This class owns immutable manifests and attaches them to each derived artifact."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def for_dataset(
        self, build_id: ResearchDatasetBuildId
    ) -> DecisionInputManifestRef:
        build_value = getattr(build_id, "value", build_id)
        source_id = f"research_dataset_build:{build_value}"
        existing = self._by_source("research_dataset_build", source_id)
        if existing is not None:
            return existing
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT b.composite_snapshot_id, b.output_manifest_content_id, "
            "coalesce(e.dataset_role, 'decision'), "
            "coalesce(e.information_class, 'causal'), "
            "coalesce(e.temporal_contract_kind, 'decision_panel'), "
            "coalesce(e.lineage_completeness, 'complete'), "
            "coalesce(e.safety_status, 'safe'), "
            "coalesce(e.structurally_decision_eligible, true) "
            "FROM research.research_dataset_builds b LEFT JOIN "
            "research.research_dataset_enrichments e USING "
            "(research_dataset_build_id) WHERE b.research_dataset_build_id = ?",
            [build_value],
        ).fetchone()
        if row is None:
            raise DecisionInputManifestError("research dataset build is unavailable")
        snapshots = tuple(
            ContentId.parse(value[0])
            for value in connection.execute(
                "SELECT market_manifest_content_id FROM "
                "research.composite_snapshot_members WHERE composite_snapshot_id = ? "
                "ORDER BY database_name",
                [row[0]],
            ).fetchall()
        )
        dependencies = tuple(
            ContentId.parse(value[0])
            for value in connection.execute(
                "SELECT dependency_manifest_content_id FROM "
                "research.research_dataset_enrichment_inputs "
                "WHERE research_dataset_build_id = ? ORDER BY input_ordinal",
                [build_value],
            ).fetchall()
        )
        information = InformationClass(row[3])
        temporal = TemporalContractKind(row[4])
        lineage = LineageCompleteness(row[5])
        safety = SafetyStatus(row[6])
        eligible = bool(row[7]) and row[2] == "decision"
        findings = _safety_findings(
            information,
            temporal,
            lineage,
            safety,
            eligible,
        )
        licensing = self._licensing_classes(row[0])
        material = {
            "schema": "persistra.portfolio.decision_input_manifest@1",
            "source_kind": "research_dataset_build",
            "source_id": source_id,
            "source_snapshot_content_ids": snapshots,
            "dependency_manifest_content_ids": (
                ContentId.parse(row[1]),
                *dependencies,
            ),
            "information_class": information,
            "temporal_contract_kind": temporal,
            "lineage_completeness": lineage,
            "safety_status": safety,
            "structurally_decision_eligible": eligible,
            "licensing_classes": licensing,
            "conformance_status": (
                "passed" if temporal is not TemporalContractKind.OPAQUE else "failed"
            ),
            "findings": findings,
        }
        return self._register(material)

    def register_external(
        self, declaration: ExternalDecisionInputDeclaration
    ) -> DecisionInputManifestRef:
        """Register exact external event-strategy evidence before planning a run."""
        source_id = str(declaration.source_content_id)
        existing = self._by_source("external_strategy", source_id)
        if existing is not None:
            expected = _external_material(declaration)
            if existing.manifest_content_id != scoped_content_id(expected):
                raise DecisionInputManifestError(
                    "external strategy input was registered with different evidence"
                )
            return existing
        return self._register(_external_material(declaration))

    def for_artifact(self, artifact_kind: str, artifact_id: object) -> DecisionInputManifestRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT decision_input_manifest_id FROM "
            "portfolio.artifact_safety_bindings WHERE artifact_kind = ? "
            "AND artifact_id = ?",
            [artifact_kind, getattr(artifact_id, "value", artifact_id)],
        ).fetchone()
        if row is None:
            raise DecisionInputManifestError(
                f"{artifact_kind} has no decision-input safety binding"
            )
        return self.get(DecisionInputManifestId.parse(row[0]))

    def get(self, manifest_id: DecisionInputManifestId) -> DecisionInputManifestRef:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT manifest_content_id, source_kind, source_id, "
            "source_snapshot_content_ids_json, "
            "dependency_manifest_content_ids_json, information_class, "
            "temporal_contract_kind, lineage_completeness, safety_status, "
            "structurally_decision_eligible, licensing_classes_json, "
            "conformance_status, findings_json FROM "
            "portfolio.decision_input_manifests WHERE decision_input_manifest_id = ?",
            [manifest_id.value],
        ).fetchone()
        if row is None:
            raise DecisionInputManifestError("decision-input manifest is unavailable")
        result = DecisionInputManifestRef(
            manifest_id,
            ContentId.parse(row[0]),
            str(row[1]),
            str(row[2]),
            tuple(ContentId.parse(item) for item in json.loads(row[3])),
            tuple(ContentId.parse(item) for item in json.loads(row[4])),
            InformationClass(row[5]),
            TemporalContractKind(row[6]),
            LineageCompleteness(row[7]),
            SafetyStatus(row[8]),
            bool(row[9]),
            tuple(json.loads(row[10])),
            str(row[11]),
            tuple(json.loads(row[12])),
        )
        material = _manifest_material(result)
        if scoped_content_id(material) != result.manifest_content_id:
            raise DecisionInputManifestError(
                "stored decision-input manifest does not rebuild"
            )
        return result

    def validate(
        self,
        manifest: DecisionInputManifestRef,
        override: UnsafeDecisionInputOverride | None,
    ) -> tuple[bool, tuple[str, ...]]:
        """Reject structural violations. Make acknowledgement necessary for unsafe inputs."""
        verified = self.get(manifest.decision_input_manifest_id)
        if verified != manifest:
            raise DecisionInputManifestError(
                "decision-input reference does not match persisted evidence"
            )
        if verified.is_structurally_forbidden:
            raise DecisionInputSafetyError(
                "label, retrospective, or structurally ineligible ancestry is forbidden"
            )
        if verified.requires_unsafe_override and override is None:
            raise DecisionInputSafetyError(
                "unsafe or opaque decision inputs require an explicit override"
            )
        tainted = verified.requires_unsafe_override
        findings = verified.findings + (
            ("decision_input.unsafe_override",) if tainted else ()
        )
        return tainted, tuple(dict.fromkeys(findings))

    def bind(
        self,
        *,
        artifact_kind: str,
        artifact_id: object,
        manifest: DecisionInputManifestRef,
        override: UnsafeDecisionInputOverride | None,
        created_at: datetime,
    ) -> None:
        tainted, findings = self.validate(manifest, override)
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        value = getattr(artifact_id, "value", artifact_id)
        existing = connection.execute(
            "SELECT decision_input_manifest_id, unsafe_override_content_id, "
            "tainted, findings_json FROM portfolio.artifact_safety_bindings "
            "WHERE artifact_kind = ? AND artifact_id = ?",
            [artifact_kind, value],
        ).fetchone()
        expected = (
            manifest.decision_input_manifest_id.value,
            None if override is None else str(override.content_id),
            tainted,
            _json(findings),
        )
        if existing is not None:
            if tuple(existing) != expected:
                raise DecisionInputManifestError(
                    "artifact safety binding does not match execution"
                )
            return
        connection.execute(
            "INSERT INTO portfolio.artifact_safety_bindings VALUES "
            "(?, ?, ?, ?, ?, ?, ?)",
            [artifact_kind, value, *expected, created_at],
        )

    def _by_source(
        self, source_kind: str, source_id: str
    ) -> DecisionInputManifestRef | None:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT decision_input_manifest_id FROM "
            "portfolio.decision_input_manifests WHERE source_kind = ? AND source_id = ?",
            [source_kind, source_id],
        ).fetchone()
        return None if row is None else self.get(DecisionInputManifestId.parse(row[0]))

    def _register(self, material: dict[str, Any]) -> DecisionInputManifestRef:
        manifest_content_id = scoped_content_id(material)
        manifest_id = DecisionInputManifestId.new()

        def operation(context: Any) -> None:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT decision_input_manifest_id, manifest_content_id FROM "
                "portfolio.decision_input_manifests WHERE source_kind = ? "
                "AND source_id = ?",
                [material["source_kind"], material["source_id"]],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(manifest_content_id):
                    raise DecisionInputManifestError(
                        "decision-input source evidence changed"
                    )
                return
            connection.execute(
                "INSERT INTO portfolio.decision_input_manifests VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    manifest_id.value,
                    material["source_kind"],
                    material["source_id"],
                    str(manifest_content_id),
                    _json(material["source_snapshot_content_ids"]),
                    _json(material["dependency_manifest_content_ids"]),
                    material["information_class"].value,
                    material["temporal_contract_kind"].value,
                    material["lineage_completeness"].value,
                    material["safety_status"].value,
                    material["structurally_decision_eligible"],
                    _json(material["licensing_classes"]),
                    material["conformance_status"],
                    _json(material["findings"]),
                    context.recorded_at,
                ],
            )

        self._project.services.transactions.run(
            "decision_input_manifest_register", operation
        )
        result = self._by_source(material["source_kind"], material["source_id"])
        if result is None:
            raise DecisionInputManifestError("decision-input manifest was not committed")
        return result

    def _licensing_classes(self, composite_snapshot_id: object) -> tuple[str, ...]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        members = connection.execute(
            "SELECT database_name, market_snapshot_id FROM "
            "research.composite_snapshot_members WHERE composite_snapshot_id = ? "
            "ORDER BY database_name",
            [composite_snapshot_id],
        ).fetchall()
        classes: set[str] = set()
        for database_name, snapshot_id in members:
            escaped = f"market_{database_name}".replace('"', '""')
            sequence = connection.execute(
                f'SELECT catalog_sequence FROM "{escaped}".snapshots.market_snapshots '
                "WHERE market_snapshot_id = ?",
                [snapshot_id],
            ).fetchone()
            if sequence is None:
                raise DecisionInputManifestError(
                    "composite snapshot member is unavailable"
                )
            definitions = connection.execute(
                f'SELECT definition_json FROM "{escaped}".catalog.source_versions '
                "WHERE catalog_sequence <= ?",
                [sequence[0]],
            ).fetchall()
            for (encoded,) in definitions:
                value = json.loads(encoded)
                licensing = value.get("licensing_class")
                if isinstance(licensing, str) and licensing:
                    classes.add(licensing)
        return tuple(sorted(classes or {"unclassified"}))


def _external_material(declaration: ExternalDecisionInputDeclaration) -> dict[str, Any]:
    findings = tuple(
        dict.fromkeys(
            (
                *declaration.findings,
                *_safety_findings(
                    declaration.information_class,
                    declaration.temporal_contract_kind,
                    declaration.lineage_completeness,
                    declaration.safety_status,
                    declaration.structurally_decision_eligible,
                ),
            )
        )
    )
    return {
        "schema": "persistra.portfolio.decision_input_manifest@1",
        "source_kind": "external_strategy",
        "source_id": str(declaration.source_content_id),
        "source_snapshot_content_ids": (),
        "dependency_manifest_content_ids": (declaration.source_content_id,),
        "information_class": declaration.information_class,
        "temporal_contract_kind": declaration.temporal_contract_kind,
        "lineage_completeness": declaration.lineage_completeness,
        "safety_status": declaration.safety_status,
        "structurally_decision_eligible": declaration.structurally_decision_eligible,
        "licensing_classes": tuple(sorted(declaration.licensing_classes)),
        "conformance_status": declaration.conformance_status,
        "findings": findings,
    }


def _manifest_material(manifest: DecisionInputManifestRef) -> dict[str, Any]:
    return {
        "schema": "persistra.portfolio.decision_input_manifest@1",
        "source_kind": manifest.source_kind,
        "source_id": manifest.source_id,
        "source_snapshot_content_ids": manifest.source_snapshot_content_ids,
        "dependency_manifest_content_ids": manifest.dependency_manifest_content_ids,
        "information_class": manifest.information_class,
        "temporal_contract_kind": manifest.temporal_contract_kind,
        "lineage_completeness": manifest.lineage_completeness,
        "safety_status": manifest.safety_status,
        "structurally_decision_eligible": manifest.structurally_decision_eligible,
        "licensing_classes": manifest.licensing_classes,
        "conformance_status": manifest.conformance_status,
        "findings": manifest.findings,
    }


def _safety_findings(
    information: InformationClass,
    temporal: TemporalContractKind,
    lineage: LineageCompleteness,
    safety: SafetyStatus,
    eligible: bool,
) -> tuple[str, ...]:
    findings: list[str] = []
    if information in {InformationClass.LABEL, InformationClass.RETROSPECTIVE}:
        findings.append("decision_input.information_class.forbidden")
    elif information is InformationClass.OPAQUE:
        findings.append("decision_input.information_class.opaque")
    if temporal is TemporalContractKind.OPAQUE:
        findings.append("decision_input.temporal_contract.opaque")
    if lineage is not LineageCompleteness.COMPLETE:
        findings.append("decision_input.lineage.incomplete")
    if safety is SafetyStatus.UNSAFE:
        findings.append("decision_input.safety.unsafe")
    if not eligible:
        findings.append("decision_input.structurally_ineligible")
    return tuple(findings)


def _json(value: object) -> str:
    return json.dumps(
        value,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


__all__ = ["DecisionInputService"]
