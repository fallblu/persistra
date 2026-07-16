# Focused specification 16: Plotly visualization and HTML reports

**Status:** Implementation-ready draft  
**Umbrella:** [`v3-spec.md`](v3-spec.md)\
**Primary packages:** `persistra.viz`, `persistra.reports`  
**Required before:** focused specifications 17–18  
**Last reviewed:** 2026-07-16

## 1. Purpose and relationship to the umbrella specification

This specification defines Persistra v3 visualization and reporting. It fixes a Plotly-only
figure API, deterministic visual data models, themes, fidelity/safety presentation, empty and
unavailable behavior, reusable report sections, guaranteed self-contained interactive HTML,
directory bundles, optional static rendering, and immutable report artifact identity.

Plans 01–15 remain normative. This plan renders their public result and immutable analysis
objects; it does not query private tables, calculate independent finance metrics, mutate a run
or analysis, or weaken comparison compatibility. Plan 17 uses the same public figures/sections.

## 2. Scope

### 2.1 In scope

- Plotly as the only supported 3.0 plotting backend
- Pure figure functions for performance, drawdown, distributions, rolling metrics,
  exposures, holdings, turnover, costs, capacity, orders/fills, attribution, alpha,
  validation, scenarios/studies, comparison, diagnostics, fidelity, and provenance
- Stable figure input models and deterministic trace/layout ordering
- Configurable accessible themes, number/time formatting, and semantic color roles
- Explicit missing, unavailable, unsafe, fidelity, comparison, and truncation presentation
- Reusable typed report sections and a standard run/study report
- Self-contained offline HTML and optional local-asset directory bundles
- Report planning, render attempts, immutable Plan-15 analysis artifacts, manifests, and APIs
- Security/sanitization, resource budgets, failure behavior, and testing strategy

### 2.2 Out of scope

- Matplotlib, Seaborn, Bokeh, Altair, a backend abstraction, or arbitrary JavaScript plugins
- Finance calculations, metric formulas, attribution linking, or compatibility decisions
- A general dashboard/UI framework, server, authentication, or hosted report service
- Silent visual downsampling or aggregation that changes the represented meaning
- Browser screenshots as the authority for data correctness
- Guaranteed PNG/SVG/PDF in the base or `viz` installation; static rendering is optional
- Editing reports after completion; changes produce a new report artifact

## 3. Normative decisions

1. Figure functions accept only typed Plan-15 run/analysis handles or immutable public figure
   input models and return a Plotly `Figure`. They never display, write files, open a browser,
   mutate input, or create an analysis artifact.
2. Financial values shown in a figure must already exist in a run or immutable analysis
   artifact. Visualization may reshape, filter, paginate, and apply an explicitly visual-only
   bounded reduction; it cannot independently compute a metric with financial semantics.
3. Plotly is the sole backend. There is no backend protocol in 3.0 and no promise of identical
   output from another plotting library.
4. The base package imports without Plotly/Jinja/report dependencies. The required `viz` extra
   installs Plotly and HTML-report dependencies. Stored report/result metadata remains readable
   in base. Missing dependencies fail at capability invocation with exact installation guidance.
5. Plot functions are deterministic for equal input roots, configuration, locale/timezone,
   Plotly version, and renderer schema. Trace order, category order, colors, labels, and layout
   never depend on set/hash/database insertion order.
6. A figure is not a persisted artifact by default. A persisted report is an immutable Plan-15
   `analysis_artifact` of kind `report`; its identity includes every run/analysis input and
   renderer/template/dependency/configuration fact.
7. The guaranteed report is one self-contained interactive HTML file with Plotly JavaScript,
   styles, figure data, manifest summary, and required assets embedded. It performs no network
   request when opened.
8. Directory-bundle mode may deduplicate Plotly/assets across reports but uses only relative
   manifest-listed files, verifies checksums, and is a distinct output mode/identity.
9. Static PNG/SVG/PDF depends on a separately installed renderer capability and is optional.
   Its absence cannot fail HTML report release acceptance.
10. Unsafe data, material fidelity limitations, compatible reuse, unavailable analysis,
    incomplete samples, and warned comparison are visible in the figure/report near the
    affected claim. Styling alone is not the only signal.
11. Incompatible comparisons cannot render a combined authoritative chart. They may render a
    differences panel and separate unaligned figures labeled incompatible.
12. Missing and unavailable differ from empty. Empty applicable data returns a valid annotated
    figure; unavailable returns a valid reason/warning figure or raises only under strict mode;
    not-applicable surfaces say why.
