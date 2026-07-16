# Persistra v3 Greenfield Specification

**Status:** Draft umbrella specification  
**Target release:** 3.0.0  
**Last updated:** 2026-07-15  
**Scope:** Complete greenfield replacement of the existing project

## 1. Purpose and status

This document defines the proposed full-project direction for Persistra v3. It is the
umbrella specification for a clean-slate quantitative research library covering market
data, exploratory research, feature and label engineering, alpha analysis, portfolio
construction, simulation, experiments, result analysis, visualization, and reporting.

The document is intentionally broader than an implementation plan for any one component.
It establishes boundaries, terminology, dependency direction, workflows, reliability
expectations, and a staged delivery plan. Before implementation, each major subsystem must
receive a focused specification with exact schemas, APIs, algorithms, edge cases, and
acceptance tests.

The words **must**, **should**, and **may** express draft design intent:

- **Must** identifies a requirement for v3 to satisfy this specification.
- **Should** identifies the preferred design, subject to revision in a focused spec.
- **May** identifies an optional capability that must not compromise required behavior.

No portion of the v2 API, architecture, storage layout, examples, or documentation is a
compatibility constraint. A concept is included only if it independently belongs in v3.
There will be no compatibility shims, migration helpers, or v2-to-v3 API mapping. From a
user-facing design perspective, v3 should behave as though v2 never existed.

## 2. Mission

Persistra v3 is a local-first quantitative research workbench for developing, validating,
simulating, and analyzing equity and ETF strategies. It emphasizes point-in-time
correctness, explicit assumptions, reproducible workflows, statistically disciplined
evaluation, and realistic portfolio and execution modeling on commodity hardware.

The intended user is a Python-capable individual researcher progressing from educational
quantitative work toward professional-quality research. The library should remain
approachable enough to teach its models, while being rigorous enough that showcased
strategies and results withstand serious technical scrutiny.

“Near-production quality” means that research code, provenance, temporal semantics,
accounting, simulation assumptions, diagnostics, and tests are engineered carefully. It
does not mean that v3 is a production trading system or that strategies can be routed to a
broker unchanged.

## 3. Design principles

### 3.1 Correctness before convenience

Persistra must not make an unrealistic assumption merely to simplify an implementation
and then hide that assumption behind a friendly API. When an exact market fact cannot be
known from the input data, the system must represent a model, policy, range, warning, or
unavailable result rather than invent certainty.

### 3.2 Point-in-time by construction

Historical research must distinguish when something happened from when it became
knowable. Data revisions, changing identifiers, universe membership, fundamentals,
estimates, and macroeconomic vintages must be selected using explicit as-of semantics.
Public availability and Persistra's own receipt time are separate cutoffs. Unsafe data may
be explored, but simulations must reject it by default.

### 3.3 Explicit information and timing boundaries

Every price-dependent decision or state transition must identify which observations it
uses and when they became available. Decision time, order creation, submission,
eligibility, activation, and fill time are distinct concepts.

### 3.4 Separation of concerns

Data ingestion, research transformations, forecasting, portfolio construction, order
generation, execution simulation, accounting, analysis, and presentation must remain
separate. A high-level workflow may compose them, but no monolithic engine or data-store
class should absorb unrelated responsibilities.

### 3.5 Composable research components

Features, labels, signals, forecasts, portfolio constructors, constraints, risk models,
rebalance policies, cost models, and simulators should be independently testable and
composable. Stateful callback strategies remain possible for genuinely event-dependent
logic but are not the only or default abstraction.

### 3.6 Reproducibility and auditability

Every material result must be traceable through its design, execution, attempt, artifact,
and, when applicable, analysis identities to an immutable data snapshot, resolved
configuration, source code state, dependency environment, random seeds, temporal split,
simulation fidelity profile, warnings, and structured history.

### 3.7 Local-first operation

The normal workflow must require no server. One Linux workstation, Python environment,
and local DuckDB files should be sufficient. The architecture should exploit a 32 GB
research laptop without assuming that all input data fits in memory.

### 3.8 SQL and Python as complementary research surfaces

DuckDB should perform large scans, filters, joins, windows, and point-in-time selection.
Python and pandas should support numerical research and ecosystem interoperability. Users
may query documented SQL views, but managed writes must pass through Persistra services.

### 3.9 Immutable facts, derived views

Source observations and committed run and analysis records should be append-only or
revision-preserving. Adjusted prices, standardized facts, features, labels, positions,
metrics, and reports are derived products whose lineage must remain inspectable.

### 3.10 Honest performance

Vectorized workflows should be fast, and event simulation should be efficient, but the
library must not trade away temporal or accounting correctness for a benchmark. Fidelity
and performance are separate axes.

### 3.11 Extensibility without premature abstraction

Persistra v3 is one package and supports one database engine. It should define extension
contracts for provider adapters, custom data, features, portfolio components, and models,
but it must not add generic backends or plugins without a concrete use case.

## 4. Goals

Persistra v3 must treat the following as first-class workflows:

- Exploratory market and reference-data analysis
- Point-in-time universe definition and inspection
- Feature engineering and reusable feature materialization
- Label engineering with structural leakage separation
- Alpha and factor analysis before portfolio simulation
- Signal and forecast evaluation
- Portfolio construction, risk modeling, and constrained optimization
- Fast vectorized portfolio simulation
- Stateful event-driven order and execution simulation
- Grid, random, Bayesian, and custom parameter searches
- Walk-forward evaluation
- Finance-aware temporal cross-validation
- Scenario and stress testing
- Monte Carlo and bootstrap analysis
- Benchmarking and strategy comparison
- Result diagnostics, attribution, and capacity analysis
- Reproducible notebooks
- Self-contained HTML research reports
- A local read-only interactive dashboard delivered through an optional installation extra

Supporting goals include:

- Canonical ingestion and validation contracts for external provider repositories
- Structured, versioned, user-facing dataframes
- SQL access for nonstandard research queries
- Deterministic and resumable local studies
- Portable run exports
- Clear extension paths for future datasets and simulation fidelity

## 5. Non-goals for 3.0

The following are explicitly outside the 3.0 scope:

- Compatibility with any v2 API, file layout, or persisted artifact
- Migration tooling from v2
- Live trading or broker integration
- A long-running paper-trading service
- Production operations, recovery, alerting, or deployment guarantees
- Vendor-specific acquisition clients in the main repository
- Asset classes other than equities and ETFs
- Options exercise and assignment
- Futures rolls and variation margin
- ETF creation and redemption mechanics
- FX and cross-currency accounting
- Fixed-income cash-flow modeling
- Full trade-and-quote market replay
- Level-2 order-book storage or exchange queue simulation
- Exact matching-engine or broker behavior
- Distributed compute infrastructure
- Shared, multi-user database operation
- PostgreSQL, SQLite, or a generic database-backend abstraction
- A hosted web product, authentication, or user management
- Tax reporting or tax-aware portfolio optimization
- Built-in domain models for specific alternative datasets
- An in-house machine-learning framework
- A general workflow scheduler or MLOps platform
- Guaranteed support for unstructured text, image, audio, or video storage in DuckDB
- Windows support in the initial release

These exclusions do not prohibit future work. They prevent v3 from implying support that
its data, models, tests, and operating architecture cannot honestly provide.

## 6. Supported market scope

### 6.1 Geography and currency

The implemented 3.0 scope is US-listed, USD-denominated equities and ETFs. Currency is
still stored explicitly on instruments, prices, and cash accounts so multi-currency
support can be added without replacing the domain model.

### 6.2 Instruments

The following instruments are supported directly:

- Exchange-listed common stock
- Exchange-traded funds
- REITs
- Listed ADRs
- SPAC common shares

Preferred shares and closed-end funds should be representable but receive no specialized
modeling guarantee. Warrants, rights, units, and OTC securities are excluded from the
implemented 3.0 workflows. SPAC support therefore begins at unit separation:
pre-separation SPAC units follow the units exclusion.

The instrument model must distinguish:

- **Issuer:** the legal or reporting entity
- **Security:** the financial claim issued by an issuer
- **Listing:** a security’s presence on a venue under effective-dated identifiers
- **Instrument:** the tradeable listing used by market and simulation records
- **Identifier:** an effective-dated external or vendor identity

Ticker symbols are attributes, never primary keys. The identifier system should support
ticker, exchange ticker, FIGI, composite FIGI, CUSIP, ISIN, CIK, LEI, and arbitrary vendor
identifiers without requiring every identifier for every instrument.

### 6.3 Market frequencies

The simulators must support robust daily and intraday fixed-time bars. Canonical bars use
explicit interval start and end timestamps rather than one ambiguous timestamp. Common
daily, hourly, minute, and second frequencies should be validated; arbitrary fixed
durations may be represented.

Trades and top-of-book quotes are canonical 3.0 datasets for research. They are not
required inputs to the 3.0 simulators. Their schemas and event types must leave room for a
future market-replay simulator without pretending that it already exists.

Volume, dollar, tick, imbalance, and other non-time bars are derived custom datasets in
3.0, not canonical market observations.

## 7. Reliability contract

Persistra should publish a precise reliability contract. The following guarantees are
required at the umbrella-spec level; focused specs must turn each into concrete
invariants and acceptance cases.

| Area | Required guarantee | Honest boundary |
| --- | --- | --- |
| Information | Strategy-visible data satisfies its public and configured project-knowledge cutoffs | Unsafe overrides are explicit and contaminate downstream artifacts |
| Revisions | Historical queries select the revision-specific applicable known revision | Unknown correction availability is ingestion-bounded and unsafe |
| Identity | Instruments survive ticker and venue changes | Vendor mappings may remain incomplete and diagnosable |
| Universe | Eligibility is point-in-time with reasons for inclusion/exclusion | A present-day universe is unsafe for historical simulation |
| Calendar | Sessions, holidays, timezones, and DST are explicit | Unsupported venues cannot silently use a weekday calendar |
| Corporate actions | Holdings, cash, identity, and entitlements are adjusted auditably | Unsupported entitlements remain explicit unresolved state |
| Missing data | Missing, stale, halted, invalid, and unavailable prices are distinct | Halts are distinguished only when trading-status observations exist; no synthetic price or fill is fabricated by default |
| Orders | Every order has a complete state-transition history | Coarse data limits fill certainty |
| Execution | Spread, latency, fees, slippage, participation, and impact are explicit | Bar data cannot reveal queue priority or exact intrabar path |
| Shorting | Borrow, fees, availability, collateral, and margin are modeled | Broker-specific locate behavior is excluded |
| Settlement | Cash and asset settlement follow effective-dated policies | Cross-market settlement is deferred |
| Accounting | The journal balances and all projections reconcile | Numerical tolerances and rounding policies are explicit |
| Determinism | Deterministic-capable matching execution identity replays deterministically | Opaque external state is ineligible; compatible reuse is warned |
| Comparison | Incompatible fidelity or safety profiles are flagged | The library cannot make incomparable assumptions equivalent |

