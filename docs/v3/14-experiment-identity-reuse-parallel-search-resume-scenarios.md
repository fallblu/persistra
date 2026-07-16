# Focused specification 14: experiment identity, reuse, parallel search, resume, and scenarios

**Status:** Implementation-ready draft  
**Umbrella:** [`v3-spec.md`](v3-spec.md)\
**Primary package:** `persistra.experiments`  
**Required before:** focused specifications 15–18  
**Last reviewed:** 2026-07-16

## 1. Purpose and relationship to the umbrella specification

This specification defines experiment orchestration for Persistra v3. It fixes the
study/trial/fold/scenario/run hierarchy, design/execution/attempt/artifact identities,
exact and warned compatible reuse, code provenance, local parallel worker protocol,
interruption and resume, search, scenarios, stress, Monte Carlo, bootstrap, progress, and
failure contracts.

Plans 01–13 remain normative. This plan schedules their immutable research and simulator
occurrences; it does not alter their data cutoffs, construction, accounting, event order,
fidelity, checkpoint contents, or completion rules. Plan 15 owns durable final result
schemas, transactional result merge, analysis artifacts, and portable export.

## 2. Scope

### 2.1 In scope

- Simple runs and nested studies without flattening context into tags
- Typed parameter domains, conditional parameters, and canonical trial configurations
- Grid, seeded random, user-defined, and Bayesian search
- Exact fold, trial, scenario, and run planning
- Design, execution, attempt, and content-addressed artifact identity
- Exact reuse by default and explicit versioned compatibility reuse
- Code, dependency, solver, runtime, platform, and nondeterminism provenance
- Shared market leases, isolated worker databases, bounded local processes, and progress
- Same-attempt checkpoint resume versus new-attempt retry
- Failure thresholds, stop policies, cancellation, and auditable skipped work
- Historical/hypothetical scenarios, seeded Monte Carlo, and dependence-aware bootstrap
- Coordinator manifests and the verified handoff to Plan 15

### 2.2 Out of scope

- Distributed/network scheduling, remote artifact stores, Kubernetes, service queues, or
  multi-user coordination
- Changing a simulator's event/checkpoint semantics or resuming across execution identities
- Final result-table design, analysis calculations, comparisons, export, plots, or reports
- Automatic hyperparameter-space inference, arbitrary object serialization, or unbounded
  user code
- Presenting randomized search, Bayesian optimization, scenarios, or bootstrap as causal
  evidence without the owning validation design
- Silent environment relaxation, invisible cache hits, or artifact mutation

## 3. Normative decisions

1. `Study`, `Trial`, `Fold`, `Scenario`, and `RunPlan` are distinct immutable records. A
   simple run receives explicit singleton trial/fold/scenario records through a convenience
   builder; downstream schemas never use nullable hierarchy keys.
2. A design identity hashes the fully resolved research question, not a friendly name. An
   execution identity adds every known behavior-affecting implementation/environment fact.
3. An attempt ID is randomly assigned to one concrete start or retry of one execution
   identity. It is not a content hash and never changes identity after failure.
4. An artifact identity is the SHA-256 root of a completed, verified immutable artifact
   manifest and its content roots. It is unavailable for partial, interrupted, or failed
   attempts.
5. Exact reuse requires equal execution identity, a completed eligible attempt, a verified
   artifact, and a policy that does not forbid reuse. Design equality alone is never exact.
6. Compatibility reuse is opt-in per request, governed by a named/versioned allowlist of
   differences, records every actual difference, retains the source execution/artifact
   identity, and emits a persistent material warning. It never creates a fake artifact
   under the requested execution identity.
7. Unknown material code, dependency, input, platform behavior, or nondeterminism makes
   exact reuse and deterministic replay ineligible. It may execute under explicit policy
   with monotone findings; an override cannot manufacture an identity fact.
8. Workers are local processes. They read exact immutable market members under Plan-02
   shared leases and exclusively write one isolated disposable DuckDB file. They never
   write the project research database.
9. The coordinator is the sole research-database writer. Plan 15 validates and transactionally
   merges a completed worker artifact. Cross-file ACID is not claimed.
10. Work scheduling order is deterministic and distinct from completion order. Completion,
    worker PID, filesystem path, and wall clock never affect semantic roots.
11. Same-attempt resume is allowed only for an interrupted simulator occurrence using its
    own verified Plan-12/13 checkpoint. A failed attempt or incompatible/corrupt checkpoint
    is retried as a new attempt and occurrence.
12. Cancellation is cooperative at a simulator safe boundary. It never marks partial
    output complete. A killed worker becomes lost/interrupted with explicit evidence.
13. Search suggestions are immutable, ordinal, typed, and deduplicated by canonical trial
    content. Previously evaluated configurations are not rerun unless the reuse/retry policy
    explicitly calls for an attempt.
14. Bayesian search is required for 3.0 through the `search` extra. The base package can
    read its stored plans/results and fails with installation guidance when asked to plan it.
15. Scenario perturbations are ordered typed transformations of exact immutable inputs or
    policies. Their applicability, information timing, realism limitation, and roots enter
    design/execution/fidelity as appropriate.
16. Random search, Bayesian search, Monte Carlo, and bootstrap use namespaced deterministic
    seed streams. Inserting unrelated work does not perturb prior draws.
17. Failed trials remain outcomes. Stop thresholds act only after a deterministic completed
    outcome boundary and produce explicit `not_scheduled`/`cancelled` records for affected
    work; nothing vanishes from the planned manifest.
18. Search objectives consume only eligible immutable validation/analysis outputs declared
    by the design. Final holdouts and label-classified values cannot leak into planning or
    simulator decision paths.
19. All enumeration, queues, callbacks, state, manifests, and frames are bounded. Exceeding
    a limit fails or stops at a declared boundary without sampling hidden work.