13. Point count/resource limits never cause silent truncation. Reduction is named, deterministic,
    records original/rendered counts and method, preserves mandatory extrema/events where
    applicable, and is visible in figure/report provenance.
14. Reports are planned from section requirements. Missing required analysis can fail, render
    unavailable, or be computed as a new Plan-15 analysis only under an explicit build policy;
    it is never calculated inside a template.
15. Templates and renderers receive escaped text and canonical bounded data. User HTML/
    JavaScript is rejected by default. A trusted custom section is visibly unsafe and isolated.
16. Figure JSON/HTML byte identity is not financial artifact identity. Report identity covers
    canonical semantic manifest plus exact emitted bytes/checksums and dependency versions.
17. Time axes use exact UTC data and declared display timezone; hover includes timezone/instant
    where ambiguity matters. Local display conversion cannot change interval membership.
18. Colors, line styles, symbols, labels, and annotations jointly encode meaning. No required
    distinction relies solely on color.
19. Reports include exact source run/analysis/report identities in visible content and a
    machine-readable embedded manifest. Compatible reuse always displays source and requested
    identities/differences.
20. Every operation is bounded, synchronous, and explicit about materialization. Report writes
    stage, verify, then publish/register; partial files never become completed artifacts.

## 4. Package and optional-dependency boundary

```text
src/persistra/
├── viz/
│   ├── __init__.py
│   ├── models.py
│   ├── themes.py
│   ├── formatting.py
│   ├── performance.py
│   ├── portfolio.py
│   ├── execution.py
│   ├── attribution.py
│   ├── diagnostics.py
│   ├── validation.py
│   ├── studies.py
│   └── provenance.py
└── reports/
    ├── __init__.py
    ├── models.py
    ├── sections.py
    ├── builder.py
    ├── renderer.py
    ├── manifests.py
    ├── repository.py
    └── templates/
```

`persistra.viz` and `persistra.reports` use lazy dependency guards; top-level `persistra`
never imports Plotly. `pip install persistra[viz]` is the required supported visualization/
HTML-report capability. A separate `static` extra may install the pinned browser/static image
renderer. The `dashboard` extra in Plan 17 depends on `viz` but not `static`.

Core result/analysis models contain no Plotly types. Plotly `Figure` appears only at the viz
boundary. Jinja/templates are report implementation details and cannot become a public data
model or metric engine.

## 5. Identity, values, and configuration

### 5.1 Assigned IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `ReportPlanId` | `report_plan` | One immutable resolved section/input plan |
| `ReportRenderAttemptId` | `report_render_attempt` | One staged render attempt |
| `ReportOutputId` | `report_output` | One verified emitted HTML/bundle output |

The completed persisted report also has Plan-15 `AnalysisArtifactId` and
`analysis_artifact_content_id`. On-demand figures do not allocate IDs.

### 5.2 Theme and render values

```python no-run
@dataclass(frozen=True, slots=True)
class FigureConfig:
    theme: ThemeRef = ThemeRef("persistra.default_light@1")
    display_timezone: str = "UTC"
    locale: str = "en_US"
    width: int | None = None
    height: int | None = None
    strict_unavailable: bool = False
    reduction: VisualReductionPolicy = VisualReductionPolicy.none()
    limits: FigureLimits = FigureLimits()

@dataclass(frozen=True, slots=True)
class ReportRequest:
    title: str
    inputs: tuple[RunRef | AnalysisArtifactRef, ...]
    template: ReportTemplateRef
    sections: tuple[ReportSectionSpec, ...] | None
    theme: ThemeRef
    output_mode: ReportOutputMode
    missing_analysis: MissingAnalysisPolicy
    annotation_cutoff: datetime | None
    output_path: Path
    limits: ReportLimits
```

Report templates and sections use these exact public values:

