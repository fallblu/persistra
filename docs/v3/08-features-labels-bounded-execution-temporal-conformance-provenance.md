# Focused specification 08: Features, labels, bounded execution, temporal conformance, materialization, and provenance

**Status:** implementation plan
**Target:** Persistra 3.0
**Primary packages:** `persistra.research.components`,
`persistra.research.features`, `persistra.research.labels`,
`persistra.research.conformance`, and `persistra.research.materialization`

## 1. Purpose and relationship to the umbrella specification

This plan turns the feature and label direction in the
[v3 umbrella specification](../v3-spec.md) into an implementable contract. It defines one
versioned dependency model for feature and label computation while preserving a hard
capability boundary between information available at a decision and information learned
after it. It also defines the bounded execution interface through which managed and
conforming custom components operate, the exact evidence required by temporal conformance,
and the immutable materializations that later datasets and analyses consume.

Focused specifications 01 through 07 remain normative. In particular, this plan reuses:

- plan-01 typed IDs, UTC instants, durations, canonical serialization, content IDs,
  qualified names, numeric rules, and event envelopes;
- plan-02 project modes, research-database ownership, leases, migrations, settings,
  verified copies, and atomic transaction rules;
- plan-03 immutable dataset revisions, exact market/composite snapshots, public and
  project-knowledge time, safety propagation, and licensing lineage;
- plan-04 instrument identities, calendars, universe evaluations, and decision schedules;
- plans 05 and 06 canonical market/fundamental/estimate/macro/benchmark/rate semantics; and
- plan-07 research-dataset grain, dual cutoffs, typed joins, missing audit, SQL/workspace
  boundaries, information classes, structural eligibility, and safety findings.

A component never reimplements snapshot selection, revision choice, universe membership,
or public/project cutoff logic. Its primary input is an exact completed plan-07 research
dataset build. A feature materialization can then be bound through plan-07's reserved
`feature` input kind. A label materialization can be bound only to an analysis-role
dataset or analysis SQL/workspace context through the reserved `label` kind.

Focused specification 09 consumes feature and label materializations for alpha diagnostics
and owns finance-aware splitting and purging. Specifications 10, 12, and 13 may consume
feature-enriched decision datasets, never label handles. Specification 14 may add attempts
and compatible reuse without weakening exact identity here. Specification 18 owns the
release benchmark and the cross-plan conformance fixture suite.

## 2. Scope

### 2.1 In scope

- Stable feature and label definition lineages with immutable semantic versions
- Typed parameter schemas, output schemas, units, numeric kinds, and assumptions
- One acyclic definition/materialization dependency graph for datasets, features, and labels
- Exact dataset-build binding and transitive snapshot/schedule/cutoff compatibility
- Entity/time grain, evaluation frequency, lookback, warmup, and forecast-horizon contracts
- Managed causal operators with deterministic formulas and missing behavior
- Bounded Python and bounded SQL component interfaces
- Explicit opaque whole-frame/unrestricted execution for research-only use
- Exact temporal-conformance suites and immutable conformance results
- Backward-only feature partitions and explicitly forward-bounded label partitions
- Feature availability transformations and label information intervals
- Structural label isolation across datasets, SQL, workspaces, custom code, and public APIs
- Immutable feature/label materialization metadata, output relations, lineage, and findings
- Exact execution/provenance identity and verified exact retry
- The coherent initial managed feature and label catalog
- Resource ceilings, dataframe boundaries, events, failures, and acceptance tests

### 2.2 Out of scope

- Alpha diagnostics, label-aware splitters, purging, embargo, or model validation
- Signals, forecasts, fitted predictive models, risk models, or portfolio construction
- Simulation-time feature computation or event-engine history APIs
- A hostile-code Python sandbox or proof that arbitrary code is causal
- Distributed execution, remote workers, or a general workflow scheduler
- Automatic compatible reuse across different execution identities
- SQL UDF execution, arbitrary database connections, external table scans, or network access
- Mutation, overwrite, deletion, or compaction of completed definitions/results in 3.0
- Silent adoption of the current v2 in-memory transformer classes as managed v3 features

## 3. Normative decisions

1. A feature and a label are independently registered definitions. Neither is merely a
   specially named dataframe column or workspace table.
2. Definitions are lazy. Registration executes no data query. Materialization binds exact
   definition versions, parameters, dataset builds, dependencies, code/environment, limits,
   and conformance evidence.
3. One typed DAG resolves both feature and label dependencies. A feature node accepts only
   dataset and feature edges. A label node may accept dataset, feature, and label edges.
   Therefore label ancestry cannot exist in a valid feature graph.
4. The initial component entity key is exactly plan-07
   `(decision_at, InstrumentId)`. Managed operators preserve those direct keys or a
   declared schedule subset; they never synthesize, cast, rename into, or deduplicate keys.
5. A feature partition receives the current core rows and only its declared backward
   overlap. It receives no future row, label relation, repository, SQL connection, project
   service, filesystem path, or network client.
6. A label partition is a separate capability. It may receive only the declared bounded
   forward horizon and lookback needed for its label anchors. That capability is never
   constructible from feature, strategy, portfolio, or simulator services.
7. Managed causal operators are safe by construction only when all dependencies are
   causal/safe and the runtime validates their registered operator contract. A bounded
   custom operator may be classified temporally conforming only for the exact code,
   environment, contract, suite, and passing result.
8. Conformance sentinels are evidence against accidental leakage, not a proof about
   adversarial arbitrary code. Unrestricted Python/SQL, external reads, undeclared state,
   or whole-frame access remain opaque and unsafe regardless of test results. SQL UDFs are
   unsupported initially; a future UDF capability starts opaque.
9. A code hash proves byte identity of captured evidence, not completeness of Python
   behavior. User version, source/file manifests, Git state, dependency lock, runtime
   environment, and executor identity jointly describe implementation provenance.
10. Feature availability is never earlier than the maximum availability of evidence it
    used. A declared transformation may add only nonnegative delay. Label availability is
    additionally never earlier than its label interval end.
11. Labels always retain `InformationClass.LABEL`, even if their implementation is
    deterministic, technically safe, and fully conforming. Safety and information class
    remain independent axes.
12. Missing inputs, insufficient history, not scheduled, not yet available, censoring,
    ambiguous future paths, and invalid numeric results are different states. No component
    silently fills, drops, clips, or substitutes values.
13. A completed materialization is immutable and reusable exactly only when its complete
    execution and provenance content match. Friendly names or equal output values do not
    establish reuse.
14. Feature and label physical relations live in distinct migration-owned schemas.
    Physical names, paths, staging objects, and connections are never public handles.
15. Materialization may add safety findings but cannot remove, downgrade, or hide inherited
    findings, information classes, lineage gaps, or licensing restrictions.

## 4. Identity, versions, enums, and public values

### 4.1 Typed IDs

This plan adds these plan-01 typed UUID identities:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `FeatureDefinitionId` | `feature_definition` | Stable lineage for one qualified feature name |
| `LabelDefinitionId` | `label_definition` | Stable lineage for one qualified label name |
| `FeatureMaterializationId` | `feature_materialization` | One immutable feature execution occurrence |
| `LabelMaterializationId` | `label_materialization` | One immutable label execution occurrence |
| `TemporalConformanceResultId` | `temporal_conformance_result` | One immutable exact suite execution |

Feature and label IDs are distinct Python types even where metadata tables use a common
`component_definition_id` column. Materialization and conformance IDs are occurrence
identities, not content hashes. Every definition/materialization/conformance payload also
has separately named plan-01 `ContentId` fields.

### 4.2 Semantic component versions

`ResearchComponentVersion` is the exact ASCII form
`MAJOR.MINOR.PATCH`:

- each component is a base-10 integer in `[0, 2_147_483_647]`;
- leading zeroes are forbidden except for the value zero;
- prerelease/build metadata, a leading `v`, whitespace, and shortened forms are rejected;
- comparison is lexicographic on the three integers; and
- canonical serialization uses the original-equivalent normalized text.

A qualified name has one stable typed definition ID and any number of immutable semantic
versions. New registrations for that name must compare greater than the current version;
skips are allowed. A separate positive, gap-free `registration_sequence` is allocated
per stable ID for event sequencing. Semantic versions express user-facing compatibility;
they do not replace schema versions, content IDs, or execution identity.

Semantic-version intent is enforced:

- patch: documented behavior, implementation, performance, or diagnostics may change only
  when declared input/output semantics and schemas remain compatible;
- minor: backward-compatible parameters or outputs may be added, with existing output
  meanings preserved; and
- major: inputs, output meaning/schema, timing, missing behavior, or parameter compatibility
  may change.

Persistra validates mechanical compatibility but cannot prove economic semantic-version
intent. A false user declaration remains provenance; it never enables cross-version exact
reuse.

### 4.3 Stable enums

| Enum | Values |
| --- | --- |
| `ResearchComponentKind` | `feature`, `label` |
| `ComponentInputKind` | `dataset_field`, `feature_output`, `label_output` |
| `ComponentImplementationKind` | `managed_operator`, `bounded_python`, `bounded_sql`, `unrestricted_python`, `unrestricted_sql` |
| `ExecutionTrust` | `managed`, `temporally_conforming`, `opaque` |
| `PartitionShape` | `row_local`, `entity_time`, `cross_section`, `panel_block` |
| `ComponentDependencyScope` | `entity`, `group`, `panel`, `opaque` |
| `EvaluationFrequencyKind` | `every_base_decision`, `schedule_subset` |
| `HistoryWindowKind` | `none`, `observations`, `elapsed` |
| `AvailabilityTransformKind` | `max_input`, `max_input_plus_delay` |
| `ComponentValueState` | `computed`, `not_scheduled`, `input_missing`, `insufficient_history`, `not_available`, `censored`, `ambiguous_path`, `invalid_numeric` |
| `ComponentMissingKind` | `require_all`, `minimum_valid`, `fail_materialization` |
| `ConformanceStatus` | `passed`, `failed` |
| `HorizonKind` | `decision_steps`, `elapsed`, `event_window` |
| `ElapsedEndpointKind` | `exact`, `first_at_or_after` |
| `LabelOverlapKind` | `may_overlap`, `disjoint_by_construction` |
| `CensoringPolicy` | `censor`, `fail_materialization` |
| `DelistingTreatment` | `censor`, `source_terminal_return`, `fail_materialization` |
| `SameBarBarrierPolicy` | `ambiguous`, `upper_first`, `lower_first` |

`label_output` is valid only on a label definition. Registration of a feature with such
an edge fails structurally before dependency data or SQL is accessed. An unrestricted
implementation always has `ExecutionTrust.OPAQUE`; callers cannot assert a stronger enum.
A bounded custom implementation receives `temporally_conforming` only from the service
after exact conformance and runtime validation, never as a registration argument.

### 4.4 Core public models

Public value objects are frozen, slotted, bounded, and canonically serializable:

```python no-run
@dataclass(frozen=True, slots=True)
class FeatureDefinitionRef:
    name: QualifiedName
    version: ResearchComponentVersion


@dataclass(frozen=True, slots=True)
class LabelDefinitionRef:
    name: QualifiedName
    version: ResearchComponentVersion


@dataclass(frozen=True, slots=True)
class ObservationHistory:
    observations: int
    minimum_valid: int


@dataclass(frozen=True, slots=True)
class ElapsedHistory:
    duration: Duration
    minimum_valid: int


@dataclass(frozen=True, slots=True)
class ComponentMaterializationLimits:
    max_base_rows: int = 25_000_000
    max_output_rows: int = 25_000_000
    max_output_columns: int = 1_024
    max_dependency_nodes: int = 100_000
    max_lineage_items: int = 250_000_000
    core_partition_rows: int = 100_000
    max_partition_rows_with_overlap: int = 500_000
    max_partition_bytes: int = 1_073_741_824
    max_cross_section_rows: int = 1_000_000
    max_lookback_observations: int = 10_000
    max_horizon_observations: int = 10_000
    direct_pandas_rows: int = 2_000_000
    timeout: Duration = Duration(1_800_000_000)
```

Counts and byte/time limits are positive. A no-history component uses a distinct
`NoHistory` value rather than zero observations. `minimum_valid` is positive and cannot
exceed the supplied window. Project hard ceilings may be lower than these request defaults.
Any effective limit change enters execution identity.

## 5. Project, database, and lifecycle ownership

Registration, conformance publication, and materialization require
`ProjectMode.RESEARCH_WRITE`. They write only the research database under its exclusive
plan-02 lease and hold shared leases on every exact market database in the transitive
composite snapshot. Feature/label services never mutate attached market files.
Definition, conformance, materialization, provenance, and bounded dataframe inspection are
available in `read_only` and `research_write` through immutable repository handles.

Research migrations create:

- component definition/version/input metadata in schema `research`;
- conformance, materialization, dependency, row-lineage, and safety metadata in
  `research`;
- immutable dynamic feature relations in migration-owned schema `feature_data`; and
- immutable dynamic label relations in migration-owned schema `label_data`.

The schemas are capability boundaries in addition to storage organization. Callers never
receive raw connections or physical names, and strategy/simulation repositories do not
install label relation adapters. Research SQL may bind an exact label handle only in an
analysis context and retains `InformationClass.LABEL`.

Definitions, versions, conformance results, completed materializations, dependencies,
lineage, and findings are append-only in 3.0. A failed definition registration publishes
nothing. A completed conformance run publishes its pass or fail result because the result
itself is evidence. A failed materialization publishes no materialization, dynamic
relation, lifecycle event, or partially advanced dependency.

Missing nodes in one requested materialization graph are staged and published in
topological order in one research transaction. Already completed exact nodes are verified
and reused. All newly published nodes use one captured publication instant, while their
peer events retain deterministic topological order. A root failure exposes none of the
new nodes. Stale internal staging is handled by plan-02/07 recovery and is never promoted
by inference.

## 6. Definition and version contract

### 6.1 Shared definition fields

Every feature or label version declares:

- stable qualified name, exact semantic version, kind, owner, description, and tags;
- a nonempty `Assumptions and limitations` section;
- ordered typed inputs and an acyclic dependency contract;
- typed parameter schema, defaults, validation, and canonical encoding;
- instrument entity grain and decision-time key meaning;
- evaluation frequency and exact schedule-subset policy when applicable;
- partition shape, cross-sample dependency scope/root contract, history/lookback, and
  warmup;
- availability transformation;
- missing-data and invalid-numeric policies;
- deterministic ordered output schema, units, numeric kinds, nullability, and states;
- implementation kind, implementation identity, execution-trust eligibility, and required
  temporal-conformance suite;