20. Mutable notes/tags belong to Plan 15 annotations and never enter identities.

## 4. Identities and immutable values

### 4.1 Assigned IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `StudyId` | `study` | One study design occurrence |
| `TrialId` | `trial` | One canonical parameter configuration within a study |
| `ExperimentFoldId` | `experiment_fold` | One study-owned reference to an exact Plan-09 split/fold |
| `ScenarioId` | `scenario` | One ordered perturbation configuration |
| `RunPlanId` | `run_plan` | One resolved trial × fold × scenario execution plan |
| `AttemptId` | `attempt` | One concrete execution or retry |
| `SearchPlanId` | `search_plan` | One immutable candidate-generation policy |
| `SearchSuggestionId` | `search_suggestion` | One suggestion ordinal/outcome |
| `WorkerAssignmentId` | `worker_assignment` | One attempt dispatched to one local worker |
| `ReuseDecisionId` | `reuse_decision` | One explicit exact/compatible/miss decision |

Plan-09 validation-plan identity and scoped fold ordinal remain authority for temporal
membership. `ExperimentFoldId` is deliberately not a general `FoldId`: its record binds
`(ValidationPlanId, fold_ordinal, membership_content_id, role_content_id)` into one study
and must not recalculate or rebind membership.

### 4.2 Content identities

```python no-run
@dataclass(frozen=True, slots=True)
class DesignIdentity:
    schema_version: SchemaVersion
    content_id: ContentId

@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    schema_version: SchemaVersion
    design_identity: DesignIdentity
    content_id: ContentId

@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    format_version: SchemaVersion
    manifest_content_id: ContentId
```

These types wrap content identities and are not `EntityId` subclasses. Canonical wire forms
include their kind, version, and SHA-256 content ID. `ArtifactIdentity` hashes the canonical
artifact manifest, which in turn names every immutable table/file root; it does not hash a
mutable pathname or DuckDB page layout alone.

### 4.3 Stable states

- Study: `planned`, `running`, `stopping`, `completed`, `completed_with_failures`, `failed`,
  `cancelled`
- Run plan: `planned`, `reused_exact`, `reused_compatible`, `scheduled`, `completed`,
  `failed`, `cancelled`, `not_scheduled`
- Attempt: `created`, `assigned`, `running`, `interrupted`, `failed`, `completed`, `lost`,
  `cancelled`
- Reuse: `miss`, `exact`, `compatible`, `ineligible`, `corrupt_source`
- Search kind: `grid`, `random`, `user_defined`, `bayesian`
- Scenario kind: `baseline`, `historical_stress`, `hypothetical`, `monte_carlo`, `bootstrap`

State histories are append-only with legal-transition validation. `completed` attempt
requires artifact identity; every other attempt state forbids it.

## 5. Study hierarchy and public requests

```python no-run
@dataclass(frozen=True, slots=True)
class StudyRequest:
    name: str
    common_design: ResearchDesignRef
    search: SearchSpec
    folds: FoldSetRef
    scenarios: ScenarioSetRef
    simulator: VectorizedSimulationTemplate | EventSimulationTemplate
    objective: ObjectiveSpec | None
    reuse: ReusePolicy = ReusePolicy.exact()
    retry: RetryPolicy = RetryPolicy()
    stop: StudyStopPolicy = StudyStopPolicy()
    workers: LocalWorkerPolicy = LocalWorkerPolicy()
    seed: SeedSpec = SeedSpec(0)
    limits: ExperimentLimits = ExperimentLimits()
```

The object graph is closed and constructible:

```python no-run
@dataclass(frozen=True, slots=True)
class ResearchDesignRef:
    market_context: CompositeAsOfContext
    dataset_build_id: ResearchDatasetBuildId
    universe_evaluation_id: UniverseEvaluationId
    validation_plan_id: ValidationPlanId
    strategy_or_constructor: EntityId
    opening: AccountingOpeningRef
    accounting_policy: AccountingPolicyBundleRef
    benchmark: BenchmarkVersionRef | None
    risk_free: RiskFreeCurveRef | None
    design_content_id: ContentId

@dataclass(frozen=True, slots=True)
class ParameterPredicate:
    path: str
    operator: Literal["eq", "in", "lt", "le", "gt", "ge"]
    values: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ParameterDomain:
    path: str
    value_kind: Literal["bool", "int", "decimal", "string", "duration", "instant", "qualified_name", "typed_ref"]
    domain_kind: Literal["choice", "integer_range", "decimal_grid", "log_grid", "continuous", "distribution", "custom"]
    values: tuple[str, ...] = ()
    lower: str | None = None
    upper: str | None = None
    step: str | None = None
    distribution: Literal["uniform", "log_uniform", "normal"] | None = None
    custom_generator: QualifiedName | None = None
    active_when: tuple[ParameterPredicate, ...] = ()

@dataclass(frozen=True, slots=True)
class SearchSpec:
    kind: Literal["grid", "random", "user_defined", "bayesian"]
    domains: tuple[ParameterDomain, ...]
    explicit_configurations: tuple[ParameterValues, ...] = ()
    max_suggestions: int = 1
    batch_size: int = 1
    surrogate: QualifiedName | None = None
    acquisition: QualifiedName | None = None
    failed_objective: Literal["censor", "penalize", "ignore"] = "censor"

@dataclass(frozen=True, slots=True)
class FoldSetRef:
    validation_plan_id: ValidationPlanId
    fold_ordinals: tuple[int, ...]
    membership_manifest_content_id: ContentId

@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    name: str
    kind: Literal["baseline", "historical_stress", "hypothetical", "monte_carlo", "bootstrap"]
    perturbation_content_id: ContentId
    repetitions: int = 1

@dataclass(frozen=True, slots=True)
class ScenarioSetRef:
    scenarios: tuple[ScenarioSpec, ...]
    set_content_id: ContentId

@dataclass(frozen=True, slots=True)
class VectorizedSimulationTemplate:
    base_request: VectorizedSimulationRequest
    parameter_slots: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class EventSimulationTemplate:
    base_request: EventSimulationRequest
    parameter_slots: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class ObjectiveSpec:
    metric: AnalysisDefinitionRef
    metric_name: QualifiedName
    direction: Literal["minimize", "maximize"]
    slice_name: str
    aggregation: Literal["single", "mean", "median", "worst"]
    tie_rule: Literal["lower_trial_ordinal", "canonical_parameter_bytes"]
    unavailable: Literal["fail", "censor", "penalize"]
    penalty: Decimal | None = None

@dataclass(frozen=True, slots=True)
class ReusePolicy:
    kind: Literal["none", "exact", "compatible"] = "exact"
    compatibility_policy: QualifiedName | None = None

@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    retryable_reasons: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class StudyStopPolicy:
    max_completed: int | None = None
    max_failed: int | None = None
    objective_threshold: Decimal | None = None

@dataclass(frozen=True, slots=True)
class LocalWorkerPolicy:
    workers: int = 1
    start_method: Literal["spawn"] = "spawn"
    worker_memory_bytes: int | None = None

@dataclass(frozen=True, slots=True)
class ExperimentLimits:
    max_trials: int = 100_000
    max_folds: int = 10_000
    max_scenarios: int = 100_000
    max_run_plans: int = 1_000_000
    max_attempts: int = 10_000_000
    max_workers: int = 64
    max_search_state_bytes: int = 100_000_000
    timeout: Duration = Duration(86_400_000_000)
```

