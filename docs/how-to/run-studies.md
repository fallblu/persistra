# Run studies and scenarios

Study planning freezes the parameter, fold, scenario, environment, retry, and reuse
inputs. Grid, random, and user-defined searches expand at planning time. Bayesian
search expands one deduplicated Optuna suggestion at a time, after the previous trial's
persisted objective observations are available.

## Workers

Workers must be importable module-level callables because execution uses Python's
`spawn` process method. A worker receives a `RunAssignment` containing exact
parameters, fold, scenario, execution identity, attempt identity, and an isolated
output path. It returns a finite `WorkerOutcome`; the coordinator seals that outcome in
the isolated DuckDB file, reopens and verifies the closed file, persists the objective,
and only then completes the attempt.

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

`StudyExecutionPolicy` bounds local worker count and can stop after deterministic
completed, failed, or objective boundaries. One spawned worker pool is reused across
scheduling batches; results are consumed in schedule order, so identities and outputs
are stable across worker counts and completion order. `cancel()` persists cooperative
cancellation intent. Retries allocate a new attempt against the same run plan — the
plan's schedule ordinal never changes — while retaining failed attempt evidence.

## Scenarios

Historical stress, hypothetical, Monte Carlo, and moving/stationary bootstrap workers
can materialize their resolved numeric input path with `apply_scenario`; randomized
methods use the scenario's derived seed. Scenario transformations are assumptions, not
forecasts: the coordinator never silently mutates canonical market data, and a worker
must deliberately use the resolved scenario input.

## Reuse

Exact reuse is the default: a run plan whose execution identity matches a completed
attempt reuses it. Typed compatibility reuse (same semantics, different
dependency-irrelevant facts) is explicit and warned, and comparison analyses classify
compatibility before combined claims.