### 7.1 Unsafe data

Exploratory queries may use observations whose availability semantics are unknown. A
simulation must reject such inputs by default. An explicit unsafe override may allow the
run, but must:

- Set a run-level unsafe flag
- List every unsafe dataset and reason
- Appear prominently in summaries and reports
- Propagate into derived features, labels, comparisons, and exports
- Prevent accidental presentation as a safe result

Opaque Python, unrestricted SQL, workspace tables with incomplete lineage, and derived
data whose temporal behavior has not passed the required conformance contract are unsafe
by default. An unsafe override may admit opaque code or data while preserving the run-level
taint. A dependency on a label is a structural violation rather than an ordinary unsafe
input and can never enter a simulation decision dataset.

There is no normal public API for bypassing structural ingestion validation.

## 8. Primary workflows

### 8.1 Initialize and open a project

The user may initialize an optional project skeleton with `persistra init`. A project
contains portable configuration, Python research code, notebooks, reports, and a hidden
local state directory. Existing Python projects may open Persistra without adopting the
generated layout.

`Project` is the main lifetime and service boundary. It resolves configuration, acquires
database leases, opens databases, checks schema versions, controls transactions, and
exposes namespaced services. It is synchronous and used as a context manager.

### 8.2 Ingest provider data

Provider adapters live in separate repositories. An adapter obtains source data, archives
raw provider payloads when desired, translates records to canonical staging models, and
submits a batch to Persistra.

Persistra validates the entire batch, records findings, and then rejects it, quarantines it
as a whole, commits it, or atomically commits accepted records while quarantining affected
records. A successful full or partial commit creates a dataset revision eligible for a new
snapshot. Adapters never write directly into managed canonical tables.

### 8.3 Explore and inspect data

The user queries canonical views through typed Python methods or parameterized read-only
SQL. Query results materialize as pandas dataframes. Coverage, source, revision, public
availability, local receipt, quality, eligibility, and safety information must be
inspectable alongside values.

### 8.4 Construct a point-in-time universe

Universe definitions may combine memberships, listings, classifications, prices,
liquidity, fundamental conditions, and custom eligibility rules. Evaluation occurs as of
each decision point. Failed eligibility rows remain available with reason codes rather
than disappearing silently.

### 8.5 Build features and labels

Features and labels are registered, versioned definitions with declared inputs,
parameters, lookback or horizon, frequency, entity scope, temporal behavior, execution
trust, and output schema. SQL and Python implementations share one dependency, safety, and
provenance model.

Labels intentionally use future information and live in separate schemas and APIs. They
cannot enter a strategy’s decision dataset. Materializations are reused only when their
data snapshot, parameters, and complete execution identity match.

Materialization binds an exact completed base research-dataset build. An enriched research
dataset then binds exact completed feature/label materialization occurrences; it does not
refer to a moving definition name or create a circular dependency on the build being
produced. Convenience orchestration may perform those stages in order while preserving the
same immutable identities.

### 8.6 Evaluate alpha before simulation

The user measures signal coverage, information coefficients, quantile returns, turnover,
decay, autocorrelation, exposures, monotonicity, stability, and regime behavior before
introducing portfolio and execution assumptions.

### 8.7 Construct a portfolio

Signals with declared meaning become forecasts or allocation inputs. Portfolio rules or
optimizers apply risk models, constraints, costs, and benchmark information to produce a
target portfolio. A rebalance policy compares current and target state and emits orders.

### 8.8 Run a vectorized simulation

The vectorized simulator provides rapid research iteration over target holdings or
weights. It still uses explicit timing, costs, accounting, and normalized results. Its
fidelity profile makes clear which order-level behaviors were bypassed.

### 8.9 Run an event simulation

The event simulator processes chronologically ordered information, strategy decisions,
orders, market eligibility, partial fills, settlement, financing, corporate actions,
margin, and accounting. Every state transition is recorded.

### 8.10 Run a study

A study combines parameter trials, temporal folds, scenarios, and simulation runs. Local
workers read immutable market snapshots under shared leases and write isolated temporary
result databases. A coordinator validates and transactionally merges completed outputs
into the research database. Interrupted work resumes from recorded execution identities as
new attempts.

### 8.11 Analyze and communicate results

The user queries structured results and creates immutable analysis artifacts for metrics,
attribution, comparisons, and diagnostics. Visualizations and self-contained HTML reports
pin the exact run and analysis artifacts they render. Completed artifacts may also be
explored in the read-only dashboard when its optional installation extra is present.

## 9. System architecture

### 9.1 High-level flow

```text
external provider adapter
        │
        ▼
canonical staging records
        │
        ▼
validation ──────► rejection or quarantine
        │
        ▼
market database + immutable snapshot
        │
        ▼
point-in-time research dataset
        │
        ├────► features and labels ────► alpha analysis
        │
        ▼
signal or forecast
        │
        ▼
portfolio construction and rebalance policy
        │
        ├────► vectorized simulation
        │
        └────► orders ─► execution ─► accounting
                                │
                                ▼
                    research database + run artifact
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
                 notebook    HTML report  dashboard
```

### 9.2 Dependency direction

```text
domain
  ↓
database, catalog, ingestion, and market data
  ↓
research datasets, features, labels, and portfolio construction
  ↓
simulation and experiments
  ↓
results and analysis
  ↓
visualization, reports, and dashboard
```

Lower layers must not import higher layers. In particular:

- Market-data code must not depend on simulation.
- Accounting must not depend on a strategy implementation.
- Simulation must not depend on Plotly, reporting, or Streamlit.
- Metrics must not be implemented inside visualization functions.
- Dashboard pages must use the same public result and analysis APIs as notebooks.
- Provider packages must depend on Persistra’s ingestion contract, not vice versa.

## 10. Proposed repository structure

```text
persistra/
├── AGENTS.md
├── LICENSE
├── README.md
├── Makefile
├── pyproject.toml
├── uv.lock
├── mkdocs.yml
├── benchmarks/
│   ├── datasets/
│   ├── research/
│   └── simulation/
├── docs/
│   ├── v3-spec.md
│   ├── v3/
│   │   ├── 01-domain-identity-time-money-events.md
│   │   └── ...
│   ├── getting-started/
│   ├── concepts/
│   ├── data/
│   ├── research/
│   ├── portfolio/
│   ├── simulation/
│   ├── experiments/
│   ├── analysis/
│   ├── results/
│   ├── recipes/
│   ├── architecture/
│   └── reference/
├── examples/
│   ├── fixtures/
│   ├── notebooks/
│   ├── strategies/
│   └── projects/
├── scripts/
│   ├── checks/
│   └── fixtures/
├── src/
│   └── persistra/
└── tests/
    ├── unit/
    ├── integration/
    ├── contracts/
    ├── scenarios/
    ├── properties/
    ├── migrations/
    ├── documentation/
    └── performance/
```

The final docs tree will be created incrementally. Accepted planning detail is broken into
numbered focused component specifications under `docs/v3/`; each document links back to
this umbrella specification and is reviewed cumulatively as later plans are added.

## 11. Proposed package structure

```text
src/persistra/
├── __init__.py
├── project.py
├── config/
│   ├── models.py
│   └── loading.py
├── domain/
│   ├── identifiers.py
│   ├── money.py
│   ├── time.py
│   ├── instruments.py
│   └── events.py
├── db/
│   ├── connection.py
│   ├── migrations.py
│   ├── queries.py
│   └── migrations/
├── catalog/
│   ├── datasets.py
│   ├── sources.py
│   ├── batches.py
│   ├── snapshots.py
│   └── quality.py
├── ingestion/
│   ├── records.py
│   ├── staging.py
│   ├── validation.py
│   ├── quarantine.py
│   └── writer.py
├── market/
│   ├── instruments.py
│   ├── calendars.py
│   ├── bars.py
│   ├── trades.py
│   ├── quotes.py
│   ├── status.py
│   ├── actions.py
│   ├── fundamentals.py
│   ├── estimates.py
│   ├── macro.py
│   ├── benchmarks.py
│   ├── rates.py
│   ├── universes.py
│   └── adjustments.py
├── research/
│   ├── datasets.py
│   ├── eligibility.py
│   ├── temporal.py
│   ├── sql.py
│   ├── workspace.py
│   ├── safety.py
│   ├── materialization.py
│   ├── components/
│   ├── conformance.py
│   ├── features/
│   ├── labels/
│   ├── alpha/
│   └── validation/
├── portfolio/
│   ├── signals.py
│   ├── forecasts.py
│   ├── allocation.py
│   ├── optimization.py
│   ├── constraints.py
│   ├── risk_models.py
│   └── rebalance.py
├── simulation/
│   ├── configuration.py
│   ├── fidelity.py
│   ├── vectorized/
│   ├── event/
│   ├── orders/
│   ├── execution/
│   └── accounting/
├── experiments/
│   ├── studies.py
│   ├── trials.py
│   ├── folds.py
│   ├── scenarios.py
│   ├── search.py
│   ├── runner.py
│   └── registry.py
├── results/
│   ├── models.py
│   ├── repository.py
│   ├── exports.py
│   └── comparison.py
├── analysis/
│   ├── performance.py
│   ├── risk.py
│   ├── benchmark.py
│   ├── execution.py
│   ├── attribution.py
│   ├── capacity.py
│   ├── statistics.py
│   └── scenarios.py
├── viz/
│   ├── performance.py
│   ├── portfolio.py
│   ├── execution.py
│   ├── attribution.py
│   ├── diagnostics.py
│   └── style.py
├── reports/
│   ├── builder.py
│   ├── sections.py
│   └── templates/
├── dashboard/
│   ├── app.py
│   ├── state.py
│   └── pages/
├── cli/
│   ├── main.py
│   └── commands/
└── _internal/
```

This is a boundary map, not a promise that every leaf becomes a separate file. Focused
design should collapse empty abstractions and split files that become too broad.

## 12. Project and configuration model

### 12.1 Workspace

A conventional project may use:

```text
my-strategy/
├── persistra.toml
├── notebooks/
├── research/
├── strategies/
├── tests/
├── reports/
└── .persistra/
    ├── research.duckdb
    ├── artifacts/
    ├── logs/
    └── tmp/
```

The structure is optional. `Project.open(path)` locates `persistra.toml`, resolves paths,
and constructs the same services in any Python repository.

### 12.2 Configuration

`persistra.toml` contains infrastructure and portable project defaults, including:

- Project name
- Registered market databases
- Research database location
- Artifact and temporary directories
- Default calendar, universe, benchmark, and risk-free series
- Logging and resource defaults

Strategy graphs and arbitrary Python callables do not belong in TOML. Python is the
authoritative configuration surface for research logic.