Parameter paths/domains are unique and ordered; canonical scalar text follows Plan 01;
ranges are closed with lower <= upper and positive steps; inactive variant fields are
forbidden; predicates may reference only earlier paths and must be acyclic. Grid/random/
user-defined/Bayesian variants require only their stated fields; custom generators and
Bayesian surrogate/acquisition names resolve to registered implementations. Fold ordinals,
scenario names, slots, retry reasons, and input IDs are unique; baseline appears exactly once;
all counts are positive and the expanded trial × fold × scenario plan fits limits. A penalty
is present exactly for `penalize`; compatible reuse requires its policy. Validation errors map
to `StudyPlanningError`, unavailable objectives to the declared outcome, and limit expansion
to `ExperimentLimitError` before worker assignment. Every resolved ref, default, domain AST,
and policy enters design identity.

The common design pins composite snapshots, research datasets/materializations, universe,
split design, strategy, portfolio, opening/accounting, simulator/fidelity, benchmark/rates,
and component versions. Trial parameters can fill only declared typed slots. Fold and
scenario expansion happens before run identity and produces a complete bounded plan.

`project.services.experiments.run(single_run_request)` constructs a study with one canonical trial,
one exact fold (which may be a declared full interval), and baseline scenario. This is API
convenience, not an alternate identity path.

## 6. Parameter domains and search

### 6.1 Domain grammar

Supported scalar types are boolean, integer, finite decimal/float with canonical decimal
text, string enum, duration, instant, qualified name/version, and typed ID/reference. Domains
are `choice`, closed integer range, finite decimal grid, log grid, bounded continuous,
distribution, or registered custom generator. Parameter paths address declared configuration
slots and cannot address credentials, paths, identity outputs, cutoffs, label role, or unsafe
flags unless the design explicitly makes a safe policy dimension searchable.

Conditional parameters use an acyclic predicate grammar of equality/membership/comparison
over earlier parameters. A configuration contains exactly its active parameters; inactive
defaults do not enter identity. Validation rejects NaN/infinity, ambiguous float text,
duplicate canonical values, empty domains, cycles, and more candidates than the bound.

### 6.2 Grid, random, and user-defined

Grid uses declared parameter order and canonical value order, with the rightmost active
dimension varying fastest. Conditional expansion is deterministic. Random search samples
from declared distributions through a suggestion-ordinal seed stream and deduplicates; a
bounded exhaustion outcome is explicit. User-defined search validates an ordered finite
tuple of complete configurations and preserves input ordinal after canonicalization.

### 6.3 Bayesian search

Bayesian search operates sequentially in deterministic suggestion rounds. Its exact
surrogate/acquisition/initial-design versions, normalization, objective direction, constraint
handling, pending-point policy, batch size, seed stream, dependency versions, and serialized
optimizer-state schema enter execution identity. Stored optimizer state is canonical data,
never pickle.

Only completed eligible objective observations through the prior round enter a suggestion.
Parallel completions are incorporated in deterministic suggestion/run-plan order, not arrival
order. Failed/unavailable objectives use an explicit censor/penalty/ignore policy. Same inputs
must reproduce suggestions for replay-eligible dependency versions; otherwise the search is
visibly nondeterministic and exact resume/reuse is ineligible.

The base installation exposes configuration/read models but raises
`SearchExtraRequiredError` before planning Bayesian work. Release tests install and exercise
the `search` extra; its absence is not feature deferral.

### 6.4 Objective and validation safety

An objective names one versioned Plan-15 metric/analysis output, direction, eligible fold/
slice, aggregation, unavailable policy, and tie rule. It cannot read final holdout outcomes
before a nested selection design permits them. Plan-09 holdout-use state and contamination
propagate. Equal objectives tie by canonical trial content, never completion time.

The coordinator owns objective computation: after each run's Plan-15 publication commits,
the coordinator submits the declared Plan-15 metric/analysis request for that run — an
ordinary plan-15 analysis executed under the coordinator's identity, with the study,
trial, and run IDs in its lineage — and records the resulting artifact (or its failure) as
the trial's objective observation before the next suggestion round that would consume it.
A failed, unavailable, or unsafe objective artifact maps to the declared
censor/penalty/ignore policy and is persisted with its reason; the coordinator never
recomputes a differing value for the same run, and exact replay returns the existing
artifact. Plan 14 remains outside analysis mathematics — it only invokes and consumes the
plan-15 surface.

