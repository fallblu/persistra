# Persistra 3.3.0 roadmap

## Purpose

This roadmap defines the work for Persistra 3.3.0. The theme is execution and currency.

This roadmap also contains the plan for Persistra 4.0.0.

The final section lists the breaking removals that the earlier releases defer.

This roadmap starts from `develop` after the `release/3.2.0` merge.

## Inherited rules

This roadmap inherits these sections from `ROADMAP-3.1.0.md`:

- The release principles.
- The capability deferral rule.
- The branch rules.
- The verification gate.

## Additional branch rules

- [ ] Add user-facing changes to the 3.3.0 section of `CHANGELOG.md`.
- [ ] Record a benchmark measurement for each changed execution path.
- [ ] Compare each identity against the 3.0.2 baseline fixtures.
- [ ] Keep accounting balanced in native and reporting views.

## Entry gate

Do not start this roadmap until these conditions hold:

- [ ] Persistra 3.2.0 is tagged and published.
- [ ] The native currency columns exist and carry back-filled USD values.
- [ ] The benchmark harness records runtime, query count, and peak memory.
- [ ] The 3.0.2 baseline fixtures cover both simulation engines.

## Why the order changed

The first roadmap draft rewrote both simulation engines, then changed their ledgers in a
later branch. Each engine would receive two rewrites.

Persistra 3.1.0 lands the native currency columns additively. Both engine branches in
this roadmap therefore write native ledgers from the start. The currency branch then
turns on non-USD behavior. Each engine receives one rewrite.

## Branch sequence

| Wave | Branch | Prerequisites |
| --- | --- | --- |
| 1 | `refactor/3.3-vector-simulation` | None |
| 1 | `feat/3.3-event-strategy-engine` | None |
| 1 | `refactor/3.3-large-methods` | None |
| 2 | `feat/3.3-multi-currency-accounting` | Both simulation branches |
| 3 | `docs/3.3-execution-guides` | All implementation branches |
| 4 | `release/3.3.0` | All prior branches |

The two engine branches touch different modules. They can proceed together.

## Wave 1: Bounded and reactive execution

### `refactor/3.3-vector-simulation`

This branch removes repeated scans and database reads from vectorized simulation. It also
divides the engine into explicit phases.

The method `VectorizedSimulationService._execute` has 519 lines. Inside the decision loop
it calls `_position_map` twice for each decision. It calls the private accounting cash
method once for each decision. It filters the complete weights frame once for each
decision, which costs one full scan for each decision.

#### Design decisions

- [ ] Set runtime, query-count, and peak-memory budgets in the shared harness.
- [ ] Define in-memory state and reconciliation checkpoints.
- [ ] Define persistence batch sizes.
- [ ] Define incremental manifest identity behavior.
- [ ] Define the native ledger write path for each posting.

#### Implementation

- [ ] Normalize and sort all inputs once.
- [ ] Index weights by decision timestamp.
- [ ] Index bars by instrument and timestamp.
- [ ] Add direct next-bar lookup.
- [ ] Index corporate actions by effective timestamp and instrument.
- [ ] Index corporate-action legs with their actions.
- [ ] Maintain cash in memory during execution.
- [ ] Maintain positions in memory during execution.
- [ ] Maintain cumulative fills and pending state in memory.
- [ ] Remove repeated position and cash queries from the decision loop.
- [ ] Remove cumulative fill rescans.
- [ ] Remove full bar filters from capacity calculation.
- [ ] Reconcile in-memory state at explicit checkpoints.
- [ ] Batch fills, postings, positions, and metrics.
- [ ] Compute manifest identities as batches become final.
- [ ] Divide execution into planning, market, accounting, and persistence phases.
- [ ] Write native currency columns for each posting.
- [ ] Keep the public simulation API simple.
- [ ] Replace private accounting access with a typed internal interface.
- [ ] Lower the private-usage ceiling by the number of removed suppressions.

#### Tests

- [ ] Vary decisions while other benchmark dimensions remain fixed.
- [ ] Vary instruments while other benchmark dimensions remain fixed.
- [ ] Vary orders while other benchmark dimensions remain fixed.
- [ ] Vary bar density while other benchmark dimensions remain fixed.
- [ ] Measure database query count.
- [ ] Measure peak memory.
- [ ] Measure runtime growth.
- [ ] Compare results and identities with the 3.0.2 baseline fixtures.
- [ ] Test each reconciliation checkpoint.
- [ ] Inject failure at each persistence boundary.

