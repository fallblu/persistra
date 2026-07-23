"""This module contains the project-owned services for canonical economic-data families."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from persistra.catalog.services import advance_catalog, insert_event
from persistra.db import ProjectMode
from persistra.domain import (
    ContentId,
    Currency,
    EntityId,
    NumericKind,
    QualifiedName,
    SchemaVersion,
    SourceNumeric,
    Unit,
    UnitSpec,
)
from persistra.domain.frames import build_frame
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    BenchmarkResolutionError,
    CapabilityUnavailableError,
    EstimateQueryError,
    FilingResolutionError,
    FundamentalMappingError,
    FundamentalQueryError,
    MacroQueryError,
    MarketDataLimitError,
    RateConventionError,
    RateUnavailableError,
)
from persistra.market.economic_frames import (
    ACTUALS_FRAME,
    BENCHMARK_CONSTITUENTS_FRAME,
    BENCHMARK_SERIES_FRAME,
    CONSENSUS_FRAME,
    ESTIMATES_FRAME,
    FILINGS_FRAME,
    MACRO_FRAME,
    RAW_FACTS_FRAME,
    RISK_FREE_FRAME,
)
from persistra.market.economic_models import (
    ActualObservation,
    BenchmarkConstituent,
    BenchmarkDefinition,
    BenchmarkId,
    BenchmarkQuery,
    BenchmarkSeriesObservation,
    BenchmarkVersionRef,
    ConsensusEstimate,
    EstimateMeasureDefinition,
    EstimateMeasureId,
    EstimateQuery,
    FactNumericKind,
    FilingId,
    FilingMode,
    FilingObservation,
    FundamentalMappingDefinition,
    FundamentalMappingId,
    FundamentalNormalizationId,
    FundamentalNormalizationRunId,
    FundamentalQuery,
    IndividualEstimate,
    MacroQuery,
    MacroRelease,
    MacroSeriesDefinition,
    MacroSeriesId,
    MacroSeriesRef,
    MacroVintageMode,
    NormalizedConceptDefinition,
    NormalizedConceptId,
    RawFundamentalFact,
    ResolvedBenchmarkVersionRef,
    ResolvedMacroSeriesRef,
    ResolvedRiskFreeCurveRef,
    RiskFreeCurveDefinition,
    RiskFreeCurveId,
    RiskFreeCurveRef,
    RiskFreePoint,
    RiskFreeQuery,
    Tenor,
    VintageCompleteness,
)
from persistra.reference.services import cutoff_sql, market_for_context

if TYPE_CHECKING:
    from collections.abc import Iterable

    import pandas as pd

    from persistra.db.connection import ManagedConnection
    from persistra.db.services import TransactionContext
    from persistra.project import Project
    from persistra.reference import AsOfContext, IssuerId


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _wire(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, SourceNumeric):
        return {
            "integral": value.integral,
            "kind": value.kind.value,
            "unit": str(value.unit.unit),
            "value": value.canonical_text,
        }
    if isinstance(value, EntityId | ContentId | QualifiedName | SchemaVersion | Currency):
        return str(value)
    if isinstance(value, UnitSpec):
        return {"numeric_kind": value.numeric_kind.value, "unit": str(value.unit)}
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _wire(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, dict):
        mapping = cast("dict[object, object]", value)
        return {str(key): _wire(item) for key, item in mapping.items()}
    if isinstance(value, tuple | list):
        sequence = cast("tuple[object, ...] | list[object]", value)
        return [_wire(item) for item in sequence]
    raise TypeError(f"unsupported economic identity value {type(value)!r}")


def _content_id(schema: str, value: object) -> ContentId:
    return ContentId.from_bytes(
        canonical_bytes({"schema": schema, "value": _wire(value)})
    )


def _safe(quality: str) -> str:
    return "safe" if quality in {"observed", "policy_derived"} else "unsafe"


def _uuid(value: EntityId | None) -> UUID | None:
    return None if value is None else value.value


def _source_numeric(value: SourceNumeric | None) -> Decimal | None:
    return None if value is None else value.envelope_value


def _occurrence_id(content_id: ContentId) -> UUID:
    return UUID(bytes=content_id.digest[:16])


def _insert_market_metadata(
    connection: ManagedConnection,
    *,
    revision_id: UUID,
    source_id: UUID | None,
    event_at: datetime | None,
    available_at: datetime,
    availability_quality: str,
    ingested_at: datetime,
    catalog_sequence: int,
    content_id: ContentId,
) -> None:
    connection.execute(
        "INSERT INTO canonical.market_revision_metadata "
        "(canonical_revision_id, source_id, event_at, available_at, "
        "availability_quality, ingested_at, catalog_sequence, content_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            revision_id,
            source_id,
            event_at,
            available_at,
            availability_quality,
            ingested_at,
            catalog_sequence,
            str(content_id),
        ],
    )


def _register_versioned(
    connection: ManagedConnection,
    *,
    table: str,
    id_column: str,
    version_column: str,
    name: QualifiedName,
    version: int,
    id_type: type[EntityId],
    content_id: ContentId,
    values: list[Any],
    insert_sql: str,
    change_kind: str,
    context: TransactionContext,
) -> tuple[EntityId, bool]:
    existing = connection.execute(
        f"SELECT {id_column}, definition_content_id FROM {table} "
        f"WHERE qualified_name = ? AND {version_column} = ?",
        [str(name), version],
    ).fetchone()
    if existing is not None:
        if existing[1] != str(content_id):
            raise FundamentalMappingError("definition version conflicts")
        return id_type.parse(existing[0]), False
    prior = connection.execute(
        f"SELECT {id_column}, {version_column} FROM {table} "
        "WHERE qualified_name = ? ORDER BY 2 DESC LIMIT 1",
        [str(name)],
    ).fetchone()
    if prior is not None and int(prior[1]) + 1 != version:
        raise FundamentalMappingError("definition versions must be contiguous")
    identity = id_type.new() if prior is None else id_type.parse(prior[0])
    sequence = advance_catalog(
        connection,
        change_kind=change_kind,
        entity_id=identity,
        change_content_id=content_id,
        recorded_at=context.recorded_at,
    )
    connection.execute(
        insert_sql,
        [identity.value, version, str(name), *values, str(content_id), sequence],
    )
    return identity, True


class FundamentalService:
    """This class represents filings, raw facts, curated concepts, mappings, and
    normalization."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def ingest_filing(self, observation: FilingObservation) -> FilingId:
        self._require_write()

        def operation(context: TransactionContext) -> FilingId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            content_id = _content_id("persistra.fundamental.filing", observation)
            duplicate = connection.execute(
                "SELECT canonical_revision_id FROM canonical.market_revision_metadata "
                "WHERE content_id = ?",
                [str(content_id)],
            ).fetchone()
            if duplicate is not None:
                return observation.filing_id
            sequence = advance_catalog(
                connection,
                change_kind="fundamental.filing_ingested",
                entity_id=observation.filing_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            report = connection.execute(
                "SELECT issuer_id, report_kind, fiscal_period_end FROM canonical.reports "
                "WHERE report_id = ?",
                [observation.report_id.value],
            ).fetchone()
            expected_report = (
                observation.issuer_id.value,
                observation.form_type,
                observation.report_period_end,
            )
            if report is None:
                connection.execute(
                    "INSERT INTO canonical.reports VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        observation.report_id.value,
                        *expected_report,
                        sequence,
                        context.recorded_at,
                    ],
                )
                insert_event(
                    connection,
                    event_name="persistra.fundamental.report_created",
                    aggregate_kind="persistra.aggregate.report",
                    aggregate_id=observation.report_id,
                    aggregate_sequence=1,
                    recorded_at=context.recorded_at,
                    payload={"report_id": observation.report_id},
                )
            elif report != expected_report:
                raise FilingResolutionError("report identity conflicts")
            filing = connection.execute(
                "SELECT accession_namespace, normalized_accession FROM canonical.filings "
                "WHERE filing_id = ?",
                [observation.filing_id.value],
            ).fetchone()
            expected_filing = (
                observation.accession_namespace,
                observation.normalized_accession,
            )
            if filing is None:
                connection.execute(
                    "INSERT INTO canonical.filings VALUES (?, ?, ?, ?, ?)",
                    [
                        observation.filing_id.value,
                        *expected_filing,
                        sequence,
                        context.recorded_at,
                    ],
                )
                insert_event(
                    connection,
                    event_name="persistra.fundamental.filing_created",
                    aggregate_kind="persistra.aggregate.filing",
                    aggregate_id=observation.filing_id,
                    aggregate_sequence=1,
                    recorded_at=context.recorded_at,
                    payload={"filing_id": observation.filing_id},
                )
            elif filing != expected_filing:
                raise FilingResolutionError("filing accession identity conflicts")
            revision_id = (
                _occurrence_id(content_id)
                if observation.canonical_revision_id is None
                else observation.canonical_revision_id.value
            )
            connection.execute(
                "INSERT INTO canonical.filing_observations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    revision_id,
                    observation.filing_id.value,
                    observation.report_id.value,
                    observation.issuer_id.value,
                    observation.source_filing_key,
                    observation.form_type,
                    observation.status.value,
                    observation.filing_date,
                    observation.accepted_at,
                    observation.report_period_start,
                    observation.report_period_end,
                    observation.fiscal_year,
                    (
                        None
                        if observation.fiscal_period_kind is None
                        else observation.fiscal_period_kind.value
                    ),
                    observation.is_amendment,
                    _uuid(observation.amends_filing_id),
                    observation.taxonomy_namespace,
                    observation.taxonomy_version,
                    str(observation.document_content_id),
                    observation.document_location,
                    observation.document_redistributable,
                    _json(dict(observation.source_metadata)),
                ],
            )
            self.insert_metadata(
                connection,
                revision_id,
                observation.source_id,
                observation.accepted_at,
                observation.available_at,
                observation.availability_quality.value,
                context,
                sequence,
                content_id,
            )
            return observation.filing_id

        return self._project.services.transactions.run("filing_ingest", operation)

    def ingest_facts(
        self, observations: tuple[RawFundamentalFact, ...]
    ) -> tuple[UUID, ...]:
        self._require_write()
        if not observations:
            raise FundamentalQueryError("fact ingestion requires observations")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[UUID] = []
            for observation in observations:
                if connection.execute(
                    "SELECT 1 FROM canonical.filing_observations WHERE filing_id = ?",
                    [observation.filing_id.value],
                ).fetchone() is None:
                    raise FilingResolutionError("fact filing is not registered")
                content_id = _content_id(
                    "persistra.fundamental.raw_fact", observation
                )
                duplicate = connection.execute(
                    "SELECT canonical_revision_id FROM canonical.market_revision_metadata "
                    "WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if duplicate is not None:
                    result.append(duplicate[0])
                    continue
                revision_id = (
                    _occurrence_id(content_id)
                    if observation.canonical_revision_id is None
                    else observation.canonical_revision_id.value
                )
                sequence = advance_catalog(
                    connection,
                    change_kind="fundamental.fact_ingested",
                    entity_id=observation.issuer_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                dimensions_id = scoped_content_id(
                    {"dimensions": observation.dimensions}
                )
                connection.execute(
                    "INSERT INTO canonical.fundamental_raw_facts VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?)",
                    [
                        revision_id,
                        observation.filing_id.value,
                        observation.report_id.value,
                        observation.issuer_id.value,
                        observation.taxonomy_namespace,
                        observation.taxonomy_version,
                        observation.source_concept_name,
                        observation.period_kind.value,
                        observation.period_start,
                        observation.period_end,
                        str(observation.period_policy_content_id),
                        observation.fiscal_year,
                        (
                            None
                            if observation.fiscal_period_kind is None
                            else observation.fiscal_period_kind.value
                        ),
                        observation.numeric_kind.value,
                        _source_numeric(observation.value),
                        observation.is_nil,
                        observation.nil_reason_code,
                        str(observation.unit.unit),
                        (
                            None
                            if observation.currency is None
                            else observation.currency.code
                        ),
                        observation.source_decimals,
                        observation.source_precision,
                        str(dimensions_id),
                        _json(dict(observation.dimensions)),
                        observation.source_fact_key,
                        _json(dict(observation.source_metadata)),
                    ],
                )
                self.insert_metadata(
                    connection,
                    revision_id,
                    observation.source_id,
                    None,
                    observation.available_at,
                    observation.availability_quality.value,
                    context,
                    sequence,
                    content_id,
                )
                result.append(revision_id)
            return tuple(result)

        return self._project.services.transactions.run("fundamental_facts_ingest", operation)

    def register_concept(
        self, definition: NormalizedConceptDefinition
    ) -> NormalizedConceptId:
        self._require_write()
        content_id = _content_id("persistra.fundamental.concept", definition)

        def operation(context: TransactionContext) -> NormalizedConceptId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identity, created = _register_versioned(
                connection,
                table="canonical.normalized_concepts",
                id_column="normalized_concept_id",
                version_column="concept_version",
                name=definition.name,
                version=definition.version,
                id_type=NormalizedConceptId,
                content_id=content_id,
                values=[
                    definition.period_kind.value,
                    definition.numeric_kind.value,
                    str(definition.canonical_unit.unit),
                    canonical_bytes(definition).decode(),
                ],
                insert_sql=(
                    "INSERT INTO canonical.normalized_concepts "
                    "(normalized_concept_id, concept_version, qualified_name, "
                    "period_kind, numeric_kind, canonical_unit_name, definition_json, "
                    "definition_content_id, created_catalog_sequence) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                change_kind="fundamental.concept_registered",
                context=context,
            )
            if created:
                insert_event(
                    connection,
                    event_name="persistra.fundamental.concept_registered",
                    aggregate_kind="persistra.aggregate.normalized_concept",
                    aggregate_id=identity,
                    aggregate_sequence=definition.version,
                    recorded_at=context.recorded_at,
                    payload={"normalized_concept_id": identity},
                )
            return NormalizedConceptId.parse(identity.value)

        return self._project.services.transactions.run("concept_register", operation)

    def register_mapping(
        self, definition: FundamentalMappingDefinition
    ) -> FundamentalMappingId:
        self._require_write()
        content_id = _content_id("persistra.fundamental.mapping", definition)

        def operation(context: TransactionContext) -> FundamentalMappingId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT fundamental_mapping_id, definition_content_id FROM "
                "canonical.fundamental_mappings WHERE mapping_policy_name = ? "
                "AND mapping_version = ? AND source_taxonomy_namespace = ? "
                "AND source_concept_name = ?",
                [
                    str(definition.name),
                    definition.version,
                    definition.source_taxonomy_namespace,
                    definition.source_concept_name,
                ],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id):
                    raise FundamentalMappingError("mapping version conflicts")
                return FundamentalMappingId.parse(existing[0])
            mapping_id = FundamentalMappingId.new()
            sequence = advance_catalog(
                connection,
                change_kind="fundamental.mapping_registered",
                entity_id=mapping_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.fundamental_mappings VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    mapping_id.value,
                    definition.version,
                    str(definition.name),
                    definition.source_taxonomy_namespace,
                    definition.source_taxonomy_version_pattern,
                    definition.source_concept_name,
                    definition.normalized_concept_id.value,
                    definition.normalized_concept_version,
                    definition.sign_multiplier.envelope_value,
                    definition.scale_multiplier.envelope_value,
                    str(definition.dimension_policy_content_id),
                    _json(dict(definition.applicability)),
                    str(content_id),
                    sequence,
                ],
            )
            return mapping_id

        return self._project.services.transactions.run("mapping_register", operation)

    def normalize(
        self,
        *,
        mapping_policy: QualifiedName,
        max_rows: int = 100_000,
    ) -> FundamentalNormalizationRunId:
        self._require_write()

        def operation(context: TransactionContext) -> FundamentalNormalizationRunId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            state = connection.execute(
                "SELECT current_sequence, chain_content_id FROM catalog.catalog_clock"
            ).fetchone()
            inputs = connection.execute(
                "SELECT f.canonical_revision_id, f.value_decimal, m.fundamental_mapping_id, "
                "m.mapping_version, m.normalized_concept_id, "
                "m.normalized_concept_version, m.sign_multiplier, m.scale_multiplier, "
                "c.canonical_unit_name FROM canonical.fundamental_raw_facts f "
                "JOIN canonical.fundamental_mappings m "
                "ON m.source_taxonomy_namespace = f.taxonomy_namespace "
                "AND f.taxonomy_version LIKE m.source_taxonomy_version_pattern "
                "AND m.source_concept_name = f.source_concept_name "
                "JOIN canonical.normalized_concepts c "
                "ON c.normalized_concept_id = m.normalized_concept_id "
                "AND c.concept_version = m.normalized_concept_version "
                "WHERE m.mapping_policy_name = ? AND NOT f.is_nil LIMIT ?",
                [str(mapping_policy), max_rows + 1],
            ).fetchall()
            if len(inputs) > max_rows:
                raise MarketDataLimitError("normalization input exceeds its row ceiling")
            execution_id = _content_id(
                "persistra.fundamental.normalization",
                {
                    "mapping_policy": mapping_policy,
                    "input_sequence": int(state[0]),
                    "inputs": [str(row[0]) for row in inputs],
                },
            )
            existing = connection.execute(
                "SELECT fundamental_normalization_run_id FROM "
                "canonical.fundamental_normalization_runs "
                "WHERE execution_content_id = ?",
                [str(execution_id)],
            ).fetchone()
            if existing is not None:
                return FundamentalNormalizationRunId.parse(existing[0])
            run_id = FundamentalNormalizationRunId(
                UUID(bytes=execution_id.digest[:16])
            )
            outputs: list[tuple[Any, ...]] = []
            for row in inputs:
                value = Decimal(row[1]) * Decimal(row[6]) * Decimal(row[7])
                output_id = FundamentalNormalizationId.new()
                output_execution = _content_id(
                    "persistra.fundamental.normalization.output",
                    (run_id, str(row[0]), str(row[2]), int(row[3]), format(value, "f")),
                )
                outputs.append((output_id, row, value, output_execution))
            manifest_id = _content_id(
                "persistra.fundamental.normalization.manifest",
                tuple(str(item[0]) for item in outputs),
            )
            sequence = advance_catalog(
                connection,
                change_kind="fundamental.normalization_completed",
                entity_id=run_id,
                change_content_id=manifest_id,
                recorded_at=context.recorded_at,
            )
            connection.execute(
                "INSERT INTO canonical.fundamental_normalization_runs VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id.value,
                    str(scoped_content_id(mapping_policy)),
                    int(state[0]),
                    state[1],
                    str(execution_id),
                    str(manifest_id),
                    len(outputs),
                    len(outputs),
                    0,
                    0,
                    0,
                    sequence,
                    context.recorded_at,
                ],
            )
            for output_id, row, value, output_execution in outputs:
                connection.execute(
                    "INSERT INTO canonical.fundamental_normalizations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        output_id.value,
                        run_id.value,
                        row[0],
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                        value,
                        row[8],
                        "normalized",
                        "[]",
                        str(output_execution),
                        sequence,
                        context.recorded_at,
                    ],
                )
            return run_id

        return self._project.services.transactions.run("fundamental_normalize", operation)

    def filings(
        self,
        issuers: tuple[IssuerId, ...],
        start_date: date,
        end_date: date,
        *,
        context: AsOfContext,
        max_rows: int = 2_000_000,
    ) -> pd.DataFrame:
        if not issuers or start_date > end_date:
            raise FundamentalQueryError("filing query bounds are invalid")
        opened, sequence = market_for_context(self._project, context)
        cutoff, params = cutoff_sql(context)
        rows = opened.connection.execute(
            "SELECT o.canonical_revision_id, o.filing_id, o.report_id, o.issuer_id, "
            "m.source_id, f.accession_namespace, f.normalized_accession, o.form_type, "
            "o.filing_status, o.filing_date, o.accepted_at, o.report_period_start, "
            "o.report_period_end, o.fiscal_year, o.fiscal_period_kind, o.is_amendment, "
            "o.amends_filing_id, o.taxonomy_namespace, o.taxonomy_version, "
            "o.document_content_id, o.document_redistributable, m.available_at, "
            "m.availability_quality FROM canonical.filing_observations o "
            "JOIN canonical.filings f USING (filing_id) "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE o.issuer_id IN (SELECT unnest(?)) AND o.report_period_end >= ? "
            f"AND o.report_period_end <= ? AND m.{cutoff.replace(' AND ', ' AND m.')} "
            "AND m.catalog_sequence <= ? ORDER BY o.issuer_id, o.report_period_end, "
            "o.accepted_at NULLS LAST, o.canonical_revision_id LIMIT ?",
            [
                [issuer.value for issuer in issuers],
                start_date,
                end_date,
                *params,
                sequence,
                max_rows + 1,
            ],
        ).fetchall()
        if len(rows) > max_rows:
            raise MarketDataLimitError("filing query exceeds its row ceiling")
        return build_frame(
            FILINGS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "filing_id": str(row[1]),
                    "report_id": str(row[2]),
                    "issuer_id": str(row[3]),
                    "source_id": None if row[4] is None else str(row[4]),
                    "accession_namespace": row[5],
                    "normalized_accession": row[6],
                    "form_type": row[7],
                    "filing_status": row[8],
                    "filing_date": row[9],
                    "accepted_at": row[10],
                    "report_period_start": row[11],
                    "report_period_end": row[12],
                    "fiscal_year": row[13],
                    "fiscal_period_kind": row[14],
                    "is_amendment": bool(row[15]),
                    "amends_filing_id": None if row[16] is None else str(row[16]),
                    "taxonomy_namespace": row[17],
                    "taxonomy_version": row[18],
                    "document_content_id": row[19],
                    "document_redistributable": bool(row[20]),
                    "available_at": row[21],
                    "availability_quality": row[22],
                    "safety_status": _safe(row[22]),
                }
                for row in rows
            ],
        )

    def raw_facts(self, query: FundamentalQuery) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, query.context)
        cutoff, params = cutoff_sql(query.context)
        period = ""
        values: list[Any] = [
            [issuer.value for issuer in query.issuers],
            [str(concept) for concept in query.concepts],
            query.start_date,
            query.end_date,
            *params,
            sequence,
        ]
        if query.period_kind is not None:
            period = "AND f.period_kind = ? "
            values.append(query.period_kind.value)
        mode_qualify = self._filing_mode_sql(query.filing_mode)
        values.append(query.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT f.canonical_revision_id, f.filing_id, f.report_id, f.issuer_id, "
            "m.source_id, f.taxonomy_namespace, f.taxonomy_version, "
            "f.source_concept_name, f.period_kind, f.period_start, f.period_end, "
            "f.period_policy_content_id, f.fiscal_year, f.fiscal_period_kind, "
            "f.numeric_kind, f.value_decimal, f.is_nil, f.nil_reason_code, f.unit_name, "
            "f.currency, f.source_decimals, f.source_precision, f.dimensions_json, "
            "fo.accepted_at, m.available_at, m.availability_quality "
            "FROM canonical.fundamental_raw_facts f "
            "JOIN canonical.filing_observations fo USING (filing_id) "
            "JOIN canonical.market_revision_metadata m "
            "ON m.canonical_revision_id = f.canonical_revision_id "
            "WHERE f.issuer_id IN (SELECT unnest(?)) "
            "AND f.source_concept_name IN (SELECT unnest(?)) AND f.period_end >= ? "
            f"AND f.period_end <= ? AND m.{cutoff.replace(' AND ', ' AND m.')} "
            f"AND m.catalog_sequence <= ? {period}{mode_qualify}"
            "ORDER BY f.issuer_id, f.period_end, f.period_start NULLS LAST, "
            "f.taxonomy_namespace, f.taxonomy_version, f.source_concept_name, "
            "f.canonical_revision_id LIMIT ?",
            values,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("fundamental query exceeds its row ceiling")
        return build_frame(
            RAW_FACTS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "filing_id": str(row[1]),
                    "report_id": str(row[2]),
                    "issuer_id": str(row[3]),
                    "source_id": None if row[4] is None else str(row[4]),
                    "taxonomy_namespace": row[5],
                    "taxonomy_version": row[6],
                    "source_concept_name": row[7],
                    "period_kind": row[8],
                    "period_start": row[9],
                    "period_end": row[10],
                    "period_policy_content_id": row[11],
                    "fiscal_year": row[12],
                    "fiscal_period_kind": row[13],
                    "numeric_kind": row[14],
                    "value": None if row[15] is None else float(row[15]),
                    "is_nil": bool(row[16]),
                    "nil_reason_code": row[17],
                    "unit_name": row[18],
                    "currency": row[19],
                    "source_decimals": row[20],
                    "source_precision": row[21],
                    "dimensions": row[22],
                    "accepted_at": row[23],
                    "available_at": row[24],
                    "availability_quality": row[25],
                    "safety_status": _safe(row[25]),
                }
                for row in rows
            ],
        )

    @staticmethod
    def _filing_mode_sql(mode: FilingMode) -> str:
        if mode is FilingMode.ALL_FILINGS or mode is FilingMode.AS_REPORTED:
            return ""
        if mode is FilingMode.ORIGINAL:
            return (
                "QUALIFY row_number() OVER (PARTITION BY f.report_id "
                "ORDER BY fo.is_amendment, fo.accepted_at, f.filing_id) = 1 "
            )
        if mode is FilingMode.LATEST_FILING_IN_REPORT:
            return (
                "QUALIFY row_number() OVER (PARTITION BY f.report_id "
                "ORDER BY fo.accepted_at DESC NULLS LAST, f.filing_id DESC) = 1 "
            )
        return (
            "QUALIFY row_number() OVER (PARTITION BY f.issuer_id, "
            "f.taxonomy_namespace, f.source_concept_name, f.period_kind, "
            "f.period_start, f.period_end, f.period_policy_content_id, f.numeric_kind, "
            "f.unit_name, f.currency, f.dimensions_content_id "
            "ORDER BY fo.accepted_at DESC NULLS LAST, f.filing_id DESC) = 1 "
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "fundamental mutation requires market_write mode"
            )

    @staticmethod
    def insert_metadata(
        connection: ManagedConnection,
        revision_id: UUID,
        source_id: EntityId | None,
        event_at: datetime | None,
        available_at: datetime,
        quality: str,
        context: TransactionContext,
        sequence: int,
        content_id: ContentId,
    ) -> None:
        _insert_market_metadata(
            connection,
            revision_id=revision_id,
            source_id=_uuid(source_id),
            event_at=event_at,
            available_at=available_at,
            availability_quality=quality,
            ingested_at=context.recorded_at,
            catalog_sequence=sequence,
            content_id=content_id,
        )


