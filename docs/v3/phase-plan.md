## Phase Branches

1. `v3/01-clean-slate-foundation`
   - Remove all v2 application code, native docs, tests, examples, Parquet fixtures, and obsolete configuration while preserving governance, license, Git history, and `docs/v3`.
   - Establish the Python 3.12+ package, strict tooling, test taxonomy/IDs, fixture generators, coverage ramp, optional-dependency guards, CLI shell, structured errors/logging, and `persistra.errors`.
   - Implement focused spec 01: typed identities, canonical hashing/serialization, UTC time and intervals, injected clocks, fixed-precision values, units, deterministic seeds, and domain events.
   - Exit with a clean installable skeleton and domain round-trip/property tests; never leave a deletion-only broken commit.

2. `v3/02-project-database-catalog`
   - Implement `Project.init/open/inspect/close`, strict immutable TOML configuration, explicit modes/capabilities, managed DuckDB connections, transactions, role-specific schemas, migrations, Linux leases, verified backups/copies/restores, doctor, and operational CLI commands.
   - Add source/dataset registries, batch staging and validation, per-record dispositions, revisions/retractions, quarantine/remediation, catalog roots, market snapshots, and composite snapshots.
   - Cover multiprocess lease conflicts, stale ownership, failure injection, migration backup, atomic batch publication, exact retry, and snapshot stability.
   - Exit with public project APIs capable of safely owning empty and populated managed databases.

3. `v3/03-daily-market-research-foundation`
   - Implement issuer/security/venue/listing/instrument identities, external identifiers, classifications, effective intervals, reviewed calendars, schedules, memberships, and universe evaluation with complete rejection audits.
   - Add daily `BarSpec`, raw unadjusted daily bars, trading status, split/cash-dividend action terms, point-in-time queries, and minimal adjustment support.
   - Add the minimal research-dataset builder: exact instrument-decision grain, dual cutoffs, snapshot binding, cardinality-safe joins, eligibility/missing audits, and structural label exclusion.
   - Exit with deterministic source fixtures producing a pinned daily decision dataset entirely through public APIs.

4. `v3/04-flagship-vectorized-slice`
   - Implement managed returns and momentum, signal semantics, a minimal portfolio constructor, monthly rebalance policy, foundational journal cash/positions/lots, explicit costs, split/dividend handling, and the vectorized simulator.
   - Persist normalized run results and provide initial performance metrics, one Plotly performance figure, and a self-contained HTML report.
   - The evolving flagship starts as a momentum-only vertical here; no notebook-only implementation is allowed.
   - Exit when deterministic fixtures run from ingestion to a pinned report with reconciled accounting and no private API use.

5. `v3/05-canonical-data-temporal-hardening`
   - Complete intraday bars, trades, quotes, trading status, corporate-action/lifecycle schemas, point-in-time and retrospective adjustment policies, and source precedence.
   - Implement filings, raw and normalized fundamentals, estimates/consensus/actuals, macro vintages, benchmark definitions/series/constituents, risk-free curves, and custom dataset contracts.
   - Complete public/project-knowledge cutoffs, revision-specific correction availability, provider conformance, partial quarantine/remediation, safety/licensing propagation, and all canonical dataframe contracts.
   - Exit when later ingestion cannot affect pinned queries and every canonical family passes temporal and ingestion contracts.

6. `v3/06-features-labels-workspaces`
   - Complete research-dataset definitions/builds, entity bridges, temporal joins, missing policies, lineage, immutable publication, bounded result handles, and enriched dataset binding.
   - Implement the unified feature/label DAG, separate physical schemas, bounded Python and SQL execution, managed causal operators, label horizons, temporal-conformance sentinels, exact materialization identity, and the full catalog marked initial or required in focused spec 08.
   - Add parsed DuckDB-compatible read-only SQL using SQLGlot, typed operation contexts, static lineage/safety analysis, immutable workspace versions, resource limits, and cancellation/recovery.
   - Exit with bounded-memory materialization and proof that label, retrospective, or opaque ancestry cannot be laundered through SQL or workspaces.

7. `v3/07-alpha-validation`
   - Implement required alpha diagnostics: coverage, Pearson/Spearman IC, quantiles/spreads, monotonicity, persistence, turnover, decay, autocorrelation, exposure and regime slices, dependence-aware inference, and multiple-testing adjustments.
   - Implement expanding, rolling, purged, embargoed, combinatorial, nested, and terminal-holdout validation over exact closed information intervals.
   - Enforce same-decision panel roles, dependency-derived purge scope, isolated inner selection, one managed clean holdout use, exact retries, and append-only contamination.
   - Exit with a documented label-classified alpha workflow and leakage tests across managed, custom, SQL, workspace, splitter, and sklearn-adapter paths.

