from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from persistra import Project, ProjectMode
from persistra.catalog import (
    BatchHeader,
    BatchStatus,
    ComponentRef,
    DatasetDefinition,
    DatasetRef,
    IngestionRecord,
    MarketSnapshotId,
    RevisionEffect,
    SourceDefinition,
    SourceRef,
)
from persistra.db import DatabaseName, DatabaseRole, MaintenanceIntent, MarketDatabase
from persistra.db.connection import create_database_file
from persistra.domain import ContentId, FixedClock, QualifiedName
from persistra.errors import BatchConflictError, CatalogReferenceError, ValidationTokenError

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 1, 10, 12, tzinfo=UTC)


def _content(value: bytes) -> ContentId:
    return ContentId.from_bytes(value)


def _project(tmp_path: Path) -> Path:
    layout = Project.init(tmp_path / "project")
    market = layout.state_path / "market.duckdb"
    create_database_file(
        market,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=FixedClock(NOW),
    )
    with layout.config_path.open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.primary]\npath = ".persistra/market.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    return layout.root


def _definitions() -> tuple[SourceDefinition, DatasetDefinition]:
    source_ref = SourceRef(QualifiedName("example.synthetic"), 1)
    source = SourceDefinition(
        name=source_ref.name,
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
    dataset = DatasetDefinition(
        name=QualifiedName("example.daily_values"),
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
        supported_sources=(source_ref,),
    )
    return source, dataset


def _header(key: str, dataset_name: str = "example.daily_values") -> BatchHeader:
    return BatchHeader(
        SourceRef(QualifiedName("example.synthetic"), 1),
        DatasetRef(QualifiedName(dataset_name), 1),
        key,
        ComponentRef(QualifiedName("example.adapter"), "1.0"),
    )


def _record(value: str, available_at: datetime = NOW) -> IngestionRecord:
    return IngestionRecord(
        natural_key=(("instrument", "A"), ("date", "2026-01-09")),
        payload=(("value", value),),
        event_at=NOW - timedelta(days=1),
        available_at=available_at,
        source_record_key="A:2026-01-09",
        source_revision_key=f"revision-{value}",
    )


def test_registry_ingestion_retry_quarantine_and_snapshots(tmp_path: Path) -> None:
    root = _project(tmp_path)
    source, dataset = _definitions()
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        resolved_source = project.services.catalog.sources.register(source)
        assert project.services.catalog.sources.register(source) == resolved_source
        assert project.services.catalog.sources.get(resolved_source) == source
        resolved_dataset = project.services.catalog.datasets.register(dataset)
        assert project.services.catalog.datasets.get(resolved_dataset) == dataset

        first = project.services.ingestion.submit(_header("first"), (_record("100"),))
        assert first.status is BatchStatus.COMMITTED
        assert first.counts.accepted_new == 1
        assert project.services.ingestion.submit(
            _header("first"), (_record("100"),)
        ) == first
        with pytest.raises(BatchConflictError):
            project.services.ingestion.submit(_header("first"), (_record("101"),))

        snapshot_one = project.services.snapshots.create()
        second = project.services.ingestion.submit(_header("second"), (_record("110"),))
        assert second.counts.accepted_revision == 1
        snapshot_two = project.services.snapshots.create()
        assert project.services.snapshots.create() == snapshot_two

        cutoff = NOW + timedelta(days=1)
        at_one = project.services.snapshots.select(
            _header("unused").dataset,
            snapshot=snapshot_one,
            public_cutoff=cutoff,
            project_cutoff=cutoff,
        )
        at_two = project.services.snapshots.select(
            _header("unused").dataset,
            snapshot=snapshot_two,
            public_cutoff=cutoff,
            project_cutoff=cutoff,
        )
        assert at_one[0].payload == (("value", "100"),)
        assert at_two[0].payload == (("value", "110"),)

        quarantined = project.services.ingestion.submit(
            _header("bad-time"),
            (_record("invalid", NOW - timedelta(days=2)),),
        )
        assert quarantined.status is BatchStatus.QUARANTINED
        assert quarantined.counts.quarantined == 1
        quarantined_rows = project.services.ingestion.quarantine.list(
            batch_id=quarantined.batch_id
        )
        assert quarantined_rows[0].reason_code == "ingestion.availability.before_event"

        retraction = IngestionRecord(
            natural_key=_record("ignored").natural_key,
            payload=(),
            event_at=NOW - timedelta(days=1),
            available_at=NOW,
            source_record_key="A:2026-01-09",
            source_revision_key="retraction-1",
            revision_effect=RevisionEffect.RETRACT,
        )
        result = project.services.ingestion.submit(_header("retract"), (retraction,))
        assert result.counts.accepted_revision == 1
        snapshot_three = project.services.snapshots.create()
        selected = project.services.snapshots.select(
            _header("unused").dataset,
            snapshot=snapshot_three,
            public_cutoff=cutoff,
            project_cutoff=cutoff,
        )
        assert selected[0].effect is RevisionEffect.RETRACT
        history = project.services.catalog.revisions.history(
            _header("unused").dataset,
            natural_key=retraction.natural_key,
        )
        assert [item.effect for item in history] == [
            RevisionEffect.UPSERT,
            RevisionEffect.UPSERT,
            RevisionEffect.RETRACT,
        ]
    copy_path = tmp_path / "snapshot-copies" / "market.duckdb"
    copy_path.parent.mkdir()
    with Project.open(
        root,
        mode=ProjectMode.MAINTENANCE,
        maintenance_database=MarketDatabase(DatabaseName("primary")),
        maintenance_intent=MaintenanceIntent.SNAPSHOT_COPY,
        clock=FixedClock(NOW),
    ) as project:
        copy = project.services.databases.snapshot_copy(
            snapshot_id=snapshot_three.snapshot_id,
            destination=copy_path,
        )
        assert copy.destination == copy_path
    with Project.open(
        root,
        mode=ProjectMode.RESEARCH_WRITE,
        clock=FixedClock(NOW),
    ) as project:
        with pytest.raises(CatalogReferenceError, match="not committed"):
            project.services.snapshots.create_composite(
                {
                    DatabaseName("primary"): replace(
                        snapshot_three, snapshot_id=MarketSnapshotId.new()
                    )
                }
            )
        composite = project.services.snapshots.create_composite(
            {DatabaseName("primary"): snapshot_three}
        )
        assert project.services.snapshots.create_composite(
            {DatabaseName("primary"): snapshot_three}
        ) == composite
    with Project.open(root, mode=ProjectMode.READ_ONLY) as project:
        reopened = project.services.snapshots.select(
            _header("unused").dataset,
            snapshot=snapshot_one,
            public_cutoff=cutoff,
            project_cutoff=cutoff,
        )
        assert reopened[0].payload == (("value", "100"),)


def test_validation_token_failure_is_atomic_and_retryable(tmp_path: Path) -> None:
    root = _project(tmp_path)
    source, dataset = _definitions()
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        project.services.catalog.sources.register(source)
        project.services.catalog.datasets.register(dataset)
        handle = project.services.ingestion.begin(_header("manual"))
        project.services.ingestion.stage(handle.batch_id, (_record("100"),))
        validation = project.services.ingestion.validate(handle.batch_id)
        with pytest.raises(ValidationTokenError):
            project.services.ingestion.commit(
                handle.batch_id,
                validation_token=_content(b"wrong-token"),
            )
        assert project.services.ingestion.get(handle.batch_id).status is BatchStatus.VALIDATED
        assert project.services.catalog.revisions.history(_header("unused").dataset) == ()
        project.services.catalog.sources.register(
            replace(source, provider_display_name="Synthetic v2")
        )
        with pytest.raises(ValidationTokenError, match="catalog changed"):
            project.services.ingestion.commit(
                handle.batch_id,
                validation_token=validation.token,
            )
        validation = project.services.ingestion.validate(handle.batch_id)
        result = project.services.ingestion.commit(
            handle.batch_id,
            validation_token=validation.token,
        )
        assert result.counts.accepted_new == 1

        duplicate = project.services.ingestion.submit(
            _header("duplicate"), (_record("100"),)
        )
        assert duplicate.counts.duplicate_ignored == 1
        assert len(project.services.catalog.revisions.history(_header("unused").dataset)) == 1

        second_dataset = replace(
            dataset, name=QualifiedName("example.daily_values_two")
        )
        project.services.catalog.datasets.register(second_dataset)
        independent = project.services.ingestion.submit(
            _header("independent", "example.daily_values_two"), (_record("100"),)
        )
        assert independent.counts.accepted_new == 1
