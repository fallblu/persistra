# Persistra 3.1.0 roadmap

## Purpose

This roadmap defines the work for Persistra 3.1.0. It covers all findings in the
Persistra 3.0.2 review.

The review examined commit `d64fb30646c05f673c0e387e15abd5ea7d280664`. This roadmap
starts from `develop` at commit `f065310`.

The later commits added controlled-language rules and documentation checks. They did not
close the review findings.

All P0, P1, and P2 findings are release requirements. A branch can change its design
after the necessary interview. It cannot remove its assigned release requirement.

## Release principles

- [ ] Make each stable public capability executable for supported input.
- [ ] Reject each unavailable capability during request construction.
- [ ] Preserve current public enum members and SQL relation types in 3.1.0.
- [ ] Use capability status and typed errors instead of breaking removals.
- [ ] Enforce each accepted resource limit.
- [ ] Measure limits that make performance or memory claims.
- [ ] Preserve point-in-time rules across each new workflow.
- [ ] Preserve deterministic identities and balanced accounting.
- [ ] Use public APIs in all user workflow documentation.
- [ ] Keep release actions under human control.

## Branch rules

Create each implementation branch from the latest `develop` after its prerequisite
branches merge.

Before implementation, complete a branch-specific interview. Confirm scope, API shape,
edge cases, compatibility, and tests.

Each branch must meet these conditions:

- [ ] Keep each commit coherent and green.
- [ ] Use subject-only Conventional Commit messages.
- [ ] Add user-facing changes to the 3.1.0 section of `CHANGELOG.md`.
- [ ] Add migrations for each persistent schema change.
- [ ] Test migration from a 3.0.2 project when a schema changes.
- [ ] Update API documentation and docstrings with the implementation.
- [ ] Follow ASD-STE100 Simplified Technical English in documentation.
- [ ] Run the complete verification gate before merge.
- [ ] Use a pull request with Summary and Test plan sections.
- [ ] Use rebase-and-merge into `develop`.

Use this verification gate:

```bash
make lint type test docs-check
make docs-build
make schema-check
uv lock --check
```

Dependency and packaging branches must also test the affected dependency bands and
installation profiles.

## Branch sequence

| Wave | Branch | Prerequisites |
| --- | --- | --- |
| 1 | `feat/3.1-capability-registry` | None |
| 1 | `fix/3.1-sql-contracts` | None |
| 1 | `fix/3.1-provider-conformance` | `feat/3.1-capability-registry` |
| 1 | `feat/3.1-project-bootstrap` | None |
| 2 | `refactor/3.1-research-workflows` | `feat/3.1-capability-registry` |
| 2 | `refactor/3.1-bounded-readers` | `fix/3.1-sql-contracts`, `refactor/3.1-research-workflows` |
| 2 | `refactor/3.1-vector-simulation` | None |
| 2 | `feat/3.1-event-strategy-engine` | None |
| 3 | `feat/3.1-final-holdouts` | `feat/3.1-capability-registry`, `refactor/3.1-research-workflows` |
| 3 | `feat/3.1-research-capabilities` | `feat/3.1-capability-registry`, `refactor/3.1-bounded-readers` |
| 3 | `feat/3.1-vintage-acquisition` | `feat/3.1-capability-registry`, `fix/3.1-provider-conformance` |
| 3 | `feat/3.1-multi-currency-accounting` | Both simulation branches, `feat/3.1-vintage-acquisition` |
| 4 | `refactor/3.1-optional-dependencies` | All feature and runtime refactor branches |
| 4 | `test/3.1-release-assurance` | All feature and runtime refactor branches |
| 4 | `docs/3.1-public-workflow` | All implementation and packaging branches |
| 5 | `release/3.1.0` | All prior branches |

Branches in the same wave can proceed together when they do not change the same files.
Recheck the branch base before work starts.

## Wave 1: Public contract correctness

### `feat/3.1-capability-registry`

This branch creates one source of truth for public capability status. Other branches
change status only after their capability tests pass.

#### Design decisions

- [ ] Define the exact meaning of `stable`, `experimental`, `planned`, and `unavailable`.
- [ ] Define compatibility rules for serialized requests that contain unavailable values.
- [ ] Define the public query API and the internal registration API.
- [ ] Define how optional installation requirements appear in capability records.

