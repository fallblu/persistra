# Persistra v3 implementation review

**Review date:** 2026-07-18  
**Reviewed branch:** `v3-integration` at `4a40873`  
**Scope:** Current implementation, public API, tests, typing, packaging configuration,
documentation, and practical user workflows. Per review direction, this review does not
evaluate v2 compatibility or compare v3 behavior with a prior release.

## Executive summary

The repository contains a promising, coherent foundation, but it is not ready for a full v3
release. Project/database ownership, typed domain values, canonical data storage, bounded
queries, immutable identities, accounting journals, the basic vectorized workflow, offline
reports, and the loopback dashboard are meaningful implementations rather than empty
scaffolding. The all-extras development environment passes lint, strict typing, documentation
builds, and 163 tests.

The current release-candidate description nevertheless materially overstates the implemented
surface. Several normative v3 contracts are partial, some public enums accept operations that
are not executable, and late-stage subsystems implement a narrow demonstration slice under
names that imply the complete design. Three correctness problems should block any release:

1. Portable export manifests are not authenticated on read, so run identity, provenance, and
   fidelity claims can be changed without detection.
2. `persistra.standard@1` does not implement the specified metric catalog, and at least the
   turnover and historical VaR calculations disagree with their normative formulas.
3. Event simulation backdates close/high/low/volume-derived decisions to the bar open and does
   not enforce a valid horizon for every order, violating the project's central temporal
   contract.

Other release-blocking gaps include absent unsafe-lineage enforcement at portfolio/simulation
boundaries, nonfunctional portions of the managed feature and alpha catalogs, a placeholder
Bayesian search path, no stateful event-strategy callback, no normalized event-run result,
incomplete validation/forecast/result/analysis contracts, no final multifactor flagship, no
benchmark implementation, a failing clean CI configuration, and insufficient test
traceability. The recommended decision is **do not release v3 until all critical and high
findings below are resolved or the normative specifications and public claims are explicitly
re-scoped**.

## What is working well

- The top-level API is intentionally small and typed. Namespace exports are explicit, and
  optional namespaces generally import without eagerly importing their optional runtime.
- `Project` establishes thread/process ownership, leases, explicit modes, managed DuckDB
  connections, and bounded service access. Basic initialization, inspection, diagnostics, and
  read-only use worked in both the development environment and a clean base installation.
- Domain identity, serialization, time, fixed-precision number, dataframe, event, and seed
  primitives have comparatively strong tests and clear failure types.
- Catalog ingestion, revisions, quarantine, precedence, snapshots, research dataset creation,
  accounting, and the vectorized vertical slice have substantial integration coverage.
- The accounting journal balances in the exercised long/short, fee, split, dividend, accrual,
  borrow, and settlement examples.
- Public result queries are bounded and raise instead of silently truncating.
- HTML reports are self-contained, and report directory bundles verify a closed file set and
  reject unsafe paths.
- Dashboard configuration defaults to loopback, rejects a public bind without an explicit
  unsupported override, disables telemetry/static serving, and uses short-lived project
  scopes.
- The codebase passes Ruff and strict Pyright without errors.

These strengths make the repository a good foundation for completing v3. They do not offset
the correctness and contract gaps below.

## Review method and observed results

### Automated checks

| Check | Result |
| --- | --- |
| `make lint` | Passed |
| `make type` | Passed: 0 errors, warnings, or information messages |
| `make test` in the existing all-extras environment | Passed: 163 tests in 168.03 seconds |
| Branch-aware coverage from that run | 82.44%, above configured 80% but below specified 90% |
| `make docs-check` | Passed |
| `make docs-build` | Passed under MkDocs strict mode |
| `uv lock --check` | Passed |
| Installed interpreter exercised | CPython 3.12.8 on Linux |

The full run's coverage is uneven. Examples include event simulation at 73%, research
components at 68%, legacy feature services at 61%, reports at 70%, SQL services at 74%, and
the dashboard launcher at 28%. More importantly, line coverage cannot detect unimplemented
requirements that have no code.

### Clean-install and CI reproduction

A clean Python 3.12 virtual environment installed with the same extras as the `verify` CI job,
`.[dev,docs]`. It correctly omitted `sqlglot`, `cvxpy`, `plotly`, `streamlit`, and `optuna`.
Basic project initialization/opening succeeded in that environment.

The full test suite did not:

```text
1 failed, 158 passed, 4 skipped
coverage: 76.19% (required: 80%)
failure: VisualizationExtraRequiredError in the flagship integration test
```

The cause is direct: `.github/workflows/ci.yml:19` installs only `dev` and `docs`, while the
flagship test invokes Plotly. Thus the checked-in primary CI job is expected to fail on every
Python version unless an undeclared package happens to be present.

### Practical user-path checks

- `persistra project init`, `project inspect`, and `doctor` worked and returned useful JSON.
- Opening the resulting project read-only and listing its empty result repository worked in a
  clean base install.
- The complete public flagship integration path ran in the all-extras environment, including
  market/reference data, research dataset and feature materialization, target construction,
  vectorized and event simulation, analysis, exports, figures, reports, and dashboard data.
- A real dashboard process started on `127.0.0.1:8765` and served HTML. Interrupting it with
  Ctrl-C emitted a Python `KeyboardInterrupt` traceback from the CLI wrapper.
- A generated portable DuckDB export was copied, its manifest JSON was edited in place, and
  `open_export()` accepted the modified run ID and fidelity finding while returning the
  original stored manifest content ID.
- Turnover was independently recalculated from the same completed run using focused spec 15's
  formula. The library returned `3.051171495200339`; the specified formula returned
  `1.224771926317711`.

### Checks not performed

- Python 3.13 and 3.14 were not installed locally; only the CI declaration was inspected.
- The formal 5,000-instrument/20-year benchmark could not be run because its generator,
  validator, manifest, runner, and runbook are absent.
- A wheel/sdist build was not run because repository instructions reserve build/release
  operations for explicit human authorization. The checked-in CI build configuration was
  reviewed instead.
- No v2 API, artifact, database, or behavioral comparison was performed.

## Critical findings

### V3R-001: Portable export provenance can be changed without detection

**Impact:** Critical integrity and security failure.

Export creation computes a semantic manifest ID at
`src/persistra/results/exports.py:72-88`, but verification never recomputes it. DuckDB
verification validates only the tables named by the untrusted manifest and then returns the
stored ID (`exports.py:127-151`). Bundle verification trusts the manifest's own ID and listed
files (`exports.py:154-161`). `open_export()` repeats the same trust pattern
(`exports.py:397-421`).

The manual reproduction changed `run_record_id` and `fidelity_findings` inside
`_persistra_export_manifest.manifest_json`. `open_export()` then reported the attacker-chosen
run ID and fidelity tuple while preserving the original manifest ID:

```text
original run: 2d6cd6ea-b88d-4b99-b04b-85d531a04707
opened run:   run_record:00000000-0000-4000-8000-000000000002
opened fidelity: ('tampered.provenance.accepted',)
stored/opened manifest ID: sha256:5598832d...
```

Directory exports also lack report-bundle-style path validation and closed-set verification.
An edited manifest can add unsafe relative paths, omit unlisted files, or redirect a table
lookup outside the bundle.

**Required change:**

- Parse a strict versioned manifest schema.
- Recompute `scoped_content_id({"schema": ..., "manifest": semantic_manifest})` and compare it
  with the stored ID before using any identity or table description.
- Require exactly the supported table set and reject missing, extra, duplicated, case-colliding,
  absolute, symlinked, or traversal paths.
- Verify the closed file set, checksums, table schemas, row counts, ordering/root convention,
  export kind, and supported reader/storage versions.
- Raise typed export verification/security errors rather than generic `ValueError`.
- Add mutation tests for every manifest field and every DuckDB/Parquet/CSV failure mode.

### V3R-002: `persistra.standard@1` is neither the specified catalog nor mathematically conformant

**Impact:** Critical financial-result correctness failure.

Focused spec 15 section 10.4 defines an exact catalog. The implementation at
`src/persistra/analysis/services.py:133-306` emits a different set:

- It omits money-weighted return, drawdown duration, payoff ratio, beta, alpha, active return,
  tracking error, information ratio, holding period, concentration, and participation
  metrics.
- It substitutes `var_95`, `cvar_95`, `excess_kurtosis`, `total_cost`, and
  `capacity_shortfall` for specified names and shapes.
- `hit_rate` uses unit `rate` instead of specified `ratio`.
- Historical VaR uses a single order statistic with no type-7 interpolation and allows one
  observation (`analysis/services.py:195-198, 280-281`) instead of requiring 20.
- Turnover is `traded / average_nav` (`analysis/services.py:216-234`) rather than
  `traded / (2 * average_nav) * year_duration / elapsed_duration`.
