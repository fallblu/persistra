# Focused specification 18: testing, conformance, properties, and the 24 GiB benchmark

**Status:** Implementation-ready draft  
**Umbrella:** [`../v3-spec.md`](../v3-spec.md)  
**Primary owners:** `tests/`, `benchmarks/`, `scripts/fixtures/`, `scripts/checks/`  
**Required before:** v3 implementation and release acceptance  
**Last reviewed:** 2026-07-16

## 1. Purpose and relationship to the umbrella specification

This specification defines the verification architecture for all Persistra v3 contracts. It
fixes test layers, deterministic fixture ownership, extension conformance suites, temporal and
financial goldens, Hypothesis property/state-machine testing, fault/recovery testing, optional
dependency and compatibility matrices, documentation checks, coverage, performance evidence,
and the exact release-gating 24 GiB workload.

Plans 01–17 remain normative. This plan tests them; it cannot relax identity, temporal safety,
accounting, execution, reproducibility, result, visualization, or dashboard semantics to make
a suite or benchmark pass.

## 2. Scope

### 2.1 In scope

- Repository test taxonomy, markers, fixture packages, seeds, clocks, and isolation
- Unit, integration, contract, scenario/golden, property/stateful, migration, documentation,
  optional-install, security/accessibility, compatibility, fault, and performance tests
- Public conformance kits for provider and research/execution/analysis extensions
- Cross-plan invariant registry and minimized-regression workflow
- Deterministic textual source fixtures and generated sample DuckDB databases
- Supported Python/Linux/runtime-extra/DuckDB/export/browser matrix ownership
- Ordinary CI versus controlled release-gate separation
- Exact 5,000-active-instrument, 20-year, ten-feature, monthly simulation memory workload
- Cold-cache `/usr/bin/time -v` protocol, result manifest, regression triage, and acceptance

### 2.2 Out of scope

- Weakening a hard contract because a third-party dependency is difficult to test
- Network-dependent tests in the default/release deterministic suites
- Opaque committed multi-gigabyte fixture databases when deterministic generation is possible
- Using wall-clock microbenchmarks from shared CI as hard release thresholds
- Treating coverage percentage as proof of correctness
- Pixel-only screenshot testing as visualization authority
- Benchmarking distributed execution, market replay, Windows, hosted dashboard, or static
  rendering as part of the 24 GiB memory gate
- Publishing packages, releases, benchmark artifacts, or fixture data automatically

## 3. Normative decisions

1. Every normative requirement has at least one mapped test ID before its implementation
   checkpoint is complete. The requirement matrix is generated and fails on orphaned normative
   sections, missing tests, duplicate IDs, or stale links.
2. Tests use public APIs unless explicitly testing a private pure unit. End-to-end, conformance,
   docs, dashboard, and compatibility suites never depend on private SQL/table names.
3. Time, IDs, seeds, filesystem roots, environment, locale, and timezone are injected/fixed.
   Tests do not depend on current date, host timezone, unordered iteration, or ambient random
   state.
4. Fixture facts are deterministic text/config/code plus content manifests. Generated DuckDB/
   Parquet/HTML files are test outputs or separately versioned compatibility fixtures, not
   casually committed opaque data.
5. Hand-worked golden fixtures are authoritative for finance/accounting/timing examples.
   Golden output is reviewed as semantic typed data; snapshot updates require an explicit
   reason and cannot mask an unexplained behavior change.
6. Hypothesis generates valid and invalid sequences around invariants. Shrunk failures are
   automatically reproducible by seed/example; semantically valuable counterexamples become
   named permanent regression fixtures.
7. Stateful tests assert invariants after every accepted/rejected transition, not only at
   terminal state. A rejected operation proves no forbidden partial state.
8. Fault injection enumerates every staged transaction/checkpoint/write/rename/handoff boundary.
   The suite proves prior-or-complete visibility and recovery, not merely a raised exception.
9. Conformance suites are versioned public contracts. Passing a base protocol type check alone
   is insufficient; extensions must pass timing, safety, determinism, resource, schema,
   idempotency, failure, and lineage cases applicable to their capability.
10. Tests do not phone home or require credentials. Provider network tests use recorded licensed-
    appropriate protocol fixtures or are explicitly manual/non-gating outside deterministic CI.
11. Optional extras have install/import/capability tests in clean environments. Base must not
    import optional dependencies. Required extras are release-gating; optional static output is
    tested when present but does not gate 3.0.
12. Migration and export compatibility fixtures are immutable small golden files only where
    native byte-format testing requires them. Each has license/source/generator/version/checksum
    and supported-reader retirement policy.
13. Branch coverage is the project gate: at least 90% overall for implemented v3 before release,
    with near-complete meaningful branch coverage for identity/canonical hashing, temporal
    selection/safety, ingestion atomicity, accounting, orders, reuse, publication, and export.
14. Mutants/manual fault review target critical invariants; achieving a number never replaces
    missing semantic tests. Exclusions are narrow, reviewed, and documented.
15. Ordinary CI runs deterministic correctness, docs, schema, optional smoke, and a non-gating
    performance smoke. The hard memory gate runs only on a controlled Linux benchmark host.