#### Implementation

- [ ] Add immutable capability identifiers and status records.
- [ ] Record status, reason, version, requirements, and optional installation profile.
- [ ] Register each `FeatureSqlRelation` variant.
- [ ] Register each `ManagedOperator` value.
- [ ] Register each `AlphaMetricKind` value.
- [ ] Register each validation mode.
- [ ] Register first-party provider families and vintage support.
- [ ] Register simulation modes and strategy support.
- [ ] Replace duplicated executable allowlists with registry queries.
- [ ] Validate unavailable choices when callers construct requests.
- [ ] Raise one precise typed capability error.
- [ ] Preserve all current enum members and SQL relation union members.
- [ ] Expose a read-only public capability query.
- [ ] Generate machine-readable capability data for documentation.
- [ ] Prevent a capability from becoming stable without executable evidence.

#### Tests

- [ ] Test each status and each status transition rule.
- [ ] Test precise construction-time errors for unavailable choices.
- [ ] Test stable capability execution with representative input.
- [ ] Test synchronization between enums, unions, services, and registry records.
- [ ] Test deterministic serialization of capability data.
- [ ] Test old serialized requests with preserved public values.

#### Exit criteria

- [ ] One registry controls validation and documentation status.
- [ ] No stable registry entry lacks an executable test.
- [ ] No unavailable value reaches a late service failure.

### `fix/3.1-sql-contracts`

This branch corrects SQL preview behavior and enforces every accepted SQL read limit.
It owns bounded SQL result reading.

#### Design decisions

- [ ] Select the DuckDB cancellation mechanism.
- [ ] Define timeout behavior during connection cleanup and transactions.
- [ ] Define result metadata for applied limits and termination reasons.
- [ ] Define unsupported limit combinations.

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

#### Exit criteria

- [ ] SQL preview metadata agrees with returned data.
- [ ] No accepted SQL safety limit is ignored.
- [ ] SQL peak materialization follows the configured batch size.

### `fix/3.1-provider-conformance`

This branch makes a passing provider report prove real managed interoperability.

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

### `feat/3.1-project-bootstrap`

This branch makes project initialization create a complete database topology atomically.

#### Design decisions

- [ ] Define research and market database specification models.
- [ ] Choose idempotent or conflict behavior for repeated initialization.
- [ ] Define path ownership and rollback rules.
- [ ] Define behavior for existing compatible database files.

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
- [ ] Apply the same validation rules during later database addition.
- [ ] Keep project configuration valid after each failure.

#### Tests

- [ ] Test complete research and market initialization.
- [ ] Test repeated initialization behavior.
- [ ] Test mixed created and reused resources.
- [ ] Test validation before filesystem changes.
- [ ] Inject failure after each creation phase.
- [ ] Test rollback without loss of existing files.
- [ ] Test read-only and creation policies.
- [ ] Test concurrent initialization conflicts.

#### Exit criteria

- [ ] One public call can create a complete project.
- [ ] A failed call leaves no partial new project.
- [ ] Post-initialization expansion uses a supported public API.

## Wave 2: Bounded and maintainable execution

### `refactor/3.1-research-workflows`

This branch divides large research workflows into explicit phases. It must preserve
public behavior before later capability work starts.

#### Design decisions

- [ ] Define typed inputs and outputs for each phase.
- [ ] Define transaction ownership across phase boundaries.
- [ ] Define shared temporal-boundary and manifest services.
- [ ] Select failure-injection points.

#### Implementation

- [ ] Divide analysis `_compute` into validation, loading, calculation, and persistence phases.
- [ ] Divide catalog ingestion `commit` into planning, normalization, mutation, and finalization phases.
- [ ] Divide component materialization into planning, execution, identity, and persistence phases.
- [ ] Keep one simple public orchestration entry point for each workflow.
- [ ] Isolate pure planning from storage mutation.
- [ ] Replace large nested closures with one transaction coordinator.
- [ ] Centralize temporal-boundary enforcement.
- [ ] Centralize manifest creation.
- [ ] Give each phase a typed immutable contract.
- [ ] Preserve current content identities for equivalent input.
- [ ] Preserve current database output for equivalent input.

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Add integration tests for each orchestration entry point.
- [ ] Inject failure at each phase boundary.
- [ ] Test rollback and retry after each injected failure.
- [ ] Compare identities and rows with 3.0.2 fixtures.

