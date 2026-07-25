# Persistra 3.1.0 roadmap

## Purpose

This roadmap defines the work for Persistra 3.1.0. The theme is correctness and honesty.

The 3.0.2 review found fifteen problems. One release cannot close all of them safely.
This roadmap closes the problems that make the shipped public contract wrong. The
remaining problems move to `ROADMAP-3.2.0.md` and `ROADMAP-3.3.0.md`.

The review examined commit `d64fb30`. This roadmap starts from `develop` at commit
`f065310`.

## What changed in this revision

The first draft of this roadmap put all fifteen findings in one release. That plan had
570 checklist items and fifteen implementation branches. It rewrote both simulation
engines and then rewrote their ledgers again in a later branch. This revision makes the
following changes.

- Split the work across three releases.
- Add a capability deferral rule, so that one blocked branch cannot block the release.
- Restore the deleted benchmark harness instead of writing a new one.
- Restore the deleted documentation set instead of writing a new one.
- Move optional dependency work to the first wave, because the hard part is already done.
- Add the missing 3.0.2 comparison fixtures as a prerequisite branch.
- Add the missing benchmark harness as a prerequisite branch.
- Add the SQL function allowlist defect, which the first draft did not record.
- Land the multi-currency schema early and additively, then change behavior in 3.3.0.
- Remove the vintage acquisition prerequisite from multi-currency accounting.
- Add priority, size, and confidence to the traceability table.
- Add an evidence location, a risk register, and a deferral register.

## Prior art

Two branches in the first draft specified artifacts that exist in Git history. A
developer must restore those artifacts before new work starts.

### Benchmark harness

Commit `514c276` removed a complete release benchmark harness on 2026-07-18. The harness
had a deterministic fixture generator, a JSON manifest, and an independent validator. It
also had an 8 GiB peak resident set gate, a runbook, and a CI job. The directory
`benchmarks/` still holds the orphaned `__pycache__` directory.

Restore the harness with these commands:

```bash
git show 514c276^:benchmarks/__init__.py > benchmarks/__init__.py
git show 514c276^:benchmarks/validator.py > benchmarks/validator.py
git show 514c276^:benchmarks/RUNBOOK.md > benchmarks/RUNBOOK.md
git show 514c276^:benchmarks/daily_equity_1000x10.py > benchmarks/daily_equity_1000x10.py
mkdir -p benchmarks/manifests
git show 514c276^:benchmarks/manifests/daily_equity_1000x10-v1.json \
  > benchmarks/manifests/daily_equity_1000x10-v1.json
git show 514c276^:Makefile | grep -A 3 benchmark
git show 514c276^:.github/workflows/ci.yml | grep -B 3 -A 8 benchmark
```

### Documentation set

Commit `96c911a` removed 1,134 lines of documentation on 2026-07-20. The removed files
were a getting-started guide, six how-to guides, and nine explanation pages. The
`docs/3.1-public-workflow` branch specifies almost the same page set.

List the removed files with this command:

```bash
git show --stat 96c911a
```

The changelog records the removal as a decision. It states that guides and explanation
pages are not in the repository. This roadmap reverses that decision.

The `docs/3.1-public-workflow` branch must record the reason for the reversal in
`CONTRIBUTING.md`. Without a recorded reason, a later cleanup will remove the pages
again.

## Release principles

- [ ] Make each stable public capability executable for supported input.
- [ ] Reject each unavailable capability during request construction.
- [ ] Preserve current public enum members and SQL relation types in 3.1.0.
- [ ] Use capability status and typed errors instead of breaking removals.
- [ ] Enforce each accepted resource limit.
- [ ] Measure limits that make performance or memory claims.
- [ ] Preserve point-in-time rules across each new workflow.
- [ ] Preserve deterministic identities and balanced accounting.
- [ ] Reject non-deterministic input to any identity-bearing operation.
- [ ] Use public APIs in all user workflow documentation.
- [ ] Keep release actions under human control.

## Capability deferral rule

The first draft stated that a branch cannot remove its assigned release requirement. That
rule and the capability registry contradict each other. The registry exists to report an
honest status for work that is not complete.

A finding is closed by one of two outcomes:

1. The capability is implemented, tested, and registered as `stable`.
2. The capability is registered as `planned` or `unavailable`.

Outcome 2 has these conditions:

- [ ] Request construction raises a precise typed capability error.
- [ ] The registry records the reason and the target release.
- [ ] The published capability matrix shows the status.
- [ ] A human approves the deferral and records it in the deferral register.

A deferral is not a waiver. The deferral register in this document lists each deferred
item and its target release.

## Branch rules

Create each implementation branch from the latest `develop` after its prerequisite
branches merge.

Before implementation, complete a branch-specific interview. Confirm scope, API shape,
edge cases, compatibility, and tests. Record each design decision in a short architecture
decision record under `docs/explanation/`.

Each branch must meet these conditions:

