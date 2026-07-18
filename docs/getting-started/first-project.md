# First project: the flagship momentum workflow

`persistra.flagship.FLAGSHIP_MOMENTUM_V1` is a versioned profile for a small end-to-end
conformance flow. It binds the 12–1 momentum definition, ascending percentile-rank
signal, top-half equal-weight constructor, opening capital, and execution-cost policy.
This tutorial follows it from an initialized project to a rendered report.

## 1. Open a project

Every capability is reached through one thread-owned `Project` lifecycle with an
explicit mode. Mutating research artifacts requires `RESEARCH_WRITE`; market data
ingestion requires `MARKET_WRITE`; maintenance operations require `MAINTENANCE`.

```python
from persistra import Project, ProjectMode

layout = Project.init("/path/to/project", name="tutorial")

with Project.open(layout.root, mode=ProjectMode.RESEARCH_WRITE) as project:
    inspection = project.inspect()
```

## 2. Ingest data and build a research dataset

Register a market database and sources, ingest canonical daily bars and corporate
actions, create an immutable snapshot, and build a split-adjusted daily research
dataset at exact `(decision_at, instrument_id)` grain. The
[ingestion](../how-to/ingest-market-data.md) and
[research dataset](../how-to/build-research-datasets.md) guides cover each step.

## 3. Register the flagship definitions

```python
from persistra.flagship import FLAGSHIP_MOMENTUM_V1

# Inside a RESEARCH_WRITE project lifecycle, with a built research dataset:
features = project.services.research.features
features.register(FLAGSHIP_MOMENTUM_V1.momentum)
```

Materialize the momentum feature, register and materialize the rank signal, then
register the constructor and call `project.services.portfolio.construct(...)` to
produce target weights.

## 4. Simulate, analyze, and report

Plan and run a `VectorizedSimulationRequest` through
`project.services.simulation.vectorized`, then query the immutable result handle:

```python
from persistra.reports import ReportRequest

# run = project.services.simulation.vectorized.run(plan).result()
metrics = project.services.analysis.metrics.compute(run)
plan = project.services.reports.plan(ReportRequest(run.id, metrics.id))
report = project.services.reports.render(plan)
```

Vectorized runs intentionally record the `simulation.vectorized.no_orders` fidelity
finding; the event engine provides the order lifecycle. The
[simulation guide](../how-to/run-simulations.md) explains both engines and the
[analysis guide](../how-to/analyze-and-report.md) covers metrics, exports, and report
bundles.

## 5. Read results back

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
Bounded public queries raise rather than silently truncate. Figures reshape exact result
or analysis values and never become a second metric engine.
