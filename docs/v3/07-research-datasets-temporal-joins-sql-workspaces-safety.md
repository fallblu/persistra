# Focused specification 07: Research datasets, temporal joins, SQL, workspaces, and safety

**Status:** implementation-ready greenfield v3 plan

**Depends on:** [focused specification 01](01-domain-identity-time-money-events.md),
[focused specification 02](02-project-databases-leases-copies-migrations.md),
[focused specification 03](03-catalog-ingestion-quarantine-snapshots.md),
[focused specification 04](04-reference-identifiers-calendars-universes.md),
[focused specification 05](05-market-bars-trades-quotes-actions-adjustments.md), and
[focused specification 06](06-fundamentals-estimates-macro-benchmarks-rates.md)

**Owners:** `persistra.research.datasets`, `persistra.research.temporal`,
`persistra.research.sql`, `persistra.research.workspace`,
`persistra.research.safety`

**Required before:** focused specifications 08–18

## 1. Purpose

This plan defines the boundary that turns immutable market snapshots into research rows.
It specifies versioned research-dataset definitions, exact decision schedules and universe
audits, public/project-knowledge cutoffs, cardinality-safe temporal joins, missing-row
behavior, monotone safety findings, bounded pandas access, parameterized read-only SQL, and
controlled workspace materialization with complete lineage.

The dataset builder is the only normal path that may claim a table is structurally usable
as simulation decision data. SQL and workspace APIs remain useful for exploration, but a
query does not become causal merely because it is read-only, parsed, hashed, or persisted.
Label and retrospective dependencies stay structurally excluded from decision datasets;
opaque lineage may be explored and may later enter a simulation only through the explicit
unsafe override owned by the simulation plans.

## 2. Scope and boundaries

### 2.1 In scope

- Versioned instrument-decision research-dataset definitions and immutable completed builds
- Exact composite snapshots, universe evaluations, decision schedules, and output grain
- Per-decision public cutoffs and optional fixed project-knowledge cutoffs
- Snapshot/revision/source-precedence selection before temporal joining
- Identity, parent-entity, and explicitly bounded global-series bridges
- Exact, backward-as-of, and effective-interval joins with complete tie-breakers
- One-row-per-instrument-decision enforcement and many-to-many prevention
- Explicit missing-input actions, row retention/loss audit, and selected-row lineage
- Safety, information-class, temporal-contract, licensing, and provenance propagation
- Bounded dataframe/chunk APIs and versioned public schemas
- One-statement parameterized read-only SQL over typed operation-context relations
- Static SQL dependency/safety analysis and explicit opaque classification
- Immutable, versioned workspace materializations created only from `SELECT`
- Research-role schemas, transactions, events, failures, limits, and acceptance tests

### 2.2 Out of scope

- Feature or label definitions, implementations, dependency execution, and cache reuse
- Python/custom-SQL temporal conformance and bounded custom component execution
- Feature/label materialization tables and provenance beyond the integration contract here
- Alpha diagnostics, cross-validation, portfolio construction, or simulation
- Arbitrary dataframe upload as a substitute for registered custom-data ingestion
- Direct SQL writes, raw connections, user DDL/DML, arbitrary schemas, or external scans
- A general SQL sandbox or proof that arbitrary relational logic is causal
- Distributed execution, a workflow scheduler, server access, or multi-user workspaces
- Deletion/compaction of completed dataset builds or workspace versions in 3.0

Focused specification 08 implements feature/label inputs and managed/custom execution on
this builder boundary. It does not weaken the snapshot, cutoff, information-class,
row-grain, audit, or lineage rules here.
Focused specification 09 consumes analysis datasets; specifications 12 and 13 consume
decision datasets and own the unsafe-run override.

## 3. Normative decisions

1. A completed research dataset is an immutable build, not a moving query over latest data.
2. Every build pins one exact plan-03 composite snapshot and one exact compatible plan-04
   universe evaluation. Convenience resolution happens before build identity is computed.
3. The initial decision-row grain is exactly `(decision_at, InstrumentId)`. Issuer,
   security, macro, benchmark, and rate inputs reach it only through declared bridges.
4. A public cutoff is resolved separately for every decision and cannot follow that
   decision. The optional project cutoff is one fixed instant for the complete build.
5. Revision/snapshot eligibility and source precedence are resolved before temporal join
   ranking. Insertion order, current state, and generic latest-ingested wins are forbidden.
6. Every joined input produces at most one logical candidate per base row. One-to-many
   observations must be narrowed by a domain-owned scalar selection/aggregate. Plan 08's
   initial components consume scalar dataset fields; they do not legitimize accidental row
   multiplication or arbitrary raw-collection aggregation.
7. Missing, source-missing, retracted, conflicted, unsafe, and not-evaluated are distinct.
   Carry, fill, coalescing, and row deletion never occur without a versioned policy.
8. Strategy-visible rows and counts contain only cutoff-eligible evidence. A later row's
   existence cannot leak through a missing reason, coverage count, lineage ID, or audit.
9. Safety findings are immutable and monotone through dependencies. Materialization may add
   findings but can never remove, downgrade, or relabel inherited findings.
10. `label` and `retrospective` information are structurally forbidden from a decision
    dataset and cannot be admitted by an unsafe override. `opaque` is different: it is
    unsafe, remains visibly tainted, and may be admitted only by a later run-level override.
11. Read-only SQL is one parsed `SELECT` over typed context relations. Read-only describes
    database mutation capability, not temporal safety.
12. SQL text, bindings, dependency resolution, analyzer/code identity, snapshots, temporal
    contract, output schema, and inherited findings enter workspace execution identity.
13. Workspace names are conveniences over immutable versions. Managed consumers resolve a
    name to an exact materialization before computing their own identity.
14. Market files remain read-only. Dataset/workspace publication changes only the research
    database in one final transaction under its exclusive lease.

## 4. Identity, enums, and public value surface

### 4.1 Typed IDs

This plan adds these plan-01 typed UUID identities:

| Type | Kind token | Meaning |
| --- | --- | --- |
| `ResearchDatasetId` | `research_dataset` | Stable versioned dataset-definition lineage |
| `ResearchDatasetBuildId` | `research_dataset_build` | One immutable completed dataset execution |
| `WorkspaceObjectId` | `workspace_object` | Stable user-facing workspace-name lineage |
| `WorkspaceMaterializationId` | `workspace_materialization` | One immutable workspace object version |
| `SafetyFindingId` | `safety_finding` | One immutable research safety/structure finding |

Definition and workspace versions are positive integers scoped to their stable ID. A build
and a workspace materialization are immutable lifecycle occurrences. Content IDs identify
definitions, query text, parameter sets, dependency/lineage manifests, schemas, execution,
and output manifests; none replaces the relational UUID.

### 4.2 Stable enums

| Enum | Values |
| --- | --- |
| `ResearchDatasetRole` | `decision`, `analysis` |
| `CutoffMode` | `public`, `public_and_project` |
| `ResearchInputKind` | `canonical`, `workspace`, `feature`, `label` |
| `InformationClass` | `causal`, `opaque`, `retrospective`, `label` |
| `TemporalContractKind` | `decision_panel`, `point_in_time`, `period_panel`, `opaque` |
| `EntityBridgeKind` | `identity`, `issuer_parent`, `security_parent`, `global_series` |
| `TemporalJoinKind` | `exact`, `backward_asof`, `interval_contains` |
| `AsOfAgeMode` | `bounded`, `explicit_unbounded` |
| `MissingInputAction` | `retain_null`, `mark_unusable`, `drop_with_audit`, `fail_build` |
| `InputOutcome` | `selected`, `component_noncomputed`, `source_missing`, `not_available`, `retracted`, `conflict`, `unsafe`, `not_evaluated` |
| `SafetyStatus` | `safe`, `unsafe` |
| `SafetySeverity` | `warning`, `unsafe`, `structural` |
| `LineageCompleteness` | `complete`, `partial`, `opaque` |
| `SqlTemporalClass` | `row_local`, `opaque` |

Plan 08 enables the `feature` and `label` input kinds with exact completed
materialization references. Registration still rejects either kind when its owning
capability/migration is unavailable.
`CutoffMode` and `PublicCutoffPolicy` are owned by plan 04 and reused unchanged here;
`CutoffMode.PUBLIC_AND_PROJECT` serializes as `public_and_project`.

### 4.3 Immutable public models

Core value objects are frozen, slotted, bounded, and canonicalizable:

```python no-run
@dataclass(frozen=True, slots=True)
class ResearchDatasetRef:
    name: QualifiedName
    version: int


@dataclass(frozen=True, slots=True)
class ResearchCutoffSpec:
    mode: CutoffMode
    public_policy: PublicCutoffPolicy


@dataclass(frozen=True, slots=True)
class ResearchBuildLimits:
    max_base_rows: int = 25_000_000
    max_output_rows: int = 25_000_000
    max_columns: int = 1_024
    partition_rows: int = 100_000
    max_lineage_items: int = 250_000_000


@dataclass(frozen=True, slots=True)
class SqlReadLimits:
    max_rows: int = 1_000_000
    max_columns: int = 1_024
    max_dependency_nodes: int = 100_000
    max_findings: int = 1_000_000
    chunk_rows: int = 100_000
    timeout: Duration = Duration(300_000_000)


@dataclass(frozen=True, slots=True)
class WorkspaceMaterializationLimits:
    max_output_rows: int = 25_000_000
    max_columns: int = 1_024
    max_dependency_nodes: int = 100_000
    max_findings: int = 1_000_000
    chunk_rows: int = 100_000
    timeout: Duration = Duration(300_000_000)
```

Plan-04 `PublicCutoffPolicy.at_decision()` is zero lag;
`PublicCutoffPolicy.lagged(Duration(...))` resolves `C(d) = d - lag`. These are the only
initial policies and their canonical schema/content identity enters every schedule.
`ResearchCutoffSpec.public(...)` and `public_and_project(...)` set the matching enum and
validate that policy. The latter makes `project_cutoff_at` mandatory on each build request
rather than embedding a moving receipt time in the definition.

Positive limits and the project memory/temporary ceilings are validated before execution.
Increasing a limit changes execution identity; it never turns an unbounded operation into
a supported path.

## 5. Database ownership and lifecycle

Dataset-definition registration, builds, and workspace materialization require
`ProjectMode.RESEARCH_WRITE`. They use the research database under its exclusive lease and
every selected market database under a shared lease. Dataset rows, workspace physical
relations, lineage, findings, and events publish in one research-database transaction. No
operation writes an attached market database or requires a cross-file transaction.

Read-only SQL and dataset inspection are available in `read_only` and `research_write`.
Each operation owns a stable read transaction, exact composite snapshot, bounded query
context, and repository handles; no connection or physical relation name escapes. A
research-write project still treats attached `market_<name>` databases as read-only under
plan 02.

Definitions, completed builds, workspace versions, lineage rows, and safety findings are
append-only in 3.0. Friendly workspace-name resolution may advance to a new immutable
version through the managed API, but older versions and dependencies remain addressable.
An exact execution-content retry verifies and returns the existing build/materialization.
A different definition, snapshot, cutoff, query byte, binding, dependency, environment,
limit, or schema creates a different execution identity.

Large builds use deterministic decision/entity partitions and transaction-local staging.
Only the final verified physical relation and metadata become visible at commit. A crash or
failure leaves no completed metadata; stale internal staging is diagnosed and removed on a
later research-write open only when no completed object references it.

## 6. Research-dataset definition contract

### 6.1 Definition fields

A `ResearchDatasetDefinition` declares:

- qualified name, positive definition version, role, description, and owner;
- exact base entity kind (`instrument` initially) and row key;
- versioned plan-04 universe definition and decision-schedule specification;
- half-open observation/build interval semantics;
- `CutoffMode`, public-cutoff policy, and project-cutoff requirement;
- ordered typed inputs with projection, information class, entity bridge, temporal join,
  source precedence, domain policy, and missing action;
- deterministic output names, units, nullable dtypes, and schema version;
- default build limits and licensing/export classification; and
- definition schema version, canonical content ID, registration instant, and code identity.

The definition does not contain `latest` snapshot state. `build()` receives an exact
`CompositeSnapshotId`; a convenience method may first resolve/create a composite snapshot
and then call the same exact path. Definition changes append a version. A change to row
meaning, universe/schedule, cutoff policy, join semantics, missing action, output meaning,
or information class is breaking for cached output and therefore changes definition/
execution identity.

All initial dataset definitions require a plan-04 instrument universe and the same
instrument-decision base grain. Plan 08 label inputs are analysis-only:
`role=decision` rejects `InformationClass.LABEL` and
`RETROSPECTIVE` anywhere in the transitive dependency graph before any value query runs.

### 6.2 Ordered input contract

Each input has a unique ASCII name matching `[a-z][a-z0-9_]{0,62}`, a positive ordinal,
and one typed reference:

```python no-run
@dataclass(frozen=True, slots=True)
class ResearchInputSpec:
    name: str
    kind: ResearchInputKind
    information_class: InformationClass
    reference: CanonicalInputRef | WorkspaceInputRef | FeatureInputRef | LabelInputRef
    projection: OutputSchema
    entity_bridge: EntityBridgeSpec
    temporal_join: TemporalJoinSpec
    source_precedence: SourcePrecedenceRef | None
    missing_action: MissingInputAction
```