```python no-run
@dataclass(frozen=True, slots=True)
class ReportTemplateRef:
    name: QualifiedName
    version: int
    definition_content_id: ContentId

@dataclass(frozen=True, slots=True)
class ReportSectionSpec:
    section: QualifiedName
    version: int
    title_override: str | None = None
    input_roles: tuple[str, ...] = ()
    missing_analysis: MissingAnalysisPolicy | None = None
    failure: Literal["fail_report", "render_unavailable", "omit_with_reason"] = "render_unavailable"

@dataclass(frozen=True, slots=True)
class SectionResourceDeclaration:
    max_input_rows: int
    max_output_blocks: int
    max_figures: int
    max_tables: int
    timeout: Duration

@dataclass(frozen=True, slots=True)
class ReportSectionDefinition:
    name: QualifiedName
    version: int
    accepted_subjects: tuple[Literal["run", "study", "comparison"], ...]
    required_logical_tables: tuple[str, ...]
    required_analysis_definitions: tuple[AnalysisDefinitionRef, ...]
    optional_analysis_requests: tuple[AnalysisRequest, ...]
    applicability: Literal["all", "vectorized", "event", "study", "comparison"]
    block_kinds: tuple[Literal["heading", "prose", "key_value", "table", "figure", "warning", "provenance", "appendix"], ...]
    default_failure: Literal["fail_report", "render_unavailable", "omit_with_reason"]
    renderer_name: QualifiedName
    renderer_version: int
    renderer_content_id: ContentId
    compatible_template_names: tuple[QualifiedName, ...]
    minimum_template_versions: tuple[int, ...]
    resources: SectionResourceDeclaration
    conformance_content_id: ContentId
    definition_content_id: ContentId
```

Names/versions resolve in the report registry before planning; unknown roles, duplicate
sections, unused overrides, incompatible subjects, and failure policies weaker than the
registered section default are rejected. `sections=None` expands to the installed template's
ordered defaults below; an explicit tuple is used exactly in caller order. Renderer/template
names and versions are unique and paired by ordinal, resource values are positive, optional
analysis requests must match the declared definitions, and conformance/renderer/definition
roots are mandatory identity inputs.

| Template ref | Ordered installed section refs |
| --- | --- |
| `persistra.report.run_vectorized@1` | `summary`, `provenance`, `performance_risk`, `portfolio`, `synthetic_execution_costs`, `attribution`, `diagnostics`, `reproduction` |
| `persistra.report.run_event@1` | `summary`, `provenance`, `performance_risk`, `portfolio`, `orders_execution_costs`, `accounting`, `attribution`, `diagnostics`, `reproduction` |
| `persistra.report.study@1` | `summary`, `study_design`, `trial_fold_scenario_outcomes`, `objective_stability`, `diagnostics`, `provenance`, `reproduction` |
| `persistra.report.comparison@1` | `summary`, `compatibility`, `separate_performance`, `differences`, `diagnostics`, `provenance`, `reproduction` |

Every table entry expands to `persistra.report.section.<token>@1`. The registry fixture pins
each section's exact logical-table/analysis requirements, applicability value, block schema,
and failure default using `ReportSectionDefinition`; its canonical roots and the fully expanded
ordered manifest for every template are golden acceptance fixtures. Event-only/accounting
sections are inapplicable to vectorized templates rather than silently empty, and standard
templates may change only by new version.

Friendly references resolve to exact content/versions before planning. `output_path` affects
where bytes are written but not semantic report content; normalized output mode/filename and
emitted byte checksum enter the output manifest. Width/height must be positive and bounded.

The limits and reduction values are enumerated dataclasses in the style of earlier plans;
all values are positive, enter report/figure identity, and never authorize silent data
loss:

```python no-run
@dataclass(frozen=True, slots=True)
class FigureLimits:
    max_input_rows: int = 2_000_000
    max_points_per_trace: int = 200_000
    max_traces: int = 200
    max_figure_json_bytes: int = 50_000_000
    timeout: Duration = Duration(300_000_000)

@dataclass(frozen=True, slots=True)
class ReportLimits:
    max_sections: int = 200
    max_figures: int = 500
    max_tables: int = 500
    max_output_bytes: int = 500_000_000
    max_asset_bytes: int = 100_000_000
    timeout: Duration = Duration(1_800_000_000)
```

`VisualReductionPolicy` has exactly these variants, each versioned and recorded in figure
provenance: `none()` (fail when a reducible render limit would be exceeded);
`min_max_envelope(buckets: int)` (per-bucket min/max/first/last over the canonical order);
`every_nth(stride: int)`
(deterministic decimation keeping first/last); `event_preserving(stride: int)`
(deterministic stride decimation that additionally retains every point flagged as an
event — flows, corporate actions, findings, and drawdown extrema — by the figure's data
model); and `top_n(n: int, rank_by: str, direction: Literal["ascending", "descending"] =
"descending", magnitude: bool = False, other: Literal["sum", "mean"] = "sum")`.
For `top_n`, the named finite numeric series-summary column is ranked by signed value or
absolute magnitude as declared, unavailable/null ranks are ineligible and fold into `other`,
ties use series-key bytes, and `other` is the pointwise sum or arithmetic mean over aligned
eligible values with an unavailable point when no member is computed. Figure requirements
declare whether each ranking/aggregation choice is semantically legal. Reduction changes
presentation only; every reduced figure is labeled with the policy, parameters, and original
counts.