## 7. Design and execution identity

### 7.1 Design identity includes

- exact common design and canonical active trial parameters;
- exact composite/member snapshots and project/public cutoff mode;
- universe evaluation and instrument/calendar/settlement manifests;
- research dataset, feature/forecast/risk/portfolio definition and output roots;
- Plan-09 split/fold membership and selection/holdout role;
- exact scenario transformation definitions, ordered roots, and realized scenario inputs;
- simulator type/request semantics, opening, accounting and fidelity policies;
- declared component qualified names and semantic versions;
- objective semantics when it can affect adaptive search; and
- design-identity schema version.

Safety/licensing/lineage facts that describe the research question enter design. Machine
paths, allocated IDs, attempt state, worker count, completion order, notes, and output roots
do not.

### 7.2 Execution identity additionally includes

- exact code identities/hashes for Persistra and every material custom component;
- package/Python/DuckDB/solver/search/BLAS and other material dependency versions;
- platform, architecture, endianness, locale/timezone database, thread/math/runtime settings
  proven behavior-affecting by the component declarations;
- exact resolved configuration, event-priority/schema/migration versions, limits, and
  simulator fidelity profile;
- random seed plan, namespace algorithm, and deterministic/nondeterministic declarations;
- external executable/service identities and immutable response roots when permitted; and
- execution-identity schema version.

Worker count is excluded only when conformance proves partition-invariant semantics; otherwise
it enters. Absolute disposable paths and PIDs never enter. Dirty Git state records commit,
dirty flag, relevant file manifest/hashes, and untracked material file declarations. A Git
hash without dirty-file roots is insufficient.

Unresolved material facts set `execution_identity_complete=false`, with reasons. A content
root may still describe the known manifest, but it is not eligible for exact reuse/replay.

## 8. Reuse

### 8.1 Exact reuse

The coordinator searches only registered completed artifacts with equal execution identity.
It verifies source attempt terminal state, artifact manifest/schema, all required table/file
roots, simulator completion/reconciliation, safety/licensing eligibility, and current
readability before returning a reuse decision. Corruption quarantines the candidate from
reuse and continues/fails under policy; it never falls back silently to design equality.

An exact reuse edge points from requested run plan to source attempt/artifact. No new
simulator occurrence, attempt, or copied artifact is created. Plan 15 can expose the same
immutable artifact through another study relationship.

### 8.2 Compatibility reuse

A `CompatibilityPolicy` has qualified name, semantic/schema version, ordered field rules,
source/target supported ranges, rationale, comparison class, and implementation identity.
It first requires equal design identity unless a narrower explicitly named design projection
is part of a future umbrella revision. Rules may ignore only enumerated execution differences
such as a proven nonsemantic patch dependency or platform fact. They cannot ignore snapshots,
cutoffs, trial/fold/scenario, strategy/portfolio/simulation semantics, seeds, fidelity,
safety/licensing, accounting/event order, output schema, or unknown material identity.

Every requested-versus-source difference is normalized and classified. An unlisted
difference rejects. A compatible edge stores policy, differences, source execution/attempt/
artifact, requested execution, verification evidence, and permanent warning. APIs return a
`ReusedRunHandle` whose `artifact_identity` and `source_execution_identity` remain original;
they never synthesize completion for the requested execution.

### 8.3 No invisible substitution

Planning returns a `ReuseDecision` before scheduling. CLI/API output states exact,
compatible, miss, or ineligible. `reuse=none` always schedules a new attempt. Failed,
interrupted, incomplete, deleted, unreadable, or unverified artifacts are never reusable.

## 9. Attempts, retry, and resume

An attempt binds one run plan, exact execution identity, allocated simulator occurrence,
worker assignment history, started/completed instants, status history, failure category,
checkpoint reference, and optional completed artifact.

- `interrupted` with a valid Plan-12/13 checkpoint may resume the same attempt, worker file,
  and simulator occurrence. Resume re-verifies execution identity and checkpoint; assignment
  may change, semantic identity cannot.
- `lost` may resume only if the isolated file and verified checkpoint are recovered; otherwise
  it transitions to failed and retry creates a new attempt.
- `failed`/`cancelled` are terminal. An eligible retry allocates a new attempt, simulator
  occurrence, and isolated file for the same execution identity.
- a changed request/code/seed/environment is a new execution identity/run plan, never retry.

Retry policies classify modeled, infrastructure, resource, invariant, and user-cancel
failures; set bounded counts/backoff bookkeeping; and cannot retry structural safety,
licensing, invalid-design, or deterministic invariant failures unless a new design/execution
fact addresses them. Wall-clock backoff affects dispatch only, not results or identity.

## 10. Local parallel protocol

### 10.1 Coordinator planning

The coordinator holds `ProjectMode.RESEARCH_WRITE` and the exclusive research lease only for
short planning/state/merge transactions. It freezes exact market snapshots/copies before
workers start, commits the complete run-plan queue, then releases the research writer. It
never keeps writable research attached while workers run.

Scheduling order is `(study run ordinal, trial ordinal, fold ordinal, scenario ordinal,
attempt ordinal)`. A bounded dispatcher selects the earliest ready items, subject to declared
Bayesian rounds and resource tokens. Worker-count changes cannot change that order.

### 10.2 Worker assignment

Each spawned local process receives a canonical bounded assignment manifest by controlled
IPC: attempt/execution identity, exact read-only member paths/database IDs/snapshot roots,
isolated output path/database ID, simulator plan, limits, seed namespace, and coordinator
protocol version. It receives no credentials beyond already authorized local capabilities.