The referenced values are the following closed public contracts (Plan-03 owns
`SourcePrecedenceRef`):

```python no-run
@dataclass(frozen=True, slots=True)
class DomainQueryRef:
    contract_name: QualifiedName
    contract_version: int
    parameters_content_id: ContentId

@dataclass(frozen=True, slots=True)
class CanonicalInputRef:
    dataset_name: QualifiedName
    dataset_version: int
    query: DomainQueryRef

@dataclass(frozen=True, slots=True)
class WorkspaceInputRef:
    materialization_id: WorkspaceMaterializationId
    object_version: int
    output_manifest_content_id: ContentId

@dataclass(frozen=True, slots=True)
class FeatureInputRef:
    kind: Literal["feature"]
    materialization_id: EntityId
    definition_name: QualifiedName
    definition_version: ResearchComponentVersion
    output_names: tuple[str, ...]
    output_manifest_content_id: ContentId
    relationship_root_content_id: ContentId

@dataclass(frozen=True, slots=True)
class LabelInputRef:
    kind: Literal["label"]
    materialization_id: EntityId
    definition_name: QualifiedName
    definition_version: ResearchComponentVersion
    output_names: tuple[str, ...]
    output_manifest_content_id: ContentId
    relationship_root_content_id: ContentId

@dataclass(frozen=True, slots=True)
class OutputFieldSpec:
    source_name: str
    output_name: str
    dtype: Literal["bool", "int64", "float64", "decimal", "string", "instant", "date", "id"]
    nullable: bool
    unit: UnitSpec | None
    state_output_name: str | None
    reason_output_name: str | None

@dataclass(frozen=True, slots=True)
class OutputSchema:
    fields: tuple[OutputFieldSpec, ...]

@dataclass(frozen=True, slots=True)
class EntityBridgeSpec:
    kind: Literal["identity", "issuer_parent", "security_parent", "global_series"]
    parent_policy_name: QualifiedName | None = None
    parent_policy_version: int | None = None
    parent_policy_content_id: ContentId | None = None
    global_series_content_id: ContentId | None = None

@dataclass(frozen=True, slots=True)
class TemporalJoinSpec:
    kind: Literal["exact", "backward_asof", "interval_contains"]
    base_anchor: Literal["decision_at", "session_open", "session_close"]
    input_anchor: str
    max_age: Duration | None
    explicit_unbounded: bool = False
```

Names use the input-name grammar and are unique; `OutputSchema.fields` is nonempty and
ordered, output names are unique, `unit` is required for numeric fields, and state/reason
siblings are both present or both absent. `identity` forbids all optional bridge fields;
`issuer_parent` and `security_parent` require all three parent-policy fields and use the
effective Plan-04 relationship at the join anchor; `global_series` requires only the exact
singleton series content ID.
`exact` requires equal anchors and no age bound; `backward_asof` requires exactly one of a
positive `max_age` or `explicit_unbounded=true`; `interval_contains` requires a domain
effective interval and the same explicit bound choice. `parameters_content_id` resolves a
registered, schema-validated domain query parameter object—never arbitrary JSON—and its
contract must be owned by the referenced dataset/version. Unknown union values, unused
variant fields, empty projections, or mismatched component kinds fail registration with
`ResearchDatasetDefinitionError` before any query.

A canonical reference includes the exact registered dataset/version and domain query
contract, not a table/column string. Depending on its owner it pins, as applicable:

- instrument/venue/calendar/resolution and raw condition/status policies;
- bar specification, raw/adjusted mode, action revisions, adjustment policy, and segments;
- filing mode, normalization mapping, fiscal/period/dimension/unit semantics;
- estimate measure/target/method/contributor/actual and share basis;
- macro series/release/vintage/completeness/period policy;
- benchmark kind/version/calendar/methodology/return policy; or
- risk-free curve/version/tenor/quote/compounding/day-count/conversion policy.

The domain owner supplies a registered bounded query adapter that returns a common candidate
envelope plus typed values. Dataset code never reconstructs domain meaning from arbitrary
column names. A source-precedence reference is required when multiple providers may be
eligible; field-wise provider coalescing remains forbidden.

The adapter contract is typed and shared by every canonical domain:

```python no-run
class DomainQueryAdapter(Protocol):
    def candidates(
        self,
        reference: CanonicalInputRef,
        context: AsOfContext,
        entities: tuple[EntityId, ...],   # bounded resolved keys for one partition
        value_interval: TimeInterval,     # bounded value-time window
    ) -> Iterator[CandidateEnvelope]: ...

@dataclass(frozen=True, slots=True)
class CandidateEnvelope:
    entity_id: EntityId
    natural_key_content_id: str
    canonical_revision_id: uuid.UUID
    revision_ordinal: int
    source_id: uuid.UUID
    value_time: datetime                    # the domain-owned anchor (section 10.1)
    effective_interval: TimeInterval | None
    available_at: datetime
    availability_quality: AvailabilityQuality
    state: str                              # value / source_missing / retracted / unavailable / conflict
    state_reason_code: str | None
    state_evidence_content_id: str | None
    information_class: InformationClass
    values: Mapping[str, object]            # declared output name -> typed value
    unit_specs: Mapping[str, UnitSpec]
    safety_finding_content_ids: tuple[str, ...]
    licensing_class: str
    lineage_content_id: str
```

Plans 04, 05, and 06 each register exactly one adapter per canonical dataset qualified
name they own (reference/calendars/universes, bars/trades/quotes/status/actions, and
fundamentals/estimates/macro/benchmarks/rates respectively; adjusted prices are a mode of
the bar adapter per section 9.1, not a separate dataset).
Registration validates that the adapter declares its value-time anchor, its complete
typed output list with `UnitSpec`s, and the section-9 selection order; the builder rejects
an input whose dataset has no registered adapter.

`source_missing` is valid only for an explicit cutoff-eligible nil/no-trade/no-value source
row. It requires both `state_reason_code` and `state_evidence_content_id`, carries typed null
values, and is the state used by Plan-05 `no_trade` and Plan-06 `is_nil` adapters. Mere row
absence produces no envelope and becomes `not_available`; `unavailable` is reserved for an
explicit row whose value cannot be supplied for another declared reason.

A workspace reference pins an exact `WorkspaceMaterializationId`, object version, output
manifest, selected columns, and dependency/safety manifest—not a friendly name. A
decision-role definition accepts it only when it is structurally decision-eligible under
section 12.3 and the declared join can map its direct primary decision keys to the build
base without cardinality ambiguity. Snapshot, schedule, cutoff, temporal, or lineage
mismatches remain exact unsafe/opaque findings rather than disappearing; an unrelated or
synthesized key and any label/retrospective ancestry are structural failures. The resolved
occurrence graph must be acyclic. A feature/label reference pins an exact plan-08
materialization ID, definition/version, selected outputs, output/availability/interval
schema, dependency-scope/per-output relationship-root, dependency/safety/licensing
manifests, and direct base-key manifest. A label
reference is accepted only by an analysis-role definition.

A feature adapter accepts `exact` or `backward_asof`, not
`interval_contains`. It validates direct base-key membership, then considers only rows
at or before the join anchor whose selected output availability is no later than the row's
public cutoff; backward-as-of also enforces the declared maximum age. A later/unavailable
output yields evidence-free `not_available`. An eligible `computed` output is
`selected`/`unsafe`; an eligible noncomputed output is
`component_noncomputed` with its exact plan-08 state/reason/lineage. Causal component
evidence obeys the no-future rule; opaque component evidence retains its unsafe finding and
later requires the run-level override. The plan-08 `not_available` state remains
evidence-free at a decision boundary.

A label adapter accepts only `exact` on the direct anchor keys and only for an analysis
dataset. It intentionally does not compare label availability with the prediction-start
public cutoff; doing so would erase the future outcome the analysis dataset requested.
Instead it retains the exact closed label interval, output availability, state, lineage,
and `InformationClass.LABEL`. Fixed project cutoff still requires the label
materialization, definition/conformance evidence, and all used source evidence to have
been project-known by `P`. This path is absent from decision builders and cannot be
enabled by an unsafe override.

The owning adapter/materialization supplies the minimum information, safety, temporal,
lineage, and licensing classifications. A definition may impose a stricter information or
missing policy, but registration/build rejects any declaration that would weaken, erase, or
contradict the resolved dependency metadata.

Projection names are prefixed by the input name unless an explicit collision-free alias is
registered. Reserved base/audit names begin with `research_` and cannot be shadowed. Every
projected analytical value has a unit/numeric-kind contract and a sibling input-state field
unless its schema is structurally nonnullable and `fail_build` is the missing action.

### 6.3 Example definition

```python no-run
definition = project.services.research.datasets.register(
    ResearchDatasetDefinition(
        name=QualifiedName("project.dataset.daily_us_equities"),
        version=1,
        role=ResearchDatasetRole.DECISION,
        universe=UniverseRef("project.universe.liquid_us", version=4),
        decisions=SessionDecisionSchedule(
            calendar=CalendarRef("persistra.calendar.xnys", version=3),
            anchor=SessionDecisionAnchor.CLOSE,
            selection=SessionSelection.EVERY_SESSION,
            delay=Duration(0),
        ),
        cutoff=ResearchCutoffSpec.public_and_project(
            public_policy=PublicCutoffPolicy.at_decision(),
        ),
        inputs=(
            CanonicalResearchInput.bars(
                name="daily_bar",
                spec=BarSpecRef("persistra.bar.session.regular", version=1),
                price_mode=AdjustmentPriceMode.RAW,
                join=TemporalJoinSpec.backward_asof(
                    value_time="interval_end",
                    max_age=Duration(604_800_000_000),
                ),
                missing=MissingInputAction.MARK_UNUSABLE,
            ),
        ),
    )
)
```

The seven-day `Duration` is fixed elapsed time, not a session-count promise. A schedule-aware
previous-session input instead declares that exact calendar policy through its domain query
contract.

## 7. Decision schedule, universe, and base row grain

Build interval is UTC half-open `[start_at, end_at)`. The plan-04
`SessionDecisionSchedule` resolves through its calendar version to an immutable,
content-addressed schedule containing strictly increasing unique
`(decision_at, session_date)` rows. Every decision is UTC and microsecond-exact. Anchor,
selection, delay, calendar/version/generator, or resolved-boundary changes produce a
different schedule content ID and build identity.

The builder receives or creates one plan-04 `UniverseEvaluationId`. It must match the
dataset's universe definition/version, composite snapshot, schedule content, interval,
cutoff mode, public-cutoff policy, project cutoff, and instrument grain exactly. A larger
evaluation may be reused only through a content-addressed exact slice whose manifest enters
build identity; an overlapping but differently evaluated panel is not compatible reuse.

The evaluation is a first-class dependency: its candidate/rule lineage, information class,
safety findings, source licensing, and schedule/cutoff manifests fold into the build before
ordered inputs. An unsafe universe makes the build unsafe; an incompatible or structurally
invalid universe fails rather than becoming an overrideable warning.

The universe audit candidate envelope supplies unique base keys
`(decision_at, instrument_id)`. Dataset audit begins with every candidate row:

- universe-rejected candidates remain audit-only with their plan-04 reasons;
- universe-eligible candidates proceed through ordered inputs;
- missing policies may retain, mark unusable, audit-drop, or fail them; and
- only explicitly included rows enter the physical value relation.

The builder never regenerates a universe from output data and never treats absence from the
eligible set as evidence that an instrument did not exist. A duplicate base key, mismatched
session date, schedule gap, or unresolvable instrument ID fails the build before input joins.

## 8. Dual-cutoff model

### 8.1 Public cutoff per decision

For decision `d`, the declared plan-04 policy deterministically resolves public cutoff `C(d)`.
It must be UTC/microsecond exact and satisfy `C(d) <= d`. A close-decision policy may use
the decision instant; an open/latency policy normally returns an earlier instant. The
policy content ID and the resolved `(decision_at, cutoff_at)` schedule enter build identity
and have golden fixtures.

The initial policy is the plan-01 exact subtraction `C(d) = d - lag` for a nonnegative
`Duration`; underflow is a definition/build error. Session-aware open/phase behavior is
expressed by the pinned decision schedule plus an exact lag, not by host-local wall-clock
arithmetic. A future policy kind requires a new canonical schema and fixtures.

For an original or revision to be publicly eligible:

```text
available_at(revision) is not null
and available_at(revision) <= C(d)
```

An observed or reviewed policy-derived availability may remain safe. Ingestion-bounded or
otherwise unsafe availability may be selected only with its finding intact. A revision
whose availability has no defensible bound is `not_available` in the managed causal path.
An explicitly unsafe research policy may assume eligibility no earlier than its own
`ingested_at`; that policy/content ID and `research.availability.assumed_at_ingestion`
finding are mandatory. It never inherits an earlier revision's time.

### 8.2 Optional project cutoff

`CutoffMode.PUBLIC` applies no local-receipt bound. `PUBLIC_AND_PROJECT` additionally
requires one nonnull fixed `project_cutoff_at=P` and, for every canonical source revision:

```text
ingested_at(revision) <= P
```

Derived market inputs such as normalized facts also satisfy their owning project-knowledge
creation rule. Workspace/feature/label inputs must have been created by `P`, and their
exact definitions, parameters, implementation/conformance evidence, plus every transitive
source dependency must satisfy the applicable registration/receipt/creation bound.
Definition or policy state registered after `P` is excluded or receives an explicit
retrospective-definition unsafe finding; it cannot silently claim to have been
project-known.