#### Exit criteria

- [ ] Each named phase has direct deterministic tests.
- [ ] Storage mutation has one clear transaction owner.
- [ ] Equivalent input preserves behavior and identity.

### `refactor/3.1-bounded-readers`

This branch makes non-SQL row iterators use bounded database batches. The SQL branch
owns the SQL reader implementation.

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
- [ ] Test incremental identity against canonical full-frame identity.

#### Exit criteria

- [ ] Peak reader memory does not grow with total relation size.
- [ ] Every row bound applies before full materialization.
- [ ] Early consumer termination releases all database resources.

### `refactor/3.1-vector-simulation`

This branch removes repeated scans and database reads from vectorized simulation. It
also divides the engine into explicit phases.

#### Design decisions

- [ ] Set runtime, query-count, and peak-memory budgets.
- [ ] Define in-memory state and reconciliation checkpoints.
- [ ] Define persistence batch sizes.
- [ ] Define incremental manifest identity behavior.

#### Implementation

- [ ] Normalize and sort all inputs once.
- [ ] Index weights by decision timestamp.
- [ ] Index bars by instrument and timestamp.
- [ ] Add direct next-bar lookup.
- [ ] Index corporate actions by effective timestamp and instrument.
- [ ] Index corporate-action legs with their actions.
- [ ] Maintain cash in memory during execution.
- [ ] Maintain positions in memory during execution.
- [ ] Maintain cumulative fills and pending state in memory.
- [ ] Remove repeated position and cash queries from the decision loop.
- [ ] Remove cumulative fill rescans.
- [ ] Remove full bar filters from capacity calculation.
- [ ] Reconcile in-memory state at explicit checkpoints.
- [ ] Batch fills, postings, positions, and metrics.
- [ ] Compute manifest identities as batches become final.
- [ ] Divide execution into planning, market, accounting, and persistence phases.
- [ ] Keep the public simulation API simple.

#### Tests

- [ ] Vary decisions while other benchmark dimensions remain fixed.
- [ ] Vary instruments while other benchmark dimensions remain fixed.
- [ ] Vary orders while other benchmark dimensions remain fixed.
- [ ] Vary bar density while other benchmark dimensions remain fixed.
- [ ] Measure database query count.
- [ ] Measure peak memory.
- [ ] Measure runtime growth.
- [ ] Compare results and identities with deterministic 3.0.2 fixtures.
- [ ] Test each reconciliation checkpoint.
- [ ] Inject failure at each persistence boundary.

#### Exit criteria

- [ ] Query count has no repeated state lookup for each decision.
- [ ] Runtime growth meets the recorded complexity budget.
- [ ] Results preserve accounting and identity invariants.

### `feat/3.1-event-strategy-engine`

This branch makes event simulation scalable and reactive. It preserves declarative
order replay as a deterministic mode.

#### Design decisions

- [ ] Define the immutable strategy state and event protocol.
- [ ] Define the command types that a strategy can return.
- [ ] Set limits for orders, bars, instruments, and emitted events.
- [ ] Define equal-timestamp phase order.
- [ ] Define corporate-action entitlement and cash-in-lieu policies.
- [ ] Define strategy failure and cancellation behavior.

#### Implementation

- [ ] Preserve current `OrderSpec` replay behavior as a supported mode.
- [ ] Partition replay orders by instrument and activation timestamp.
- [ ] Use per-instrument cursors or heaps for order activation.
- [ ] Stop scanning every order for every bar.
- [ ] Enforce request limits before execution.
- [ ] Enforce emitted-event limits during execution.
- [ ] Stream ordered bars where practical.
- [ ] Add a stateful strategy protocol.
- [ ] Give strategies immutable market, fill, position, and cash state.
- [ ] Let strategies return typed commands.
- [ ] Process market events in one deterministic phase.
- [ ] Apply corporate actions in one deterministic phase.
- [ ] Run strategy decisions in one deterministic phase.
- [ ] Activate orders and generate fills in separate phases.
- [ ] Run accounting and reconciliation in separate phases.
- [ ] Handle splits and dividends.
- [ ] Handle symbol changes and delistings.
- [ ] Handle fractional cash-in-lieu results.
- [ ] Divide the large execution method into typed phases.
- [ ] Record phase order and strategy identity in results.