8. `v3/08-forecasts-risk-portfolio`
   - Implement typed signals, direct and fitted forecasts, managed preprocessing, fit membership, model selection, row-relative causal release, forecast combination, and point-in-time inference.
   - Add sample/EWMA/shrinkage/user covariance and factor risk models, PSD validation/repair, expected-cost models, constraints, simple constructors, and CVXPY convex optimization through the `optimize` extra.
   - Independently verify every solver result. Solver failure is structured and visible by default; retain-current or simpler fallbacks exist only when explicitly configured and recorded.
   - Implement target/current-state contracts, multi-strategy intent, and rebalance boundaries without producing quantities or orders inside portfolio construction.
   - Exit with long-only and long-short construction scenarios and complete fit/release/solver provenance.

9. `v3/09-accounting-core`
   - Implement the immutable general and memorandum journals, chart of accounts, exact per-commodity double entry, source idempotency, reversal/correction rules, FIFO long/short lots, fill templates, cash flows, fees, and effective-dated settlement.
   - Build pure transition kernels plus managed persistence, projection rebuilding, normalized snapshots, and reconciliation.
   - Cover hand-worked and generated cash, fill, cross-zero, lot, settlement, fee, and correction sequences.
   - Exit when every transaction balances exactly and projections rebuild from the journal.

10. `v3/10-accounting-vectorized-hardening`

- Complete interest/financing accruals, borrow authorization/inventory/fees, margin and liquidation intent, corporate-action entitlements, fractional/cash-in-lieu handling, marks, staleness, NAV, and reconciled `CurrentPortfolioView`.
- Harden vectorized timing, target acquisition, endogenous current state, next-open execution capabilities, cash/borrow feasibility, capacity shortfall, accounting-only events, checkpoints, recovery, and fidelity profiles.
- Integrate the final flagship strategy and verify all portfolio/accounting contracts together.
- Exit with hand-worked and stateful property scenarios reconciling long-only and long-short economics.

1. `v3/11-event-simulation`

- Implement the total event clock and fixed same-timestamp priority contract, availability visibility, stateful callbacks, immutable order transitions, fill progress, cancellation/replacement, all required order types/TIFs, and forced-order ownership.
- Add conservative default OHLC ambiguity, seeded alternatives, causal capacity, partial fills, spread/slippage/delay/impact attribution, shorting, settlement, actions, margin, checkpoint/resume, and complete fidelity output.
- Differentially test vectorized/event economics under the restricted common profile.
- Exit with documented explainable fidelity differences and complete order, fill, event, and journal histories.

1. `v3/12-studies-search-scenarios`

- Implement study/trial/fold/scenario/run/attempt hierarchy; design, execution, attempt, and artifact identities; exact reuse; explicit warned compatibility reuse; retries; resume; and terminal accounting for every plan.
- Add grid, random, custom, and Optuna Bayesian search through the `search` extra, deterministic seed allocation, objective safety, stop/failure policies, scenarios, stress, Monte Carlo, and bootstrap methods.
- Implement read-only leased workers, isolated temporary DuckDB outputs, verified handoff, sole-writer transactional coordination, scheduling-order determinism, and interruption recovery.
- Exit with identical identities and outputs across worker counts, completion order, interruption, and resume where determinism is promised.

1. `v3/13-results-analysis-export`

- Implement verified worker publication, immutable completed-run repositories, bounded ordered query handles, fixed normalized result tables, annotations, logs, archival, and reference-aware deletion.
- Add immutable analysis definitions/attempts/artifacts, the complete `persistra.standard@1` metric catalog, benchmark analysis, attribution, execution/capacity analysis, scenario aggregation, statistical uncertainty, and compatibility-aware comparisons.
- Implement dependency-closed portable DuckDB exports plus versioned Parquet/CSV interoperability, checksum verification, and copy-based upgrade infrastructure.
- Only the final current v3 storage/export format is promised initially; v2 and intermediate pre-release database files are unsupported and disposable.
- Exit when completed runs remain byte/logically unchanged while multiple analyses and exports are produced and independently reopened.

1. `v3/14-presentation-dashboard-release-hardening`