16. The release memory target is peak resident set size at or below 24 GiB for the exact
    workload in section 14, with no swap and a cold operating-system/DuckDB cache.
17. Benchmark fixture generation is a separate verified step. The measured workload starts
    from the completed immutable raw/reference database and includes dataset/feature/universe/
    portfolio/vectorized simulation/accounting/result publication described below.
18. The benchmark uses one Python process and DuckDB internal threads; local study workers are
    disabled. Peak RSS reported by `/usr/bin/time -v` therefore covers the measured process.
19. Benchmark parameters, input/output roots, plans, runtime, query plans, spill, database sizes,
    hardware/kernel/libraries/settings, and measurement method are recorded. A lone RSS number
    is invalid evidence.
20. A benchmark failure blocks release acceptance but authorizes no automatic code, test,
    fixture, threshold, or version change. Investigation identifies regression versus invalid
    environment/fixture before a human-approved correction.
21. Performance optimization cannot introduce sampling, hidden truncation, unsafe temporal
    behavior, altered numeric policy, unverified approximation, or weaker artifact completeness.
22. All test tools and benchmark scripts have bounded resources and cleanup ownership. Failed
    tests preserve only declared diagnostic artifacts and never delete user data.

## 4. Repository structure and test IDs

```text
tests/
├── unit/
├── integration/
├── contracts/
│   ├── providers/
│   ├── research_components/
│   ├── execution_policies/
│   ├── accounting_policies/
│   ├── analysis_components/
│   └── presentation/
├── scenarios/
│   ├── temporal/
│   ├── accounting/
│   ├── execution/
│   ├── experiments/
│   └── results/
├── properties/
├── stateful/
├── faults/
├── migrations/
├── compatibility/
├── documentation/
├── security/
├── accessibility/
├── optional/
├── performance/
└── fixtures/
    ├── source/
    ├── expected/
    ├── manifests/
    └── builders/
benchmarks/
├── datasets/
├── research/
├── simulation/
├── manifests/
└── results/
scripts/
├── fixtures/
└── checks/
```

Normative test IDs use `V3-P<plan>-<section>-<slug>`, for example
`V3-P13-7-IOC-PARTIAL-CANCEL`. Tests declare one or more IDs through a marker. The generated
matrix records plan/section/requirement text hash, test path/node ID, layer, extras/platform,
fixture IDs, and last observed outcome. Text-hash change requires review, not automatic relink.

Pytest markers are `unit`, `integration`, `contract`, `scenario`, `property`, `stateful`,
`fault`, `migration`, `compatibility`, `docs`, `security`, `accessibility`, `optional`,
`performance_smoke`, and `benchmark_gate`. Unregistered markers fail. `benchmark_gate` never
runs as part of `make test`.

## 5. Deterministic test environment

Default tests set UTC host/process timezone where supported, locale `C.UTF-8`, fixed injected
clock, repository fixture UUID namespace, named Plan-01 seeds, one-thread math/solver defaults
unless testing parallel invariance, no network, and temporary project roots. Environment
variables are scoped by fixtures and restored.

Every test gets a fresh project/database or an immutable shared fixture opened read-only.
Writable fixtures cannot be session-shared. Test cleanup checks Plan-02 ownership manifests;
it never recursively deletes an unowned path. Subprocess tests use bounded timeout, sanitized
environment, captured structured logs, and process-group cleanup.

Randomized tests record master seed, namespaced draw key, Hypothesis seed/example database
artifact, dependency versions, and failing canonical input. Repetition under the recorded
environment must reproduce semantic roots. Nondeterminism tests intentionally vary hash seed,
insertion/order, chunks, thread/worker counts, and locale/timezone.

## 6. Fixture architecture

### 6.1 Fixture identities

Every fixture has qualified name/version, canonical definition content ID, generator version/
code root, seed manifest, expected schema/count/root manifest, safety/licensing classification,
and applicable plans/tests. Builders use deterministic Plan-01 fixture IDs and clocks; production
identity algorithms are not replaced by UUID5.

Small source data are UTF-8 CSV/JSON/JSONL/TOML/YAML only where the owning parser supports it.
Expected finance outputs use canonical JSON/CSV with decimal text, UTC instants, IDs, state,
reasons, and tolerances. Golden native DuckDB files are limited to migration/export/storage
compatibility and generated by a pinned script/environment.

### 6.2 Core fixture families

- calendars: DST, holiday, early close, halt, settlement T+3/T+2/T+1 boundaries;
- revisions: late/corrected/unknown-publication/project-cutoff/quarantine/remediation;
- identifiers/universes: reuse, gaps, mapping conflicts, lifecycle, point-in-time membership;
- market/fundamental/estimate/macro/rate/action: exact availability and amendment cases;
- datasets/features/labels: dual cutoff, overlapping intervals, direct/transitive label and
  retrospective roots, opaque/custom conformance, fitted-release proofs;
- validation/portfolio: purge/embargo/nested holdout, expected costs, fallback/failure,
  long-only/long-short constraints and current-state construction;
