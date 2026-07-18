# V3 implementation status

The focused specifications describe the complete v3 design. This matrix describes the
implemented and supported surface of the current code. A type, enum value, or migration table
does not by itself make a capability supported.

| Area | Supported now | Explicit boundary |
|---|---|---|
| Projects and databases | Managed project lifecycle, role/mode enforcement, leases, forward migrations, verified backup/copy/restore/fork | One process/thread owns a writable project; no remote database service |
| Catalog and market data | Registration, ingestion, revision/quarantine, snapshots, identifiers, calendars, universes, bars, quotes, trades, actions, fundamentals, estimates, macro, benchmark and rate observations | Provider adapters must pass the conformance kit; no credential storage |
| Research data and safety | Exact-cutoff datasets, bounded SQL/workspaces, registered executable features/labels, persisted decision-input manifests, structural label rejection and typed opaque-input override | Managed operators that lack execution kernels are rejected at registration |
| Alpha and validation | The registered executable alpha metrics; expanding, rolling and combinatorial-purged memberships | Nested selection, a sealed final-holdout capability/contamination ledger and sklearn adapters are unavailable |
| Forecasts | Registered direct finite linear transforms with row state and safety lineage | No fitted estimator, preprocessing pipeline, model selection or forecast combination |
| Risk | Sample, EWMA and fixed-shrinkage covariance with explicit estimate states and PSD policy | No factor model or user-supplied exposure/covariance model |
| Portfolio | Rank signals, equal-weight construction, and convex gross/net/max-weight/risk/turnover optimization | No sector/factor/tracking-error/ADV constraint family, expected-cost model, or multi-strategy allocator |
| Accounting | Immutable double-entry journal, FIFO lots, borrow authorization, settlements, splits, dividends and reconciliation used by the simulators | The complete entitlement/collateral/correction/liquidation design is not yet exposed as one policy surface |
| Vectorized simulation | Deterministic target execution, cash feasibility, normalized publication and declared fidelity findings | Synthetic fills, T0 settlement and no event-order lifecycle |
| Event simulation | Causally timestamped completed-bar observations, predeclared order lifecycle, costs, borrow, T+N market-session settlement proxy, accounting and normalized publication | This is a bounded static bar-order engine, not the focused-spec stateful strategy callback/checkpoint, intrabar clock, margin-liquidation or entitlement engine |
| Experiments | Complete fixed-search planning; seeded random/user-defined; sequential deduplicated Optuna ask/tell; spawned local workers; isolated verified DuckDB handoff; objective/progress/retry/cancel state; typed compatibility reuse; deterministic numeric scenario transforms | Worker callbacks own simulation/analysis invocation; remote workers and general workflow scheduling are out of scope |
| Results and analysis | Common vectorized/event run records and normalized core tables, bounded handles, standard metrics, compact attribution/execution/comparison/scenario summaries, annotations, retention, structured logs and closed exports | Advanced Brinson/factor attribution, statistical inference and the full focused-spec analysis catalog are unavailable |
| Presentation | Deterministic Plotly figures, offline HTML reports/bundles, and verified loopback read-only dashboard sources | No static image/PDF renderer, remote hosting, authentication, upload, arbitrary SQL or dashboard writes |
| Release evidence | Python 3.12–3.14/all-extra CI definitions, isolated-extra and dependency-band jobs, package smoke, strict docs build, unit/integration/contract/property/security-oriented coverage | The formal 24 GiB benchmark result and 90% aggregate coverage gate are not yet satisfied |

Unavailable capabilities fail during definition/request validation where a public request
could otherwise imply support. They must not silently omit rows or downgrade fidelity.

The [assumptions and limitations](assumptions-and-limitations.md) page explains the financial
and temporal consequences of the bounded simulation surfaces. This matrix is
the current operational status and must be updated whenever a boundary changes.