- [ ] Keep each commit coherent and green.
- [ ] Use subject-only Conventional Commit messages.
- [ ] Add user-facing changes to the 3.1.0 section of `CHANGELOG.md`.
- [ ] Add migrations for each persistent schema change.
- [ ] Test migration from the 3.0.2 baseline project when a schema changes.
- [ ] Update API documentation and docstrings with the implementation.
- [ ] Follow ASD-STE100 Simplified Technical English in documentation.
- [ ] Add no new `reportPrivateUsage` suppression.
- [ ] Run the complete verification gate before merge.
- [ ] Rebase onto `develop` and rerun the gate before merge.
- [ ] Use a pull request with Summary and Test plan sections.
- [ ] Use rebase-and-merge into `develop`.

Dependency and packaging branches must also test the affected dependency bands and
installation profiles.

## Verification gate

Use this verification gate:

```bash
make lint type test docs-check
make docs-build
make schema-check
make private-usage-check
make markers-check
uv lock --check
uv build
make package-smoke
```

Branches that change a measured path must also run this command:

```bash
make benchmark-smoke
```

The first draft gate omitted the package build and the benchmark step. CI already builds
the wheel and installs it. The local gate must agree with CI.

## Branch sequence

| Wave | Branch | Prerequisites |
| --- | --- | --- |
| 1 | `test/3.1-compat-baseline` | None |
| 1 | `test/3.1-bench-harness` | None |
| 1 | `chore/3.1-verification-gates` | None |
| 1 | `refactor/3.1-optional-dependencies` | None |
| 1 | `feat/3.1-capability-registry` | None |
| 1 | `feat/3.1-project-bootstrap` | None |
| 2 | `fix/3.1-sql-contracts` | `test/3.1-bench-harness` |
| 2 | `feat/3.1-currency-schema` | `test/3.1-compat-baseline` |
| 2 | `fix/3.1-provider-conformance` | `feat/3.1-capability-registry` |
| 3 | `refactor/3.1-bounded-readers` | `fix/3.1-sql-contracts`, both wave 1 test branches |
| 3 | `test/3.1-release-assurance` | `test/3.1-bench-harness`, `feat/3.1-project-bootstrap` |
| 4 | `docs/3.1-public-workflow` | All implementation branches |
| 5 | `release/3.1.0` | All prior branches |

Branches in the same wave can proceed together when they do not change the same files.
Recheck the branch base before work starts.

## Wave 1: Foundations

### `test/3.1-compat-baseline`

This branch creates the 3.0.2 comparison fixtures. Four later branches claim to compare
results against that release. No such fixture exists today.

#### Design decisions

- [ ] Choose between a committed database file and a deterministic generator script.
- [ ] Define the identity manifest format and its schema version.
- [ ] Define the refresh policy when a later schema version changes stored identities.
- [ ] Define the size budget for committed fixture data.

#### Implementation

- [ ] Add a 3.0.2 project fixture at schema version 24.
- [ ] Record the exact 3.0.2 commit and package version with the fixture.
- [ ] Generate a canonical identity manifest for dataset builds.
- [ ] Generate a canonical identity manifest for feature and label materializations.
- [ ] Generate a canonical identity manifest for vectorized simulation results.
- [ ] Generate a canonical identity manifest for event simulation results.
- [ ] Add a helper that opens the baseline project in a temporary copy.
- [ ] Add a helper that compares current identities against the manifest.
- [ ] Document the refresh procedure in the fixture runbook.

#### Tests

- [ ] Test that the baseline project opens and migrates to the schema head.
- [ ] Test that migration preserves each recorded identity.
- [ ] Test that the comparison helper detects a changed identity.
- [ ] Test that the fixture copy never mutates the committed file.

#### Exit criteria

- [ ] A branch can compare current output against 3.0.2 with one helper call.
- [ ] Migration from 3.0.2 has a test that runs in CI.

### `test/3.1-bench-harness`

This branch restores and extends the deleted benchmark harness. Later branches make
performance claims. Those claims need one shared measurement contract.

#### Design decisions

- [ ] Define hardware normalization for a laptop-scale run.
- [ ] Define the budget file format and its review procedure.
- [ ] Decide which measurements gate CI and which measurements only get recorded.
- [ ] Define the tolerance band for an accepted measurement.

#### Implementation

- [ ] Restore the harness from commit `514c276^`.
- [ ] Restore the `benchmark-smoke` target in the `Makefile`.
- [ ] Restore the benchmark job in the CI workflow.
- [ ] Remove the orphaned `benchmarks/__pycache__` directory.
- [ ] Add a database query counter to the measured boundary.
- [ ] Add a peak resident set measurement for each reader family.
- [ ] Add a machine-readable budget file with runtime, query count, and memory fields.
- [ ] Record each measurement as a JSON artifact.
- [ ] Fail CI when a measurement exceeds its approved budget.
- [ ] Document the measurement protocol in the restored runbook.

#### Tests

- [ ] Test the fixture generator for determinism.
- [ ] Test the independent validator against a corrupted fixture.
- [ ] Test that the query counter records a known query count.
- [ ] Test that a budget breach fails the gate.
- [ ] Test that the artifact format is deterministic.