- accounting: opening, fills, fees, lots, settlement, cash flows, accrual, borrow/recall,
  margin, actions/fractions/basis, missing marks, rebuild/reconciliation;
- simulation/orders: next-open projection, same-close warning, capacity, ambiguity, all order
  types/TIF/transitions, partial/cancel/replace, forced orders, equivalence, resume;
- experiments/results: identities/reuse, workers, search/scenarios, publication, metrics,
  attribution, comparison, export/upgrade/reference retention;
- presentation: deterministic figures, warnings/reduction, HTML/CSP/XSS/accessibility, dashboard
  read-only/cache/writer conflict; and
- flagship end-to-end workflow covering every public layer without notebook/private logic.

### 6.3 Sample project

The documented sample database is generated from small textual fixtures through public APIs.
The generator verifies manifests, can reproduce byte-independent logical roots, and writes to
an ignored build directory. Docs/tests regenerate or use a checksum-verified cached copy. A
checked-in opaque sample database is forbidden unless native compatibility itself is tested.

## 7. Test layers

### 7.1 Unit and component integration

Unit tests cover pure validation, canonicalization, hashes, numeric/time operations, policy
decisions, formulas, transitions, and render models without DuckDB when possible. Integration
tests cover migrations, repositories, transactions, attachments/leases, bounded partitioning,
simulators, worker handoff, result publication, analysis, export, and presentation through
public services.

SQL schema tests create every migration from zero, inspect exact columns/types/constraints/
indexes/views, apply every supported upgrade path, reopen read-only/read-write as appropriate,
and reject unknown/newer/partially applied state. SQL snippets in focused specs are parsed or
executed against the owning migration dialect where they are normative.

### 7.2 Scenario and golden tests

Scenario fixtures are small enough for independent hand calculation and show each state before
and after an operation. Accounting goldens balance general/memorandum USD and quantity
commodities, lots, settlement, NAV, and P&L. Temporal goldens list every candidate observation
and why it is included/excluded. Execution goldens list path ambiguity/capacity/cost/accounting.

Numeric assertions use exact decimal equality until a plan explicitly uses float; float tests
use definition-owned absolute/relative/ULP tolerance and reject NaN/infinity except structured
unavailable display. No repository-wide approximate default hides drift.

### 7.3 Documentation tests

Public API snippets execute in isolated projects with the extras they declare. `no-run` blocks
are syntax/type checked when possible. Link/nav/reference/test-ID checks run on every docs
change. Strict MkDocs treats warnings as failures except explicitly approved tool advisories.
Notebooks are nonauthoritative and run in scheduled/manual CI from fresh fixtures.

## 8. Extension conformance suites

Each suite is a public pytest-style kit with versioned case manifest, fixture factories,
capability adapter, expected structured outcomes, and machine-readable report. Extensions
declare the highest suite version passed; core rejects incompatible versions.

Required suites are:

| Suite | Mandatory coverage |
| --- | --- |
| Provider | identity, schema, availability, revisions, pagination, idempotency, quarantine, credentials/redaction, rate/retry, licensing |
| Research component | role separation, exact inputs/outputs, bounded execution, temporal sentinels, label/retrospective prohibition, conformance, lineage, determinism |
| Splitter/validator | interval hulls, entity/group/panel purge, embargo, nested/holdout audit, invalid folds, deterministic membership |
| Portfolio component | point-in-time forecasts/state, units, constraints, solver verification, fallback/failure, expected-versus-realized cost separation |
| Accounting policy | typed decisions only, posting templates, balance, idempotency, correction dependency, precision, rebuild/reconciliation |
| Execution policy | visibility, latency, order/TIF transitions, ambiguity, shared capacity, evidence class, cost overlap, borrow/margin, determinism |
| Search/scenario | typed bounded space, seed isolation, completion-order invariance, safety/timing, preserved/destroyed dependence, failure/stop |
| Metric/attribution/comparison | requirements/units/unavailable, golden formula, reconciliation, evidence, compatibility, identity/version |
| Plot/report | public inputs, no finance calculation, deterministic semantic JSON, unavailable/warnings, reduction, security/accessibility/offline closure |
| Dashboard | optional import, read-only public APIs, source/lease/cache roots, zero writes, loopback security, page semantics/resources |

Unknown/opaque custom code can run only under the owning unsafe policy and does not claim
conformance. A conformance pass is tied to exact component code/dependency/config and expires
when any material identity changes.

## 9. Property and state-machine testing

### 9.1 Domain, temporal, and data properties

- identity wire/storage round-trip, cross-kind inequality, canonical hash stability, and no
  UUID business ordering;
- time normalization/half-open intervals/DST/date policy and fixed-precision arithmetic,
  quantization, currency mismatch, overflow, and negative-zero normalization;
- append-only revision selection monotonic with knowledge cutoff, stable snapshots, unknown
  publication bounded by ingestion, and public/project cutoff separation;
- ingestion atomic groups/dispositions/quarantine/remediation/idempotency under faults;
- identifier/universe interval nonoverlap and as-of membership stability;
- temporal join never selects a value unavailable at the row cutoff;
- direct/transitive label/retrospective roots and unreleased fits never reach decision contexts,
  including custom/materialized/workspace/SQL paths; and