#### Tests

- [ ] Test equal timestamps with deterministic ordering.
- [ ] Test partial fills and rejected orders.
- [ ] Test action and order collisions.
- [ ] Test strategy commands after fills.
- [ ] Test strategy commands after position and cash changes.
- [ ] Test each order, bar, instrument, and event limit.
- [ ] Test replay compatibility with 3.0.2 fixtures.
- [ ] Test deterministic strategy replay.
- [ ] Test each supported corporate-action lifecycle.
- [ ] Inject failure at each execution and persistence phase.
- [ ] Benchmark bars and orders independently.

#### Exit criteria

- [ ] Event replay does not scan every order for every bar.
- [ ] Strategies can react to new managed state.
- [ ] Replay and strategy modes remain deterministic.

## Wave 3: Research governance and market breadth

### `feat/3.1-final-holdouts`

This branch adds managed final-holdout assets and audited confirmatory access.

#### Design decisions

- [ ] Define the holdout asset schema and content identity.
- [ ] Define single-use, bounded-use, and administrator reuse policies.
- [ ] Define authorization and administrator boundaries.
- [ ] Define which metadata exploratory services can reveal.
- [ ] Define result behavior after a failed confirmatory use.

#### Implementation

- [ ] Add an immutable final-holdout asset.
- [ ] Bind each asset to dataset, label, universe, temporal boundary, and split policy.
- [ ] Seal membership and content identity before exploratory analysis.
- [ ] Add managed holdout tables and migrations.
- [ ] Require `FinalHoldoutUseId` for access.
- [ ] Require `AnalysisIntent.CONFIRMATORY_HOLDOUT` for analysis access.
- [ ] Record each access attempt.
- [ ] Record each successful use and derived result.
- [ ] Enforce single-use policies.
- [ ] Enforce bounded-use policies.
- [ ] Enforce administrator-authorized reuse.
- [ ] Block exploratory row access.
- [ ] Block exploratory summary statistics.
- [ ] Make experiments use managed holdout IDs for confirmatory evaluation.
- [ ] Reject arbitrary fold IDs for confirmatory evaluation.
- [ ] Include holdout identity and use identity in result provenance.
- [ ] Keep sealed membership immutable after creation.

#### Tests

- [ ] Test creation, sealing, and immutable identity.
- [ ] Test each use policy.
- [ ] Test authorized and unauthorized reuse.
- [ ] Test complete access audit records.
- [ ] Test experiments with managed holdouts.
- [ ] Test rejection of arbitrary confirmatory fold IDs.
- [ ] Test exploratory dataset services against sealed rows.
- [ ] Test exploratory SQL services against sealed rows.
- [ ] Test exploratory feature and analysis services against summary disclosure.
- [ ] Test concurrent attempts to consume one single-use holdout.
- [ ] Test rollback after failed confirmatory execution.

#### Exit criteria

- [ ] Confirmatory access is sealed, authorized, and audited.
- [ ] Exploratory paths cannot reveal holdout rows or summaries.
- [ ] Experiments cannot bypass managed holdout policy.

### `feat/3.1-research-capabilities`

This branch implements every currently declared research capability that cannot execute.
It changes registry entries to stable only after their tests pass.

#### Design decisions

- [ ] Specify formulas, units, missing-data rules, and minimum samples.
- [ ] Specify lookback, availability, and leakage rules for each operator.
- [ ] Specify tie handling for labels and rank diagnostics.
- [ ] Define nested validation assembly and identity rules.
- [ ] Define feature SQL relation dependency and materialization behavior.

#### SQL relations

- [ ] Resolve `FeatureSqlRelation` dependencies.
- [ ] Execute feature relations in managed SQL reads.
- [ ] Apply the same limits as other SQL relations.
- [ ] Record feature ancestry in SQL result provenance.

#### Managed operators

