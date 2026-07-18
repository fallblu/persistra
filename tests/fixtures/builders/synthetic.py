"""Synthetic custom-dataset family used to prove the contract kit standalone.

The dataset uses a nonreserved ``example.`` owner prefix (spec 03 §6.2) and rides
the generic catalog ingestion/selection machinery, so binding it to the family
harness exercises the whole kit without any built-in canonical family.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from support.env import NOW
from support.families import FamilyHarness, FamilyQuery

from persistra.catalog import (
    BatchHeader,
    CanonicalRevisionId,
    ComponentRef,
    DatasetDefinition,
    DatasetRef,
    IngestionRecord,
    RevisionEffect,
    SnapshotRef,
    SourceDefinition,
    SourceRef,
)
from persistra.domain import ContentId, QualifiedName, SchemaVersion
from persistra.domain.frames import ColumnDtype, ColumnSpec, FrameContract, build_frame

if TYPE_CHECKING:
    from datetime import datetime

    from persistra import Project
    from persistra.catalog import BatchResult, QuarantineId

_FACTS = json.loads((Path(__file__).resolve().parents[1] / "source" / "synthetic.json").read_text())
_SOURCE = SourceRef(QualifiedName("example.synthetic"), 1)
_DATASET = DatasetRef(QualifiedName("example.daily_values"), 1)
_EVENT_AT = NOW - timedelta(days=1)

SYNTHETIC_FRAME = FrameContract(
    name=QualifiedName("example.dataframe.synthetic"),
    version=SchemaVersion(1),
    columns=(
        ColumnSpec("revision_id", ColumnDtype.STRING),
        ColumnSpec("instrument", ColumnDtype.STRING),
        ColumnSpec("session_date", ColumnDtype.DATE),
        ColumnSpec("value", ColumnDtype.FLOAT),
        ColumnSpec("available_at", ColumnDtype.INSTANT),
        ColumnSpec("audit_state", ColumnDtype.STRING),
    ),
    ordering=("available_at", "revision_id"),
)


def _content(value: bytes) -> ContentId:
    return ContentId.from_bytes(value)


def source_definition() -> SourceDefinition:
    return SourceDefinition(
        name=_SOURCE.name,
        provider_display_name="Synthetic",
        licensing_class="redistributable",
        adapter_contract=ComponentRef(QualifiedName("example.adapter"), "1.0"),
        adapter_version_range=">=1,<2",
        conformance_content_id=_content(b"conformance"),
        source_key_schema_content_id=_content(b"source-key"),
        revision_token_policy=QualifiedName("example.revision_token"),
        timestamp_precision="microsecond",
        timezone_guarantee="utc",
        raw_archive_policy=QualifiedName("example.raw_archive"),
        redistributable=True,
        enabled=True,
    )


def dataset_definition() -> DatasetDefinition:
    return DatasetDefinition(
        name=_DATASET.name,
        record_model=ComponentRef(QualifiedName("example.record"), "1.0"),
        entity_grain=QualifiedName("example.instrument"),
        time_grain=QualifiedName("example.daily"),
        natural_key_schema_content_id=_content(b"natural-key"),
        row_schema_content_id=_content(b"row"),
        revision_policy=QualifiedName("example.append_revision"),
        retractions_allowed=True,
        retraction_schema_content_id=_content(b"retraction"),
        availability_policy=QualifiedName("example.explicit_availability"),
        validation_policy=QualifiedName("example.basic_validation"),
        supported_sources=(_SOURCE,),
    )


_ADAPTER = ComponentRef(QualifiedName("example.adapter"), "1.0")


def _header(key: str) -> BatchHeader:
    return BatchHeader(_SOURCE, _DATASET, key, _ADAPTER)


def _key(instrument: str) -> tuple[tuple[str, str], ...]:
    return (("instrument", instrument), ("date", _FACTS["session_date"]))


def _record(
    instrument: str, value: str, available_at: datetime, revision_key: str
) -> IngestionRecord:
    return IngestionRecord(
        natural_key=_key(instrument),
        payload=(("value", value),),
        event_at=_EVENT_AT,
        available_at=available_at,
        source_record_key=f"{instrument}:{_FACTS['session_date']}",
        source_revision_key=revision_key,
    )


class SyntheticFamilyHarness(FamilyHarness):
    """Binds the synthetic custom dataset to the generic contract suite."""

    label = "example.daily_values"
    frame_contract = SYNTHETIC_FRAME

    def register(self, project: Project) -> None:
        project.services.catalog.sources.register(source_definition())
        project.services.catalog.datasets.register(dataset_definition())

    def dataset(self) -> DatasetRef:
        return _DATASET

    def ingest_initial(self, project: Project) -> BatchResult:
        record = _record(
            _FACTS["instrument"], _FACTS["initial_value"], self.initial_available_at, "revision-1"
        )
        return project.services.ingestion.submit(_header("initial"), (record,))

    def ingest_correction(self, project: Project) -> BatchResult:
        record = _record(
            _FACTS["instrument"],
            _FACTS["correction_value"],
            self.correction_available_at,
            "revision-2",
        )
        return project.services.ingestion.submit(_header("correction"), (record,))

    def ingest_retraction(self, project: Project) -> BatchResult:
        head = self._head_revision(project)
        retraction = IngestionRecord(
            natural_key=_key(_FACTS["instrument"]),
            payload=(),
            event_at=_EVENT_AT,
            available_at=NOW,
            source_record_key=f"{_FACTS['instrument']}:{_FACTS['session_date']}",
            source_revision_key="retraction-1",
            revision_effect=RevisionEffect.RETRACT,
            retraction_target_revision_id=head,
            retraction_reason_code="provider.deleted",
            retraction_evidence_content_id=_content(b"provider-deletion"),
        )
        return project.services.ingestion.submit(_header("retract"), (retraction,))

    def ingest_invalid_group(self, project: Project) -> BatchResult:
        valid = _record(
            _FACTS["valid_partner_instrument"], _FACTS["initial_value"], NOW, "revision-valid"
        )
        invalid = _record(
            _FACTS["invalid_instrument"],
            _FACTS["initial_value"],
            NOW - timedelta(days=2),
            "revision-invalid",
        )
        return project.services.ingestion.submit(_header("invalid-group"), (valid, invalid))

    def remediate(self, project: Project, quarantine_id: QuarantineId) -> BatchResult:
        record = _record(
            _FACTS["remediation_instrument"], _FACTS["initial_value"], NOW, "revision-remediated"
        )
        return project.services.ingestion.quarantine.remediate(
            quarantine_id, header=_header("remediation"), records=(record,)
        )

    def pin_snapshot(self, project: Project) -> SnapshotRef:
        return project.services.snapshots.create()

    def query(
        self,
        project: Project,
        *,
        snapshot: object,
        public_cutoff: datetime,
        project_cutoff: datetime,
    ) -> FamilyQuery:
        assert isinstance(snapshot, SnapshotRef)
        selection = project.services.snapshots.select(
            _DATASET,
            snapshot=snapshot,
            public_cutoff=public_cutoff,
            project_cutoff=project_cutoff,
        )
        heads = tuple(
            (
                json.dumps(dict(observation.natural_key), sort_keys=True),
                observation.revision_id.to_wire(),
            )
            for observation in selection.observations
        )
        canonical_material = [
            [
                dict(observation.natural_key),
                dict(observation.payload),
                observation.revision_id.to_wire(),
            ]
            for observation in selection.observations
        ]
        canonical = json.dumps(sorted(canonical_material, key=repr), sort_keys=True).encode()
        rows = [
            {
                "revision_id": observation.revision_id.to_wire(),
                "instrument": dict(observation.natural_key)["instrument"],
                "session_date": _parse_session_date(str(dict(observation.natural_key)["date"])),
                "value": float(dict(observation.payload)["value"]),
                "available_at": observation.available_at,
                "audit_state": "available",
            }
            for observation in selection.observations
        ]
        frame = build_frame(SYNTHETIC_FRAME, rows)
        return FamilyQuery(
            canonical=canonical,
            row_count=len(selection.observations),
            audit_states=tuple(audit.state for audit in selection.audits),
            heads=heads,
            frame=frame,
        )

    def _head_revision(self, project: Project) -> CanonicalRevisionId:
        snapshot = project.services.snapshots.create()
        selection = project.services.snapshots.select(
            _DATASET,
            snapshot=snapshot,
            public_cutoff=NOW + timedelta(days=3650),
            project_cutoff=NOW + timedelta(days=3650),
        )
        for observation in selection.observations:
            if dict(observation.natural_key)["instrument"] == _FACTS["instrument"]:
                return observation.revision_id
        raise AssertionError("initial natural key is not selectable")


def _parse_session_date(text: str) -> date:
    year, month, day = (int(part) for part in text.split("-"))
    return date(year, month, day)