#### Exit criteria

- [ ] One harness measures runtime, query count, and peak memory.
- [ ] Each budget lives in one reviewed file.
- [ ] CI fails on an unapproved regression.

### `chore/3.1-verification-gates`

This branch makes the verification gate measure what the project claims. The current
coverage floor is below the current coverage.

#### Design decisions

- [ ] Choose the branch coverage floor from the current measurement.
- [ ] Define the private-usage ratchet format.
- [ ] Define which test directories imply which markers.

#### Implementation

- [ ] Raise the line coverage floor to 90 percent.
- [ ] Add a branch coverage floor at the current measured value.
- [ ] Add a `private-usage-check` target that counts `reportPrivateUsage` suppressions.
- [ ] Record the current count of 326 suppressions as the ceiling.
- [ ] Fail the check when the count increases.
- [ ] Add a `markers-check` target that verifies marker application.
- [ ] Apply the `integration` marker to each test under `tests/integration`.
- [ ] Apply the `contract` marker to each test under `tests/contracts`.
- [ ] Add a `package-smoke` target that matches the CI package job.
- [ ] Rename the `Unreleased` changelog section to `3.1.0`.
- [ ] Add the evidence document skeleton at `docs/releases/3.1.0-evidence.md`.

#### Tests

- [ ] Test that the private-usage check fails on an added suppression.
- [ ] Test that the marker check fails on an unmarked integration test.
- [ ] Test that the coverage floors match the recorded values.

#### Exit criteria

- [ ] No configured marker has zero meaningful uses.
- [ ] The coverage floor is at or above the current measurement.
- [ ] Private-usage suppressions cannot increase without review.

### `refactor/3.1-optional-dependencies`

This branch reduces the required installation. The first draft placed this work last. The
hard part is already complete, so the work belongs first.

Every heavy dependency already uses a lazy import at a capability boundary. The modules
`cvxpy`, `sqlglot`, `streamlit`, `plotly`, `optuna`, and `duckdb` load through
`import_module`. Four declared dependencies have zero references in `src/persistra`.

#### Design decisions

- [ ] Define the minimum supported core.
- [ ] Map public capabilities to installation profiles.
- [ ] Define imports that remain safe in a core installation.
- [ ] Decide whether `duckdb` belongs in the core or in a profile.

#### Implementation

- [ ] Remove the unused `scipy` dependency.
- [ ] Remove the unused `scikit-learn` dependency.
- [ ] Remove the unused `jinja2` dependency.
- [ ] Remove the unused `pytz` dependency.
- [ ] Define a core installation for project, storage, schemas, identity, and market data.
- [ ] Add a `research` extra for the SQL and component stack.
- [ ] Add an `optimization` extra for the convex solver stack.
- [ ] Add a `search` extra for the study stack.
- [ ] Add a `viz` extra for the figure stack.
- [ ] Add a `dashboard` extra for the browser application stack.
- [ ] Add an `all` extra.
- [ ] Preserve the `dev` and `docs` tool groups.
- [ ] Add a typed optional-dependency error.
- [ ] Name the necessary extra in each optional-dependency error.
- [ ] Connect installation requirements to capability records.
- [ ] Correct the false dependency claim from the 3.0.0 changelog in the 3.1.0 section.
- [ ] Update the lockfile after the final dependency map.

#### Tests

- [ ] Build and install the core wheel without optional stacks.
- [ ] Smoke-test each extra independently.
- [ ] Smoke-test the `all` extra.
- [ ] Test public imports in each supported profile.
- [ ] Test typed errors for absent extras.
- [ ] Test the lowest-direct dependency band.
- [ ] Test the highest dependency band.
- [ ] Test Python 3.12, 3.13, and 3.14.
- [ ] Inspect wheel and source distribution contents.

#### Exit criteria

- [ ] Core installation excludes each optional capability stack.
- [ ] Every supported extra passes an independent smoke test.
- [ ] Missing extras fail with precise typed guidance.
- [ ] No declared runtime dependency lacks a source reference.

### `feat/3.1-capability-registry`

This branch creates one source of truth for public capability status. Other branches
change status only after their capability tests pass.

Two divergent allowlists exist today. The set `_EXECUTABLE_MANAGED_OPERATORS` lives in
`research/component_services.py`. The set `_EXECUTABLE_ALPHA_METRICS` lives in
`research/alpha.py`. Both already reject at construction time. The registry removes the
duplication and generates the published matrix.

Only one public choice fails late. A `FeatureSqlRelation` binding fails inside
`SqlReadService._resolve_dependency`. The registry must move that failure to request
construction.

#### Design decisions

- [ ] Define the exact meaning of `stable`, `experimental`, `planned`, and `unavailable`.
- [ ] Define compatibility rules for serialized requests that contain unavailable values.
- [ ] Define the public query API and the internal registration API.
- [ ] Define how optional installation requirements appear in capability records.
- [ ] Define the exception hierarchy for the new typed capability error.

#### Implementation

