# Focused specification 17: read-only Streamlit dashboard prototype

**Status:** Implementation-ready prototype specification  
**Umbrella:** [`v3-spec.md`](v3-spec.md)\
**Primary package:** `persistra.dashboard`  
**Required before:** focused specification 18  
**Last reviewed:** 2026-07-16

## 1. Purpose and relationship to the umbrella specification

This specification defines the required Persistra v3 local Streamlit research explorer and
the evidence required before Streamlit becomes the permanent dashboard framework. It fixes the
read-only boundary, startup/source modes, lease behavior, public API use, pages, state/cache,
security, optional dependencies, resources, and prototype acceptance criteria.

Plans 01–16 remain normative. The dashboard renders Plan-15 immutable results/analyses and
Plan-16 Plotly figures/typed presentation models. It does not calculate finance semantics,
write annotations, launch experiments, generate reports, ingest data, or expose DuckDB.

## 2. Scope

### 2.1 In scope

- A required 3.0 local Streamlit prototype behind the `dashboard` extra
- Project research database, verified backup/snapshot copy, and portable export source modes
- Read-only/shared-lease startup and active-writer refusal/recovery guidance
- Run overview, performance/drawdown, positions/exposures, orders/execution, attribution,
  diagnostics, study/trial comparison, and canonical/feature/provenance inspection pages
- Reuse of Plan-16 figures and Plan-15 bounded result/analysis APIs
- Per-session navigation/filter state and content-root-keyed immutable query caching
- Empty/unavailable/not-applicable/unsafe/fidelity/comparison/reuse presentation
- Local-only security posture, accessibility, limits, diagnostics, and framework evaluation
- CLI launch contract and optional-dependency/import matrix

### 2.2 Out of scope

- Ingestion, simulation/study launch, analysis/report generation, annotation/tag mutation,
  deletion/archive, database migration, export creation, or any other managed write
- Hosted deployment, authentication/authorization, multi-user tenancy, collaboration, or
  production web-server support
- Public Internet or LAN exposure as a supported configuration
- Raw SQL consoles, arbitrary table browsing, unrestricted dataframe download, file upload,
  custom Python execution, or filesystem exploration
- A second plotting/metric implementation or dashboard-specific result schema
- Persisted dashboard state, saved views, user accounts, alerts, scheduling, or live updates
- Promising Streamlit permanently before the prototype exit criteria pass

## 3. Normative decisions

1. The dashboard is a required 3.0 feature delivered through optional installation extra
   `dashboard`; optional describes dependency installation, not roadmap deferral.
2. `persistra` base and all non-dashboard namespaces import without Streamlit. Importing
   `persistra.dashboard` exposes lightweight launch/config models; Streamlit imports lazily at
   invocation. Missing dependencies produce `pip install persistra[dashboard]` guidance.
3. The dashboard process is read-only. It never acquires `RESEARCH_WRITE`, calls a mutating
   service, starts a worker, writes a cache into managed databases, or offers a UI control that
   implies persistence.
4. Every page uses public Plan-15 result/analysis/query handles and Plan-16 figure functions or
   typed blocks. It does not query physical schemas, table names, private repositories, or
   compute metrics/attribution/comparison in page code.
5. A live project research database opens only under Plan-02 read-only/shared lease. If an
   active writer or incompatible lease exists, startup/query fails visibly with instructions
   to stop the writer or use a verified backup/portable export. It does not retry forever or
   open an unsafe copy.
6. DuckDB's process/file lock remains authoritative in addition to the advisory lease. The
   dashboard does not claim concurrent read access to a file open for writing.
7. Verified backup/snapshot and Plan-15 portable export modes are immutable/read-only and are
   preferred for browsing while ingestion/studies/analysis writes continue elsewhere.
8. Source selection occurs through validated CLI/config before Streamlit starts. The app has no
   general file uploader/path textbox; large database upload is memory-unsafe and extension
   filtering is not a security boundary.