- [ ] Implement `AMIHUD_ILLIQUIDITY`.
- [ ] Implement `DOWNSIDE_DEVIATION`.
- [ ] Implement `ESTIMATE_DISPERSION`.
- [ ] Implement `EVENT_RETURN`.
- [ ] Implement `EXPECTED_SHORTFALL`.
- [ ] Implement `MAXIMUM_ADVERSE_EXCURSION`.
- [ ] Implement `MAXIMUM_FAVORABLE_EXCURSION`.
- [ ] Implement `REGIME_THRESHOLD`.
- [ ] Implement `RETURN_SKEWNESS`.
- [ ] Implement `ROLLING_BETA`.
- [ ] Implement `ROLLING_CORRELATION`.
- [ ] Implement `ROLLING_COVARIANCE`.
- [ ] Implement `TRADE_ACTIVITY`.
- [ ] Implement `TRIPLE_BARRIER`.
- [ ] Implement `TURNOVER`.
- [ ] Implement `VOLUME_ACTIVITY`.

#### Alpha metrics

- [ ] Implement `AUTOCORRELATION`.
- [ ] Implement `CATEGORICAL_EXPOSURE`.
- [ ] Implement `DECAY`.
- [ ] Implement `JOINT_EXPOSURE`.
- [ ] Implement `NUMERIC_EXPOSURE`.
- [ ] Implement `PERSISTENCE`.
- [ ] Implement `TURNOVER`.

#### Validation

- [ ] Implement `ValidationSchemeKind.NESTED` construction.
- [ ] Add a public nested validation assembly API.
- [ ] Preserve outer and inner fold ancestry.
- [ ] Enforce purging and embargo rules at both levels.
- [ ] Prevent inner selection data from reaching outer evaluation.

#### Tests

- [ ] Add numerical reference tests for each operator.
- [ ] Add numerical reference tests for each alpha metric.
- [ ] Add property tests for temporal cutoffs.
- [ ] Add property tests for units and monotonic transformations.
- [ ] Test missing, constant, sparse, and short input.
- [ ] Test feature SQL limits and ancestry.
- [ ] Test nested fold isolation and identity.
- [ ] Test each capability through its public service.
- [ ] Test bounded materialization for large input.

#### Exit criteria

- [ ] Every preserved public research choice has an executable path.
- [ ] Each capability has documented numerical and temporal semantics.
- [ ] The registry and executable tests agree.

### `feat/3.1-vintage-acquisition`

This branch adds true historical vintages and broader first-party market data. It must
select sources before implementation.

#### Design decisions

- [ ] Select at least one revision-aware provider.
- [ ] Review provider licenses and redistribution limits.
- [ ] Define credential and offline-test requirements.
- [ ] Select maintained data families for 3.1.0.
- [ ] Define strict point-in-time adapter requirements.

#### Implementation

- [ ] Ingest macro observations with release and revision timestamps.
- [ ] Record observation, release, availability, and revision timestamps.
- [ ] Add first-party fundamental ingestion.
- [ ] Record filing date and acceptance timestamp.
- [ ] Preserve restatements and effective availability.
- [ ] Preserve raw provider payload identity.
- [ ] Record provider and adapter versions.
- [ ] Broaden maintained price and corporate-action acquisition.
- [ ] Broaden maintained reference data acquisition.
- [ ] Add historical index membership acquisition.
- [ ] Preserve each membership change and its availability.
- [ ] Mark latest-only adapters in machine-readable metadata.
- [ ] Mark each adapter vintage capability in the registry.
- [ ] Reject latest-only adapters for strict point-in-time requests.
- [ ] Connect provider fixtures to the conformance suite.

#### Tests

- [ ] Add offline fixtures with revisions.
- [ ] Add offline fixtures with late arrivals.
- [ ] Add offline fixtures with corrections.
- [ ] Add offline fixtures with provider restatements.
- [ ] Test as-of queries before and after each revision.
- [ ] Test filing acceptance boundaries.
- [ ] Test historical membership boundaries.
- [ ] Test raw payload and managed output identities.
- [ ] Run provider conformance for each new adapter family.
- [ ] Test latest-only rejection for strict research.

#### Exit criteria

- [ ] One first-party path verifies revisions and historical availability.
- [ ] Fundamentals and membership history have maintained acquisition paths.
- [ ] Machine-readable metadata states each adapter limitation.