The worker acquires Plan-02 shared leases for all market members, verifies them, opens them
read-only, and exclusively creates/opens only its disposable research-role file. A worker
cannot attach the project research database. Environment/provenance are measured again and
must equal planned execution facts before running.

### 10.3 Completion handoff and merge

The worker closes its database, fsyncs where supported, creates a canonical handoff manifest,
and sends a completion message containing identities, status, schema, counts, logical table
roots, file checksum/size, and safe diagnostics. Message receipt is not publication.

The coordinator reacquires the exclusive research lease, opens the worker file read-only,
recomputes and verifies database role/disposable flag, design/execution/attempt/occurrence,
simulator completion, schemas/counts/roots/checksum, journal reconciliation, safety/licensing/
fidelity, and no external unresolved references. Plan 15 then copies into staging, verifies,
and atomically publishes or rolls back. Only after publication may retention policy delete
the isolated file; deletion is never required for semantic completion.

Plan 15's destination publication is a lossless normalized mapping of source occurrence
tables, including sampled equity and external-flow-split return intervals. It may validate
and index those facts but cannot add a hidden financial calculation to the Plan-14 source
`ArtifactIdentity`; post-run alternative returns and metrics are separate analysis artifacts.

### 10.4 Progress and control

Progress is a typed post-commit event stream: study planned, suggestion, run planned, reuse,
attempt assigned/started/checkpoint/completed/failed, merge, stop, and study terminal. Delivery
is at-least-once and consumers deduplicate by event ID. The default terminal renderer is an
adapter; experiment core imports no progress UI library.

Cancellation writes intent through the coordinator. Workers observe it at simulator safe
boundaries. Escalated process termination is infrastructure evidence and cannot publish the
current event/attempt as complete.

## 11. Failure and stopping policy

Every planned run has an outcome. Planning failures prevent the affected plan and may fail
the study. Execution failures retain attempt/category/reasons/last verified prefix. A study
can declare maximum absolute/fractional failures, consecutive failures in deterministic plan
order, objective-unavailable count, or fatal reason classes.

Thresholds evaluate only when all prior ordinals needed by the rule are terminal, so worker
completion races cannot change stopping. Not-yet-dispatched plans transition to
`not_scheduled`; running work is allowed to finish or cooperatively cancelled per frozen
policy. A study terminal manifest reconciles planned/reused/scheduled/completed/failed/
cancelled/not-scheduled counts exactly.

## 12. Scenarios and stress

### 12.1 Scenario model

A scenario is an ordered tuple of registered transformations. Each declares target
capability, exact applicability interval/assets, operation, parameters, timing/availability,
required input roots, output root, preserves/destroys properties, causal/retrospective class,
and fidelity/safety effect. Overlapping transformations require an explicit composition
order and conflict policy.

Supported 3.0 targets include raw-derived price/return path capabilities, spread/impact/
latency/liquidity policies, borrow availability/rates, financing/rates, supported action/
delisting terms, universe/missingness, risk-model inputs, portfolio constraints, and
execution status/rejection. Canonical market facts are never overwritten; scenarios create
run-owned immutable projections.

Historical stress selects an exact known interval and reuses observed eligible paths under
a declared mapping/alignment rule. Hypothetical shocks are parameterized transformations.
Both remain scenarios in design identity and use normal simulator/accounting/result paths.

### 12.2 Timing and safety

A scenario cannot make a fact visible earlier than its base availability unless it is
explicitly a synthetic model input available at the scenario's declared instant. Strategy
contexts see only scenario outputs permitted by that cutoff. Retrospective perturbations are
analysis/stress assumptions and remain visibly classified; they cannot become training or
decision facts through override.

## 13. Monte Carlo and bootstrap

Each replicate is a scenario with stable replicate ordinal and a namespaced seed. A method
records population, sampling unit, replacement, block/cluster construction, block-length or
distribution, boundary handling, cross-sectional coupling, stratification, missingness,
parameter uncertainty, number of replicates, and the dependence structures it preserves and
destroys.

Initial methods are:

- moving/stationary time-series block bootstrap with explicit temporal dependence limits;
- cross-sectional resampling only where entity exchangeability is asserted and tested;
- trade resampling for post-run analysis, not a replacement for market/order simulation;
- seeded parameter uncertainty applied to registered model/policy inputs; and
- seeded simulation of registered returns, costs, borrow, liquidity, or missingness models.

Resampled market paths preserve instrument/action/calendar coherence only when the method
explicitly transforms them together; otherwise dependent accounting/action simulation is
ineligible. Monte Carlo is not exact reuse eligible when its generator identity or seed is
unknown. Aggregation and confidence intervals are Plan 15 analysis artifacts, not mutations
of replicate runs.

## 14. Storage schema

The research database owns migration-managed `experiments` metadata and controlled
`experiment_data` parameter/difference/progress rows. Worker simulator output stays in its
Plan-12/13 schemas until Plan-15 merge.