#### Exit criteria

- [ ] Query count has no repeated state lookup for each decision.
- [ ] Runtime growth meets the recorded complexity budget.
- [ ] Results preserve accounting and identity invariants.
- [ ] No simulation method is longer than 120 lines.

### `feat/3.3-event-strategy-engine`

This branch makes event simulation scalable and reactive. It preserves declarative order
replay as a deterministic mode.

The method `EventSimulationService._execute` has 746 lines. It is the largest function in
the project.

#### Design decisions

- [ ] Define the immutable strategy state and event protocol.
- [ ] Define the command types that a strategy can return.
- [ ] Set limits for orders, bars, instruments, and emitted events.
- [ ] Define equal-timestamp phase order.
- [ ] Define corporate-action entitlement and cash-in-lieu policies.
- [ ] Define strategy failure and cancellation behavior.
- [ ] Define the native ledger write path for each fill and action.

#### Implementation

- [ ] Preserve current `OrderSpec` replay behavior as a supported mode.
- [ ] Partition replay orders by instrument and activation timestamp.
- [ ] Use per-instrument cursors or heaps for order activation.
- [ ] Stop scanning every order for every bar.
- [ ] Enforce request limits before execution.
- [ ] Enforce emitted-event limits during execution.
- [ ] Stream ordered bars where practical.
- [ ] Add a stateful strategy protocol.
- [ ] Give strategies immutable market, fill, position, and cash state.
- [ ] Let strategies return typed commands.
- [ ] Process market events in one deterministic phase.
- [ ] Apply corporate actions in one deterministic phase.
- [ ] Run strategy decisions in one deterministic phase.
- [ ] Activate orders and generate fills in separate phases.
- [ ] Run accounting and reconciliation in separate phases.
- [ ] Handle splits and dividends.
- [ ] Handle symbol changes and delistings.
- [ ] Handle fractional cash-in-lieu results.
- [ ] Divide the large execution method into typed phases.
- [ ] Write native currency columns for each posting.
- [ ] Record phase order and strategy identity in results.

#### Tests

- [ ] Test equal timestamps with deterministic ordering.
- [ ] Test partial fills and rejected orders.
- [ ] Test action and order collisions.
- [ ] Test strategy commands after fills.
- [ ] Test strategy commands after position and cash changes.
- [ ] Test each order, bar, instrument, and event limit.
- [ ] Test replay compatibility with the 3.0.2 baseline fixtures.
- [ ] Test deterministic strategy replay.
- [ ] Test each supported corporate-action lifecycle.
- [ ] Inject failure at each execution and persistence phase.
- [ ] Benchmark bars and orders independently.

#### Exit criteria

- [ ] Event replay does not scan every order for every bar.
- [ ] Strategies can react to new managed state.
- [ ] Replay and strategy modes remain deterministic.
- [ ] No event simulation method is longer than 120 lines.

### `refactor/3.3-large-methods`

This branch divides the remaining oversized methods outside research, catalog, and
simulation. The 3.2.0 roadmap closed the research and catalog packages.

The method `inspect_database` has 260 lines. The method
`PortfolioConstructionService.construct` has 210 lines. The method `_query_run` has 199
lines. The method `MarketDataService.ingest` has 194 lines. The method `Project.open` has
179 lines. The method `_apply_trade` has 179 lines.

#### Design decisions

- [ ] Define the phase contract for each divided method.
- [ ] Define which methods stay long with a recorded reason.
- [ ] Define the enforced method length limit.

#### Implementation

- [ ] Divide database inspection into topology, ledger, and reporting phases.
- [ ] Divide portfolio construction into planning, solving, and persistence phases.
- [ ] Divide the dashboard run query into loading, shaping, and rendering phases.
- [ ] Divide market ingestion into normalization, validation, and persistence phases.
- [ ] Divide project open into resolution, locking, and service assembly phases.
- [ ] Divide trade application into matching, posting, and reconciliation phases.
- [ ] Divide universe evaluation into selection and classification phases.
- [ ] Add a lint rule that fails on a method longer than 120 lines.
- [ ] Record an approved exception list for the lint rule.
- [ ] Replace private cross-layer access with typed internal interfaces.
- [ ] Lower the private-usage ceiling by the number of removed suppressions.

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Compare identities and rows with the 3.0.2 baseline fixtures.
- [ ] Test that the lint rule fails on a long method.
- [ ] Test that the public surface did not change.