- deterministic ordering/math/runtime policy;
- default materialization limits and licensing/export policy;
- definition schema version, definition content ID, registration sequence, and instant.

A label additionally declares its horizon, label interval, overlap class, censoring,
delisting treatment, and label-availability policy. A feature has no horizon and cannot
declare forward access. A definition has no `latest` dataset/snapshot reference and no
physical table/column name.

### 6.2 Registration and immutability

Version 1 of a qualified name creates its typed stable ID. A later semantic version retains
that ID and allocates the next registration sequence. Registration validates names,
reserved namespaces, exact version monotonicity, schema compatibility, dependency kinds,
parameter defaults, units, lookback/horizon bounds, output names, implementation
capabilities, and canonical-content reproduction.

An exact retry of the same name/version/content returns the stored version and emits no
event. The same name/version with different content is a conflict. A different qualified
name always receives a different stable ID even if all content is otherwise equal.
Renaming therefore creates a new lineage; display metadata may reference its predecessor
without aliasing identity.

No mutable `current` implementation exists. Convenience lookup of the greatest semantic
version is permitted only before a request is frozen. Materialization, dataset binding,
workspace binding, conformance, events, and provenance always store exact ID/version/content.

Registration is explicit through the open project's component services. Importing a module
does not mutate a process-global registry, and users do not edit a built-in dispatch table.
Built-ins are installed from a versioned package manifest; custom implementations are
passed as explicit implementation references whose captured identity enters the registered
version.

### 6.3 Parameters and outputs

Parameter schemas use a versioned, closed type system:

- boolean;
- signed 64-bit integer;
- finite `float64` with canonical bit/negative-zero policy;
- plan-01 `Decimal`, `Duration`, UTC instant, civil date, typed ID, or qualified name;
- a bounded enum owned by the definition; and
- a bounded tuple of one scalar type.

Null, mappings, arbitrary JSON, Python objects, callables, SQL fragments, paths, secrets,
and values with nonfinite floats are not parameters. Optional behavior uses an explicit
enum or option wrapper in the schema. Defaults are canonical values and are expanded before
parameter-content identity is computed.

Output names follow plan-07's lower-snake input-name grammar, cannot start with
`research_`, `feature_`, or `label_`, and are unique within the definition. Each
logical output has:

- dtype and nullability;
- unit and numeric kind;
- description and economic direction when applicable;
- one value column;
- one required `<name>_state` column;
- one required `<name>_reason_code` column;
- one required `<name>_available_at` column; and
- one required `<name>_lineage_content_id` column.

The value and availability are nonnull exactly when state is `computed`. A computed
numeric value is finite. Other states have a typed null value and one stable primary
reason; bounded ordered secondary reasons live in the row-lineage record. Multi-output
definitions may produce different states/availabilities per output but may not omit a
declared output dynamically.

## 7. Inputs and the unified dependency graph

### 7.1 Input ports

Each definition input has a unique name and contiguous positive ordinal:

```python no-run
@dataclass(frozen=True, slots=True)
class ComponentInputSpec:
    name: str
    ordinal: int
    kind: ComponentInputKind
    reference: DatasetFieldSpec | FeatureDependencySpec | LabelDependencySpec
    required_dtype: DataType
    required_unit: Unit
    missing_policy: ComponentMissingPolicy
```

A `DatasetFieldSpec` identifies a logical field and state from the primary exact
plan-07 dataset-build binding. It uses the dataset definition/output field identity and
unit contract, never an internal column string. A materialization validates that the exact
bound build contains a compatible field and that its row keys, snapshot, schedule, cutoffs,
information class, safety, lineage, and licensing manifests are available.
Its dependency-scope evidence retains the owning input projection, entity bridge, and
lineage: plan-07 `global_series` is panel-wide, exact identity/parent bridges remain
entity-scoped unless a registered operator joins entities, and opaque/incomplete field
lineage is never asserted independent.

A feature/label dependency pins an exact definition ID and semantic version, selected
output, canonical parameter bindings, and base-binding rule. The normal base rule is
`same_primary_dataset`: every node resolves against the root materialization's exact
dataset build. A future cross-panel rule requires a new focused contract; matching values
or timestamps are not enough.

Dependency outputs join by exact direct `(decision_at, instrument_id)` keys. A missing
dependency key becomes `input_missing`; there is no implicit backward-as-of or nearest
feature join inside the graph. A schedule-subset consumer may depend on a full-frequency
node. A full-frequency consumer may depend on a subset node only with the resulting
explicit missing states. Lagged use is expressed by the consumer's declared history
window, not by changing key meaning.

Graph resolution propagates required coverage backward through every edge. A dependency
materialization's node-specific interval is the smallest half-open base-decision interval
covering the consumer's core keys plus its declared history/horizon needs; requirements
from shared consumers are unioned before execution. The exact dependency occurrence pins
that expanded interval. Missing coverage is never fetched from another build or silently
treated as a reusable larger/smaller execution.

### 7.2 Allowed graph edges

The initial edge matrix is exact:

| Consumer | Dataset field | Feature output | Label output |
| --- | ---: | ---: | ---: |
| Feature | yes | yes | **no** |
| Label | yes | yes | yes |

An input build for a feature may have plan-07 role `decision` or `analysis`, but its
transitive root closure must be complete enough to prove no label or retrospective
ancestry. A decision-role build is not automatically safe; opaque/unsafe dependencies
remain opaque/unsafe. A label may use either role and always becomes label information.

Registration performs definition-level gray/black cycle detection over exact definition
versions. Materialization repeats cycle detection over exact definition, parameters, base
build, and resolved occurrence nodes. A self edge, a gray node, a dependency that resolves
to current staging, or a hidden label edge in a feature fails structurally. Repeated black
nodes share one exact materialization while retaining ordered occurrence-edge lineage.

### 7.3 Dataset and workspace integration

A feature or label definition is not itself a plan-07 dataset input. The integration object
is an exact completed materialization:

```python no-run
feature_input = FeatureInputRef(
    materialization_id=feature_materialization.id,
    outputs=("momentum",),
)

label_input = LabelInputRef(
    materialization_id=label_materialization.id,
    outputs=("forward_return",),
)
```

A plan-07 feature adapter validates direct key provenance, exact base-build/snapshot/
schedule/cutoff manifests, output availability, selected outputs, and cardinality before
applying the declared temporal join and missing action. A feature materialization can be
structurally decision-eligible only if its feature graph is label/retrospective-free and
its direct keys remain proved. Opaque/unsafe feature materializations may remain
structurally eligible under plan 07 but require the later run-level unsafe override.

An eligible `computed` output becomes plan-07 `selected`/`unsafe`. An
eligible exact row with a noncomputed plan-08 state becomes `component_noncomputed` so
warmup/missing/invalid state survives the dataset missing policy; opaque rows retain their
unsafe finding. A row/output later than the public cutoff becomes evidence-free
`not_available`; its materialized existence cannot leak through the causal audit.
Label censored/ambiguous/noncomputed states use `component_noncomputed` only inside an
analysis-role dataset and retain their closed intervals.

A label adapter exists only for `ResearchDatasetRole.ANALYSIS`. Binding one to a decision
definition, feature definition, strategy SQL context, simulator, or portfolio service
raises plan-07 `ResearchLabelLeakageError` before value access. A workspace can consume a
label only through the general analysis SQL service; the workspace and every descendant
retain label class and structural ineligibility.

Definitions remain lazy. The ordinary workflow explicitly materializes features/labels
from a completed base dataset, then binds exact occurrences to a later enriched dataset.
A convenience `materialize_components(...)` may resolve and publish the missing exact DAG
before invoking that later dataset build, but it cannot create a circular dependency on
the build being produced or leave a friendly definition name in build identity.

## 8. Grain, evaluation frequency, and partitions

### 8.1 Key and frequency

The initial entity grain is one instrument. The time key is the base dataset's exact
`decision_at`; `session_date` is retained metadata and never a join key by itself.
`EVERY_BASE_DECISION` evaluates every included base key, including unusable rows whose
inputs then produce explicit missing states.

`SCHEDULE_SUBSET` pins a plan-04 `SessionDecisionSchedule` and calendar version. Its
decisions must be an exact subset of the base schedule over the materialization interval.
The physical output contains only scheduled base keys; a coverage manifest proves subset
membership and records omitted key counts without inspecting future values. A downstream
plan-07 dataset join restores its own base and audits absent rows.

No initial component resamples to arbitrary civil dates, changes time zones, invents
business days, maps to the nearest decision, or emits more than one row for a base key.

### 8.2 Partition shapes

- `row_local`: each output depends only on fields at the same key; no overlap is supplied.
- `entity_time`: an instrument shard and decision interval plus declared backward history
  for features, or declared forward horizon for labels.
- `cross_section`: all eligible instruments for one or more complete decision instants;
  the executor never splits one decision's cross-section between callbacks.
- `panel_block`: a bounded set of complete entities and decisions for an operator whose
  registered managed contract needs both axes.

Partitions carry immutable typed arrays/dataframes plus metadata; they are not ordinary
project query handles. Core keys are sorted by decision instant then instrument UUID bytes.
Entity-history rows are sorted by instrument UUID bytes then decision instant. Each
partition identifies core rows separately from read-only overlap rows.

The callback may return rows only for core keys and at most one row per key. It cannot
return overlap rows, a key absent from the core, duplicate keys, reordered schema, or
undeclared columns. The executor reorders valid core output canonically before hashing, so
callback order has no semantic effect.

### 8.3 History and warmup

A feature history window is one of:

- `none`;
- `observations(N)`: the current eligible observation plus at most `N - 1` earlier
  observations for that entity, with no calendar-gap inference; or
- `elapsed(D)`: eligible observations with
  `decision_at > current_decision_at - D` and
  `decision_at <= current_decision_at`.

`N` and `D` are positive. An elapsed window uses exact UTC duration arithmetic, not
session counting. A definition separately declares positive `minimum_valid`. Warmup rows
remain present with `insufficient_history`; they are never silently dropped.

For a feature, the runner supplies only backward overlap and never a row whose
`decision_at` is greater than the greatest current core decision for that entity. For a
cross-sectional feature, it supplies only the current decision's cross-section and any
declared backward entity history through a managed two-stage operator. Unsupported mixed
access is opaque rather than approximated.

History outside the declared maximum cannot affect a conforming output. Partition overlap
may contain missing/unusable rows so the operator's declared observation-count policy can
distinguish base decisions from valid values. It cannot silently compress time to only
nonmissing values unless the definition explicitly declares `minimum_valid` reduction
semantics.

### 8.4 Cross-sample dependency scope and relationship roots

Every output declares a `ComponentDependencyScope` contract and every materialized output
row retains its resolved relationship-root manifest. Scope answers which other supervised
samples may be statistically/dependently coupled by the value's actual registered
computation; it is separate from information class, safety, and partition size.

The initial roots are canonical:

- `entity`: the exact `InstrumentId` at the output key;
- `group`: one or more exact causal plan-04 classification/membership or registered
  group-partition identities, hashing the scheme/definition version, group node/value, and
  grouping policy; the row manifest separately proves the selected point-in-time
  membership lineage; and
- `panel`: the primary build's exact base-key/panel manifest shared by all output rows.

`opaque` means the implementation or lineage cannot prove a narrower root. Consumers such
as plan 09 treat it as panel-wide for leakage prevention. A root manifest contains bounded
typed IDs/content IDs, never a friendly category label or copied member list; large
membership evidence remains in the content-addressed lineage store.

Scope is derived under these minimum rules:

- `row_local` and `entity_time` are `entity` only when every selected dataset/component
  input is entity-scoped and the operator performs no cross-entity aggregation;
- plan-07 `global_series`, an all-market cross-section, a cross-entity lag, or an initial
  `panel_block` operator is `panel`;
- `cross_section` may be `group` only when a managed/conforming contract names one exact
  causal grouping input and the executor proves each computation used a complete bounded
  group root; otherwise it is `panel`;
- every dependency edge propagates its stronger resolved scope/root closure; and
- unrestricted execution, unresolved dynamic grouping, incomplete root lineage, or a
  scope-conformance failure is `opaque` even when output values happen to match.

For conservative folding, `entity < group < panel`; `opaque` maps to `panel`. A definition
may declare a stronger scope, but it cannot declare or emit one weaker than its partition,
input, used-row, or operator evidence. Multi-output definitions declare scope per output;
the materialization-level scope is their strongest fold while row lineage keeps the exact
selected-output roots. Group/root order is canonical by scope then content-ID bytes.

Managed operator metadata supplies the scope derivation. Bounded Python/SQL conformance
must include the exact scope/root suite when claiming entity/group; the ordinary temporal
suite alone is insufficient. Runtime validates that used-input masks, partition coverage,
group roots, and emitted root manifests agree. Underdeclaration is structural failure;
unproved narrowing becomes opaque rather than a user assertion.

## 9. Availability, information intervals, and missing states

### 9.1 Feature availability

For one computed feature output at key `k`, let `A_i` be the plan-07 public availability
instant of every source value actually used, including feature dependencies. The managed
base availability is:

```text
A_base(k) = max(A_i)
```

`MAX_INPUT` returns `A_base`. `MAX_INPUT_PLUS_DELAY` adds one declared nonnegative
plan-01 `Duration` with checked UTC arithmetic. No policy can subtract time, use
registration/ingestion as an earlier substitute, or return an instant earlier than an
input. Unknown or opaque availability cannot be made causal by a transformation.

Each output stores `<name>_available_at` independently from materialization
`created_at`. If an exact plan-07 join requests the feature at cutoff `C(d)`, the value
is eligible only when its output availability is no later than `C(d)` and the optional
project cutoff admits the materialization and every dependency. A value computed for key
`d` but available after that cutoff is `not_available`; its later existence or value
is not disclosed in the causal input audit.

Managed/conforming output availability is derived from its validated used-input mask. An
opaque implementation must still produce a nonnull declared availability through the
registered transformation; because its actual read set is unproved, that instant is an
unsafe provenance assertion and never upgrades the output. A consuming plan-07 policy may
admit the opaque value only under its later unsafe path. A definition unable to represent
even a declared conservative availability cannot publish a computed feature value.

### 9.2 Label interval and availability

Every computed or censored label row stores:

- `label_start_at`: the decision/price/event anchor at which prediction begins;
- `label_end_at`: the final instant whose evidence may affect the label;
- `<name>_available_at` for each output: the maximum of `label_end_at`, that output's
  used evidence availabilities, and the declared nonnegative publication delay; and
- exact endpoint/horizon/evidence lineage.

