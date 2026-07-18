# Design reference: experiments and results

This page describes the implemented behavior of the experiment, result, analysis, and
export subsystems.

## Experiments

A study freezes its parameter, fold, scenario, environment, retry, and reuse inputs at
planning time and carries a design identity that excludes allocated IDs and wall-clock
time. Grid, random, and user-defined searches expand at planning time; Bayesian search
uses seeded Optuna TPE ask/tell, expanding one deduplicated suggestion at a time after the
previous trial's persisted objective is available, and deterministically substituting a
declared grid point when a discrete duplicate is drawn.

Execution spawns local workers via Python's `spawn` method against one reused process
pool. A worker receives a `RunAssignment` with an isolated output path and returns a finite
`WorkerOutcome`; the coordinator seals the outcome in an isolated DuckDB file, reopens and
verifies the closed file, persists the objective, and only then completes the attempt.
Results are consumed in schedule order, so identities and outputs are stable across worker
counts and completion order. Retries allocate a new attempt against the same run plan
without changing its schedule ordinal, retaining failed-attempt evidence; `cancel()`
persists cooperative cancellation intent. Remote workers and general workflow scheduling
are out of scope.

## Results

Verified worker publication produces immutable completed-run records with fixed normalized
result tables (equity, returns, positions, cash, exposures, rebalances, trade intents,
targets, orders, order transitions, fills, costs, events, journal, settlements, lots, lot
events, borrow, cash flows, quality, logs). Both engines publish this common schema.
Queries go through bounded ordered handles that raise rather than truncate. Annotations,
retention, and reference-aware deletion operate around the immutable core; a completed run
stays byte- and logically-unchanged while analyses accrue.

## Analysis and export

Analyses are immutable artifacts bound to their run and inputs. The
`persistra.standard@1` metric catalog is the implemented single-run set (see the
[metric catalog](../../reference/metric-catalog.md)); compact attribution, execution,
comparison, and scenario aggregation analyses sit beside it. Advanced Brinson/factor
attribution, full statistical inference, and the complete focused-spec analysis catalog
are not implemented. Comparisons classify compatibility before combined claims.

Portable exports are dependency-closed DuckDB files or Parquet/CSV bundles whose tables
and manifest are checksum-verified on write and re-verified on open (see the
[export formats reference](../../reference/export-formats.md)). Only the current export
format is promised; earlier pre-release exports are disposable.