- Benchmark and risk-free inputs are not part of the request or identity. Sharpe/Sortino assume
  zero risk-free, while beta/alpha/active metrics cannot be computed.

The turnover discrepancy was reproduced on the flagship output as described above. This is not
only an omitted feature; a published metric name returns the wrong defined quantity.

**Required change:**

- Treat the specification table as a generated/checked registry and implement its exact names,
  formulas, units, minimum samples, states, warnings, and identities.
- Split metric definitions from execution, with hand-worked golden fixtures for every metric.
- Add benchmark/risk-free/cash-flow/lot/exposure/participation inputs to typed analysis requests.
- Refuse an incomplete metric set rather than advertising it as `persistra.standard@1`.
- If the narrow set must remain temporarily, rename it to an explicitly provisional set and
  remove release-candidate claims until the normative set exists.

### V3R-003: Event simulation uses future bar facts at the bar-open timestamp

**Impact:** Critical point-in-time and accounting-timestamp failure.

Every bar is assigned `effective_at = interval_start`
(`src/persistra/simulation/event_services.py:262-272`). At that instant the simulator reads
the bar's full volume for capacity (`event_services.py:336-339`), high/low for limit and stop
reachability, and close for market-on-close (`event_services.py:625-680`). The resulting fill,
journal transaction, settlement, and order transitions are all recorded at the open-time
`effective_at`.

Consequences include:

- A market-on-close fill is priced from the close but timestamped at the open.
- Intrabar high/low reachability is known and acted upon at the open rather than represented as
  a coarse interval outcome with a defensible timing boundary.
- Same-bar reported volume constrains capacity before it is observable.
- Accounting history can show cash/position changes before the price path that caused them.

The request validator compounds this: it checks the horizon against only the earliest order
submission (`event_models.py:157-165`). A later order may be submitted after the horizon, then
receive created/submitted/accepted transitions at its future timestamp and an expiration
transition at the earlier horizon (`event_services.py:245-260, 508-525`).

**Required change:**

- Implement the focused spec's total event clock and explicit observation-availability events.
- Record bar-derived outcomes no earlier than their defensible occurrence/availability
  boundary; represent intrabar timing uncertainty explicitly.
- Separate open, intrabar, close, and post-close capabilities, including order-type eligibility.
- Use only causally available volume/ADV at order eligibility.
- Require `horizon_at` to be after every order/action/callback boundary.
- Add sentinel tests proving close/high/low/volume cannot affect state before availability.

### V3R-004: Safety and lineage are not enforced at portfolio and simulation boundaries

**Impact:** Critical violation of v3's primary no-lookahead guarantee.

The v3 specification requires unsafe/opaque ancestry to be rejected by simulation by default,
with explicit taint under a narrow override, while labels and retrospective roots are always
structurally forbidden. The implemented simulation requests contain no safety policy, unsafe
override, lineage root, or finding set (`src/persistra/simulation/models.py:44-94` and
`simulation/event_models.py:111-165`). Planning checks target existence and a few basic limits,
not safety.

The advanced forecast path reads a named column from an enriched research relation and creates
forecast lineage without checking the enrichment's `safety_status`, information class,
temporal class, or label ancestry (`src/persistra/portfolio/advanced_services.py:119-213`).
Optimization likewise checks only that forecast and risk share a base dataset
(`advanced_services.py:535-601`). No safety material appears in the optimization or simulation
identity.

The simple flagship path uses a separate legacy feature/signal pipeline, which avoids some
unsafe inputs by being narrow but does not prove the general contract.

**Required change:**

- Define one typed decision-input manifest consumed by forecast, risk, construction, and both
  simulators.
- Carry source snapshot roots, information/temporal class, lineage completeness, licensing,
  conformance status, and all findings through every derived artifact.
- Reject direct or indirect label/retrospective ancestry unconditionally.
- Require a typed, persisted unsafe override for eligible opaque inputs and propagate taint
  into results, comparison, export, figures, reports, and dashboard.
- Add adversarial laundering tests through feature, SQL, workspace, forecast, risk,
  construction, reuse, export, and reopen paths.

## High-priority release blockers

### V3R-005: Public research catalogs accept operations that are silently skipped or fail late