`P` is constant across the build. It may precede, equal, or follow individual decisions;
the public cutoff still prevents later public information from entering an earlier row.
The same mode and exact cutoff are required on the universe evaluation.

### 8.3 No future-evidence side channel

Candidate lookup may inspect snapshot indexes internally, but the decision relation,
causal audit, row counts, input states, and selected lineage disclose only evidence eligible
at that row's cutoffs. When no value is eligible, the causal state is `not_available`; it
does not say whether a later revision exists in the pinned snapshot.

An explicitly requested retrospective diagnostic may compare with later snapshot evidence,
but its output is `InformationClass.RETROSPECTIVE`, lives outside the decision relation, and
is structurally ineligible for decision/workspace-derived strategy input. Future candidate
IDs, values, timestamps, and cross-sectional counts never enter causal output.

## 9. Snapshot, revision, and source selection

For each input, decision partition, and bounded entity set, the adapter executes this exact
order:

1. resolve the definition, input reference, composite member, dataset/source versions,
   entity resolutions, and domain policies from the selected snapshot;
2. restrict canonical revisions to the member market snapshot's catalog high-water mark;
3. apply `available_at <= C(d)` and optional source/derived project-knowledge bounds;
4. select the highest eligible plan-03 revision ordinal for each
   `(dataset, source, natural key)` chain;
5. treat a selected retraction as no domain value while preserving a known retracted state;
6. apply domain validation/safety and effective identity/calendar resolution at the
   declared anchor;
7. apply one complete source-precedence policy to candidate observations; and
8. pass the resulting bounded candidates to the temporal join.

Temporal ranking never chooses a lower revision merely because the higher eligible revision
is inconvenient. Source precedence never selects a future/unavailable candidate and never
mixes fields from several provider rows. The installed explicit-order policy forbids equal
priorities; a malformed/unknown policy is a definition error, while a remaining unequal
candidate tie after its total within-source ordering returns `conflict`.

Later ingestion, a newer market/composite snapshot, changed source precedence, remediated
entity resolution, mapping/action/calendar version, or domain policy cannot affect the
completed build. Every resolved identity/content ID appears in the input manifest.

### 9.1 Per-decision adjusted panels

For a canonical bar input in adjusted mode, the plan-05 bar adapter generalizes the
plan-05 scalar adjustment contract to decision panels: each decision row is its own
anchor. For every decision row, the adapter restricts plan-05 factor rows to those whose
action revisions are eligible under that row's dual cutoffs and snapshot, anchors the
cumulative multipliers at the row's decision instant, and applies them to the selected raw
bars. The result for each decision row must be exactly what one plan-05 scalar
materialization anchored at that row's cutoffs would produce; an implementation may use an
incremental factor join or per-cutoff factor caching, but never one retrospective adjusted
history shared across decisions. The panel's identity pins the plan-05 adjustment policy
identity, the factor rows' content IDs, and the decision schedule; factor rows are small
relative to bars, so the join stays within the input's bounded execution budget.

## 10. Temporal and entity join contract

### 10.1 Value-time anchor

Every canonical input names one domain-owned `value_time` or effective interval used for
joining. Examples include bar `interval_end`, filing acceptance, estimate publication,
macro/rate release, or reference validity. A fiscal target, future estimate horizon,
announced future action effective date, and other payload times may legitimately follow the
decision when their information event was eligible; the builder does not apply a generic
`event_at <= decision_at` rule to every domain.

The domain adapter proves that the named anchor is meaningful for its dataset. A caller
cannot choose an arbitrary timestamp column merely to make rows match.

### 10.2 Join kinds

`exact` requires candidate value time equal to the declared row anchor after exact calendar/
period policy resolution. More than one candidate after revision/source selection is an
ambiguity failure.

`backward_asof` requires candidate value time `<=` the row anchor and selects the greatest
value time, followed by the domain's explicit source key/revision/ID tie-breaker. It requires
either a positive fixed `max_age` or `explicit_unbounded`. Bounded mode rejects candidates
older than the limit. Explicit-unbounded mode is not automatically unsafe, but it is visible
in definition/provenance and cannot masquerade as a freshness guarantee. There is no
forward/nearest as-of join in a decision dataset.

`interval_contains` requires `valid_from <= anchor < valid_to`, treating null `valid_to` as
open. Overlapping eligible intervals after precedence are a conflict; greatest-start or
shortest-interval heuristics are forbidden.

All comparisons use UTC microsecond instants or exact source civil-period policies. A join
does not truncate timestamps, cast through host-local time, equate a period end with
availability, or use SQL insertion order.

### 10.3 Entity bridges

- `identity` joins the base `InstrumentId` to the same typed instrument ID.
- `issuer_parent` and `security_parent` resolve the instrument's effective plan-04 parent
  at the decision/value anchor and retain exact resolution lineage.
- `global_series` broadcasts one explicitly named macro, benchmark, or curve/tenor candidate
  across base instruments at the same decision; it may not mean “whatever series is current.”

Every bridge is a function from one base row to at most one input entity. Missing or
ambiguous parent resolution is an input outcome, not a fuzzy name/ticker join. A bridge
change enters definition and execution identity.

### 10.4 Cardinality

Each input must validate base-to-input cardinality as `many base rows to at most one logical
candidate each`. The join key includes `decision_at`, typed entity identity, and every
domain discriminator needed to make the input scalar at its declared projection. SQL
asserts candidate count before adding columns.

Trades, quotes, multiple facts/dimensions, constituent sets, curve tenors, and other
one-to-many observations cannot be flattened by duplicating base rows or choosing an
arbitrary member. The definition must narrow them through an owning domain query/aggregate
to one scalar record. Plan 08's initial scalar-field component contract can transform that
result but does not accept an arbitrary raw collection; a future collection-valued input
requires an additive focused contract. A duplicate output
`(decision_at, instrument_id)` is a failed invariant, never a deduplication opportunity.

## 11. Missing input, row retention, and audit

Inputs execute in definition ordinal. Each universe-eligible base row records one
`InputOutcome` per declared input and one final row decision. Outcomes mean:

- `selected`: exactly one eligible logical value/record lineage was selected;
- `component_noncomputed`: one exact eligible plan-08 component row/output was
  selected, but its preserved state is warmup/missing/censored/ambiguous/invalid rather
  than `computed`;
- `source_missing`: an eligible source row explicitly asserts nil/no-trade/no-value;
- `not_available`: no causal value is eligible at the row's snapshot/cutoffs, without
  revealing whether later evidence exists;
- `retracted`: the cutoff-eligible selected source head is a plan-03 retraction;
- `conflict`: eligible candidates remain nonunique after declared policies;
- `unsafe`: a value is selected but carries one or more unsafe findings; or
- `not_evaluated`: an earlier row disposition prevented this later input's lookup.

The input's missing action applies to every nonselected value state, including
`component_noncomputed`, allowed by its policy:

- `retain_null` keeps the row usable, writes typed null value columns, and preserves the
  state/reasons. It requires nullable outputs and is never implicit imputation.
- `mark_unusable` keeps the row in the physical relation/audit but sets `row_usable=false`.
- `drop_with_audit` excludes it from the physical relation but retains the complete row and
  input audit. It is explicit row loss, never a SQL inner-join side effect.
- `fail_build` aborts before publication with a bounded sample and aggregate counts.

An unsafe selected value remains selected and taints the build; the missing policy cannot
convert it to safe. A conflict defaults to `fail_build` for decision-role datasets. A
definition may use a stricter action for a state but cannot coerce retracted/conflicted/
source-missing into an ordinary value.

Universe-rejected candidates have only their plan-04/base-row audit and no input-outcome
rows. Every universe-eligible candidate has one outcome for every declared input ordinal;
`retain_null` and `mark_unusable` continue later inputs, while inputs after
`drop_with_audit` are `not_evaluated`. A `fail_build` publishes none of them.
This complete rectangular outcome contract is included in the lineage-item preflight and
may require a narrower definition/interval when it exceeds the configured ceiling.

No generic forward fill, zero fill, mean fill, provider coalescing, or dropping of nulls is
supported. Backward-as-of is the only initial carry-like operation, and its age semantics
are explicit in the join. Output summaries reconcile universe candidate, eligible,
included, usable, and audited-drop counts exactly.

## 12. Safety, information, lineage, and licensing

### 12.1 Separate axes

Every input/build/workspace object carries separate, noninterchangeable attributes:

- `InformationClass`: whether the values are causal, opaque, retrospective, or labels;
- `SafetyStatus`: whether any unsafe finding is inherited or introduced;
- `TemporalContractKind`: what time/entity panel semantics the relation actually preserves;
- `LineageCompleteness`: whether every dependency/column/code edge is resolved; and
- licensing/export classifications inherited from source definitions.

`safe` does not mean licensed for export. `causal` does not erase an unsafe availability
policy. `complete` lineage does not prove opaque SQL causal. A label can have complete,
technically safe lineage and still be structurally forbidden from decision input.

### 12.2 Folding rules

Dependency folding is deterministic:

1. union inherited finding content IDs and retain every origin edge;
2. add findings from cutoff, join, SQL, schema, resource, or policy analysis;
3. set `SafetyStatus.UNSAFE` when any `unsafe` finding exists;
4. fold information class as `label` over `retrospective` over `opaque` over `causal` for
   summary display while retaining every dependency's exact class;
5. fold lineage as `opaque` over `partial` over `complete`; and
6. intersect licensing permissions without broadening any source permission.

Warnings remain warnings unless their registered code declares unsafe severity. No API may
acknowledge, suppress, or relabel a finding while deriving data. User annotations later may
comment on a finding but do not alter it.

Focused specification 10 adds one narrow boundary outside this dataset/workspace fold.
A label-classified forecast/risk fit may produce a `CausalFitRelease` only after exact
plan-09 role/membership, training-label interval/availability, selection/holdout, logical
fit availability, implementation, safety, and complete-root checks pass. The fit and its
training-label root closure remain label-classified audit artifacts. A later prediction or
risk row receives a separate causal decision-dependency root only when that release and all
inference inputs are publicly available by the row cutoff and all fit/release/definition/
parameter/selection/source evidence was recorded by the fixed project cutoff when enabled.
Direct label roots, unreleased fits, or failed/incomplete release evidence still fold to
`label` and reject.

This is not a new `ResearchInputKind` in the initial plan-07 builder and does not modify
ordinary dataset, workspace, or feature folding. Plan-10 portfolio adapters own the
released row contract; this builder cannot construct, inspect, or assert a release.

### 12.3 Structural decision eligibility

Structural eligibility answers only whether an artifact may be bound into the managed
decision-dataset builder without possibly hiding a label/retrospective dependency or
inventing decision keys. It does not assert temporal safety. A dataset build or workspace
materialization is structurally decision-eligible only when:

- a dataset has role `decision`, or a workspace names one exact primary decision-panel
  dependency;
- output `decision_at`/`instrument_id` are nonnull, unique, direct unmodified key
  projections from the managed base and every output key belongs to that base;
- the resolved immutable dependency-root closure is complete enough to prove there is no
  `label` or `retrospective` ancestry, including through every workspace/feature layer;
- no expression, cast, join, aggregate, generator, or user assertion synthesizes or changes
  either decision key; and
- key provenance, dependency closure, and runtime key/count validation have immutable
  manifests.

It need not be safe, causal, same-snapshot, complete in column/code lineage, or carry a
proved `decision_panel` temporal contract. Opaque SQL/code, mixed snapshots, partial
column lineage, fixed-as-of reuse, or a subset of primary keys can therefore remain
structurally eligible while making safety unsafe and/or temporal contract opaque. Those
artifacts enter simulation only after the dataset builder restores its declared base row
grain/audit and a later explicit unsafe override records every finding.

Label/retrospective ancestry, unresolved dependency roots that could hide such ancestry,
missing/generated/duplicate decision keys, and analysis-role dataset builds are structural
failures and cannot be admitted by an override. Only completed dataset builds expose
`decision_rows()`; a structurally eligible workspace is an input candidate, not a direct
simulation handle.

The plan-10 release boundary does not make a fit, training label, forecast, or risk output
an ordinary structurally eligible workspace/dataset input. Its decision eligibility is
proved and consumed through the distinct plan-10 adapter above. Any future proposal to
bind such outputs back into this builder requires an additive typed input kind and must
retain both decision and training-audit root closures.

### 12.4 Strategy-visible boundary

`decision_rows()` is available only for a structurally decision-eligible build. It returns
usable causal/opaque rows, excludes audit-only and future-diagnostic fields, and carries the
build safety manifest. A later simulator rejects unsafe input unless its explicit override
is enabled and records every finding. The builder itself never returns a bare dataframe
whose safety/provenance object can be lost accidentally.

Exploratory `rows()` may include unusable rows and states. `eligibility_audit()` exposes
cutoff-causal universe/input reasons. A separate retrospective diagnostic result is visibly
typed, cannot be rebound as causal workspace input, and is absent from strategy services.

## 13. Build algorithm, identity, and atomic publication

### 13.1 Build request

```python no-run
build = project.services.research.datasets.build(
    definition=ResearchDatasetRef("project.dataset.daily_us_equities", version=1),
    composite_snapshot=composite_snapshot,
    start_at=start_at,
    end_at=end_at,
    project_cutoff_at=project_cutoff,
    universe_evaluation=universe_evaluation,
)
```