class EstimateService:
    """This class represents the estimate measure definitions and point-in-time observation
    families."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register_measure(
        self, definition: EstimateMeasureDefinition
    ) -> EstimateMeasureId:
        self._require_write()
        content_id = _content_id("persistra.estimate.measure", definition)

        def operation(context: TransactionContext) -> EstimateMeasureId:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identity, _created = _register_versioned(
                connection,
                table="canonical.estimate_measures",
                id_column="estimate_measure_id",
                version_column="measure_version",
                name=definition.name,
                version=definition.version,
                id_type=EstimateMeasureId,
                content_id=content_id,
                values=[
                    definition.entity_kind,
                    definition.numeric_kind.value,
                    str(definition.canonical_unit.unit),
                    canonical_bytes(definition).decode(),
                ],
                insert_sql=(
                    "INSERT INTO canonical.estimate_measures "
                    "(estimate_measure_id, measure_version, qualified_name, entity_kind, "
                    "numeric_kind, canonical_unit_name, definition_json, "
                    "definition_content_id, created_catalog_sequence) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                change_kind="estimate.measure_registered",
                context=context,
            )
            return EstimateMeasureId.parse(identity.value)

        return self._project.services.transactions.run("estimate_measure_register", operation)

    def ingest_individual(
        self, observations: tuple[IndividualEstimate, ...]
    ) -> tuple[UUID, ...]:
        return self._ingest("individual", observations)

    def ingest_consensus(
        self, observations: tuple[ConsensusEstimate, ...]
    ) -> tuple[UUID, ...]:
        return self._ingest("consensus", observations)

    def ingest_actuals(
        self, observations: tuple[ActualObservation, ...]
    ) -> tuple[UUID, ...]:
        return self._ingest("actual", observations)

    def _ingest(self, family: str, observations: tuple[Any, ...]) -> tuple[UUID, ...]:
        self._require_write()
        if not observations:
            raise EstimateQueryError("estimate ingestion requires observations")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[UUID] = []
            for observation in observations:
                content_id = _content_id(f"persistra.estimate.{family}", observation)
                duplicate = connection.execute(
                    "SELECT canonical_revision_id FROM canonical.market_revision_metadata "
                    "WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone()
                if duplicate is not None:
                    result.append(duplicate[0])
                    continue
                revision_id = (
                    _occurrence_id(content_id)
                    if observation.canonical_revision_id is None
                    else observation.canonical_revision_id.value
                )
                sequence = advance_catalog(
                    connection,
                    change_kind=f"estimate.{family}_ingested",
                    entity_id=observation.measure_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                if family == "individual":
                    self._insert_individual(connection, revision_id, observation)
                elif family == "consensus":
                    self._insert_consensus(connection, revision_id, observation)
                else:
                    self._insert_actual(connection, revision_id, observation)
                FundamentalService.insert_metadata(
                    connection,
                    revision_id,
                    observation.source_id,
                    observation.event_at,
                    observation.available_at,
                    observation.availability_quality.value,
                    context,
                    sequence,
                    content_id,
                )
                result.append(revision_id)
            return tuple(result)

        return self._project.services.transactions.run(
            f"estimate_{family}_ingest", operation
        )

    @staticmethod
    def _target(target: Any) -> list[Any]:
        return [
            target.kind.value,
            target.fiscal_year,
            (
                None
                if target.fiscal_period_kind is None
                else target.fiscal_period_kind.value
            ),
            target.period_end,
            _uuid(target.report_id),
            target.horizon_days,
            target.target_at,
            str(target.policy_content_id),
        ]

    @classmethod
    def _insert_individual(
        cls, connection: ManagedConnection, revision_id: UUID, row: IndividualEstimate
    ) -> None:
        connection.execute(
            "INSERT INTO canonical.individual_estimates VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                revision_id,
                row.source_estimate_key,
                row.measure_id.value,
                row.measure_version,
                row.subject_entity_kind,
                row.subject_entity_id.value,
                _uuid(row.contributor_id),
                *cls._target(row.target),
                row.value.envelope_value,
                str(row.value.unit.unit),
                None if row.currency is None else row.currency.code,
                (
                    None
                    if row.split_basis_content_id is None
                    else str(row.split_basis_content_id)
                ),
                row.source_revision_label,
                _json(dict(row.source_metadata)),
            ],
        )

    @classmethod
    def _insert_consensus(
        cls, connection: ManagedConnection, revision_id: UUID, row: ConsensusEstimate
    ) -> None:
        connection.execute(
            "INSERT INTO canonical.estimate_consensus VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?)",
            [
                revision_id,
                row.source_consensus_key,
                row.measure_id.value,
                row.measure_version,
                row.subject_entity_kind,
                row.subject_entity_id.value,
                *cls._target(row.target),
                row.contributor_count,
                _source_numeric(row.mean),
                _source_numeric(row.median),
                _source_numeric(row.high),
                _source_numeric(row.low),
                _source_numeric(row.standard_deviation),
                str(row.unit.unit),
                None if row.currency is None else row.currency.code,
                str(row.methodology_content_id),
                (
                    None
                    if row.constituent_manifest_content_id is None
                    else str(row.constituent_manifest_content_id)
                ),
                _json(dict(row.source_metadata)),
            ],
        )

    @staticmethod
    def _insert_actual(
        connection: ManagedConnection, revision_id: UUID, row: ActualObservation
    ) -> None:
        connection.execute(
            "INSERT INTO canonical.estimate_actuals VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                revision_id,
                row.source_actual_key,
                row.measure_id.value,
                row.measure_version,
                row.subject_entity_kind,
                row.subject_entity_id.value,
                row.fiscal_year,
                None if row.fiscal_period_kind is None else row.fiscal_period_kind.value,
                row.target_period_end,
                row.value.envelope_value,
                str(row.value.unit.unit),
                None if row.currency is None else row.currency.code,
                _uuid(row.filing_id),
                _uuid(row.raw_fact_revision_id),
                _uuid(row.normalization_id),
                str(row.actual_policy_content_id),
                _json(dict(row.source_metadata)),
            ],
        )

    def individual(self, query: EstimateQuery) -> pd.DataFrame:
        return self._query(query, "individual")

    def consensus(self, query: EstimateQuery) -> pd.DataFrame:
        return self._query(query, "consensus")

    def actuals(self, query: EstimateQuery) -> pd.DataFrame:
        return self._query(query, "actual")

    def _query(self, query: EstimateQuery, family: str) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, query.context)
        cutoff, params = cutoff_sql(query.context)
        table = {
            "individual": "individual_estimates",
            "consensus": "estimate_consensus",
            "actual": "estimate_actuals",
        }[family]
        key = {
            "individual": "source_estimate_key",
            "consensus": "source_consensus_key",
            "actual": "source_actual_key",
        }[family]
        values: list[Any] = [
            [subject.value for subject in query.subjects],
            [str(measure) for measure in query.measures],
            query.start,
            query.end,
            *params,
            sequence,
        ]
        if family != "actual":
            values.append(query.target_kind.value)
        values.append(query.max_rows + 1)
        rows = opened.connection.execute(
            f"SELECT e.*, m.source_id, m.event_at, m.available_at, "
            "m.availability_quality, d.qualified_name, d.numeric_kind "
            f"FROM canonical.{table} e JOIN canonical.market_revision_metadata m "
            "USING (canonical_revision_id) JOIN canonical.estimate_measures d "
            "ON d.estimate_measure_id = e.estimate_measure_id "
            "AND d.measure_version = e.measure_version "
            "WHERE e.subject_entity_id IN (SELECT unnest(?)) "
            "AND d.qualified_name IN (SELECT unnest(?)) AND m.event_at >= ? "
            f"AND m.event_at < ? AND m.{cutoff.replace(' AND ', ' AND m.')} "
            f"AND m.catalog_sequence <= ? AND "
            + (
                "e.target_kind = ? "
                if family != "actual"
                else "1 = 1 "
            )
            + f"ORDER BY e.subject_entity_id, m.event_at, e.{key}, "
            "e.canonical_revision_id LIMIT ?",
            values,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("estimate query exceeds its row ceiling")
        if family == "individual":
            return self._individual_frame(rows)
        if family == "consensus":
            return self._consensus_frame(rows)
        return self._actuals_frame(rows)

    @staticmethod
    def _individual_frame(rows: Iterable[tuple[Any, ...]]) -> pd.DataFrame:
        return build_frame(
            ESTIMATES_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "estimate_measure_id": str(row[2]),
                    "measure_version": int(row[3]),
                    "measure_name": row[25],
                    "subject_entity_kind": row[4],
                    "subject_entity_id": str(row[5]),
                    "estimate_contributor_id": (
                        None if row[6] is None else str(row[6])
                    ),
                    "source_id": None if row[21] is None else str(row[21]),
                    "numeric_kind": row[26],
                    "target_kind": row[7],
                    "target_fiscal_year": row[8],
                    "target_fiscal_period_kind": row[9],
                    "target_period_end": row[10],
                    "horizon_days": row[12],
                    "target_at": row[13],
                    "value": float(row[15]),
                    "unit_name": row[16],
                    "currency": row[17],
                    "event_at": row[22],
                    "available_at": row[23],
                    "availability_quality": row[24],
                    "source_revision_label": row[19],
                    "safety_status": _safe(row[24]),
                }
                for row in rows
            ],
        )

    @staticmethod
    def _consensus_frame(rows: Iterable[tuple[Any, ...]]) -> pd.DataFrame:
        return build_frame(
            CONSENSUS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "estimate_measure_id": str(row[2]),
                    "measure_version": int(row[3]),
                    "measure_name": row[29],
                    "subject_entity_kind": row[4],
                    "subject_entity_id": str(row[5]),
                    "source_id": None if row[25] is None else str(row[25]),
                    "numeric_kind": row[30],
                    "target_kind": row[6],
                    "target_period_end": row[9],
                    "target_at": row[12],
                    "contributor_count": int(row[14]),
                    "mean": None if row[15] is None else float(row[15]),
                    "median": None if row[16] is None else float(row[16]),
                    "high": None if row[17] is None else float(row[17]),
                    "low": None if row[18] is None else float(row[18]),
                    "standard_deviation": (
                        None if row[19] is None else float(row[19])
                    ),
                    "unit_name": row[20],
                    "currency": row[21],
                    "methodology_content_id": row[22],
                    "event_at": row[26],
                    "available_at": row[27],
                    "safety_status": _safe(row[28]),
                }
                for row in rows
            ],
        )

    @staticmethod
    def _actuals_frame(rows: Iterable[tuple[Any, ...]]) -> pd.DataFrame:
        return build_frame(
            ACTUALS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "estimate_measure_id": str(row[2]),
                    "measure_version": int(row[3]),
                    "measure_name": row[21],
                    "subject_entity_kind": row[4],
                    "subject_entity_id": str(row[5]),
                    "source_id": None if row[17] is None else str(row[17]),
                    "numeric_kind": row[22],
                    "target_period_end": row[8],
                    "value": float(row[9]),
                    "unit_name": row[10],
                    "currency": row[11],
                    "filing_id": None if row[12] is None else str(row[12]),
                    "raw_fact_revision_id": (
                        None if row[13] is None else str(row[13])
                    ),
                    "fundamental_normalization_id": (
                        None if row[14] is None else str(row[14])
                    ),
                    "event_at": row[18],
                    "available_at": row[19],
                    "safety_status": _safe(row[20]),
                }
                for row in rows
            ],
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("estimate mutation requires market_write mode")


class MacroService:
    """This class represents the versioned macro series, atomic releases, and vintage selection."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(self, definition: MacroSeriesDefinition) -> ResolvedMacroSeriesRef:
        self._require_write()
        content_id = _content_id("persistra.macro.series", definition)

        def operation(context: TransactionContext) -> ResolvedMacroSeriesRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identity, _created = _register_versioned(
                connection,
                table="canonical.macro_series",
                id_column="macro_series_id",
                version_column="series_version",
                name=definition.name,
                version=definition.version,
                id_type=MacroSeriesId,
                content_id=content_id,
                values=[
                    str(definition.frequency),
                    str(definition.seasonal_adjustment_status),
                    str(definition.geography_code),
                    str(definition.unit.unit),
                    definition.numeric_kind.value,
                    definition.vintage_completeness.value,
                    str(definition.period_policy_content_id),
                    canonical_bytes(definition).decode(),
                ],
                insert_sql=(
                    "INSERT INTO canonical.macro_series "
                    "(macro_series_id, series_version, qualified_name, frequency, "
                    "seasonal_adjustment_status, geography_code, unit_name, numeric_kind, "
                    "vintage_completeness, period_policy_content_id, definition_json, "
                    "definition_content_id, created_catalog_sequence) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                change_kind="macro.series_registered",
                context=context,
            )
            return ResolvedMacroSeriesRef(
                MacroSeriesId.parse(identity.value), definition.version, content_id
            )

        return self._project.services.transactions.run("macro_series_register", operation)

    def resolve(
        self, reference: MacroSeriesRef, *, context: AsOfContext
    ) -> ResolvedMacroSeriesRef:
        opened, sequence = market_for_context(self._project, context)
        row = opened.connection.execute(
            "SELECT macro_series_id, definition_content_id FROM canonical.macro_series "
            "WHERE qualified_name = ? AND series_version = ? "
            "AND created_catalog_sequence <= ?",
            [str(reference.name), reference.version, sequence],
        ).fetchone()
        if row is None:
            raise MacroQueryError("macro series is unavailable in the snapshot")
        return ResolvedMacroSeriesRef(
            MacroSeriesId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def get(
        self, reference: MacroSeriesRef, *, context: AsOfContext
    ) -> MacroSeriesDefinition:
        opened, sequence = market_for_context(self._project, context)
        row = opened.connection.execute(
            "SELECT definition_json FROM canonical.macro_series "
            "WHERE qualified_name = ? AND series_version = ? "
            "AND created_catalog_sequence <= ?",
            [str(reference.name), reference.version, sequence],
        ).fetchone()
        if row is None:
            raise MacroQueryError("macro series is unavailable")
        value = json.loads(row[0])
        return MacroSeriesDefinition(
            QualifiedName(value["name"]),
            int(value["version"]),
            QualifiedName(value["frequency"]),
            QualifiedName(value["seasonal_adjustment_status"]),
            QualifiedName(value["geography_code"]),
            UnitSpec(Unit(value["unit"]["unit"]), NumericKind(value["unit"]["numeric_kind"])),
            FactNumericKind(value["numeric_kind"]),
            VintageCompleteness(value["vintage_completeness"]),
            ContentId.parse(value["period_policy_content_id"]),
        )

    def ingest(self, release: MacroRelease) -> UUID:
        self._require_write()

        def operation(context: TransactionContext) -> UUID:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            content_id = _content_id("persistra.macro.release", release)
            release_revision_id = (
                _occurrence_id(content_id)
                if release.canonical_revision_id is None
                else release.canonical_revision_id.value
            )
            duplicate = connection.execute(
                "SELECT canonical_revision_id FROM canonical.market_revision_metadata "
                "WHERE content_id = ?",
                [str(content_id)],
            ).fetchone()
            if duplicate is not None:
                return duplicate[0]
            sequence = advance_catalog(
                connection,
                change_kind="macro.release_ingested",
                entity_id=release.release_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            master = connection.execute(
                "SELECT macro_series_id, source_id, source_release_key "
                "FROM canonical.macro_releases WHERE macro_release_id = ?",
                [release.release_id.value],
            ).fetchone()
            expected = (
                release.series.macro_series_id.value,
                _uuid(release.source_id),
                release.source_release_key,
            )
            if master is None:
                connection.execute(
                    "INSERT INTO canonical.macro_releases VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        release.release_id.value,
                        *expected,
                        sequence,
                        context.recorded_at,
                    ],
                )
            elif master != expected:
                raise MacroQueryError("macro release master conflicts")
            connection.execute(
                "INSERT INTO canonical.macro_release_observations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    release_revision_id,
                    release.release_id.value,
                    release.series.macro_series_id.value,
                    release.series.version,
                    release.release_at,
                    release.source_release_sequence,
                    str(release.release_manifest_content_id),
                    "{}",
                ],
            )
            FundamentalService.insert_metadata(
                connection,
                release_revision_id,
                release.source_id,
                release.release_at,
                release.available_at,
                release.availability_quality.value,
                context,
                sequence,
                content_id,
            )
            for point in release.observations:
                point_content = _content_id(
                    "persistra.macro.observation",
                    {
                        "release_revision_id": str(release_revision_id),
                        "point": point,
                    },
                )
                point_revision = _occurrence_id(point_content)
                connection.execute(
                    "INSERT INTO canonical.macro_observations VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        point_revision,
                        release.series.macro_series_id.value,
                        release.series.version,
                        release.release_id.value,
                        release_revision_id,
                        point.source_vintage_key,
                        point.period_start,
                        point.period_end,
                        point.vintage_status.value,
                        _source_numeric(point.value),
                        point.is_missing,
                        point.missing_reason_code,
                        str(point.unit.unit),
                        _json(dict(point.source_metadata)),
                    ],
                )
                _insert_market_metadata(
                    connection,
                    revision_id=point_revision,
                    source_id=_uuid(release.source_id),
                    event_at=release.release_at,
                    available_at=release.available_at,
                    availability_quality=release.availability_quality.value,
                    ingested_at=context.recorded_at,
                    catalog_sequence=sequence,
                    content_id=point_content,
                )
            return release_revision_id

        return self._project.services.transactions.run("macro_release_ingest", operation)

    def query(self, query: MacroQuery) -> pd.DataFrame:
        opened, sequence = market_for_context(self._project, query.context)
        resolved = self.resolve(query.series, context=query.context)
        cutoff, params = cutoff_sql(query.context)
        release_clause = ""
        values: list[Any] = [
            resolved.macro_series_id.value,
            resolved.version,
            query.start_date,
            query.end_date,
            *params,
            sequence,
        ]
        if query.vintage_mode is MacroVintageMode.EXACT_RELEASE:
            release_clause = "AND o.macro_release_id = ? "
            assert query.exact_release_id is not None
            values.append(query.exact_release_id.value)
        qualify = ""
        if query.vintage_mode is MacroVintageMode.FIRST_RELEASE:
            qualify = (
                "QUALIFY row_number() OVER (PARTITION BY o.observation_period_start, "
                "o.observation_period_end ORDER BY r.release_at, "
                "o.canonical_revision_id) = 1 "
            )
        elif query.vintage_mode is MacroVintageMode.LATEST_KNOWN:
            qualify = (
                "QUALIFY row_number() OVER (PARTITION BY o.observation_period_start, "
                "o.observation_period_end ORDER BY r.release_at DESC, "
                "o.canonical_revision_id DESC) = 1 "
            )
        values.append(query.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT o.canonical_revision_id, o.macro_series_id, o.series_version, "
            "d.qualified_name, o.macro_release_id, o.macro_release_revision_id, "
            "m.source_id, d.numeric_kind, o.observation_period_start, "
            "o.observation_period_end, r.release_at, r.source_release_sequence, "
            "o.source_vintage_key, o.vintage_status, o.value_decimal, o.is_missing, "
            "o.missing_reason_code, o.unit_name, m.available_at, "
            "d.vintage_completeness, m.availability_quality "
            "FROM canonical.macro_observations o JOIN "
            "canonical.macro_release_observations r "
            "ON r.canonical_revision_id = o.macro_release_revision_id "
            "JOIN canonical.macro_series d ON d.macro_series_id = o.macro_series_id "
            "AND d.series_version = o.series_version "
            "JOIN canonical.market_revision_metadata m "
            "ON m.canonical_revision_id = o.canonical_revision_id "
            "WHERE o.macro_series_id = ? AND o.series_version = ? "
            "AND o.observation_period_end >= ? AND o.observation_period_start <= ? "
            f"AND m.{cutoff.replace(' AND ', ' AND m.')} "
            f"AND m.catalog_sequence <= ? {release_clause}{qualify}"
            "ORDER BY o.observation_period_end, r.release_at, "
            "o.canonical_revision_id LIMIT ?",
            values,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("macro query exceeds its row ceiling")
        return build_frame(
            MACRO_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "macro_series_id": str(row[1]),
                    "series_version": int(row[2]),
                    "series_name": row[3],
                    "macro_release_id": str(row[4]),
                    "macro_release_revision_id": str(row[5]),
                    "source_id": None if row[6] is None else str(row[6]),
                    "numeric_kind": row[7],
                    "observation_period_start": row[8],
                    "observation_period_end": row[9],
                    "release_at": row[10],
                    "source_release_sequence": row[11],
                    "source_vintage_key": row[12],
                    "vintage_status": row[13],
                    "value": None if row[14] is None else float(row[14]),
                    "is_missing": bool(row[15]),
                    "missing_reason_code": row[16],
                    "unit_name": row[17],
                    "available_at": row[18],
                    "vintage_completeness": row[19],
                    "safety_status": (
                        "safe"
                        if row[19] == "complete"
                        and row[20] in {"observed", "policy_derived"}
                        else "unsafe"
                    ),
                }
                for row in rows
            ],
        )

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("macro mutation requires market_write mode")