`ManagedOperator` exposes a broad catalog, but `_operator_value()` implements only a subset and
ends with `ValueError("managed operator is registered but not executable in this version")`
(`src/persistra/research/component_services.py:1350-1479`). Examples with no execution branch
include downside deviation, return skewness, expected shortfall, turnover, Amihud illiquidity,
volume/trade activity, estimate dispersion, regime threshold, rolling covariance/correlation/
beta, and maximum favorable/adverse excursion.

`AlphaMetricKind` similarly exposes turnover, persistence, decay, autocorrelation, and
categorical/numeric/joint exposure, but `_compute()` silently `continue`s for everything other
than five metrics (`src/persistra/research/alpha_services.py:380-425`). A valid public request
can therefore complete without the requested outputs.

This should be corrected before expanding tests: registration must reject unavailable
capabilities, or every public enum member must have exact execution, state, and golden tests.
Silent omission is never acceptable.

### V3R-006: The event subsystem is a static order replay, not the specified stateful simulator

The public `EventSimulationRequest` accepts only a precomputed tuple of `OrderSpec`; there is no
stateful strategy callback/context, observation visibility surface, command batch, state
schema, forced-order ownership, or strategy checkpoint API. The single final checkpoint is a
content hash, not a resumable state. Event runs expose events/orders/transitions/fills/journal
but have no `result()` and are never published into `results.run_records`, which is keyed only
to `vectorized_simulation_id` (`src/persistra/db/migrations.py:688-697`).

Settlement is always immediate T0 reclassification and is recorded as such in fidelity
(`event_services.py:569-577`), not the effective-dated US settlement contract. Margin
liquidation, financing events, corporate-action entitlements, latency, delay cost, and
checkpoint/resume are also absent from the event path.

Either implement focused spec 13 and publish event output through the common result contract,
or rename and document this as a bounded static bar-order demonstrator.

### V3R-007: Experiment orchestration is planning metadata, and Bayesian search is randomized grid

When `SearchKind.BAYESIAN` is selected, code checks whether Optuna is installed, then shuffles
the Cartesian grid with `random.Random` exactly as random search does
(`src/persistra/experiments/services.py:484-509`). No Optuna study, sampler, objective feedback,
trial state, pruning, or sequential suggestion exists.

Scenario, stress, Monte Carlo, and bootstrap objects are persisted as names/parameters/seeds
but are not executed. Attempts can be manually marked interrupted/resumed/completed, but there
is no worker process, leased read-only worker input, isolated output, verified handoff,
coordinator loop, scheduling policy, cancellation, progress API, or integration with
simulation/analysis. Compatibility reuse is a string-key exception rather than the specified
typed compatibility decision.

Implement the actual execution coordinator and each search/scenario method, or reduce public
claims to deterministic study-plan bookkeeping. In particular, do not expose `BAYESIAN` until
it uses Optuna and objective feedback.

### V3R-008: Results, analyses, and exports cover only a small vectorized subset

The fixed result storage contains only equity, returns, positions, cash, targets, and cost
components (`src/persistra/db/migrations.py:698-759`). The result handle is vectorized-specific
and queries synthetic fills/journal through simulator tables
(`src/persistra/results/services.py:105-239`). It lacks normalized:

- exposures;
- rebalance decisions and trade intents;
- event orders, transitions, fills, and lifecycle events;
- settlements, lots, borrow, margin, corporate actions, and cash flows;
- quality, safety, fidelity, and structured log rows.

Exports include only eight frames and no selected analyses, dependencies, logs, annotations,
schema/engine compatibility facts, or event results
(`src/persistra/results/exports.py:27-36, 47-125`).

Attribution currently reports only net P&L, cost, gross-before-cost, and a hard-coded zero
residual. Execution analysis contains five aggregate rows. Comparison checks only fidelity
tuple equality and execution ID equality. Scenario analysis computes mean/min/max over supplied
metric handles. These are useful initial summaries, but not focused spec 15.

Complete the normalized contract first, then make analysis/export/dashboard consume only that
public contract. Avoid direct joins back into mutable simulator/accounting implementation
tables from `RunHandle`.

### V3R-009: The final flagship and release benchmark are absent

The normative phase plan requires a monthly long-only multifactor strategy using momentum,
earnings yield, profitability, inverse volatility, a point-in-time top-1,000 liquidity
universe, benchmark-relative optimization, sector/tracking-error/turnover/ADV constraints, and
next-open execution. `src/persistra/flagship.py:14-55` instead defines momentum alone, selects
the top half with equal weights, and uses two simple cost parameters.