Environment substitution is limited to path values. Secrets belong to external provider
adapters and machine-local configuration, not committed project files. Explicit Python
arguments override TOML values without mutating global state.

`persistra.toml` is strictly validated: unknown keys are rejected and values are typed.
The configuration schema evolves only backward-compatibly within 3.x through additive
keys with defaults, so no configuration version field or migration mechanism is required.

### 12.3 Composite snapshots

A project may register multiple market databases by logical name. A composite research
snapshot records one immutable snapshot identifier for each database used. No query may
silently combine “latest” states captured at different moments.

## 13. Database architecture

### 13.1 DuckDB only

DuckDB is the sole managed database backend. Persistra must use DuckDB directly rather
than SQLAlchemy or a lowest-common-denominator abstraction. SQLite and PostgreSQL adapters
are not planned for 3.0.

### 13.2 Database separation

Persistra uses two logical database roles:

- **Market databases** contain canonical source observations, reference data, lineage,
  validation state, and snapshots. A market database may be shared read-only by many
  research projects.
- **Research databases** contain controlled workspace materializations, features, labels,
  studies, runs, results, immutable analysis artifacts, annotations, and artifact
  manifests. Each project normally has its own research database. Migration-owned
  `research_data`, `feature_data`, and `label_data` schemas keep immutable dynamic
  outputs physically separated without exposing caller DDL or relation names.

This separation prevents one strategy project from owning the market-data source of truth
and allows large canonical datasets to be reused.

### 13.3 Concurrency

One process owns writes to a managed DuckDB database. Multiple workers may open immutable
market databases read-only. Parallel study workers write isolated temporary DuckDB files;
the coordinator validates and merges them transactionally.

Persistra coordinates every managed database with an application-level shared/exclusive
lease in addition to DuckDB's file lock. Read-only projects and study workers hold shared
leases. Ingestion, migrations, and other writers require an exclusive lease and fail with
an actionable ownership error by default when readers are active; an explicit bounded wait
may be requested. An ordinary study therefore blocks ingestion into each market database
it reads for the study's lifetime.

When concurrent ingestion is necessary, the user may create a verified physical snapshot
copy and point the study at that immutable file. The copy records its source database,
logical snapshot, checksum, DuckDB storage identity, and verification result. Logical
snapshot identifiers alone do not bypass file-locking constraints.

DuckDB does not permit read-only attachment to a database file that another process holds
open for writing. Readers of the research database, including the dashboard, therefore
operate only while no writer is active. Inspecting results concurrently with an active
study means pointing the reader at a verified backup or portable run export instead of
the live research database. This limitation is documented rather than hidden behind a
synchronization mechanism.

DuckDB files must not be opened for active read-write use over network-mounted storage.
Cross-device synchronization is external to Persistra. Persistra should provide verified
backup, export, and snapshot-manifest operations that make external synchronization safe.

### 13.4 SQL surface

Users receive:

- Typed high-level query methods for standard workflows
- Parameterized, read-only SQL over documented typed operation-context relations
- Controlled materialization of `SELECT` queries into immutable versioned workspace objects
- Explicit pandas materialization

Every controlled SQL materialization records the normalized query and content identity,
source snapshots, referenced datasets and columns when resolvable, analyzer/executor
identity, label dependencies, and inherited safety findings. SQL UDFs and external scans
are unsupported in 3.0. Lineage or temporal behavior that cannot be resolved makes the
output unsafe. Label-derived output remains ineligible for simulation decision datasets
regardless of an unsafe override.

Persistra does not expose its raw connection as supported public API. Arbitrarily opening
and mutating a managed DuckDB file outside Persistra is unsupported and may violate schema,
lineage, migration, or snapshot invariants.

Managed writes use ingestion, feature, experiment, result, annotation, and workspace APIs.
Direct SQL writes to managed schemas are unsupported.

### 13.5 Pandas boundary

Pandas is the only supported public dataframe representation in 3.0. NumPy may be used for
numerical kernels, and DuckDB may use internal interchange mechanisms, but Arrow and
Polars are not public domain contracts. Public result dataframes should favor explicit
columns over semantic indexes and must have versioned schema contracts.

### 13.6 Schemas and migrations

Managed tables are organized into named DuckDB schemas separating catalog, canonical
data, quality state, snapshots, workspace data, research materializations, experiments,
results, immutable analysis artifacts and their caches, and annotations.

All schema changes use versioned forward migrations. Writable open detects version
mismatches. Nontrivial migrations require an explicit CLI operation and create a verified
backup by default. Pre-release development databases may be declared disposable until
schema stability is reached.

## 14. Temporal and revision model

### 14.1 Temporal fields

Canonical observations use the temporal fields relevant to their domain. Common concepts
include:

- `event_at`: when the represented market or business event occurred
- `published_at`: when the source reports publishing that specific observation or revision
- `available_at`: the resolved instant when that specific revision became eligible under a
  documented public-information policy
- `ingested_at`: when Persistra received that specific revision
- `source_updated_at`: a distinct source-reported update time when it is not the publication
  time
- `valid_from` and `valid_to`: the effective interval for identities or memberships
- `interval_start` and `interval_end`: the covered interval for bars or period data
- `session_date`: the venue-local trading session

Each revision also records an availability-quality classification such as observed,
policy-derived, conservatively bounded by ingestion, or unknown. Public-information queries
apply `available_at`; project-knowledge queries additionally apply an `ingested_at` cutoff.
Both modes remain bounded by the selected immutable snapshot.

Names and exact SQL types require a focused schema spec, but the distinctions must remain.

### 14.2 Append-only revisions

New observations and corrections are appended. A stable natural identity, source,
revision relationship, batch identifier, payload hash, and revision-specific availability
allow conflicts and supersession to be resolved. Canonical as-of views choose the
applicable revision known by the requested public and, when selected, project-knowledge
cutoffs. A correction never inherits the original observation's availability silently.
When a correction changes a natural-key field, it appends an explicit retraction to the
old key's revision chain and an upsert to the corrected key in one atomic disposition
group. The old bytes remain auditable; no row is updated or deleted.

Full copies of every dataset are not created for every snapshot. A snapshot should pin
committed revisions through a catalog sequence, manifest, content identity, or equivalent
immutable mechanism defined by the storage spec.

Committed canonical data is retained indefinitely. 3.0 provides no deletion or compaction
of committed batches or revisions; reclaiming space means rebuilding a market database
from sources. Run deletion in the research database is governed separately by the
results-and-artifacts rules.

### 14.3 Availability policies

When a source does not provide `published_at` or direct availability metadata, a
dataset-specific policy applies to the original observation:

- Bars become available at interval end plus declared publication latency.
- Corporate actions become available from their announcement or publication observation;
  declaration, ex, record, effective, and payment dates remain separate event fields used
  by the research question and entitlement policy.
- Fundamentals require filing or publication availability for safe point-in-time use.
- Estimates require the publication or revision timestamp.
- Macro series require release vintage and publication time.
- Universes require both effective intervals and membership-publication metadata.
- Unknown custom datasets are unsafe for simulation unless an explicit policy is supplied.

A later correction or revision without a source publication timestamp receives an
`available_at` no earlier than `ingested_at` and an ingestion-bounded unsafe classification.
It cannot use the original observation's interval-end policy. A reviewed dataset policy may
classify deterministic original-observation latency as safe, but the library must never
silently substitute `event_at` for missing availability or erase availability quality.

### 14.4 Latest views

Interactive exploration may request a moving `latest` view. At the start of any
simulation, materialization, or study, `latest` resolves to an immutable snapshot that is
recorded in the artifact.

## 15. Ingestion, validation, and data quality

### 15.1 Provider boundary

Provider-specific network clients, credentials, rate limiting, raw downloads, and source
archives belong in dedicated adapter repositories. Persistra publishes typed canonical
record models, batch-writing interfaces, and a provider conformance suite.

Adapters should retain original vendor payloads when licensing and storage policy permit.
Persistra retains normalized source observations, hashes, source identities, and lineage;
it does not become a generic archive for arbitrary payload formats.

### 15.2 Batch lifecycle

```text
created → staged → validated → committed
                   ├─→ committed_with_quarantine
                   ├─→ rejected
                   └─→ quarantined
```

A batch commit is atomic. Partial canonical writes are not visible. Validation findings
are persisted whether the batch succeeds or fails. `committed_with_quarantine` atomically
publishes only accepted records while preserving quarantined records and their findings
under the immutable source-batch identity. A fully quarantined batch publishes no canonical
records.

Every submitted record receives a stable disposition. The original batch retains its
source hash, submitted counts, accepted counts, quarantined counts, and rejected counts.
Remediation never rewrites that batch; corrected records arrive in a linked child batch so
retries, snapshots, and coverage audits remain reproducible.

### 15.3 Required validation

Every managed ingestion commit passes validation. The normal public API has no bypass.
Validation covers at least:

- Required fields and data types
- Natural-key uniqueness
- Duplicate and conflicting observations
- Identifier and entity resolution
- Timestamp ordering and timezone correctness
- Exchange-session alignment
- OHLC consistency
- Price and quantity domain constraints
- Missing sessions and incomplete coverage
- Implausible gaps, returns, spreads, or volumes
- Corporate-action consistency
- Universe interval validity
- Revision and lineage consistency
- Source-specific contractual requirements

Default outcomes are:

- Structural errors reject the batch.
- Conflicting observations quarantine affected records or the batch.
- Statistical anomalies commit with persisted warnings unless a stricter policy applies.

Quality rules must emit stable reason codes, severity, affected keys, evidence, rule
version, and remediation status.

## 16. Canonical market and research data

### 16.1 Market bars

Bars store raw observations with instrument, venue, interval, session, source, currency,
OHLCV, optional VWAP and activity statistics, revision identity, and availability.
Adjusted OHLC series are never treated as canonical source observations.

### 16.2 Trades and quotes

Canonical trades represent executed prints with event and availability time, instrument,
venue, price, size, source, and source-specific condition metadata. Canonical quotes cover
top-of-book bid and ask price and size. Full depth is deferred.

Trades and quotes support exploratory and feature research in 3.0. A future market-replay
spec will determine how they drive simulation.

### 16.3 Corporate actions and lifecycle events

The canonical model covers:

- Ordinary and special cash dividends
- Forward and reverse splits
- Stock dividends
- Symbol and listing changes
- Mergers and acquisitions
- Spinoffs
- Delistings and liquidations
- ETF distributions
- Explicit unresolved entitlements for unsupported rights or distributions

Events preserve the domain-specific dates needed for announcement, entitlement, economic
effect, and payment. Portfolio handling must not collapse them into one generic action
date.

### 16.4 Adjustments