### 5.3 Theme contract

A theme declares semantic roles: background/surface/text/muted/grid, positive/negative/neutral,
long/short/cash/benchmark, observed/estimated/modeled/unavailable, warning/unsafe/incompatible,
categorical palette, line/symbol cycles, fonts, spacing, and Plotly layout defaults. It records
WCAG-oriented contrast tests and color-vision fixtures. User themes register qualified name,
version, canonical values, licensing, and conformance; raw executable theme callbacks reject.

## 6. Figure input and output contract

### 6.1 Input resolution

Each plot function declares a `FigureRequirement`: accepted subject kinds, exact required
logical table/analysis definition and minimum versions, applicable simulator/fidelity fields,
comparison classification, columns/units/states, maximum rows, canonical order, and permitted
visual reduction. A resolver uses only Plan-15 bounded public APIs and returns an immutable
`FigureDataModel` with source identities, counts, warnings, and applicability.

No function accepts arbitrary SQL/table names. Advanced users may construct a validated public
figure model directly; it has exact schema/units and carries `external_unverified` provenance
unless rooted in a managed artifact.

### 6.2 Deterministic figure construction

Equal resolved models/configuration/dependency versions produce equal canonical figure JSON
after removing explicitly nonsemantic Plotly-generated IDs. Rules include:

- traces sort by semantic layer, series key bytes, then stable source ordinal;
- x values sort by exact instant/key and never rely on dataframe order;
- category orders are explicit; missing categories do not recolor remaining categories;
- theme color assignment hashes stable semantic keys into a collision-resolved palette order;
- numeric formatting is unit-specific and does not feed rounded display values back into data;
- hover `customdata` uses bounded typed arrays, never HTML assembled from untrusted text;
- `uirevision`, trace UIDs, and animation are disabled or deterministically set; and
- figure metadata embeds source content IDs, renderer/config roots, counts, warnings, and
  reduction evidence.

### 6.3 Empty, unavailable, and warning figures

A valid no-row result returns axes/title plus a centered `No applicable observations` message,
source identity, and zero count. An unavailable result includes stable reason and requirements;
not-applicable identifies the simulator/subject mismatch. Strict mode raises a typed exception
after producing the same structured outcome model, not an unstructured Plotly error.

Unsafe/warned states add a visible banner/annotation and machine-readable metadata. Individual
unavailable series use breaks/markers rather than interpolation. Stale/incomplete values have
distinct line/symbol style and hover reason.

## 7. Required figure families

### 7.1 Performance and risk

- equity/NAV and external-flow markers from exact run rows;
- TWR/cumulative return and benchmark from a chosen immutable metric/series artifact;
- drawdown depth with peak/trough/recovery annotations from analysis output;
- return/cost distributions, rolling metric series, tail/risk and regime views; and
- metric summary table using structured states/units/warnings.

No plot recomputes returns, drawdowns, rolling windows, annualization, or benchmark alignment.

### 7.2 Portfolio and execution

- gross/net/classification/factor/benchmark-relative exposure;
- holdings/weights/concentration, cash decomposition, turnover, and target-to-fill shortfall;
- orders by status/progress, event timeline, fills, latency, participation, and capacity;
- cost component/evidence decomposition and implementation shortfall; and
- borrow/margin/settlement/action timelines.

Plan-12 vectorized inputs render synthetic fills/shortfall and explicitly omit order charts.
They never generate cancelled/rejected/fill-rate order traces. Plan-13 partial terminal orders
retain cumulative fill and terminal status as distinct encodings.

### 7.3 Attribution, diagnostics, validation, and studies

- reconciled attribution components/residual and long/short/cost decomposition;
- alpha IC/quantiles/coverage/turnover/decay/exposure and validation fold/purge/holdout state;
- quality/fidelity/provenance/lineage and structured diagnostic families;
- study trial/fold/scenario outcomes, objective surfaces, failure coverage, and search progress;
- Monte Carlo/bootstrap distributions with preserved/destroyed-dependence warning; and
- run comparison only after Plan-15 compatibility decision.