- [ ] Add immutable capability identifiers and status records.
- [ ] Record status, reason, version, requirements, and optional installation profile.
- [ ] Record the target release for each deferred capability.
- [ ] Register each `FeatureSqlRelation` variant.
- [ ] Register each `ManagedOperator` value.
- [ ] Register each `AlphaMetricKind` value.
- [ ] Register each validation mode.
- [ ] Register first-party provider families and vintage support.
- [ ] Register simulation modes and strategy support.
- [ ] Replace both duplicated executable allowlists with registry queries.
- [ ] Validate unavailable choices when callers construct requests.
- [ ] Move the `FeatureSqlRelation` rejection to `SqlReadContext` construction.
- [ ] Raise one precise typed capability error.
- [ ] Derive the new error from the current error type for each affected path.
- [ ] Preserve all current enum members and SQL relation union members.
- [ ] Expose a read-only public capability query.
- [ ] Generate machine-readable capability data for documentation.
- [ ] Prevent a capability from becoming stable without executable evidence.

#### Tests

- [ ] Test each status and each status transition rule.
- [ ] Test precise construction-time errors for unavailable choices.
- [ ] Test that each new error is catchable as its 3.0.2 error type.
- [ ] Test stable capability execution with representative input.
- [ ] Test synchronization between enums, unions, services, and registry records.
- [ ] Test deterministic serialization of capability data.
- [ ] Test old serialized requests with preserved public values.

#### Exit criteria

- [ ] One registry controls validation and documentation status.
- [ ] No stable registry entry lacks an executable test.
- [ ] No unavailable value reaches a late service failure.
- [ ] No caller that catches a 3.0.2 error type stops working.

### `feat/3.1-project-bootstrap`

This branch makes project initialization create a complete database topology atomically.

A market database can be created today through a maintenance project. The created
database is never written to `persistra.toml`. The method `_register_created_database`
registers the database in memory only. No public API adds a database to project
configuration.

#### Design decisions

- [ ] Define research and market database specification models.
- [ ] Choose idempotent or conflict behavior for repeated initialization.
- [ ] Define path ownership and rollback rules.
- [ ] Define behavior for existing compatible database files.
- [ ] Define the configuration write procedure and its durability rules.

#### Implementation

- [ ] Add validated research database specifications to `Project.init`.
- [ ] Add validated market database specifications to `Project.init`.
- [ ] Support logical name, path, schema target, read-only policy, and creation policy.
- [ ] Validate every name and path before file creation.
- [ ] Detect specification conflicts before file creation.
- [ ] Create configuration and database files as one coordinated operation.
- [ ] Remove newly created files after an initialization failure.
- [ ] Do not remove files that existed before initialization.
- [ ] Return structured created, reused, and skipped resource data.
- [ ] Add public `Project.add_database` support.
- [ ] Write each added database to project configuration durably.
- [ ] Apply the same validation rules during later database addition.
- [ ] Keep project configuration valid after each failure.
- [ ] Add a `--market` option to the `project init` command.
- [ ] Add a `project add-database` command.
- [ ] Update the CLI reference documentation.

#### Tests

- [ ] Test complete research and market initialization.
- [ ] Test repeated initialization behavior.
- [ ] Test mixed created and reused resources.
- [ ] Test validation before filesystem changes.
- [ ] Inject failure after each creation phase.
- [ ] Test rollback without loss of existing files.
- [ ] Test read-only and creation policies.
- [ ] Test concurrent initialization conflicts.
- [ ] Test that an added database survives a project reopen.
- [ ] Test each new CLI command.

#### Exit criteria

- [ ] One public call can create a complete project.
- [ ] A failed call leaves no partial new project.
- [ ] Post-initialization expansion uses a supported public API.
- [ ] The CLI can create every database topology that the API can create.

## Wave 2: Public contract correctness

### `fix/3.1-sql-contracts`

This branch corrects SQL preview behavior. It enforces every accepted SQL read limit. It
also closes the function allowlist defect.

#### Preview and limit defects

The method `SqlReadService.preview` sets `truncated` to `True` on every call. No test
covers `preview` or `truncated`. The fields `timeout`, `chunk_rows`, and `max_findings`
are validated at construction and then never read. The method `_execute` requests
`max_rows + 1` rows and materializes the frame in one call.

#### Function allowlist defect

The function `_validate_functions` checks the allowlist only when a node is an instance
of `exp.Anonymous`. Every function that sqlglot models as a typed node skips the
allowlist. The effective control is a fourteen-entry substring denylist.

This behavior was confirmed against sqlglot 30 and DuckDB 1.5.4. The functions `SUM`,
`POWER`, `ROW_NUMBER`, `CURRENT_DATE`, `MD5`, `DECODE`, `EXPLODE`, and `REGEXP_REPLACE`
all pass the check.

The defect is not only a hardening problem. The function `_classify` has no
non-determinism rule. A query that selects `current_date` classifies as `ROW_LOCAL` and
`CAUSAL`. The result is `SafetyStatus.SAFE` with `structurally_decision_eligible` set to
`True`. The content identity covers the SQL text and not the produced value.