Adjustment views support raw, split-adjusted, total-return-adjusted, and point-in-time
adjusted policies. Cached adjusted data is a derived materialization identified by input
snapshot and policy. Historical views must not use future-known actions unless the user
explicitly requests a retrospective series unsuitable for decision simulation.

### 16.5 Fundamentals

Fundamentals distinguish issuer from tradeable instrument and preserve:

- Filing and accession identity
- Filing, acceptance, and availability timestamps
- Original and amended reports
- Fiscal period and fiscal-year semantics
- Instant and duration facts
- Unit and reporting currency
- Taxonomy and source concept
- Dimensional qualifiers such as segment and geography
- Restatements, provider corrections, and source lineage

The market database contains source facts and a versioned canonical normalization layer.
Research ratios, trailing values, growth rates, and quality measures are features in the
research database, not overwritten canonical facts.

The normalized layer should provide a curated set of commonly used statement concepts
while retaining raw taxonomy facts for complete auditability.

### 16.6 Analyst estimates

Estimate records support individual observations and consensus snapshots. They identify
the estimated measure, fiscal period or forecast horizon, publication and revision time,
unit, currency, contributor information when available, consensus statistics, and source.
Reported actuals and surprise calculations become available only when the actual is
published.

### 16.7 Macroeconomic series

Macro records preserve observation period, release time, revision vintage, unit,
frequency, seasonal-adjustment status, geography, and source. Latest-revised-only series
are exploratory and unsafe for historical simulation.

### 16.8 Universes and classifications

Universes are named definitions evaluated point in time. Inputs may include explicit
memberships, listing state, classifications, liquidity, prices, fundamentals, and custom
rules. Membership records and classification mappings are effective dated.

Eligibility evaluation returns both accepted members and rejected candidates with stable
reason codes. Survivorship-biased current constituents cannot masquerade as a historical
universe.

### 16.9 Benchmarks and risk-free data

Benchmarks are point-in-time instruments, series, or constituent definitions. Risk-free
inputs are effective-dated curves or series with explicit tenor, compounding, day-count,
and availability semantics.

### 16.10 Custom and alternative data

Persistra does not standardize particular alternative-data domains in 3.0. It provides a
custom dataset contract declaring:

- Dataset identity and version
- Entity type and identifier mapping
- Schema
- Event and availability semantics
- Frequency or irregular-event behavior
- Source and batch lineage
- Validation and revision policy
- Point-in-time query behavior
- Optional feature transformations

Unstructured assets remain external. DuckDB stores metadata, hashes, entity links,
temporal fields, licensing-safe attributes, and asset locations.

## 17. Research datasets, features, and labels

### 17.1 Dataset builder

A base research dataset combines a composite snapshot, universe, observation interval,
decision schedule, entity grain, canonical/workspace inputs, and missing-data policy. A
feature or label materialization binds that exact completed base build. A later enriched
dataset binds exact completed materializations rather than unresolved definitions. Every
stage must expose a provenance summary and eligibility audit, and no stage may depend on
the build it is currently producing.

Dataset construction must prevent accidental many-to-many joins, duplicate entity-time
rows, post-decision revisions, and label leakage. Row loss must be explained.

### 17.2 Feature definitions

A registered feature declares:

- Stable name and semantic version
- Description and units
- Input datasets and fields
- Parameters
- Entity and time grain
- Lookback and warmup
- Availability transformation
- Missing-data policy
- Output schema
- SQL or Python implementation identity
- Dependencies on other features
- Execution trust and temporal-conformance identity

Feature implementations may use SQL or Python. One dependency graph resolves both.
Definitions are lazy; materialization happens explicitly or when dataset construction
requires it, and is reusable only when its full execution and provenance identity matches.

Managed causal operators receive only point-in-time eligible inputs and are safe by
construction. A custom implementation may become safe only through the temporal
conformance contract and an execution interface that provides bounded entity-time
partitions, declared lookback overlap, and no label access. This interface also supports
bounded-memory execution without requiring the full research dataset in pandas.

Unrestricted Python/SQL, external reads, or whole-frame access remain opaque and unsafe
even when their declarations are complete; they require the explicit unsafe simulation
override. SQL UDF execution is unsupported in 3.0, and any future UDF extension starts
opaque. Sentinel tests and conformance results are evidence, not proof of arbitrary-code
causality. A label dependency is structurally forbidden from decision data and cannot be
admitted by the unsafe override.

Code hashes provide evidence, not a claim that arbitrary Python has been completely
serialized. Git state, file hashes, environment versions, and user-supplied versioning
jointly describe provenance.

### 17.3 Built-in feature families

The planned built-in surface includes:

- Prices, returns, log returns, and excess returns
- Momentum and reversal
- Volatility, downside risk, drawdown, skew, and tail behavior
- Liquidity, spread proxies, turnover, and market activity
- Volume, trade, and quote features
- Fundamental value, quality, profitability, growth, and investment
- Estimate revisions, dispersion, and surprises
- Macro and regime variables
- Cross-sectional rank, winsorization, normalization, and neutralization
- Rolling covariance, correlation, beta, and residualization

Focused feature specs determine the exact initial catalog. Persistra should prefer a
coherent, well-tested core over a large collection of opaque indicators.

### 17.4 Labels

Labels are first-class registered objects stored and queried separately from features.
Built-in candidates include:

- Forward raw and excess returns
- Forward residual returns
- Future volatility
- Future drawdown
- Maximum favorable and adverse excursion
- Triple-barrier outcomes
- Event outcomes

Label definitions declare forecast horizon, overlap, censoring, delisting treatment, and
availability. Their physical outputs live in a separate migration-owned schema, and every
row persists its closed information interval for label-aware validation. Strategy contexts
and simulation decision datasets have no label access.

### 17.5 Alpha analysis

Pre-simulation analysis includes:

- Pearson and rank information coefficients
- IC time series, confidence, and stability
- Quantile portfolios and spreads
- Coverage and missingness
- Cross-sectional monotonicity
- Signal turnover and persistence
- Decay by forecast horizon
- Autocorrelation
- Sector, industry, style, and market exposures
- Subperiod, regime, and universe slices
- Long-short spread significance

Statistical utilities should grow to include adjusted p-values, bootstrap confidence
intervals, probabilistic and deflated Sharpe ratios, and probability-of-overfitting
diagnostics. Not every advanced method must block 3.0, but the architecture must support
them as structured analysis rather than notebook-only code.

The phase-4 “quantile portfolio” surface is a label-classified diagnostic: it computes
realized-label bucket means, top-minus-bottom spreads, monotonicity, and diagnostic
turnover without holdings, execution, costs, accounting, or a backtest claim. Alpha
definitions/results bind exact analysis datasets and feature/label occurrences, declare
exploratory/validation/confirmatory intent, use dependence-aware inference, and never
become strategy inputs. Later portfolio/simulation and immutable-analysis plans may
consume their identities but cannot reinterpret or mutate them.

## 18. Temporal validation and model research

Finance-aware splitters must support:

- Expanding-window evaluation
- Rolling-window evaluation
- Purging based on overlapping label horizons
- Embargo periods
- Combinatorial purged cross-validation
- Nested parameter selection
- A final untouched holdout period

Splits operate on timestamps and information intervals rather than assuming equally
spaced row positions. With panel data, purging must consider entity and cross-sectional
relationships defined by the research design.

Raw temporal roles keep every candidate instrument at one decision together. Purging uses
the selected targets' exact closed information intervals, including endpoint equality,
and the strongest entity/group/panel dependency scope derived from exact component and
dataset lineage. Embargo uses scheduled decision steps or elapsed UTC time after actual
information completion. Nested inner candidates come only from final outer-train
membership.

A terminal holdout boundary is frozen from schedule/base-key metadata before analytical
inspection and is excluded from every development fold. One frozen managed selection may
open it for confirmatory evaluation; retries are exact and later/different or externally
reported access makes contamination append-only. This is an auditable managed-workflow
guarantee, not secrecy against a user who directly reads a local database.

Scikit-learn estimators may be used inside workflows, but Persistra owns financial
dataset construction, split semantics, provenance, and evaluation aggregation. Persistra
does not become a general machine-learning framework or model registry.

## 19. Strategy and portfolio construction

### 19.1 Decision pipeline

```text
raw and derived data
    → features
    → signal or forecast
    → portfolio constructor
    → constraints and expected costs
    → target portfolio
    → rebalance policy
    → orders
    → execution
    → accounting
```

Each stage has a versioned input/output contract. A user may bypass an optional stage only
through an explicit compatible contract.

### 19.2 Signals and forecasts

Signals declare meaning and units, such as rank, direction, probability, expected return,
or standardized score. The library must not silently treat every numeric series as an
expected return.

A forecast may include expected value, horizon, uncertainty, confidence, and supporting
diagnostics. Forecast combination is separate from portfolio optimization.

### 19.3 Portfolio constructors

Planned built-ins include:

- Equal weight
- Rank- or score-proportional allocation
- Quantile long-short allocation
- Inverse volatility
- Risk parity
- Minimum variance
- Mean-variance
- Maximum diversification
- Benchmark-relative optimization

### 19.4 Risk models

Initial risk-model support includes sample covariance, EWMA covariance, shrinkage
covariance, and user-supplied covariance or factor models. All models declare estimation
window, missing-data policy, regularization, frequency, and availability.

### 19.5 Constraints

The portfolio layer supports explicit constraints for:

- Long-only or long-short bounds
- Gross and net exposure
- Per-position size
- Sector and industry exposure
- Factor exposure
- Benchmark-relative exposure
- Turnover
- Liquidity and capacity
- Cash
- Leverage and margin
- Tracking error

Expected transaction costs may enter portfolio optimization ex ante. The optimizer cost
model is distinct from the realized execution model.

### 19.6 Optimization

CVXPY is the required 3.0 optimization implementation, delivered through the optional
`optimize` installation extra. Initial supported problems should be convex. Cardinality
and other mixed-integer constraints require explicit solver capability and are not
guaranteed in the initial surface.

Optimization status, solver, tolerances, convergence, objective components, constraint
violations, and fallback behavior are recorded. Failure is visible by default. Optional
fallbacks, such as retaining the prior portfolio or using a simpler constructor, must be
configured and recorded; silent fallback is prohibited.

### 19.7 Rebalance policies

Rebalance policy is separate from desired holdings. It controls schedule, threshold,
buffers, minimum trade size, turnover budgets, open-order interaction, and order
generation. The same target portfolio can therefore be tested under different trading
policies.

### 19.8 Multi-strategy portfolios

Child strategies produce compatible portfolio intents. A parent allocator applies
capital, risk, exposure, and diversification rules through the same portfolio-construction
contracts. Multi-strategy behavior must not require special cases in the simulator.

### 19.9 Stateful strategies