The information interval is closed: `[label_start_at, label_end_at]`. Two labels overlap
when each start is less than or equal to the other's end. Plan 09 uses these stored
intervals for purging; it does not reconstruct horizons from names or row offsets.

A label depending on another label declares an interval that encloses every dependency
interval it uses; materialization takes the closed interval union and rejects a declared
end that would hide later evidence. A censored row records the intended start/end when they
are determinable and no future candidate/value reference beyond causally known label
evidence. A label remains
`InformationClass.LABEL` even after output availability; availability says when the
outcome became knowable, not that it was decision-time information at its start.

For a multi-output label, row-level `label_start_at`/`label_end_at` are the
conservative closed hull of every output's used/intended interval. Per-output lineage
retains its exact narrower evidence range. Plan 09 purges on the conservative row interval
unless it explicitly selects one output and its exact lineage interval; it never assumes
the shortest sibling horizon.

### 9.3 Missing policies and value states

`REQUIRE_ALL` produces `input_missing` if any required input value/state in the declared
window is unusable. `MINIMUM_VALID(n)` computes only when at least `n` valid values are
present and records exact present/expected counts; it never imputes missing positions.
`FAIL_MATERIALIZATION` aborts with bounded evidence on the first canonical partition/
key/output ordering where an input requirement fails.

State meanings are:

- `computed`: a finite/valid value and complete used-input lineage exist;
- `not_scheduled`: the key is outside the declared evaluation subset;
- `input_missing`: a required base/dependency value is absent, unusable, or noncomputed;
- `insufficient_history`: the declared warmup/minimum count is not met;
- `not_available`: required evidence is not eligible at the applicable cutoff;
- `censored`: a label horizon cannot be completed under its censoring/delisting policy;
- `ambiguous_path`: future path ordering cannot be resolved at available granularity;
- `invalid_numeric`: division by zero, nonpositive log input, overflow, incompatible
  units, or another registered numeric precondition fails.

`censored` and `ambiguous_path` are label-only. `not_scheduled` normally appears in
audit for a schedule-subset component rather than its sparse physical output.
`invalid_numeric` is not silently converted to input missing. A definition may make any
nonstructural state fatal but cannot relabel it computed.

No initial policy forward-fills, backfills, zero-fills, mean-fills, interpolates, winsorizes
unless the feature itself is an explicitly named winsorization, drops a row, or substitutes
another provider. State/reason ordering is deterministic and stable.

## 10. Implementation and bounded-execution contracts

### 10.1 Managed operators

A managed operator is shipped and registered by Persistra under a reserved
`persistra.` qualified name. Its implementation is a versioned relational/array kernel,
not caller SQL text or a Python callback. The operator contract fixes:

- accepted partition shape, input/output types, units, and parameter schema;
- dependency-scope derivation, grouping input, and relationship-root schema;
- exact history/horizon and endpoint semantics;
- missing, warmup, availability, and invalid-numeric behavior;
- ordering, tie, quantile, degrees-of-freedom, annualization, overflow, and rounding rules;
- executor/kernel/library component content IDs; and
- formula fixtures and assumptions/limitations.

The executor supplies only validated point-in-time inputs to a feature kernel and validates
the kernel's output keys, schema, states, availability, and lineage. Such a node has
`ExecutionTrust.MANAGED`; its information class is causal only when its operator declares
no forward access and all dependencies remain causal. A managed label retains label
information. Inherited unsafe findings still make the materialization unsafe; “managed”
never launders an unsafe source.

Managed kernels may compile to pinned DuckDB SQL, Arrow-style arrays, NumPy, or Python, but
that is an implementation detail named in provenance. A changed numerical kernel,
DuckDB function behavior, ordering rule, or runtime library identity changes component/
execution identity even if the public definition semantic version remains patch-compatible.

### 10.2 Bounded Python protocol

A bounded Python feature callable implements exactly:

```python no-run
class BoundedFeatureComponent(Protocol):
    def compute(
        self,
        partition: FeaturePartition,
        parameters: ParameterValues,
    ) -> ComponentOutput:
        ...
```

A bounded Python label callable implements a distinct protocol:

```python no-run
class BoundedLabelComponent(Protocol):
    def compute(
        self,
        partition: LabelPartition,
        parameters: ParameterValues,
    ) -> ComponentOutput:
        ...
```

`FeaturePartition` exposes immutable core keys, declared input columns/states/
availabilities, and read-only backward overlap. It has no method for labels, future rows,
querying another interval, resolving a friendly name, or opening the project.
`LabelPartition` additionally exposes only the definition's bounded forward rows and
explicit horizon metadata. The two concrete classes share no public constructor and are
issued only by their owning executor.

The callback receives no:

- project/repository/service object, database connection, relation name, or SQL executor;
- mutable dataframe backed by executor state;
- filesystem path, object store, URL, credentials, environment mapping, or network client;
- label handle in a feature process; or
- whole materialization frame outside the absolute unrestricted path.

Inputs are copies or read-only buffers whose mutation check is part of runtime validation.
The callback returns a `ComponentOutput` builder containing declared outputs/states for
core keys only. It cannot return a pandas index whose meaning is inferred, an object-dtype
payload, arbitrary metadata, a deferred iterator, or a relation/query handle.

This is a cooperative extension boundary for temporal correctness, not a security boundary
against malicious Python. Python code can attempt undeclared process-global, filesystem,
or network activity that a portable in-process library cannot completely prevent. Such
behavior violates the contract, invalidates the conformance claim, and must be registered/
run through the unrestricted opaque path. Deployments may add operating-system isolation,
but its presence does not change the temporal semantics defined here.

### 10.3 Bounded SQL protocol

A bounded SQL component is one parsed `SELECT`, optionally with `WITH`, over exactly one
executor relation `ctx.partition` plus typed scalar parameters. It reuses plan-07's
security gate, external-access denial, parser, type system, function allowlist, limits, and
parameter rules, then adds a stricter component analyzer:

- output keys must be direct unmodified projections of core keys;
- joins, subqueries, set operations, recursive CTEs, sampling, `LIMIT`/`OFFSET`,
  dynamic identifiers, macros, UDFs, and unregistered table functions are forbidden;
- row-local expressions are permitted;
- a feature window may use only the exact declared entity partition/order and
  `ROWS BETWEEN N PRECEDING AND CURRENT ROW`;
- a label window may use only its exact declared bounded following frame;
- cross-sectional aggregates/windows must partition by exact `decision_at`, use the
  registered tie/null ordering, and cannot inspect another decision;
- every aggregate has an explicit missing/minimum-count and numeric rule; and
- the result must contain exactly the declared output/schema for core keys.

User SQL bytes, normalized text content ID, parsed AST, analyzer, function allowlist,
DuckDB version, bindings, and generated partition relation template all enter provenance.
Analyzer acceptance plus conformance is required for
`ExecutionTrust.TEMPORALLY_CONFORMING`. An unsupported construct is not guessed safe.

Plan-07 general research SQL/workspace queries are not bounded SQL components. Wrapping a
workspace query as a definition yields `unrestricted_sql`, retains its full dependency/
analyzer findings, and remains opaque even if the query happens to use a preceding window.

### 10.4 Unrestricted execution

`unrestricted_python` is an explicit analysis-only adapter for a whole-frame callback.
It remains subject to absolute row, column, byte, time, memory, and temporary-storage
ceilings, but it may see the complete requested dataset frame and therefore is temporally
opaque. Its output must still pass schema/key/determinism checks before immutable
publication.

`unrestricted_sql` executes only by materializing an exact plan-07 workspace query and
adapting its exact output. It inherits the workspace's external-access denial; arbitrary
physical SQL is never introduced here. It is opaque because the workspace analyzer cannot
establish the component's declared bounded contract.

SQL UDFs and DuckDB Python replacement scans are unsupported in 3.0. A future UDF
capability would be unrestricted/opaque by default and could not weaken plan-07's SQL
security gate. External file/network reads belong in a registered plan-03 custom dataset,
not a feature callback. Detected or declared external/undeclared reads create an unsafe
finding and prevent a conforming classification.

Materializing any opaque implementation requires
`allow_unsafe_research_materialization=True`. That flag authorizes creation of a visibly
unsafe research artifact; it is not the plan-12/13 simulation override, is persisted in
execution identity, and cannot relabel the result safe or structurally admit a label.

## 11. Temporal conformance

### 11.1 What conformance establishes

Temporal conformance establishes that one exact bounded custom implementation:

- accepts and returns the registered bounded protocol;
- observes declared history/horizon and key boundaries on the conformance fixtures;
- is deterministic under repeated and repartitioned execution;
- does not use a label capability when executing as a feature; and
- satisfies schema, state, availability, missing, dependency-scope/root, and resource
  behavior.

It does not prove arbitrary Python semantics, absence of malicious side effects, economic
correctness, source safety, licensing permission, or equivalence to another implementation.
A passing result can support a causal classification only because runtime also supplies
the structurally bounded feature partition and validates the same exact contract.

### 11.2 Exact suite identity

A conformance request pins:

- definition ID/version/content and canonical parameter cases;
- implementation identity and captured source/Git/environment manifests;
- implementation kind and executor protocol version;
- conformance-suite schema and fixture-set content IDs;
- dependency-scope/root contract and scope-sentinel manifest when a narrow scope is claimed;
- parser/analyzer/operator/function-allowlist identities where applicable;
- partition generator, sentinel generator, comparison, canonicalization, and numeric-policy
  content IDs;
- limits, seeds, platform/runtime identity, and user-supplied implementation version.

The result applies only to that exact tuple. A source byte, dirty Git state, dependency
lock, Python/DuckDB/NumPy/pandas/Persistra version, analyzer, protocol, fixture, parameter
schema, history/horizon, or output-schema change requires another result. Persistra does
not mark an old result “still good” through semantic-version inference.

### 11.3 Required cases

The initial suite executes all applicable cases:

1. **Schema/key:** empty, singleton, normal, all-missing, duplicate-input fault, null-key
   fault, and maximum declared output schemas; outputs are core-key subsets with no
   duplicate, generated, overlap, or future key.
2. **Repeat determinism:** identical input/seed/environment produces identical canonical
   output bytes, states, reasons, availability, and lineage-use masks.
3. **Partition invariance:** different valid entity/time chunk sizes and graph evaluation
   orders produce identical complete materialization roots.
4. **Future sentinel for features:** appending, deleting, or changing rows after each core
   boundary leaves every earlier feature value/state/lineage byte-identical.
5. **Lookback sentinel:** modifying rows strictly before declared backward overlap cannot
   alter core outputs; modifying an eligible row inside overlap changes only allowed keys.
6. **Horizon sentinel for labels:** changing rows after the declared label end cannot alter
   the label; changing a row within the horizon may affect only labels whose closed
   intervals include it.
7. **Entity isolation:** modifying another instrument cannot affect row-local/entity-time
   output that claims entity scope; cross-sectional components may affect only the same
   decision's declared cross-section/group.
8. **Scope/root isolation:** entity/group claims emit the exact expected roots; mutating a
   different entity/group cannot affect output, while mutating an in-root peer may. A
   global-series, panel, incomplete-group, or hidden cross-entity dependency cannot pass as
   entity/group.
9. **Decision isolation:** modifying another decision cannot affect a pure cross-sectional
   output; no following decision affects a feature.
10. **Capability denial:** feature partitions expose no label/future/project/query
   capability; bounded SQL cannot bind anything except `ctx.partition`.
11. **Missing/warmup/numeric:** every state, minimum-valid boundary, division/log error,
    overflow, nonfinite callback output, unit mismatch, and censoring path is exercised.
12. **Availability monotonicity:** outputs never precede used input availability and label
    availability never precedes label end.
13. **Resource/cancellation:** row, overlap, byte, timeout, and output limits stop
    deterministically and publish no materialization.

Sentinel datasets use distinct impossible marker values and IDs, not merely shifted real
values. The suite compares outputs and dependency-use masks, so code cannot pass by
returning a constant while secretly reporting future lineage. A constant implementation
may still be economically useless; conformance is not an alpha-quality test.

### 11.4 Pass, fail, and runtime use

Every completed suite run persists `passed` or `failed`, ordered case outcomes, bounded
failure evidence, and exact identities. It never persists credentials, full licensed
fixtures, arbitrary exception text, or source values beyond licensing-safe sentinel
summaries. A failed result cannot be overridden into passing.

Materialization of a bounded custom component in conforming mode requires one exact passing
result and reruns inexpensive runtime guards on every partition. A runtime violation aborts
publication and records no completed materialization. Callers may instead explicitly choose
opaque research materialization; that choice uses a different execution identity and
retains a conformance-failed/not-applicable finding.

Labels use the same technical suite with forward-horizon cases, but a pass affects only
execution trust and safety findings. Their information class remains label.

## 12. Safety, information class, temporal contract, and provenance

### 12.1 Classification fold

Plan-07 folding rules apply unchanged to every materialization dependency. Local
classification is then added:

| Component condition | Local information class | Local safety |
| --- | --- | --- |
| Managed feature, backward/row-local only | causal | safe |
| Exact conforming bounded feature | causal | safe |
| Unsupported/unrestricted feature behavior | opaque | unsafe |
| Proved future-reading feature behavior | retrospective | structural/reject as a feature |
| Any label implementation | label | safe or unsafe independently |

The final information class is the strongest transitive class
`label > retrospective > opaque > causal`. A feature graph containing label or
retrospective ancestry is rejected rather than published. An opaque/unsafe dependency
makes a feature opaque/unsafe; projection or a conforming child cannot upgrade it.

A full-key feature materialization may preserve `decision_panel` only when the base has
that contract, every dependency shares its exact snapshot/schedule/cutoffs and key
semantics, the output covers the full declared keys, every computed value is eligible at
its key cutoff, and runtime proves uniqueness/direct keys. A schedule subset preserves a
validated decision-panel subset manifest. Delayed or otherwise fixed-availability output
is `point_in_time` unless a later plan-07 join causally aligns it. Opaque behavior yields
`TemporalContractKind.OPAQUE`.

Labels have a typed label-interval contract separate from plan-07 temporal-contract display;
their plan-07 `TemporalContractKind` display value is `opaque`, their summary
information class is label, and they are structurally decision-ineligible in all cases.
`opaque` here does not discard the exact label-interval manifest; it prevents a
future-information interval from masquerading as a decision panel.

### 12.2 Structural label boundary

The label boundary is enforced at all of these layers:

- feature definition registration rejects `label_output`;
- feature graph resolution rejects any transitive label root or unresolved root closure;
- feature executors cannot construct `LabelPartition` or label repositories;
- feature bounded SQL cannot bind label relations;
- plan-07 decision-dataset registration/build rejects label materializations;
- plan-07 workspace descendants retain label class through aliases, SQL, and rematerialization;
- feature adapters reject a workspace/dataset whose complete root closure includes labels;
- strategy, signal, portfolio, vectorized simulator, and event simulator dependency
  containers expose no label service/handle/SQL binding; and
- unsafe overrides reject rather than acknowledge label or retrospective ancestry.

IDs are kind-tagged and repositories validate the stored kind, so passing label UUID bytes
where a feature ID is expected is a typed-kind error. Renaming columns, casting UUIDs,
copying values, hashing, selecting, aggregating, wrapping in custom Python, or claiming
different metadata cannot change dependency-root class.

An arbitrary external Python process can always copy data outside Persistra. This plan's
guarantee applies to managed APIs, persisted lineage, and execution capabilities; it does
not claim to control code after a user deliberately extracts an analysis dataframe.

### 12.3 Implementation provenance

`ImplementationIdentity` records bounded canonical evidence:

- registered implementation qualified name and user-supplied version;
- implementation kind and entry-point/callable label for inspection, not for identity alone;
- content IDs for captured source files/modules or managed kernel/template bytes;
- source-manifest path labels relative to a declared root, sizes, modes, and file hashes;
- Git repository identity when available: commit, branch display, clean/dirty/untracked
  state, tracked-tree content ID, and bounded diff/untracked-file manifests;
- Python, Persistra, DuckDB, NumPy, pandas, parser/analyzer, compiler, and executor versions;
- environment/lock/distribution manifest and platform/architecture details;
- deterministic math, locale, time-zone database, thread, and seed policies; and
- a user assertion describing omitted dynamic state or generated-code inputs.

Absolute source paths, usernames, credentials, environment-variable values, and full diffs
are excluded from ordinary events/logs. Access-controlled provenance inspection may expose
captured source evidence subject to licensing/security policy.

A clean Git commit is not complete code provenance when generated/untracked files or the
environment affect behavior. A dirty tree is permitted for research but its exact bounded
evidence enters identity. If required source/environment evidence cannot be captured,
lineage becomes partial/opaque and the materialization is unsafe. User-supplied versioning
is required for dynamic/not-serializable behavior and remains an assertion, not proof.

### 12.4 Lineage and licensing

Every computed output lineage includes:

- base dataset build/key and exact selected input outcome/field lineage;
- dependency materialization/output/key and definition/parameter identities;
- actual window/horizon key range and a compressed deterministic used-row mask;
- resolved output dependency scope and exact relationship-root manifest;
- operator/implementation, conformance result, partition algorithm, and numeric policy;
- output state/reasons and availability/label interval derivation; and
- inherited safety/licensing manifests.

Lineage refers to content/typed IDs and bounded counts/ranges rather than copying licensed
values. A multi-output component records used inputs per output when they differ. A
`minimum_valid` operator cannot claim all inputs were used merely because they were
present.

Licensing is the most restrictive transitive permission plus any definition-specific
derived-data obligation. Ratios, returns, aggregates, ranks, hashes, model residuals, and
labels are not automatically declassified. Preview, SQL, export, report, and external
provenance inspection enforce the stored manifest independently from safety.

## 13. Materialization API, execution, identity, and retry

### 13.1 Public registration and materialization

```python no-run
feature_ref = project.services.research.features.register(
    FeatureDefinition(
        name=QualifiedName("project.feature.momentum"),
        version=ResearchComponentVersion("1.0.0"),
        description="Compounded price momentum with an explicit skip.",
        assumptions_and_limitations=(
            "Uses the selected adjusted close and observation-count windows; "
            "it does not infer equal elapsed holding periods."
        ),
        inputs=(
            DatasetFieldSpec(
                dataset=ResearchDatasetRef(
                    name=QualifiedName("project.dataset.daily_us_equities"),
                    version=1,
                ),
                output="daily_bar_close",
            ),
        ),
        parameters=momentum_parameters,
        frequency=EvaluationFrequency.every_base_decision(),
        partition=PartitionShape.ENTITY_TIME,
        dependency_scope=ComponentDependencyScope.ENTITY,
        history=ObservationHistory(observations=253, minimum_valid=253),
        availability=FeatureAvailability.max_input(),
        outputs=momentum_output_schema,
        implementation=ManagedOperatorRef("persistra.operator.momentum", version="1.0.0"),
    )
)

feature = project.services.research.features.materialize(
    definition=feature_ref,
    primary_dataset=base_build.id,
    parameters={"lookback": 252, "skip": 21},
    limits=ComponentMaterializationLimits(),
)
```

Labels use `project.services.research.labels.register/materialize` and require a
`LabelDefinition`. The two services return different typed handles. A mixed graph request
is available only through `research.materialization.materialize_graph(...)`, whose root
kind determines its result capability.

Materialization intervals default to the exact primary build interval and may be narrowed
to a half-open `[start_at, end_at)` subset of base decisions. Widening beyond the build,
resolving latest definitions, changing snapshots, or choosing another dataset field by
name similarity is forbidden.

Feature backward overlap and label forward-horizon rows may lie outside that requested
anchor interval but must remain inside the exact primary build. They do not become output
keys for the root or change its `base_key_count`. Dataset-field overlap is read from
the base build; component dependency overlap comes from the exact node-specific expanded
materialization interval resolved under section 7.1. An anchor whose required horizon
extends beyond the primary build censors/fails under policy; the executor never queries a
later unpinned build.

### 13.2 Resolution and execution algorithm

For one root request the service:

1. resolves the exact definition/version/content, complete parameters, primary dataset
   build, requested interval, limits, code/environment, and policy versions;
2. validates the primary build relation/manifest, direct base keys, snapshot, schedule,
   cutoffs, information/safety/lineage/licensing, and project lifecycle;
3. expands exact definition/parameter dependencies, rejects cycles and invalid feature
   label/retrospective roots, propagates/merges node-specific interval coverage and
   dependency scope/relationship roots, and creates a canonical topological graph;
4. resolves exact completed dependency materializations or stages missing nodes against the
   same primary build and each node's exact expanded interval;
5. requires exact passing conformance for bounded custom nodes or records the explicit
   opaque research path;
6. preflights base/output/dependency/lineage/partition/overlap/memory/temp/time ceilings;
7. creates deterministic shape-specific partitions and supplies only registered
   backward/forward overlap;
8. executes nodes in topological then canonical partition order, validating input/output
   keys, schema, states, availability, used-row masks, dependency scope/roots, runtime
   guards, and resource counts;
9. writes transaction-local dynamic output and lineage staging, establishes canonical
   key order, and hashes ordered chunks;
10. verifies row counts, key coverage/subset, no future feature access, horizon bounds,
    dependency-scope/root and output/lineage roots, safety/licensing folds, and exact-retry
    uniqueness; and
11. publishes all new immutable nodes, relations, dependencies, findings, manifests, and
    events in one research transaction.

The service never requires the complete panel in pandas for managed/bounded execution.
DuckDB scans and bounded typed partitions perform orchestration. Partition size, worker
count, dependency insertion order, or hash-map order cannot change values, states, lineage,
availability, output bytes, or content roots.

### 13.3 Execution content

`execution_content_id` hashes canonical schema
`persistra.research.component_execution@1` containing at least:

- component kind, definition stable ID/version/content, expanded parameters, and outputs;
- exact primary research dataset build/definition/execution/output manifests;
- composite/member snapshots, universe evaluation, schedule, cutoffs, interval, and key
  manifest inherited from the primary build;
- canonical topological definition/occurrence dependency graph and exact dependency output
  manifests;
- frequency, partition, dependency-scope/root, history/warmup or horizon, availability,
  missing, numeric, and ordering/tie policies;
- implementation/source/Git/environment identities and exact conformance result where used;
- safety/information/temporal/lineage/licensing policy identities;
- limits, partition algorithm, thread/seed/runtime settings, and materializer component; and
- explicit unsafe-research authorization when applicable.

It excludes the new materialization UUID, publication instant, physical relation/staging
name/path, event ID, and output content root to avoid circular identity. The independently
verified output manifest includes the materialization ID, schema, key range/counts,
canonical ordered chunk IDs, aggregate root, classifications, dependency-scope/root, and
lineage/licensing roots.

### 13.4 Exact reuse, failure, and concurrency

There is at most one completed materialization per component kind and
`execution_content_id`. An exact retry recomputes and verifies definition, dependencies,
dynamic relation, dependency-scope/relationship-root and output/lineage roots, findings,
and licensing before returning it. Any mismatch is corruption, not a cache miss. Equal
values under different input/code/limits/conformance identities are different executions.

Plan 14 may define explicitly compatible reuse, but a compatible result keeps its original
identity and records a reuse edge; it is never returned as this plan's exact execution.

Research writers serialize under the plan-02 exclusive lease. Concurrent identical
requests resolve to one verified result and one event. Readers see the state before or
after the publication transaction, never staging or a partial DAG. Validation, callback,
timeout, cancellation, resource, conformance, hash, or commit failure publishes no
materialization. Bounded diagnostics contain stable reasons, keys/counts/ranges, and
content IDs rather than complete values or arbitrary callback exception text.

## 14. Metadata and physical schemas

### 14.1 Definitions

```sql
CREATE TABLE research.component_definitions (
    component_definition_id UUID PRIMARY KEY,
    component_kind VARCHAR NOT NULL CHECK (component_kind IN ('feature', 'label')),
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE research.component_versions (
    component_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    registration_sequence INTEGER NOT NULL CHECK (registration_sequence >= 1),
    definition_schema_version INTEGER NOT NULL CHECK (definition_schema_version >= 1),
    description VARCHAR NOT NULL,
    assumptions_and_limitations VARCHAR NOT NULL,
    parameter_schema_content_id VARCHAR NOT NULL,
    output_schema_content_id VARCHAR NOT NULL,
    frequency_content_id VARCHAR NOT NULL,
    partition_shape VARCHAR NOT NULL CHECK (
        partition_shape IN ('row_local', 'entity_time', 'cross_section', 'panel_block')
    ),
    dependency_scope VARCHAR NOT NULL CHECK (
        dependency_scope IN ('entity', 'group', 'panel', 'opaque')
    ),
    dependency_scope_contract_content_id VARCHAR NOT NULL,
    history_content_id VARCHAR NOT NULL,
    horizon_content_id VARCHAR,
    availability_policy_content_id VARCHAR NOT NULL,
    missing_policy_content_id VARCHAR NOT NULL,
    implementation_kind VARCHAR NOT NULL CHECK (
        implementation_kind IN (
            'managed_operator', 'bounded_python', 'bounded_sql',
            'unrestricted_python', 'unrestricted_sql'
        )
    ),
    implementation_identity_content_id VARCHAR NOT NULL,
    required_conformance_suite_content_id VARCHAR,
    materialization_limits_content_id VARCHAR NOT NULL,
    licensing_policy_content_id VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (component_definition_id, semantic_version),
    UNIQUE (component_definition_id, registration_sequence),
    CHECK (length(assumptions_and_limitations) > 0),
    CHECK (
        (implementation_kind = 'managed_operator'
            AND required_conformance_suite_content_id IS NULL)
        OR (implementation_kind IN ('bounded_python', 'bounded_sql')
            AND required_conformance_suite_content_id IS NOT NULL)
        OR (implementation_kind IN ('unrestricted_python', 'unrestricted_sql')
            AND required_conformance_suite_content_id IS NULL)
    ),
    CHECK (length(assumptions_and_limitations) <= 65536)
);

CREATE TABLE research.component_inputs (
    component_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
    input_name VARCHAR NOT NULL,
    input_kind VARCHAR NOT NULL CHECK (
        input_kind IN ('dataset_field', 'feature_output', 'label_output')
    ),
    reference_content_id VARCHAR NOT NULL,
    dtype_content_id VARCHAR NOT NULL,
    unit_content_id VARCHAR NOT NULL,
    missing_policy_content_id VARCHAR NOT NULL,
    input_definition_content_id VARCHAR NOT NULL,
    input_definition_json JSON NOT NULL,
    PRIMARY KEY (component_definition_id, semantic_version, input_ordinal),
    UNIQUE (component_definition_id, semantic_version, input_name)
);
```

The repository joins `component_definitions` to validate kind-specific constraints that
cannot be expressed by a local SQL `CHECK`: feature versions have null horizon and no
`label_output`; label versions have a nonnull horizon/overlap/censor/delisting contract.
The nonnull `history_content_id` records either `NoHistory` or bounded pre-anchor
history. A label's nonnull horizon grants only its bounded forward access.
`dependency_scope` is the definition-level strongest output declaration; the contract
content identifies every per-output rule, grouping input/root schema, propagation fold,
and applicable scope-conformance suite.

`semantic_version` is validated by the domain type before insertion and compared by its
parsed integer tuple, never database text ordering. Inputs are contiguous and every
referenced definition version exists before publication. Definition JSON is bounded
canonical representation used for reproduction, not a permissive extension field.

### 14.2 Temporal-conformance results

```sql
CREATE TABLE research.temporal_conformance_results (
    temporal_conformance_result_id UUID PRIMARY KEY,
    component_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    suite_content_id VARCHAR NOT NULL,
    fixture_manifest_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    status VARCHAR NOT NULL CHECK (status IN ('passed', 'failed')),
    case_count INTEGER NOT NULL CHECK (case_count > 0),
    passed_case_count INTEGER NOT NULL CHECK (passed_case_count >= 0),
    failed_case_count INTEGER NOT NULL CHECK (failed_case_count >= 0),
    outcome_manifest_content_id VARCHAR NOT NULL,
    evidence_content_id VARCHAR NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL,
    CHECK (passed_case_count + failed_case_count = case_count),
    CHECK (
        (status = 'passed' AND failed_case_count = 0)
        OR (status = 'failed' AND failed_case_count > 0)
    )
);

CREATE TABLE research.temporal_conformance_cases (
    temporal_conformance_result_id UUID NOT NULL,
    case_ordinal INTEGER NOT NULL CHECK (case_ordinal >= 1),
    case_code VARCHAR NOT NULL,
    passed BOOLEAN NOT NULL,
    observed_manifest_content_id VARCHAR NOT NULL,
    evidence_json JSON NOT NULL,
    PRIMARY KEY (temporal_conformance_result_id, case_ordinal),
    UNIQUE (temporal_conformance_result_id, case_code)
);
```