9. No DuckDB/project connection is globally cached. Each bounded query opens a read-only
   service scope on the executing session thread, verifies source identity/root, materializes
   bounded public output, and closes/detaches it deterministically.
10. Only immutable serialized query/figure input data may be cached. Cache keys include source
    database/export identity, schema/storage compatibility, subject/table/artifact roots,
    exact filters, query/renderer versions, locale/timezone, and limits.
11. A cache hit is verified against the current immutable root/fingerprint before use. Live
    research changes invalidate rather than mix results. Cache never stores secrets, licensed
    raw values beyond policy, connection objects, or unbounded frames.
12. Session state contains navigation, selected IDs, filters, pagination, and presentation
    preferences only. It is not provenance or durable state and can disappear at any rerun.
13. Page/widget keys are stable qualified strings. UI order never affects result identity,
    data order, or cache semantics.
14. The dashboard renders structured unavailable/not-applicable/empty states and warnings. It
    never converts them to zero, drops failures, invents vectorized orders, or combines an
    incompatible comparison.
15. Default server binding is loopback. The launch service rejects non-loopback address unless
    an explicit unsupported-development override is supplied, and then displays a persistent
    security warning. Hosted/public deployment remains unsupported.
16. Framework XSRF/CORS/security protections remain enabled. The dashboard enables no static
    file serving, unsafe HTML, raw component JavaScript, external CDN, telemetry, or automatic
    browser opening by default.
17. Visible source content is subject to Plan-15 licensing/redaction. Downloads are bounded
    render-time copies of already authorized public tables/HTML and do not mutate/register an
    artifact.
18. Page errors are isolated into structured panels with stable reason/correlation ID and safe
    recovery. One unavailable artifact does not crash unrelated navigation.
19. Resource limits and explicit pagination apply before pandas/Plotly/Streamlit materialization.
    Browser rendering never receives an unbounded table/figure.
20. Framework permanence requires passing the functional, security, accessibility, performance,
    optional-boundary, and maintainability evaluation in this plan; otherwise the prototype is
    revised before implementation expands.

## 4. Package and installation boundary

```text
src/persistra/dashboard/
├── __init__.py
├── configuration.py
├── launcher.py
├── app.py
├── source.py
├── state.py
├── cache.py
├── components.py
└── pages/
    ├── overview.py
    ├── performance.py
    ├── portfolio.py
    ├── execution.py
    ├── attribution.py
    ├── diagnostics.py
    ├── studies.py
    └── inspection.py
```

`dashboard` depends on `viz` and installs Streamlit plus dashboard-only dependencies. It does
not depend on `static`, `search`, or `optimize`. The `all` extra includes it. Dashboard modules
must not leak Streamlit types into `persistra.results`, `analysis`, `viz`, or `reports`.

The exact Streamlit lower/upper compatibility range is pinned and tested during implementation.
Framework features are accessed through a small internal adapter so widget/cache/navigation
API churn is localized; this is not a general dashboard framework abstraction.

## 5. Startup and source model

### 5.1 Launch request

```python no-run
@dataclass(frozen=True, slots=True)
class DashboardRequest:
    source: ProjectDashboardSource | BackupDashboardSource | PortableExportSource
    bind_address: str = "127.0.0.1"
    port: int = 8501
    open_browser: bool = False
    theme: ThemeRef = ThemeRef("persistra.default_light@1")
    display_timezone: str = "UTC"
    limits: DashboardLimits = DashboardLimits()
    unsupported_network_override: bool = False
```

The CLI is:

```text
persistra dashboard --project /path/to/project
persistra dashboard --backup /path/to/research.backup.duckdb
persistra dashboard --export /path/to/run-export.duckdb
```

Exactly one source is required. Paths resolve/canonicalize before launch, reject symlink/
ownership/type surprises under Plan 02, and are passed to the child app through a bounded
one-use local configuration token rather than query parameters or environment dumps. The
dashboard does not display absolute paths by default.