The research dataset definition itself accepts only `DailyBarInput` and decision role
(`src/persistra/research/models.py:153-193`), so the required fundamentals and broader
canonical inputs cannot yet be assembled through that base definition.

There is no `benchmarks/` directory, `daily_equity_5000x20` module, generator, independent
validator, expected manifest, runbook, telemetry, or scaled smoke evidence. The Makefile also
lacks the specified schema, contract, or benchmark targets.

Implement both artifacts before calling the code release-ready. The formal 24 GiB host result
may remain an external human-controlled gate, but the executable workload and validator must
exist in the repository.

### V3R-010: Validation, forecasting, risk, optimization, and accounting remain narrow slices

- Validation supports expanding, rolling, and combinatorial membership. `NESTED` is rejected,
  and `FinalHoldoutUseId` has no service implementation. There is no sealed holdout
  consumption/contamination ledger or sklearn adapter.
- Only direct linear forecast transforms exist. There is no fitted forecast, preprocessing,
  fit membership, model selection, row-relative release, or forecast combination.
- Risk supports sample/EWMA/fixed shrinkage covariance only. There are no factor/user
  covariance models or exposure contracts.
- Optimization exposes gross/net/max-weight and turnover penalty only. Expected costs, sector/
  factor constraints, tracking error, ADV, per-asset bounds, multi-strategy intent, fallback
  policies, and structured solver failure results are absent.
- The accounting service has strong journal basics but not the full entitlement, lifecycle,
  effective-dated settlement policy, collateral, forced liquidation, or dependency-aware
  correction contract. Both simulators settle fills immediately.

These gaps should be tracked in a normative requirement matrix rather than hidden behind broad
implemented-surface bullets.

### V3R-011: Checked-in CI and clean-extra validation are not release-capable

The primary CI job is currently reproducibly red because it installs insufficient extras.
The package-smoke job tests only `import persistra` from one Python 3.12 wheel
(`.github/workflows/ci.yml:23-31`). It does not test:

- base, research, search, optimize, viz, dashboard, and all extra combinations;
- minimum versus resolved dependency bands;
- namespace import safety and actionable invocation errors in isolation;
- wheel/sdist file contents, license, `py.typed`, CLI, or a base project lifecycle;
- the export/database/browser compatibility matrices.

Create explicit jobs/environments for each capability, merge coverage from required-extra
jobs, and make the ordinary PR workflow pass from a clean checkout.

### V3R-012: Test evidence is far below focused spec 18

The configured threshold is 80% (`pyproject.toml:89-107`), while focused spec 18 requires at
least 90% overall plus reviewed near-complete critical modules. Only one property marker, one
multiprocess marker, and one browser marker are present. There are no marked scenario, fault,
performance, or compatibility tests and only a small set of contract IDs. There is no full
Plans 01-18 traceability matrix.

The Makefile has no `schema-check` or `contracts` target despite the normative plan. Missing
evidence includes:

- temporal, accounting, order, experiment, result, and presentation state machines;
- deterministic variation across process/hash seed/partition/worker count;
- crash/fault injection and prior-or-complete recovery;
- current-schema structural checks independent of migration execution;
- security fuzzing/path/archive/HTML/log-redaction suites;
- minimum/resolved dependency and Python 3.12-3.14 execution evidence;
- database/export/browser fixtures and upgrade/reopen evidence;
- resource/performance trends and the formal benchmark implementation.

Increase coverage only after adding requirement-driven tests; raising the threshold against
the current narrow surface would not establish completeness.

### V3R-013: Public documentation overclaims implementation and is not yet a usable guide

`docs/index.md:12-34` labels the broad surface implemented even where it is only represented by
an enum, table, or narrow slice. Examples include temporal safety, alpha diagnostics,
forecasts, settlement, event simulation, scenarios, normalized results, attribution, and
verified exports. `docs/release-readiness.md:3` calls the implementation release-candidate
code despite the gaps above.

The public guide has only three workflows: reading a preexisting run, rendering a report, and
launching the dashboard (`docs/guide.md:8-81`). It does not show users how to:

- initialize/configure a project and market database;
- register a provider/source/dataset and ingest/remediate/snapshot data;
- create reference entities, calendars, and a point-in-time universe;
- build/enrich a research dataset and use feature/label conformance;
- perform alpha/validation/forecast/risk/optimization workflows;
- run vectorized/event studies, scenarios, exports, and verification;
- understand assumptions, temporal boundaries, settlement/fidelity, or failure states.