```sql
CREATE TABLE experiments.search_plans (
    search_plan_id UUID PRIMARY KEY,
    search_kind VARCHAR NOT NULL CHECK (
        search_kind IN ('grid', 'random', 'user_defined', 'bayesian')
    ),
    parameter_schema_content_id VARCHAR NOT NULL,
    search_policy_content_id VARCHAR NOT NULL,
    objective_content_id VARCHAR,
    seed_namespace_content_id VARCHAR NOT NULL,
    implementation_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    search_plan_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE experiments.studies (
    study_id UUID PRIMARY KEY,
    name VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (
        status IN ('planned', 'running', 'stopping', 'completed', 'completed_with_failures', 'failed', 'cancelled')
    ),
    request_content_id VARCHAR NOT NULL,
    common_design_content_id VARCHAR NOT NULL,
    search_plan_id UUID NOT NULL,
    fold_set_content_id VARCHAR NOT NULL,
    scenario_set_content_id VARCHAR NOT NULL,
    reuse_policy_content_id VARCHAR NOT NULL,
    stop_policy_content_id VARCHAR NOT NULL,
    seed_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    terminal_manifest_content_id VARCHAR,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    CHECK ((status IN ('completed', 'completed_with_failures', 'failed', 'cancelled')) = (terminal_manifest_content_id IS NOT NULL))
);

CREATE TABLE experiments.trials (
    trial_id UUID PRIMARY KEY,
    study_id UUID NOT NULL,
    trial_ordinal BIGINT NOT NULL CHECK (trial_ordinal >= 1),
    parameter_content_id VARCHAR NOT NULL,
    parameter_schema_content_id VARCHAR NOT NULL,
    suggestion_id UUID,
    trial_content_id VARCHAR NOT NULL,
    UNIQUE (study_id, trial_ordinal),
    UNIQUE (study_id, trial_content_id)
);

CREATE TABLE experiments.scenarios (
    scenario_id UUID PRIMARY KEY,
    study_id UUID NOT NULL,
    scenario_ordinal BIGINT NOT NULL CHECK (scenario_ordinal >= 1),
    scenario_kind VARCHAR NOT NULL CHECK (
        scenario_kind IN ('baseline', 'historical_stress', 'hypothetical', 'monte_carlo', 'bootstrap')
    ),
    definition_content_id VARCHAR NOT NULL,
    realized_input_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    fidelity_effect_content_id VARCHAR NOT NULL,
    scenario_content_id VARCHAR NOT NULL,
    UNIQUE (study_id, scenario_ordinal),
    UNIQUE (study_id, scenario_content_id)
);

CREATE TABLE experiments.experiment_folds (
    experiment_fold_id UUID PRIMARY KEY,
    study_id UUID NOT NULL,
    fold_ordinal INTEGER NOT NULL CHECK (fold_ordinal >= 1),
    validation_plan_id UUID NOT NULL,
    validation_fold_ordinal INTEGER NOT NULL CHECK (validation_fold_ordinal >= 1),
    membership_content_id VARCHAR NOT NULL,
    role_content_id VARCHAR NOT NULL,
    experiment_fold_content_id VARCHAR NOT NULL,
    UNIQUE (study_id, fold_ordinal),
    UNIQUE (study_id, validation_plan_id, validation_fold_ordinal),
    UNIQUE (study_id, experiment_fold_content_id)
);
```

```sql
CREATE TABLE experiments.run_plans (
    run_plan_id UUID PRIMARY KEY,
    study_id UUID NOT NULL,
    run_ordinal BIGINT NOT NULL CHECK (run_ordinal >= 1),
    trial_id UUID NOT NULL,
    experiment_fold_id UUID NOT NULL,
    scenario_id UUID NOT NULL,
    status VARCHAR NOT NULL CHECK (
        status IN ('planned', 'reused_exact', 'reused_compatible', 'scheduled', 'completed', 'failed', 'cancelled', 'not_scheduled')
    ),
    design_identity_content_id VARCHAR NOT NULL,
    execution_identity_content_id VARCHAR NOT NULL,
    execution_identity_complete BOOLEAN NOT NULL,
    simulator_kind VARCHAR NOT NULL CHECK (simulator_kind IN ('vectorized', 'event')),
    simulator_plan_content_id VARCHAR NOT NULL,
    reuse_decision_id UUID,
    terminal_content_id VARCHAR,
    UNIQUE (study_id, run_ordinal),
    UNIQUE (study_id, trial_id, experiment_fold_id, scenario_id)
);

CREATE TABLE experiments.attempts (
    attempt_id UUID PRIMARY KEY,
    run_plan_id UUID NOT NULL,
    attempt_ordinal INTEGER NOT NULL CHECK (attempt_ordinal >= 1),
    status VARCHAR NOT NULL CHECK (
        status IN ('created', 'assigned', 'running', 'interrupted', 'failed', 'completed', 'lost', 'cancelled')
    ),
    execution_identity_content_id VARCHAR NOT NULL,
    simulator_occurrence_kind VARCHAR NOT NULL CHECK (simulator_occurrence_kind IN ('vectorized', 'event')),
    simulator_occurrence_id UUID,
    isolated_database_id UUID,
    isolated_path_token VARCHAR,
    checkpoint_id UUID,
    artifact_manifest_content_id VARCHAR,
    failure_content_id VARCHAR,
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    UNIQUE (run_plan_id, attempt_ordinal),
    CHECK ((status = 'completed') = (artifact_manifest_content_id IS NOT NULL))
);

CREATE TABLE experiments.reuse_decisions (
    reuse_decision_id UUID PRIMARY KEY,
    run_plan_id UUID NOT NULL,
    reuse_state VARCHAR NOT NULL CHECK (
        reuse_state IN ('miss', 'exact', 'compatible', 'ineligible', 'corrupt_source')
    ),
    requested_execution_content_id VARCHAR NOT NULL,
    source_execution_content_id VARCHAR,
    source_attempt_id UUID,
    source_artifact_content_id VARCHAR,
    compatibility_policy_content_id VARCHAR,
    difference_manifest_content_id VARCHAR NOT NULL,
    verification_content_id VARCHAR NOT NULL,
    warning_content_id VARCHAR,
    decided_at TIMESTAMPTZ NOT NULL,
    CHECK ((reuse_state IN ('exact', 'compatible')) = (source_artifact_content_id IS NOT NULL)),
    CHECK ((reuse_state = 'compatible') = (compatibility_policy_content_id IS NOT NULL))
);
```