- Complete Plotly figure families, deterministic visual reduction, themes, accessibility and warning states, reusable report sections, self-contained offline HTML, and checksum-closed directory bundles. Static PNG/SVG/PDF output remains deferred behind a clean extension boundary.
- Build the read-only Streamlit prototype and eight required pages using only public result/analysis/viz APIs, short-lived thread-owned read scopes, exact immutable cache keys, loopback defaults, and no telemetry/network/write capability.
- Adopt Streamlit by ADR if the prototype passes its security, accessibility, resource, API, and packaging gates; otherwise revise the bounded adapter/spec and continue.
- Complete provider/component conformance kits, state machines, compatibility and optional-install matrices, docs, recipes, generated examples, package smoke installs, and flagship report.
- Build the exact `persistra.benchmark.daily_equity_5000x20@1` generator, validator, and runbook. Run a scaled smoke benchmark locally. Do not claim the formal 24 GiB gate because the available WSL2 host has only about 16 GB RAM and enabled swap.
- Exit with all implementable 3.0 acceptance criteria satisfied and the sole external release-evidence gap clearly recorded.

## Public Interfaces and Dependency Policy

- Top level exports only `Project`, foundational immutable configuration types, typed exceptions, and version metadata. Domain capabilities remain in clear namespaces: `domain`, `catalog`, `ingestion`, `market`, `research`, `portfolio`, `accounting`, `simulation`, `experiments`, `results`, `analysis`, `viz`, `reports`, and `dashboard`.
- Public APIs are synchronous, require explicit project/service ownership for mutations, expose no raw DuckDB connection, use pandas with explicit versioned columns, and return structured unavailable/failure reasons where absence is a normal research result.
- Exact public names, schemas, reason codes, event names, algorithms, state transitions, and limits in focused specs 01–18 are normative unless revised through the reviewed consistency process.
- Use stdlib TOML and CLI facilities where adequate; use SQLGlot for SQL parsing, Optuna for Bayesian search, CVXPY with open-source solvers for convex optimization, Plotly/Jinja for visualization/reporting, and Streamlit for the gated dashboard prototype.
- Support Linux on CPython 3.12, 3.13, and 3.14; 3.14 is the current stable feature line at planning time. [Python 3.14.6 release](https://www.python.org/downloads/release/python-3146/)
- Start dependency bands on the currently validated major/minor lines: DuckDB 1.5, SQLGlot 30, Optuna 4, CVXPY 1, Plotly 6, Streamlit 1, pandas 3, and `exchange-calendars>=4.13,<5`. Record exact lower/upper bounds in `tests/compatibility/support.toml` after clean minimum/resolved environment validation. Current reference releases include [DuckDB 1.5.4](https://pypi.org/project/duckdb/), [SQLGlot 30.12](https://pypi.org/project/sqlglot/), [Optuna 4.9](https://pypi.org/project/optuna/), [CVXPY 1.9](https://pypi.org/project/cvxpy/), [Plotly 6.9](https://pypi.org/project/plotly/), and [Streamlit 1.59](https://pypi.org/project/streamlit/).
- Dependency groups are `base`, `research`, `search`, `optimize`, `viz`, `dashboard`, `all`, `dev`, and `docs`; `static` remains a guarded, unimplemented extension point. Every optional namespace must import safely without its extra and fail actionably only when invoked.
- The package version remains unchanged until a human explicitly authorizes the separate release/version-bump operation.

## Flagship Strategy

- Final strategy: monthly, long-only US equity multi-factor portfolio using:
  - 12–1 momentum;
  - trailing earnings yield;
  - gross profitability;
  - inverse 63-session realized volatility.
- Each factor uses point-in-time data, documented missing policy, cross-sectional 1st/99th percentile winsorization, sector-relative standardization, and equal 25% composite weight.
- Candidate universe uses point-in-time listing/universe membership, price and history eligibility, and the top 1,000 instruments by lagged 60-session median dollar volume.
- `persistra.flagship_multifactor@1` converts one composite z-score to 2% annual expected excess return and performs benchmark-relative optimization:
  - maximize expected active return minus `5 ×` active variance, modeled transaction cost, and a 20-basis-point turnover penalty;
  - fully invested and long-only;
  - maximum 2% instrument weight;
  - sector active weight within ±3 percentage points;
  - annualized tracking error no greater than 6%;
  - one-way rebalance turnover no greater than 20%;
  - trade size no greater than 10% of lagged 20-session ADV;
  - next-open execution with explicit costs and conservative feasibility.
- Compare against a point-in-time broad US equity total-return benchmark and explicit risk-free series; committed fixtures use deterministic synthetic equivalents.
- Put all numerical assumptions in the versioned Python profile and sensitivity scenarios, never in TOML or notebook-only code. Optimization failure remains visible unless an example explicitly selects and labels a fallback.
- Commit generators and textual/redistributable fixture facts, not generated DuckDB databases or HTML reports.