Case ordinals follow the versioned suite manifest, not callback completion order. Evidence
JSON contains bounded types/counts/ranges/content IDs. The status and its event commit
together. A repeated exact suite execution verifies and returns the existing result; it
does not allocate a second occurrence or event.

### 14.3 Completed materializations

```sql
CREATE TABLE research.component_materializations (
    component_materialization_id UUID PRIMARY KEY,
    component_kind VARCHAR NOT NULL CHECK (component_kind IN ('feature', 'label')),
    component_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    primary_research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    composite_manifest_content_id VARCHAR NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_schedule_content_id VARCHAR NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    parameters_content_id VARCHAR NOT NULL,
    dependency_manifest_content_id VARCHAR NOT NULL,
    dependency_scope VARCHAR NOT NULL CHECK (
        dependency_scope IN ('entity', 'group', 'panel', 'opaque')
    ),
    dependency_scope_manifest_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    temporal_conformance_result_id UUID,
    execution_trust VARCHAR NOT NULL CHECK (
        execution_trust IN ('managed', 'temporally_conforming', 'opaque')
    ),
    partition_contract_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL,
    output_schema_content_id VARCHAR NOT NULL,
    output_relation_name VARCHAR NOT NULL UNIQUE,
    output_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    temporal_contract_kind VARCHAR NOT NULL CHECK (
        temporal_contract_kind IN (
            'decision_panel', 'point_in_time', 'period_panel', 'opaque'
        )
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    structurally_decision_eligible BOOLEAN NOT NULL,
    base_key_count BIGINT NOT NULL CHECK (base_key_count >= 0),
    evaluation_key_count BIGINT NOT NULL CHECK (evaluation_key_count >= 0),
    output_row_count BIGINT NOT NULL CHECK (output_row_count >= 0),
    output_count INTEGER NOT NULL CHECK (output_count > 0),
    computed_value_count BIGINT NOT NULL CHECK (computed_value_count >= 0),
    noncomputed_value_count BIGINT NOT NULL CHECK (noncomputed_value_count >= 0),
    key_audit_count BIGINT NOT NULL CHECK (key_audit_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (component_kind, execution_content_id),
    CHECK (start_at < end_at),
    CHECK (evaluation_key_count <= base_key_count),
    CHECK (output_row_count = evaluation_key_count),
    CHECK (key_audit_count = base_key_count),
    CHECK (
        computed_value_count + noncomputed_value_count
            = output_row_count * output_count
    ),
    CHECK (
        (execution_trust = 'managed'
            AND temporal_conformance_result_id IS NULL)
        OR (execution_trust = 'temporally_conforming'
            AND temporal_conformance_result_id IS NOT NULL)
        OR execution_trust = 'opaque'
    ),
    CHECK (
        (component_kind = 'feature'
            AND information_class IN ('causal', 'opaque'))
        OR (component_kind = 'label'
            AND information_class = 'label')
    ),
    CHECK (
        component_kind = 'feature'
        OR temporal_contract_kind = 'opaque'
    ),
    CHECK (
        NOT structurally_decision_eligible
        OR (
            component_kind = 'feature'
            AND dependency_root_closure_complete
            AND information_class IN ('causal', 'opaque')
        )
    )
);

CREATE TABLE research.component_materialization_dependencies (
    component_materialization_id UUID NOT NULL,
    dependency_ordinal INTEGER NOT NULL CHECK (dependency_ordinal >= 1),
    dependency_kind VARCHAR NOT NULL CHECK (
        dependency_kind IN (
            'research_dataset_build', 'feature_materialization', 'label_materialization'
        )
    ),
    dependency_id UUID NOT NULL,
    dependency_content_id VARCHAR NOT NULL,
    selected_output_content_id VARCHAR,
    dependency_scope VARCHAR NOT NULL CHECK (
        dependency_scope IN ('entity', 'group', 'panel', 'opaque')
    ),
    dependency_scope_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    temporal_contract_kind VARCHAR NOT NULL CHECK (
        temporal_contract_kind IN (
            'decision_panel', 'point_in_time', 'period_panel', 'opaque'
        )
    ),
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    PRIMARY KEY (component_materialization_id, dependency_ordinal),
    UNIQUE (
        component_materialization_id,
        dependency_kind,
        dependency_id,
        selected_output_content_id
    )
);
```

The repository validates that `component_kind` matches the definition's typed ID and
chooses `FeatureMaterializationId` or `LabelMaterializationId` at the public boundary.
Dependency ordinals are canonical topological order with the primary dataset first.
Repeated definition occurrences may point to one dependency ID but selected-output edges
remain distinguishable.

Each dependency row stores that selected edge's resolved strongest scope and bounded root
manifest. The materialization-level fields fold all outputs/edges; exact per-key/output
roots remain in `component_output_lineage`. A primary dataset edge derives roots from its
exact plan-07 projection/entity-bridge lineage. An opaque edge remains opaque through a
managed child.

`base_key_count` is the count of included physical primary-build keys in the requested
interval, including retained unusable rows; universe-ineligible and plan-07 audited-dropped
keys remain in the primary build's audit rather than becoming component inputs.
`evaluation_key_count` is the exact every-decision or proved schedule-subset count.
Output value-state counts reconcile against `output_row_count * output_count`, and the
key-audit count equals the included primary-key count.

The shared plan-07 `research.safety_findings.subject_kind` constraint includes
`feature_materialization`, `label_materialization`, and the later plan-09
`alpha_analysis_result`/`validation_plan` subjects. Findings keep the same immutable
schema, monotone folding, origin-edge, evidence, and uniqueness rules. A conformance
failure used for opaque research becomes a materialization finding; conformance result
rows are not themselves relabeled safety subjects.

### 14.4 Output lineage

```sql
CREATE TABLE research.component_output_lineage (
    component_materialization_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    output_ordinal INTEGER NOT NULL CHECK (output_ordinal >= 1),
    output_state VARCHAR NOT NULL CHECK (
        output_state IN (
            'computed', 'not_scheduled', 'input_missing', 'insufficient_history',
            'not_available', 'censored', 'ambiguous_path', 'invalid_numeric'
        )
    ),
    primary_reason_code VARCHAR NOT NULL,
    evidence_start_at TIMESTAMPTZ,
    evidence_end_at TIMESTAMPTZ,
    output_available_at TIMESTAMPTZ,
    used_input_manifest_content_id VARCHAR,
    dependency_scope VARCHAR NOT NULL CHECK (
        dependency_scope IN ('entity', 'group', 'panel', 'opaque')
    ),
    relationship_root_manifest_content_id VARCHAR NOT NULL,
    lineage_content_id VARCHAR NOT NULL,
    reason_codes_json JSON NOT NULL,
    PRIMARY KEY (
        component_materialization_id,
        decision_at,
        instrument_id,
        output_ordinal
    ),
    CHECK (
        (output_state = 'computed'
            AND evidence_end_at IS NOT NULL
            AND output_available_at IS NOT NULL
            AND used_input_manifest_content_id IS NOT NULL)
        OR (output_state <> 'computed')
    )
);
```

For a causal unavailable/missing feature, evidence fields never reveal a future candidate.
For a label, evidence start/end and used-input manifest describe only the bounded label
interval actually evaluated. Large used-row masks are stored in the content-addressed
lineage manifest store; the table retains its content ID, not an unbounded JSON array.
The relationship-root manifest is present for every output state. A noncomputed causal
feature may contain only roots proved from cutoff-eligible keys/metadata; an unavailable
grouping value cannot leak its later category and therefore folds to a conservative
panel/opaque root. Label roots remain label-classified with the interval evidence.

Schedule-subset omission remains explicit:

```sql
CREATE TABLE research.component_key_audit (
    component_materialization_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    evaluation_eligible BOOLEAN NOT NULL,
    primary_reason_code VARCHAR NOT NULL,
    reason_codes_json JSON NOT NULL,
    base_row_lineage_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        component_materialization_id,
        decision_at,
        instrument_id
    )
);
```

There is one audit row per included primary-build key in the requested interval.
Every-decision materializations mark every key eligible. A schedule subset marks omitted
keys `component.value.not_scheduled`; it does not create dynamic output/lineage rows for
them. Audit counts reconcile exactly with base/evaluation/output counts.

### 14.5 Dynamic feature relation

Each completed feature materialization owns one relation
`feature_data.materialization_<uuidhex>`:

```sql
CREATE TABLE feature_data.materialization_<uuidhex> (
    feature_materialization_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    session_date DATE,
    instrument_id UUID NOT NULL,
    feature_base_row_lineage_content_id VARCHAR NOT NULL,
    feature_safety_status VARCHAR NOT NULL CHECK (
        feature_safety_status IN ('safe', 'unsafe')
    ),
    <name> <declared type>,
    <name>_state VARCHAR NOT NULL,
    <name>_reason_code VARCHAR NOT NULL,
    <name>_available_at TIMESTAMPTZ,
    <name>_lineage_content_id VARCHAR NOT NULL,
    <additional declared output groups>,
    PRIMARY KEY (decision_at, instrument_id)
);
```

There is one complete five-column dynamic group per output. A value and availability are
nonnull exactly for `computed`; a definition whose computed availability is unknown must
be opaque/unsafe and stores the most conservative known bound or fails when no bound can be
represented. The output manifest fixes field order, dtypes, units, numeric kinds, nulls,
states, key subset, and canonical chunk hashes.

### 14.6 Dynamic label relation

Each completed label materialization owns one relation
`label_data.materialization_<uuidhex>`:

```sql
CREATE TABLE label_data.materialization_<uuidhex> (
    label_materialization_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    session_date DATE,
    instrument_id UUID NOT NULL,
    label_start_at TIMESTAMPTZ NOT NULL,
    label_end_at TIMESTAMPTZ NOT NULL,
    label_base_row_lineage_content_id VARCHAR NOT NULL,
    label_safety_status VARCHAR NOT NULL CHECK (
        label_safety_status IN ('safe', 'unsafe')
    ),
    <name> <declared type>,
    <name>_state VARCHAR NOT NULL,
    <name>_reason_code VARCHAR NOT NULL,
    <name>_available_at TIMESTAMPTZ,
    <name>_lineage_content_id VARCHAR NOT NULL,
    <additional declared output groups>,
    PRIMARY KEY (decision_at, instrument_id),
    CHECK (label_start_at <= label_end_at)
);
```

Intended interval endpoints remain present for censored/ambiguous outputs when the
definition can resolve them. A computed output's availability is nonnull and not earlier
than `label_end_at`. No label relation template is installed into a strategy/simulation
repository or attached context.

### 14.7 Physical naming and verification

Relation names are derived solely from the typed materialization UUID, quoted internally,
and accepted from no caller. Feature and label UUID kind tags plus separate schemas prevent
accidental cross-repository lookup. Staging names use an internal operation UUID and are
not persisted as portable identity.

Every output relation is verified in decision/instrument UUID-byte order. Chunk boundaries
are implementation-versioned and deterministic. Empty outputs retain their full dynamic
schema, classifications, manifests, and deterministic empty root. Physical DuckDB plans,
row-group boundaries, paths, and relation names are excluded from public provenance.

## 15. Result handles and dataframe contracts

### 15.1 Feature surface

```python no-run
summary = feature.summary()
rows = feature.rows(max_rows=2_000_000)
provenance = feature.provenance()
dependencies = feature.dependencies()
lineage = feature.lineage(max_rows=2_000_000)
findings = feature.safety_findings()

for chunk in feature.iter_rows(chunk_rows=100_000):
    consume(chunk)
```

A feature handle can create a typed plan-07 `FeatureInputRef`; it does not itself expose
`decision_rows()` or become a simulator input. A plan-07 completed decision dataset owns
the final row restoration, cutoff eligibility, missing audit, and unsafe-run handoff.

### 15.2 Label surface

Label handles expose only the research label service:

```python no-run
rows = label.rows(max_rows=2_000_000)
intervals = label.intervals(max_rows=2_000_000)
provenance = label.provenance()
dependencies = label.dependencies()
lineage = label.lineage(max_rows=2_000_000)
```

`LabelMaterialization` has no `as_feature()`, `decision_rows()`, strategy binding,
portfolio binding, or simulation binding. Its `LabelInputRef` constructor checks that the
target context is analysis role. General research SQL gets a distinct
`LabelMaterializationSqlRelation` whose metadata always marks label information.

### 15.3 Versioned frames

Normal dataframe methods never truncate. Crossing `max_rows` raises
`ComponentResultLimitError`. `preview(rows=N)` is separately named, marked truncated,
and analysis-only. Iterators yield deterministic complete chunks and hold no write
transaction while caller code runs.

| Frame | Schema | Required fields |
| --- | --- | --- |
| Feature rows | `persistra.dataframe.feature_materialization@1` | materialization/decision/session/instrument IDs, base lineage, safety, then ordered output value/state/reason/availability/lineage/scope-root groups |
| Label rows | `persistra.dataframe.label_materialization@1` | materialization/decision/session/instrument IDs, label start/end, base lineage, safety, then ordered output value/state/reason/availability/lineage/scope-root groups |
| Label intervals | `persistra.dataframe.label_intervals@1` | materialization/output/key, closed start/end, availability, state, overlap/censor/delist policies |
| Component lineage | `persistra.dataframe.component_lineage@1` | materialization/output/key/state/reasons/evidence range/availability/used-input, dependency scope, relationship-root, and lineage IDs |
| Component provenance | `persistra.dataframe.component_provenance@1` | definition/version/parameters/base/dependency/snapshot/schedule/cutoff/code/environment/conformance/execution/output/safety/licensing IDs |
| Conformance cases | `persistra.dataframe.temporal_conformance@1` | result/definition/version/suite/case/status/observed/evidence IDs |

Frames use explicit columns, typed-wire IDs, `datetime64[us, UTC]`, Python civil dates,
pandas nullable dtypes, finite `float64`, and stable key/output ordering. Semantic keys
are not hidden in a pandas index. Empty frames preserve exact dtypes and dynamic schemas.

## 16. Initial managed feature catalog

### 16.1 Shared numerical conventions

Every initial managed feature is registered under the displayed
`persistra.feature.*` name at semantic version `1.0.0`. Factories bind parameters but
do not hide them from definition/materialization identity.

Unless a feature below says otherwise:

- input positions are exact base decisions, not compressed nonnull observations;
- prices and denominators must be finite and strictly positive;
- missing exact endpoints produce `input_missing`;
- an incomplete reduction uses its declared `minimum_valid`, otherwise
  `insufficient_history`;
- arithmetic uses finite `float64` under the pinned numeric kernel, with checked
  conversion from source decimals/units;