```python no-run
@dataclass(frozen=True, slots=True)
class DashboardLimits:
    max_rows_per_query: int = 1_000_000
    max_points_per_figure: int = 200_000
    max_table_display_rows: int = 10_000
    max_concurrent_queries: int = 4
    query_timeout: Duration = Duration(60_000_000)
    max_runs_listed: int = 10_000
```

All values are positive. A query or figure exceeding a limit shows a structured truncation
notice with original counts and a narrower-filter suggestion; limits never silently drop
rows without the notice.

### 5.2 Project source

Startup validates the project, configuration, research database ID/role/schema, advisory
shared lease, DuckDB read-only open, and referenced market database identities. It never runs
migrations. A required migration, active writer, missing member, or incompatible schema stops
with commands for `db inspect`, `db backup`, or `runs export` as appropriate.

The app may inspect canonical/feature data only when the project source pins exact composite
snapshots and the page's public capability is available. It never resolves `latest` differently
inside one page render. Market members open read-only under shared leases for the shortest
bounded query scope.

### 5.3 Backup and portable export source

A backup must pass Plan-02 copy manifest/database identity/checksum verification and opens
read-only. A portable export must pass Plan-15 reader/storage/schema/manifest/logical-root/
extension/closure verification with external access disabled. Inapplicable pages render their
missing capability; an export need not contain project canonical data.

Source mode, IDs, snapshot/manifest roots, schema/storage versions, verification state, and
staleness/copy instant are always visible in the sidebar and provenance page.

## 6. Application shell and state

The shell renders source identity/status, global unsafe/fidelity/licensing/compatible-reuse
banner, navigation, selected study/run/analysis, interval/instrument/slice filters, timezone,
theme, query budget, and page content. It restores only validated session values that still
exist in the current source root; stale selections reset with a message.

`DashboardSessionState` is a typed adapter around Streamlit session state. It stores wire IDs
and primitive validated filter values, not handles, connections, dataframes, figures, callable
objects, credentials, or arbitrary pickle. Every widget has one stable key under
`persistra.dashboard.<page>.<control>@1`.

Streamlit reruns execute the page from the top. Page modules therefore have no hidden mutable
module state and obtain everything through the typed state/source services. Session state is
explicitly ephemeral; Streamlit documents it as per-session state shared across pages in a
multipage app ([session state](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)).

## 7. Query and cache contract

### 7.1 Query flow

Each page declares a `PageQueryPlan` before reading: exact subject IDs/roots, capability/table,
filters, columns, sort, page cursor, requested rows/points, and maximum bytes. The plan is
validated by Plan-15 public services. Queries return immutable serializable models/frames and
close the project/export reader before rendering.

A page cannot pass preview/truncated data into a metric or attribution calculation. It can
only visualize the exact already-computed artifact or display a labeled preview.

### 7.2 Cache

The dashboard may use `st.cache_data` only through `DashboardDataCache`. Key material is an
explicit canonical `DashboardCacheKey`, not Streamlit's implicit hashing of handles. Entries
have max count/bytes and a bounded TTL for cleanup, but correctness relies on immutable roots,
not time. Cached output is copied/immutable so one session cannot mutate another.

Connections/resources are deliberately not placed in `st.cache_resource`: Streamlit notes
that global cached resources are shared across sessions and must be thread-safe, while cleanup
callbacks are not guaranteed at shutdown ([resource cache](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_resource)).
Plan-02 project/connection thread ownership is therefore preserved by short per-query scopes.

Cache diagnostics expose hit/miss/invalidated, source root, age, rows/bytes, and version without
showing values. A source fingerprint/root mismatch evicts. Memory pressure evicts by stable
least-recently-used metadata but does not change semantic output.

## 8. Required pages

### 8.1 Run overview

Shows exact run/artifact/design/execution/attempt/study/trial/fold/scenario identities,
simulator/status/interval, safety/licensing/fidelity, compatible-reuse differences, data
snapshots, strategy/portfolio configuration, headline existing metric artifact values, and
provenance. Missing standard analyses are shown as unavailable with CLI/API generation guidance;
the dashboard cannot compute them.

### 8.2 Performance and drawdowns