### `feat/3.1-multi-currency-accounting`

This branch extends point-in-time currency support through accounting, simulation, and
results.

#### Design decisions

- [ ] Define reporting-currency configuration and USD compatibility behavior.
- [ ] Define native and reporting amount models.
- [ ] Define FX path selection and staleness policy.
- [ ] Define settlement and action conversion times.
- [ ] Define migration rules for USD-specific stored fields.

#### Implementation

- [ ] Add a reporting currency to portfolio configuration.
- [ ] Add a reporting currency to simulation configuration.
- [ ] Replace internal USD assumptions with currency-aware values.
- [ ] Maintain cash ledgers by native currency.
- [ ] Record native trade, fee, settlement, dividend, and action amounts.
- [ ] Resolve FX marks at the correct availability cutoff.
- [ ] Record FX rate identity and timestamp.
- [ ] Record the complete FX conversion path.
- [ ] Record native and reporting values.
- [ ] Separate local-asset profit from FX profit.
- [ ] Expose currency exposures.
- [ ] Expose conversion staleness.
- [ ] Reject missing or stale FX paths with typed errors.
- [ ] Prevent non-USD assets from entering unsupported operations.
- [ ] Update vectorized simulation for native ledgers.
- [ ] Update event simulation for native ledgers.
- [ ] Update accounting reconciliation for each currency.
- [ ] Update result metrics, reports, exports, and dashboard views.
- [ ] Migrate current USD data without identity ambiguity.

#### Tests

- [ ] Test same-currency and cross-currency trades.
- [ ] Test native-currency dividends.
- [ ] Test fees and commissions in different currencies.
- [ ] Test settlement across currencies.
- [ ] Test splits and cash-in-lieu across currencies.
- [ ] Test cash transfers across currencies.
- [ ] Test direct and multi-leg FX paths.
- [ ] Test stale and missing FX data.
- [ ] Test point-in-time FX availability.
- [ ] Test local and FX profit decomposition.
- [ ] Test balance by ledger and currency.
- [ ] Test migration of USD-only projects.

#### Exit criteria

- [ ] Non-USD assets cannot silently use USD values.
- [ ] Each translated amount contains complete FX provenance.
- [ ] Accounting remains balanced in native and reporting views.

## Wave 4: Packaging, assurance, and documentation

### `refactor/3.1-optional-dependencies`

This branch reduces the required installation and adds independently tested capability
profiles.

#### Design decisions

- [ ] Define the minimum supported core.
- [ ] Map public capabilities to installation profiles.
- [ ] Decide which direct dependencies are necessary.
- [ ] Define imports that remain safe in a core installation.

#### Implementation

- [ ] Define a core installation for project, storage, schemas, identity, and basic market operations.
- [ ] Add a `research` extra.
- [ ] Add a `sql` extra.
- [ ] Add an `optimization` extra.
- [ ] Add a `search` extra.
- [ ] Add a `viz` extra.
- [ ] Add a `dashboard` extra.
- [ ] Add an `all` extra.
- [ ] Preserve `dev` and `docs` tool groups.
- [ ] Audit each direct runtime dependency against source imports.
- [ ] Remove unnecessary direct declarations.
- [ ] Isolate optional imports at capability boundaries.
- [ ] Add a typed optional-dependency error.
- [ ] Name the necessary extra in each optional-dependency error.
- [ ] Connect installation requirements to capability records.
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

### `test/3.1-release-assurance`

This branch closes cross-system failure, concurrency, scale, and browser test gaps.
Feature branches still own their direct tests.

#### Design decisions

- [ ] Set stable runtime, query-count, and memory budgets.
- [ ] Define benchmark hardware normalization.
- [ ] Define critical module coverage expectations.
- [ ] Define browser support and test scope.

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

#### Browser and performance tests

- [ ] Test dashboard navigation in a browser.
- [ ] Test dashboard state and representative charts.
- [ ] Test dashboard error display and recovery.
- [ ] Use the `browser` marker.
- [ ] Benchmark bounded queries and materialization.
- [ ] Benchmark vectorized simulation.
- [ ] Benchmark event replay and strategy execution.
- [ ] Record elapsed runtime.
- [ ] Record peak resident memory.
- [ ] Record database query count.
- [ ] Fail CI on approved budget regressions.

