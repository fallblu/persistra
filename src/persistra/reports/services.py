"""This module contains the managed self-contained HTML report planning and rendering."""

from __future__ import annotations

import hashlib
import html
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from persistra._identity import scoped_identity_content_id as scoped_content_id
from persistra.analysis import AnalysisArtifactId
from persistra.db import ProjectMode
from persistra.domain import ContentId
from persistra.errors import (
    CapabilityUnavailableError,
    ReportPlanningError,
    ReportRenderError,
    ReportSecurityError,
    ReportVerificationError,
)
from persistra.reports.models import (
    ReportBundleRef,
    ReportOutputId,
    ReportPlan,
    ReportPlanId,
    ReportRef,
    ReportRequest,
)
from persistra.viz import diagnostics, execution, performance, portfolio, provenance

if TYPE_CHECKING:
    from collections.abc import Callable

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
                "template": "persistra.report.run_vectorized@1",
                "output_mode": request.output_mode,
                "sections": request.sections,
                "limits": request.limits,
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
            section_html = _figure_sections(run, metrics, plan.request.sections)
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
            "schema": "persistra.report.run_vectorized@1",
            "run_record_id": str(run.id),
            "metrics_artifact_id": str(metrics.id),
            "report_execution_content_id": str(plan.execution_content_id),
            "run_provenance": run.provenance(),
            "fidelity_findings": list(run.fidelity()),
            "output_mode": plan.request.output_mode.value,
            "sections": [name for name, _title, _body in section_html],
        }
        rendered = _render_html(
            title=plan.request.title,
            metric_rows=metric_rows,
            sections=section_html,
            manifest=manifest,
        )
        if len(rendered) > plan.request.limits.max_report_bytes:
            raise ReportRenderError("report exceeds max_report_bytes")
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

    def verify_bundle(self, path: str | Path) -> ContentId:
        """Verify a closed report directory without opening its HTML."""
        return verify_bundle(path)

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
    sections: list[tuple[str, str, str]],
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
    rendered_sections = "".join(
        f'<section id="{html.escape(name)}"><h2>{html.escape(title)}</h2>{body}</section>'
        for name, title, body in sections
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
*:focus-visible{{outline:3px solid #2563eb;outline-offset:2px}}
table{{border-collapse:collapse;width:100%}}
th,td{{padding:.55rem;border:1px solid #cbd5e1;text-align:left}}
.warning{{border-left:5px solid #b45309;background:#fffbeb;padding:1rem}}
code{{word-break:break-all}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>
</head>
<body>
<h1>{html.escape(title)}</h1>
<section><h2>Summary metrics</h2>
<table><thead><tr><th>Metric</th><th>State</th><th>Value</th><th>Unit</th><th>Warning</th></tr></thead>
<tbody>{rows}</tbody></table></section>
{rendered_sections}
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
        if destination.exists():
            raise FileExistsError(f"report destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(f".{destination.name}.partial")
        staging.write_bytes(self.open_bytes())
        os.replace(staging, destination)
        return destination

    def copy_bundle_to(self, path: str | Path) -> ReportBundleRef:
        """Publish and verify a checksum-closed relocatable offline bundle."""
        destination = Path(path).resolve()
        if destination.exists():
            raise FileExistsError(f"report bundle destination already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_name(f".{destination.name}.partial")
        if staging.exists():
            raise ReportSecurityError("report bundle staging destination already exists")
        try:
            staging.mkdir()
            report_path = staging / "index.html"
            report_path.write_bytes(self.open_bytes())
            files = [
                {
                    "path": "index.html",
                    "sha256": _sha256(report_path),
                    "byte_count": report_path.stat().st_size,
                }
            ]
            semantic_manifest = {
                "schema": "persistra.report.directory_bundle@1",
                "report_output_id": str(self.reference.report_output_id),
                "report_output_content_id": str(self.reference.output_content_id),
                "files": files,
            }
            manifest_content_id = scoped_content_id(semantic_manifest)
            manifest = {
                **semantic_manifest,
                "manifest_content_id": str(manifest_content_id),
            }
            manifest_path = staging / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            os.replace(staging, destination)
            verified = verify_bundle(destination)
            if verified != manifest_content_id:
                raise ReportVerificationError("published report bundle identity changed")
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        byte_count = sum(item.stat().st_size for item in destination.iterdir())
        return ReportBundleRef(str(destination), manifest_content_id, 2, byte_count)


_STANDARD_SECTIONS = (
    "performance_risk",
    "portfolio",
    "synthetic_execution_costs",
    "diagnostics",
    "provenance",
    "reproduction",
)


def _figure_sections(
    run: Any,
    metrics: Any,
    requested: tuple[str, ...] | None,
) -> list[tuple[str, str, str]]:
    selected = requested or _STANDARD_SECTIONS
    unknown = sorted(set(selected) - set(_STANDARD_SECTIONS))
    if unknown:
        raise ReportPlanningError(f"unknown report sections: {', '.join(unknown)}")
    factories: dict[str, tuple[str, Callable[[], tuple[Any, ...]]]] = {
        "performance_risk": (
            "Performance and risk",
            lambda: (
                performance.equity(run),
                performance.returns(run),
                performance.metric_summary(metrics),
            ),
        ),
        "portfolio": (
            "Portfolio",
            lambda: (
                portfolio.exposure(run),
                portfolio.positions(run),
                portfolio.target_shortfall(run),
            ),
        ),
        "synthetic_execution_costs": (
            "Synthetic execution and costs",
            lambda: (execution.fills(run), execution.costs(run)),
        ),
        "diagnostics": ("Diagnostics", lambda: (diagnostics.fidelity(run),)),
        "provenance": ("Provenance", lambda: (provenance.roots(run),)),
    }
    sections: list[tuple[str, str, str]] = []
    include_plotly = True
    for name in selected:
        if name == "reproduction":
            body = (
                "<p>Reopen the immutable run and verify the report manifest content IDs "
                "before reproducing the analysis.</p>"
            )
            sections.append((name, "Reproduction", body))
            continue
        title, factory = factories[name]
        bodies: list[str] = []
        for figure in factory():
            bodies.append(
                figure.to_html(
                    full_html=False,
                    include_plotlyjs=include_plotly,
                    config={
                        "displaylogo": False,
                        "responsive": True,
                        "scrollZoom": False,
                    },
                )
            )
            include_plotly = False
        sections.append((name, title, "".join(bodies)))
    return sections


def verify_bundle(path: str | Path) -> ContentId:
    """Verify safe relative paths and each checksum in a report bundle."""
    root = Path(path).resolve()
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReportVerificationError("report bundle manifest is unreadable") from error
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise ReportVerificationError("report bundle file closure is missing")
    typed_files = cast("list[dict[str, Any]]", files)
    seen: set[str] = set()
    for item in typed_files:
        relative = str(item.get("path", ""))
        candidate = Path(relative)
        folded = relative.casefold()
        if (
            not relative
            or candidate.is_absolute()
            or ".." in candidate.parts
            or folded in seen
        ):
            raise ReportSecurityError("report bundle contains an unsafe or colliding path")
        seen.add(folded)
        resolved = (root / candidate).resolve()
        if root not in resolved.parents or resolved.is_symlink():
            raise ReportSecurityError("report bundle file escapes its root")
        if _sha256(resolved) != item.get("sha256"):
            raise ReportVerificationError("report bundle file checksum does not verify")
    actual = {
        item.name
        for item in root.iterdir()
        if item.is_file() and not item.is_symlink()
    }
    if actual != {str(item["path"]) for item in typed_files} | {"manifest.json"}:
        raise ReportVerificationError("report bundle contains an unlisted or missing file")
    semantic = {key: value for key, value in manifest.items() if key != "manifest_content_id"}
    content_id = scoped_content_id(semantic)
    if str(content_id) != manifest.get("manifest_content_id"):
        raise ReportVerificationError("report bundle manifest identity does not verify")
    return content_id


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