#### Exit criteria

- [ ] No method is longer than 120 lines without a recorded exception.
- [ ] The private-usage ceiling is lower than the 3.2.0 ceiling.
- [ ] Equivalent input preserves behavior and identity.

## Wave 2: Multi-currency behavior

### `feat/3.3-multi-currency-accounting`

This branch turns on multi-currency behavior. Persistra 3.1.0 added the columns. Both
engines already write them.

#### Why this branch does not depend on vintage acquisition

The first roadmap draft made this branch depend on vintage acquisition. That dependency
is not necessary. Spot FX pairs already ingest through the Alpha Vantage adapter. The
asset class `AssetClass.FX` and the pair instrument model both exist.

Only one exit criterion needs revision-aware data. That criterion is strict point-in-time
FX. Gate that criterion alone. Do not gate the branch.

#### The FX mark plumbing problem

Simulation and accounting reject pair instruments today. Spot FX pair bars are the only
first-party FX source. The branch must therefore define how a rate reaches the ledger.

This design decision was absent from the first roadmap draft. Resolve it in the interview
before code starts.

#### Design decisions

- [ ] Define reporting-currency configuration and USD compatibility behavior.
- [ ] Define how a spot FX pair bar becomes an accounting FX mark.
- [ ] Decide whether accounting admits pair instruments or reads a separate rate relation.
- [ ] Define FX path selection and staleness policy.
- [ ] Define settlement and action conversion times.
- [ ] Define the strict point-in-time FX policy and its data requirement.

#### Implementation

- [ ] Accept a reporting currency other than USD in portfolio configuration.
- [ ] Accept a reporting currency other than USD in simulation configuration.
- [ ] Replace internal USD assumptions with currency-aware values.
- [ ] Maintain cash ledgers by native currency.
- [ ] Record native trade, fee, settlement, dividend, and action amounts.
- [ ] Add the FX mark source that the design decision selected.
- [ ] Resolve FX marks at the correct availability cutoff.
- [ ] Record FX rate identity and timestamp.
- [ ] Record the complete FX conversion path.
- [ ] Record native and reporting values.
- [ ] Separate local-asset profit from FX profit.
- [ ] Expose currency exposures.
- [ ] Expose conversion staleness.
- [ ] Reject missing or stale FX paths with typed errors.
- [ ] Prevent non-USD assets from entering unsupported operations.
- [ ] Update accounting reconciliation for each currency.
- [ ] Update result metrics, reports, exports, and dashboard views.
- [ ] Keep the deprecated USD columns populated for the reporting currency.

#### Tests

- [ ] Test same-currency and cross-currency trades.
- [ ] Test native-currency dividends.
- [ ] Test fees and commissions in different currencies.
- [ ] Test settlement across currencies.
- [ ] Test splits and cash-in-lieu across currencies.
- [ ] Test cash transfers across currencies.
- [ ] Test direct and multi-leg FX paths.
- [ ] Test stale and missing FX data.
- [ ] Test point-in-time FX availability.
- [ ] Test local and FX profit decomposition.
- [ ] Test balance by ledger and currency.
- [ ] Test that a USD-only project produces 3.0.2 identities.

#### Exit criteria

- [ ] Non-USD assets cannot silently use USD values.
- [ ] Each translated amount contains complete FX provenance.
- [ ] Accounting remains balanced in native and reporting views.
- [ ] A USD-only project keeps its 3.0.2 results and identities.

#### Gated exit criterion

- [ ] Strict point-in-time FX marks use revision-aware data.

Close this criterion only when `feat/3.2-vintage-acquisition` shipped a revision-aware FX
source. If that source is absent, register strict point-in-time FX as `unavailable` under
the deferral rule.

## Wave 3: Documentation

### `docs/3.3-execution-guides`

#### Implementation

- [ ] Add a strategy authoring guide.
- [ ] Add a currency and FX concept page.
- [ ] Add an FX provenance concept page.
- [ ] Document the equal-timestamp phase order.
- [ ] Document the corporate-action entitlement policy.
- [ ] Document each recorded performance budget.
- [ ] Extend the quickstart with a strategy example.
- [ ] Republish the generated capability matrix.
- [ ] Publish the 4.0.0 deprecation notice.
- [ ] Apply ASD-STE100 controlled language.