Uses Plan-16 equity/return/benchmark/drawdown/rolling/distribution figures and Plan-15 metric
tables. Filters can select an already existing analysis artifact/slice. It never recomputes
returns, annualization, risk-free alignment, or drawdowns from visible equity rows.

### 8.3 Positions and exposures

Shows bounded point-in-time holdings, cash decomposition, long/short/gross/net, classification/
factor/benchmark-relative exposure, concentration, turnover, borrow, margin, settlement, and
action timelines from exact public run/analysis data. Unknown/absent/unavailable/stale remain
distinct. Instrument expansion is paginated and capped.

### 8.4 Orders and execution

For event runs, shows order status separate from fill progress, transitions, cancellation/
replacement lineage, fills, latency, participation/capacity, observed/estimated/modeled costs,
and implementation shortfall. For vectorized runs, shows targets/rebalances/synthetic fills/
shortfall and a visible no-order fidelity panel; it never manufactures order rates.

### 8.5 Attribution

Selects existing Plan-15 attribution artifacts, shows reconciliation state/residual, holdings/
transaction/classification/factor/strategy/long-short/cost/benchmark components, requirements,
and unavailable periods. Unreconciled artifacts are visibly nonauthoritative.

### 8.6 Diagnostics

Displays registered scalar/time-series/cross-sectional/event/tabular diagnostics, data-quality
findings, temporal conformance, alpha/validation/holdout contamination, simulator fidelity,
accounting reconciliation, logs, and warning filters. It honors diagnostic registered schemas
and cannot render arbitrary HTML.

### 8.7 Study and trial comparison

Shows Plan-14 planned/reused/scheduled/completed/failed/cancelled/not-scheduled coverage,
search suggestions/objectives, folds/scenarios/replicates, failure reasons, stability artifacts,
and existing Plan-15 comparisons. Compatible/warned/incompatible classification controls
combined views. Completion/failure counts are never filtered out of denominators silently.

### 8.8 Data, feature, and provenance inspection

Project mode can inspect bounded canonical observations/revisions/availability, universe and
identifier membership, research dataset rows/states, feature/label metadata and lineage,
component conformance, snapshots, code/dependencies, and export/storage compatibility through
public services. Label values are available only on analysis-authorized surfaces and never
installed into a strategy context. Backup/export mode states unavailable capabilities.

## 9. Presentation and interaction contract

All figures come from Plan 16 with exact figure config, warnings, reduction evidence, and
accessibility metadata. Tables use Plan-15 canonical order, stable nullable dtypes, explicit
units/state/reason, bounded pagination, and CSV download only when licensing and byte/row limits
permit. Download bytes are generated in memory from the current exact page root and are not
registered artifacts.

Unsafe, contaminated, compatible reuse, optimistic same-close, retrospective capacity,
estimated/model costs, incomplete marks, unreconciled accounting/attribution, and incompatible
comparison use persistent text banners plus icons/styles. A user cannot dismiss them globally.

Filters that would require a new analysis show what is missing and the public API/CLI recipe;
they do not approximate. Cross-filter selections use exact IDs, not ticker text. URL query
parameters may encode nonsecret view state only after validation and never paths/credentials.

## 10. Read-only enforcement

Read-only is enforced in layers:

- the launcher permits only dashboard source types and `ProjectMode.READ_ONLY`;
- project/export connections use DuckDB read-only mode and shared advisory leases;
- page dependencies expose query interfaces without mutation methods;
- dashboard package has an import-lint rule forbidding ingestion/runner/publication/annotation/
  report-render/retention write services;
- no UI controls invoke writes; download is response-only;
- tests monkeypatch/deny filesystem and DuckDB write calls after startup; and
- schema/database file checksum/change sentinels prove no managed mutation across sessions.

Existing reports may be inspected/downloaded. Creating a report, export, analysis, annotation,
backup, or snapshot is outside the dashboard and shown only as an external CLI/API instruction.

## 11. Security and deployment boundary