There is no API reference navigation, runnable example package, notebook, sample project, or
assumptions-and-limitations guide. The many focused specifications are valuable design records
but are not a substitute for tested user documentation.

Finally, `scripts/check_docs.py:6-27` checks only that seven files exist and two phrases are
present/absent. It does not check docstrings, snippets, imports, internal links, API names,
navigation completeness, or realism-sensitive limitations despite the command being described
as the documentation gate.

### V3R-014: Dashboard backup verification does not match its security contract

The dashboard's backup source checks an optional caller-supplied checksum and verifies only
that the file is a managed research database (`src/persistra/dashboard/source.py:86-125`). It
does not require or validate a Plan-02 copy manifest/checksum marker. The integration test
actually passes the live project research database as a `BackupDashboardSource`.

Require `verify_published_copy()` and a backup/snapshot copy kind before opening a backup
source. Keep the explicit project-source path for live databases. Add tamper, incomplete-copy,
writer-conflict, and symlink/path-identity tests. Also catch `KeyboardInterrupt` in the CLI
launcher so a normal Ctrl-C exits cleanly without a traceback.

### V3R-015: Structured logs are configured but not emitted or exported

`src/persistra/logging.py` defines `configure_logging()` but nothing calls it or obtains a
Structlog logger. The configured project log directory is otherwise unused. Results and
exports have no structured log tables/files, so the specification's persistent diagnostic and
redaction guarantees cannot hold.

Define a bounded event/log schema, initialize it in CLI/library entry points, add stable event
names and safe context at subsystem boundaries, persist run/attempt logs, and include selected
logs in verified exports. Test credential/payload/path redaction.

## Code quality and maintainability opportunities

### V3R-016: Service modules are too large and tightly coupled for the risk they carry

Examples include `catalog/services.py` at roughly 3,359 lines, `market/services.py` at 2,295,
`market/economic_services.py` at 2,169, `db/migrations.py` at 2,106,
`research/component_services.py` at 1,576, and `accounting/services.py` at 1,456. Services
frequently call one another's private methods and the private project connection. This makes
transactions work today, but blurs domain boundaries and encourages integration tests to query
private tables—as the flagship test does for checkpoint evidence.

Refactor by behavior after correctness is locked down:

- Extract pure selection, temporal, accounting, execution, metric, and verification kernels.
- Keep repositories/transactions thin and capability-scoped.
- Introduce typed internal manifests instead of passing unstructured tuples/JSON/string reason
  codes.
- Expose public read models for replay/checkpoint/safety evidence needed by conformance tests.
- Split migrations by immutable step/module while preserving installed checksums.

Do not perform a broad aesthetic refactor before adding the missing golden and state-machine
tests.

### V3R-017: Failure types and validation behavior are inconsistent

Export verification raises generic `ValueError`; report model validation uses generic
`ValueError`; copy operations sometimes raise `FileNotFoundError`; and a registered but
unsupported research operator fails with generic `ValueError`. Other paths correctly use
stable `PersistraError` subclasses and reason codes.

Complete the public error taxonomy, require a stable reason for every public failure, and add a
CLI exception boundary that emits safe structured errors with a nonzero exit code instead of a
traceback.

### V3R-018: Packaging and project metadata need a final consistency pass

- The project metadata and normative specs require Python 3.12+, while `AGENTS.md` says 3.11+.
  Resolve the governance mismatch.
- Classifiers list only Python 3.12 even though 3.13 and 3.14 are declared supported.
- The documentation URL points to the repository root rather than a published documentation
  location.
- Version `2.0.0` is intentionally unchanged until human release authorization; it must remain
  so until the release owner approves the version operation.
- The empty `base` and `static` extras are intentional but should have isolated tests proving
  their exact supported behavior.

## Subsystem readiness matrix