Plots display structured unavailable/failed/not-scheduled outcomes rather than filtering them
out. Final-holdout contamination and compatible reuse are prominent.

## 8. Visual reduction and large outputs

The default is no reduction and a bounded error above the figure point limit. Registered
visual-only reductions include deterministic min/max envelope per equal-count canonical bucket, event-
preserving thinning, stable top-N plus explicit `other`, and uniform stride for nonfinancial
diagnostic points. Each declares which extrema/events/totals it preserves/destroys.

For `min_max_envelope`, let one trace contain `M > 0` eligible points in canonical order and
`B = min(buckets, M)`. Bucket `j` contains zero-based ordinals
`floor(j*M/B)` through `floor((j+1)*M/B)-1`, inclusive. It emits the distinct source points
that are first, minimum, maximum, or last in that bucket; numeric ties choose the earliest
source ordinal, and the emitted points are finally ordered by source ordinal. Thus there are
no empty buckets, the final point is retained, and one point satisfying multiple roles appears
once. `M = 0` uses the normal empty-figure contract.

`max_input_rows`, `timeout`, and `max_figure_json_bytes` are unconditional safety ceilings;
they are checked respectively before reduction, throughout resolution/rendering, and after
canonical serialization. `max_points_per_trace` is reducible by envelope/stride/event-
preserving policies, and `max_traces` is reducible only by `top_n`. A reduction that still
exceeds its permitted render ceiling fails with `FigureResourceLimitError`; no reduction may
rescue or stream past an unconditional ceiling.

Reduction operates on already computed values and cannot calculate a new finance statistic.
The figure stores original/eligible/rendered counts, parameters, bucket boundaries, preserved
event roots, and reduction warning. Reports show this in captions/provenance. Server/browser
Plotly sampling is disabled where it could hide semantics.

## 9. Report architecture

### 9.1 Planning and sections

A section is a registered typed builder with qualified name/version, input requirements,
output block schema, renderer/template version, optional analysis requests, applicability,
failure policy, resource declaration, and conformance tests. It returns immutable blocks:
heading, prose, key-value, table, Plotly figure, warning, provenance, or appendix reference.
It never returns arbitrary executable template code.

The standard run report contains:

1. executive summary and structured unavailable warnings;
2. data snapshots, universe, temporal/safety/licensing state;
3. strategy, portfolio, accounting, simulator, and fidelity configuration;
4. performance, risk, drawdowns, and stress;
5. holdings, cash, exposures, turnover, and capacity;
6. execution/orders/synthetic fills and costs as applicable;
7. reconciled attribution;
8. diagnostics, validation/study/scenario outcomes, and warnings; and
9. exact provenance, identities, reproduction/compatibility details.

A study/comparison report swaps applicable sections but uses the same block/render contract.
Section applicability is explicit; omitted sections appear in the manifest with reason.

### 9.2 Missing analysis policy

`require_existing` fails planning if an exact required analysis artifact is absent.
`render_unavailable` emits a visible unavailable section. `compute_missing` creates exact
Plan-15 analysis requests before report identity freezes, commits those independent artifacts,
then plans against their IDs. Failed analysis remains a section outcome; template code never
falls back to a private formula.

### 9.3 Report identity

Report execution content includes exact ordered run/analysis inputs and roots, annotation
revision cutoff/snapshot, section requirements/outcomes, template/theme/renderer versions and
bytes, Plotly/Jinja/dependency versions, locale/timezone, reduction/format/resource policies,
safety/licensing/fidelity/comparison warnings, output mode, and report schema. It excludes
attempt/output IDs, path, completion instant, and output checksum.

The completed report manifest adds every section/block/figure canonical root, embedded/local
asset checksums, emitted HTML/file-tree checksum, byte/file counts, CSP, output ID, and
analysis-artifact content root. Exact replay verifies bytes/roots under equal execution
content; dependency/template change creates a new report artifact.

## 10. HTML renderer and security

### 10.1 Self-contained mode

One UTF-8 HTML5 file embeds minified pinned Plotly JavaScript, its required third-party
license notice, CSS, canonical figure JSON,
bounded table data, text, and an escaped JSON manifest. It uses no CDN, web font, analytics,
remote image, iframe, fetch/XHR, service worker, or external link execution. External source
links are ordinary `https` anchors with safe attributes and are not required to render.

The renderer sets a restrictive documented CSP using exact script/style hashes rather than
random nonces, disables inline event handlers and `javascript:` URLs, escapes all
text/attributes/JSON closing sequences, validates URI schemes, and sanitizes trusted Markdown
to the supported element/attribute allowlist. Plotly config removes cloud/edit links.

