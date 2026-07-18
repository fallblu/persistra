# Public API overview

`Project` is the lifecycle root. Mutating capabilities require the matching
`ProjectMode` and are reached through `project.services`; result handles remain bounded
and do not expose SQL. Each namespace below links to its generated documentation.

| Namespace | Primary public surface |
|---|---|
| [`persistra`](persistra.md) | `Project`, `ProjectMode`, `ProjectOverrides`, version metadata |
| [`persistra.domain`](domain.md) | immutable identities, content IDs, time/money/duration primitives, clocks |
| [`persistra.catalog`](catalog.md) | sources, datasets, revisions, batches, snapshots, ingestion contracts |
| [`persistra.reference`](reference.md) | entities, identifiers, calendars, classifications, universes |
| [`persistra.market`](market.md) | canonical market/economic observations, bars, adjustments |
| [`persistra.research`](research.md) | datasets, SQL workspaces, components, features, labels, alpha, validation |
| [`persistra.portfolio`](portfolio.md) | decision-input safety, signals, forecasts, risk, construction, optimization |
| [`persistra.accounting`](accounting.md) | books, journal facts, settlements, lots, borrow, actions |
| [`persistra.simulation`](simulation.md) | vectorized and bounded event-order simulation, order kernels |
| [`persistra.experiments`](experiments.md) | studies, searches, scenarios, worker assignments and outcomes |
| [`persistra.results`](results.md) | normalized run handles, annotations, retention, portable exports |
| [`persistra.analysis`](analysis.md) | metrics, attribution, execution, comparison, scenario aggregation |
| [`persistra.viz`](viz.md) | deterministic Plotly figure families |
| [`persistra.reports`](reports.md) | offline HTML report plans, artifacts, bundle verification |
| [`persistra.dashboard`](dashboard.md) | verified read-only project, backup, and portable-export sources |
| [`persistra.conformance`](conformance.md) | provider/component conformance kits and reports |
| [`persistra.flagship`](flagship.md) | the versioned flagship momentum profile |
| [`persistra.errors`](errors.md) | the typed exception namespace with stable reason codes |

`persistra.ingestion` re-exports the catalog's versioned ingestion record contracts,
and `persistra.logging` provides the bounded structured-logging helpers used by run
publication. Both are documented on their parent pages.