- partition/chunk/thread/order changes preserve logical roots for replay-eligible components.

### 9.2 Accounting state machine

Generated operations combine deposits/withdrawals, buys/sells/cross-zero legs, partial fills,
fees, settlement, interest/borrow accrual, locate/use/return/recall, margin evaluations/forced
intents, splits/dividends/mergers/delistings/fractions/corrections, marks, snapshots, rebuild,
and failure injection. After every step:

- journal sequences are gap-free and sources idempotent;
- each general/memorandum transaction balances exact USD and quantity commodities;
- no posting/account balance is silently edited and reversals/dependencies are legal;
- FIFO long/short lot quantity/basis/realized P&L and position projections reconcile;
- settled/unsettled/available/restricted/receivable/payable/accrual balances conserve;
- borrow authorization/open/recalled/returned state matches short inventory;
- margin/collateral/NAV count each economic value once;
- actions/entitlements/fractions conserve configured economics or remain blocked; and
- snapshots rebuild to identical projections; mismatch never publishes a portfolio state.

### 9.3 Order/event state machine

Generated sequences include market/status/action/settlement/accrual events, callbacks,
submissions, acceptance/activation, triggers, partial fills, cancel/replace races, TIF expiry,
latency, capacity, recall/margin forced orders, interruption/resume, and horizon. Invariants are:

- total priority/stable sequence and closed strategy-visible prefix;
- only legal immutable status transitions; status remains distinct from fill progress;
- cumulative fill plus remaining equals original quantity and never overfills;
- FOK has zero or complete fill, IOC cancels remainder in the same cycle;
- replacement parent history is retained and child quantity is explicit;
- capacity is allocated once across competitors and never claims queue evidence;
- fill/cost evidence and Plan-11 accounting source trace exactly once;
- forced ownership cannot be cancelled/replaced and cannot invent liquidity;
- Plan-12 synthetic fills have no order status/remainder; and
- checkpoint resume equals uninterrupted semantic roots while failed retry uses new IDs.

### 9.4 Experiment/result/presentation state machines

Generated study/worker/publication/analysis/export/report/dashboard operations assert exact
identity/reuse, compatible original identity/warning, deterministic planning independent of
completion, complete outcome counts, isolated worker writes, staged atomic publication,
immutable runs/analyses/reports, reference-safe retention, export closure/upgrade, figure
semantic determinism, HTML security, dashboard cache-root correctness, and zero dashboard
writes after every transition.

## 10. Fault, concurrency, and recovery testing

A shared fault injector names transaction boundaries rather than source line numbers. Every
multi-stage plan enumerates pre-write, staging, per-chunk, validation, manifest, event, commit,
fsync, close, handoff, copy, register, and rename boundaries. Each injected failure verifies
visible database/files, leases, next retry/resume, cleanup ownership, and structured reasons.

Concurrency suites use deterministic barriers, not sleep races, for:

- shared/exclusive lease conflicts, stale-owner proof, and DuckDB lock interaction;
- concurrent idempotent ingestion/materialization/accounting requests;
- study workers reading immutable market members and writing isolated files;
- completion-order-independent Bayesian/stop/merge results;
- duplicate/conflicting worker handoff/publication/reuse;
- annotation optimistic revisions and archive/delete reference races; and
- dashboard read/query/cache behavior when a writer is active or begins between scopes.

Repeated stress runs are diagnostic; at least one barrier-controlled proof covers every race.
Tests never force-kill or clean resources outside their owned temporary fixture.

## 11. Compatibility and optional-install matrices

### 11.1 Platform/runtime matrix

Release CI covers every supported Python minor on Linux, minimum and resolved dependency sets,
and base, `research`, `search`, `optimize`, `viz`, `dashboard`, `all`, plus `static` when
available. macOS is best-effort non-gating; Windows remains unsupported. Import tests inspect
loaded modules to catch optional dependency leakage.

Solver/search/Plotly/Streamlit/DuckDB lower bounds are exercised in clean environments.
Dependency upgrades run deterministic semantic roots and conformance suites before constraint
changes. No test silently installs a missing extra into the base job.

### 11.2 Database/export matrix

For every still-supported database/export format, fixtures record Persistra schema, creating
Persistra/DuckDB/storage versions, required extensions, logical roots, file checksum, reader
range, and retirement release. Tests open read-only with every declared current reader, migrate
by verified copy into a new file, recheck logical roots/public APIs, and leave source bytes.
Unsupported forward/corrupt/extension files fail with guidance before mutation.

### 11.3 Browser/dashboard matrix

Plan-16 standard HTML is tested offline in the current supported headless browser baseline and
one prior supported baseline; semantic DOM/manifest/Plotly JSON, CSP/network, accessibility,
and interactions are authority. Plan-17 uses framework-native app tests plus one headless
loopback smoke. Browser/static version changes do not rewrite finance goldens.

## 12. Coverage and quality gates

The standard pre-commit/checkpoint gate remains:

```text
make lint type test
make docs-check        # whenever docs/docstrings change
make docs-build        # strict documentation checkpoints/release
```

V3 implementation adds `make schema-check`, `make contracts`, and controlled matrix jobs while
keeping the existing commands authoritative. Coverage is measured with branch coverage over
the supported base test job plus merged required-extra reports. Generated migrations/fixtures,
vendored assets, and trivial type-only declarations may be excluded only by reviewed config.

Critical module reports list uncovered branches with an owner/test plan. A release cannot meet
90% overall by heavily testing presentation while leaving temporal/accounting/order branches
below their reviewed near-complete targets.

Flaky tests are bugs. Quarantine requires issue/owner/expiry/reason, stays visible, and cannot
cover a release-critical invariant or be excluded from the release gate indefinitely.

## 13. Performance suites outside the memory gate

Non-gating suites track ingestion throughput, temporal joins, feature materialization, alpha/
validation, optimization, accounting events, vectorized/event simulation, experiment scaling,
publication/analysis/export, Plotly/report, and dashboard query/render. Each uses versioned
fixtures and records runtime/RSS/I/O/spill/query plans. Shared CI trends are informational.

Controlled performance regressions use multiple iterations after a separate warmup, robust
statistics, fixed CPU governor/affinity where supported, and reviewed thresholds. Event-
simulation throughput and local parallel scaling are separate from the memory gate and cannot
change its fixture/settings.

## 14. Versioned 24 GiB release benchmark

### 14.1 Benchmark identity and measured boundary

The workload is `persistra.benchmark.daily_equity_5000x20@1`. Its semantic manifest includes
every generator/query/policy/schema/settings fact below. Any change creates `@2`; historical
results are not compared across semantic versions as if identical.

Fixture generation creates and verifies an immutable market/reference database before the
measured command. Generation time/RSS are reported separately. The measured command creates a
fresh research project/database, attaches the fixture read-only, builds the exact research
dataset/features/universe, runs the portfolio/vectorized simulation/accounting, publishes the
result, verifies roots, and exits. It excludes docs, plots, reports, dashboard, static export,
and study workers.

### 14.2 Calendar, instruments, and universe churn

- Venue/calendar: `XNYS`, sessions from `2005-01-03` through `2024-12-31` inclusive under the
  exact pinned Plan-04 calendar release; the manifest records the resulting session count/root.
- Active universe: exactly 5,000 instruments at every ordinary session close.
- Initial instruments: ordinals `1..5000`; fixture symbols are display-only `B000001` etc.
- Churn: at the first session of each calendar quarter starting 2006 Q1, the 50 lowest active
  instrument ordinals not previously removed leave after prior close and 50 new ordinals enter
  at that session open. Total instruments and every effective interval are recorded.
- Issuer/security/listing/instrument/venue IDs use deterministic fixture namespace keys. Terms
  are USD common equity, price quantum USD 0.000001, quantity quantum 0.000001 share, round lot
  100 shares, `whole_share_default=false`, contract multiplier one, and the exact benchmark
  settlement policy below.
- Sectors: 10 sectors assigned by `(instrument_ordinal - 1) mod 10`, effective with listing.

The research universe at each session is point-in-time active membership, not survivorship-
backfilled. Churn replacements have no fabricated pre-entry history.

### 14.3 Raw daily bars and actions

The seed is integer `20250300`. For every ASCII stream label and tuple of integer/string parts,
`H(label, parts...)` is the unsigned big-endian integer in the first eight bytes of SHA-256 over
the Plan-01 canonical JSON bytes of
`["persistra.benchmark.daily_equity_5000x20@1", 20250300, label, parts...]`.
`U = (H + 0.5) / 2^64` and `D = 2U - 1` are evaluated with decimal precision 80. There is no
ambient PRNG state. Quarter/year selections sort by `(H(label, period, instrument_ordinal),
instrument_ordinal)`. Hash-derived indices are zero-based; prose such as “session 6” means the
sixth actual XNYS session, one-based. These rules make generation partition/order independent
and are duplicated in an independent validator, not inferred only from the generator
implementation.

For active instrument ordinal `i`, global session ordinal `t`, and sector `s`, define
`r = 0.0002 + 0.004*D("common", t) + 0.003*D("sector", s, t) +
0.020*D("idio", i, t)`. Before the first active session, the unrecorded anchor close is
`20 + (i mod 180)` USD. Thereafter, with prior raw close `p`, same-open split ratio `q` (new
shares per old share, otherwise one), `base = p/q`, raw
`open = base*exp(0.25*r + 0.003*D("gap", i, t))`, and raw
`close = base*exp(r)`. Raw `high` is `max(open, close)*exp(0.004*U("high", i, t))`; raw `low`
is `min(open, close)*exp(-0.004*U("low", i, t))`. Each is rounded half-even to USD 0.000001,
then high/low are expanded by one price quantum if rounding would fail to bound open/close.
Volume is `100 * max(1, floor(((10_000 + 200*(i mod 5000)) *
(0.5 + U("volume", i, t))) / 100))` shares. OHLC validation uses these stored values; rows
selected missing below are omitted only after generation so the recurrence and later roots do
not depend on absence. No provider/network access occurs.