- no annualization factor is inferred from “daily”; a positive finite factor is explicit;
- no price adjustment is applied inside a feature—the input dataset pins raw/adjusted mode;
- output availability is the maximum used-input availability plus declared delay; and
- ties use the rule stated here, never engine insertion order.

For an entity's ordered base decisions, write `P_t` for the selected price at position
`t`, `r_t = P_t / P_{t-1} - 1`, and
`ell_t = log(P_t / P_{t-1})`. A window of `N` returns ending at `t` is
`t-N+1, ..., t` and therefore requires `N+1` price endpoints when returns are computed
inside the operator.

Sample standard deviation uses divisor `n-1`; population standard deviation uses
`n`. Quantiles use Hyndman-Fan type 7 linear interpolation over values sorted by numeric
value then instrument UUID bytes. The UUID tie order affects deterministic row association,
not the quantile value. Every catalog definition documents units and whether its output is
a level, rate, return, ratio, count, currency amount, or dimensionless score.

### 16.2 Prices, returns, momentum, and reversal

| Definition | Exact output |
| --- | --- |
| `persistra.feature.price` | Direct finite projection of the declared point-in-time price field; identity is useful for uniform graph provenance and never changes raw/adjusted mode |
| `persistra.feature.simple_return` | `P_t / P_(t-k) - 1` for positive integer `k` |
| `persistra.feature.log_return` | `log(P_t / P_(t-k))` for positive integer `k` |
| `persistra.feature.excess_return` | asset simple return minus same-horizon benchmark/risk-free simple return, or asset log return minus same-horizon log return, selected by required `return_kind` |
| `persistra.feature.momentum` | `P_(t-skip) / P_(t-lookback) - 1`, where `lookback > skip >= 0` |
| `persistra.feature.reversal` | negative of `simple_return(k)`; its sign convention is explicit rather than inferred from a “short-term” name |

The two endpoints of a multi-step return must be present at the exact base positions. The
operator never jumps across a missing endpoint to the last valid price. Excess-return
inputs must share currency, interval, return convention, and endpoint schedule. A quoted
annualized yield is first converted to a matching holding-period return by the exact
plan-06 rate policy; subtracting a yield directly is invalid.

`momentum(lookback=252, skip=21)` compares the exact 252nd and 21st prior base positions.
It does not mean calendar months and does not assert equal elapsed holding periods across
instruments with different missing/suspension histories. That limitation appears in every
registered instance.

### 16.3 Volatility, downside, drawdown, skew, and tails

| Definition | Exact output |
| --- | --- |
| `persistra.feature.realized_volatility` | sample standard deviation of `N` one-step log returns times `sqrt(annualization_factor)`; requires at least `max(2, minimum_valid)` |
| `persistra.feature.downside_deviation` | `sqrt(mean(min(r_i - target, 0)^2)) * sqrt(annualization_factor)` over valid simple or log returns |
| `persistra.feature.max_drawdown` | `max_j(1 - P_j / max_(i<=j) P_i)` over the declared price window; a nonnegative magnitude |
| `persistra.feature.return_skewness` | population third central moment divided by population standard deviation cubed over valid returns; requires at least three and nonzero dispersion |
| `persistra.feature.expected_shortfall` | arithmetic mean of returns less than or equal to the type-7 lower quantile at `alpha`, with `0 < alpha < 0.5`; output is a signed lower-tail return |

The volatility annualization factor is a scale convention, not an observed session count.
Drawdown begins with the first valid exact window price and does not use a pre-window peak;
a definition that needs since-inception drawdown declares a correspondingly bounded
lookback. Expected shortfall is an empirical historical feature, not a parametric risk
forecast. Missing-return policy and minimum count enter definition identity.

### 16.4 Liquidity, spread, volume, trade, quote, and activity

| Definition | Exact output |
| --- | --- |
| `persistra.feature.turnover` | per-row `volume / shares_outstanding`, optionally reduced by arithmetic mean over an exact window |
| `persistra.feature.amihud_illiquidity` | arithmetic mean of `abs(simple_return) / dollar_volume` over valid rows; currency unit is retained as inverse currency |
| `persistra.feature.quoted_spread_bps` | `10_000 * (ask - bid) / ((ask + bid) / 2)` with positive quotes and `ask >= bid` |
| `persistra.feature.volume_activity` | exact-window sum or mean, selected by enum, of volume or dollar volume |
| `persistra.feature.trade_activity` | exact-window sum or mean of nonnegative plan-05 `trade_count` |

Volume units, share basis, price currency, quote venue/consolidation, and session/bar
specification must match. Shares outstanding are point-in-time plan-06 facts and split
basis must be compatible with volume. Dollar volume is either the canonical bar value or
`price * volume` under a declared price field; it is never guessed. A zero dollar volume
is `invalid_numeric`, not infinite illiquidity.

Quoted spread is an observed-quote statistic at the dataset's selected timestamp, not an
execution-cost promise. Trade counts reflect provider coverage and feed licensing, not
total market activity unless the source contract says so. Aggregation of arbitrary raw
quote collections is deferred until a collection-valued bounded-input contract exists;
the initial quote feature consumes one plan-07 scalar quote selection.

### 16.5 Fundamental value, quality, profitability, growth, and investment

The initial managed fiscal operators use exact plan-06 report/concept/period/dimension/
unit lineage projected by the base dataset:

| Definition | Exact output |
| --- | --- |
| `persistra.feature.fundamental_ratio` | compatible numerator divided by nonzero denominator at the same decision, with explicit unit/currency conversion |
| `persistra.feature.trailing_fiscal_sum` | sum of the latest `period_count` distinct, consecutive, eligible fiscal periods under a pinned plan-06 period policy; repeated decision rows with the same fact lineage count once |
| `persistra.feature.fundamental_growth` | `current / prior - 1` between exact distinct fiscal periods separated by declared fiscal lag; nonpositive/zero-denominator policy is explicit |
| `persistra.feature.book_to_market` | eligible common-equity value divided by same-decision market capitalization |
| `persistra.feature.gross_profitability` | trailing gross profit divided by the declared average or ending asset basis |
| `persistra.feature.return_on_assets` | trailing net income divided by declared average or ending asset basis |
| `persistra.feature.asset_growth` | total assets divided by exact prior-period total assets minus one |

`trailing_fiscal_sum` rejects overlapping durations, dimension conflicts, duplicate
periods, mixed units/currencies without an exact conversion policy, and nonconsecutive
periods when the selected policy requires continuity. It does not add the same quarterly
fact once per decision at which it remained current. Average balance-sheet basis uses
`(beginning + ending) / 2` only when both exact periods are supplied; it never silently
falls back to ending balance.

The named ratio recipes pin exact plan-06 concept definitions and numerator/denominator
period/basis policies. A project may register other ratios with the generic managed
operator, but a new economic meaning receives its own qualified definition and assumptions.

### 16.6 Estimates, macro, and regimes

| Definition | Exact output |
| --- | --- |
| `persistra.feature.estimate_revision` | current point-in-time consensus statistic minus, or divided by then minus one from, the exact prior eligible statistic for the same measure/target/method over declared history |
| `persistra.feature.estimate_dispersion` | source consensus standard deviation divided by absolute mean when `scaled=true`, otherwise the source standard deviation; requires positive contributor count and exact methodology |
| `persistra.feature.estimate_surprise` | actual minus the last eligible consensus selected strictly before actual publication, optionally divided by a declared positive scale |
| `persistra.feature.macro_level` | direct point-in-time release/vintage value broadcast through plan-07 `global_series` |
| `persistra.feature.macro_change` | exact level difference or ratio-minus-one across declared base positions, retaining release/vintage lineage |
| `persistra.feature.regime_threshold` | registered ordered category from deterministic comparisons of one or more causal macro features to fixed parameter thresholds |

Estimate revision never compares moving targets with different fiscal periods/horizons.
Dispersion uses a source consensus snapshot; recomputation from individual contributors
would be a separately named future operator. Surprise cannot be available before the exact
actual revision and the selected pre-actual consensus are available. Later actual
corrections produce later point-in-time feature values; they do not rewrite a pinned
materialization.

A macro level/change never uses a final vintage for an earlier decision. Threshold regimes
are descriptive deterministic transforms, not fitted hidden-state models. A learned regime
model belongs to later fitted-model plans and cannot be registered as this managed operator.

### 16.7 Cross-sectional transformations

Cross-sectional operators receive all evaluation-eligible rows at exactly one
`decision_at`. They exclude noncomputed input values from the estimation set but retain
their output keys with `input_missing`. The usable count and membership root are in every
row's lineage.

| Definition | Exact output |
| --- | --- |
| `persistra.feature.cross_sectional_rank` | average tie rank; percentile is `0.5` for one value and `(average_rank - 1) / (n - 1)` otherwise; ascending/descending is explicit |
| `persistra.feature.cross_sectional_winsorize` | clip to explicit lower/upper type-7 quantiles with `0 <= lower < upper <= 1` |
| `persistra.feature.cross_sectional_zscore` | `(x - mean) / population_std`; requires declared minimum count and positive dispersion |
| `persistra.feature.cross_sectional_neutralize` | residual from unweighted least squares on an explicit intercept enum and ordered causal exposure columns, using pinned rank-revealing QR/tolerance |

Rank ties compare exact numeric equality after declared conversion; UUID order only makes
row output deterministic and does not break the average tie. Winsorization is an explicit
feature and cannot appear as a hidden missing/numeric policy. Neutralization records design
columns, usable membership, solver/kernel, rank, and tolerance. A rank-deficient design is
`invalid_numeric` unless the definition explicitly selects the pinned column-dropping
policy; no pseudoinverse behavior is inferred from a library default.

### 16.8 Rolling covariance, correlation, beta, and residualization

For paired valid return observations `x_i, y_i`:

- `rolling_covariance` is sample covariance with divisor `n-1`;
- `rolling_correlation` is sample covariance divided by the two sample standard
  deviations and requires both positive;
- `rolling_beta` is sample covariance divided by sample variance of the declared
  benchmark `y`; and
- `rolling_residual` is
  `x_t - (alpha_t + beta_t * y_t)`, where the intercept enum is explicit and
  `alpha_t = mean(x) - beta_t * mean(y)` when enabled.

The regression window ends at the current decision and uses no later return. Paired
missingness is exact: a position contributes only when both values are computed. Minimum
paired count, window, return convention, benchmark identity, intercept, and degrees of
freedom enter identity. Residuals are statistical transformations, not claims of causal
factor structure.

### 16.9 Catalog completeness and extension

This catalog covers the umbrella families with parameterized, composable primitives rather
than hundreds of opaque named indicators. New managed operators require:

- an exact formula and unit/numeric contract;
- availability, history/horizon, missing, tie, and invalid behavior;
- deterministic fixtures and partition-invariance tests;
- an assumptions/limitations section;
- a reserved qualified name/version and operator identity; and
- additive documentation and conformance coverage.

The ten-feature release memory workload in plan 18 must select exact registered instances
spanning returns, momentum, volatility/downside/drawdown, liquidity/activity, and
cross-sectional transforms. Plan 18 owns the final fixture cardinalities and parameter set;
it may not substitute opaque callbacks for these managed operators.

## 17. Initial managed label catalog

### 17.1 Horizon and endpoint rules

Every initial label is registered under `persistra.label.*` at semantic version
`1.0.0`. Its primary anchor is a base decision and its horizon is one of:

- `decision_steps(N)`: the exact `N`th later decision in the same pinned base schedule,
  where `N > 0`;
- `elapsed(D, exact)`: the exact base observation at
  `decision_at + D`; absence censors/fails;
- `elapsed(D, first_at_or_after, max_slippage)`: the first base observation at or after
  the target instant but no later than positive `max_slippage`; or
- `event_window`: a pinned event definition and exact pre/post UTC durations with a
  registered event-to-instrument bridge.

Decision steps are schedule positions, not valid-price positions. An endpoint with a
missing required price is censored or fatal under policy; the operator never skips forward
to a convenient quote. Checked UTC arithmetic and the base calendar resolve elapsed
targets. Endpoint choice and slippage are stored per row.

`MAY_OVERLAP` retains every anchor and its closed interval for plan-09 purging.
`DISJOINT_BY_CONSTRUCTION` is accepted only when the evaluation schedule/horizon proof
shows adjacent intervals do not overlap; it is not a promise asserted by the caller.
Labels do not thin rows implicitly to manufacture disjointness.

### 17.2 Censoring and delistings

At an incomplete horizon:

- `CENSOR` writes a null value with state `censored`, intended interval/end when
  resolvable, and stable reason;
- `FAIL_MATERIALIZATION` aborts atomically with bounded earliest-key evidence.

For an instrument that delists before its horizon:

- `CENSOR` does not use the last quote as a terminal value;
- `SOURCE_TERMINAL_RETURN` requires an exact plan-03 registered source/custom dataset
  value linked to the plan-05 delisting/liquidation event, with compatible currency,
  price-basis, public availability, and lineage;
  or
- `FAIL_MATERIALIZATION` aborts.

Plan-05 action/lifecycle evidence alone is not a terminal return. Zero return, minus-one
return, last observation carried to horizon, benchmark substitution, and present-day
security status are never implicit delisting assumptions. The chosen treatment enters
definition, row state, lineage, and execution identity.

### 17.3 Forward returns and residual returns

| Definition | Exact output |
| --- | --- |
| `persistra.label.forward_return` | simple `P_end / P_start - 1` or log `log(P_end / P_start)`, selected by required return kind |
| `persistra.label.forward_excess_return` | forward asset return minus exact same-interval benchmark/risk-free return of the same return kind |
| `persistra.label.forward_residual_return` | forward asset return minus `beta_start * benchmark_forward_return`, optionally minus causal `alpha_start`; beta/alpha must be exact feature outputs available at label start |

Start/end prices must share the definition's raw/adjusted/action/currency policy. Excess and
residual benchmark endpoints use the same closed label interval and pinned benchmark
definition. Residual coefficients are causal features fixed at the start; they are not fit
using the label interval. The residual label therefore remains a label because its realized
asset/benchmark returns are future outcomes.

### 17.4 Future risk and path labels

| Definition | Exact output |
| --- | --- |
| `persistra.label.future_volatility` | sample standard deviation of one-step log returns strictly after the start through the endpoint, times explicit `sqrt(annualization_factor)` |
| `persistra.label.future_drawdown` | maximum nonnegative drawdown magnitude over prices from start through endpoint, with the start price establishing the initial peak |
| `persistra.label.maximum_favorable_excursion` | maximum signed price-relative excursion over declared high/low/close path fields |
| `persistra.label.maximum_adverse_excursion` | minimum signed price-relative excursion over the same path |

