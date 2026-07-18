# Public API map

`Project` is the lifecycle root. Mutating capabilities require the matching `ProjectMode` and
are reached through `project.services`; result handles remain bounded and do not expose SQL.

| Namespace | Primary public surface |
|---|---|
| `persistra` | `Project`, `ProjectMode`, `ProjectOverrides`, version metadata |
| `persistra.domain` | immutable identities, content IDs, time/money/duration primitives, clocks |
| `persistra.catalog` | sources, datasets, revisions, batches, snapshots and ingestion contracts |
| `persistra.reference` | entities, identifiers, calendars, classifications and universes |
| `persistra.market` | canonical market/economic observations, bars and adjustments |
| `persistra.research` | datasets, SQL/workspaces, components, features, labels, alpha and validation |
| `persistra.portfolio` | decision-input safety, signals, forecasts, risk, construction and optimization |
| `persistra.accounting` | books, journal facts, settlements, lots, borrow and actions |
| `persistra.simulation` | vectorized and bounded static event-order simulation |
| `persistra.experiments` | studies, searches, scenarios, worker assignments and outcomes |
| `persistra.results` | normalized run handles, annotations, retention and portable export verification |
| `persistra.analysis` | metrics, attribution, execution, comparison and scenario aggregation |
| `persistra.viz` | deterministic Plotly figure families |
| `persistra.reports` | offline HTML report plans, artifacts and bundle verification |
| `persistra.dashboard` | verified read-only project, backup and portable-export sources |

The exact supported depth of each namespace is listed in the
[implementation status](implementation-status.md). Focused specifications are design
authority, not generated API documentation.
