# Analyze, report, and export

## Standard metrics

```python
# Inside a RESEARCH_WRITE project lifecycle:
run = project.services.results.get(run_id)
metrics = project.services.analysis.metrics.compute(run)
sharpe = metrics.scalar("persistra.metric.sharpe")
```

`compute` evaluates the `persistra.standard@1` catalog — see the
[metric catalog reference](../reference/metric-catalog.md) for every definition. Metric
results carry state, unit, observation count, and warning evidence. Supplying
misaligned optional inputs (risk-free returns, benchmark returns, eligible fill
volumes) raises `AnalysisInputError` at request time; absent inputs produce explicit
`missing_input` states instead. Identical requests return the existing immutable
artifact.

Compact attribution, execution, comparison, and scenario aggregation analyses live
beside metrics on `project.services.analysis`.

## Reports

Report planning and rendering require `RESEARCH_WRITE` because the completed report is
an immutable analysis artifact. Copying a completed report is an external publication
action and does not mutate the project.

```python
from persistra import Project, ProjectMode
from persistra.reports import ReportRequest, verify_bundle
from persistra.results import RunRecordId

run_id = RunRecordId.parse("run_record:00000000-0000-4000-8000-000000000001")

with Project.open("/path/to/project", mode=ProjectMode.RESEARCH_WRITE) as project:
    run = project.services.results.get(run_id)
    metrics = project.services.analysis.metrics.compute(run)
    plan = project.services.reports.plan(ReportRequest(run.id, metrics.id))
    report = project.services.reports.render(plan)
    bundle = report.copy_bundle_to("/new/report-directory")

assert verify_bundle(bundle.path) == bundle.manifest_content_id
```

The self-contained HTML embeds Plotly, styles, data, and a machine-readable manifest. A
directory bundle contains only safe relative files and a checksum-closed manifest.
Neither mode performs a network request.

## Portable exports

`project.services.results.exports.create(run, destination)` writes a dependency-closed
DuckDB file (or a Parquet/CSV bundle) whose tables and manifest are checksum-verified.
`persistra.results.open_export(path)` reopens it read-only, re-verifying every table
once per handle. Export writers stage to a `.partial` path and clean up on failure, so
an interrupted export can simply be retried. See the
[export format reference](../reference/export-formats.md).