A workspace materialization can therefore embed wall-clock time and keep a safe
classification. That breaks two release principles.

#### Design decisions

- [ ] Select the DuckDB cancellation mechanism.
- [ ] Define timeout behavior during connection cleanup and transactions.
- [ ] Define result metadata for applied limits and termination reasons.
- [ ] Define unsupported limit combinations.
- [ ] Define the deterministic function classification and its published list.
- [ ] Decide whether a non-deterministic function is rejected or classified as unsafe.

DuckDB 1.5.4 exposes `connection.interrupt` and `connection.query_progress`. The method
`interrupt` acts on the whole connection. This project shares one connection across
services. The design must therefore use a dedicated cursor or connection for each bounded
read.

#### Implementation

- [ ] Give `SqlService.preview` a dedicated execution path.
- [ ] Request `max_rows + 1` rows for previews.
- [ ] Return no more than `max_rows` preview rows.
- [ ] Set `truncated` only when the extra row exists.
- [ ] Report returned rows, applied limit, truncation, and termination reason.
- [ ] Keep strict size rejection in the full read API.
- [ ] Apply SQL limits before Pandas frame creation.
- [ ] Make `chunk_rows` control DuckDB fetch size.
- [ ] Enforce `timeout` through cancellation or interruption.
- [ ] Stop finding generation at `max_findings`.
- [ ] Report finding truncation.
- [ ] Reject unsupported limit combinations during request construction.
- [ ] Release cursors and transactions when a reader stops early.
- [ ] Apply the function allowlist to every `exp.Func` node.
- [ ] Keep the substring denylist as a second control.
- [ ] Reject each non-deterministic function in an identity-bearing read.
- [ ] Add a sqlglot version conformance test for the allowlist.
- [ ] Publish the allowlist in the reference documentation.

#### Tests

- [ ] Test previews with zero rows.
- [ ] Test previews below the limit.
- [ ] Test previews at the exact limit.
- [ ] Test previews one row above the limit.
- [ ] Test previews far above the limit.
- [ ] Test strict read rejection above `max_rows`.
- [ ] Test actual fetch batches against `chunk_rows`.
- [ ] Test finding truncation at `max_findings`.
- [ ] Test timeout interruption and cleanup.
- [ ] Test early iterator close.
- [ ] Test all result metadata.
- [ ] Test allowlist rejection for each typed function class.
- [ ] Test rejection of `current_date`, `now`, and `random`.
- [ ] Test that the allowlist test fails when sqlglot reclassifies a function.
- [ ] Add a property test that generates function calls against the allowlist.

#### Exit criteria

- [ ] SQL preview metadata agrees with returned data.
- [ ] No accepted SQL safety limit is ignored.
- [ ] SQL peak materialization follows the configured batch size.
- [ ] No non-deterministic query receives a safe classification.
- [ ] The allowlist does not depend on the sqlglot node taxonomy.

### `feat/3.1-currency-schema`

This branch lands the multi-currency data model early and additively. It changes no
behavior. The behavioral work happens in 3.3.0.

The first draft placed the whole multi-currency effort after both simulation engine
rewrites. That plan rewrote each engine twice. This branch fixes the stored shape first,
so that the 3.3.0 engine work targets the final model one time.

The names `cash_usd` and `signed_cash_usd` are physical column names in `migrations.py`.
This branch keeps those columns and populates them. Their removal moves to 4.0.0.

#### Design decisions

- [ ] Define native and reporting amount models.
- [ ] Define the FX rate identity and its provenance fields.
- [ ] Define the migration rule that back-fills USD rows.
- [ ] Define how added columns affect stored content identities.
- [ ] Define the deprecation policy for the USD-specific columns.

#### Implementation

- [ ] Add native currency and native amount columns to each cash relation.
- [ ] Add native amount columns to trade, fee, settlement, and dividend relations.
- [ ] Add FX rate identity, timestamp, and conversion path columns.
- [ ] Add a reporting currency field to portfolio configuration.
- [ ] Add a reporting currency field to simulation configuration.
- [ ] Default each reporting currency to USD.
- [ ] Keep `cash_usd` and `signed_cash_usd` populated for compatibility.
- [ ] Mark the USD-specific columns as deprecated in the schema documentation.
- [ ] Add the migration that back-fills each native column with USD values.
- [ ] Preserve every 3.0.2 content identity through the migration.
- [ ] Add no behavior that reads the new columns.

#### Tests

- [ ] Test migration from the 3.0.2 baseline project.
- [ ] Test that every recorded 3.0.2 identity is preserved.
- [ ] Test that back-filled native amounts equal the USD amounts.
- [ ] Test that a reporting currency other than USD is rejected for now.
- [ ] Test that the schema check accepts the new topology.

#### Exit criteria

- [ ] The stored model can hold native and reporting amounts.
- [ ] No 3.0.2 identity changes.
- [ ] No behavior depends on the new columns yet.

### `fix/3.1-provider-conformance`

This branch makes a passing provider report prove real managed interoperability.