This is a bounded uniform-shock synthetic process, not a market-realism claim. It preserves
positive raw prices, persistent liquidity dispersion, split discontinuities, and exact
Plan-05 price/quantity quanta. Validation must pass without disabling plausibility checks;
synthetic origin remains visible.

Deterministic special cases are:

- isolated missing bar when `H("isolated", i, t) mod 10_000 = 0`;
- in each calendar year, rank instruments active for every session of that year by
  `H("block-member", year, i)` and take the first 50; each gets one five-session missing block
  beginning at
  `H("block-start", year, i) mod (year_session_count - 4)`, so it cannot overlap entry/exit;
- each quarter, rank instruments active at its first session by
  `H("split-member", quarter, i)`, take the first 10, declare after session 1 close, and apply
  at session 6 open an alternating 2-for-1 (`q=2`) or 1-for-2 (`q=0.5`) split according to
  zero-based global quarter ordinal from 2005 Q1 (even is 2-for-1); ex/effective/record are
  session 6 and Plan-05 availability is the declaration instant;
- each quarter, independently rank active instruments by
  `H("dividend-member", quarter, i)`, take the first 500, and declare after session 1 close a
  cash dividend of the declaration close times
  `(0.001 + 0.004*U("dividend-rate", quarter, i))` rounded half-even to USD 0.000001 per
  pre-split share, with ex-date session 11, record date session 12, payment date session 21,
  and Plan-05 availability at the declaration instant; and
- each churn exit is announced after the prior close and resolves at the next session open for
  cash equal to its prior raw close times `(0.9 + 0.2*U("delisting", quarter, i))`, rounded
  half-even to USD 0.000001, so accounting never invents zero.

Missing rows remain absent with explicit status/quality fixture records. Splits/dividends/
delistings are raw canonical actions processed by Plans 05/11; prices are never pre-adjusted.
If a named action session exceeds the sessions available in a holiday-shortened quarter, the
ordinal refers to that quarter's actual XNYS sessions; every quarter in the fixed range has at
least 21. Multiple independently selected actions on one instrument are retained and applied
in Plan-13 priority order; the manifest records every selected ordinal and term.

### 14.4 Research dataset and ten features

The dataset has one row per active instrument/session after point-in-time universe selection,
including explicit noncomputed states for missing inputs. It selects raw close/volume, action
adjustment capability for research returns, sector, and membership under public-information
cutoff at that session's canonical close availability. Project-knowledge cutoff is fixed to the
fixture completion and introduces no moving ingestion advantage.

The exact Plan-08 registered instances, with minimum full windows, are:

1. `return_1d`: `persistra.feature.simple_return(k=1)` over split-adjusted close;
2. `return_5d`: `persistra.feature.simple_return(k=5)` over split-adjusted close;
3. `momentum_21d`: `persistra.feature.momentum(lookback=21, skip=0)` over split-adjusted
   close;
4. `momentum_126d_skip5`: `persistra.feature.momentum(lookback=126, skip=5)`, exactly
   `(split_adjusted_close[t-5] / split_adjusted_close[t-126]) - 1`;
5. `momentum_252d_skip21`: `persistra.feature.momentum(lookback=252, skip=21)`, exactly
   `(split_adjusted_close[t-21] / split_adjusted_close[t-252]) - 1`;
6. `realized_volatility_21d`: `persistra.feature.realized_volatility(window=21,
   return_kind=log, annualization_factor=252, minimum_valid=21)`, the sample standard
   deviation of the exact 21 one-session log returns times `sqrt(252)`;
7. `realized_volatility_63d`: the same registered operator with `window=63` and
   `minimum_valid=63`;
8. `mean_dollar_volume_21d`: `persistra.feature.volume_activity(field=dollar_volume,
   reducer=mean, window=21, minimum_valid=21)`, with dollar volume exactly raw
   `close * volume` in USD;
9. `cross_sectional_percentile_momentum_126`:
   `persistra.feature.cross_sectional_rank(input=feature_4, direction=ascending,
   output=percentile)` within the exact active eligible cross-section, using
   `(average_tie_rank - 1) / (n - 1)` and the Plan-08 singleton rule; and
10. `sector_zscore_momentum_126`: `persistra.feature.cross_sectional_zscore` of feature 4
    independently within each exact point-in-time sector group, with population standard
    deviation and `minimum_count=20`; it is unavailable for lower count or zero dispersion.

Any missing required window value makes features 1–8 noncomputed for that row; features 9–10
use only computed feature-4 rows and retain exact coverage/denominator/state. Feature order,
definitions, float/numeric policy, output schema/count/chunk/root, and query plans are recorded.

### 14.5 Monthly universe selection and portfolio

Decisions occur after the last completed XNYS session close of each calendar month from the
first month with a complete 252-session lookback through December 2024. At each decision:

1. candidates are exact active members with computed close, feature 8, and feature 5;
2. rank descending by feature 8, tie by instrument ID bytes;
3. select exactly the first 1,000 when available; a lower count fails the benchmark; and
4. target equal risky weight `0.001` for each selected instrument and zero for other held
   instruments, with residual cash only from execution/rounding/economics.