For excursion labels, `side` is explicit `long` or `short`; let `s` be `+1` or
`-1`. Each path observation's excursion is
`s * (path_price / P_start - 1)`. MFE is the maximum and MAE the minimum, so MAE is
normally nonpositive. Long MFE evaluates highs and long MAE lows; short MFE evaluates lows
and short MAE highs under that signed formula. This is a price-relative diagnostic, not a
leveraged/borrow/cost/margin P&L model. High/low provenance, bar interval,
venue/consolidation, adjustment, and missing-bar policy are pinned.

Future volatility needs at least two valid one-step returns. Partial windows are censored,
not annualized from an undeclared count. Future drawdown does not use a peak before the
label start.

### 17.5 Triple-barrier outcome

`persistra.label.triple_barrier` declares:

- a positive upper and lower simple-return magnitude, with `lower < 1`;
- one exact vertical horizon;
- the selected adjusted/raw start price and high/low path fields;
- optional causal side/volatility feature scaling fixed at label start;
- censoring/delisting policy; and
- `SameBarBarrierPolicy`.

For a long-oriented unscaled label, the upper price is
`P_start * (1 + upper)` and lower price is `P_start * (1 - lower)`.
Side/scaling transformations are applied once at start and recorded. Bars are processed in
ascending interval-end order:

1. the first bar touching only upper yields class `1`;
2. the first bar touching only lower yields class `-1`;
3. if neither is touched before the vertical endpoint, class is `0`; and
4. if both are touched first in the same bar, intrabar order is unknowable at bar
   granularity.

The default `AMBIGUOUS` writes null class/state `ambiguous_path`. `UPPER_FIRST` or
`LOWER_FIRST` is an explicit modeling assumption, makes the result unsafe by default,
and appears in every row lineage and assumptions report. It does not claim observed
intrabar ordering. Exact trade/quote paths may define a separate higher-fidelity instance
whose own timestamp/tie policy resolves order.

Outputs include class, barrier-hit instant/bar ID when unambiguous, realized return to hit/
vertical endpoint, and the closed label interval. All outputs share exact path lineage.

### 17.6 Event outcomes

`persistra.label.event_return` binds one registered event family, exact event revision,
event-to-instrument bridge, pre/post window, endpoint policy, and raw/excess/log return
kind. An anchor row can map to at most one logical event under its declared event-selection
policy; multiple eligible events are a conflict, not arbitrary first/last selection.

The label interval covers every observation used from the pre-event start through the
post-event endpoint. Event publication/availability is part of label availability and
lineage. Backdated/corrected event revisions in a later snapshot create a different
materialization; they never rewrite the pinned result.

Other event outcomes require their own typed output/formula contract. Free-form callback
categories are custom labels, not managed event outcomes.

### 17.7 Label catalog limitations

Labels describe observed outcomes under explicit data conventions. They do not model
execution, fills, costs, financing, taxes, borrow, margin, capacity, or portfolio
accounting. MFE/MAE and barriers do not infer intrabar paths. Forward returns do not imply
tradeability at their endpoints. These limitations are included in definition docs and
later alpha/report provenance.

## 18. Resources, determinism, security, licensing, and observability

### 18.1 Default ceilings

| Resource | Managed/bounded materialization | Unrestricted research materialization | Conformance run |
| --- | ---: | ---: | ---: |
| Primary base rows | 25,000,000 | 2,000,000 | 1,000,000 fixture rows |
| Output rows | 25,000,000 | 2,000,000 | 1,000,000 fixture rows |
| Output columns | 1,024 | 1,024 | 1,024 |
| Direct dependency nodes | 256 | 256 | 256 |
| Transitive graph nodes | 100,000 | 100,000 | 100,000 |
| Lineage items | 250,000,000 | 25,000,000 | 25,000,000 |
| Core partition rows | 100,000 | whole frame under row limit | 100,000 |
| Rows including overlap | 500,000 | whole frame under row limit | 500,000 |
| Partition bytes | 1 GiB | 4 GiB absolute | 1 GiB |
| Complete cross-section | 1,000,000 rows | whole frame under row limit | 1,000,000 rows |
| Lookback/horizon observations | 10,000 each | declared but not enforced as a capability | 10,000 each |
| Callback/SQL source text | 256 KiB direct text plus bounded source manifest | 1 MiB direct text plus bounded source manifest | same as definition |
| Canonical cell / row bytes | 1 MiB / 16 MiB | 1 MiB / 16 MiB | 1 MiB / 16 MiB |
| Default timeout | 30 minutes | 30 minutes | 30 minutes |

Project configuration may lower any ceiling. A permitted per-request increase cannot
exceed deployment hard ceilings and enters execution identity. Estimate preflight is an
early guard; runtime row/byte/memory/temp/time counters are authoritative.

A graph exceeding a ceiling fails rather than pruning dependencies. A partition exceeding
the overlap/cross-section ceiling fails rather than shortening history, splitting a
cross-section, dropping entities, sampling, or switching to whole-frame. Output limits
never silently truncate or reduce precision.

### 18.2 Determinism and concurrency

Canonical execution order is:

1. dependency topological order using definition content then parameter/base identity;
2. decision instant, instrument UUID bytes, output ordinal; and
3. registered input ordinal within each row/window.

Parallel workers may execute independent partitions, but publication merges by this order.
Floating reductions use the registered deterministic reduction tree and null/NaN policy,
not worker completion order. Thread count, math kernel, BLAS/LAPACK, architecture, locale,
time-zone database, and seed policy enter environment/execution identity where relevant.

Randomness is unsupported in managed initial features/labels. A custom bounded definition
that legitimately needs pseudorandomness must declare a scalar seed and deterministic
counter-based generator contract; it remains custom and cannot access ambient RNG state.
Unseeded or process-global randomness is opaque and makes exact publication fail if output
reproduction differs.

### 18.3 Output data and code security

Dynamic output types are limited to plan-07's public materialization types: boolean, signed
64-bit integer, finite `float64`, `DECIMAL(p,s)` with `p <= 38`, bounded UTF-8 enum/
string, typed UUID, civil date, and UTC-microsecond timestamp. Nested/object/JSON/blob,
unsigned/128-bit integer, naive timestamp, nonfinite float, arbitrary Python object, and
duplicate/unnamed output columns are rejected. Definition metadata may use bounded
canonical JSON, never analytical object payloads.

Plan-07 SQL external-access denial applies to bounded/unrestricted SQL. Bounded Python
receives no external capability, but Persistra does not claim process isolation against
malicious code. Callback exceptions are mapped to stable phase/reason plus bounded type/
location labels; logs/events do not copy exception messages, source text, dataframe values,
parameters marked sensitive, or credentials.

Source capture follows allowlisted roots and bounded file counts/bytes. It does not traverse
symlinks outside the declared root, read device/special files, or inspect unrelated home/
environment content. Omitted or inaccessible behavior is recorded as partial provenance,
not silently ignored.

### 18.4 Project-knowledge cutoff

When a feature materialization is later bound to a plan-07
`PUBLIC_AND_PROJECT` dataset with fixed cutoff `P`:

- its `created_at` must be no later than `P`;
- its exact definition version, parameter binding, implementation identity, conformance
  result, and every dependency definition/materialization must have been registered/created
  no later than `P`; and
- every transitive canonical source must already satisfy plan-07's project cutoff.

Otherwise the adapter excludes it or records the exact retrospective-definition/project-
knowledge unsafe finding under the consuming policy. It cannot assign the materialization
an earlier creation instant. Public availability still applies independently per output/
decision; project knowledge never makes future public evidence causal.

### 18.5 Observability

Metrics distinguish definition registration, conformance pass/fail/case, graph resolution,
exact hit/verification, node/partition execution, warmup/missing/censor states, opaque
authorization, callback/analyzer rejection, resource/cancellation, lineage counts, and
publication. Metrics/logs are observability only; completed metadata and lifecycle events
are authority.

Cardinality labels are bounded enums and component/content ID prefixes, never user-provided
qualified names, instrument IDs, parameter values, output values, source paths, or full
exception text.

## 19. Events, exceptions, and stable reason codes

### 19.1 Lifecycle events

| Event type | Aggregate kind | Published when |
| --- | --- | --- |
| `persistra.feature.definition_registered@1` | `persistra.aggregate.feature_definition` | A feature semantic version commits |
| `persistra.label.definition_registered@1` | `persistra.aggregate.label_definition` | A label semantic version commits |
| `persistra.component.temporal_conformance_completed@1` | `persistra.aggregate.temporal_conformance_result` | An exact passed or failed suite result commits |
| `persistra.feature.materialized@1` | `persistra.aggregate.feature_materialization` | A verified immutable feature output commits |
| `persistra.label.materialized@1` | `persistra.aggregate.label_materialization` | A verified immutable label output commits |

Definition events use the typed definition ID and aggregate sequence equal to its
gap-free registration sequence, not semantic-version integers. Materialization and
conformance-result IDs are single-occurrence aggregates with sequence 1. Exact retries
emit no duplicate event.

Events contain typed IDs/versions, content/manifests, base build/snapshot, bounded counts,
classifications, bounded dependency-scope/root manifest IDs, and the injected publication
instant. They contain no feature/label values, full code/SQL/diffs, source paths, callback
parameters, credentials, physical relation names, complete relationship member lists, or
complete lineage masks. Definition, conformance result, or materialized state and its
event commit together.

All lifecycle events use the publication transaction's one captured instant for
`event_at`, `available_at`, and `recorded_at`. That event time does not replace
feature public availability, label interval/availability, source time, or decision time.
Topologically published materializations order peer events deterministically under plan 01.

### 19.2 Public exceptions

| Exception | Stable reason code | Trigger |
| --- | --- | --- |
| `ComponentDefinitionError` | `component.definition.invalid` | Definition/version/parameter/output contract is invalid |
| `ComponentVersionConflictError` | `component.version.conflict` | Name/version/content or monotonic-version intent conflicts |
| `ComponentDependencyError` | `component.dependency.invalid` | Edge, cycle, base binding, output, or graph closure is invalid |
| `FeatureLabelDependencyError` | `research.information.label_forbidden` | Direct/transitive label ancestry reaches a feature/decision path |
| `FeatureRetrospectiveDependencyError` | `research.information.retrospective_forbidden` | Retrospective ancestry reaches a feature/decision path |
| `TemporalConformanceError` | `component.conformance.failed` | Exact suite fails or no exact pass exists for conforming mode |
| `ComponentExecutionError` | `component.execution.failed` | Managed/custom execution cannot complete |
| `ComponentContractViolationError` | `component.execution.contract_violation` | Callback/SQL violates keys, overlap, schema, state, or capability |
| `ComponentResultLimitError` | `component.resource.limit` | Rows, bytes, graph, time, memory, temp, or dataframe crosses a limit |
| `ComponentExactReuseError` | `component.reuse.corrupt` | Stored exact materialization/result fails verification |
| `LabelHorizonError` | `label.horizon.invalid` | Horizon, endpoint, overlap, censor, or delisting contract is invalid |
| `LabelPathAmbiguityError` | `label.path.ambiguous` | Policy makes an unresolved path fatal |

Exceptions inherit the plan-01 hierarchy and carry bounded structured context. A top-level
execution error preserves its stable causal exception/reason in diagnostics rather than
replacing it with arbitrary callback text.

### 19.3 Finding and row-state reasons

| Reason code | Meaning/default disposition |
| --- | --- |
| `component.dependency.cycle` | structural/fail |
| `component.dependency.base_mismatch` | structural/fail |
| `component.dependency.snapshot_mismatch` | structural for managed same-base graph |
| `component.dependency.schedule_mismatch` | structural for managed same-base graph |
| `component.dependency.cutoff_mismatch` | structural for managed same-base graph |
| `component.dependency.scope_underdeclared` | structural/fail when declared scope is weaker than proved use |
| `component.dependency.scope_unproved` | opaque/panel-conservative for incomplete root proof |
| `component.dependency.group_root_incomplete` | opaque/panel-conservative or fatal by policy |
| `research.information.label_forbidden` | structural/fail on feature/decision surfaces |
| `research.information.retrospective_forbidden` | structural/fail on feature/decision surfaces |
| `component.execution.opaque` | unsafe |
| `component.execution.external_access` | unsafe/contract failure |
| `component.execution.whole_frame` | unsafe |
| `component.execution.future_access` | retrospective/structural for a feature |
| `component.execution.overlap_violation` | contract failure |
| `component.execution.key_violation` | structural/fail |
| `component.execution.schema_violation` | fail |
| `component.execution.nondeterministic` | fail/unsafe |
| `component.conformance.passed` | evidence only |
| `component.conformance.failed` | fail conforming mode; unsafe opaque mode |
| `component.provenance.partial` | unsafe |
| `component.provenance.opaque` | unsafe |
| `component.value.computed` | successful value |
| `component.value.not_scheduled` | explicit subset audit |
| `component.value.input_missing` | declared missing policy |
| `component.value.insufficient_history` | declared warmup/minimum policy |
| `component.value.not_available` | cutoff-causal absence without future evidence |
| `component.value.invalid_numeric` | declared invalid-numeric policy |
| `feature.availability.after_cutoff` | not available at consuming cutoff |
| `feature.availability.unknown` | opaque/unsafe or fail safe mode |
| `label.value.censored` | declared censoring |
| `label.horizon.incomplete` | censor/fail policy |
| `label.endpoint.missing` | censor/fail policy |
| `label.delisting.censored` | declared censoring |
| `label.delisting.terminal_return_missing` | censor/fail policy |
| `label.path.ambiguous` | ambiguous state or fatal policy |
| `label.path.same_bar_assumption` | unsafe when upper/lower order is assumed |
| `component.resource.limit` | fail |

Plan-07 source/missing/safety reasons are inherited rather than renamed. Definitions may
make a nonstructural state fatal but cannot downgrade a structural/unsafe reason or turn a
noncomputed state into computed. New codes append; persisted meanings do not change.

## 20. Required edge-case behavior

Implementations and reviews must preserve these cases:

- Adding a future row, correction, action, macro vintage, actual, estimate revision, or
  label value cannot change an earlier managed/conforming feature value, state, audit,
  availability, lineage, or content root.
- A feature with 252-position lookback receives exactly backward positions; a partition
  boundary cannot shorten the window or expose position `t+1`.
- Observation lookback counts base decisions, not only nonnull values. Missing endpoint
  prices do not cause return/momentum to jump to another observation.
- An elapsed window across DST/holidays uses exact UTC duration; a decision-step horizon
  uses the pinned schedule rather than civil-day arithmetic.