```sql
CREATE TABLE experiments.search_suggestions (
    search_suggestion_id UUID PRIMARY KEY,
    search_plan_id UUID NOT NULL,
    suggestion_ordinal BIGINT NOT NULL CHECK (suggestion_ordinal >= 1),
    round_ordinal BIGINT NOT NULL CHECK (round_ordinal >= 1),
    parameter_content_id VARCHAR NOT NULL,
    input_observation_content_id VARCHAR NOT NULL,
    optimizer_state_before_content_id VARCHAR NOT NULL,
    optimizer_state_after_content_id VARCHAR NOT NULL,
    seed_draw_content_id VARCHAR NOT NULL,
    outcome VARCHAR NOT NULL CHECK (outcome IN ('suggested', 'duplicate', 'exhausted', 'failed')),
    reason_code VARCHAR,
    UNIQUE (search_plan_id, suggestion_ordinal)
);

CREATE TABLE experiments.worker_assignments (
    worker_assignment_id UUID PRIMARY KEY,
    attempt_id UUID NOT NULL,
    assignment_ordinal INTEGER NOT NULL CHECK (assignment_ordinal >= 1),
    protocol_version VARCHAR NOT NULL,
    assignment_content_id VARCHAR NOT NULL,
    environment_content_id VARCHAR NOT NULL,
    isolated_database_id UUID NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('assigned', 'started', 'returned', 'lost', 'cancelled')),
    handoff_content_id VARCHAR,
    assigned_at TIMESTAMPTZ NOT NULL,
    returned_at TIMESTAMPTZ,
    UNIQUE (attempt_id, assignment_ordinal)
);

CREATE TABLE experiment_data.compatibility_differences (
    reuse_decision_id UUID NOT NULL,
    difference_ordinal INTEGER NOT NULL CHECK (difference_ordinal >= 1),
    field_path VARCHAR NOT NULL,
    requested_value_content_id VARCHAR NOT NULL,
    source_value_content_id VARCHAR NOT NULL,
    rule_content_id VARCHAR NOT NULL,
    classification VARCHAR NOT NULL CHECK (classification IN ('ignored_compatible', 'material_rejected')),
    PRIMARY KEY (reuse_decision_id, difference_ordinal)
);
```

Exact fold bindings, state transitions, parameter values, scenario transformations, seed
draws, progress events, failures, stop outcomes, and manifests use similarly normalized,
bounded relations. Plan 15 specifies copied run-result keys and publication tables.

## 15. Public API, CLI, events, and errors

```python no-run
plan = project.services.experiments.plan(request)
study = project.services.experiments.run(plan)
study = project.services.experiments.resume(study.id)
study.cancel(reason="user requested")
runs = study.runs(limit=1_000)
```

Planning/running require `RESEARCH_WRITE`; bounded inspection is available read-only when no
writer conflicts. The operational CLI adds `persistra studies list/show/resume/cancel` while
`persistra runs list/show` remains Plan-15 result inspection. CLI configuration validates to
the same Python request; it is not a second research language.

Domain events are post-commit and include study planned/started/stopping/terminal, suggestion,
run planned/reuse/scheduled/terminal, attempt assigned/started/resumed/interrupted/failed/
completed, worker lost/handoff verified, and merge requested/completed/failed. Structured
tables remain authority.

Exceptions include `ExperimentPlanningError`, `ExperimentIdentityError`, `ReuseVerificationError`,
`CompatibilityReuseError`, `SearchPlanningError`, `SearchExtraRequiredError`,
`WorkerProtocolError`, `AttemptResumeError`, `ScenarioValidationError`, and
`ExperimentResourceLimitError`. Stable reasons cover incomplete identity, unsafe/licensing
rejection, search exhaustion/objective unavailable, holdout forbidden, exact miss, corrupt
artifact, incompatible difference, worker environment mismatch/lost, checkpoint mismatch,
retry exhausted, failure threshold, cancellation, and incomplete terminal manifest.

## 16. Edge cases, security, and resources

| Case | Required outcome |
| --- | --- |
| Empty search | Planning error; simple run uses explicit singleton search |
| Conditional parameter inactive | Omitted from canonical config and identity |
| Same canonical trial suggested twice | One trial; later suggestion records duplicate |
| Exact identity but corrupt artifact | Quarantine from reuse and record `corrupt_source` |
| Design match, environment differs | Exact miss; compatible only under explicit rule and warning |
| Unknown custom-code hash | Execution incomplete; exact reuse/replay ineligible |
| Interrupted valid checkpoint | Resume same attempt/occurrence after verification |
| Failed attempt | New attempt/occurrence; never relabel old attempt |
| Worker finishes after cancellation | Verify and apply frozen finish/cancel policy; never race silently |
| Two workers return same attempt | Accept only assigned generation; conflicting handoff is invariant failure |
| Research writer appears during workers | Workers unaffected on immutable market files; merge waits/fails by lease policy |
| Bayesian result completion races | Incorporate in deterministic planned order/round |
| Scenario transformations conflict | Explicit composition rule or planning failure |
| Bootstrap breaks action coherence | Reject simulator use; analysis-only if declared |
| Stop threshold reached | Deterministic remaining outcomes become explicit not-scheduled/cancelled |

Assignments use opaque path tokens in durable tables; absolute paths are local coordinator
state and redacted from portable artifacts. No secrets, environment dumps, arbitrary pickle,
unbounded exception text, or database credentials enter manifests/events. Worker processes
receive least-authority read-only market and one-file write capabilities.

Limits cover studies, trials, parameters/domain values, folds, scenarios/replicates,
run plans, suggestions/rounds, attempts/retries, workers, pending queue, transformations,
optimizer state bytes, IPC bytes, artifact bytes/rows, progress backlog, and coordinator
transactions. CPU/memory/temp/thread limits are enforced per worker where the platform
supports them and always recorded.

## 17. Migration and extension policy

V2 sweep/run identities are not imported as exact v3 experiments. They may be registered as
opaque external evidence with unknown execution identity and no exact reuse eligibility.
Plan-02 verified migrations own `experiments`/`experiment_data`; Plan 15 owns result/export
migration compatibility.