No label or fitted model is used. The strategy/constructor is registered, causal,
partition-invariant, and exact. Opening capital is USD 10,000,000 at the first decision
predecessor boundary.

### 14.6 Vectorized simulation, accounting, and results

- Simulator: Plan 12 next-session-open fractional synthetic execution.
- Reference: exact field-restricted raw open; current-session high/low/close/volume hidden.
- Quantity: fractional to 1e-6 shares; execution-NAV target conversion.
- Rebalance: every scheduled decision, no threshold/buffer/minimum suppression.
- Capacity: causally available 21-session lagged ADV, maximum 10% participation; clipped
  remainder expires as vectorized shortfall.
- Costs: constant 5 basis points one-way embedded slippage, zero spread/impact/delay,
  commission USD 0.005/share with USD 1 minimum per synthetic fill, zero regulatory fee.
- Short/borrow/margin: long-only; normal Plan-11 cash feasibility and simplified policy remain
  enabled but no synthetic credit/unlimited borrow.
- Settlement/actions/accrual: exact effective-dated US cycle, generated actions/delistings,
  zero financing/cash rate, no external flows after opening.
- Marks: raw close at completed sessions, exact missing/stale policy with maximum five eligible
  sessions; unresolved required final mark fails rather than inventing zero.
- Sampling: each session close plus every flow/action/settlement boundary; exact flow-split
  returns, accounting snapshot/reconciliation at each decision and final boundary.
- Result: Plan-15 lossless publication of the completed isolated artifact into a fresh research
  database and full logical-root/reconciliation verification.

No checkpoint resume, event simulator, study worker, compatible reuse, analysis metric, plot,
report, export, or dashboard is part of the measured path.

### 14.7 Fixed runtime environment and command

The controlled release host is dedicated Linux x86-64 with at least 32 GiB physical RAM, swap
disabled, no cgroup/container memory overcommit, local SSD temp/output, fixed performance CPU
governor, and no unrelated user workload. The manifest records machine model, CPU/microcode,
RAM, storage/filesystem, kernel, libc, Python, Persistra commit/dirty root, DuckDB and every
dependency, and environment.

DuckDB settings are exactly: 4 threads, memory limit 16 GiB, one clean dedicated temp directory
with at least 100 GiB free, explicit stable insertion-order-independent queries, and no remote
extensions. BLAS/math threads are one. Persistra partition size is 100,000 rows unless an owning
plan requires a smaller fixed batch; every effective limit is recorded.

After reboot, fixture checksum verification is performed with direct I/O or before the cache-
cold point under the controlled runbook. The operator then establishes cold cache by the
approved host procedure, verifies swap remains zero and no prior benchmark process, and runs
exactly once:

```text
/usr/bin/time -v uv run python -m benchmarks.daily_equity_5000x20 \
  --fixture <verified-fixture-path> \
  --output <new-empty-output-directory> \
  --manifest benchmarks/manifests/daily_equity_5000x20-v1.json
```

The shell/runner does not pipe output through another process. The benchmark module refuses a
nonempty output, wrong fixture root, warm-run marker, enabled swap, wrong thread/memory/temp
settings, missing `/usr/bin/time` parent evidence, active unrelated worker marker, dirty
unrecorded code, or incompatible environment. Repetition requires another cold-cache cycle and
is a new recorded attempt, never averaged invisibly.

### 14.8 Measurement and pass criteria

The primary value is `/usr/bin/time -v` `Maximum resident set size`, converted from KiB and
required to be `<= 25,769,803,776` bytes (24 GiB). The manifest also records wall/user/system
time, exit status, page faults, filesystem I/O, DuckDB peak/spill/temp metrics, phase-level
high-water telemetry when nonintrusive, input/output/temp peak sizes, row counts, and query
plans.

Pass requires:

- exit zero and primary peak RSS at or below the byte threshold;
- exact fixture, dataset, ten-feature, universe, decision, target, fill/shortfall, journal,
  accounting, equity/return, result-table count and content roots matching the reviewed
  expected manifest;
- no swap use, OOM, sampling, truncation, skipped decision, unsafe override, reconciliation
  mismatch, hidden retry, or undeclared spill/settings change;
- cold-cache/environment/runbook attestation complete; and
- result database/public API reopen and final manifest verification after process exit.

An invalid environment/manifest/root produces `invalid`, not pass/fail. A semantically correct
run above memory threshold is `failed_memory`. A lower-memory run with wrong roots is
`failed_correctness`. Both block release acceptance.

## 15. Benchmark artifacts and regression process

The runner emits canonical JSON environment/workload/result manifests, `/usr/bin/time` text,
structured phase metrics, query plans, schema/count/root report, and safe logs. Artifacts are
checksummed and stored in the controlled benchmark-results location; committing/publishing
them requires normal human review and repository policy.

