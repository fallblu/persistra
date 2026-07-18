from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("sqlglot")

from persistra import Project, ProjectMode
from persistra.catalog.models import CompositeSnapshotId
from persistra.db.connection import ManagedConnection
from persistra.domain import ContentId, FixedClock, QualifiedName
from persistra.errors import SqlSecurityError, WorkspaceConflictError
from persistra.reference import InstrumentId, UniverseEvaluationId
from persistra.research import (
    DatasetBuildSqlRelation,
    InformationClass,
    ResearchDatasetBuildId,
    ResearchDatasetId,
    SafetyStatus,
    SqlReadContext,
    WorkspaceSqlRelation,
)

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 2, 2, 12, tzinfo=UTC)


def _seed_build(tmp_path: Path) -> tuple[Path, ResearchDatasetBuildId]:
    layout = Project.init(tmp_path / "project")
    build_id = ResearchDatasetBuildId.new()
    relation = f"dataset_{build_id.value.hex}"
    assert layout.research_database_path is not None
    connection = ManagedConnection(layout.research_database_path, read_only=False)
    try:
        connection.execute(
            f'CREATE TABLE research_data."{relation}" ('
            "decision_at TIMESTAMPTZ NOT NULL, instrument_id UUID NOT NULL, "
            "close DOUBLE NOT NULL)"
        )
        connection.executemany(
            f'INSERT INTO research_data."{relation}" VALUES (?, ?, ?)',
            [
                (datetime(2026, 1, 2, 21, tzinfo=UTC), InstrumentId.new().value, 100.0),
                (datetime(2026, 1, 5, 21, tzinfo=UTC), InstrumentId.new().value, 102.0),
            ],
        )
        connection.execute(
            "INSERT INTO research.research_dataset_builds VALUES "
            "(?, ?, 1, ?, ?, ?, ?, ?, 2, 2, ?)",
            [
                build_id.value,
                ResearchDatasetId.new().value,
                CompositeSnapshotId.new().value,
                UniverseEvaluationId.new().value,
                str(ContentId.from_bytes(b"sql-fixture-execution")),
                relation,
                str(ContentId.from_bytes(b"sql-fixture-output")),
                NOW,
            ],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return layout.root, build_id


def test_read_only_sql_and_workspace_preserve_dependency_safety(tmp_path: Path) -> None:
    root, build_id = _seed_build(tmp_path)
    context = SqlReadContext(
        {"dataset": DatasetBuildSqlRelation(build_id)},
        primary_decision_relation="dataset",
    )
    query = (
        "SELECT decision_at, instrument_id, close FROM ctx.dataset "
        "WHERE close > ? ORDER BY decision_at, instrument_id"
    )
    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        result = project.services.research.sql.read(
            query, parameters=(100.0,), context=context
        )
        assert result.rows()["close"].tolist() == [102.0]
        assert result.audit.information_class is InformationClass.CAUSAL
        assert result.audit.safety_status is SafetyStatus.SAFE
        assert result.audit.structurally_decision_eligible

        with pytest.raises(SqlSecurityError):
            project.services.research.sql.read(
                "SELECT * FROM read_csv('/tmp/secret.csv')",
                context=context,
            )

        first = project.services.research.workspace.materialize(
            name=QualifiedName("workspace.cleaned_prices"),
            query=query,
            parameters=(100.0,),
            context=context,
        )
        retry = project.services.research.workspace.materialize(
            name=QualifiedName("workspace.cleaned_prices"),
            query=query,
            parameters=(100.0,),
            context=context,
        )
        assert retry.reference == first.reference
        assert first.rows()["close"].tolist() == [102.0]
        assert first.reference.structurally_decision_eligible

        changed_query = query.replace("100.0", "100.0").replace("close > ?", "close >= ?")
        with pytest.raises(WorkspaceConflictError):
            project.services.research.workspace.materialize(
                name=QualifiedName("workspace.cleaned_prices"),
                query=changed_query,
                parameters=(100.0,),
                context=context,
            )
        second = project.services.research.workspace.materialize(
            name=QualifiedName("workspace.cleaned_prices"),
            query=changed_query,
            parameters=(100.0,),
            context=context,
            new_version=True,
        )
        assert second.reference.object_version == 2

        opaque = project.services.research.workspace.materialize(
            name=QualifiedName("workspace.price_summary"),
            query="SELECT avg(close) AS mean_close FROM ctx.prices",
            context=SqlReadContext(
                {
                    "prices": WorkspaceSqlRelation(
                        first.reference.workspace_materialization_id
                    )
                }
            ),
        )
        assert opaque.reference.information_class is InformationClass.OPAQUE
        assert opaque.reference.safety_status is SafetyStatus.UNSAFE
        assert not opaque.reference.structurally_decision_eligible