class BenchmarkService:
    """This class represents the benchmark definitions, official series, and effective
    constituents."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: BenchmarkDefinition
    ) -> ResolvedBenchmarkVersionRef:
        self._require_write()
        content_id = _content_id("persistra.benchmark.definition", definition)

        def operation(context: TransactionContext) -> ResolvedBenchmarkVersionRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            existing = connection.execute(
                "SELECT v.benchmark_id, v.definition_content_id FROM "
                "canonical.benchmarks b JOIN canonical.benchmark_versions v "
                "USING (benchmark_id) WHERE b.qualified_name = ? "
                "AND v.benchmark_version = ?",
                [str(definition.name), definition.version],
            ).fetchone()
            if existing is not None:
                if existing[1] != str(content_id):
                    raise BenchmarkResolutionError("benchmark version conflicts")
                return ResolvedBenchmarkVersionRef(
                    BenchmarkId.parse(existing[0]), definition.version, content_id
                )
            master = connection.execute(
                "SELECT benchmark_id FROM canonical.benchmarks WHERE qualified_name = ?",
                [str(definition.name)],
            ).fetchone()
            benchmark_id = (
                BenchmarkId.new()
                if master is None
                else BenchmarkId.parse(master[0])
            )
            sequence = advance_catalog(
                connection,
                change_kind="benchmark.version_registered",
                entity_id=benchmark_id,
                change_content_id=content_id,
                recorded_at=context.recorded_at,
            )
            if master is None:
                connection.execute(
                    "INSERT INTO canonical.benchmarks VALUES (?, ?, ?, ?)",
                    [
                        benchmark_id.value,
                        str(definition.name),
                        sequence,
                        context.recorded_at,
                    ],
                )
            connection.execute(
                "INSERT INTO canonical.benchmark_versions VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    benchmark_id.value,
                    definition.version,
                    definition.kind.value,
                    _uuid(definition.instrument_id),
                    definition.currency.code,
                    self.calendar_id(connection, definition.calendar),
                    str(definition.methodology_content_id),
                    definition.licensing_class,
                    str(content_id),
                    canonical_bytes(definition).decode(),
                    sequence,
                ],
            )
            return ResolvedBenchmarkVersionRef(
                benchmark_id, definition.version, content_id
            )

        return self._project.services.transactions.run("benchmark_register", operation)

    def resolve(
        self, reference: BenchmarkVersionRef, *, context: AsOfContext
    ) -> ResolvedBenchmarkVersionRef:
        opened, sequence = market_for_context(self._project, context)
        row = opened.connection.execute(
            "SELECT v.benchmark_id, v.definition_content_id FROM canonical.benchmarks b "
            "JOIN canonical.benchmark_versions v USING (benchmark_id) "
            "WHERE b.qualified_name = ? AND v.benchmark_version = ? "
            "AND v.created_catalog_sequence <= ?",
            [str(reference.name), reference.version, sequence],
        ).fetchone()
        if row is None:
            raise BenchmarkResolutionError("benchmark is unavailable")
        return ResolvedBenchmarkVersionRef(
            BenchmarkId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )

    def ingest_series(
        self, observations: tuple[BenchmarkSeriesObservation, ...]
    ) -> tuple[UUID, ...]:
        return self._ingest(observations, "series")

    def ingest_constituents(
        self, observations: tuple[BenchmarkConstituent, ...]
    ) -> tuple[UUID, ...]:
        return self._ingest(observations, "constituent")

    def _ingest(self, observations: tuple[Any, ...], family: str) -> tuple[UUID, ...]:
        self._require_write()

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[UUID] = []
            for row in observations:
                content_id = _content_id(f"persistra.benchmark.{family}", row)
                revision_id = (
                    _occurrence_id(content_id)
                    if row.canonical_revision_id is None
                    else row.canonical_revision_id.value
                )
                if connection.execute(
                    "SELECT 1 FROM canonical.market_revision_metadata WHERE content_id = ?",
                    [str(content_id)],
                ).fetchone() is not None:
                    result.append(revision_id)
                    continue
                sequence = advance_catalog(
                    connection,
                    change_kind=f"benchmark.{family}_ingested",
                    entity_id=row.benchmark.benchmark_id,
                    change_content_id=content_id,
                    recorded_at=context.recorded_at,
                )
                if family == "series":
                    connection.execute(
                        "INSERT INTO canonical.benchmark_series_observations VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            revision_id,
                            row.benchmark.benchmark_id.value,
                            row.benchmark.version,
                            row.series_kind.value,
                            row.interval_start,
                            row.interval_end,
                            row.session_date,
                            row.value.envelope_value,
                            row.currency.code,
                            str(row.calendar_schedule_content_id),
                            str(row.source_methodology_content_id),
                        ],
                    )
                    event_at = row.interval_end
                else:
                    connection.execute(
                        "INSERT INTO canonical.benchmark_constituents VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            revision_id,
                            row.benchmark.benchmark_id.value,
                            row.benchmark.version,
                            row.instrument_id.value,
                            row.membership_role,
                            _source_numeric(row.weight),
                            _source_numeric(row.index_shares),
                            _source_numeric(row.divisor_contribution),
                            row.valid_from,
                            row.valid_to,
                            str(row.methodology_content_id),
                            _json(dict(row.source_metadata)),
                        ],
                    )
                    event_at = row.valid_from
                FundamentalService.insert_metadata(
                    connection,
                    revision_id,
                    row.source_id,
                    event_at,
                    row.available_at,
                    row.availability_quality.value,
                    context,
                    sequence,
                    content_id,
                )
                result.append(revision_id)
            return tuple(result)

        return self._project.services.transactions.run(
            f"benchmark_{family}_ingest", operation
        )

    def series(self, query: BenchmarkQuery) -> pd.DataFrame:
        resolved = self.resolve(query.benchmark, context=query.context)
        opened, sequence = market_for_context(self._project, query.context)
        cutoff, params = cutoff_sql(query.context)
        kind = ""
        values: list[Any] = [
            resolved.benchmark_id.value,
            resolved.version,
            query.start,
            query.end,
            *params,
            sequence,
        ]
        if query.series_kind is not None:
            kind = "AND b.series_kind = ? "
            values.append(query.series_kind.value)
        values.append(query.max_rows + 1)
        rows = opened.connection.execute(
            "SELECT b.canonical_revision_id, b.benchmark_id, b.benchmark_version, "
            "m.source_id, b.series_kind, b.interval_start, b.interval_end, "
            "b.session_date, b.value_decimal, b.currency, "
            "b.calendar_schedule_content_id, b.source_methodology_content_id, "
            "m.available_at, m.availability_quality "
            "FROM canonical.benchmark_series_observations b "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE b.benchmark_id = ? AND b.benchmark_version = ? "
            "AND b.interval_end >= ? AND b.interval_end < ? "
            f"AND m.{cutoff.replace(' AND ', ' AND m.')} "
            f"AND m.catalog_sequence <= ? {kind}"
            "ORDER BY b.interval_end, b.canonical_revision_id LIMIT ?",
            values,
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("benchmark query exceeds its row ceiling")
        return build_frame(
            BENCHMARK_SERIES_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "benchmark_id": str(row[1]),
                    "benchmark_version": int(row[2]),
                    "source_id": None if row[3] is None else str(row[3]),
                    "series_kind": row[4],
                    "interval_start": row[5],
                    "interval_end": row[6],
                    "session_date": row[7],
                    "value": float(row[8]),
                    "currency": row[9],
                    "calendar_schedule_content_id": row[10],
                    "source_methodology_content_id": row[11],
                    "available_at": row[12],
                    "safety_status": _safe(row[13]),
                }
                for row in rows
            ],
        )

    def constituents(self, query: BenchmarkQuery) -> pd.DataFrame:
        resolved = self.resolve(query.benchmark, context=query.context)
        opened, sequence = market_for_context(self._project, query.context)
        cutoff, params = cutoff_sql(query.context)
        rows = opened.connection.execute(
            "SELECT b.canonical_revision_id, b.benchmark_id, b.benchmark_version, "
            "b.instrument_id, m.source_id, b.membership_role, b.weight, "
            "b.index_shares, b.divisor_contribution, b.valid_from, b.valid_to, "
            "b.methodology_content_id, m.available_at, m.availability_quality "
            "FROM canonical.benchmark_constituents b "
            "JOIN canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE b.benchmark_id = ? AND b.benchmark_version = ? "
            "AND b.valid_from < ? AND (b.valid_to IS NULL OR b.valid_to > ?) "
            f"AND m.{cutoff.replace(' AND ', ' AND m.')} "
            "AND m.catalog_sequence <= ? ORDER BY b.valid_from, b.instrument_id, "
            "b.canonical_revision_id LIMIT ?",
            [
                resolved.benchmark_id.value,
                resolved.version,
                query.end,
                query.start,
                *params,
                sequence,
                query.max_rows + 1,
            ],
        ).fetchall()
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("constituent query exceeds its row ceiling")
        return build_frame(
            BENCHMARK_CONSTITUENTS_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "benchmark_id": str(row[1]),
                    "benchmark_version": int(row[2]),
                    "instrument_id": str(row[3]),
                    "source_id": None if row[4] is None else str(row[4]),
                    "membership_role": row[5],
                    "weight": None if row[6] is None else float(row[6]),
                    "index_shares": None if row[7] is None else float(row[7]),
                    "divisor_contribution": (
                        None if row[8] is None else float(row[8])
                    ),
                    "valid_from": row[9],
                    "valid_to": row[10],
                    "methodology_content_id": row[11],
                    "available_at": row[12],
                    "safety_status": _safe(row[13]),
                }
                for row in rows
            ],
        )

    @staticmethod
    def calendar_id(connection: ManagedConnection, reference: Any) -> UUID:
        row = connection.execute(
            "SELECT calendar_id FROM canonical.calendar_definitions "
            "WHERE qualified_name = ? AND calendar_version = ?",
            [str(reference.name), reference.version],
        ).fetchone()
        if row is None:
            raise BenchmarkResolutionError("benchmark calendar is unavailable")
        return row[0]

    def _require_write(self) -> None:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "benchmark mutation requires market_write mode"
            )


class RiskFreeCurveService:
    """This class represents the risk-free curve definition registry."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def register(
        self, definition: RiskFreeCurveDefinition
    ) -> ResolvedRiskFreeCurveRef:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("curve registration requires market_write")
        content_id = _content_id("persistra.risk_free.curve", definition)

        def operation(context: TransactionContext) -> ResolvedRiskFreeCurveRef:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            identity, _created = _register_versioned(
                connection,
                table="canonical.risk_free_curves",
                id_column="risk_free_curve_id",
                version_column="curve_version",
                name=definition.name,
                version=definition.version,
                id_type=RiskFreeCurveId,
                content_id=content_id,
                values=[
                    definition.currency.code,
                    definition.quote_kind.value,
                    definition.compounding.value,
                    definition.compounding_periods_per_year,
                    definition.day_count.value,
                    BenchmarkService.calendar_id(connection, definition.calendar),
                    str(definition.business_day_policy_content_id),
                    canonical_bytes(definition).decode(),
                ],
                insert_sql=(
                    "INSERT INTO canonical.risk_free_curves "
                    "(risk_free_curve_id, curve_version, qualified_name, currency, "
                    "quote_kind, compounding_kind, compounding_periods_per_year, "
                    "day_count_kind, calendar_id, business_day_policy_content_id, "
                    "definition_json, definition_content_id, "
                    "created_catalog_sequence) VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                change_kind="risk_free.curve_registered",
                context=context,
            )
            return ResolvedRiskFreeCurveRef(
                RiskFreeCurveId.parse(identity.value), definition.version, content_id
            )

        return self._project.services.transactions.run("risk_free_curve_register", operation)

    def resolve(
        self, reference: RiskFreeCurveRef, *, context: AsOfContext
    ) -> ResolvedRiskFreeCurveRef:
        opened, sequence = market_for_context(self._project, context)
        row = opened.connection.execute(
            "SELECT risk_free_curve_id, definition_content_id FROM "
            "canonical.risk_free_curves WHERE qualified_name = ? AND curve_version = ? "
            "AND created_catalog_sequence <= ?",
            [str(reference.name), reference.version, sequence],
        ).fetchone()
        if row is None:
            raise RateConventionError("risk-free curve is unavailable")
        return ResolvedRiskFreeCurveRef(
            RiskFreeCurveId.parse(row[0]), reference.version, ContentId.parse(row[1])
        )


class RateService:
    """This class represents the canonical curve points and exact-tenor lookup."""

    __slots__ = ("_curves", "_project")

    def __init__(self, project: Project, curves: RiskFreeCurveService) -> None:
        self._project = project
        self._curves = curves

    def ingest(self, observations: tuple[RiskFreePoint, ...]) -> tuple[UUID, ...]:
        if self._project._mode is not ProjectMode.MARKET_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("rate ingestion requires market_write")
        if not observations:
            raise RateConventionError("rate ingestion requires points")

        def operation(context: TransactionContext) -> tuple[UUID, ...]:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            result: list[UUID] = []
            groups: dict[tuple[UUID, int, str, date], list[RiskFreePoint]] = {}
            for row in observations:
                key = (
                    row.curve.risk_free_curve_id.value,
                    row.curve.version,
                    row.source_release_key,
                    row.effective_date,
                )
                groups.setdefault(key, []).append(row)
            for points in groups.values():
                if len({point.tenor for point in points}) != len(points):
                    raise RateConventionError("curve release contains duplicate tenors")
                for row in points:
                    content_id = _content_id("persistra.risk_free.point", row)
                    revision_id = (
                        _occurrence_id(content_id)
                        if row.canonical_revision_id is None
                        else row.canonical_revision_id.value
                    )
                    duplicate = connection.execute(
                        "SELECT canonical_revision_id FROM "
                        "canonical.market_revision_metadata WHERE content_id = ?",
                        [str(content_id)],
                    ).fetchone()
                    if duplicate is not None:
                        result.append(duplicate[0])
                        continue
                    sequence = advance_catalog(
                        connection,
                        change_kind="risk_free.point_ingested",
                        entity_id=row.curve.risk_free_curve_id,
                        change_content_id=content_id,
                        recorded_at=context.recorded_at,
                    )
                    connection.execute(
                        "INSERT INTO canonical.risk_free_points VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            revision_id,
                            row.curve.risk_free_curve_id.value,
                            row.curve.version,
                            row.source_release_key,
                            row.effective_date,
                            row.release_at,
                            row.tenor.kind.value,
                            row.tenor.count,
                            row.maturity_date,
                            row.value.envelope_value,
                            row.quote_kind.value,
                            row.compounding.value,
                            row.compounding_periods_per_year,
                            row.day_count.value,
                            str(row.source_curve_manifest_content_id),
                            _json(dict(row.source_metadata)),
                        ],
                    )
                    FundamentalService.insert_metadata(
                        connection,
                        revision_id,
                        row.source_id,
                        row.release_at,
                        row.available_at,
                        row.availability_quality.value,
                        context,
                        sequence,
                        content_id,
                    )
                    result.append(revision_id)
            return tuple(result)

        return self._project.services.transactions.run("risk_free_points_ingest", operation)

    def points(self, query: RiskFreeQuery) -> pd.DataFrame:
        resolved = self._curves.resolve(query.curve, context=query.context)
        opened, sequence = market_for_context(self._project, query.context)
        cutoff, params = cutoff_sql(query.context)
        tenor_pairs = {(tenor.kind.value, tenor.count) for tenor in query.tenors}
        rows = opened.connection.execute(
            "SELECT p.canonical_revision_id, p.risk_free_curve_id, p.curve_version, "
            "m.source_id, p.effective_date, p.release_at, m.available_at, p.tenor_kind, "
            "p.tenor_count, p.maturity_date, p.quote_kind, p.rate_or_factor, "
            "p.compounding_kind, p.compounding_periods_per_year, p.day_count_kind, "
            "p.source_curve_manifest_content_id, m.availability_quality "
            "FROM canonical.risk_free_points p JOIN "
            "canonical.market_revision_metadata m USING (canonical_revision_id) "
            "WHERE p.risk_free_curve_id = ? AND p.curve_version = ? "
            "AND p.effective_date >= ? AND p.effective_date <= ? "
            f"AND m.{cutoff.replace(' AND ', ' AND m.')} "
            "AND m.catalog_sequence <= ? ORDER BY p.effective_date, p.tenor_kind, "
            "p.tenor_count, p.release_at, p.canonical_revision_id LIMIT ?",
            [
                resolved.risk_free_curve_id.value,
                resolved.version,
                query.start_date,
                query.end_date,
                *params,
                sequence,
                query.max_rows + 1,
            ],
        ).fetchall()
        rows = [row for row in rows if (row[7], int(row[8])) in tenor_pairs]
        if len(rows) > query.max_rows:
            raise MarketDataLimitError("rate query exceeds its row ceiling")
        return build_frame(
            RISK_FREE_FRAME,
            [
                {
                    "canonical_revision_id": str(row[0]),
                    "risk_free_curve_id": str(row[1]),
                    "curve_version": int(row[2]),
                    "source_id": None if row[3] is None else str(row[3]),
                    "effective_date": row[4],
                    "release_at": row[5],
                    "available_at": row[6],
                    "tenor_kind": row[7],
                    "tenor_count": int(row[8]),
                    "maturity_date": row[9],
                    "quote_kind": row[10],
                    "rate_or_factor": float(row[11]),
                    "compounding_kind": row[12],
                    "compounding_periods_per_year": row[13],
                    "day_count_kind": row[14],
                    "source_curve_manifest_content_id": row[15],
                    "safety_status": _safe(row[16]),
                }
                for row in rows
            ],
        )

    def at(
        self,
        *,
        curve: RiskFreeCurveRef,
        effective_date: date,
        tenor: Tenor,
        context: AsOfContext,
    ) -> dict[str, Any]:
        frame = self.points(
            RiskFreeQuery(curve, effective_date, effective_date, (tenor,), context)
        )
        if frame.empty:
            return {
                "state": "missing",
                "reason_code": "rate.unavailable",
                "value": None,
            }
        row = frame.iloc[-1]
        return {
            "state": "selected",
            "reason_code": "rate.selected",
            "value": float(row["rate_or_factor"]),
            "canonical_revision_id": row["canonical_revision_id"],
        }

    def require(
        self,
        *,
        curve: RiskFreeCurveRef,
        effective_date: date,
        tenor: Tenor,
        context: AsOfContext,
    ) -> float:
        result = self.at(
            curve=curve,
            effective_date=effective_date,
            tenor=tenor,
            context=context,
        )
        if result["state"] != "selected":
            raise RateUnavailableError("exact risk-free point is unavailable")
        return float(result["value"])