Custom search, objective, scenario, resampler, retry, stop, or compatibility policies register
qualified name, semantic/schema version, canonical config, required capabilities, code/
dependency identity, deterministic/resource contract, output schema, and conformance tests.
Compatibility policies are security-sensitive allowlists and cannot use arbitrary callbacks
to declare unknown differences harmless.

## 18. Implementation sequence

1. Add hierarchy/identity/parameter values, schemas, repositories, limits, and exact planning.
2. Implement grid/random/user search, folds/scenario expansion, seed namespaces, objective
   eligibility, complete queue manifests, and terminal accounting.
3. Implement provenance and execution completeness, exact reuse verification, and explicit
   compatibility policy/difference edges.
4. Implement attempt state/retry/same-attempt resume and Plan-12/13 occurrence adapters.
5. Implement local worker protocol, shared leases, disposable files, deterministic dispatcher,
   progress/cancel/control, handoff verification, and Plan-15 merge boundary.
6. Implement Bayesian search extra with canonical optimizer state and deterministic rounds.
7. Implement scenario/stress transformations, Monte Carlo/bootstrap methods, safety/fidelity,
   failure/stop policies, fault/resource/determinism tests.
8. Complete docs, strict build, benchmark hooks, and cumulative Plans 01–14 review.

## 19. Acceptance tests and exit criteria

### 19.1 Hierarchy, identity, and reuse

- Simple and nested studies round-trip with nonnullable singleton hierarchy; canonical
  parameter conditionality, order, float/decimal forms, duplicates, and limits are golden.
- Design identity changes for every material input/fold/scenario/semantic change and not for
  allocated IDs/paths/worker completion; execution changes for every behavior-affecting code/
  environment/seed/fidelity/schema change.
- Dirty/unknown/external/nondeterministic provenance produces exact eligibility correctly.
- Exact reuse verifies all roots and never crosses execution identity. Compatible reuse
  records every allowed difference/warning, retains source identity, and rejects forbidden/
  unknown differences. Corruption never substitutes.

### 19.2 Search, scenario, and safety

- Grid ordering/conditionality, seeded random draws/dedup/exhaustion, user candidates, and
  Bayesian sequential/batch rounds reproduce across worker counts and completion races.
- Base import works without search dependencies; requesting Bayesian gives installation
  guidance; the `search` extra passes its release matrix.
- Objective selection respects Plan-09 nested/holdout state and structured unavailable
  results; labels never enter simulator decision paths.
- Historical/hypothetical/Monte Carlo/bootstrap fixtures verify exact inputs, transform
  order, availability, preserved/destroyed dependence, coherent actions, seed isolation,
  safety/fidelity propagation, and explicit ineligible combinations.

### 19.3 Workers, retry, resume, and completion

- Workers never attach research writable, verify shared market snapshots, write one isolated
  file, and reproduce roots across 1/N workers, dispatch delays, partition and completion order.
- Handoff verification catches wrong role/database/design/execution/attempt/occurrence/schema/
  count/root/checksum/reconciliation/fidelity/safety/licensing/external reference.
- Fault injection at dispatch/start/event/checkpoint/close/handoff/stage/merge boundaries
  publishes no partial result and retains a recoverable or terminal outcome.
- Interrupted valid checkpoint resumes same attempt/occurrence to uninterrupted roots;
  corrupt/mismatched checkpoint rejects; failed retry creates new attempt/occurrence.
- Cancellation, lost workers, retry exhaustion, failure thresholds, stopping, and every
  planned-count reconciliation are deterministic and auditable.
- Bounded APIs/frames/events, migrations/copies/reopen, docs snippets, strict MkDocs,
  `make lint type test`, and docs checks pass.

### 19.4 End-to-end exit

A documented study must run grid, random, user, and Bayesian searches over exact temporal
folds and baseline/stress scenarios with vectorized and event simulators; demonstrate exact
reuse, warned compatible reuse, one corrupt candidate, one failure/retry, same-attempt resume,
worker loss, deterministic stop, Monte Carlo/bootstrap limitation, and transactional Plan-15
handoff; and reproduce semantic roots at worker counts one and four using public APIs only.

Plan 14 is complete only when all repository gates, docs checks, strict build, optional-extra
tests, benchmark hooks, and cumulative review find no contradiction with the umbrella or
Plans 01–13.

## 20. Review checklist for dependent plans

Plans 15–18 must preserve:

- nonnullable hierarchy and exact trial/fold/scenario/run relationships;
- design versus execution versus assigned attempt versus content-addressed artifact identity;
- exact reuse verification and compatibility reuse's original identity/difference/warning;
- immutable simulator occurrence/event/checkpoint/accounting/fidelity content;
- same-attempt interruption resume versus new-attempt failed retry;
- isolated-worker and sole-coordinator-writer protocol without cross-file ACID claims;
- deterministic planning/seed/scheduling semantics independent of completion order;
- complete failure/stop/not-scheduled accounting and bounded evidence;
- scenario timing/safety/fidelity and explicit dependence preservation/destruction; and
- optional `search` installation boundary with stored outputs readable from base.

Plan 15 publishes verified artifacts and analyses but cannot recalculate run identity or
mutate completed source output. Plans 16–17 query public immutable results. Plan 18 must test
worker-count invariance and cannot relax identity/reuse to satisfy performance targets.

## 21. Consistency statement

This plan implements the umbrella experiment hierarchy, identity, reuse, search, local
parallelism, resume, scenario, stress, Monte Carlo, and bootstrap direction. It preserves
the simulators as owners of occurrence content and checkpoints, makes compatibility reuse a
visible relationship rather than identity substitution, and confines project publication
to a verified coordinator handoff owned by Plan 15. No project-level direction is revised.
