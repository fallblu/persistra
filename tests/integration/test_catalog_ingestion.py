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
    DispositionGroupId,
    IngestionRecord,
    MarketSnapshotId,
    RevisionEffect,
    SourceDefinition,
    SourceRef,
)
from persistra.catalog.services import SnapshotService
from persistra.db import DatabaseName, DatabaseRole, MaintenanceIntent, MarketDatabase
from persistra.db.connection import ManagedConnection, create_database_file
from persistra.domain import ContentId, FixedClock, QualifiedName
from persistra.errors import (
    BatchConflictError,
    CapabilityUnavailableError,
    CatalogDefinitionError,
    CatalogReferenceError,
    ValidationTokenError,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
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
        assert at_one.observations[0].payload == (("value", "100"),)
        assert at_two.observations[0].payload == (("value", "110"),)

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
        assert project.services.ingestion.quarantine.findings(
            quarantined_rows[0].quarantine_id
        )[0].reason_code == "ingestion.availability.before_event"

        retraction = IngestionRecord(
            natural_key=_record("ignored").natural_key,
            payload=(),
            event_at=NOW - timedelta(days=1),
            available_at=NOW,
            source_record_key="A:2026-01-09",
            source_revision_key="retraction-1",
            revision_effect=RevisionEffect.RETRACT,
            retraction_target_revision_id=at_two.observations[0].revision_id,
            retraction_reason_code="provider.deleted",
            retraction_evidence_content_id=_content(b"provider-deletion"),
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
        assert selected.observations == ()
        assert selected.audits[0].state == "retracted"
        history = project.services.catalog.revisions.history(
            _header("unused").dataset,
            natural_key=retraction.natural_key,
        )
        assert [item.effect for item in history] == [
            RevisionEffect.UPSERT,
            RevisionEffect.UPSERT,
            RevisionEffect.RETRACT,
        ]
        stale_retraction = replace(
            retraction,
            source_revision_key="retraction-stale",
            retraction_target_revision_id=at_two.observations[0].revision_id,
        )
        stale_result = project.services.ingestion.submit(
            _header("stale-retraction"), (stale_retraction,)
        )
        assert stale_result.status is BatchStatus.QUARANTINED
        assert project.services.ingestion.quarantine.list(
            batch_id=stale_result.batch_id
        )[0].reason_code == "ingestion.retraction.target_not_head"
        remediation_header = _header("remediation")
        project.services.ingestion.begin(
            remediation_header,
            parent_batch_id=quarantined.batch_id,
            parent_submitted_record_id=quarantined_rows[0].submitted_record_id,
            remediation_relationship="corrects",
        )
        with pytest.raises(CatalogDefinitionError, match="original relationship"):
            project.services.ingestion.quarantine.remediate(
                quarantined_rows[0].quarantine_id,
                header=remediation_header,
                records=(),
                relationship="replaces",
            )
        remediation = project.services.ingestion.quarantine.remediate(
            quarantined_rows[0].quarantine_id,
            header=remediation_header,
            records=(
                replace(
                    _record("remediated"),
                    natural_key=(("instrument", "B"), ("date", "2026-01-09")),
                ),
            ),
        )
        assert remediation.counts.accepted_new == 1
        remediation_history = (
            project.services.ingestion.quarantine.remediation_history(
                quarantined_rows[0].quarantine_id
            )
        )
        assert remediation_history.state == "resolved_new"
        assert remediation_history.attempts[0].accepted_new == 1
        assert remediation_history.attempts[0].child_batch_id == remediation.batch_id
        with pytest.raises(CatalogDefinitionError, match="already has a remediation"):
            project.services.ingestion.quarantine.remediate(
                quarantined_rows[0].quarantine_id,
                header=_header("duplicate-remediation"),
                records=(
                    replace(
                        _record("duplicate-remediation"),
                        natural_key=(("instrument", "C"), ("date", "2026-01-09")),
                    ),
                ),
            )
        stale_quarantine = project.services.ingestion.quarantine.list(
            batch_id=stale_result.batch_id
        )[0]
        failed_remediation = project.services.ingestion.quarantine.remediate(
            stale_quarantine.quarantine_id,
            header=_header("failed-remediation"),
            records=(
                replace(
                    _record("still-invalid", NOW - timedelta(days=2)),
                    natural_key=(("instrument", "D"), ("date", "2026-01-09")),
                ),
            ),
        )
        assert failed_remediation.status is BatchStatus.QUARANTINED
        successful_retry = project.services.ingestion.quarantine.remediate(
            stale_quarantine.quarantine_id,
            header=_header("successful-remediation-retry"),
            records=(
                replace(
                    _record("retry-valid"),
                    natural_key=(("instrument", "D"), ("date", "2026-01-09")),
                ),
            ),
        )
        assert successful_retry.counts.accepted_new == 1
        retry_history = project.services.ingestion.quarantine.remediation_history(
            stale_quarantine.quarantine_id
        )
        assert retry_history.state == "resolved_new"
        assert len(retry_history.attempts) == 2
        event_names = {
            item["event_name"] for item in project.services.diagnostics.events(limit=100)
        }
        assert {
            "persistra.catalog.source_registered",
            "persistra.catalog.dataset_registered",
            "persistra.ingestion.batch_created",
            "persistra.ingestion.batch_staged",
            "persistra.ingestion.batch_validated",
            "persistra.ingestion.validation_attempt_completed",
            "persistra.snapshot.market_created",
            "persistra.ingestion.remediation_linked",
        } <= event_names
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
    config_path = root / "persistra.toml"
    config_text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        config_text.replace(
            'path = ".persistra/market.duckdb"',
            f'path = "{copy_path}"',
        ).replace("verify_copy_on_open = false", "verify_copy_on_open = true"),
        encoding="utf-8",
    )
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
        assert composite.members[0].verified_copy_id == copy.copy_id
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
        assert reopened.observations[0].payload == (("value", "100"),)


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
        revision_key_conflict = project.services.ingestion.submit(
            _header("revision-key-conflict"),
            (replace(_record("101"), source_revision_key="revision-100"),),
        )
        assert revision_key_conflict.status is BatchStatus.QUARANTINED

        second_dataset = replace(
            dataset, name=QualifiedName("example.daily_values_two")
        )
        project.services.catalog.datasets.register(second_dataset)
        independent = project.services.ingestion.submit(
            _header("independent", "example.daily_values_two"), (_record("100"),)
        )
        assert independent.counts.accepted_new == 1


def test_streaming_staging_resumes_prefix_and_aborts(tmp_path: Path) -> None:
    root = _project(tmp_path)
    source, dataset = _definitions()
    dataset = replace(dataset, staging_chunk_rows=1)
    first = _record("100")
    second = replace(
        _record("110"),
        natural_key=(("instrument", "B"), ("date", "2026-01-09")),
    )

    def interrupted_records() -> Iterator[IngestionRecord]:
        yield first
        raise RuntimeError("adapter interrupted")

    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        project.services.catalog.sources.register(source)
        project.services.catalog.datasets.register(dataset)
        handle = project.services.ingestion.begin(_header("resumable"))
        with pytest.raises(RuntimeError, match="adapter interrupted"):
            project.services.ingestion.stage(handle.batch_id, interrupted_records())
        assert project.services.ingestion.get(handle.batch_id).status is BatchStatus.STAGING
        resumed = project.services.ingestion.resume_staging(
            handle.batch_id, (first, second)
        )
        assert resumed.status is BatchStatus.STAGED
        validation = project.services.ingestion.validate(handle.batch_id)
        result = project.services.ingestion.commit(
            handle.batch_id, validation_token=validation.token
        )
        assert result.counts.accepted_new == 2
        assert project.services.ingestion.submit(
            _header("resumable"), (first, second)
        ) == result
        with pytest.raises(BatchConflictError, match="stored content prefix"):
            project.services.ingestion.submit(
                _header("resumable"), (replace(first, payload=(("value", "bad"),)), second)
            )
        with pytest.raises(BatchConflictError, match="expectation"):
            project.services.ingestion.submit(
                replace(
                    _header("resumable"),
                    expected_batch_content_id=_content(b"wrong-terminal-expectation"),
                ),
                (first, second),
            )
        with pytest.raises(BatchConflictError, match="expected ID"):
            project.services.ingestion.submit(
                replace(
                    _header("wrong-new-expectation"),
                    expected_batch_content_id=_content(b"wrong-new-expectation"),
                ),
                (first,),
            )

        aborted = project.services.ingestion.begin(_header("abort"))
        with pytest.raises(RuntimeError, match="adapter interrupted"):
            project.services.ingestion.stage(aborted.batch_id, interrupted_records())
        aborted_result = project.services.ingestion.abort_batch(aborted.batch_id)
        assert aborted_result.status is BatchStatus.ABORTED
        assert aborted_result.counts.rejected == 1
        assert project.services.ingestion.abort_batch(aborted.batch_id) == aborted_result


def test_validation_quarantines_entire_in_batch_revision_conflict(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    source, dataset = _definitions()
    first = replace(_record("100"), source_revision_key="shared-revision")
    second = replace(
        _record("110"),
        natural_key=(("instrument", "B"), ("date", "2026-01-09")),
        source_revision_key="shared-revision",
    )
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        project.services.catalog.sources.register(source)
        project.services.catalog.datasets.register(dataset)
        handle = project.services.ingestion.begin(_header("cross-record-conflict"))
        project.services.ingestion.stage(handle.batch_id, (first, second))
        validation = project.services.ingestion.validate(handle.batch_id)
        assert validation.proposed_status is BatchStatus.QUARANTINED
        assert validation.quarantined_count == 2
        result = project.services.ingestion.commit(
            handle.batch_id, validation_token=validation.token
        )
        assert result.status is validation.proposed_status
        assert result.counts.quarantined == validation.quarantined_count
        quarantined = project.services.ingestion.quarantine.list(batch_id=handle.batch_id)
        assert len(quarantined) == 2
        assert {item.reason_code for item in quarantined} == {
            "ingestion.revision_key.conflict"
        }


def test_batch_contracts_and_in_batch_head_evolution_are_validated(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    source, dataset = _definitions()
    unsupported = replace(
        source,
        name=QualifiedName("example.unsupported"),
        provider_display_name="Unsupported",
    )
    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        project.services.catalog.sources.register(source)
        project.services.catalog.sources.register(unsupported)
        project.services.catalog.datasets.register(dataset)
        with pytest.raises(CatalogDefinitionError, match="not supported"):
            project.services.ingestion.begin(
                replace(
                    _header("unsupported-source"),
                    source=SourceRef(unsupported.name, 1),
                )
            )
        with pytest.raises(CatalogDefinitionError, match="adapter"):
            project.services.ingestion.begin(
                replace(
                    _header("wrong-adapter"),
                    adapter=ComponentRef(QualifiedName("example.wrong_adapter"), "1.0"),
                )
            )

        project.services.ingestion.submit(_header("seed-head"), (_record("100"),))
        seeded_head = project.services.catalog.revisions.history(
            _header("unused").dataset
        )[0]
        upsert = replace(_record("110"), source_revision_key="head-upsert")
        retraction = IngestionRecord(
            natural_key=upsert.natural_key,
            payload=(),
            event_at=NOW - timedelta(days=1),
            available_at=NOW,
            source_revision_key="head-retraction",
            revision_effect=RevisionEffect.RETRACT,
            retraction_target_revision_id=seeded_head.revision_id,
            retraction_reason_code="provider.deleted",
            retraction_evidence_content_id=_content(b"head-retraction"),
        )
        handle = project.services.ingestion.begin(_header("head-evolution"))
        project.services.ingestion.stage(handle.batch_id, (upsert, retraction))
        validation = project.services.ingestion.validate(handle.batch_id)
        assert validation.proposed_status is BatchStatus.COMMITTED_WITH_QUARANTINE
        assert validation.quarantined_count == 1
        result = project.services.ingestion.commit(
            handle.batch_id, validation_token=validation.token
        )
        assert result.status is validation.proposed_status
        assert result.counts.quarantined == validation.quarantined_count
        current_head = project.services.catalog.revisions.history(
            _header("unused").dataset
        )[-1]
        duplicate_retraction = replace(
            retraction,
            source_revision_key="duplicate-retraction",
            retraction_target_revision_id=current_head.revision_id,
        )
        duplicate_handle = project.services.ingestion.begin(
            _header("duplicate-retractions")
        )
        project.services.ingestion.stage(
            duplicate_handle.batch_id,
            (duplicate_retraction, duplicate_retraction),
        )
        duplicate_validation = project.services.ingestion.validate(
            duplicate_handle.batch_id
        )
        assert duplicate_validation.quarantined_count == 0
        duplicate_result = project.services.ingestion.commit(
            duplicate_handle.batch_id,
            validation_token=duplicate_validation.token,
        )
        assert duplicate_result.counts.accepted_revision == 1
        assert duplicate_result.counts.duplicate_ignored == 1


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE catalog.canonical_revisions "
        "SET canonical_payload_json = '[[\"value\",\"tampered\"]]'",
        "UPDATE catalog.canonical_revisions "
        "SET natural_key_json = '[[\"instrument\",\"TAMPERED\"]]'",
        "UPDATE catalog.canonical_retractions "
        "SET retraction_reason_code = 'tampered.reason'",
        "UPDATE catalog.validation_attempts "
        "SET validation_token_content_id = 'sha256:"
        + "0" * 64
        + "'",
        "UPDATE catalog.dataset_state SET revision_count = revision_count + 1",
    ],
)
def test_snapshot_integrity_rebuild_detects_count_preserving_tampering(
    tmp_path: Path, mutation: str
) -> None:
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
        project.services.ingestion.submit(_header("snapshot-source"), (_record("100"),))
        head = project.services.catalog.revisions.history(_header("unused").dataset)[0]
        project.services.ingestion.submit(
            _header("snapshot-retraction"),
            (
                IngestionRecord(
                    natural_key=head.natural_key,
                    payload=(),
                    event_at=NOW - timedelta(days=1),
                    available_at=NOW,
                    source_revision_key="snapshot-retraction",
                    revision_effect=RevisionEffect.RETRACT,
                    retraction_target_revision_id=head.revision_id,
                    retraction_reason_code="provider.deleted",
                    retraction_evidence_content_id=_content(b"snapshot-retraction"),
                ),
            ),
        )
        snapshot = project.services.snapshots.create()

    connection = ManagedConnection(root / ".persistra" / "market.duckdb", read_only=False)
    try:
        connection.execute(mutation)
        connection.execute("CHECKPOINT")
    finally:
        connection.close()

    with Project.open(root, mode=ProjectMode.READ_ONLY) as project:
        with pytest.raises(CatalogDefinitionError, match="does not rebuild"):
            project.services.snapshots.latest()
        with pytest.raises(CatalogDefinitionError, match="does not rebuild"):
            project.services.snapshots.select(
                _header("unused").dataset,
                snapshot=snapshot,
                public_cutoff=NOW + timedelta(days=1),
                project_cutoff=NOW + timedelta(days=1),
            )


def test_quarantine_queries_route_explicitly_with_multiple_markets(tmp_path: Path) -> None:
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
        result = project.services.ingestion.submit(
            _header("routed-quarantine"),
            (_record("invalid", NOW - timedelta(days=2)),),
        )
        quarantine_id = project.services.ingestion.quarantine.list(
            batch_id=result.batch_id
        )[0].quarantine_id

    secondary = root / ".persistra" / "secondary.duckdb"
    create_database_file(
        secondary,
        role=DatabaseRole.MARKET,
        project_id=None,
        disposable=False,
        clock=FixedClock(NOW),
    )
    with (root / "persistra.toml").open("a", encoding="utf-8") as config:
        config.write(
            '\n[databases.markets.secondary]\npath = ".persistra/secondary.duckdb"\n'
            "verify_copy_on_open = false\n"
        )
    with Project.open(root, mode=ProjectMode.READ_ONLY) as project:
        with pytest.raises(CapabilityUnavailableError, match="explicit"):
            project.services.ingestion.quarantine.findings(quarantine_id)
        findings = project.services.ingestion.quarantine.findings(
            quarantine_id, market=DatabaseName("primary")
        )
        assert findings[0].reason_code == "ingestion.availability.before_event"
        history = project.services.ingestion.quarantine.remediation_history(
            quarantine_id, market=DatabaseName("primary")
        )
        assert history.state == "open"


def test_snapshot_source_state_is_isolated_by_source_version(tmp_path: Path) -> None:
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
        project.services.ingestion.submit(_header("source-v1"), (_record("100"),))
        first_snapshot = project.services.snapshots.create()

        project.services.catalog.sources.register(
            replace(source, provider_display_name="Synthetic version 2")
        )
        project.services.catalog.datasets.register(
            replace(
                dataset,
                supported_sources=(SourceRef(source.name, 2),),
            )
        )
        second_header = replace(
            _header("source-v2"),
            source=SourceRef(source.name, 2),
            dataset=DatasetRef(dataset.name, 2),
        )
        second_record = replace(
            _record("200"),
            natural_key=(("instrument", "B"), ("date", "2026-01-09")),
            source_record_key="B:2026-01-09",
        )
        project.services.ingestion.submit(second_header, (second_record,))
        second_snapshot = project.services.snapshots.create()

    connection = ManagedConnection(root / ".persistra" / "market.duckdb", read_only=True)
    try:
        first_state = connection.execute(
            "SELECT state_content_id FROM snapshots.snapshot_source_state "
            "WHERE market_snapshot_id = ? AND source_version = 1",
            [first_snapshot.snapshot_id.value],
        ).fetchone()[0]
        second_state = connection.execute(
            "SELECT state_content_id FROM snapshots.snapshot_source_state "
            "WHERE market_snapshot_id = ? AND source_version = 1",
            [second_snapshot.snapshot_id.value],
        ).fetchone()[0]
    finally:
        connection.close()
    assert first_state == second_state


def test_atomic_correction_groups_and_already_retracted_heads(tmp_path: Path) -> None:
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
        project.services.ingestion.submit(_header("correction-seed"), (_record("100"),))
        old_head = project.services.catalog.revisions.history(
            _header("unused").dataset
        )[-1]
        correction_group = DispositionGroupId.new()
        retract = IngestionRecord(
            natural_key=old_head.natural_key,
            payload=(),
            event_at=NOW - timedelta(days=1),
            available_at=NOW,
            source_revision_key="natural-key-retract",
            revision_effect=RevisionEffect.RETRACT,
            retraction_target_revision_id=old_head.revision_id,
            retraction_reason_code="provider.natural_key_correction",
            retraction_evidence_content_id=_content(b"key-correction"),
            disposition_group_id=correction_group,
        )
        replacement = replace(
            _record("corrected"),
            natural_key=(("instrument", "B"), ("date", "2026-01-09")),
            source_record_key="B:2026-01-09",
            disposition_group_id=correction_group,
        )
        corrected = project.services.ingestion.submit(
            _header("atomic-correction"), (retract, replacement)
        )
        assert corrected.counts.accepted_revision == 1
        assert corrected.counts.accepted_new == 1

        retracted_head = project.services.catalog.revisions.history(
            _header("unused").dataset,
            natural_key=old_head.natural_key,
        )[-1]
        repeated_retraction = replace(
            retract,
            source_revision_key="already-retracted",
            retraction_target_revision_id=retracted_head.revision_id,
            retraction_reason_code="provider.withdrawn",
            disposition_group_id=None,
        )
        repeated = project.services.ingestion.submit(
            _header("already-retracted"), (repeated_retraction,)
        )
        assert repeated.status is BatchStatus.QUARANTINED
        assert project.services.ingestion.quarantine.list(
            batch_id=repeated.batch_id
        )[0].reason_code == "ingestion.retraction.target_not_head"

        invalid_group = DispositionGroupId.new()
        invalid = replace(
            _record("invalid-group", NOW - timedelta(days=2)),
            natural_key=(("instrument", "C"), ("date", "2026-01-09")),
            source_record_key="C:2026-01-09",
            disposition_group_id=invalid_group,
        )
        otherwise_valid = replace(
            _record("valid-group"),
            natural_key=(("instrument", "D"), ("date", "2026-01-09")),
            source_record_key="D:2026-01-09",
            disposition_group_id=invalid_group,
        )
        grouped = project.services.ingestion.submit(
            _header("atomic-quarantine"), (invalid, otherwise_valid)
        )
        assert grouped.status is BatchStatus.QUARANTINED
        assert grouped.counts.quarantined == 2
        quarantined = project.services.ingestion.quarantine.list(batch_id=grouped.batch_id)
        assert {item.disposition_group_id for item in quarantined} == {invalid_group}


def test_latest_warning_survives_composite_binding(tmp_path: Path) -> None:
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
        project.services.ingestion.submit(_header("pinned"), (_record("100"),))
        pinned = project.services.snapshots.create()
        project.services.ingestion.submit(_header("unpinned"), (_record("110"),))
        latest = project.services.snapshots.latest()
        assert latest is not None
        assert latest.snapshot_id == pinned.snapshot_id
        assert latest.warnings == ("snapshot.catalog_unpinned",)

    with Project.open(root, mode=ProjectMode.RESEARCH_WRITE) as project:
        latest = project.services.snapshots.latest(market=DatabaseName("primary"))
        assert latest is not None
        composite = project.services.snapshots.create_composite(
            {DatabaseName("primary"): latest}
        )
        assert composite.members[0].warnings == ("snapshot.catalog_unpinned",)


def test_snapshot_failure_is_reported_after_batch_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    source, dataset = _definitions()

    def fail_snapshot(_service: SnapshotService) -> None:
        raise RuntimeError("injected snapshot failure")

    with Project.open(
        root,
        mode=ProjectMode.MARKET_WRITE,
        writable_market=DatabaseName("primary"),
        clock=FixedClock(NOW),
    ) as project:
        project.services.catalog.sources.register(source)
        project.services.catalog.datasets.register(dataset)
        handle = project.services.ingestion.begin(_header("snapshot-failure"))
        project.services.ingestion.stage(handle.batch_id, (_record("100"),))
        validation = project.services.ingestion.validate(handle.batch_id)
        monkeypatch.setattr(SnapshotService, "create", fail_snapshot)
        result = project.services.ingestion.commit(
            handle.batch_id,
            validation_token=validation.token,
            create_snapshot=True,
        )
        assert result.status is BatchStatus.COMMITTED
        assert result.snapshot is None
        assert result.snapshot_failure is not None
        assert result.snapshot_failure.reason_code == "snapshot.create_failed"
        assert project.services.catalog.revisions.history(_header("unused").dataset)