### 10.2 Directory bundle

Bundle mode stages a directory containing `index.html`, local hashed Plotly/CSS/assets,
figure/data parts, and canonical manifest. Every reference is relative, normalized, inside the
bundle, checksum-listed, and case-collision checked. Symlinks, traversal, absolute/file/network
asset references, and executable user uploads reject. Opening `index.html` offline works
without a server for the supported browser matrix. Third-party assets retain manifest-listed
license notices in both modes; stripping them fails verification.

### 10.3 Static rendering

`persistra[static]` supplies a pinned renderer adapter for PNG/SVG/PDF. It runs with network
disabled, bounded process/time/memory, exact browser/renderer identity, and sanitized inputs.
Static outputs are optional report attachments with checksums. PDF page layout/accessibility
limitations are documented; static failure does not invalidate an already verified HTML
artifact unless requested as required.

## 11. Persistence schema

Plan 15 owns the existing `analysis`/`analysis_data` schemas and artifact envelope. This plan
adds report-specific migration tables under those schemas.

```sql
CREATE TABLE analysis.report_plans (
    report_plan_id UUID PRIMARY KEY,
    analysis_execution_content_id VARCHAR NOT NULL,
    template_content_id VARCHAR NOT NULL,
    theme_content_id VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    section_plan_content_id VARCHAR NOT NULL,
    output_mode VARCHAR NOT NULL CHECK (output_mode IN ('self_contained_html', 'directory_bundle')),
    renderer_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    report_plan_content_id VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analysis.report_outputs (
    report_output_id UUID PRIMARY KEY,
    report_plan_id UUID NOT NULL,
    analysis_artifact_id UUID NOT NULL UNIQUE,
    completed_render_attempt_id UUID NOT NULL,
    output_mode VARCHAR NOT NULL CHECK (output_mode IN ('self_contained_html', 'directory_bundle')),
    section_manifest_content_id VARCHAR NOT NULL,
    asset_manifest_content_id VARCHAR NOT NULL,
    embedded_manifest_content_id VARCHAR NOT NULL,
    output_content_id VARCHAR NOT NULL UNIQUE,
    byte_count BIGINT NOT NULL CHECK (byte_count >= 0),
    file_count BIGINT NOT NULL CHECK (file_count >= 1),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analysis.report_render_attempts (
    report_render_attempt_id UUID PRIMARY KEY,
    report_plan_id UUID NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN ('planned', 'rendering', 'verifying', 'completed', 'failed', 'cancelled')),
    report_output_id UUID,
    failure_content_id VARCHAR,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    CHECK ((status = 'completed') = (report_output_id IS NOT NULL))
);
```

```sql
CREATE TABLE analysis_data.report_sections (
    analysis_artifact_id UUID NOT NULL,
    section_ordinal INTEGER NOT NULL CHECK (section_ordinal >= 1),
    section_name VARCHAR NOT NULL,
    section_version INTEGER NOT NULL CHECK (section_version >= 1),
    state VARCHAR NOT NULL CHECK (state IN ('rendered', 'unavailable', 'not_applicable', 'failed')),
    input_content_id VARCHAR NOT NULL,
    block_manifest_content_id VARCHAR NOT NULL,
    warning_content_id VARCHAR NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (analysis_artifact_id, section_ordinal)
);

CREATE TABLE analysis_data.report_figures (
    analysis_artifact_id UUID NOT NULL,
    figure_ordinal INTEGER NOT NULL CHECK (figure_ordinal >= 1),
    section_ordinal INTEGER NOT NULL CHECK (section_ordinal >= 1),
    figure_kind VARCHAR NOT NULL,
    source_content_id VARCHAR NOT NULL,
    renderer_config_content_id VARCHAR NOT NULL,
    canonical_figure_content_id VARCHAR NOT NULL,
    original_point_count BIGINT NOT NULL CHECK (original_point_count >= 0),
    rendered_point_count BIGINT NOT NULL CHECK (rendered_point_count >= 0),
    reduction_content_id VARCHAR NOT NULL,
    warning_content_id VARCHAR NOT NULL,
    PRIMARY KEY (analysis_artifact_id, figure_ordinal),
    CHECK (rendered_point_count <= original_point_count)
);
```

Paths are not persisted as portable authority. Project-local output location is a managed
artifact-location record with opaque token and may be repaired without changing report
content. Plan-15 portable export can embed the self-contained bytes or selected bundle tree.