| Area | Assessment | Before-release focus |
| --- | --- | --- |
| Domain primitives | Strong foundation | Add remaining boundary/property cases and governance traceability |
| Project/database/leases/copies | Substantial | Fault/recovery, schema checks, copy-source security, full matrix evidence |
| Catalog/ingestion/snapshots | Substantial but not fully evidenced | Complete provider/resource/state-machine contracts and acceptance traceability |
| Reference and market data | Broad canonical slice | Deepen edge cases, cross-family joins, adjustment/action ambiguity, resource tests |
| Research datasets/SQL/components | Partial | General canonical inputs, full operator catalog, safety propagation, bounded execution evidence |
| Alpha and validation | Partial | Execute every public metric; nested/holdout/adapters/inference/contamination |
| Forecast/risk/portfolio | Early functional slice | Fitted models, causal release, factor risk, costs/constraints/fallbacks, safety |
| Accounting | Strong journal core, partial economic model | Effective settlement, entitlements, margin/liquidation, corrections, state machines |
| Vectorized simulation | Functional narrow vertical | Safety input contract, settlement/action fidelity, recovery/replay public evidence |
| Event simulation | Demonstrator only | Correct event time, callbacks, commands, latency, recovery, forced orders, result publication |
| Experiments/search/scenarios | Planner/state ledger only | Real execution, workers, Optuna, scenario methods, stop/failure policies |
| Results/analysis/export | Partial and one critical defect | Common normalized results, exact metrics, analysis depth, authenticated exports |
| Visualization/reports | Useful vectorized slice | Full families/states, event inputs, accessibility/browser security matrix |
| Dashboard | Working prototype | Verified backups, true page semantics, browser/accessibility/security tests, clean shutdown |
| Packaging/CI | Not release-ready | Fix clean CI, extras/minimum/matrix/package smoke jobs |
| Documentation | Design-rich, user-poor | Accurate status, end-to-end guides, API reference, runnable examples, limitations |
| Benchmark/release evidence | Absent | Implement generator/validator/runbook and evidence ledger |

## Recommended remediation sequence

### 1. Establish an honest release baseline

- Change the implementation status from release candidate to preview/incomplete.
- Create a machine-readable Plans 01-18 requirement matrix with one of: implemented and tested,
  intentionally revised, deferred with public removal, or release-blocking.
- Decide explicitly whether the full normative design is still the v3.0 contract. If not,
  revise specifications and remove public symbols/claims rather than shipping placeholders.

### 2. Fix correctness and trust boundaries

1. Authenticate and harden every portable export format.
2. Replace the provisional metric engine with exact versioned definitions and golden tests.
3. Correct the event clock, bar visibility, horizon validation, and accounting timestamps.
4. Implement end-to-end safety/lineage enforcement and taint propagation.
5. Reject every registered-but-unimplemented operator/metric/search kind until implemented.

### 3. Complete the end-to-end contracts

- Publish vectorized and event simulations through one normalized result schema.
- Complete stateful event execution and effective-dated accounting integration.
- Complete validation/holdout, fitted forecast/risk/optimization, and study worker/search/
  scenario workflows.
- Implement the final multifactor flagship entirely through public APIs.
- Implement the exact benchmark generator, independent validator, runner, and runbook.

### 4. Build release evidence

- Add schema/contracts targets, requirement IDs, state machines, fault/concurrency/security
  suites, and compatibility fixtures.
- Reach at least 90% branch-aware coverage with near-complete critical modules.
- Fix CI and add isolated extras, minimum/resolved dependency, Python 3.12-3.14, wheel/sdist,
  browser, and export/database matrix jobs.
- Record a reproducible release evidence ledger rather than a prose checklist alone.

### 5. Make the product usable and accurately documented

- Add tested setup, ingestion, research, validation, portfolio, simulation, study, analysis,
  export, report, and dashboard guides.
- Generate an API reference from the actual public namespaces.
- Add a small sample project and runnable examples that require no private APIs.
- Publish assumptions and limitations for every realism-sensitive feature.
- Make documentation checks execute snippets and verify links, imports, nav, and API names.

## Proposed release gate

V3 should become eligible for final human release review only when:

- all critical and high findings in this review are closed or the relevant public contract is
  explicitly removed/revised;
- no public enum or request silently skips or late-fails as an unimplemented capability;
- portable artifacts reject all identity/provenance/closure tampering;
- the exact metric catalog and event timing contracts pass independent goldens;
- unsafe/label/retrospective lineage cannot be laundered into any simulation or export;
- the final flagship and executable benchmark artifacts exist and reproduce;
- clean CI passes every supported Python/extras/dependency job;
- focused spec 18 traceability, fault/state-machine/security/coverage gates pass;
- user documentation describes only implemented behavior and its limitations; and
- the human release owner separately authorizes versioning, build, tag, push, and publication.

Until then, the current implementation is best described as a substantial v3 foundation and
integrated preview, not a full v3 release candidate.