#### Tests

- [ ] Validate every Python example.
- [ ] Execute the extended quickstart against an installed wheel.
- [ ] Run strict MkDocs build.

#### Exit criteria

- [ ] A user can write and run a stateful strategy from the guide alone.
- [ ] Every deprecated field carries a documented removal target.

## Wave 4: Release preparation

### `release/3.3.0`

Follow the release procedure in `ROADMAP-3.1.0.md`. Change each version string to 3.3.0.

## Release acceptance criteria

- [ ] Vectorized simulation avoids repeated state queries for each decision.
- [ ] Event replay avoids a complete order scan for each bar.
- [ ] Strategies can react to fills, positions, and cash.
- [ ] Non-USD assets cannot enter USD-only accounting silently.
- [ ] Each translated amount contains complete FX provenance.
- [ ] A USD-only project keeps its 3.0.2 results and identities.
- [ ] No method is longer than 120 lines without a recorded exception.
- [ ] Every changed execution path has a recorded benchmark measurement.
- [ ] The private-usage ceiling is lower than the 3.2.0 ceiling.

## Evidence

Record release evidence at `docs/releases/3.3.0-evidence.md`. Use the artifact list from
`ROADMAP-3.1.0.md`. Add these artifacts:

- [ ] The simulation benchmark measurements for each varied dimension.
- [ ] The query-count measurements for both engines.
- [ ] The accounting balance report for each tested currency.
- [ ] The FX provenance sample for a cross-currency trade.

## Risks

| Risk | Effect | Response |
| --- | --- | --- |
| FX mark plumbing needs a new relation | The currency branch grows | Resolve the design decision before code starts |
| Engine rewrites change identities | Baseline comparison fails | Treat any identity change as a defect until reviewed |
| Strategy protocol design needs iteration | The event branch slips | Ship replay improvements first and strategies second |
| Benchmarks regress on new hardware | Budgets look breached | Rebase budgets once and record the reason |
| Revision-aware FX never arrives | Strict point-in-time FX cannot ship | Register the capability as unavailable |

## Finding traceability

| Review finding | Priority | Size | Confidence | Owning branch |
| --- | --- | --- | --- | --- |
| Vectorized simulation scans | P1 | XL | Medium | `refactor/3.3-vector-simulation` |
| Static event simulation | P1 | XL | Low | `feat/3.3-event-strategy-engine` |
| USD accounting boundary | P1 | XL | Medium | `feat/3.3-multi-currency-accounting` |
| Remaining large methods | P2 | L | High | `refactor/3.3-large-methods` |
| Execution documentation gaps | P2 | M | High | `docs/3.3-execution-guides` |

## Persistra 4.0.0 plan

Persistra 4.0.0 removes what the 3.x line deprecated. It adds no new capability.

### Removal rule

A public element is removable only when all of these conditions hold:

- [ ] The element carried a deprecated or unavailable status for two minor releases.
- [ ] The published capability matrix showed that status.
- [ ] A replacement exists and has documentation.
- [ ] The changelog announced the removal target.

### Planned removals

| Element | Deprecated in | Replacement |
| --- | --- | --- |
| The `cash_usd` column | 3.1.0 | Native cash columns |
| The `signed_cash_usd` column | 3.1.0 | Native signed cash columns |
| The `opening_cash_usd` field | 3.1.0 | A native opening amount |
| Enum members still unavailable after 3.3.0 | 3.1.0 | A typed capability error |
| Any lint exception left in the length list | 3.3.0 | A divided method |

### Planned work

- [ ] Remove each deprecated column and add the migration.
- [ ] Remove each deprecated model field.
- [ ] Remove each enum member that never became executable.
- [ ] Raise the minimum supported Python version if the support policy allows it.
- [ ] Publish a 3.3 to 4.0 migration guide.
- [ ] Test migration from a 3.3.0 baseline project.

### Open question for 4.0.0

The removal of `cash_usd` changes stored identities for projects that keep USD data. The
release must choose one of two paths. Either it preserves identities through a
compatibility hash, or it declares an identity break and documents the effect. Resolve
this in the 4.0.0 interview.

## Completion rule

Persistra 3.3.0 is ready only when every release acceptance criterion has recorded
evidence. A version change alone does not make the release ready.