The property `ConformanceReport.passed` returns true when no case failed. A report with
every case skipped therefore passes. The check `_idempotency` compares
`adapter.sample_records` with itself. The adapter protocol never receives a managed
connection, so no case exercises managed state.

#### Design decisions

- [ ] Define minimum evidence for a passing report.
- [ ] Define the difference between skipped and not-applicable checks.
- [ ] Select safe authenticated probe behavior.
- [ ] Define fixture versions and provider version reporting.

#### Implementation

- [ ] Add passed, failed, skipped, and not-applicable outcomes.
- [ ] Require one successful declared capability for a passing report.
- [ ] Mark zero-capability adapters as incomplete.
- [ ] Bind provider checks to canonical family fixtures.
- [ ] Run real normalization and validation operations.
- [ ] Run real managed ingestion and bounded query operations.
- [ ] Ingest the same canonical payload twice for idempotency.
- [ ] Compare managed identities and state after repeated ingestion.
- [ ] Verify snapshot creation from managed provider data.
- [ ] Validate credential schemas without exposing values.
- [ ] Separate credential schema checks from authenticated probes.
- [ ] Record provider version and declared capabilities.
- [ ] Record fixture identities and managed output identities.
- [ ] Record evidence for each conformance outcome.
- [ ] Run the suite against the Alpha Vantage adapter.

#### Tests

- [ ] Test duplicate delivery.
- [ ] Test corrected delivery.
- [ ] Test out-of-order delivery.
- [ ] Test pagination.
- [ ] Test rate-limit behavior.
- [ ] Test retry behavior.
- [ ] Test partial failure and recovery.
- [ ] Test a zero-capability adapter.
- [ ] Test a report with all checks skipped.
- [ ] Test safe credential redaction.

#### Exit criteria

- [ ] A provider cannot pass without a successful managed operation.
- [ ] Idempotency checks compare managed state.
- [ ] Reports contain enough evidence for independent review.

## Wave 3: Bounded execution and assurance

### `refactor/3.1-bounded-readers`

This branch makes non-SQL row iterators use bounded database batches. The SQL branch owns
the SQL reader implementation.

Six iterator methods materialize a complete frame and then slice it. The methods are
`SqlReadResult.iter_rows`, `FeatureRows.iter_rows`, `ComponentRows.iter_rows`,
`DatasetRows.iter_rows`, `TradeService.iter_chunks`, and `QuoteService.iter_chunks`. The
two market methods also return `Any`.

#### Design decisions

- [ ] Select the shared cursor or Arrow batch abstraction.
- [ ] Define iterator lifetime and transaction ownership.
- [ ] Define cancellation and deadline propagation.
- [ ] Define stable keyset order for each persisted relation.
- [ ] Set peak-memory budgets for each reader family.

#### Implementation

- [ ] Stream trade batches from DuckDB.
- [ ] Stream quote batches from DuckDB.
- [ ] Stream dataset row batches from DuckDB.
- [ ] Stream feature row batches from DuckDB.
- [ ] Stream component row batches from DuckDB.
- [ ] Stream workspace relation batches from DuckDB.
- [ ] Replace each `Any` return type with a precise iterator type.
- [ ] Push `LIMIT max_rows + 1` into bounded queries.
- [ ] Use keyset pagination for stable persisted relations.
- [ ] Avoid offset pagination for large persisted relations.
- [ ] Do not slice a fully materialized frame in iterator methods.
- [ ] Do not concatenate all batches before returning an iterator.
- [ ] Propagate cancellation to every batch read.
- [ ] Propagate deadlines to every batch read.
- [ ] Close cursors when consumers stop early.
- [ ] Compute required content hashes incrementally.
- [ ] Document order, lifetime, transaction, and early-stop behavior.

#### Tests

- [ ] Measure trade reader peak memory as total rows increase.
- [ ] Measure quote reader peak memory as total rows increase.
- [ ] Measure dataset reader peak memory as total rows increase.
- [ ] Measure feature reader peak memory as total rows increase.
- [ ] Measure component reader peak memory as total rows increase.
- [ ] Measure workspace reader peak memory as total rows increase.
- [ ] Measure SQL reader peak memory as total rows increase.
- [ ] Test stable ordering across batch boundaries.
- [ ] Test hard bounds at zero, exact limit, and one row above.
- [ ] Test cancellation and deadlines between batches.
- [ ] Test early close without a leaked transaction.
- [ ] Test incremental identity against the 3.0.2 baseline identity.

#### Exit criteria

- [ ] Peak reader memory does not grow with total relation size.
- [ ] Every row bound applies before full materialization.
- [ ] Early consumer termination releases all database resources.
- [ ] No public iterator returns `Any`.

### `test/3.1-release-assurance`

This branch closes cross-system failure, concurrency, and browser test gaps. Feature
branches still own their direct tests. Simulation benchmarks move to 3.3.0.

Seven markers are configured under `--strict-markers`. The markers `integration`,
`scenario`, and `fault` have zero uses. The markers `browser`, `multiprocess`, and
`property` have one use each.

#### Design decisions