`universe_evaluation` is optional. When supplied, it must satisfy section 7 exactly. When
omitted, the builder creates the required plan-04 evaluation in the same research
transaction; its rows, event, build rows, and build event commit together. A build failure
then exposes neither a new evaluation nor a completed build. Reusing an existing exact
evaluation does not emit another universe event.

The service:

1. resolves and validates the definition, exact composite snapshot, market members, code,
   environment, and capability versions;
2. resolves/materializes the exact schedule and compatible universe evaluation;
3. preflights candidate counts, columns, estimated lineage items, disk/temp/memory ceilings,
   and definition limits;
4. rejects structural label/retrospective dependencies before value access for a decision
   build; an analysis build validates every explicit label/retrospective input and marks
   the resulting information class before value access;
5. creates deterministic decision/entity partitions from sorted base keys;
6. performs section-9 selection and section-10 joins input-by-input in each partition;
7. applies missing actions and writes transaction-local output/audit/lineage staging;
8. verifies unique keys, exact counts, schemas, cutoff sentinels, partition/chunk hashes,
   inherited findings, and output manifests;
9. derives the final internal relation name solely from the build UUID; and
10. publishes the immutable relation, metadata, audits, findings, and event in one research
    transaction.

No full panel must enter pandas. Internal DuckDB queries and bounded partitions do scans,
joins, ranking, and validation. Partition boundaries cannot affect selection, order,
floating conversion, missing action, content IDs, or output bytes.

### 13.2 Execution content

`execution_content_id` hashes canonical schema `persistra.research.dataset_execution@1`
containing at least:

- dataset ID/version/definition content and ordered input definitions;
- composite snapshot ID/content and every member manifest;
- exact universe evaluation/slice and resolved schedule/cutoff schedule content;
- start/end, cutoff mode, public policy, fixed project cutoff, and unsafe assumptions;
- every resolved domain definition, source precedence, entity bridge, join, missing,
  adjustment/mapping/action/calendar/rate policy, and output schema;
- per-input ordered selected-revision/logical-lineage and causal outcome/state manifests,
  including deterministic counts but excluding licensed values;
- builder/analyzer implementation content, Persistra/DuckDB/Python/environment identity;
- build limits, partition algorithm/version, and licensing/safety policy identities; and
- transitive workspace/feature/analysis-label inputs and their exact output/lineage/
  availability/interval manifests.

The UUID is not an execution hash. An exact content retry recomputes and verifies the stored
definition, input, output, audit, and safety manifests before returning the existing build.
Mismatch is corruption. Plan 14 may later define compatible reuse, but it cannot call a
different execution identity exact.

The manifests hashed into execution content exclude the new build UUID, publication
instant, physical relation name/path, and event ID so identity is not circular. The output
manifest may reference the already derived execution/build IDs; it is verified separately
and does not feed back into `execution_content_id`.

### 13.3 Failure and retry

Validation/join/resource failure publishes no completed build or event. Bounded failure
evidence contains counts, keys, reason codes, and content IDs rather than complete values.
A retry after failure is a new unpersisted attempt until success; plan 14 later adds durable
attempt history without changing completed-build identity.

A process death may leave only migration-owned staging relations. Research-write open
compares them with completed metadata and active owner state; it never guesses that staging
is complete. Referenced data is preserved, unreferenced stale staging is removable through
the managed recovery path, and read-only open reports but does not mutate it.

## 14. Definition and completed-build schema

### 14.1 Definitions

```sql
CREATE TABLE research.research_datasets (
    research_dataset_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE research.research_dataset_versions (
    research_dataset_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    dataset_role VARCHAR NOT NULL CHECK (dataset_role IN ('decision', 'analysis')),
    entity_kind VARCHAR NOT NULL CHECK (entity_kind = 'instrument'),
    universe_definition_id UUID NOT NULL,
    universe_definition_version INTEGER NOT NULL CHECK (universe_definition_version >= 1),
    schedule_definition_content_id VARCHAR NOT NULL,
    cutoff_mode VARCHAR NOT NULL CHECK (cutoff_mode IN ('public', 'public_and_project')),
    public_cutoff_policy_content_id VARCHAR NOT NULL,
    output_schema_version INTEGER NOT NULL CHECK (output_schema_version >= 1),
    output_schema_content_id VARCHAR NOT NULL,
    build_limits_content_id VARCHAR NOT NULL,
    licensing_policy_content_id VARCHAR NOT NULL,
    builder_component_content_id VARCHAR NOT NULL,
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (research_dataset_id, definition_version)
);

CREATE TABLE research.research_dataset_inputs (
    research_dataset_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
    input_name VARCHAR NOT NULL,
    input_kind VARCHAR NOT NULL CHECK (
        input_kind IN ('canonical', 'workspace', 'feature', 'label')
    ),
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    reference_content_id VARCHAR NOT NULL,
    projection_schema_content_id VARCHAR NOT NULL,
    entity_bridge_content_id VARCHAR NOT NULL,
    temporal_join_content_id VARCHAR NOT NULL,
    source_precedence_content_id VARCHAR,
    missing_action VARCHAR NOT NULL CHECK (
        missing_action IN ('retain_null', 'mark_unusable', 'drop_with_audit', 'fail_build')
    ),
    input_definition_content_id VARCHAR NOT NULL,
    input_definition_json JSON NOT NULL,
    PRIMARY KEY (research_dataset_id, definition_version, input_ordinal),
    UNIQUE (research_dataset_id, definition_version, input_name)
);
```

Registration validates contiguous input ordinals, exact content reproduction, output-name
uniqueness, capability availability, role/information compatibility, and every referenced
definition. Creating version 1 and its master/inputs/event is atomic. Later versions retain
the same stable ID/name and must equal current version plus one. Changing any versioned
semantic field requires that new version; changing the qualified name or stable lineage
purpose allocates a new ID/name.

### 14.2 Completed builds

```sql
CREATE TABLE research.research_dataset_builds (
    research_dataset_build_id UUID PRIMARY KEY,
    research_dataset_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    composite_snapshot_id UUID NOT NULL,
    composite_manifest_content_id VARCHAR NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    universe_execution_content_id VARCHAR NOT NULL,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    calendar_schedule_content_id VARCHAR NOT NULL,
    cutoff_schedule_content_id VARCHAR NOT NULL,
    cutoff_mode VARCHAR NOT NULL CHECK (cutoff_mode IN ('public', 'public_and_project')),
    public_cutoff_policy_content_id VARCHAR NOT NULL,
    project_cutoff_at TIMESTAMPTZ,
    input_manifest_content_id VARCHAR NOT NULL,
    build_limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_relation_name VARCHAR NOT NULL UNIQUE,
    output_manifest_content_id VARCHAR NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    temporal_contract_kind VARCHAR NOT NULL CHECK (
        temporal_contract_kind IN ('decision_panel', 'point_in_time', 'period_panel', 'opaque')
    ),
    structurally_decision_eligible BOOLEAN NOT NULL,
    base_candidate_count BIGINT NOT NULL CHECK (base_candidate_count >= 0),
    universe_eligible_count BIGINT NOT NULL CHECK (universe_eligible_count >= 0),
    included_count BIGINT NOT NULL CHECK (included_count >= 0),
    usable_count BIGINT NOT NULL CHECK (usable_count >= 0),
    dropped_count BIGINT NOT NULL CHECK (dropped_count >= 0),
    input_outcome_count BIGINT NOT NULL CHECK (input_outcome_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (start_at < end_at),
    CHECK (
        (cutoff_mode = 'public' AND project_cutoff_at IS NULL)
        OR (cutoff_mode = 'public_and_project' AND project_cutoff_at IS NOT NULL)
    ),
    CHECK (universe_eligible_count <= base_candidate_count),
    CHECK (included_count + dropped_count = universe_eligible_count),
    CHECK (usable_count <= included_count),
    CHECK (
        NOT structurally_decision_eligible
        OR (
            dependency_root_closure_complete
            AND information_class NOT IN ('retrospective', 'label')
        )
    )
);

CREATE TABLE research.research_dataset_build_inputs (
    research_dataset_build_id UUID NOT NULL,
    input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
    input_name VARCHAR NOT NULL,
    resolved_reference_content_id VARCHAR NOT NULL,
    resolved_dependency_id UUID,
    resolved_dependency_version INTEGER,
    snapshot_member_content_id VARCHAR,
    temporal_contract_content_id VARCHAR NOT NULL,
    temporal_contract_kind VARCHAR NOT NULL CHECK (
        temporal_contract_kind IN ('decision_panel', 'point_in_time', 'period_panel', 'opaque')
    ),
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    safety_manifest_content_id VARCHAR NOT NULL,
    licensing_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    PRIMARY KEY (research_dataset_build_id, input_ordinal),
    UNIQUE (research_dataset_build_id, input_name)
);
```

`resolved_dependency_version` is for an owning positive-integer dataset/workspace
version when applicable. An exact plan-08 feature/label materialization is an occurrence:
its typed materialization ID is `resolved_dependency_id`, this integer is null, and
its semantic definition version/content remain inside the resolved-reference/dependency
manifests.

`output_relation_name` is migration-owned internal metadata derived from the build UUID. It
is never accepted from callers or exposed as a public query handle. `created_at` is the one
injected-clock instant captured for final publication; market event times never substitute.

## 15. Output relation, audit, lineage, and findings

### 15.1 Physical output template

Each completed build owns one immutable wide relation in migration-owned schema
`research_data`. Its internal name is `dataset_<uuidhex>` and its logical template is:

```sql
CREATE TABLE research_data.dataset_<uuidhex> (
    research_dataset_build_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    session_date DATE,
    instrument_id UUID NOT NULL,
    research_row_usable BOOLEAN NOT NULL,
    research_primary_reason_code VARCHAR NOT NULL,
    research_reason_codes_json JSON NOT NULL,
    research_warning_codes_json JSON NOT NULL,
    research_safety_status VARCHAR NOT NULL CHECK (
        research_safety_status IN ('safe', 'unsafe')
    ),
    research_row_lineage_content_id VARCHAR NOT NULL,
    <declared typed value and input-state columns>,
    PRIMARY KEY (decision_at, instrument_id)
);
```

Only universe-eligible rows not disposed as `drop_with_audit` enter this relation. Marked-
unusable and retained-null rows remain so row loss is visible. Dynamic columns come only
from the registered output schema; types, nullability, units, numeric kind, field order,
and dataframe dtype are content-addressed. User text cannot become an identifier without
validated alias allocation and internal quoting.

The output manifest schema `persistra.research.dataset_output_manifest@1` contains the
build/execution/schema IDs, sorted key range/counts, deterministic partition/chunk content
IDs, aggregate content root, and safety/licensing classification. It excludes physical
paths and the internal relation name. Verification reads the completed relation in key order
and reproduces every chunk/root.

### 15.2 Row and input audit

```sql
CREATE TABLE research.research_dataset_row_audit (
    research_dataset_build_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    session_date DATE,
    instrument_id UUID NOT NULL,
    universe_eligible BOOLEAN NOT NULL,
    included BOOLEAN NOT NULL,
    row_usable BOOLEAN NOT NULL,
    primary_reason_code VARCHAR NOT NULL,
    reason_codes_json JSON NOT NULL,
    warning_codes_json JSON NOT NULL,
    input_state_content_id VARCHAR,
    row_lineage_content_id VARCHAR,
    PRIMARY KEY (research_dataset_build_id, decision_at, instrument_id),
    CHECK (NOT included OR universe_eligible),
    CHECK (NOT row_usable OR included)
);

CREATE TABLE research.research_dataset_input_outcomes (
    research_dataset_build_id UUID NOT NULL,
    input_ordinal INTEGER NOT NULL CHECK (input_ordinal >= 1),
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    outcome VARCHAR NOT NULL CHECK (
        outcome IN (
            'selected', 'component_noncomputed', 'source_missing', 'not_available',
            'retracted', 'conflict', 'unsafe', 'not_evaluated'
        )
    ),
    component_value_state VARCHAR CHECK (
        component_value_state IS NULL
        OR component_value_state IN (
            'computed', 'not_scheduled', 'input_missing', 'insufficient_history',
            'not_available', 'censored', 'ambiguous_path', 'invalid_numeric'
        )
    ),
    selected_canonical_revision_id UUID,
    selected_value_at TIMESTAMPTZ,
    selected_available_at TIMESTAMPTZ,
    selected_ingested_at TIMESTAMPTZ,
    outcome_evidence_content_id VARCHAR,
    outcome_evidence_json JSON,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    reason_codes_json JSON NOT NULL,
    warning_codes_json JSON NOT NULL,
    PRIMARY KEY (
        research_dataset_build_id,
        input_ordinal,
        decision_at,
        instrument_id
    ),
    CHECK (
        (outcome IN ('selected', 'unsafe')
            AND outcome_evidence_content_id IS NOT NULL
            AND outcome_evidence_json IS NOT NULL)
        OR (outcome = 'component_noncomputed'
            AND component_value_state IS NOT NULL
            AND component_value_state <> 'computed'
            AND selected_canonical_revision_id IS NULL
            AND selected_value_at IS NULL
            AND selected_available_at IS NULL
            AND selected_ingested_at IS NULL
            AND outcome_evidence_content_id IS NOT NULL
            AND outcome_evidence_json IS NOT NULL)
        OR (outcome IN ('source_missing', 'retracted', 'conflict')
            AND selected_canonical_revision_id IS NULL
            AND selected_value_at IS NULL
            AND selected_available_at IS NULL
            AND selected_ingested_at IS NULL
            AND outcome_evidence_content_id IS NOT NULL
            AND outcome_evidence_json IS NOT NULL)
        OR (outcome IN ('not_available', 'not_evaluated')
            AND selected_canonical_revision_id IS NULL
            AND selected_value_at IS NULL
            AND selected_available_at IS NULL
            AND selected_ingested_at IS NULL
            AND outcome_evidence_content_id IS NULL
            AND outcome_evidence_json IS NULL)
    ),
    CHECK (
        (outcome IN ('selected', 'unsafe')
            AND (component_value_state IS NULL OR component_value_state = 'computed'))
        OR (outcome = 'component_noncomputed')
        OR (outcome NOT IN ('selected', 'unsafe', 'component_noncomputed')
            AND component_value_state IS NULL)
    )
);
```