Composition is the default research model. An advanced callback interface supports
event-dependent state machines, order management, and strategies whose decisions cannot
be represented as scheduled vectorized forecasts. Stateful code receives a strictly
point-in-time context and uses the same order and accounting contracts.

## 20. Simulation fidelity

### 20.1 Fidelity levels

Persistra defines three conceptual fidelity levels:

1. **Vectorized portfolio simulation:** implemented in 3.0 for fast target-based research.
2. **Stateful order simulation:** implemented in 3.0 for explicit order, fill, settlement,
   and accounting behavior.
3. **Market replay:** future architecture for quote/trade-driven simulation; not
   implemented in 3.0.

These levels share result concepts but are not presented as equally realistic.

### 20.2 Fidelity profile

Every run records at least:

- Simulator and version
- Input market-data granularity
- Decision schedule and information cutoff
- Public-information or project-knowledge cutoff mode and availability-quality profile
- Order-submission and activation policy
- Latency model
- Bar-path or ambiguity policy
- Spread source or estimator
- Fee, slippage, and impact models
- Volume-participation policy
- Short availability and borrow model
- Margin model
- Settlement policy
- Corporate-action policy
- Stale and missing-price policy
- Rounding and precision policy
- Unsafe-data flags
- Custom-component trust and temporal-conformance status
- Random seeds

Comparisons must warn when material fidelity fields differ.

### 20.3 Vectorized simulation

The vectorized simulator operates on target holdings or weights and a decision/execution
schedule. It must still account for turnover, explicit costs, cash, corporate actions,
financing, and time alignment. It may approximate granular order behavior, but the result
must state those approximations.

Under a restricted idealized configuration, vectorized and event-driven simulations
should satisfy defined equivalence properties. Byte-identical ledgers are not required.

### 20.4 Event time and ordering

Events use timezone-aware instants plus venue-local session identity. Stable sequence keys
resolve events sharing a timestamp. The focused engine spec must define priority and
visibility for market data, actions, orders, fills, settlements, financing, margin, and
strategy callbacks.

No strategy callback may see an event that is not yet available. The engine should make
information cutoffs testable with sentinel observations.

### 20.5 Default execution timing

A decision made after a completed bar defaults to next-eligible-event execution. Same-close
execution remains available only as an explicitly optimistic research assumption and is
identified prominently in the fidelity profile.

The order model uses eligibility timestamps and latency rather than a generic “delay N
bars” as its primary temporal abstraction.

## 21. Orders and execution

### 21.1 Order types

The planned 3.0 order surface includes:

- Market
- Limit
- Stop
- Stop-limit
- Market-on-open
- Market-on-close

Limit-on-open and limit-on-close require a focused auction-data assessment and may be
deferred. Whole shares are the default for listed-equity order simulation. Vectorized
research may use fractional quantities, and an explicit broker policy may allow them.

### 21.2 Time in force

Initial policies include day, good-till-cancelled, immediate-or-cancel, and fill-or-kill.
IOC and FOK results based only on bars must carry fidelity limitations because bar data
does not reveal the full available queue.

### 21.3 Lifecycle

An order has an immutable transition history across states such as:

```text
created → submitted ────────────────→ rejected
             └─→ accepted → active ─→ filled
                              ├─→ cancelled
                              ├─→ expired
                              ├─→ replaced
                              └─→ partially filled ─→ filled
                                                    ├─→ cancelled
                                                    ├─→ expired
                                                    └─→ replaced
```

Strategies and rebalance policies may cancel or replace orders. Ownership and reason are
recorded for every transition. A replacement creates an auditable relationship rather
than erasing the prior order.

Cancellation and replacement are also valid before activation from submitted or accepted
states when the configured venue and latency policy permit them. The focused order spec
must enumerate every legal transition and rejection point; the diagram shows the primary
fill path rather than removing pre-activation controls.

Status and execution progress are distinct. An order has one current or terminal status
plus cumulative filled and remaining quantity, so a terminal `cancelled`, `expired`, or
`replaced` order may retain prior fills without inventing compound statuses. A replacement
is a linked child order for only the intended new quantity. Fill-or-kill is atomic and
never partially fills; immediate-or-cancel may partially fill and then cancels its
remainder in the same eligibility cycle.

### 21.4 Bar ambiguity

OHLC bars do not reveal intrabar path or queue order. Fill models therefore use named,
recorded ambiguity policies, including conservative, optimistic, seeded randomized,
user-supplied, or reject-ambiguous behavior. Conservative behavior is the default.

### 21.5 Liquidity and partial fills

Execution models support partial fills, volume participation limits, minimum size, and
remaining quantity. Reported volume constrains capacity but does not establish queue
priority. Every fill states whether its spread was observed or estimated.

### 21.6 Costs and impact

Commission, regulatory fees, spread, slippage, delay cost, borrow, financing, and market
impact are distinct components. Models may be composed but may not double count a cost
without an explicit configuration warning.

Impact is a scenario model, not objective truth. Parameters, calibration source, and
applicable liquidity regime must be recorded.

### 21.7 Shorting

Long-short equity research is first class. Short simulation includes:

- Quantity-limited borrow inventory
- Availability and locate outcome
- Effective-dated borrow rates
- Short-sale proceeds and collateral treatment
- Dividend and distribution obligations
- Initial and maintenance margin
- Recall or forced-close policy

The locate lifecycle is simplified and configurable; broker-specific workflows are out of
scope.

### 21.8 Margin and liquidation

Margin uses a generic initial/maintenance interface with a documented US-equity default.
Requirements are effective dated when necessary. Margin breaches create deterministic,
policy-driven forced orders whose priority and selection logic are recorded.

### 21.9 Settlement

Cash and asset settlement use effective-dated conventions so historical tests can reflect
changes in US settlement cycles. The accounting system distinguishes available,
receivable, payable, settled, and unsettled balances. Ordinary margin-account workflows
may configure permitted use of unsettled proceeds without deleting the ledger distinction.

## 22. Accounting

### 22.1 Journal as source of truth

An immutable double-entry journal is the authoritative accounting record. Cash balances,
positions, lots, realized P&L, accrued costs, settlement state, exposures, and periodic
snapshots are projections from journaled events.

The journal must balance after every atomic transaction. Derived projections must be
rebuildable and reconcilable through a diagnostic command.

### 22.2 Numerical representation

The planned hybrid model is:

- Pandas and NumPy research calculations use `float64`.
- Stored monetary journal amounts use fixed-precision DuckDB decimal types.
- Domain money values use a fixed-precision representation.
- Prices and quantities retain declared precision.
- Conversion occurs explicitly at execution and accounting boundaries.

Focused design must define precision, rounding, overflow, tolerance, and performance
behavior. Venue, instrument, currency, and broker constraints jointly resolve the
execution precision policy recorded on an order.

### 22.3 Accounts and entries

The chart of accounts should represent at least:

- Settled and unsettled cash
- Securities inventory by lot
- Short inventory and collateral
- Receivables and payables
- Fees, spread, slippage, and impact costs
- Borrow and financing accruals
- Dividend income and short dividend expense
- Realized gains and losses
- Capital contributions and withdrawals
- Corporate-action entitlements

The exact accounting treatment requires a dedicated ledger specification and hand-worked
examples.

### 22.4 Lots and positions

Inventory lots are required even though tax reporting is excluded. Lots support realized
P&L, corporate actions, settlement, borrow attribution, and auditability. Tax-lot election
and jurisdiction-specific tax logic remain out of scope.

### 22.5 Valuation

Marking policy identifies source, observation time, staleness, currency, and fallback.
Missing prices do not silently become zero or reuse an unlimited stale mark. Equity and
exposure outputs retain valuation-quality diagnostics.

A halted instrument is distinguished from ordinary missing data only when trading-status
observations have been ingested; otherwise the missing-data policy applies. Canonical
schemas must leave room for trading-status observations without requiring them in 3.0.

### 22.6 Cash flows and accruals

Initial capital, later deposits, and withdrawals are journaled. Positive cash interest,
negative cash financing, borrow costs, and other accruals use explicit effective-dated
models. This supports both time-weighted and money-weighted performance.

### 22.7 Materialized snapshots

Periodic accounting snapshots improve query and resume performance. They are caches, not
authority. Rebuilding from the journal must reproduce them within declared precision.

## 23. Experiments and validation studies

### 23.1 Hierarchy

- A **study** represents a research question and common design.
- A **trial** represents one parameter configuration.
- A **fold** represents one temporal training, validation, and test partition.
- A **scenario** represents one set of data or model perturbations.
- A **run** represents one resolved execution design for a trial, fold, and scenario; an
  **attempt** is one concrete execution or retry of that run's execution identity.

This hierarchy must support simple single runs without ceremony and complex nested studies
without flattening all context into tags.

### 23.2 Search

Grid, random, user-defined, and Bayesian search are required 3.0 capabilities. Bayesian
search is delivered through the optional `search` installation extra; optional describes
installation, not release deferral. Parameter domains, types, transforms, and conditional
relationships are declared. Distributed scheduling is out of scope.

Failed trials are auditable outcomes. They do not necessarily abort the study; a study may
set failure thresholds and stop policies.

### 23.3 Run identity and reuse

Persistra separates four identities:

- **Design identity** hashes the resolved research question: inputs, snapshots, split,
  strategy, portfolio, simulation, scenario, and declared component versions.
- **Execution identity** adds all material code hashes, dependency and solver versions,
  runtime configuration, platform constraints that affect behavior, random-seed plan, and
  fidelity policy.
- **Attempt identity** uniquely identifies one execution or retry of an execution identity.
- **Artifact identity** content-addresses the immutable outputs and manifest produced by an
  attempt.

Exact reuse is the default and requires a matching execution identity plus a complete,
verified artifact. A deliberately relaxed compatibility-reuse mode may match design
identity under a versioned compatibility policy, but it is explicit, records every ignored
difference, emits a persistent warning, and preserves the reused artifact's original
execution identity. There is no invisible cache substitution, and an environment
difference can never masquerade as exact reuse.

### 23.4 Code provenance

Git commit, dirty state, relevant file hashes, notebook identity, package version, Python
version, dependency and solver versions, platform, and user-supplied component versions are
recorded when available. Dirty worktrees are allowed and clearly identified. A material
dependency, external input, or nondeterministic behavior whose identity cannot be resolved
makes exact reuse and deterministic replay ineligible.

### 23.5 Local parallel execution

Workers open market data read-only under shared database leases and write isolated
temporary DuckDB result files. The coordinator verifies schema, design, execution, attempt,
and artifact identities, completeness, and checksums before transactional merge.
Interrupted studies resume by scheduling missing or eligible failed execution identities as
new attempts.

Progress uses a generic event or callback interface with a default terminal renderer. The
experiment core does not depend directly on a particular progress-bar library.

### 23.6 Scenario and stress testing

Scenarios may perturb:

- Returns and price paths
- Spread, impact, latency, and liquidity
- Borrow availability and rates
- Financing and cash rates
- Corporate actions or delisting assumptions
- Universe and missing-data conditions
- Risk-model estimates
- Portfolio constraints
- Execution outages or rejected orders

Historical stress windows and hypothetical shocks share structured scenario definitions.
Scenario outputs aggregate through the normal result and analysis interfaces.

### 23.7 Monte Carlo and bootstrap

Planned methods include time-series block bootstrap, cross-sectional resampling where
valid, trade resampling, parameter uncertainty, and seeded simulation of model inputs.
Every method must document which dependence structure it preserves or destroys.

## 24. Results and artifacts

### 24.1 Completed-run immutability

A completed run is immutable. A retry creates another attempt. User notes, labels, and tags
remain mutable in separate annotation tables and never alter the run identity.

Metrics, attribution, comparisons, diagnostics, and reports computed after completion do
not append to or replace run outputs. Each becomes an immutable analysis artifact with its
own identity, input run or analysis identities, resolved configuration, implementation and
dependency identity, attempt history, warnings, and content checksum. Recalculation creates
a new analysis artifact. User annotations are the only mutable run-associated records.

Deletion is explicit, checks references, and requires confirmation. Archival is preferred.

### 24.2 Structured result tables

The research database stores normalized, identity-keyed tables for:

- Design, execution, attempt, and artifact identity, configuration, provenance, safety,
  and fidelity
- Signals and forecasts
- Target portfolios and rebalance decisions
- Orders and every state transition
- Fills and cost components
- Journal entries and accounting snapshots
- Holdings, lots, cash, exposures, and margin
- Settlement state
- Corporate-action processing
- Equity and return series
- Diagnostics and quality findings
- Fold, trial, study, and scenario relationships
- Analysis-artifact identities and immutable metric, attribution, comparison, diagnostic,
  and report outputs

Exact schemas belong in the result-storage specification.

### 24.3 Diagnostic outputs

User-defined diagnostics use registered table schemas. The system should not rely on one
untyped name/value table for arbitrary information. Scalar, time-series, cross-sectional,
event, and tabular diagnostics may use separate contracts.

### 24.4 Logs

Important lifecycle events, warnings, and failures are structured in DuckDB. Verbose logs
may live as external files referenced by an artifact manifest. Secrets and external
credentials must not appear in either surface.

### 24.5 Portable export

A portable run export is a standalone DuckDB file containing the selected immutable run,
selected analysis artifacts, required structured dependencies, annotations as requested,
Persistra schema version, and manifest. It contains no unresolved local file references.
An optional report directory contains HTML and static assets.

Portability means reopening within the published Persistra 3.x and DuckDB compatibility
matrix, not arbitrary DuckDB versions. The manifest records the Persistra version and
schema, DuckDB library and storage versions, required extensions, source and artifact
checksums, and the supported reader range. Compatibility tests cover the current export
format and every prior format still supported. An incompatible native file is upgraded by
a verified copy migration rather than modified in place.

CSV and a versioned Parquet manifest bundle may be offered as explicit interoperability and
long-term recovery exports. Neither is a native Persistra storage or run-artifact contract
in 3.0.

## 25. Metrics, attribution, and comparison

### 25.1 Structured metrics

A metric result contains:

- Stable metric identity and version
- Estimate
- Units
- Observation count and interval
- Annualization or frequency policy
- Required benchmark or risk-free input
- Warnings
- Availability or failure reason
- Optional confidence interval and method

Convenience scalar access is permitted. Invalid metrics produce structured unavailable
results; dataframe summaries may render the estimate as `NaN` while preserving the reason.
Stored metric results always belong to an immutable analysis artifact; a metric version or
dependency change creates a new artifact rather than mutating the completed run or an older
analysis.

### 25.2 Metric families

Planned families include:

- Time-weighted and money-weighted returns
- Annualized return and volatility
- Sharpe, Sortino, Calmar, and related ratios
- Drawdown depth, duration, and recovery
- Tail loss, VaR, expected shortfall, skew, and kurtosis
- Hit rate, payoff, and distribution summaries
- Benchmark alpha, beta, active return, tracking error, and information ratio
- Gross, net, sector, industry, factor, and benchmark-relative exposure
- Turnover, holding period, and concentration
- Fees, spread, slippage, impact, borrow, and financing costs
- Capacity and participation estimates
- Fold, trial, scenario, and regime stability

Annualization is metric specific. Actual elapsed time is the default performance basis;
frequency-based statistical estimators declare their convention. Effective-dated
benchmarks and risk-free curves are aligned point in time.

### 25.3 Attribution

Initial attribution includes:

- Holdings and transaction contribution
- Sector and industry contribution
- Factor exposure and contribution
- Strategy-component contribution
- Long, short, gross, and net decomposition
- Cost attribution
- Benchmark-relative contribution

Exact institutional Brinson variants may follow after the foundational attribution model.

### 25.4 Execution analysis

When required observations exist, analysis covers:

- Arrival-price slippage
- Spread cost
- Delay cost
- Market-impact estimate
- Participation
- Fill rate
- Cancellation, expiration, and rejection rates
- Implementation shortfall

Unavailable observed quotes or arrival prices must not be replaced with unmarked estimates.

### 25.5 Comparison

Run comparison checks data snapshots, universes, date ranges, folds, benchmarks, cash-flow
policies, simulation levels, and fidelity profiles. Differences are classified as
compatible, comparable with warnings, or incompatible. A chart must not make invalid
comparisons appear authoritative.

## 26. Visualization, reports, and dashboard

### 26.1 Plotting

Plotly is the sole supported plotting backend in 3.0. Plot functions:

- Accept result or structured analysis objects
- Return a figure without displaying or writing it
- Contain no independent financial calculations
- Share a configurable theme system
- Indicate unsafe data and important fidelity assumptions where relevant
- Handle empty or unavailable inputs with clear messages

Planned figures cover performance, drawdowns, distributions, rolling metrics, exposures,
holdings, turnover, costs, capacity, orders, fills, attribution, alpha diagnostics,
cross-validation, scenarios, and provenance.

### 26.2 Reports

The guaranteed report format is self-contained interactive HTML. A directory-bundle mode
may share Plotly assets across large reports. Static PNG, SVG, and PDF export is optional
because it depends on additional browser and rendering components.

Report sections are reusable public builders. A standard run report includes:

- Executive summary
- Data snapshot and safety status
- Strategy, portfolio, and fidelity configuration
- Performance and risk
- Drawdowns and stress periods
- Holdings, exposures, and turnover
- Execution and costs
- Attribution
- Diagnostics and warnings
- Provenance and reproduction details

Every persisted report records and displays the exact run and analysis artifact identities
used for each section. Regenerating a report after an analysis or dependency change creates
a new report artifact.

### 26.3 Dashboard

The optional `dashboard` installation extra provides a required 3.0 local Streamlit
research explorer. Optional describes installation from the base environment, not release
status. It is late in the roadmap and must be prototyped before its framework choice
becomes permanent.

The dashboard opens research databases read-only under a shared lease. Because DuckDB does
not allow read-only attachment while another process is writing, running the dashboard
against a research database with an active writer is unsupported; a verified backup or
portable run export serves that workflow instead.

The 3.0 dashboard is read-only and includes:

- Run overview
- Performance and drawdowns
- Positions and exposures
- Orders and execution
- Attribution
- Diagnostics
- Study and trial comparison
- Canonical data, feature, and provenance inspection

It does not ingest data, launch runs, mutate results, manage users, or promise hosted
deployment. Public hosting may be documented only as an unsupported demonstration recipe
using redistributable sample data.

## 27. Public API principles

- The top-level package exports only `Project`, a small set of foundational configuration
  types, exceptions, and version metadata.
- Capabilities live in clear namespaces such as `persistra.research`,
  `persistra.portfolio`, and `persistra.simulation`.
- APIs are synchronous in 3.0.
- Configuration values are immutable after validation.
- Methods avoid hidden global state and implicit default database connections.
- Every operation that changes managed state requires an explicit project or repository
  service.
- Public dataframes use stable, versioned schemas and explicit columns.
- Result queries may be lazy internally but materialize to pandas explicitly.
- Errors use typed exceptions and stable reason codes where programmatic handling matters.
- Optimistic assumptions require explicit selection; conservative behavior is the default.
- API convenience methods may compose lower layers but must not create a second behavior
  path with different semantics.

Illustrative APIs in this umbrella spec are nonbinding. Focused specs own exact naming and
signatures.

## 28. CLI

The proposed CLI surface is operational:

- `persistra init`
- `persistra db migrate`
- `persistra db inspect`
- `persistra db backup`
- `persistra db snapshot-copy`
- `persistra data validate`
- `persistra data quarantine`
- `persistra data snapshot`
- `persistra runs list`
- `persistra runs show`
- `persistra runs export`
- `persistra runs delete`
- `persistra report`
- `persistra dashboard`
- `persistra doctor`

`persistra db backup` performs the verified backup that migration and external
synchronization workflows rely on. `persistra db snapshot-copy` creates and verifies the
physical immutable market snapshot used when studies must coexist with ingestion.
`persistra data quarantine` lists and inspects quarantined records; remediation submits a
linked child batch rather than changing the original disposition. `persistra runs delete`
is confirmation-gated, checks references, and prefers archival, matching the
results-and-artifacts rules.

The CLI does not initially execute arbitrary strategy files. Python scripts and notebooks
invoke the public API directly, avoiding a parallel YAML or TOML strategy language.

## 29. Extension contracts

### 29.1 Provider adapters

External providers implement canonical staging records and batch submission. A published
conformance suite validates schema, temporal semantics, source identity, error behavior,
and batch atomicity.

### 29.2 Custom datasets

Custom datasets declare entity mapping, schema, timing, revisions, validation, and query
behavior. They participate in snapshots, provenance, feature dependencies, and unsafe-data
checks. Unrestricted custom readers and transformations remain unsafe until they satisfy
the temporal conformance and bounded-execution contract.

### 29.3 Research components

Users may register features, labels, signal transforms, forecast models, risk models,
portfolio constructors, constraints, cost models, rebalance policies, metrics, and report
sections through typed contracts. Registration must not require editing global registries
at import time. Registration alone never grants temporal-safety status.

### 29.4 Execution and accounting policies

Custom execution models operate through explicit order, market observation, and fill
contracts. Custom policies may not mutate journal or portfolio state directly; they emit
validated domain decisions consumed by the owning subsystem.

## 30. Dependencies and packaging

### 30.1 Platform

- Python 3.12 or newer — a deliberate floor bump from v2’s 3.11, since a greenfield
  release without a compatibility constraint adopts a modern baseline