- Cross-sectional ranks/winsorization/z-scores always use the complete eligible same-time
  cross-section. A resource limit fails instead of splitting it.
- Row-local/entity-time outputs claim entity scope only with entity-scoped inputs;
  global-series/cross-entity/panel dependencies fold panel-wide. A proved causal grouped
  cross-section retains its exact point-in-time group root.
- Missing/opaque group lineage never defaults to the displayed category or entity scope;
  it becomes panel-conservative, and an unavailable future category is absent from causal
  root evidence.
- Equal cross-sectional values receive average rank independent of insertion/partition
  order. A one-value cross-section ranks at 0.5.
- Zero denominators, nonpositive log prices, zero dispersion, singular neutralization,
  nonfinite callbacks, and unit mismatch are explicit invalid states/failures.
- Repeated fiscal facts at multiple decisions count once per exact report/period lineage
  in trailing/growth features.
- Estimate surprise selects consensus strictly before actual availability; a revised actual
  after the pinned cutoff cannot appear earlier.
- A feature with positive availability delay may be computed but is unavailable to an
  earlier/equal cutoff until its exact output availability is admitted.
- A passing conformance result for one dirty-tree/environment state does not apply after
  any relevant source, Git, lock, runtime, suite, contract, or parameter-schema change.
- Conformance partition invariance includes empty/all-missing/core-smaller-than-overlap and
  exact maximum-bound partitions.
- A callback returning a correct value under a future/overlap key still fails key
  validation; output sorting does not legitimize the key.
- Whole-frame Python that happens to use only past rows remains opaque. Bounded Python that
  performs an undeclared external read violates its contract and cannot stay conforming.
- A label definition hidden behind feature aliases, workspace SQL, copied columns, custom
  callbacks, or UUID casts remains label/structurally forbidden.
- A technically safe/passed label never becomes causal. Its availability after horizon
  does not make it usable at the label start.
- A horizon missing its exact endpoint censors/fails; it never selects the last available
  row unless the registered elapsed endpoint rule explicitly allows bounded first-after.
- A delisting never becomes zero/last-price/minus-one return implicitly. Source terminal
  return is used only when exact eligible lineage exists.
- A triple-barrier bar touching both barriers is ambiguous by default. Choosing an order is
  an unsafe modeling assumption, not observed path fidelity.
- Label intervals sharing only an endpoint overlap because intervals are closed.
- Empty base/subset/materialization results retain full schemas, manifests,
  classifications, exact empty hashes, and lifecycle behavior.
- Dependency graph insertion order, requested root order, partition size, worker
  completion, and hash-map order cannot change execution/output identity.
- Exact retry verifies stored output/lineage/findings; it never trusts a matching execution
  content row without checking the dynamic relation.
- Cancellation after staging but before commit leaves no completed node/event. A graph
  request cannot publish dependencies while losing its failed root.
- Project cutoff earlier than definition/materialization/conformance creation cannot be
  backdated into eligibility.
- Licensing restrictions survive ratios, ranks, returns, residuals, labels, previews, SQL,
  and exports independently of causal safety.

## 21. Migration, compatibility, and extension policy

Plan-02 research migrations create the metadata tables, `feature_data`/`label_data`
schemas, dynamic-relation templates, indexes/constraints, recovery records, and the
additive plan-07 safety-finding subject kinds. No migration writes a market database.
Dynamic relations are created only by managed repositories from validated schemas.

This is a greenfield v3 contract. Existing v2 classes in `persistra.features` are
in-memory array/dataframe transformers with no v3 definition, snapshot, availability,
bounded-partition, lineage, or label capability contract. They:

- remain available under their documented v2-compatible APIs during migration;
- are not automatically registered as `managed`;
- may be wrapped explicitly as `unrestricted_python` and remain opaque/unsafe; or
- may receive a new managed v3 definition only after its exact behavior is specified and
  tested under this plan.

Existing pandas frames, pickles, notebook variables, SQL views, and arbitrary workspace
tables cannot be imported as safe feature/label materializations. An importer may preserve
them as opaque analysis artifacts with original bytes/schema/provenance/licensing evidence.

Compatibility rules are:

- changing a definition's semantic version creates immutable version content under the
  same stable ID; changing qualified name creates another stable ID;
- changing parameters, base dataset, interval, dependency, dependency-scope/root,
  code/environment, conformance, limit, partition, numeric, safety, or licensing policy
  creates another execution identity;
- changing managed operator/analyzer/kernel semantics creates another implementation/
  execution identity and never reclassifies an old materialization;
- adding a new output/state/enum/reason is schema/versioned and append-only;
- plan 09 consumes stored label intervals and exact feature/label handles; it cannot
  reconstruct them with ad hoc future SQL;
- plan 10 may introduce fitted model artifacts as feature dependencies only through a new
  typed causal-fit contract; it cannot disguise a label-trained model as a managed feature;
- plan 12/13 own the unsafe simulation override and still reject labels/retrospective roots;
- plan 14 may add attempts/reuse/resume while retaining immutable completed occurrence and
  exact-versus-compatible distinctions; and
- plan 18 owns fixture scale/benchmark invocation but cannot weaken the component contracts.

Future entity grains, collection-valued inputs, distributed partitions, adversarial worker
isolation, UDFs, learned/fitted components, deletions, retention, and compaction require
focused additive contracts. Persisted readers reject unsupported schema/version/kind values
rather than guessing.

## 22. Acceptance tests and exit criteria

### 22.1 Definition, parameters, and graph

- Property tests reproduce semantic versions, definitions, parameters, schemas, units, and
  content IDs across insertion order/process and distinguish every semantic change.
- Registration rejects invalid names/versions, same-version conflicts, empty assumptions,
  noncanonical/default parameters, nonfinite values, invalid outputs, unsupported types,
  missing history/horizon, and implementation/trust mismatches.
- Graph tests cover every allowed edge, direct/transitive feature-to-label rejection,
  retrospective/unresolved roots, cycles, diamonds/shared nodes, exact output selection,
  parameterized dependencies, base mismatch, dependency-scope/root propagation, and
  deterministic topological order.
- Exact retry and concurrent registration produce one version/event; registration
  sequences remain gap-free despite skipped semantic versions and failed transactions.

### 22.2 Managed operator golden tests

- Hand-computed fixtures cover every catalog formula, unit, endpoint, sign, sample/
  population divisor, annualization, quantile interpolation, tie, missing, warmup, and
  invalid-numeric boundary.
- Returns/momentum prove exact position behavior; volatility/downside/drawdown/skew/tails
  cover minimum counts, zero dispersion, price gaps, and nonpositive inputs.
- Liquidity/activity cover zero volume, share basis, currencies, quote locks/crosses,
  provider count coverage, and window reductions.
- Fiscal tests cover amendments, repeated decision visibility, distinct periods,
  continuity, dimensions, currencies/units, TTM, ratios, growth, and denominator bases.
- Estimate/macro tests cover same-target revisions, source consensus dispersion, pre-actual
  surprise selection, later actual corrections, release vintages, and broadcast lineage.
- Cross-sectional tests cover empty/one/all-equal/missing/large sections, average ties,
  type-7 bounds, zero dispersion, singular/exact-rank neutralization, entity/group/panel
  scope derivation, point-in-time membership roots, and opaque fallback.
- Rolling paired tests cover paired missingness, zero benchmark variance, intercept
  convention, window endpoints, and no future observations.

### 22.3 Labels and structural leakage

- Golden labels cover each horizon/endpoint/slippage boundary, overlap proof, closed
  intervals, incomplete endpoints, censor/fail, delisting treatments, and availability.
- Forward raw/log/excess/residual returns cover matching endpoint/basis/benchmark and causal
  start coefficients.
- Future volatility/drawdown and MFE/MAE cover path endpoints, high/low fields, sides,
  partial windows, adjustments, and signed conventions.
- Triple-barrier tests cover upper/lower/vertical first hit, exact boundary equality, both
  barriers in one bar, every same-bar policy, gaps, delistings, and higher-resolution paths.
- Event outcomes cover revisions, conflicts, entity bridges, pre/post windows, availability,
  and multiple events.
- Leakage tests attempt labels through direct feature edges, transitive definitions,
  dataset roles, SQL CTEs/aliases, workspace versions, unrestricted/bounded callbacks,
  copied UUIDs/columns, strategy/service containers, and both simulator override paths.
  Every managed route fails before label value access.

### 22.4 Bounded execution and conformance

- Protocol tests prove feature partitions expose backward overlap only and label partitions
  expose only declared horizons; neither exposes project/query/repository/external handles.
- Sentinel fixtures mutate future, pre-lookback, in-window, other-entity, other-decision,
  other-group, global-series, missing, label, and external capability inputs and assert the
  exact allowed effect set and relationship-root manifest.
- Repartition/property tests vary core/overlap/cross-section sizes, graph/root order, worker
  count, and completion order while reproducing identical output/lineage roots.
- Bounded SQL parser/analyzer fixtures accept the complete registered subset and reject
  joins, later/following feature frames, unbound relations, UDFs, external/physical scans,
  unsupported windows/aggregates, dynamic identifiers, and key changes.
- Conformance identity tests invalidate a pass for every code/Git/environment/suite/
  fixture/protocol/definition/parameter/history/horizon/output change.
- Passing, failing, exact retry, opaque fallback, runtime contract violation, cancellation,
  and bounded failure evidence all have atomic persistence/event tests.
- Tests explicitly document that passing sentinels is evidence, not arbitrary-code proof,
  and never classify unrestricted whole-frame code as conforming.

### 22.5 Materialization, persistence, and APIs

- Exact execution identity distinguishes every base/snapshot/universe/schedule/cutoff/
  interval/dependency/scope/root/code/environment/conformance/partition/limit/policy input.
- Fault injection at every resolution, staging, partition, callback, hash, lineage,
  finding, dynamic relation, metadata, event, and commit step proves all-or-nothing graph
  publication.
- Dynamic relations validate direct unique keys, exact row counts, schema/type/null/state/
  availability/scope/root invariants, deterministic chunks/roots, and empty outputs.
- Concurrent identical/different writers serialize; readers see only complete old/new
  states; reopen/copy verifies relations and reports corruption/missing staging correctly.
- Frame tests assert exact schemas/order/dtypes/UTC/nulls/typed IDs, ordinary limit failure,
  explicit preview truncation, deterministic iteration, and project-lifecycle ownership.
- Public handles expose no raw connection, physical relation/path, mutable safety metadata,
  feature-to-label conversion, or strategy label capability.

### 22.6 Resources, provenance, and licensing

- Row/column/graph/lineage/lookback/horizon/cross-section/overlap/byte/time/memory/temp and
  direct-pandas ceilings fail without sampling, shrinking windows, or partial publication.
- Source/Git/environment manifests cover clean/dirty/untracked/generated/missing evidence,
  symlink/root bounds, safe redaction, and exact invalidation.
- Numeric determinism fixtures pin reduction/tie/solver behavior within one exact
  environment identity; environment changes cannot claim the same execution identity.
- Project-cutoff fixtures independently gate source receipt, definition/conformance/
  materialization creation, and public output availability.
- Licensing tests prove every transformation and dataframe/SQL/export/report boundary
  retains the most restrictive transitive permissions without exposing protected values in
  lineage/events/errors/logs.

### 22.7 Exit criteria

This plan is complete when:

- all public IDs, versions, enums, models, schemas, APIs, events, exceptions, states,
  reasons, limits, and manifests above are implemented and documented;
- the initial managed feature/label catalog passes exact golden and partition-invariance
  fixtures;
- bounded custom Python/SQL can earn only exact evidence-backed temporal conformance while
  unrestricted/external/whole-frame behavior remains opaque;
- feature availability and label intervals/availability reproduce without future-evidence
  leakage;
- structural label exclusion works transitively through every managed dataset, SQL,
  workspace, component, strategy, and simulator path and cannot be overridden;
- immutable materializations, lineage, safety, licensing, events, exact retry, concurrency,
  cancellation, and recovery satisfy the atomic contracts;
- the flagship return/momentum flow and a documented feature/label/alpha input workflow
  operate without full-panel pandas materialization; and
- lint, static types, tests, docs checks, strict docs build, and the agreed coverage gate
  pass.

## 23. Review checklist for dependent plans

Every later plan consuming a component must state:

- exact feature/label definition ID, semantic version/content, parameters, output, and
  materialization occurrence/execution/output manifests;
- primary dataset build, composite/member snapshot, universe, schedule/cutoffs, interval,
  base key, and direct-key/subset proof;
- complete dependency graph and how label/retrospective roots are excluded from every
  decision/strategy path;
- partition shape, dependency scope/relationship roots, history/warmup or
  horizon/endpoints, frequency, missing/numeric, availability, censoring, delisting, and
  overlap contracts;
- implementation kind, source/Git/environment identity, execution trust, conformance
  result, and why sentinels are evidence rather than arbitrary-code proof;
- information, safety/findings, temporal contract, lineage completeness, and licensing/
  export classification without conflating the axes;
- output state/reason/null handling and whether unavailable/missing/censored/ambiguous/
  invalid rows remain visible;
- exact versus compatible reuse, limits, ordering, hashing, dataframe boundary, failure,
  cancellation, and concurrency behavior;
- for labels, closed stored information intervals and the plan-09 purge/embargo use; and
- for simulation, the final plan-07 decision dataset and any recorded unsafe override,
  while proving no label/retrospective ancestry exists.

## 24. Consistency statement

This focused plan implements the umbrella feature/label direction without changing its
project-level guarantees. It deliberately resolves several local choices the umbrella left
open:

- exact managed catalog formulas are the coherent core in sections 16 and 17;
- semantic component versions use strict three-integer versions plus separate gap-free
  registration event sequence;
- labels and features share dependency machinery but never service/storage capabilities;
- custom safety depends on a bounded runtime contract plus exact conformance evidence,
  while unrestricted/external/whole-frame execution stays opaque;
- per-output entity/group/panel dependency scope and relationship roots remain exact
  lineage so plan-09 validation can purge conservatively without guessing from names;
- labels use stored closed information intervals and explicit endpoint/censor/delisting
  semantics; and
- exact materializations bind completed plan-07 base dataset builds, avoiding circular
  dataset/component identities.

Plans 01 through 07 remain authoritative for primitives, project/database state, source
history, snapshots, calendars/universes, canonical domains, dataset joins, SQL/workspace
security, and safety folding. Any later change to those shared contracts must revise the
umbrella and every affected focused plan together rather than silently forking feature or
label behavior.