Streamlit's normal local command starts a web server; its documentation describes local use at
loopback and treats security as shared responsibility ([Streamlit trust and security](https://docs.streamlit.io/deploy/streamlit-community-cloud/get-started/trust-and-security)).
Persistra supports only a trusted local researcher on loopback in 3.0. It provides no
authentication and therefore makes no safe LAN/Internet claim.

The launcher validates loopback address/port, refuses privileged/in-use ports, preserves XSRF
and CORS protection, disables usage statistics where supported, and supplies a generated
minimal config. It does not read project `.streamlit` config that could enable unsafe serving,
uploads, or network binding without explicit audited override.

There is no file uploader. Streamlit itself notes that extension/type filtering is only best
effort and uploaded files are held in backend memory ([file uploader](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader));
database sources are instead verified before process launch. Static serving is disabled.

All rendered text is escaped through Plan-16 models; unsafe HTML/JavaScript components are
forbidden. External links are allowlisted `https` and visibly external. Errors redact paths,
credentials, environment, SQL, licensed values, and stack locals. The dashboard makes no
outbound network request and standard tests run with network denied.

## 12. Resources and failure behavior

Limits cover selectable runs/analyses/studies, query rows/columns/bytes/time, pages/cursors,
cached entries/bytes/TTL, table display/download, figure points/traces/categories/bytes,
diagnostics/log rows, session-state bytes, concurrent sessions, and total process memory.
Defaults target one local user and a small bounded number of browser sessions.

| Case | Required outcome |
| --- | --- |
| Dashboard extra missing | Actionable install error; base imports remain clean |
| Research writer active | Refuse source with backup/export guidance |
| Writer begins between reruns | Next open/lease fails visibly; never use mixed cache |
| Backup/export checksum mismatch | Refuse before page rendering |
| Source schema/storage unsupported | Compatibility guidance; never migrate |
| Cached root differs | Evict and requery exact source |
| Query exceeds limit | Structured panel with narrower-filter/pagination guidance |
| Missing analysis | Unavailable plus generation guidance, no calculation |
| Vectorized order page | Exact not-applicable/no-order view |
| Incompatible comparison | Differences and separate views only |
| Page exception | Safe page-local error; shell/navigation survive |
| Browser disconnect/session loss | Ephemeral state/cache may disappear; no managed state affected |
| Non-loopback request | Reject unless unsupported override with persistent warning |

## 13. Public API and CLI

```python no-run
from persistra.dashboard import DashboardRequest, launch

launch(DashboardRequest(source=PortableExportSource(path)))
```

`launch()` validates and delegates to the framework runner without importing Streamlit until
needed. It is blocking and returns a structured exit outcome. Test-only app construction takes
an injected verified source service and does not spawn a server.

Exceptions include `DashboardExtraRequiredError`, `DashboardSourceError`,
`DashboardWriterConflictError`, `DashboardCompatibilityError`, `DashboardSecurityError`,
`DashboardQueryLimitError`, and `DashboardPageError`. Stable reasons cover wrong source role,
unverified copy/export, writer/lease conflict, migration needed, unsupported reader/storage,
cache-root mismatch, missing capability/analysis, licensing refusal, non-loopback bind, and
resource limit.

## 14. Prototype framework evaluation

Before Streamlit becomes permanent, an architecture decision record evaluates:

- clean `dashboard` extra and import startup behavior;
- multipage navigation, stable widget/session state, and deep-link limits;
- Plotly interaction, large-table pagination, accessibility, and unavailable-state rendering;
- read-only DuckDB/lease behavior across reruns/sessions and clean resource release;
- explicit cache keys/invalidation/memory bounds and no connection cross-thread sharing;
- framework rerun testability and deterministic page composition;
- XSRF/CORS/network/static/HTML security controls and loopback enforcement;
- packaging, startup time, memory, dependency footprint, version churn, and Linux support;
- public API separation and reuse of Plan-16 components; and
- maintainability of eight required pages without a parallel presentation/calculation stack.

The decision is `adopt`, `adopt_with_bounded_adapter_changes`, or `reject_and_respecify`.
Adoption requires all hard requirements above. A rejected prototype does not weaken dashboard
requirements; focused spec 17 is revised before broader UI implementation.

## 15. Testing and acceptance criteria

### 15.1 Optional boundary and sources

- Base/research/viz imports and stored dashboard-related metadata work without Streamlit;
  `dashboard` installs/imports/launches in the supported Python/Linux matrix; missing-extra
  guidance is exact and `all` includes it.
- Project/backup/export sources verify roles/IDs/schemas/roots/storage/closure/licenses; active
  writer, migration, corruption, missing member, and unsupported reader fail before content.
- No page, rerun, session, cache, download, or failure changes managed database/file checksums
  or calls a write-capable service.

### 15.2 Pages, semantics, and cache

- Every required page works for vectorized/event/single-run/study/backup/export applicable
  fixtures using only public Plan-15/16 APIs; import/static analysis forbids private SQL/writes.
- Golden UI models cover empty/unavailable/not-applicable/unsafe/contaminated/fidelity/
  compatible/incompatible/reconciled/unreconciled/truncated states without semantic loss.
- Vectorized pages contain no order status; event pages keep status separate from progress and
  cost evidence classes exact.
- Cache keys vary for every source/root/filter/version/locale/limit change; hits equal misses;
  invalidation, eviction, concurrent sessions, mutable-copy attempts, and live-source changes
  cannot mix artifacts.
- Session/widget state resets safely for removed IDs/source changes and never stores handles,
  frames, figures, secrets, or pickle.

### 15.3 Security, accessibility, and resources

- Framework-native app tests and browser smoke tests cover navigation, filters, pagination,
  downloads, reruns, back/forward, page isolation, reconnect, and source switching by restart.
- Loopback enforcement, XSRF/CORS defaults, telemetry/network denial, static/upload absence,
  HTML/script/URI escaping, path redaction, and unsupported network warning are tested.
- Keyboard navigation, headings/landmarks/labels/focus, contrast, non-color warnings, screen-
  reader descriptions, responsive layout, and reduced motion pass standard-page checks.
- Query/cache/figure/table/download/session/process limits fail visibly without browser/server
  crash or partial managed state. Startup and representative-page latency/memory are recorded.
- Docs snippets, strict MkDocs, CLI help, `make lint type test`, docs checks, and optional install
  matrix pass.

### 15.4 End-to-end prototype exit

Using one live read-only project with no writer, one verified backup taken while later project
writes continue, and one portable export, a documented demo must navigate all eight pages,
inspect vectorized and event runs/studies, show every material warning state, prove cache
invalidation and zero writes, survive a page failure/session reconnect, and pass the framework
evaluation with an explicit adoption decision.

Plan 17 is complete only when repository gates, docs checks, strict build, dashboard install/
security/accessibility/performance suites, benchmark hooks, and cumulative review find no
contradiction with the umbrella or Plans 01–16.

## 16. Review checklist for Plan 18

Plan 18 must preserve and test:

- the `dashboard` required-extra/base-import boundary;
- strict read-only public API use and active-writer refusal;
- exact source/root/cache identity and no cross-thread/global connection cache;
- all eight pages and vectorized/event semantic distinctions;
- structured unavailable/fidelity/safety/comparison/reuse/reconciliation presentation;
- loopback-only unsupported-hosting boundary, no uploads/static/unsafe HTML/network;
- explicit bounds, zero managed writes, ephemeral session state, and cache invalidation;
- reuse of Plan-16 figures/accessibility and Plan-15 query/licensing/export contracts; and
- a recorded evidence-based framework adoption decision.

Performance tests cannot justify private SQL, global connections, hidden reduction, writable
caches, or weaker security.

## 17. Consistency statement

This plan implements the umbrella's required local Streamlit explorer while respecting the
one-writer DuckDB constraint and every immutable result/analysis boundary. It keeps the app
small, read-only, local, bounded, and replaceable until the prototype proves the framework.
No project-level direction is revised.