Outcome evidence JSON is bounded canonical metadata containing typed IDs, versions,
content IDs, timing/policy identity, and—for a decision input—only cutoff-eligible
source/revision references, never licensed value payloads. A complex selected logical
value may cite a manifest rather than one canonical revision;
`selected_canonical_revision_id` is then null. Source-missing, retracted, and conflict
evidence cites only causally eligible source evidence. An analysis-label selection instead
cites its exact plan-08 materialization/output and closed interval and remains visibly
label-classified. Unavailable and not-evaluated outcomes never store a candidate/evidence
reference.

`component_noncomputed` evidence cites the exact component materialization/output row,
preserved state/reasons, dependency scope/relationship roots, and causal lineage or label
interval as appropriate; it contains no analytical value. For a decision input, a
component row/output that is unavailable at the cutoff is instead evidence-free
`not_available`, so this outcome cannot disclose that a later materialized value or future
group root exists.

Input outcomes exist for each declared input on every universe-eligible row; a disposed
row's later inputs are `not_evaluated`. `input_outcome_count` must equal universe-eligible
rows times declared input count. Audit ordering is decision, instrument UUID bytes, then
input ordinal. Row-level reasons preserve definition/input order; summaries never use
hash/insertion order.

### 15.3 Safety findings

```sql
CREATE TABLE research.safety_findings (
    safety_finding_id UUID PRIMARY KEY,
    subject_kind VARCHAR NOT NULL CHECK (
        subject_kind IN (
            'research_dataset_build', 'workspace_materialization',
            'feature_materialization', 'label_materialization',
            'alpha_analysis_result', 'validation_plan',
            'signal_materialization', 'forecast_fit',
            'forecast_materialization', 'risk_model_fit',
            'risk_materialization', 'expected_cost_materialization',
            'portfolio_construction_result'
        )
    ),
    subject_id UUID NOT NULL,
    severity VARCHAR NOT NULL CHECK (severity IN ('warning', 'unsafe', 'structural')),
    reason_code VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    inherited BOOLEAN NOT NULL,
    origin_subject_kind VARCHAR,
    origin_subject_id UUID,
    evidence_content_id VARCHAR NOT NULL,
    evidence_json JSON NOT NULL,
    finding_content_id VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (subject_kind, subject_id, finding_content_id),
    CHECK (
        (inherited AND origin_subject_kind IS NOT NULL AND origin_subject_id IS NOT NULL)
        OR (NOT inherited AND origin_subject_kind IS NULL AND origin_subject_id IS NULL)
    )
);
```

Finding content includes stable reason/severity/class, origin edge, bounded evidence, and
policy/analyzer identity. Evidence defaults to IDs, counts, ranges, and hashes. It cannot
contain future values in a causal subject, credentials, complete licensed panels, SQL
parameter secrets, or arbitrary payload text.

Plans 08 through 10 extend the shared subject constraint with feature/label
materializations, label-classified alpha-analysis/validation-plan occurrences, and the
listed fit/decision/portfolio occurrences respectively. They reuse this table's immutable
finding, inheritance, monotone severity, evidence, and uniqueness
semantics rather than creating weaker plan-local safety stores.

## 16. Dataset APIs and dataframe contracts

### 16.1 Result surface

```python no-run
summary = build.summary()
rows = build.rows(include_unusable=True, max_rows=2_000_000)
decision_rows = build.decision_rows(max_rows=2_000_000)
audit = build.eligibility_audit(max_rows=2_000_000)
lineage = build.input_outcomes(max_rows=2_000_000)

for chunk in build.iter_rows(chunk_rows=100_000):
    consume(chunk)
```

Each materializing method returns an immutable result object containing the pandas frame,
schema ID, build ID, provenance/safety/licensing manifests, row count, and explicit
truncation state.
Normal methods never truncate: exceeding `max_rows` raises `ResearchResultLimitError`.
`preview(rows=N)` is separately named, returns `truncated=True`, and is structurally
analysis-only. Iteration yields deterministic complete chunks and does not hold a write
transaction across caller code.

`decision_rows()` rejects an analysis-role or structurally ineligible build. It does not
reject unsafe solely at this boundary because a later simulator owns the explicit override,
but its wrapper cannot be converted to a plain safe decision handle without retaining the
safety manifest.

### 16.2 Versioned frames

Frames use plan-01 typed wire IDs, `datetime64[us, UTC]`, Python dates, pandas nullable
dtypes, explicit columns rather than semantic indexes, and stable ascending order. Empty
frames retain exact schemas.

| Frame | Schema | Required columns |
| --- | --- | --- |
| Dataset rows | `persistra.dataframe.research_dataset@1` | build ID, decision/session, instrument ID, row usable/reasons/warnings/safety/lineage, then declared value and state columns |
| Eligibility audit | `persistra.dataframe.research_eligibility_audit@1` | build ID, decision/session, instrument ID, universe eligible, included/usable, reasons/warnings, input-state/lineage IDs |
| Input outcomes | `persistra.dataframe.research_input_outcomes@1` | build/input ID+ordinal, decision/instrument, outcome/component state, selected revision/times, outcome evidence, information/safety/reasons |
| Build provenance | `persistra.dataframe.research_provenance@1` | definition/build/execution/snapshot/universe/schedule/cutoff/input/output/safety/licensing content IDs and counts |

Rows sort by decision instant then instrument UUID bytes. Input outcomes add input ordinal.
Nullable timestamps sort last in audit views. Dynamic analytical values are finite
`float64` only after explicit plan-01/source-numeric conversion; exact record/lineage APIs
retain domain decimals and units where applicable.

## 17. Parameterized read-only SQL

### 17.1 Typed operation context

Public SQL never receives a connection or arbitrary catalog access. A request binds typed
relations into operation-scoped logical schema `ctx`:

```python no-run
result = project.services.research.sql.read(
    """
    SELECT instrument_id, interval_end, close
    FROM ctx.daily_bars
    WHERE instrument_id = ?
    ORDER BY interval_end
    """,
    parameters=(instrument_id,),
    context=SqlReadContext(
        composite_snapshot=composite_snapshot,
        as_of_at=as_of_at,
        cutoff_mode=CutoffMode.PUBLIC_AND_PROJECT,
        public_cutoff_at=as_of_at,
        project_cutoff_at=project_cutoff,
        relations={
            "daily_bars": CanonicalSqlRelation.bars(
                instruments=(instrument_id,),
                interval=interval,
                spec=BarSpecRef("persistra.bar.session.regular", version=1),
                price_mode=AdjustmentPriceMode.RAW,
            )
        },
    ),
    limits=SqlReadLimits(),
)
```

Relation aliases use the same bounded identifier grammar as input names. Bindings may
reference a snapshot/cutoff-bounded canonical query, exact dataset build, exact workspace
materialization, or exact plan-08 feature/label materialization. Canonical relations require
bounded entities/series and intervals plus every domain policy required by plans 04–06.
`SqlReadContext.composite_snapshot`, `as_of_at`, `cutoff_mode`, and `public_cutoff_at` are
required when any canonical relation is present; `project_cutoff_at` is required exactly
for public-and-project mode. A context containing only exact immutable materializations may
omit those fields. If its dependencies resolve to different snapshots, the context has no
synthetic composite snapshot and receives the mixed-snapshot classification in section 19.

The service parses one statement, resolves every `ctx.<alias>` AST relation node, and
replaces it with an internal parameterized relation owned by the corresponding repository.
References outside `ctx`, unresolved aliases, physical schemas/tables, attachment aliases,
and three-part catalog names are rejected. SQL text is never interpolated to perform this
replacement.

### 17.2 Fixed-as-of versus panel relations

A canonical SQL relation uses one fixed `as_of_at`, public cutoff, and optional project
cutoff; it is a `point_in_time` or bounded `period_panel` relation, not a historical
decision panel. A dataset-build binding preserves its recorded `decision_panel` contract.
Joining a fixed-as-of result across historical decisions does not acquire causal panel
semantics and is classified opaque unless a managed temporal operator owns the conversion.

When a fixed relation's public cutoff follows its effective `as_of_at`, the relation is
explicitly `InformationClass.RETROSPECTIVE` relative to that effective instant even though
the query is a valid historical-inspection API. It cannot enter decision data. Equality or
an earlier cutoff does not by itself prove a decision panel; snapshot, adapter, and safety
lineage still govern classification.

When a fixed-as-of/period relation is combined with a declared primary decision relation,
the output is also retrospective if that fixed public cutoff follows any retained primary
decision key to which its values could contribute. Row-local key/predicate analysis and
runtime output-key validation may prove all such keys were excluded; otherwise uncertainty
does not downgrade to ordinary opaque. Only the managed dataset temporal operator can
replace the fixed cutoff with the exact per-decision schedule and make a causal claim.

The typed dataset builder, not ad hoc SQL, owns per-decision cutoff schedules. This avoids
pretending that a WHERE predicate containing timestamps is equivalent to the section-8/9
selection algorithm.

### 17.3 Query identity and result

SQL text is valid UTF-8, at most 256 KiB, has CRLF normalized to LF, and is otherwise hashed
exactly under schema `persistra.research.sql_text@1`. Formatting-equivalent queries may
therefore have different identities; Persistra never falsely claims semantic equivalence.
The parser/analyzer identity and DuckDB version are separate execution inputs.

Positional `?` bindings are canonical typed scalar/array values. Placeholder count/types
must match; identifiers, SQL fragments, paths, callables, and object hooks cannot be
parameters. At most 10,000 bindings and 16 MiB of canonical parameter data are accepted.
Query text, parameter content ID, relation/dependency manifest, output schema, limits,
analyzer result, information/temporal class, findings, and licensing manifest appear in
`SqlQueryAudit`.

Initial public SQL/workspace output columns are unique identifiers using section-6.2's
lower-snake grammar and use only boolean, signed 64-bit integer, finite `float64`,
`DECIMAL(p,s)` with `p <= 38`,
UTF-8 string, UUID, `DATE`, UTC-microsecond `TIMESTAMPTZ`, or nulls of those declared types.
Naive timestamps, time-of-day, intervals, blobs, JSON/nested/list/map/struct/union types,
unsigned/128-bit integers, nonfinite floats, duplicate/unnamed columns, and values outside
the configured cell/row byte bounds are rejected before publication. Typed-ID semantics
survive direct projection/alias through context metadata; a cast or computed UUID is an
untyped UUID until a registered owning definition validates its kind.

SQL dataframes use envelope schema `persistra.dataframe.sql_result@1`; their dynamic ordered
columns/dtypes come from `output_schema_content_id`, while the immutable result object
carries query audit, row count, ordering, truncation, safety, lineage, and licensing
metadata. Empty results retain that exact dynamic schema.

Pandas mapping is nonnullable `bool`/`int64` or nullable `boolean`/`Int64`, `float64`,
`string`, `object` `Decimal`, plan-01 typed-wire or canonical UUID strings, Python civil
dates, and `datetime64[us, UTC]`. Nullability is part of the output schema and never inferred
differently from a nonempty sample.

The result is bounded like dataset frames. `read()` fails rather than silently returning a
partial result; `preview()` is explicit and marked truncated. `iter_read()` yields ordered
chunks only when the SQL contains a complete deterministic `ORDER BY` or the caller accepts
an analysis-only unordered result with that fact recorded.

## 18. SQL parsing, security, and temporal analysis

### 18.1 One read-only statement

Persistra parses SQL with the pinned DuckDB-compatible parser before relation binding or
execution. A valid request contains exactly one `SELECT`, optionally introduced by a
`WITH` clause. A trailing semicolon is accepted, but a second empty or nonempty statement
is not. Semicolons and forbidden words inside comments or string literals have no special
meaning; classification uses the parsed tree rather than keyword scanning.

The security gate rejects every statement or AST node capable of changing state, changing
the session, discovering unmanaged storage, or obtaining data outside the typed context.
This includes:

- `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `CREATE`, `ALTER`, `DROP`, `TRUNCATE`, and
  `COMMENT`;
- `COPY`, `EXPORT`, `IMPORT`, `ATTACH`, `DETACH`, `INSTALL`, `LOAD`, and secret-management
  statements;
- `PRAGMA`, `CALL`, `SET`, transaction control, prepared-statement control, and extension
  management;
- physical catalog/schema references, metadata-table functions, system catalogs, and
  replacement scans;
- filesystem, glob, URL, object-store, database, Arrow/Python-object, and external table
  functions, including `read_csv`, `read_json`, `read_parquet`, `sqlite_scan`, and
  `postgres_scan`; and
- user-defined macros, user-defined functions, sequences, nondeterministic object hooks,
  and any function absent from the versioned allowlist.

The executor uses a read-only research connection, attaches exact snapshot members
read-only, disables automatic extension loading and external access, and exposes only
operation-owned `ctx` relations. The temporary directory, memory, thread count, and query
timeout are project policy, not caller SQL. No SQL request receives database credentials,
arbitrary file paths, environment variables, a DuckDB connection, or a Python object
registry.

Read-only SQL is a constrained query facility, not a general sandbox. A parser or security
classifier failure prevents execution. A query that passes this security gate can still be
temporally opaque, retrospectively informed, licensed against export, too large, or
structurally ineligible for decisions.

### 18.2 Dependency resolution

Every relation dependency is a resolved `ctx` binding. Resolution records:

- alias and binding kind;
- exact dataset/build/materialization/domain definition IDs and versions;
- composite/member snapshot and cutoff identities, when applicable;
- selected columns and output schema content ID;
- information class, temporal contract, safety manifest, licensing class, and complete
  transitive dependency manifest; and
- binding adapter, analyzer, and relation-template component content IDs.

Common table expressions are query-local expressions, not new dependency roots. An alias
cannot shadow `ctx`, and a CTE cannot use an unbound physical relation. Column references
must resolve unambiguously after managed relation expansion. `SELECT *` may execute for
analysis, but it expands against the pinned input schema and that exact expansion enters
query identity; registered workspace materializations require an explicit output schema or
persist the fully expanded ordered schema.

Every supplied context alias must be referenced at least once and every referenced alias
must be supplied; unused bindings are rejected rather than silently entering or escaping
lineage. Repeated AST uses of one alias share its exact resolved binding.

`primary_decision_relation`, when supplied, must name one referenced exact structurally
eligible dataset/workspace decision binding. It is only a key-provenance anchor. The
analyzer records its dependency ordinal and traces direct `decision_at`/`instrument_id`
projections through aliases; naming it cannot upgrade temporal, safety, information, or
lineage classifications. Without that anchor a workspace cannot become structurally
decision-eligible.

Dependencies carrying `label` or `retrospective` information remain structurally
decision-ineligible through aliases, CTEs, nested expressions, and workspace layers.
Dependencies with `opaque` information or partial/opaque lineage remain unsafe. A wrapper
query cannot rename or cast any of those states into `causal`, `complete`, or `safe`.

Resolved occurrence dependencies form a directed acyclic graph. Resolution walks exact
IDs with gray/black cycle detection, rejects a self/current-staging reference or repeated
gray node, and records a canonical topological manifest. Reusing one already completed
dependency in several expressions is valid and folds to one node with ordered occurrence
edges; friendly names never remain in the graph.

### 18.3 Row-local temporal subset

The analyzer assigns `SqlTemporalClass.ROW_LOCAL` only when each output row can be explained
from the same input key without inspecting, ranking, or combining values from other
decision/entity keys. The initial versioned allowlist permits:

- column projection, aliases, typed casts, null checks, and deterministic `CASE`;
- deterministic allowlisted scalar arithmetic, comparison, boolean, string, date/time,
  and null-handling functions with documented null/overflow behavior;
- a `WHERE` predicate computed solely from the current row;
- full-key equijoins between relations with identical decision-panel keys, only when
  dependency metadata proves one-to-one or many-to-one cardinality; and
- `ORDER BY` solely as result presentation, provided it does not feed a limiting,
  ranking, or value-producing expression.

The analyzer assigns `SqlTemporalClass.OPAQUE` to aggregates, windows, `DISTINCT`, set
operations, recursive CTEs, scalar or correlated subqueries, lateral joins, non-equality or
partial-key joins, pivots, unnesting, sampling, `LIMIT`/`OFFSET`, top-k operations,
time-travel syntax, nondeterministic functions, and user-defined code. It also assigns
`opaque` when cardinality, temporal meaning, lineage, function behavior, or analyzer
support cannot be proved. Opaque queries may run for bounded analysis if they pass the
security gate, but they produce an unsafe finding, fold local information class to
`InformationClass.OPAQUE`, and never claim a proved `decision_panel` contract. They may
remain structurally eligible only through the independent direct-key/dependency-closure
proof in section 12.3.

Known future-reading constructs are stronger than opaque: `LEAD`, following/centered
window frames, a join/predicate that selects a later decision for an earlier primary key,
or an equivalent analyzer-proved forward reference folds
`InformationClass.RETROSPECTIVE` and is structurally forbidden. Renaming or nesting the
expression does not hide it. Unsupported cross-row behavior with no proved direction stays
opaque/unsafe rather than being guessed retrospective.

An inherited `decision_panel` temporal contract is preserved only when:

1. every dependency is an exact, compatible decision panel on the same composite snapshot,
   decision schedule, public/project cutoff schedule, and key semantics;
2. the output retains zero or one nonnull `decision_at` and `instrument_id` pair per input
   base key, with zero permitted only through a proved row-local filter;
3. joins satisfy the proven full-key cardinality contract;
4. no limit, aggregate, window, set operation, or opaque expression changes the base row
   set; and
5. output validation proves key uniqueness/subset membership and equal base/output counts
   when no row-local filter exists.

A row-local filter preserves a causal `decision_panel` **subset** contract when its output
keys are a validated subset of the declared primary relation. The key manifest records the
predicate, primary/output roots, and missing per-key audit limitation; a downstream dataset
builder records absent matches through its own missing policy/audit before simulation use.
Dropping or computing a key column is a structural failure even if all remaining
expressions are row-local. Fixed-as-of and period-panel inputs retain those contracts only
under analogous key-preserving row-local operations; combining temporal contracts without
a managed operator yields `opaque`.

A relation-free constant `SELECT` may be row-local and technically safe, but has temporal
contract `opaque` and is structurally decision-ineligible because it has no managed
entity/time grain.

The analyzer is deliberately proof-oriented. Unsupported does not mean malicious or
incorrect; it means Persistra will not assert causal structure. Analyzer rules, function
allowlist, parser version, and DuckDB version are content-addressed. A later analyzer may
classify a new execution, but it never reinterprets the stored safety result of an old one.

Plan 08 bounded SQL is a different component capability: it sees only
`ctx.partition`, enforces declared preceding/following frames by component kind, and
requires temporal conformance. Its completed result enters here as an exact
feature/label materialization. It does not reclassify a plan-07 general SQL/workspace window
or weaken this analyzer's `opaque`/retrospective rules.

### 18.4 Parser and execution bounds

Before execution the service enforces:

- at most 256 KiB of normalized SQL text;
- at most 100,000 AST nodes and 128 levels of syntactic nesting;
- at most 10,000 typed parameters totaling 16 MiB;
- at most 256 direct relation dependencies, 100,000 transitive dependency nodes,
  1,000,000 folded findings, and 1,024 output columns;
- caller/project row, chunk, memory, temporary-storage, thread, and five-minute default
  timeout limits; and
- a deterministic cancellation path that closes the operation transaction and publishes
  no materialization.

`SqlReadLimits.max_rows` is checked before dataframe publication and while streaming.
DuckDB estimates are preflight hints, not authority: runtime counters enforce the limits.
Resource exhaustion, cancellation, timeout, or client iterator abandonment closes the
operation and never exposes a silently partial ordinary result.

## 19. Managed workspace materialization

### 19.1 Public API and naming

A workspace object is a stable qualified-name lineage whose versions are immutable SQL
materializations:

```python no-run
materialization = project.services.research.workspace.materialize(
    name=QualifiedName("workspace.cleaned_daily"),
    query="""
        SELECT decision_at, instrument_id, daily_bar_close AS close
        FROM ctx.dataset
        WHERE daily_bar_state = 'selected'
        ORDER BY decision_at, instrument_id
    """,
    parameters=(),
    context=SqlReadContext(
        primary_decision_relation="dataset",
        relations={
            "dataset": DatasetBuildSqlRelation(build.id),
        }
    ),
    limits=WorkspaceMaterializationLimits(),
    new_version=True,
)
```

Because this example uses only a row-local filter, it retains a causal `decision_panel`
subset contract and is a structurally eligible input candidate: its keys are validated
against the named primary relation. A downstream dataset build must restore base rows and
audit absent matches; the name “cleaned” grants no direct simulation status.

Names follow the plan-01 `QualifiedName` grammar and must begin `workspace.`. The initial
call creates one `WorkspaceObjectId` and version 1. `new_version=True` appends exactly the
next version and atomically advances friendly-name resolution. An exact retry returns and
verifies the existing version instead of allocating another. After that exact-retry check,
a different execution for an existing name requires `new_version=True`; otherwise it is a
conflict. Callers cannot overwrite the current version accidentally.

Consumers may refer to a friendly workspace name only during request resolution. Before
their execution identity is computed, the service resolves it under the operation
transaction to exact object/materialization IDs, version, output manifest, and safety
manifest. Results never depend on a name that can later advance.

For the object being written, execution content includes the stable object ID but excludes
the not-yet-allocated materialization ID, object version, publication instant, physical
name, and event ID. The service computes it first: an identical prior execution is verified
and returned; otherwise `new_version=True` is required and the next contiguous object
version is allocated. A caller cannot force duplicate immutable versions of identical
execution content.

### 19.2 Workspace metadata

```sql
CREATE TABLE research.workspace_objects (
    workspace_object_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE research.workspace_materializations (
    workspace_materialization_id UUID PRIMARY KEY,
    workspace_object_id UUID NOT NULL,
    object_version INTEGER NOT NULL CHECK (object_version >= 1),
    query_schema_version INTEGER NOT NULL CHECK (query_schema_version >= 1),
    query_text_content_id VARCHAR NOT NULL,
    query_text VARCHAR NOT NULL,
    parameters_content_id VARCHAR NOT NULL,
    parameters_json JSON NOT NULL,
    sql_analyzer_content_id VARCHAR NOT NULL,
    sql_context_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    composite_snapshot_id UUID,
    dependency_manifest_content_id VARCHAR NOT NULL,
    primary_decision_dependency_ordinal INTEGER CHECK (
        primary_decision_dependency_ordinal >= 1
    ),
    decision_key_manifest_content_id VARCHAR,
    dependency_root_closure_complete BOOLEAN NOT NULL,
    udf_manifest_content_id VARCHAR,
    licensing_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    sql_temporal_class VARCHAR NOT NULL CHECK (
        sql_temporal_class IN ('row_local', 'opaque')
    ),
    temporal_contract_kind VARCHAR NOT NULL CHECK (
        temporal_contract_kind IN ('decision_panel', 'point_in_time', 'period_panel', 'opaque')
    ),
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    structurally_decision_eligible BOOLEAN NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_relation_name VARCHAR NOT NULL UNIQUE,
    output_manifest_content_id VARCHAR NOT NULL,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (workspace_object_id, object_version),
    CHECK (
        (primary_decision_dependency_ordinal IS NULL
            AND decision_key_manifest_content_id IS NULL)
        OR (primary_decision_dependency_ordinal IS NOT NULL
            AND decision_key_manifest_content_id IS NOT NULL)
    ),
    CHECK (
        NOT structurally_decision_eligible
        OR (
            primary_decision_dependency_ordinal IS NOT NULL
            AND dependency_root_closure_complete
            AND information_class NOT IN ('retrospective', 'label')
        )
    )
);

CREATE TABLE research.workspace_dependencies (
    workspace_materialization_id UUID NOT NULL,
    dependency_ordinal INTEGER NOT NULL CHECK (dependency_ordinal >= 1),
    dependency_kind VARCHAR NOT NULL CHECK (
        dependency_kind IN (
            'canonical_relation', 'research_dataset_build',
            'workspace_materialization', 'feature_materialization',
            'label_materialization'
        )
    ),
    dependency_id UUID,
    dependency_version INTEGER,
    dependency_content_id VARCHAR NOT NULL,
    selected_columns_content_id VARCHAR NOT NULL,
    composite_snapshot_id UUID,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque', 'retrospective', 'label')
    ),
    temporal_contract_kind VARCHAR NOT NULL CHECK (
        temporal_contract_kind IN ('decision_panel', 'point_in_time', 'period_panel', 'opaque')
    ),
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    PRIMARY KEY (workspace_materialization_id, dependency_ordinal),
    UNIQUE (workspace_materialization_id, dependency_content_id)
);
```

`query_text` and `parameters_json` contain bounded canonical representations suitable for
exact reproduction. Secret-like parameter types are rejected, logs contain only parameter
content IDs and safe type/count summaries, and access-controlled inspection is explicit.
`udf_manifest_content_id` is null in 3.0 because UDFs are forbidden; retaining the nullable
column avoids confusing a future opt-in extension with built-in scalar functions.
`dependency_version` is likewise null for feature/label materialization occurrences;
their exact IDs plus dependency content manifest carry the plan-08 semantic definition
version. It is populated only for dependency kinds whose owning version is a positive
integer.

When a primary decision relation is declared, `decision_key_manifest_content_id` records
its exact ultimate dataset build/base-key manifest, dependency ordinal, direct AST column
lineage, primary/output counts and key roots, subset-membership proof, uniqueness/null
checks, and analyzer identity. Failure to prove any output key came unmodified from that
base sets structural eligibility false; it never falls back to matching timestamp/UUID
values by coincidence.

All dependency ordinals are contiguous and reflect first resolved AST occurrence.
Duplicate references fold to one dependency edge with a canonical occurrence manifest.
The materialization information class is the strongest transitive class:
`label > retrospective > opaque > causal`. Lineage folds `opaque > partial > complete`.
Safety is unsafe if any dependency or local finding is unsafe. Label/retrospective ancestry
or incomplete dependency-root closure sets structural eligibility false regardless of an
override. Partial/opaque column or code lineage remains unsafe but does not alone make the
root closure incomplete.

### 19.3 Snapshot and temporal preservation

A workspace may combine dependencies from different snapshots for analysis. The result is
unsafe and has an opaque temporal contract, but may remain a structurally eligible input
candidate when direct primary keys and the label-free dependency-root closure are proved.
Only a safe preserved `decision_panel` claim requires every transitive market-backed
dependency to use the exact same composite snapshot manifest and every input panel to share
schedule/cutoff identity. Matching snapshot UUID text without matching manifest content is
corruption.

Row-local SQL over one exact safe decision panel preserves that panel only under section
18.3's full row/key validation; a causal row-local filter preserves an explicit panel-
subset contract and structural key eligibility. Fixed-as-of canonical relations never
become historic decision panels through a join to a timestamp column. Partial or opaque
lineage, unsupported SQL, a mixed-snapshot dependency, or an opaque ancestor can only
remain unsafe/opaque even when structural key eligibility survives.

Workspace materialization is intentionally more general than dataset construction. It may
produce analysis tables, summaries, and retrospective/label outputs, provided the query is
security-safe and bounded. Those outputs stay correctly classified and cannot enter a
decision dataset through a renamed wrapper.

### 19.4 Physical publication and inspection

The service executes the approved `SELECT` into a transaction-local staging relation,
validates the declared/derived schema and runtime limits, orders and hashes deterministic
output chunks, then publishes a migration-owned relation in plan-02 schema `workspace`. Its
internal name is `materialization_<uuidhex>` and is derived solely from the materialization
UUID. Callers cannot provide or query that name.

Workspace publication rejects nondeterministic functions, unseeded or engine-dependent
sampling, and unstable ordering/collation constructs even when an ordinary bounded
analysis read could execute them as opaque. Deterministic aggregates/windows may
materialize as opaque; determinism is necessary for exact reproduction, not proof of
causality.

Execution identity includes exact workspace object identity, SQL bytes, typed parameters,
resolved dependency graph, snapshots/cutoffs, parser/analyzer/function-allowlist/DuckDB
identities, limits, output schema, temporal/information/lineage/safety classifications,
licensing policy, and materializer component identity. The output manifest includes ordered
schema, row count, deterministic chunk content IDs, aggregate content root, and safety/
licensing class. Physical names and paths are excluded.

Output order is not relational state. When a query has a complete deterministic `ORDER BY`,
that ordering contract and null/collation rules enter the manifest and dataframe reads
reproduce it. Otherwise the materializer establishes an implementation-versioned total
order from canonical row encodings, including duplicate multiplicity, for hashing and
repeatable reads. That managed order has no analytical meaning and cannot establish a
decision-panel key. Exact retries reproduce and verify the stored root before returning.

Publication of the object/version row, dependency edges, physical relation, findings,
output manifest, friendly-name advance, and event is one research transaction. Interruption
leaves none visible. Workspace objects/materializations cannot be deleted, overwritten,
renamed, or compacted in 3.0; later lifecycle work must preserve referenced versions.

Inspection uses immutable handles:

```python no-run
frame = materialization.rows(max_rows=1_000_000)
audit = materialization.audit()
dependencies = materialization.dependencies()
findings = materialization.safety_findings()
```

Ordinary reads never truncate. `preview()` is explicit and marked truncated. A
materialization handle exposes logical schema/version/manifest metadata, not a raw
connection or internal relation name.

Workspace row dataframes use envelope schema
`persistra.dataframe.workspace_materialization@1`; their dynamic ordered columns/dtypes
come from the stored output schema and the handle retains object/materialization/version,
dependency, ordering, safety, lineage, and licensing metadata. Empty frames are typed.

## 20. Security, resources, licensing, and observability

### 20.1 Resource ceilings

Default request ceilings are:

| Resource | Dataset build | SQL read | Workspace materialization |
| --- | ---: | ---: | ---: |
| Ordered dependencies | 256 | 256 | 256 |
| Output columns | 1,024 | 1,024 | 1,024 |
| Base/audit rows | 25,000,000 | Not applicable | Not applicable |
| Output rows | 25,000,000 | 1,000,000 | 25,000,000 |
| Lineage/graph | 250,000,000 items | 100,000 nodes / 1,000,000 findings | 100,000 nodes / 1,000,000 findings |
| Partition/chunk rows | 100,000 | 100,000 | 100,000 |
| SQL text | Not applicable | 256 KiB | 256 KiB |
| Typed parameters | Not applicable | 10,000 / 16 MiB | 10,000 / 16 MiB |
| Canonical cell / row bytes | 1 MiB / 16 MiB | 1 MiB / 16 MiB | 1 MiB / 16 MiB |
| Direct pandas materialization | 2,000,000 | 1,000,000 | 1,000,000 |
| Default execution timeout | Project build policy | 5 minutes | 5 minutes |

Project configuration may lower any ceiling. Raising a supported per-request ceiling
requires research-write policy permission and enters execution identity; it cannot exceed
the deployment hard ceiling. Estimates trigger early rejection, while runtime counters,
DuckDB memory/temp limits, and disk-space checks remain authoritative. Dataset builds use
streaming partitions and may exceed the direct pandas limit without materializing the full
panel in Python.

The system never silently samples, truncates, drops columns, changes a join, widens a
cutoff, falls back to a later snapshot, substitutes a provider, or disables lineage to meet
a limit. Failure evidence reports the stable resource reason, requested/observed bound,
and safe content IDs.

### 20.2 Licensing and sensitive data

Every canonical dependency contributes its plan-03 licensing/export classification. A
dataset or workspace result receives the most restrictive transitive classification plus
any transformation-specific obligations. Projection, aggregation, hashing, or renaming
does not automatically relax a restriction; an explicit versioned licensing rule must say
that a derived form is exportable.

Dataframe reads, exports, later run artifacts, and reports must check that classification.
This plan provides no export bypass. Output/audit/lineage manifests contain typed IDs,
hashes, counts, ranges, policy identities, and bounded evidence by default—not full vendor
payloads. Diagnostic samples require the same entitlement as the source values and never
enter structured logs.

SQL text, parameters, and definition JSON must be secret-free. Typed credential/secret
objects, private-key types, arbitrary environment access, and secret-reference resolution
are rejected. Ordinary string literals/parameters are persisted for reproduction and cannot
be reliably recognized as accidentally embedded tokens, so callers must never place
credentials in them. Connection configuration remains inside project/database services and
is absent from SQL, workspace, event, exception, lineage, and output metadata.

### 20.3 Logs and metrics

Operations emit structured lifecycle logs and metrics under plan 02 with project/database,
definition/build/materialization, snapshot, partition, analyzer, and content IDs. They may
include bounded counts, elapsed time, peak managed memory/temp use, classification, and
reason codes. They do not include SQL parameter values, complete SQL text by default,
licensed rows, credentials, dataframe representations, or future candidate details.

SQL exceptions expose query content ID, parser/analyzer phase, and bounded line/column/token
class; they do not echo parameter values or the complete query. Access-controlled workspace
inspection is the only normal way to retrieve its persisted SQL text.

Metrics distinguish registration, build/materialization execution, cache verification,
selection outcomes, ambiguity, row loss, unsafe/structural findings, query rejection,
timeout, cancellation, and resource exhaustion. Metrics are observability only; completed
metadata and events remain lifecycle authority.

## 21. Events, exceptions, and stable reason codes

### 21.1 Lifecycle events

| Event type | Aggregate kind | Published when |
| --- | --- | --- |
| `persistra.research.dataset_registered@1` | `persistra.aggregate.research_dataset` | A dataset definition version commits |
| `persistra.research.dataset_built@1` | `persistra.aggregate.research_dataset_build` | A verified immutable build commits |
| `persistra.research.workspace_materialized@1` | `persistra.aggregate.workspace_materialization` | A verified workspace version commits |

Events use plan-01 typed payloads with IDs, versions, content/manifests, snapshot, counts,
safety/lineage/temporal classifications, and injected-clock instants. They never contain
complete rows, SQL parameter values, or physical relation names. The event and its state
commit together. Failed registrations/executions and ordinary SQL reads emit no lifecycle
event; there is no event per dataset row, input outcome, query, or chunk.

Dataset-registration events use the dataset ID with aggregate sequence equal to definition
version. Build and workspace-materialization IDs are single-occurrence aggregates and use
sequence 1; workspace object/version appears in the materialization payload. Exact retries
emit no duplicate event. All sequences and peer-event ordering follow plan 01.

These definition/build/materialization lifecycle events use the publication transaction's
captured instant for `event_at`, `available_at`, and `recorded_at`; they never substitute
for the source availability or decision times inside their manifests.

### 21.2 Public exceptions

| Exception | Stable reason code | Trigger |
| --- | --- | --- |
| `ResearchDatasetDefinitionError` | `research.dataset.definition_invalid` | Invalid or unsupported definition/version |
| `ResearchDatasetBuildError` | `research.dataset.build_failed` | Build cannot complete atomically |
| `ResearchTemporalJoinError` | `research.join.invalid` | Invalid temporal/entity join contract |
| `ResearchCardinalityError` | `research.join.cardinality` | More than one logical candidate or duplicate base key |
| `ResearchLabelLeakageError` | `research.information.label_forbidden` | Direct label ancestry or an unreleased fit reaches a decision surface |
| `ResearchRetrospectiveInputError` | `research.information.retrospective_forbidden` | Retrospective ancestry reaches a decision surface |
| `ResearchInputUnsafeError` | `research.input.unsafe` | A caller requires safe input but the manifest is unsafe |
| `ResearchResultLimitError` | `research.result.row_limit` | A non-preview dataframe would cross its row ceiling |
| `SqlQueryError` | `research.sql.invalid` | SQL cannot parse, bind, type, or produce a supported schema |
| `SqlStatementForbiddenError` | `research.sql.statement_forbidden` | SQL fails the read-only/external-access security gate |
| `SqlQueryLimitError` | `research.sql.limit` | SQL AST, parameters, rows, columns, time, memory, or temp crosses a limit |
| `WorkspaceMaterializationError` | `research.workspace.materialization_failed` | Workspace execution/verification cannot publish |
| `WorkspaceNameConflictError` | `research.workspace.name_conflict` | Name/version intent conflicts with current immutable state |

Exceptions inherit the plan-01 domain hierarchy and carry bounded structured context. A
top-level build/materialization error may retain a stable causal exception and specific
reason in its diagnostic record; it does not replace that cause with free text.

### 21.3 Finding and audit reasons

The following initial reason namespace is stable. Codes describe state independently from
the public exception used when policy makes that state fatal.

| Reason code | Default disposition |
| --- | --- |
| `research.snapshot.mismatch` | structural/fail |
| `research.schedule.mismatch` | structural/fail |
| `research.cutoff.invalid` | structural/fail |
| `research.availability.assumed_at_ingestion` | unsafe |
| `research.join.ambiguous` | structural/fail |
| `research.join.cardinality` | structural/fail |
| `research.join.stale` | input missing action |
| `research.input.source_missing` | input missing action |
| `research.input.not_available` | input missing action |
| `research.input.component_noncomputed` | input missing action with exact plan-08 state |
| `research.input.retracted` | input missing action |
| `research.input.conflict` | input missing action or fail |
| `research.input.unsafe` | unsafe/missing action |
| `research.input.not_evaluated` | audit only |
| `research.row.usable` | successful included row |
| `research.row.unusable` | included row retained as unusable |
| `research.row.duplicate_key` | structural/fail |
| `research.row.dropped` | explicit audit |
| `research.lineage.partial` | unsafe |
| `research.lineage.opaque` | unsafe |
| `research.temporal.opaque` | unsafe |
| `research.information.retrospective_forbidden` | structural/fail on decision surfaces |
| `research.information.label_forbidden` | structural/fail on decision surfaces |
| `research.sql.opaque` | unsafe |
| `research.sql.nondeterministic` | unsafe or forbidden by operation policy |
| `research.sql.mixed_snapshots` | unsafe/opaque |
| `research.sql.row_filter` | warning; preserves only a causal panel-subset contract and requires downstream missing audit |
| `research.workspace.snapshot_mismatch` | unsafe/opaque when an exact workspace input differs from the build base |
| `research.workspace.schedule_mismatch` | unsafe/opaque when direct keys map across different schedules |
| `research.workspace.cutoff_mismatch` | unsafe/opaque when workspace/build cutoff contracts differ |
| `research.workspace.lineage_incomplete` | unsafe |
| `research.resource.limit` | fail |

Definitions may map nonstructural input states to their declared missing action. They may
make a warning stricter, but cannot downgrade `structural` or convert an unsafe/opaque
condition to safe. New reasons append; persisted meanings do not change in place.

## 22. Required edge-case behavior

Implementations and reviews must preserve these cases:

- A row ingested after fixed project cutoff is excluded even if its public availability
  precedes the decision. A later build with a later project cutoff is a different identity.
- A correction public after a decision cannot replace the revision selected for that
  decision. A correction available before the decision participates normally in revision/
  source selection.
- A retraction effective before the cutoff removes the candidate according to plan 03. A
  later retraction cannot leak into an earlier decision's outcome or audit.
- Unknown public availability never becomes causal merely because ingestion is known.
  Explicit availability-equals-ingestion policy marks the build unsafe.
- `source_missing` requires cutoff-eligible source coverage/nil evidence that explicitly
  asserts no value. Mere absence of an eligible candidate is `not_available`; causal
  audits never inspect later evidence to distinguish the two or record its future ID,
  value, or timestamp.
- Duplicate universe/base keys fail. Two candidates surviving all revision/source/tie-break
  rules fail cardinality; arbitrary row order never selects one.
- Equal value/availability instants use the domain's registered revision/source ordering,
  then typed UUID-byte order only where that ordering is explicitly semantic. UUID order
  never resolves an economic conflict.
- DST gaps/folds, early closes, weekends, holidays, and schedule overrides use the pinned
  plan-04 calendar instants. Local wall-clock arithmetic cannot manufacture decision times.
- A weekend or holiday backward-as-of join may select the prior observation only within
  its explicit maximum age. `explicit_unbounded` is a visible definition choice and never
  the default.
- `global_series` broadcasts only a singleton logical value per decision. Multiple eligible
  releases/vintages are an ambiguity, not an accidental cartesian join.
- A workspace dependency hidden behind any number of aliases retains label,
  retrospective, opaque, mixed-snapshot, licensing, and lineage findings.
- A row-local `WHERE` can retain a causal panel-subset/direct-key contract; a downstream
  dataset builder must restore base rows and record absent matches through its declared
  missing-row audit before simulation use.
- `ORDER BY` alone affects presentation, not temporal safety. `LIMIT`, sampling, ranking,
  or top-k selection is opaque because rows inspect global ordering/cardinality.
- `LEAD`, a following/centered window, or a proved later-key join is retrospective—not an
  ordinary opaque query—and cannot enter a decision build under an unsafe override.
- A semicolon or forbidden keyword inside a quoted literal/comment does not create a second
  statement. Two parsed statements always fail.
- SQL differing only in whitespace has a different text/execution content ID. Exact retry
  means byte-equivalent normalized text plus identical context, not optimizer equivalence.
- Advancing `workspace.cleaned_daily` to version 2 leaves version 1 queryable and preserves
  every dependency that pinned version 1.
- Cancellation after staging but before publication exposes neither metadata nor a friendly
  name advance. Recovery cannot bless staging as complete.
- Empty universe/build/query results retain exact schemas, manifests, classifications, and
  deterministic empty content roots.
- An unsafe or opaque artifact cannot become safe through selection, projection, casting,
  hashing, aggregation, renaming, or rematerialization alone.

## 23. Migration, compatibility, and extension policy

Plan-02 research migrations create the `research` metadata tables plus migration-owned
`research_data` schema and install workspace relation templates in the existing controlled
`workspace` schema. They also install indexes/constraints, parser/analyzer manifests, and
recovery metadata. No migration writes a market database. Dynamic physical relations are
created only by the managed repositories from validated templates, never by caller SQL.

This is a greenfield 3.0 contract. There is no automatic import of unversioned v2 pandas
frames, DuckDB tables, SQL views, pickles, or notebooks as safe decision datasets. An
explicit importer may register them as opaque analysis dependencies with original bytes,
schema, provenance, and licensing evidence; it cannot infer historical cutoffs or causal
lineage.

Compatibility rules are:

- changing dataset row meaning, joins, cutoffs, inputs, schema, or missing behavior appends
  a dataset-definition version or allocates a new identity as section 6 requires;
- changing workspace SQL, parameters, dependencies, analyzer/environment, limits, or output
  schema appends a workspace version;
- changing parser/analyzer/function-allowlist semantics changes component/execution identity
  and never rewrites an old classification;
- plan 08 implements the feature/label input kinds and separate physical schemas without
  weakening this plan's label boundary;
- plan 09 may consume structurally eligible decision handles and explicit unsafe overrides,
  but cannot recreate temporal selection from workspace SQL;
- plan 10 consumes exact decision handles through its own signal/forecast/risk/portfolio
  adapters and may use labels only inside its validation-capability fit service; it adds no
  ordinary fit/forecast/risk `ResearchInputKind` here and cannot weaken structural
  dataset/workspace rules;
- plan 14 may add attempts, caching, compatible reuse, and recovery orchestration without
  changing immutable completed occurrence identity; and
- future deletion/retention/compaction must prove no completed manifest, run, result,
  report, or event references the object and remains outside 3.0.

Persisted enum values and reason meanings append only. Schema readers reject unsupported
versions rather than guessing. Physical relation names, DuckDB plans, internal attachment
aliases, and file paths are implementation details and never portable public identity.

## 24. Acceptance tests and exit criteria

### 24.1 Definition, schedule, and cutoff tests

- Property tests reproduce definition content across insertion order, process, and platform
  and distinguish every semantic input/policy change.
- Registration rejects invalid names, ordinals, aliases, schemas, reserved columns,
  unsupported input kinds, missing domain policies, label/retrospective decision inputs, and
  nonreproducible content.
- Golden tests cover calendar decisions across DST, early close, holiday override, and
  empty intervals with exact universe/cutoff schedules.
- Dual-cutoff tests prove public and project cutoffs independently exclude candidates and
  that later ingestion/correction/retraction cannot change an existing execution.
- Future-candidate sentinel tests compare causal outputs/audits byte-for-byte before and
  after inserting evidence unavailable at the decision/project cutoff.

### 24.2 Selection, join, and audit tests

- Golden tests cover every canonical domain adapter from plans 04–06, source precedence,
  selected revision/retraction/conflict, raw/adjusted bars, release/vintage, benchmark
  membership, and fixed-tenor rates.
- Exact, backward-as-of, and interval joins cover boundary equality, staleness, explicit
  unbounded age, global broadcast, entity bridges, and no forward/nearest fallback.
- Feature-adapter tests enforce exact/backward-only keys and per-output availability
  cutoffs; label-adapter tests enforce analysis-role/exact-key-only selection, closed
  interval preservation, and complete rejection from decision role.
- Duplicate base/candidate/cardinality faults fail deterministically in every partitioning;
  partition sizes and input order do not change selected rows, audits, or manifests.
- Every `MissingInputAction` has golden counts and row/input audit states. Count constraints
  reproduce from physical output/audit tables.
- Empty, all-missing, all-dropped, unusable, unsafe, source-missing, unavailable,
  component-noncomputed/warmup/censored/ambiguous/invalid, retracted, conflict, and
  not-evaluated panels retain exact schemas and reasons.
- Manifest tests reproduce ordered chunk roots, lineage IDs, licensing, findings, and
  dataframe schemas without copying licensed values into diagnostic metadata.

### 24.3 SQL and workspace tests

- Parser tests accept one `SELECT`/`WITH ... SELECT`, comments/quoted semicolons, positional
  parameters, and bound `ctx` relations; they reject every forbidden statement/node,
  physical relation, external/table function, metadata scan, UDF, multi-statement request,
  identifier parameter, and unresolved/ambiguous reference.
- Security tests prove no filesystem/network/object-store/Python object/session mutation or
  extension loading is reachable, including through nested CTEs, aliases, table functions,
  macros, or parser edge cases.
- Analyzer golden tests classify the complete row-local allowlist and every opaque
  construct; prove row-local filters retain only a validated panel-subset contract; prove
  key loss, labels, retrospective ancestry, or incomplete dependency-root closure cannot
  retain structural eligibility; and prove mixed snapshots, fixed-as-of joins, partial
  lineage, and unsafe ancestors never claim a safe causal panel.
- SQL text/parameter/dependency/environment identity tests distinguish every relevant byte,
  type, binding, snapshot, analyzer, limit, and output schema change.
- Output-contract tests round-trip every supported SQL type/dtype, typed-ID tag, null and
  empty schema; reject invalid names, duplicate columns, nonfinite/oversized values, naive
  time, nested/blob/JSON/unsupported numeric types, and computed UUID key forgery.
- Workspace tests cover version creation/advance/conflict/exact retry, pinned old versions,
  transitive classifications, dependency cycles, output hashing/order, empty output,
  cancellation, staged failure, and atomic friendly-name publication.
- Fuzz/property tests bound parser depth/AST size and verify forbidden statements never
  reach execution. Timeout, memory, temp, column, row, parameter, and iterator-abandonment
  tests leave no visible partial result.

### 24.4 API, concurrency, and persistence tests

- Public handles expose no raw connection, internal relation name, market attachment name,
  or path and remain usable only through the owning open project lifecycle.
- Dataframe tests assert exact columns/order/dtypes/nulls/UTC normalization, immutable result
  metadata, deterministic chunks, explicit preview truncation, and ordinary limit failure.
- Concurrent writers serialize through the research lease; readers see either the old
  complete state or new complete state, never staging or a half-published name/version.
- Fault injection at every staging, validation, manifest, metadata, event, and commit step
  proves all-or-nothing publication and deterministic retry/recovery behavior.
- Reopen/copy/snapshot tests preserve immutable IDs/manifests and diagnose missing/corrupt
  dynamic relations before returning data.

### 24.5 Exit criteria

This plan is complete when:

- all public IDs, enums, models, schemas, APIs, limits, events, exceptions, and reason codes
  above are implemented and documented;
- every domain adapter selects through its owning plan and the common cutoff/temporal
  envelope without future-evidence leakage;
- dataset/workspace outputs, audits, lineage, safety, licensing, and manifests reproduce
  under deterministic partitioning and exact retry;
- SQL is demonstrably read-only/external-disabled and its temporal claims are limited to
  the proved analyzer subset;
- structural label/retrospective exclusion works transitively and cannot be overridden;
- plan-10 fit/release subjects remain unavailable to this builder and only the separate
  release adapter can prove a causal decision row without hiding its training-audit roots;
- no partial/corrupt publication becomes visible under concurrency, crash, cancellation,
  or resource failure; and
- lint, static types, tests, docs checks, strict docs build, and the agreed coverage gate
  pass.

## 25. Review checklist for dependent plans

Every later plan that consumes research data must state:

- the exact definition/build/materialization ID and version, composite/member snapshot,
  universe evaluation, decision schedule, public/project cutoffs, and base row grain;
- the ordered inputs, source/revision/domain policies, entity bridge, temporal join,
  staleness, projection/unit semantics, and missing action;
- whether it uses a fixed-as-of relation, period panel, or true decision panel and why that
  temporal contract survives each transformation;
- information class, safety status/findings, lineage completeness, licensing/export class,
  and whether dependencies all share the required snapshot/cutoff schedule;
- how missing, unavailable, source-missing, stale, retracted, conflicted, unsafe, unusable,
  dropped, and empty states affect eligibility rather than silently disappearing;
- whether SQL/workspace operations are row-local/key-preserving or opaque, including exact
  analyzer and dependency manifests;
- how transitive labels/retrospective information are structurally separated from decision
  inputs and strategy-visible event handling;
- the limits, partition/order/content-hash rules, dataframe boundary, and failure behavior;
- which exact immutable occurrence enters later feature, run, simulation, result, report,
  cache, or reuse identity; and
- any requested unsafe override, which a later run-level policy must record without
  relabeling the underlying artifact safe.

Plan 08 builds feature and label materializations on these dataset/input/lineage rules,
including structural separation. Plan 09 must accept only exact structurally eligible
decision handles and own explicit unsafe-analysis permission. Plan 10 must retain this
plan's ordinary fold for dataset/workspace inputs while using its separately typed causal-
fit release for label-trained forecasts/risk; no fit or raw label becomes decision data.
Plans 10–13 must preserve missing/unsafe states into signals, targets, orders, accounting,
and simulation. Plans 14–18 must retain
execution/dependency identity, licensing, safety, and deterministic auditability through
reuse, optimization, analytics, reporting, extensions, and final hardening.

## 26. Consistency with the umbrella and completed plans

This specification refines umbrella plan 07 without changing its intent. It composes the
already completed contracts as follows:

- plan 01 owns typed identity, content serialization, UTC/duration/numeric semantics,
  lifecycle events, clock injection, and public error foundations;
- plan 02 owns project modes, database ownership, leases, migrations, connections,
  transactions, copies, recovery boundaries, and structured observability;
- plan 03 owns catalog/source identity, canonical revision/retraction/source precedence,
  public/project availability, licensing, market/composite snapshots, and validation;
- plan 04 owns instrument/reference/calendar/decision/universe identity and causal universe
  evaluation, including the exact `CutoffMode` and public-cutoff policy reused here;
- plan 05 owns bars/trades/quotes/status/actions/adjustments and registered market query
  adapters, including actual interval times and point-in-time action safety; and
- plan 06 owns filing/estimate/macro/benchmark/risk-free definitions, revision/release/
  vintage selection, numeric semantics, temporal evidence, and domain query adapters.

Research services consume those public repositories and immutable manifests; they do not
read canonical physical tables directly, reconstruct domain resolution, mutate market
files, reinterpret availability, or invent new identity/time/numeric rules. Any future
conflict is resolved by strengthening the owning focused plan and this composition contract
together, never by silently forking semantics inside a workspace query.