## 12. Public APIs

```python no-run
from persistra.viz import performance, execution, attribution

figure = performance.equity(run, config=figure_config)
figure = execution.costs(execution_analysis, config=figure_config)
figure = attribution.contributions(attribution_artifact, config=figure_config)

plan = project.services.reports.plan(request)
report = project.services.reports.render(plan)
report = project.services.reports.get(report.analysis_artifact_id)
```

Figure functions return `plotly.graph_objects.Figure` and no filesystem side effect. Report
render is the explicit state-changing API. `ReportHandle.open_bytes()` is bounded;
`copy_to(path)` verifies the managed content and writes a new nonauthoritative copy. No API
automatically launches a browser.

Exceptions include `VisualizationExtraRequiredError`, `FigureInputError`,
`FigureNotApplicableError`, `FigureResourceLimitError`, `ReportPlanningError`,
`ReportSectionUnavailableError`, `ReportRenderError`, `ReportVerificationError`,
`ReportSecurityError`, and `StaticRendererUnavailableError`. Reasons distinguish missing
analysis, incompatible comparison, unsafe input, point/table/byte limit, reduction forbidden,
template/theme mismatch, unsafe markup/URI, missing asset, checksum/CSP failure, and renderer
dependency mismatch.

## 13. Required edge cases

| Case | Required outcome |
| --- | --- |
| Empty applicable series | Valid annotated figure with exact schema/count |
| Structured unavailable metric | Visible reason; no zero/NaN-as-value trace |
| Plan-12 order plot | Not-applicable figure/section, never synthetic orders |
| Partial then cancelled order | Active fill progress plus cancelled terminal status preserved |
| Missing observed quote | Unavailable observed-spread point; estimator labeled estimated |
| Compatible reuse | Source/requested identities and differences visible |
| Incompatible comparison | Differences/separate views only; no combined authoritative trace |
| Unsafe or final-holdout-contaminated input | Prominent text banner plus metadata |
| Too many points | Bounded error or explicit recorded reduction, never silent |
| Missing optional section analysis | Frozen require/unavailable/compute policy decides |
| User text contains markup/script | Escaped/sanitized; never executes |
| Network unavailable | Self-contained/bundle renders normally |
| Static renderer missing | HTML succeeds; required static request fails with guidance |
| Render interrupted before rename | Staging removed/quarantined; no completed report |
| Same report execution replay | Verify existing artifact; no mutation or duplicate output |

## 14. Resources, accessibility, and privacy

Limits cover figure input/rendered points, traces, categories, hover bytes, annotations, table
rows/columns/cells, sections/blocks/figures, embedded JSON, asset/file/total bytes, recursion,
template time, render time, and static subprocess resources. Reports exceeding self-contained
limits may use bundle mode only when explicitly allowed; no silent mode switch.

Every chart has a title, axes/units, legend, source identity metadata, accessible description,
and non-color distinction for critical series. Tables use semantic headings. HTML has logical
heading order, landmarks, keyboard-friendly Plotly config where supported, skip navigation,
language declaration, visible focus, and reduced-motion style. Accessibility test failures are
release-gating for standard templates.

Reports can expose sensitive strategy parameters or licensed summaries. Section policy and
export licensing decide inclusion/redaction; redaction is visible and identity-bearing. No
credential, absolute path, raw environment secret, or unrestricted log content is rendered.

## 15. Migration and extension policy

V2 plot/report output is not imported as trusted v3 analysis. It may be an opaque external
attachment with no source/renderer identity. Plan-02 verified migrations own report tables;
completed report bytes are immutable and format changes create new artifacts.

Custom plots/sections/templates/themes register qualified name, version, canonical config,
requirements, output schema, code/dependencies, determinism/resources, safety/licensing,
HTML capability, and conformance fixtures. Default custom code returns typed figure/block
models, not raw HTML. Trusted raw HTML/JavaScript requires an explicit unsafe extension class,
is excluded from standard reports/exports by default, and makes deterministic/security claims
ineligible unless independently sandboxed and verified.

## 16. Implementation sequence

1. Add optional guards, figure models/requirements/config/limits, themes/formatting, canonical
   Plotly JSON, and empty/unavailable/warning behavior.
2. Implement performance/portfolio/execution/attribution/diagnostic/validation/study/provenance
   figures over bounded Plan-15 APIs with deterministic ordering.
