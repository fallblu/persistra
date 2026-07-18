from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("cvxpy")

from persistra import Project, ProjectMode
from persistra.catalog.models import CompositeSnapshotId
from persistra.db.connection import ManagedConnection
from persistra.domain import ContentId, FixedClock, QualifiedName
from persistra.portfolio import (
    DirectForecastDefinition,
    ForecastRef,
    ForecastTargetKind,
    OptimizationAttemptStatus,
    OptimizationRequest,
    PsdPolicy,
    RiskModelDefinition,
    RiskModelKind,
    RiskModelRef,
)
from persistra.reference import InstrumentId, UniverseEvaluationId
from persistra.research import ResearchDatasetBuildId, ResearchDatasetId

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 2, 2, 12, tzinfo=UTC)


def _seed_decision_build(tmp_path: Path) -> tuple[Path, ResearchDatasetBuildId]:
    layout = Project.init(tmp_path / "project")
    build_id = ResearchDatasetBuildId.new()
    relation = f"dataset_{build_id.value.hex}"
    instruments = [InstrumentId.new() for _ in range(3)]
    assert layout.research_database_path is not None
    connection = ManagedConnection(layout.research_database_path, read_only=False)
    try:
        connection.execute(
            f'CREATE TABLE research_data."{relation}" ('
            "research_dataset_build_id UUID NOT NULL, decision_at TIMESTAMPTZ NOT NULL, "
            "session_date DATE NOT NULL, instrument_id UUID NOT NULL, "
            "alpha DOUBLE NOT NULL, alpha_state VARCHAR NOT NULL, "
            "alpha_available_at TIMESTAMPTZ NOT NULL, "
            "alpha_lineage_content_id VARCHAR NOT NULL, "
            "asset_return DOUBLE NOT NULL, asset_return_state VARCHAR NOT NULL)"
        )
        rows: list[tuple[object, ...]] = []
        for decision_index in range(4):
            decision = datetime(2026, 1, 2 + decision_index, 21, tzinfo=UTC)
            for asset_index, instrument in enumerate(instruments, 1):
                rows.append(
                    (
                        build_id.value,
                        decision,
                        date(2026, 1, 2 + decision_index),
                        instrument.value,
                        float(asset_index),
                        "computed",
                        decision,
                        str(
                            ContentId.from_bytes(
                                f"alpha-{decision_index}-{asset_index}".encode()
                            )
                        ),
                        0.002
                        * asset_index
                        * (decision_index - 1.5),
                        "computed",
                    )
                )
        connection.executemany(
            f'INSERT INTO research_data."{relation}" VALUES '
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        connection.execute(
            "INSERT INTO research.research_dataset_builds VALUES "
            "(?, ?, 1, ?, ?, ?, ?, ?, 12, 12, ?)",
            [
                build_id.value,
                ResearchDatasetId.new().value,
                CompositeSnapshotId.new().value,
                UniverseEvaluationId.new().value,
                str(ContentId.from_bytes(b"portfolio-execution")),
                relation,
                str(ContentId.from_bytes(b"portfolio-output")),
                NOW,
            ],
        )
        connection.execute(
            "INSERT INTO research.research_dataset_enrichments VALUES "
            "(?, ?, 'decision', 'causal', 'decision_panel', 'complete', 'safe', true)",
            [build_id.value, build_id.value],
        )
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    return layout.root, build_id


def test_forecast_risk_and_verified_optimization(tmp_path: Path) -> None:
    root, build_id = _seed_decision_build(tmp_path)
    forecast_definition = DirectForecastDefinition(
        QualifiedName("forecast.direct_alpha"),
        1,
        build_id,
        "alpha",
        ForecastTargetKind.SIMPLE_RETURN,
        1,
        multiplier="0.01",
    )
    risk_definition = RiskModelDefinition(
        QualifiedName("risk.sample"),
        1,
        build_id,
        "asset_return",
        RiskModelKind.FIXED_SHRINKAGE,
        3,
        2,
        shrinkage="0.2",
        psd_policy=PsdPolicy.EIGENVALUE_CLIP,
    )
    decision = datetime(2026, 1, 5, 21, tzinfo=UTC)

    with Project.open(
        root, mode=ProjectMode.RESEARCH_WRITE, clock=FixedClock(NOW)
    ) as project:
        project.services.portfolio.forecasts.register(forecast_definition)
        forecast = project.services.portfolio.forecasts.materialize(
            ForecastRef(forecast_definition.name, forecast_definition.version)
        )
        project.services.portfolio.risk.register(risk_definition)
        risk = project.services.portfolio.risk.materialize(
            RiskModelRef(risk_definition.name, risk_definition.version)
        )
        result = project.services.portfolio.optimization.construct(
            OptimizationRequest(
                forecast.reference.forecast_materialization_id,
                risk.reference.risk_materialization_id,
                decision,
                maximum_weight="0.6",
            )
        )
        retry = project.services.portfolio.optimization.construct(
            OptimizationRequest(
                forecast.reference.forecast_materialization_id,
                risk.reference.risk_materialization_id,
                decision,
                maximum_weight="0.6",
            )
        )
        assert retry.reference == result.reference
        assert result.reference.status is OptimizationAttemptStatus.OPTIMAL
        assert result.reference.maximum_violation <= 1e-6
        assert result.weights()["target_weight"].sum() == pytest.approx(1.0)
