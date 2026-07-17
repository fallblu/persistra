"""Managed self-contained HTML report planning and rendering."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.analysis import AnalysisArtifactId
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    CapabilityUnavailableError,
    ReportPlanningError,
    ReportRenderError,
    VisualizationExtraRequiredError,
)
from persistra.reports.models import (
    ReportOutputId,
    ReportPlan,
    ReportPlanId,
    ReportRef,
    ReportRequest,
)
from persistra.viz import performance

if TYPE_CHECKING:
    from persistra.db.services import TransactionContext
    from persistra.project import Project


class ReportService:
    __slots__ = ("_project",)

    def __init__(self, project: Project) -> None:
        self._project = project

    def plan(self, request: ReportRequest) -> ReportPlan:
        if not request.title or len(request.title) > 200:
            raise ReportPlanningError("report title is invalid")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        run = connection.execute(
            "SELECT result_manifest_content_id FROM results.run_records "
            "WHERE run_record_id = ?",
            [request.run_record_id.value],
        ).fetchone()
        metrics = connection.execute(
            "SELECT output_content_id, run_record_id FROM analysis.artifacts "
            "WHERE analysis_artifact_id = ? AND artifact_kind = 'metrics'",
            [request.metrics_artifact_id.value],
        ).fetchone()
        if run is None or metrics is None or metrics[1] != request.run_record_id.value:
            raise ReportPlanningError("report run and metrics do not resolve together")
        execution = scoped_content_id(
            {
                "schema": "persistra.report.vectorized_execution@1",
                "request": request,
                "run_manifest": run[0],
                "metrics_output": metrics[0],
                "template": "persistra.report.run_vectorized.phase4@1",
            }
        )
        existing = connection.execute(
            "SELECT report_plan_id FROM analysis.report_plans "
            "WHERE execution_content_id = ?",
            [str(execution)],
        ).fetchone()
        if existing is not None:
            return ReportPlan(ReportPlanId.parse(existing[0]), request, execution)
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("report planning requires research_write mode")

        def operation(context: TransactionContext) -> ReportPlan:
            plan_id = ReportPlanId.new()
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            active.execute(
                "INSERT INTO analysis.report_plans VALUES (?, ?, ?, ?, ?)",
                [
                    plan_id.value,
                    request.run_record_id.value,
                    request.metrics_artifact_id.value,
                    str(execution),
                    context.recorded_at,
                ],
            )
            return ReportPlan(plan_id, request, execution)

        return self._project.services.transactions.run("report_plan", operation)

    def render(self, plan: ReportPlan) -> ReportHandle:
        if self._project._mode is not ProjectMode.RESEARCH_WRITE:  # pyright: ignore[reportPrivateUsage]
            raise CapabilityUnavailableError("report rendering requires research_write mode")
        verified = self.plan(plan.request)
        if verified.execution_content_id != plan.execution_content_id:
            raise ReportPlanningError("report plan content does not verify")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        existing = connection.execute(
            "SELECT report_output_id FROM analysis.report_outputs WHERE report_plan_id = ?",
            [verified.report_plan_id.value],
        ).fetchone()
        if existing is not None:
            return self.get(ReportOutputId.parse(existing[0]))
        run = self._project.services.results.get(plan.request.run_record_id)
        metrics = self._project.services.analysis.metrics.get(
            plan.request.metrics_artifact_id
        )
        try:
            figure = performance.equity(run)
            figure_html = figure.to_html(
                full_html=False,
                include_plotlyjs=True,
                config={"displaylogo": False, "responsive": True},
            )
        except VisualizationExtraRequiredError:
            raise
        except Exception as error:
            raise ReportRenderError("equity figure rendering failed") from error
        metric_rows = [
            {
                "name": item.metric_name,
                "state": item.state.value,
                "value": (
                    "Unavailable"
                    if item.estimate is None
                    else f"{item.estimate:.6f}"
                ),
                "unit": item.unit,
                "reason": item.reason_code or "",
            }
            for item in metrics.results()
        ]
        manifest = {
            "schema": "persistra.report.run_vectorized.phase4@1",
            "run_record_id": str(run.id),
            "metrics_artifact_id": str(metrics.id),
            "report_execution_content_id": str(plan.execution_content_id),
            "run_provenance": run.provenance(),
            "fidelity_findings": list(run.fidelity()),
            "sections": ["summary", "performance", "fidelity", "provenance"],
        }
        rendered = _render_html(
            title=plan.request.title,
            metric_rows=metric_rows,
            figure_html=figure_html,
            manifest=manifest,
        )
        output_content_id = ContentId.from_bytes(rendered)

        def operation(context: TransactionContext) -> ReportHandle:
            active = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
            artifact_id = AnalysisArtifactId.new()
            active.execute(
                "INSERT INTO analysis.artifacts VALUES (?, ?, ?, ?, ?, ?)",
                [
                    artifact_id.value,
                    "report",
                    run.id.value,
                    str(plan.execution_content_id),
                    str(output_content_id),
                    context.recorded_at,
                ],
            )
            output_id = ReportOutputId.new()
            active.execute(
                "INSERT INTO analysis.report_outputs VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    output_id.value,
                    verified.report_plan_id.value,
                    artifact_id.value,
                    str(output_content_id),
                    rendered,
                    len(rendered),
                    context.recorded_at,
                ],
            )
            return ReportHandle(
                self._project,
                ReportRef(
                    output_id,
                    verified.report_plan_id,
                    artifact_id,
                    output_content_id,
                    len(rendered),
                ),
            )

        return self._project.services.transactions.run("report_render", operation)

    def get(self, output_id: ReportOutputId) -> ReportHandle:
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT report_plan_id, analysis_artifact_id, output_content_id, byte_count "
            "FROM analysis.report_outputs WHERE report_output_id = ?",
            [output_id.value],
        ).fetchone()
        if row is None:
            raise ReportRenderError("report output is missing")
        return ReportHandle(
            self._project,
            ReportRef(
                output_id,
                ReportPlanId.parse(row[0]),
                AnalysisArtifactId.parse(row[1]),
                ContentId.parse(row[2]),
                int(row[3]),
            ),
        )


def _render_html(
    *,
    title: str,
    metric_rows: list[dict[str, str]],
    figure_html: str,
    manifest: dict[str, Any],
) -> bytes:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(row['name'])}</td>"
        f"<td>{html.escape(row['state'])}</td>"
        f"<td>{html.escape(row['value'])}</td>"
        f"<td>{html.escape(row['unit'])}</td>"
        f"<td>{html.escape(row['reason'])}</td>"
        "</tr>"
        for row in metric_rows
    )
    manifest_json = json.dumps(manifest, sort_keys=True, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    warnings = "".join(
        f"<li>{html.escape(item)}</li>" for item in manifest["fidelity_findings"]
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
 content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline';
 img-src data:; font-src data:">
<title>{html.escape(title)}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2rem auto;
padding:0 1rem;color:#172033}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:.55rem;border:1px solid #cbd5e1;text-align:left}}
.warning{{border-left:5px solid #b45309;background:#fffbeb;padding:1rem}}
code{{word-break:break-all}}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<section><h2>Summary metrics</h2>
<table><thead><tr><th>Metric</th><th>State</th><th>Value</th><th>Unit</th><th>Warning</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section><h2>Performance</h2>{figure_html}</section>
<section class="warning"><h2>Fidelity limitations</h2><ul>{warnings}</ul></section>
<section><h2>Provenance</h2>
<p>Run: <code>{html.escape(manifest["run_record_id"])}</code></p>
<p>Report execution: <code>{html.escape(manifest["report_execution_content_id"])}</code></p>
</section>
<script type="application/json" id="persistra-report-manifest">{manifest_json}</script>
</body></html>"""
    return document.encode("utf-8")


@dataclass(frozen=True, slots=True)
class ReportHandle:
    _project: Project
    reference: ReportRef

    def open_bytes(self, *, max_bytes: int = 500_000_000) -> bytes:
        if self.reference.byte_count > max_bytes:
            raise ReportRenderError("report exceeds max_bytes")
        connection = self._project._primary_connection()  # pyright: ignore[reportPrivateUsage]
        row = connection.execute(
            "SELECT html_bytes FROM analysis.report_outputs WHERE report_output_id = ?",
            [self.reference.report_output_id.value],
        ).fetchone()
        if row is None:
            raise ReportRenderError("report bytes are missing")
        value = bytes(row[0])
        if ContentId.from_bytes(value) != self.reference.output_content_id:
            raise ReportRenderError("report byte checksum does not verify")
        return value

    def copy_to(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.write_bytes(self.open_bytes())
        return destination
