"""This module contains the public-API-only bounded dashboard page queries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

from persistra.analysis import AnalysisArtifactId
from persistra.dashboard.cache import DashboardCacheKey, DashboardDataCache
from persistra.dashboard.configuration import (
    DashboardLimits,
    DashboardSource,
    PortableExportSource,
)
from persistra.dashboard.source import portable_run, project_scope, source_fingerprint
from persistra.errors import DashboardPageError, DashboardQueryLimitError
from persistra.experiments import StudyId
from persistra.results import RunRecordId
from persistra.viz import (
    FigureConfig,
    ThemeRef,
    attribution,
    diagnostics,
    execution,
    performance,
    portfolio,
    provenance,
)

if TYPE_CHECKING:
    from persistra.results.services import RunHandle


@dataclass(frozen=True, slots=True)
class DashboardTable:
    name: str
    frame: pd.DataFrame


@dataclass(frozen=True, slots=True)
class DashboardFigure:
    name: str
    figure_json: str


@dataclass(frozen=True, slots=True)
class DashboardPageResult:
    page: str
    run_record_id: str
    source_root: str
    tables: tuple[DashboardTable, ...]
    figures: tuple[DashboardFigure, ...]
    warnings: tuple[str, ...]
    unavailable: tuple[str, ...]
    cache_key: DashboardCacheKey


class DashboardData:
    """This class materializes pages in short-lived read scopes and caches only detached values."""

    __slots__ = (
        "_cache",
        "_display_timezone",
        "_limits",
        "_source",
        "_source_fingerprint",
        "_theme",
    )

    def __init__(
        self,
        source: DashboardSource,
        *,
        limits: DashboardLimits,
        theme: ThemeRef | None = None,
        display_timezone: str = "UTC",
    ) -> None:
        self._source = source
        self._limits = limits
        self._theme = theme or ThemeRef()
        self._display_timezone = display_timezone
        self._source_fingerprint = source_fingerprint(
            source,
            max_rows_per_table=limits.max_query_rows,
        )
        self._cache = DashboardDataCache(
            max_entries=limits.max_cache_entries,
            max_bytes=limits.max_cache_bytes,
        )

    def runs(self) -> pd.DataFrame:
        if isinstance(self._source, PortableExportSource):
            run = portable_run(
                self._source,
                max_rows_per_table=self._limits.max_query_rows,
            )
            summary = run.summary()
            return pd.DataFrame(
                [
                    {
                        "run_record_id": str(run.id),
                        "execution_content_id": str(summary.execution_content_id),
                        "result_manifest_content_id": str(
                            summary.result_manifest_content_id
                        ),
                        "decision_count": summary.decision_count,
                        "fill_count": summary.fill_count,
                        "retention_state": "portable",
                    }
                ]
            )
        with project_scope(self._source) as project:
            frame = project.services.results.list(max_rows=self._limits.max_runs).copy()
            frame["run_record_id"] = frame["run_record_id"].map(
                lambda value: str(RunRecordId.parse(str(value)))
            )
            return frame

    def query(self, run_record_id: str, page: str) -> DashboardPageResult:
        run_id = RunRecordId.parse(run_record_id)
        if isinstance(self._source, PortableExportSource):
            run = portable_run(
                self._source,
                max_rows_per_table=self._limits.max_query_rows,
            )
            if run.id != run_id:
                raise DashboardPageError("portable export does not contain the selected run")
            return self._query_run(cast("RunHandle", run), page, None)
        with project_scope(self._source) as project:
            run = project.services.results.get(run_id)
            return self._query_run(run, page, project)

    def _query_run(
        self,
        run: RunHandle,
        page: str,
        project: Any | None,
    ) -> DashboardPageResult:
        root = run.summary().result_manifest_content_id
        key = DashboardCacheKey.build(
            source_fingerprint=self._source_fingerprint,
            subject_root=root,
            page=page,
            parameters={
                "max_rows": self._limits.max_query_rows,
                "figure": self._limits.figure,
                "theme": self._theme,
                "display_timezone": self._display_timezone,
            },
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cast("DashboardPageResult", cached)
        config = FigureConfig(
            limits=self._limits.figure,
            theme=self._theme,
            display_timezone=self._display_timezone,
        )
        tables: list[DashboardTable] = []
        figures: list[DashboardFigure] = []
        unavailable: list[str] = []

        def table(name: str, frame: pd.DataFrame) -> None:
            if len(frame) > self._limits.max_query_rows:
                raise DashboardQueryLimitError("dashboard table exceeds max_query_rows")
            tables.append(DashboardTable(name, frame.copy()))

        def figure(name: str, value: Any) -> None:
            figures.append(DashboardFigure(name, str(value.to_json())))

        if page == "overview":
            summary = run.summary()
            table(
                "run summary",
                pd.DataFrame(
                    [
                        {
                            "run_record_id": str(run.id),
                            "decision_count": summary.decision_count,
                            "fill_count": summary.fill_count,
                            **run.provenance(),
                        }
                    ]
                ),
            )
            table("provenance", pd.DataFrame([{"run_record_id": str(run.id), **run.provenance()}]))
            figure("Run provenance", provenance.roots(run, config=config))
            if project is not None:
                artifacts = project.services.analysis.list(
                    run_record_id=run.id,
                    max_rows=self._limits.max_query_rows,
                )
                metrics_rows = artifacts[artifacts["artifact_kind"] == "metrics"]
                if not metrics_rows.empty:
                    metrics = project.services.analysis.metrics.get(
                        AnalysisArtifactId.parse(
                            str(metrics_rows.iloc[-1]["analysis_artifact_id"])
                        )
                    )
                    table(
                        "headline metrics",
                        pd.DataFrame(
                            [
                                {
                                    "metric": item.metric_name,
                                    "state": item.state.value,
                                    "estimate": item.estimate,
                                    "unit": item.unit,
                                    "reason": item.reason_code,
                                }
                                for item in metrics.results()
                            ]
                        ),
                    )
                    figure("Metrics", performance.metric_summary(metrics, config=config))
        elif page == "performance":
            table("equity", run.equity(max_rows=self._limits.max_query_rows))
            table("returns", run.returns(max_rows=self._limits.max_query_rows))
            figure("Equity", performance.equity(run, config=config))
            figure("Returns", performance.returns(run, config=config))
        elif page == "portfolio":
            table("positions", run.positions(max_rows=self._limits.max_query_rows))
            table("cash", run.cash(max_rows=self._limits.max_query_rows))
            table("targets", run.targets(max_rows=self._limits.max_query_rows))
            figure("Exposure", portfolio.exposure(run, config=config))
            figure("Positions", portfolio.positions(run, config=config))
            figure("Target shortfall", portfolio.target_shortfall(run, config=config))
        elif page == "execution":
            table("fills", run.fills(max_rows=self._limits.max_query_rows))
            table("costs", run.costs(max_rows=self._limits.max_query_rows))
            figure("Fills", execution.fills(run, config=config))
            figure("Costs", execution.costs(run, config=config))
            unavailable.append(
                "Order lifecycle is not applicable to normalized vectorized run exports."
            )
        elif page == "attribution":
            if project is None:
                unavailable.append(
                    "Attribution artifacts are not included in this portable export."
                )
            else:
                artifacts = project.services.analysis.list(
                    run_record_id=run.id,
                    max_rows=self._limits.max_query_rows,
                )
                table("analysis artifacts", artifacts)
                matches = artifacts[artifacts["artifact_kind"] == "attribution"]
                if matches.empty:
                    unavailable.append(
                        "No immutable attribution analysis exists; "
                        "the dashboard will not compute one."
                    )
                else:
                    handle = project.services.analysis.get_tabular(
                        AnalysisArtifactId.parse(str(matches.iloc[-1]["analysis_artifact_id"]))
                    )
                    table("attribution", handle.results(max_rows=self._limits.max_query_rows))
                    figure("Attribution", attribution.contributions(handle, config=config))
        elif page == "diagnostics":
            table("journal", run.journal(max_rows=self._limits.max_query_rows))
            table("fidelity", pd.DataFrame({"finding": list(run.fidelity())}))
            figure("Fidelity", diagnostics.fidelity(run, config=config))
        elif page == "studies":
            if project is None:
                unavailable.append("Study metadata is not included in this portable export.")
            else:
                studies = project.services.experiments.list(
                    max_rows=self._limits.max_query_rows
                )
                table("studies", studies)
                if not studies.empty:
                    study = project.services.experiments.get(
                        StudyId.parse(str(studies.iloc[-1]["study_id"]))
                    )
                    table(
                        "run plans",
                        study.run_plans(max_rows=self._limits.max_query_rows),
                    )
                    table(
                        "attempts",
                        study.attempts(max_rows=self._limits.max_query_rows),
                    )
                    table(
                        "trials",
                        study.trials(max_rows=self._limits.max_query_rows),
                    )
                    table(
                        "scenarios",
                        study.scenarios(max_rows=self._limits.max_query_rows),
                    )
        elif page == "inspection":
            table("provenance", pd.DataFrame([run.provenance()]))
            table("targets", run.targets(max_rows=self._limits.max_query_rows))
            if project is None:
                unavailable.append(
                    "Canonical data and feature inspection is unavailable in a run-only export."
                )
            else:
                table(
                    "analysis artifacts",
                    project.services.analysis.list(
                        run_record_id=run.id,
                        max_rows=self._limits.max_query_rows,
                    ),
                )
                table(
                    "annotations",
                    project.services.results.annotations(
                        run.id,
                        max_rows=self._limits.max_query_rows,
                    ),
                )
        else:
            raise DashboardPageError(f"unknown dashboard page: {page}")
        result = DashboardPageResult(
            page,
            str(run.id),
            str(root),
            tuple(tables),
            tuple(figures),
            run.fidelity(),
            tuple(unavailable),
            key,
        )
        byte_count = sum(
            len(item.figure_json.encode("utf-8")) for item in figures
        ) + sum(
            int(item.frame.memory_usage(index=True, deep=True).sum())
            for item in tables
        )
        self._cache.put(key, result, byte_count=byte_count)
        return result