- [ ] Define critical module coverage expectations.
- [ ] Define browser support and test scope.
- [ ] Define the failure-injection mechanism for process-level tests.

#### Failure and concurrency tests

- [ ] Add process-crash tests for ingestion.
- [ ] Add process-crash tests for migrations.
- [ ] Add process-crash tests for simulation persistence.
- [ ] Add process-crash tests for maintenance leases.
- [ ] Add concurrent writer scenarios.
- [ ] Add stale lease recovery scenarios.
- [ ] Add lock recovery scenarios.
- [ ] Add interrupted copy scenarios.
- [ ] Use the `fault` marker.
- [ ] Expand meaningful `multiprocess` coverage.

#### Scenario and property tests

- [ ] Add an ingestion-to-results end-to-end scenario.
- [ ] Include snapshots and research construction.
- [ ] Include vectorized and event simulation.
- [ ] Include exports and provenance verification.
- [ ] Use the `scenario` marker.
- [ ] Add temporal cutoff properties.
- [ ] Add content identity properties.
- [ ] Add accounting balance properties.
- [ ] Add ingestion idempotency properties.

#### Browser tests

- [ ] Test dashboard navigation in a browser.
- [ ] Test dashboard state and representative charts.
- [ ] Test dashboard error display and recovery.
- [ ] Use the `browser` marker.

#### Coverage

- [ ] Set expectations for dashboard services.
- [ ] Set expectations for feature and component services.
- [ ] Set expectations for report and SQL services.
- [ ] Set expectations for portfolio and reference services.
- [ ] Keep the global line coverage floor at or above 90 percent.

#### Exit criteria

- [ ] Each configured risk marker has meaningful tests.
- [ ] Transaction recovery has process-level evidence.
- [ ] Critical service coverage meets recorded expectations.

## Wave 4: Documentation

### `docs/3.1-public-workflow`

This branch restores the deleted documentation set and adds a tested public workflow.

Start from commit `96c911a^`. Restore each page, then correct it against the current API.
Do not write these pages from an empty file.

#### Implementation

- [ ] Restore the getting-started pages from `96c911a^`.
- [ ] Restore the how-to guides from `96c911a^`.
- [ ] Restore the explanation pages from `96c911a^`.
- [ ] Restore the dashboard architecture decision record.
- [ ] Correct every restored page against the current public API.
- [ ] Record the reason for the documentation reversal in `CONTRIBUTING.md`.
- [ ] Add a quickstart that uses only public APIs.
- [ ] Initialize research and market databases with one public call.
- [ ] Ingest a small offline fixture.
- [ ] Create a point-in-time snapshot.
- [ ] Create a research dataset.
- [ ] Materialize a feature and label.
- [ ] Assemble a supported validation plan.
- [ ] Run research construction.
- [ ] Run a simulation.
- [ ] Inspect metrics and content identities.
- [ ] Inspect temporal provenance.
- [ ] Export a report.
- [ ] Run all guide code against the built wheel in CI.
- [ ] Add an availability-time concept page.
- [ ] Add a content-identity concept page.
- [ ] Add a snapshot-boundary concept page.
- [ ] Add a leases concept page.
- [ ] Add an accounting-reconciliation concept page.
- [ ] Add a capability-status concept page.
- [ ] Publish the generated capability matrix.
- [ ] Update README assumptions and limitations.
- [ ] Update API navigation and links.
- [ ] Restore the navigation entries in `mkdocs.yml`.
- [ ] Restore the removed checks in `scripts/check_docs.py`.
- [ ] Apply ASD-STE100 controlled language.

#### Tests

- [ ] Validate every Python example.
- [ ] Execute the complete quickstart against an installed wheel.
- [ ] Run strict MkDocs build.
- [ ] Run controlled-language checks.
- [ ] Test generated capability data against registry data.
- [ ] Test all internal documentation links.

#### Exit criteria

- [ ] A new user can complete one correct public workflow.
- [ ] CI proves that the documented workflow executes.
- [ ] Capability documentation always agrees with the registry.
- [ ] Every deferred capability appears in the published matrix.

## Wave 5: Release preparation

### `release/3.1.0`

A human starts this branch after all implementation branches merge.

#### Entry gate

- [ ] Confirm that every prior branch merged into `develop`.
- [ ] Confirm that every checklist exit criterion has evidence.
- [ ] Confirm that no stable capability lacks an executable path.
- [ ] Confirm that every deferred capability has an approved register entry.
- [ ] Confirm that all performance budgets pass.
- [ ] Confirm that all installation profiles pass.
- [ ] Confirm that the documented workflow passes against the built wheel.

#### Release branch work

- [ ] Create `release/3.1.0` from `develop`.
- [ ] Change the version in `pyproject.toml`.
- [ ] Update `uv.lock`.
- [ ] Finalize the 3.1.0 changelog entry.
- [ ] Run the complete gate on Python 3.12, 3.13, and 3.14.
- [ ] Run lowest-direct and highest dependency checks.
- [ ] Build the wheel and source distribution.
- [ ] Install and smoke-test each supported profile.
- [ ] Inspect package contents and license data.
- [ ] Confirm that line coverage is at least 90 percent.
- [ ] Publish the evidence document.

