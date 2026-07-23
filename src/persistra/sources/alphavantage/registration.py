"""This module contains Alpha Vantage source and dataset registration for the catalog.

These definitions record the provenance and license of Alpha Vantage data. Ingestion is typed-
direct. Thus, each family goes through its matching typed canonical service. It does not go
through the generic batch pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from persistra.catalog import (
    ComponentRef,
    DatasetDefinition,
    SourceDefinition,
    SourceRef,
)
from persistra.domain import ContentId, QualifiedName

if TYPE_CHECKING:
    from persistra.catalog import ResolvedSourceRef
    from persistra.project import Project

ALPHAVANTAGE_SOURCE = SourceRef(QualifiedName("alphavantage.api"), 1)
ALPHAVANTAGE_ADAPTER = ComponentRef(QualifiedName("alphavantage.adapter"), "1.0")

_DATASET_FAMILIES: tuple[tuple[str, str, str], ...] = (
    ("alphavantage.equity_bars", "persistra.grain.instrument", "persistra.grain.session"),
    ("alphavantage.equity_actions", "persistra.grain.security", "persistra.grain.event"),
    ("alphavantage.trading_status", "persistra.grain.instrument", "persistra.grain.event"),
    ("alphavantage.macro_series", "persistra.grain.series", "persistra.grain.release"),
    ("alphavantage.rate_curves", "persistra.grain.curve", "persistra.grain.observation"),
    ("alphavantage.benchmark_series", "persistra.grain.benchmark", "persistra.grain.session"),
    ("alphavantage.crypto_bars", "persistra.grain.instrument", "persistra.grain.session"),
    ("alphavantage.fx_bars", "persistra.grain.instrument", "persistra.grain.session"),
)


def _content(label: str) -> ContentId:
    return ContentId.from_bytes(label.encode())


def alphavantage_source_definition() -> SourceDefinition:
    """Return the immutable Alpha Vantage source definition."""
    return SourceDefinition(
        name=ALPHAVANTAGE_SOURCE.name,
        provider_display_name="Alpha Vantage",
        licensing_class="licensed_no_redistribution",
        adapter_contract=ALPHAVANTAGE_ADAPTER,
        adapter_version_range=">=1,<2",
        conformance_content_id=_content("alphavantage.conformance@1"),
        source_key_schema_content_id=_content("alphavantage.source_key@1"),
        revision_token_policy=QualifiedName("alphavantage.revision_token"),
        timestamp_precision="second",
        timezone_guarantee="utc",
        raw_archive_policy=QualifiedName("alphavantage.raw_archive"),
        redistributable=False,
        enabled=True,
    )


def alphavantage_dataset_definitions() -> tuple[DatasetDefinition, ...]:
    """Return one provenance dataset definition for each Alpha Vantage family."""
    return tuple(
        DatasetDefinition(
            name=QualifiedName(name),
            record_model=ComponentRef(QualifiedName(f"{name}.record"), "1.0"),
            entity_grain=QualifiedName(entity_grain),
            time_grain=QualifiedName(time_grain),
            natural_key_schema_content_id=_content(f"{name}.natural_key@1"),
            row_schema_content_id=_content(f"{name}.row@1"),
            revision_policy=QualifiedName("alphavantage.append_revision"),
            retractions_allowed=False,
            retraction_schema_content_id=None,
            availability_policy=QualifiedName("alphavantage.ingestion_bounded"),
            validation_policy=QualifiedName("alphavantage.typed_direct"),
            supported_sources=(ALPHAVANTAGE_SOURCE,),
        )
        for name, entity_grain, time_grain in _DATASET_FAMILIES
    )


def register_alphavantage(project: Project) -> ResolvedSourceRef:
    """Idempotently register the Alpha Vantage source and its family datasets."""
    resolved = project.services.catalog.sources.register(alphavantage_source_definition())
    for dataset in alphavantage_dataset_definitions():
        project.services.catalog.datasets.register(dataset)
    return resolved