- Linux as the sole supported and CI-tested 3.0 platform
- macOS as explicitly best-effort and not release-gating
- Windows unsupported initially
- MIT license retained

### 30.2 Runtime extras

The proposed dependency groups are:

- **Base:** DuckDB, pandas, NumPy, exchange calendars, configuration, and structured
  logging
- **Research:** SciPy, scikit-learn, and statsmodels
- **Search:** Bayesian-search dependencies
- **Optimize:** CVXPY and selected open-source solvers
- **Viz:** Plotly and Jinja
- **Report export:** optional static-rendering dependencies
- **Dashboard:** Streamlit and visualization dependencies
- **All:** every supported runtime extra
- **Dev:** pytest, Hypothesis, Ruff, Pyright, coverage, and benchmark tooling
- **Docs:** MkDocs Material and notebook tooling

Capability status is independent from installation status:

| Status | 3.0 meaning | Capabilities |
| --- | --- | --- |
| Required core | Installed by default and release-gating | Project, data, research-dataset, basic portfolio, accounting, simulation, result, and export foundations |
| Required extra | Implemented, documented, and tested before release; dependencies install on demand | Advanced research, Bayesian search, convex optimization, Plotly and HTML reporting, and the read-only dashboard |
| Optional 3.0 | May ship but does not gate release | Static PNG, SVG, and PDF report export and additional solver integrations |
| Deferred | No 3.0 implementation claim | Market replay, hosted services, and other capabilities named as non-goals |

Exact packages and lower bounds require dependency review during each focused spec.
Optional namespaces must remain import safe and raise actionable errors only when an
unavailable capability is invoked.

Hatchling remains the proposed build backend and uv remains the environment and workflow
manager unless implementation identifies a concrete limitation. Claimed lower dependency
bounds should be tested.

## 31. Logging, errors, and diagnostics

Structured logging must use stable event names, levels, run identifiers, component
context, and machine-readable fields. Console rendering is a presentation choice.

Expected unavailable states use result or reason types rather than exceptions where the
condition is part of normal research, such as an undefined metric. Invalid configuration,
schema corruption, temporal-safety violations, and failed invariants use typed exceptions.

Warnings are persisted with the artifact that caused them. A warning emitted during a
backtest must remain visible after the process ends and after the result is exported.

## 32. Testing and quality strategy

### 32.1 Test layers

- Unit tests for pure transformations and domain rules
- Contract tests for public APIs and provider adapters
- Migration tests across supported schema versions
- Integration tests for complete research and simulation workflows
- Hand-calculated golden accounting and corporate-action scenarios
- Property tests for numerical, temporal, and accounting invariants
- Stateful generated tests for order and portfolio lifecycles
- Differential tests between compatible vectorized and event configurations
- Determinism and reproducibility tests
- Explicit no-lookahead sentinel tests
- Failure, interruption, resume, and transactional recovery tests
- Performance and memory benchmarks
- Documentation snippet and notebook tests

### 32.2 Critical invariants

At minimum, tests must enforce:

- Journal debits equal credits for every atomic transaction.
- Cash and position projections reconcile to the journal.
- Valuation identity holds within declared precision.
- No observation later than the public-information cutoff, or the project-knowledge cutoff
  when enabled, reaches strategy code.
- A correction with unknown source publication time never appears before its ingestion
  bound and remains unsafe.
- Label dependencies never reach simulation decision data, including through SQL,
  workspaces, or custom code.
- Opaque derived data cannot lose its unsafe classification through materialization.
- A snapshot query is stable after later ingestion.
- Amended facts and macro vintages appear only when available.
- Universe eligibility and identifier mappings respect effective intervals.
- Order state transitions follow the state machine.
- A partially filled order may terminate as filled, cancelled, expired, or replaced while
  retaining its cumulative fill history.
- Filled quantity never exceeds eligible remaining quantity.
- Settlement and margin balances remain internally consistent.
- Corporate actions conserve economic value according to the configured policy.
- Repeated seeded runs are deterministic.
- Failed transactions and incomplete batch commits do not become visible canonical data.
- A `committed_with_quarantine` batch exposes all accepted records atomically, no
  quarantined records, and stable per-record dispositions.
- Exact reuse never crosses execution identities.
- Recomputed analysis never mutates a completed run or prior analysis artifact.

### 32.3 Property and stateful testing

Hypothesis is a development dependency. Generated sequences should combine cash flows,
orders, partial fills, cancellations, replacements, splits, dividends, delistings,
settlements, borrow changes, interest, and margin events. Invariants are checked after each
step, and minimized counterexamples become permanent regression tests where useful.

### 32.4 Coverage and checks

The eventual v3 target is at least 90% branch coverage, introduced gradually. Critical
accounting, temporal-selection, and order-state modules should approach complete meaningful
branch coverage.

The verification gate remains lint, static types, and tests, with documentation checks
when docs or docstrings change. Performance results are collected in ordinary CI, while
hard regression thresholds run only in a controlled benchmark environment.

Lightweight documentation snippets execute on every relevant change. Full notebooks may
run in scheduled or manual CI.

### 32.5 Performance target

The release-gating memory benchmark is a versioned, deterministic single-run workload:

- Approximately 5,000 instruments over 20 years of US daily sessions, including
  point-in-time membership churn and deterministic missing-data cases
- Ten representative numeric features spanning returns, momentum, volatility, liquidity,
  and cross-sectional transforms
- Monthly point-in-time universe selection and equal-weight long-only rebalancing
- One vectorized simulation with explicit costs, journal accounting, and persisted
  normalized results
- A cold operating-system and DuckDB cache, no swap, fixed thread count, and no unrelated
  worker processes
- Linux peak resident set size measured by a documented command such as
  `/usr/bin/time -v`, with the exact hardware, DuckDB settings, fixture identity, command,
  query plans, runtime, database size, and measurement method recorded

Peak resident set size must not exceed 24 GiB, leaving operating headroom on a 32 GB
workstation. The benchmark specification owns exact fixture cardinalities and feature
definitions so results remain comparable across releases. Parallel-study scaling,
event-simulation throughput, and wall-clock regression thresholds are tracked separately
and do not alter this memory acceptance workload without an umbrella-spec revision.

## 33. Documentation and examples

Documentation should be organized around:

- Getting started
- Concepts and reliability guarantees
- Data management and temporal semantics
- Research datasets, features, labels, and alpha analysis
- Portfolio construction and risk
- Vectorized and event simulation
- Experiments and validation
- Results, metrics, attribution, and reporting
- Recipes
- Architecture and extension guides
- API reference

Every realism-sensitive feature must include an “Assumptions and limitations” section.
Execution models must state required data, modeled behavior, ambiguity, and unsupported
market mechanics.

The repository should include:

- One deeply documented end-to-end cross-sectional equity strategy
- Small recipes for isolated capabilities
- Deterministic textual source fixtures
- A generated sample DuckDB database created from those fixtures
- Notebooks used for explanation, not authoritative reusable implementation

Large opaque binary sample databases should not be committed when they can be generated
deterministically.

## 34. Implementation plan

### 34.1 Planning gate

This umbrella specification must be reviewed and accepted before implementation. Each
major phase begins with a focused specification describing exact API, SQL schema,
algorithms, failure behavior, edge cases, migration effect, and acceptance tests.

### 34.2 Clean-slate checkpoint

The first implementation checkpoint must:

- Preserve Git history, repository governance, and the MIT license
- Delete v2 application code
- Delete v2 tests
- Delete v2 documentation other than accepted v3 planning material
- Delete v2 examples and Parquet sample data
- Replace build and CI configuration where needed
- Establish a minimal installable v3 package skeleton
- Add smoke tests and passing quality gates

Deletion and the minimal skeleton belong in one coherent working checkpoint. A
deletion-only commit that intentionally leaves the repository broken is not desirable.

### 34.3 Delivery phases

Delivery is vertical after the foundation. Each phase begins with its focused specification
and ends with a public workflow, explicit exit tests, and updated documentation rather than
only a completed lower layer.

1. **Domain and project foundation**
   - Project configuration, workspace, domain identifiers, time, money, and base events
   - DuckDB connection ownership, shared/exclusive leases, and migration framework
   - CLI skeleton, logging, typed errors, and capability-boundary scaffolding
   - Exit: an installable package can create, open, inspect, lease, migrate, and close an
     empty project through tested public APIs

2. **Flagship daily-bar vertical slice**
   - Minimal catalog, validation, revision, partial-quarantine, and snapshot contracts
   - Instruments, listings, calendars, daily bars, and a point-in-time universe
   - Managed return and momentum features, one signal, equal-weight long-only construction,
     and monthly rebalancing
   - Foundational double-entry cash and position accounting, explicit costs, and supported
     split and cash-dividend handling
   - Vectorized simulation, normalized persisted results, core performance metrics, one
     Plotly figure, and a basic self-contained HTML report
   - Exit: the evolving flagship strategy runs from deterministic source fixtures to a
     pinned report using only public APIs and no notebook-only logic

3. **Data and temporal hardening**
   - Full source, batch, revision-specific availability, quality, quarantine, remediation,
     market-snapshot, and composite-snapshot semantics
   - Provider conformance suite and dual public/project-knowledge as-of queries
   - Intraday bars, trades, quotes, actions, lifecycle events, and adjustment views
   - Fundamentals, estimates, macro, benchmarks, risk-free series, and custom datasets
   - Exit: later ingestion cannot change pinned queries, unknown correction availability is
     rejected by safe simulation, and every canonical family passes contract fixtures

4. **Research datasets and robust alpha analysis**
   - Point-in-time dataset builder, eligibility audit, features, labels, and materialization
   - Managed causal execution, custom-code conformance, SQL/workspace lineage, and bounded
     pandas partitions
   - Alpha diagnostics plus expanding, rolling, purged, embargoed, combinatorial, nested,
     and final-holdout splitters
   - Exit: label and sentinel leakage tests cover managed, custom, SQL, and workspace paths
     while a documented alpha workflow runs within bounded memory

5. **Accounting and portfolio hardening**
   - Full journal, precision, lots, cash flows, valuation, settlement, financing, borrow,
     margin, corporate actions, projection rebuild, and reconciliation
   - Signals, forecasts, allocation and rebalance policies, risk models, constraints,
     expected costs, CVXPY optimization, and multi-strategy intent
   - Exit: hand-worked and generated long-only and long-short scenarios reconcile through
     the same contracts used by the flagship vectorized workflow

6. **Event-simulation vertical slice**
   - Event clock, visibility, order lifecycle, partial fills, cancellation and replacement,
     bar ambiguity, latency, costs, shorting, forced liquidation, and recovery
   - Vectorized/event equivalence profiles under the restricted common configuration
   - Exit: a documented strategy runs through both simulators with explainable fidelity
     differences and complete order and journal histories

