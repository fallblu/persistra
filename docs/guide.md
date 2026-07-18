# Public v3 workflow

Persistra uses one thread-owned `Project` lifecycle and explicit capability modes. The
top-level package exports only `Project`, `ProjectMode`, immutable project overrides, and
version metadata; domain capabilities live below `project.services` and their named
namespaces.

## Install capability groups

```bash
uv add "persistra[research,optimize,viz]"
```

Use `persistra[dashboard]` for the local dashboard or `persistra[all]` for every required
v3 extra. The empty `static` extra is reserved for a future reviewed browser renderer and
does not provide PNG, SVG, or PDF output.

## Read immutable results

```python
from persistra import Project, ProjectMode
from persistra.results import RunRecordId
from persistra.viz import performance, portfolio

run_id = RunRecordId.parse("run_record:00000000-0000-4000-8000-000000000001")

with Project.open("/path/to/project", mode=ProjectMode.READ_ONLY) as project:
    run = project.services.results.get(run_id)
    summary = run.summary()
    equity = run.equity(max_rows=100_000)
    equity_figure = performance.equity(run)
    exposure_figure = portfolio.exposure(run)
```

Result, analysis, export, figure, and report identities include immutable source roots.
Bounded public queries raise rather than silently truncate. Figures reshape exact result or
analysis values and never become a second metric engine.

## Execute a deterministic study

Study planning freezes the parameter, fold, scenario, environment, retry, and reuse inputs.
Grid, random, and user-defined searches expand at planning time. Bayesian search requires
`persistra[search]` and expands one deduplicated Optuna suggestion at a time, after the
previous trial's persisted objective observations are available.

Workers must be importable module-level callables because execution uses Python's `spawn`
process method. A worker receives a `RunAssignment` containing exact parameters, fold,
scenario, execution identity, attempt identity, and an isolated output path. It returns a
finite `WorkerOutcome`; the coordinator seals that outcome in the isolated DuckDB file,
reopens and verifies the closed file, persists the objective, and only then completes the
attempt.

```python
from decimal import Decimal

from persistra.domain import ContentId
from persistra.experiments import RunAssignment, WorkerOutcome


def evaluate(assignment: RunAssignment) -> WorkerOutcome:
    parameters = dict(assignment.parameters)
    objective = Decimal(parameters["turnover_penalty"])
    manifest = ContentId.from_bytes(
        f"{assignment.execution_content_id}:{objective}".encode()
    )
    return WorkerOutcome(manifest, objective)


# Inside a RESEARCH_WRITE project lifecycle:
summary = project.services.experiments.execute(
    study.reference.study_id,
    evaluate,
)
progress = study.progress()
```

`StudyExecutionPolicy` bounds local worker count and can stop after deterministic completed,
failed, or objective boundaries. `cancel()` persists cooperative cancellation intent.
Retries allocate a new attempt while retaining failed attempt evidence. Historical stress,
hypothetical, Monte Carlo, and moving/stationary bootstrap workers can materialize their
resolved numeric input path with `apply_scenario`; randomized methods use the scenario's
derived seed.

## Build and relocate an offline report

Report planning and rendering require `RESEARCH_WRITE` because the completed report is an
immutable analysis artifact. Copying a completed report is an external publication action
and does not mutate the project.

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
directory bundle contains only safe relative files and a checksum-closed manifest. Neither
mode performs a network request.

## Launch the read-only dashboard

```bash
persistra dashboard --project /path/to/project
persistra dashboard --export /path/to/run-export.duckdb
```

The dashboard defaults to `127.0.0.1:8501`, keeps XSRF/CORS protections enabled, disables
telemetry and static serving, offers no upload or arbitrary SQL surface, and opens a new
short-lived read-only scope for each page query. It caches detached data only under keys
that include the source fingerprint, result root, page parameters, limits, and renderer
version.

The eight pages cover run overview, performance, portfolio, execution, attribution,
diagnostics, studies, and provenance inspection. A missing immutable analysis is shown as
unavailable; dashboard code never computes or persists it.