#### Human release actions

- [ ] Approve the release merge.
- [ ] Merge the release branch into `main`.
- [ ] Sign and create tag `v3.1.0`.
- [ ] Push the release branches and tag.
- [ ] Publish the distributions.
- [ ] Merge the release branch back into `develop`.

## Release acceptance criteria

- [ ] SQL previews distinguish complete and truncated results.
- [ ] Every accepted SQL safety limit executes.
- [ ] The SQL function allowlist applies to every function node.
- [ ] No non-deterministic query receives a safe temporal classification.
- [ ] Every stable enum value and union variant has an executable service path.
- [ ] Every unavailable enum value fails at request construction.
- [ ] Iterator peak memory stays bounded as relation size increases.
- [ ] Provider conformance cannot pass when all capabilities are skipped.
- [ ] One public call creates a complete project topology.
- [ ] Each optional installation profile passes independent tests.
- [ ] No declared runtime dependency lacks a source reference.
- [ ] The public workflow runs against the packaged wheel.
- [ ] Failure and concurrency tests prove transactional recovery.
- [ ] The 3.0.2 baseline project migrates with preserved identities.

## Evidence

Record release evidence at `docs/releases/3.1.0-evidence.md`. Each exit criterion needs
one linked artifact.

CI must upload these artifacts for each release candidate:

- [ ] The generated capability matrix.
- [ ] The benchmark measurement JSON files.
- [ ] The coverage XML report.
- [ ] The provider conformance reports.
- [ ] The package smoke logs for each profile.
- [ ] The quickstart execution log.

## Risks

| Risk | Effect | Response |
| --- | --- | --- |
| DuckDB interrupt acts per connection | Timeout work needs a cursor redesign | Prototype in the first week of the SQL branch |
| sqlglot reclassifies functions | The allowlist changes silently | Add a version conformance test |
| Restored documentation drifts from the API | The quickstart fails in CI | Correct each page before the branch merges |
| Restored benchmarks fail on current hardware | Budgets need rebasing | Record new budgets and mark them as rebased |
| Private-usage ratchet blocks refactors | Branches stall | Allow a reviewed ceiling change with a recorded reason |
| Coverage floor rise fails on merge | Branches stall | Raise the floor in the first wave, before feature work |

## Finding traceability

| Review finding | Priority | Size | Confidence | Owning branch |
| --- | --- | --- | --- | --- |
| SQL preview semantics | P0 | S | High | `fix/3.1-sql-contracts` |
| SQL limit enforcement | P0 | L | Medium | `fix/3.1-sql-contracts` |
| SQL function allowlist bypass | P0 | M | High | `fix/3.1-sql-contracts` |
| Public capability mismatch | P0 | L | High | `feat/3.1-capability-registry` |
| Weak provider conformance | P0 | L | Medium | `fix/3.1-provider-conformance` |
| Materializing iterators | P1 | L | Medium | `refactor/3.1-bounded-readers` |
| Incomplete project initialization | P1 | M | High | `feat/3.1-project-bootstrap` |
| Broad required dependencies | P1 | S | High | `refactor/3.1-optional-dependencies` |
| Missing comparison fixtures | P1 | M | High | `test/3.1-compat-baseline` |
| Missing benchmark harness | P1 | M | High | `test/3.1-bench-harness` |
| Coverage floor below measurement | P1 | S | High | `chore/3.1-verification-gates` |
| Unused test markers | P1 | S | High | `chore/3.1-verification-gates` |
| Workflow documentation gaps | P1 | M | Medium | `docs/3.1-public-workflow` |
| Failure and concurrency test gaps | P1 | L | Medium | `test/3.1-release-assurance` |
| USD accounting boundary | P1 | M | Medium | `feat/3.1-currency-schema` |
| Private usage suppressions | P2 | S | High | `chore/3.1-verification-gates` |

## Deferral register

These findings move to a later release. Each one keeps a registry entry with a target
release.

| Finding | Target release | Reason |
| --- | --- | --- |
| Unimplemented managed operators | 3.2.0 | Needs the workflow refactor first |
| Unimplemented alpha metrics | 3.2.0 | Needs the workflow refactor first |
| Nested validation assembly | 3.2.0 | Needs a design interview |
| Feature SQL relation execution | 3.2.0 | Needs the workflow refactor first |
| Final-holdout governance | 3.2.0 | New subsystem with a large surface |
| Point-in-time acquisition gaps | 3.2.0 | Blocked on provider licensing |
| Large catalog methods | 3.2.0 | Follows the workflow refactor |
| Vectorized simulation scans | 3.3.0 | Large engine change |
| Static event simulation | 3.3.0 | Large engine change |
| Multi-currency behavior | 3.3.0 | Follows the schema branch |
| USD column removal | 4.0.0 | Breaking public change |

## Completion rule

Persistra 3.1.0 is ready only when every release acceptance criterion has recorded
evidence. A version change alone does not make the release ready.