3. Implement registered visual reduction, accessibility metadata, safe hover/text, and golden
   semantic figure fixtures.
4. Add report IDs/schemas/repositories, section/block registry, standard run/study/comparison
   plans, missing-analysis policy, and exact identity.
5. Implement self-contained and bundle renderers, offline assets, CSP/sanitization, staging/
   verification/publication, portable-export handoff, and fault/security tests.
6. Add optional static adapter, process isolation, attachment manifests, and failure policy.
7. Complete public docs/examples, base/viz/static install matrix, strict build, benchmark hooks,
   and cumulative Plans 01–16 review.

## 17. Acceptance tests and exit criteria

### 17.1 Figures

- Every required family accepts exact compatible handles, rejects wrong/unavailable/incompatible
  inputs correctly, and never queries private tables or calculates a Plan-15 finance metric.
- Canonical figure JSON is stable across dataframe/database insertion/order/chunk differences;
  equal category semantics retain color/order when categories disappear.
- Empty/unavailable/not-applicable/stale/unsafe/fidelity/compatible/incompatible/truncated states
  are visibly and machine-readably distinct.
- Plan-12 synthetic fills never create order traces; Plan-13 status/progress and observed/
  estimated/modeled cost evidence remain exact.
- Visual reduction fixtures prove counts/extrema/event preservation and visible warning; limits
  never silently drop data.
- Accessibility tests cover contrast, text alternatives, headings/landmarks, keyboard/focus,
  non-color encodings, UTC/local hover, and reduced motion.

### 17.2 Reports and artifacts

- Standard run/event/vectorized/study/comparison reports cover every required section and
  applicable/unavailable reason using only public result/analysis APIs.
- Missing-analysis policies require/render/compute exactly; computed work is a separate
  Plan-15 artifact fixed before report identity.
- Report identity changes for every material input/section/template/theme/renderer/dependency/
  locale/reduction/output-mode/warning change, not path/completion instant.
- Self-contained HTML performs zero network requests and embeds verified manifest/assets;
  bundle paths/checksums/relative closure reopen offline after relocation.
- XSS/HTML/URI/JSON/script/CSP/path/symlink/security fixtures cannot execute untrusted content.
- Fault injection at section/figure/template/write/fsync/verify/register/rename boundaries
  publishes no partial report and exact replay verifies prior bytes.
- Optional matrix proves base imports/reads metadata, `viz` plots/reports, missing `viz` guidance,
  optional `static` output/failure, and Plan-15 portable export/reopen.
- Docs snippets, strict MkDocs, migrations/copies/reopen, `make lint type test`, and docs checks
  pass.

### 17.3 End-to-end exit

A documented workflow must render all core figure families for one vectorized and one event
run; show safe/unsafe, missing, partial-order, compatible/incompatible, and reduced cases;
build and reopen self-contained run and study reports offline; build a relocated bundle;
persist exact report analysis artifacts; export them through Plan 15; and optionally demonstrate
static output without making it release-critical.

Plan 16 is complete only when repository gates, docs checks, strict build, optional install
matrix, security/accessibility suites, benchmark hooks, and cumulative review find no
contradiction with the umbrella or Plans 01–15.

## 18. Review checklist for dependent plans

Plans 17–18 must preserve:

- public Plan-15 result/analysis inputs and renderer-free finance semantics;
- Plotly-only deterministic figures with explicit unavailable/fidelity/safety/comparison state;
- vectorized no-order semantics and event status/fill-progress distinction;
- exact input/section/template/theme/dependency/report artifact identity;
- self-contained offline HTML guarantee and closed checksum-listed bundle mode;
- no network/executable user content, bounded resources, and explicit visual reduction;
- `viz`/`static` optional boundaries and base-package importability;
- report immutability and Plan-15 portable-export/reference behavior; and
- accessibility and security conformance of standard themes/templates.

Plan 17 may compose these figures/sections interactively but cannot fork their calculations or
write report/run data. Calling Streamlit's Plotly display primitive is a presentation action;
the shared figure function still returns the same deterministic `Figure` without display or
filesystem effects. Plan 18 owns semantic/canonical/accessibility/security fixtures and cannot
replace them with fragile pixel-only snapshots.

## 19. Consistency statement

This plan implements the umbrella Plotly and report direction while keeping finance semantics
in immutable result/analysis artifacts. It guarantees useful offline HTML, makes every material
warning and identity visible, avoids a premature backend abstraction, and keeps static/browser
dependencies optional. No project-level direction is revised.