7. **Studies and robust validation**
   - Design, execution, attempt, and artifact identities with exact and compatible reuse
   - Study/trial/fold/scenario registry; grid, random, custom, and Bayesian search
   - Shared market leases, isolated worker databases, transactional merge, and resume
   - Scenario, stress, Monte Carlo, and bootstrap tools
   - Exit: interruption and scheduling-order tests reproduce the same execution identities
     and verified outputs without concurrent database writes

8. **Results, immutable analysis, and portability**
   - Complete result repositories, annotations, immutable analysis artifacts, and attempts
   - Metrics, benchmark analysis, attribution, execution and capacity analysis, statistical
     uncertainty, and compatibility-aware comparison
   - Self-contained DuckDB exports, compatibility matrix, and verified copy migrations
   - Exit: a completed run remains unchanged while multiple analysis versions and reports
     are created, exported, reopened, and traced independently

9. **Presentation and optional application surfaces**
   - Complete Plotly figure families, reusable report sections, and run/study HTML reports
   - Streamlit prototype followed by the required-extra read-only dashboard
   - Optional static export when the rendering dependency review succeeds
   - Exit: every page and report section uses public result and analysis APIs and displays
     pinned provenance, safety, and fidelity information

10. **Release hardening**
    - Deepen the flagship example and complete assumptions-focused documentation
    - Migration, database, export, dependency-extra, and Linux platform verification
    - Run the versioned 24 GiB memory benchmark and controlled performance suites
    - Complete the release acceptance review and human-triggered release preparation

### 34.4 Checkpoint discipline

Each implementation checkpoint must be a coherent working unit with the project’s
verification gate passing. Multi-commit efforts use a feature branch and preserve atomic
commits. No version bump, release commit, tag, publish, push, or merge occurs without the
explicit human action required by repository policy.

The eventual 3.0.0 version bump and release are separate, human-triggered operations after
all acceptance criteria are met.

## 35. Required focused specifications

At minimum, implementation should be preceded by focused plans for:

1. [Domain identity, time, money, and event types](v3/01-domain-identity-time-money-events.md)
2. [Project configuration, database attachment, leases, verified copies, and migrations](v3/02-project-databases-leases-copies-migrations.md)
3. [Catalog, ingestion, per-record dispositions, partial quarantine, remediation, and
   snapshots](v3/03-catalog-ingestion-quarantine-snapshots.md)
4. [Instrument, listing, identifier, calendar, and universe schemas](v3/04-reference-identifiers-calendars-universes.md)
5. [Bars, trades, quotes, corporate actions, and adjustments](v3/05-market-bars-trades-quotes-actions-adjustments.md)
6. [Fundamentals, estimates, macro, benchmarks, and risk-free data](v3/06-fundamentals-estimates-macro-benchmarks-rates.md)
7. [Research dataset builder, dual-cutoff temporal joins, SQL/workspace lineage, and
   safety](v3/07-research-datasets-temporal-joins-sql-workspaces-safety.md)
8. [Feature, label, bounded execution, temporal conformance, materialization, and
   provenance](v3/08-features-labels-bounded-execution-temporal-conformance-provenance.md)
9. [Alpha diagnostics and finance-aware validation splitters](v3/09-alpha-diagnostics-finance-aware-validation.md)
10. Signals, forecasts, risk models, constraints, and optimization
11. Journal accounting, valuation, settlement, margin, borrow, and corporate actions
12. Vectorized simulator
13. Event clock, order status and fill progress, bar execution, costs, and fidelity profile
14. Experiment identity, exact and compatible reuse, local parallel execution, search,
    resume, and scenarios
15. Result schemas, immutable analysis artifacts, metrics, attribution, comparison, export,
    and DuckDB compatibility
16. Plotly visualization and HTML report architecture
17. Streamlit dashboard prototype and its optional-extra boundary within the one package
18. Testing fixtures, conformance suites, property tests, and the versioned 24 GiB benchmark
    plan

Each focused specification may revise a local recommendation here when evidence warrants
it, but must call out the conflict and update this umbrella document if the project-level
direction changes.

## 36. Principal risks and mitigations

### 36.1 Scope risk

The planned surface is large for one developer. Mitigation is strict phase ordering, a
usable daily-bar vertical slice as the first feature milestone, focused specs with exit
tests, and refusal to broaden asset classes or production deployment before the
equity-research foundation is reliable.

### 36.2 False realism

A sophisticated order model can still be wrong when fed coarse data. Mitigation is the
fidelity profile, conservative defaults, ambiguity policies, required limitations, and
comparison warnings.

### 36.3 Temporal complexity

Bitemporal facts and revisions are easy to query incorrectly. Mitigation is
revision-specific availability, separate public and project-knowledge cutoffs,
ingestion-bounded unknown corrections, canonical as-of views, a point-in-time dataset
builder, no-lookahead sentinels, and unsafe-data tainting across Python, SQL, and workspace
materializations.

### 36.4 Accounting complexity

Settlement, shorts, margin, actions, and lots create interacting state. Mitigation is an
immutable double-entry journal, hand-calculated scenarios, property-based state machines,
and rebuildable projections before engine integration.

### 36.5 Database concurrency

Local parameter searches and ingestion can conflict with DuckDB’s write model. Mitigation
is one writer, application-level shared/exclusive leases, optional verified physical
snapshot copies, read-only workers, isolated temporary databases, and transactional
coordinator merges.

### 36.6 Optional-dependency fragmentation

Research, Bayesian search, optimization, visualization, static export, and dashboard
extras may create many combinations. Mitigation is the explicit core/required-extra/
optional/deferred capability matrix, import-safe boundaries, actionable errors, and an
`all` extra used by documentation and end-to-end CI.

### 36.7 Over-abstraction

Designing generic contracts before concrete implementations can recreate cumbersome APIs.
Mitigation is one database backend, one dataframe API, one implemented market scope, and
focused specs driven by complete research workflows.

### 36.8 Reproducibility overclaim

Git hashes and dependency lists do not capture every external or runtime effect. Mitigation
is separate design, execution, attempt, artifact, and analysis identities; exact reuse by
default; deterministic defaults; immutable snapshots; and persistent warnings for relaxed
compatibility reuse and unsafe components.

## 37. Draft 3.0 acceptance criteria

The 3.0 release is eligible for final review when:

- The v2 implementation and its native artifacts are absent from the v3 codebase.
- The base package and every required extra install on supported Python versions and Linux
  through uv and pip; macOS remains explicitly non-gating best effort.
- A provider adapter can ingest, validate, revise, partially or wholly quarantine,
  remediate through linked child batches, and snapshot canonical data through a published
  contract with stable per-record dispositions.
- US equity and ETF instruments, bars, corporate actions, fundamentals, estimates, macro,
  trades, quotes, universes, benchmarks, and risk-free data have documented canonical
  schemas, revision-specific availability, and public-information and project-knowledge
  point-in-time queries.
- Shared/exclusive leases prevent market or research writers from overlapping incompatible
  readers, and verified physical snapshot copies support explicitly concurrent ingestion.
- Unsafe temporal inputs, opaque custom code, and unresolved SQL or workspace lineage are
  rejected by simulation by default and visibly tainted when overridden.
- Features and labels are registered, separated, materialized, traced to immutable
  snapshots, and governed by bounded execution and temporal-conformance contracts; label
  dependencies cannot enter decision data under any override.
- Label-classified alpha diagnostics and finance-aware validation operate on exact
  point-in-time research datasets with dependence-aware inference, closed-interval
  entity/group/panel purging, embargo, nested selection, and auditable final-holdout use/
  contamination.
- Portfolio construction supports long-only and long-short workflows, risk models,
  constraints, expected costs, and documented optimization failure behavior through the
  required `optimize` extra.
- The double-entry journal reconciles across fills, cash flows, settlement, financing,
  borrow, margin, and supported corporate actions.
- Vectorized and event-driven simulators satisfy their defined timing, accounting,
  determinism, and fidelity contracts.
- Order simulation supports the planned lifecycle, order types, partial fills followed by
  fill, cancellation, expiration, or replacement, IOC and FOK semantics, latency, costs,
  ambiguity policies, shorting, and forced liquidation.
- Studies support design, execution, attempt, and artifact identities; exact reuse by
  default; warned compatibility reuse; trials, folds, scenarios, resume, leased local
  parallel execution, and structured failures.
- Grid, random, custom, and Bayesian search are documented and tested, with Bayesian search
  delivered through the required `search` extra.
- Walk-forward, purged, embargoed, combinatorial, and nested validation workflows are
  documented and tested.
- Scenario, stress, Monte Carlo, and bootstrap analyses are available through structured
  result contracts.
- A completed run remains immutable while versioned metrics, attribution, comparisons,
  diagnostics, and reports are added as independent immutable analysis artifacts.
- Metrics, attribution, execution analysis, capacity analysis, and comparisons report
  requirements, warnings, unavailable reasons, and exact analysis identity.
- A completed run and selected analyses export to a self-contained DuckDB artifact that
  records its engine and storage compatibility and reopens across the supported current and
  prior export-format matrix with provenance, safety, and fidelity intact.
- Plotly figures and self-contained HTML reports cover both performance and diagnostic
  inspection.
- The required `dashboard` extra reads completed artifacts through public APIs without
  mutating them.
- One flagship strategy demonstrates the entire workflow from data snapshot through
  report without private or notebook-only implementation logic.
- Critical temporal, accounting, order-state, and ingestion invariants have property,
  scenario, and integration coverage.
- The versioned 5,000-instrument, 20-year daily-bar workload completes at no more than
  24 GiB peak resident set size under its documented cold-cache Linux protocol.
- Documentation states assumptions and limitations for every realism-sensitive component.
- Lint, static types, tests, docs checks, schema checks, and the agreed coverage gate pass.
- The human release owner explicitly approves the version bump and release operation.

## 38. Summary of committed direction

Persistra v3 will be a greenfield, local-first equity and ETF research workbench built on
DuckDB and pandas. It will unify point-in-time data, features, labels, alpha analysis,
portfolio construction, vectorized research, auditable event simulation, experiments,
accounting, diagnostics, visualization, and reporting without collapsing them into one
engine or storage class.

Its credibility will come from revision-specific public and project-knowledge semantics,
immutable snapshots, append-only revisions and analyses, mandatory validation, explicit
custom-code trust, a double-entry journal, complete order lifecycles, conservative defaults,
fidelity profiles, exact execution identity, structured unavailable states, and tests
centered on financial invariants.

The project will remain intentionally local and personal in operation: one package, one
database engine, one public dataframe type, no live trading, no backend abstraction, and
no hosted platform. Shared/exclusive leases make DuckDB's process boundary explicit, and
vertical delivery keeps those guarantees connected to usable workflows. The clean break is
used to establish strong boundaries rather than to recreate v2 under new names.