#### Coverage

- [ ] Set expectations for dashboard services.
- [ ] Set expectations for feature and component services.
- [ ] Set expectations for report and SQL services.
- [ ] Set expectations for portfolio and reference services.
- [ ] Keep the global coverage floor at or above 85 percent.

#### Exit criteria

- [ ] Each configured risk marker has meaningful tests.
- [ ] Transaction recovery has process-level evidence.
- [ ] Resource budgets have repeatable measurements.
- [ ] Critical service coverage meets recorded expectations.

### `docs/3.1-public-workflow`

This branch adds a tested public workflow and the necessary concept documentation.

#### Implementation

- [ ] Add a quickstart that uses only public APIs.
- [ ] Initialize research and market databases.
- [ ] Ingest a small offline fixture.
- [ ] Create a point-in-time snapshot.
- [ ] Create a research dataset.
- [ ] Materialize a feature and label.
- [ ] Assemble a supported validation plan.
- [ ] Run research construction.
- [ ] Run a simulation.
- [ ] Inspect metrics and content identities.
- [ ] Inspect temporal and FX provenance.
- [ ] Export a report.
- [ ] Run all guide code against the built wheel in CI.
- [ ] Add an availability-time concept page.
- [ ] Add a revisions concept page.
- [ ] Add a content-identity concept page.
- [ ] Add a snapshot-boundary concept page.
- [ ] Add a leases concept page.
- [ ] Add an accounting-reconciliation concept page.
- [ ] Add a capability-status concept page.
- [ ] Publish the generated capability matrix.
- [ ] Update README assumptions and limitations.
- [ ] Update API navigation and links.
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

## Wave 5: Release preparation

### `release/3.1.0`

A human starts this branch after all implementation branches merge. Release work cannot
waive an unmet requirement in this roadmap.

#### Entry gate

- [ ] Confirm that every prior branch merged into `develop`.
- [ ] Confirm that every checklist exit criterion has evidence.
- [ ] Confirm that no stable capability lacks an executable path.
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
- [ ] Confirm that coverage is at least 85 percent.

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
- [ ] Every stable enum value and union variant has an executable service path.
- [ ] Final-holdout access is sealed, authorized, and audited.
- [ ] Iterator peak memory stays bounded as relation size increases.
- [ ] Vectorized simulation avoids repeated state queries for each decision.
- [ ] Event replay avoids a complete order scan for each bar.
- [ ] Provider conformance cannot pass when all capabilities are skipped.
- [ ] One first-party acquisition path verifies revisions and historical availability.
- [ ] Non-USD assets cannot enter USD-only accounting silently.
- [ ] Each optional installation profile passes independent tests.
- [ ] The public workflow runs against the packaged wheel.
- [ ] Failure and concurrency tests prove transactional recovery.

## Finding traceability

| Review finding | Owning branch |
| --- | --- |
| SQL preview semantics | `fix/3.1-sql-contracts` |
| SQL limit enforcement | `fix/3.1-sql-contracts` |
| Public capability mismatch | `feat/3.1-capability-registry`, `feat/3.1-research-capabilities` |
| Final-holdout governance | `feat/3.1-final-holdouts` |
| Materializing iterators | `fix/3.1-sql-contracts`, `refactor/3.1-bounded-readers` |
| Vectorized simulation scans | `refactor/3.1-vector-simulation` |
| Static event simulation | `feat/3.1-event-strategy-engine` |
| Point-in-time acquisition gaps | `feat/3.1-vintage-acquisition` |
| Weak provider conformance | `fix/3.1-provider-conformance` |
| Incomplete project initialization | `feat/3.1-project-bootstrap` |
| USD accounting boundary | `feat/3.1-multi-currency-accounting` |
| Broad required dependencies | `refactor/3.1-optional-dependencies` |
| Large execution methods | Three workflow and simulation refactor branches |
| Failure, scale, and browser test gaps | `test/3.1-release-assurance` |
| Workflow documentation gaps | `docs/3.1-public-workflow` |

## Completion rule

Persistra 3.1.0 is ready only when every release acceptance criterion has recorded
evidence. A version change alone does not make the release ready.