Triage compares phase telemetry, query plans, partition/cardinality, DuckDB spill, database/temp
size, dependency/environment, and semantic roots against the last accepted same-version result.
Possible resolutions are code/query memory fix, proven measurement/run invalidation and rerun,
fixture/generator bug with new reviewed fixture version, or umbrella/benchmark revision through
explicit design review. Raising the threshold, lowering cardinality, changing features,
warming cache, setting a lower artificial memory limit solely to force spill, or omitting output
is never an automatic fix.

## 16. Security, licensing, and test-data handling

All committed fixtures are synthetic or redistribution-cleared and carry license/source.
Provider credentials never enter cassettes, logs, snapshots, failure databases, reports, or
benchmark manifests. Secret-scanning includes generated diagnostic artifacts before retention.

Security suites cover path/symlink/traversal, SQL/identifier injection, pickle/object hooks,
archive/export external references, HTML/JS/CSP/URI, dashboard bind/upload/static/network,
resource bombs, oversized/nested payloads, log/error redaction, license refusal, and least-
authority capability objects. Fuzzing is bounded and stores minimized nonsecret cases.

Benchmark synthetic data are explicitly not realistic market data and cannot support finance
claims. Its purpose is deterministic systems/memory verification.

## 17. Implementation sequence

1. Add test-ID/requirement matrix, markers, deterministic environment, fixture identity/builders,
   no-network and cleanup ownership.
2. Implement per-plan unit/integration/scenario goldens and schema/migration/docs checks alongside
   each vertical implementation checkpoint.
3. Publish extension conformance kits and component fixture adapters with exact reports.
4. Implement domain/temporal/accounting/order/experiment/result/presentation properties and
   state machines; promote minimized regressions.
5. Add named fault injector/barriers, concurrency/recovery suites, optional clean-environment
   matrix, export/database/browser compatibility fixtures, security/accessibility tests.
6. Implement sample-project and benchmark fixture generators/manifests; independent validator,
   measured workload, environment preflight, telemetry, and controlled runbook.
7. Establish coverage/critical-branch reports, performance smoke/trend, release memory evidence,
   flagship workflow, and full Plans 01–18 traceability audit.
8. Complete docs, strict build, all gates, final cumulative review, and human release-readiness
   report without version bump/tag/publish.

## 18. Acceptance tests and exit criteria

### 18.1 Traceability and correctness

- Every normative Plans 01–18 section maps to passing tests or a reviewed implementation-phase
  gate; no orphan/stale/duplicate requirement IDs.
- All hand-worked temporal/accounting/execution/metrics/attribution examples and flagship
  workflow pass through public APIs with expected exact roots/reasons.
- Property/stateful tests cover every listed invariant after each transition, reproduce seeds,
  and retain reviewed minimized counterexamples.
- Fault/concurrency suites prove prior-or-complete publication, idempotency, retry/resume,
  deterministic ordering, lease/lock safety, no partial artifacts, and safe cleanup.

### 18.2 Contracts, matrices, and presentation

- Every built-in and reference custom extension passes its applicable public conformance suite;
  known opaque components remain visibly nonconformant/unsafe.
- Supported Python/Linux/minimum/resolved dependency and base/required-extra matrices pass with
  no optional import leakage; optional static state is reported.
- Every supported migration/export/storage fixture opens/upgrades/reopens with exact logical
  roots and source preservation; unsupported/corrupt files fail safely.
- Docs snippets/links/nav/notebooks as scheduled, semantic Plotly/report HTML/offline/security/
  accessibility, and dashboard pages/cache/read-only/loopback/framework evaluation pass.
- Overall branch coverage is at least 90% and reviewed critical modules meet their near-complete
  meaningful branch targets without unjustified exclusions/quarantine.

### 18.3 Performance and benchmark

- Non-gating phase suites record versioned trends and do not introduce flaky hard thresholds.
- `daily_equity_5000x20@1` generator reproduces exact calendar/instrument/churn/bar/missing/action
  schemas/counts/roots independent of generation partition/order.
- An independent validator confirms all ten feature formulas/states, monthly top-1,000 universe,
  equal weights, simulation/cost/capacity/action/settlement/accounting/result configuration.
- Controlled cold-cache Linux run meets all correctness/environment evidence and peak RSS
  `<= 25,769,803,776` bytes with swap zero, or release remains blocked with structured triage.
- Reopening the benchmark result after process exit reproduces public counts/roots and journal/
  valuation/reconciliation invariants.

### 18.4 Final exit

Plan 18 is complete only when repository gates, docs checks, strict build, schema/contracts,
required extras, compatibility/security/accessibility suites, coverage, flagship workflow,
benchmark generator/validator/runbook, and full cumulative Plans 01–18 review pass. The actual
24 GiB controlled result is a later implementation/release acceptance artifact; this planning
checkpoint is complete when the exact executable benchmark contract and validation fixtures are
accepted. No version bump, tag, release, publish, push, or merge is authorized by this plan.

## 19. Consistency statement

This plan converts the umbrella quality strategy and every focused contract into layered,
traceable, reproducible evidence. It defines a demanding but honest memory gate without making
the synthetic workload a realism claim, preserves hard correctness boundaries under faults and
optimization, and keeps release operations human-triggered. No project-level direction is
revised.
