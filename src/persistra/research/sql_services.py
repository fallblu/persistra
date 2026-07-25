"""This module contains the parsed, bounded read-only SQL and immutable workspace services."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from importlib import import_module
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

import pandas as pd

from persistra.catalog.services import insert_event
from persistra.db import ProjectMode
from persistra.domain import ContentId, EntityId, QualifiedName
from persistra.domain.serialization import canonical_bytes, scoped_content_id
from persistra.errors import (
    CapabilityUnavailableError,
    ResearchResultLimitError,
    SqlQueryError,
    SqlSecurityError,
    WorkspaceConflictError,
    WorkspaceMaterializationError,
)
from persistra.research.models import ResearchDatasetBuildId
from persistra.research.sql_models import (
    DatasetBuildSqlRelation,
    InformationClass,
    LineageCompleteness,
    SafetyStatus,
    SqlDependency,
    SqlDependencyKind,
    SqlQueryAudit,
    SqlReadContext,
    SqlReadLimits,
    SqlTemporalClass,
    TemporalContractKind,
    WorkspaceMaterializationId,
    WorkspaceMaterializationLimits,
    WorkspaceMaterializationRef,
    WorkspaceObjectId,
    WorkspaceRef,
    WorkspaceSqlRelation,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from persistra.db.services import TransactionContext
    from persistra.project import Project


_ANALYZER_ID = scoped_content_id(
    {
        "schema": "persistra.research.sql_analyzer",
        "version": 1,
        "dialect": "duckdb",
        "allowlist": (
            "abs",
            "cast",
            "coalesce",
            "date_diff",
            "date_trunc",
            "greatest",
            "least",
            "lower",
            "nullif",
            "round",
            "upper",
        ),
    }
)
_ALLOWED_FUNCTIONS = {
    "ABS",
    "CAST",
    "COALESCE",
    "DATE_DIFF",
    "DATE_TRUNC",
    "GREATEST",
    "IF",
    "IFNULL",
    "LEAST",
    "LENGTH",
    "LOWER",
    "NULLIF",
    "ROUND",
    "SUBSTRING",
    "TRIM",
    "UPPER",
}
_FORBIDDEN_FUNCTION_FRAGMENTS = (
    "arrow",
    "csv",
    "database",
    "duckdb_",
    "env",
    "glob",
    "http",
    "json",
    "parquet",
    "postgres",
    "read_",
    "scan",
    "secret",
    "sqlite",
)


@dataclass(frozen=True, slots=True)
class _PreparedSql:
    sql: str
    parameters: tuple[object, ...]
    dependencies: tuple[SqlDependency, ...]
    audit: SqlQueryAudit


@dataclass(frozen=True, slots=True)
class SqlReadResult:
    """This class represents the bounded dataframe plus immutable query audit."""

    _frame: pd.DataFrame
    audit: SqlQueryAudit

    def rows(self) -> pd.DataFrame:
        """Return a defensive copy of the bounded result."""
        return self._frame.copy(deep=True)

    def iter_rows(self, *, chunk_rows: int = 100_000) -> Iterator[pd.DataFrame]:
        """Yield deterministic in-memory chunks without exposing a connection."""
        if chunk_rows < 1:
            raise ResearchResultLimitError("chunk_rows must be positive")
        for start in range(0, len(self._frame), chunk_rows):
            yield self._frame.iloc[start : start + chunk_rows].reset_index(drop=True)


class SqlReadService:
    """This class parses, classifies, binds, and executes one bounded read-only statement."""

    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def read(
        self,
        query: str,
        *,
        parameters: Sequence[object] = (),
        context: SqlReadContext,
        limits: SqlReadLimits | None = None,
    ) -> SqlReadResult:
        active_limits = limits or SqlReadLimits()
        prepared = self._prepare(query, tuple(parameters), context, active_limits)
        frame = self._execute(prepared, active_limits)
        audit = dataclass_replace(
            prepared.audit,
            output_schema_content_id=_schema_content_id(frame),
            row_count=len(frame),
        )
        return SqlReadResult(frame, audit)

    def preview(
        self,
        query: str,
        *,
        parameters: Sequence[object] = (),
        context: SqlReadContext,
        max_rows: int = 100,
    ) -> SqlReadResult:
        if max_rows < 1:
            raise SqlQueryError("preview max_rows must be positive")
        result = self.read(
            query,
            parameters=parameters,
            context=context,
            limits=SqlReadLimits(max_rows=max_rows),
        )
        return SqlReadResult(
            result.rows(),
            dataclass_replace(result.audit, truncated=True),
        )

    def _prepare(
        self,
        query: str,
        parameters: tuple[object, ...],
        context: SqlReadContext,
        limits: SqlReadLimits,
    ) -> _PreparedSql:
        sqlglot, exp = _sqlglot()
        normalized = query.replace("\r\n", "\n")
        if not normalized or len(normalized.encode("utf-8")) > 262_144:
            raise SqlQueryError("SQL text is empty or exceeds 256 KiB")
        try:
            statements = sqlglot.parse(normalized, read="duckdb")
        except Exception as error:
            raise SqlQueryError("SQL cannot be parsed as DuckDB SQL") from error
        if len(statements) != 1 or not isinstance(statements[0], exp.Select):
            raise SqlSecurityError("exactly one SELECT statement is required")
        expression = statements[0]
        nodes = tuple(expression.walk())
        if len(nodes) > 100_000:
            raise SqlQueryError("SQL AST exceeds its node ceiling")
        placeholders = tuple(expression.find_all(exp.Placeholder))
        if len(placeholders) != len(parameters) or len(parameters) > 10_000:
            raise SqlQueryError("SQL parameter count does not match placeholders")
        _validate_parameters(parameters)
        parameter_material = _parameter_material(parameters)
        if len(canonical_bytes(parameter_material)) > 16 * 1024 * 1024:
            raise SqlQueryError("SQL parameters exceed 16 MiB")
        _validate_functions(expression, exp)

        tables = tuple(expression.find_all(exp.Table))
        aliases: list[str] = []
        for table in tables:
            if table.catalog or table.db != "ctx" or not table.name:
                raise SqlSecurityError("SQL may reference only bound ctx relations")
            aliases.append(table.name)
        if not aliases:
            raise SqlSecurityError("SQL must reference at least one bound relation")
        if set(aliases) != set(context.relations):
            raise SqlSecurityError("SQL bindings must be referenced exactly")

        dependencies = tuple(
            self._resolve_dependency(index, alias, context.relations[alias])
            for index, alias in enumerate(dict.fromkeys(aliases), 1)
        )
        if len(dependencies) > limits.max_dependency_nodes:
            raise SqlQueryError("SQL dependency graph exceeds its limit")
        by_alias = {dependency.alias: dependency for dependency in dependencies}
        for table in tables:
            dependency = by_alias[table.name]
            schema, relation = dependency.physical_relation.split(".", 1)
            table.set("db", exp.to_identifier(schema, quoted=True))
            table.set("this", exp.to_identifier(relation, quoted=True))

        temporal_class, local_information = _classify(expression, exp)
        information = _fold_information(
            (
                *(dependency.information_class for dependency in dependencies),
                local_information,
            )
        )
        lineage = _fold_lineage(
            tuple(dependency.lineage_completeness for dependency in dependencies)
        )
        dependency_safe = all(
            dependency.safety_status is SafetyStatus.SAFE
            for dependency in dependencies
        )
        row_local = temporal_class is SqlTemporalClass.ROW_LOCAL
        primary = context.primary_decision_relation
        primary_dependency = None if primary is None else by_alias.get(primary)
        structurally_eligible = (
            primary_dependency is not None
            and row_local
            and information not in {InformationClass.LABEL, InformationClass.RETROSPECTIVE}
            and lineage is LineageCompleteness.COMPLETE
        )
        same_panel = all(
            dependency.temporal_contract is TemporalContractKind.DECISION_PANEL
            for dependency in dependencies
        )
        temporal_contract = (
            TemporalContractKind.DECISION_PANEL
            if structurally_eligible and same_panel
            else TemporalContractKind.OPAQUE
        )
        safety = (
            SafetyStatus.SAFE
            if dependency_safe
            and row_local
            and information is InformationClass.CAUSAL
            and lineage is LineageCompleteness.COMPLETE
            else SafetyStatus.UNSAFE
        )
        dependency_manifest = scoped_content_id(
            {
                "schema": "persistra.research.sql_dependencies",
                "dependencies": tuple(
                    {
                        "alias": item.alias,
                        "content_id": item.dependency_content_id,
                        "id": item.dependency_id,
                        "kind": item.kind,
                        "ordinal": item.ordinal,
                    }
                    for item in dependencies
                ),
            }
        )
        query_id = scoped_content_id(
            {"schema": "persistra.research.sql_text", "version": 1, "text": normalized}
        )
        parameter_id = scoped_content_id(
            {"schema": "persistra.research.sql_parameters", "values": parameter_material}
        )
        context_id = scoped_content_id(
            {
                "schema": "persistra.research.sql_context",
                "dependencies": dependency_manifest,
                "primary": primary,
            }
        )
        audit = SqlQueryAudit(
            query_id,
            parameter_id,
            context_id,
            _ANALYZER_ID,
            ContentId.from_bytes(b"pending-output-schema"),
            dependency_manifest,
            information,
            temporal_contract,
            lineage,
            temporal_class,
            safety,
            structurally_eligible,
            0,
        )
        return _PreparedSql(
            expression.sql(dialect="duckdb"),
            parameters,
            dependencies,
            audit,
        )

    def _resolve_dependency(
        self, ordinal: int, alias: str, relation: object
    ) -> SqlDependency:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        if isinstance(relation, DatasetBuildSqlRelation):
            row = connection.execute(
                "SELECT output_relation_name, output_manifest_content_id FROM "
                "research.research_dataset_builds WHERE research_dataset_build_id = ?",
                [relation.research_dataset_build_id.value],
            ).fetchone()
            if row is None:
                raise SqlQueryError("dataset build SQL dependency is unavailable")
            return SqlDependency(
                ordinal,
                alias,
                SqlDependencyKind.RESEARCH_DATASET_BUILD,
                relation.research_dataset_build_id,
                ContentId.parse(row[1]),
                InformationClass.CAUSAL,
                TemporalContractKind.DECISION_PANEL,
                LineageCompleteness.COMPLETE,
                SafetyStatus.SAFE,
                f"research_data.{row[0]}",
            )
        if isinstance(relation, WorkspaceSqlRelation):
            row = connection.execute(
                "SELECT output_relation_name, output_manifest_content_id, "
                "information_class, temporal_contract_kind, lineage_completeness, "
                "safety_status FROM research.workspace_materializations "
                "WHERE workspace_materialization_id = ?",
                [relation.workspace_materialization_id.value],
            ).fetchone()
            if row is None:
                raise SqlQueryError("workspace SQL dependency is unavailable")
            return SqlDependency(
                ordinal,
                alias,
                SqlDependencyKind.WORKSPACE_MATERIALIZATION,
                relation.workspace_materialization_id,
                ContentId.parse(row[1]),
                InformationClass(row[2]),
                TemporalContractKind(row[3]),
                LineageCompleteness(row[4]),
                SafetyStatus(row[5]),
                f"workspace.{row[0]}",
            )
        raise SqlQueryError("SQL relation binding kind is not yet materialized")

    def _execute(self, prepared: _PreparedSql, limits: SqlReadLimits) -> pd.DataFrame:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        cursor = connection.execute(
            f"SELECT * FROM ({prepared.sql}) AS bounded_result LIMIT ?",
            [*prepared.parameters, limits.max_rows + 1],
        )
        names = [str(column[0]) for column in cursor.description]
        if len(names) > limits.max_columns or len(names) != len(set(names)):
            raise SqlQueryError("SQL output columns exceed limits or are duplicated")
        frame = cast("pd.DataFrame", cursor.fetchdf())
        if len(frame) > limits.max_rows:
            raise ResearchResultLimitError("SQL result exceeds max_rows")
        _validate_frame(frame)
        return frame


class WorkspaceService:
    """This class publishes immutable, dependency-classified SQL materializations."""

    __slots__ = ("_project", "_sql")

    def __init__(self, project: Project, sql: SqlReadService) -> None:
        self._project = project
        self._sql = sql

    def materialize(
        self,
        *,
        name: QualifiedName,
        query: str,
        context: SqlReadContext,
        parameters: Sequence[object] = (),
        limits: WorkspaceMaterializationLimits | None = None,
        new_version: bool = False,
    ) -> WorkspaceMaterialization:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError(
                "workspace materialization requires research_write mode"
            )
        workspace_ref = WorkspaceRef(name)
        active_limits = limits or WorkspaceMaterializationLimits()
        read_limits = active_limits.as_read_limits()
        prepared = self._sql._prepare(  # pyright: ignore[reportPrivateUsage]
            query, tuple(parameters), context, read_limits
        )
        frame = self._sql._execute(prepared, read_limits)  # pyright: ignore[reportPrivateUsage]
        schema_id = _schema_content_id(frame)
        output_id = scoped_content_id(
            {
                "schema": "persistra.research.workspace_output",
                "columns": tuple(frame.columns),
                "data": tuple(
                    tuple(_cell(value) for value in row)
                    for row in frame.itertuples(index=False, name=None)
                ),
            }
        )

        def operation(context_tx: TransactionContext) -> WorkspaceMaterialization:
            connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            master = connection.execute(
                "SELECT workspace_object_id FROM research.workspace_objects "
                "WHERE qualified_name = ?",
                [str(workspace_ref.name)],
            ).fetchone()
            if master is None:
                object_id = WorkspaceObjectId.new()
                connection.execute(
                    "INSERT INTO research.workspace_objects VALUES (?, ?, ?)",
                    [object_id.value, str(workspace_ref.name), context_tx.recorded_at],
                )
                current_version = 0
            else:
                object_id = WorkspaceObjectId.parse(master[0])
                current_version = int(
                    connection.execute(
                        "SELECT coalesce(max(object_version), 0) FROM "
                        "research.workspace_materializations "
                        "WHERE workspace_object_id = ?",
                        [object_id.value],
                    ).fetchone()[0]
                )
            execution_id = scoped_content_id(
                {
                    "schema": "persistra.research.workspace_execution",
                    "workspace_object_id": object_id,
                    "query": prepared.audit.query_text_content_id,
                    "parameters": prepared.audit.parameters_content_id,
                    "context": prepared.audit.context_content_id,
                    "limits": active_limits,
                    "output_schema": schema_id,
                }
            )
            existing = connection.execute(
                "SELECT workspace_materialization_id FROM "
                "research.workspace_materializations WHERE execution_content_id = ?",
                [str(execution_id)],
            ).fetchone()
            if existing is not None:
                return self.get(WorkspaceMaterializationId.parse(existing[0]))
            if current_version and not new_version:
                raise WorkspaceConflictError(
                    "different workspace execution requires new_version=True"
                )
            materialization_id = WorkspaceMaterializationId.new()
            version = current_version + 1
            relation = f"materialization_{materialization_id.value.hex}"
            connection.execute(
                f'CREATE TABLE workspace."{relation}" AS '
                f"SELECT * FROM ({prepared.sql}) AS workspace_result LIMIT ?",
                [*prepared.parameters, active_limits.max_output_rows + 1],
            )
            published_count = int(
                connection.execute(
                    f'SELECT count(*) FROM workspace."{relation}"'
                ).fetchone()[0]
            )
            if published_count != len(frame):
                raise WorkspaceMaterializationError(
                    "workspace output changed during publication"
                )
            connection.execute(
                "INSERT INTO research.workspace_materializations VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    materialization_id.value,
                    object_id.value,
                    version,
                    str(prepared.audit.query_text_content_id),
                    query.replace("\r\n", "\n"),
                    str(prepared.audit.parameters_content_id),
                    canonical_bytes(_parameter_material(tuple(parameters))).decode(),
                    str(prepared.audit.analyzer_content_id),
                    str(prepared.audit.context_content_id),
                    str(scoped_content_id(active_limits)),
                    str(prepared.audit.dependency_manifest_content_id),
                    (
                        None
                        if context.primary_decision_relation is None
                        else next(
                            item.ordinal
                            for item in prepared.dependencies
                            if item.alias == context.primary_decision_relation
                        )
                    ),
                    prepared.audit.lineage_completeness.value,
                    prepared.audit.sql_temporal_class.value,
                    prepared.audit.temporal_contract.value,
                    prepared.audit.information_class.value,
                    prepared.audit.safety_status.value,
                    prepared.audit.structurally_decision_eligible,
                    str(execution_id),
                    str(schema_id),
                    relation,
                    str(output_id),
                    len(frame),
                    context_tx.recorded_at,
                ],
            )
            for item in prepared.dependencies:
                connection.execute(
                    "INSERT INTO research.workspace_dependencies VALUES "
                    "(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        materialization_id.value,
                        item.ordinal,
                        item.kind.value,
                        item.dependency_id.value,
                        str(item.dependency_content_id),
                        item.information_class.value,
                        item.temporal_contract.value,
                        item.lineage_completeness.value,
                        item.safety_status.value,
                    ],
                )
            insert_event(
                connection,
                event_name="persistra.research.workspace_materialized",
                aggregate_kind="persistra.aggregate.workspace_object",
                aggregate_id=object_id,
                aggregate_sequence=version,
                recorded_at=context_tx.recorded_at,
                payload={
                    "execution_content_id": execution_id,
                    "workspace_materialization_id": materialization_id,
                },
            )
            return self.get(materialization_id)

        return self._project.services.transactions.run("workspace_materialize", operation)

    def resolve(self, reference: WorkspaceRef) -> WorkspaceMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        version_sql = (
            "ORDER BY m.object_version DESC LIMIT 1"
            if reference.version is None
            else "AND m.object_version = ?"
        )
        parameters: list[object] = [str(reference.name)]
        if reference.version is not None:
            parameters.append(reference.version)
        row = connection.execute(
            "SELECT m.workspace_materialization_id FROM research.workspace_objects o "
            "JOIN research.workspace_materializations m USING (workspace_object_id) "
            f"WHERE o.qualified_name = ? {version_sql}",
            parameters,
        ).fetchone()
        if row is None:
            raise WorkspaceMaterializationError("workspace reference is unavailable")
        return self.get(WorkspaceMaterializationId.parse(row[0]))

    def get(
        self, materialization_id: WorkspaceMaterializationId
    ) -> WorkspaceMaterialization:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT workspace_object_id, object_version, execution_content_id, "
            "output_schema_content_id, output_manifest_content_id, row_count, "
            "information_class, temporal_contract_kind, safety_status, "
            "structurally_decision_eligible, output_relation_name "
            "FROM research.workspace_materializations "
            "WHERE workspace_materialization_id = ?",
            [materialization_id.value],
        ).fetchone()
        if row is None:
            raise WorkspaceMaterializationError("workspace materialization is unavailable")
        reference = WorkspaceMaterializationRef(
            WorkspaceObjectId.parse(row[0]),
            materialization_id,
            int(row[1]),
            ContentId.parse(row[2]),
            ContentId.parse(row[3]),
            ContentId.parse(row[4]),
            int(row[5]),
            InformationClass(row[6]),
            TemporalContractKind(row[7]),
            SafetyStatus(row[8]),
            bool(row[9]),
        )
        return WorkspaceMaterialization(self._project, reference, str(row[10]))


@dataclass(frozen=True, slots=True)
class WorkspaceMaterialization:
    """This class represents the project-owned immutable workspace handle."""

    _project: Project
    reference: WorkspaceMaterializationRef
    _relation: str

    def rows(self, *, max_rows: int = 1_000_000) -> pd.DataFrame:
        if max_rows < 1:
            raise ResearchResultLimitError("max_rows must be positive")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        frame = cast(
            "pd.DataFrame",
            connection.execute(
                f'SELECT * FROM workspace."{self._relation}" LIMIT ?',
                [max_rows + 1],
            ).fetchdf(),
        )
        if len(frame) > max_rows:
            raise ResearchResultLimitError("workspace rows exceed max_rows")
        return frame

    def dependencies(self) -> tuple[SqlDependency, ...]:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        rows = connection.execute(
            "SELECT dependency_ordinal, dependency_kind, dependency_id, "
            "dependency_content_id, information_class, temporal_contract_kind, "
            "lineage_completeness, safety_status FROM research.workspace_dependencies "
            "WHERE workspace_materialization_id = ? ORDER BY dependency_ordinal",
            [self.reference.workspace_materialization_id.value],
        ).fetchall()
        return tuple(
            SqlDependency(
                int(row[0]),
                f"dependency_{row[0]}",
                SqlDependencyKind(row[1]),
                _dependency_id(SqlDependencyKind(row[1]), row[2]),
                ContentId.parse(row[3]),
                InformationClass(row[4]),
                TemporalContractKind(row[5]),
                LineageCompleteness(row[6]),
                SafetyStatus(row[7]),
                "",
            )
            for row in rows
        )


def _sqlglot() -> tuple[Any, Any]:
    sqlglot = cast("Any", import_module("sqlglot"))
    exp = cast("Any", import_module("sqlglot.expressions"))
    return sqlglot, exp


def _dependency_id(kind: SqlDependencyKind, value: object) -> EntityId:
    if kind is SqlDependencyKind.RESEARCH_DATASET_BUILD:
        return ResearchDatasetBuildId.parse(value)
    if kind is SqlDependencyKind.WORKSPACE_MATERIALIZATION:
        return WorkspaceMaterializationId.parse(value)
    raise WorkspaceMaterializationError("stored dependency identity kind is unsupported")


def _validate_parameters(parameters: tuple[object, ...]) -> None:
    allowed = (bool, int, float, str, Decimal, date, datetime, UUID, EntityId)
    for value in parameters:
        if value is None or not isinstance(value, allowed):
            raise SqlQueryError("SQL parameter type is unsupported")
        if isinstance(value, float) and not math.isfinite(value):
            raise SqlQueryError("SQL parameters must be finite")
        if isinstance(value, datetime) and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise SqlQueryError("SQL timestamp parameters must be timezone-aware")


def _parameter_material(parameters: tuple[object, ...]) -> tuple[object, ...]:
    result: list[object] = []
    for value in parameters:
        if isinstance(value, float):
            result.append({"float64_hex": value.hex()})
        elif isinstance(value, UUID):
            result.append({"uuid": str(value)})
        else:
            result.append(value)
    return tuple(result)


def _validate_functions(expression: Any, exp: Any) -> None:
    for function in expression.find_all(exp.Func):
        name = str(function.sql_name()).upper()
        lowered = name.lower()
        if isinstance(function, exp.Anonymous) and name not in _ALLOWED_FUNCTIONS:
            raise SqlSecurityError(f"SQL function {name!r} is not allowlisted")
        if any(fragment in lowered for fragment in _FORBIDDEN_FUNCTION_FRAGMENTS):
            raise SqlSecurityError(f"SQL function {name!r} is forbidden")


def _classify(expression: Any, exp: Any) -> tuple[SqlTemporalClass, InformationClass]:
    for node in expression.walk():
        name = type(node).__name__.lower()
        if name == "lead":
            return SqlTemporalClass.OPAQUE, InformationClass.RETROSPECTIVE
        if isinstance(
            node,
            (
                exp.AggFunc,
                exp.Distinct,
                exp.Limit,
                exp.Offset,
                exp.SetOperation,
                exp.Subquery,
                exp.Window,
            ),
        ):
            return SqlTemporalClass.OPAQUE, InformationClass.OPAQUE
    return SqlTemporalClass.ROW_LOCAL, InformationClass.CAUSAL


def _fold_information(values: tuple[InformationClass, ...]) -> InformationClass:
    order = {
        InformationClass.CAUSAL: 0,
        InformationClass.OPAQUE: 1,
        InformationClass.RETROSPECTIVE: 2,
        InformationClass.LABEL: 3,
    }
    return max(values, key=order.__getitem__)


def _fold_lineage(values: tuple[LineageCompleteness, ...]) -> LineageCompleteness:
    order = {
        LineageCompleteness.COMPLETE: 0,
        LineageCompleteness.PARTIAL: 1,
        LineageCompleteness.OPAQUE: 2,
    }
    return max(values, key=order.__getitem__)


def _schema_content_id(frame: pd.DataFrame) -> ContentId:
    return scoped_content_id(
        {
            "schema": "persistra.research.dynamic_frame_schema",
            "columns": tuple(
                {
                    "dtype": str(frame[column].dtype),
                    "name": str(column),
                    "nullable": bool(frame[column].isna().any()),
                }
                for column in frame.columns
            ),
        }
    )


def _validate_frame(frame: pd.DataFrame) -> None:
    for column in frame.columns:
        if not column:
            raise SqlQueryError("SQL output columns must be named strings")
        series = frame[column]
        if pd.api.types.is_float_dtype(series.dtype):
            values = series.dropna()
            if not values.map(math.isfinite).all():
                raise SqlQueryError("SQL output contains nonfinite floats")


def _cell(value: Any) -> object:
    if pd.isna(value):
        return None
    if isinstance(value, float):
        return {"float64_hex": value.hex()}
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, UUID):
        return str(value)
    return value


def dataclass_replace(value: Any, **changes: object) -> Any:
    import dataclasses

    return dataclasses.replace(value, **changes)
