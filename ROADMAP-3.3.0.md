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
- [ ] Compare each unchanged legacy identity against the 3.0.2 baseline fixtures.
- [ ] Record an approved mapping for each intentional legacy identity change.
- [ ] Keep accounting balanced in native and reporting views.
- [ ] Update the callable-size baseline after each approved reduction.

## Entry gate

Do not start this roadmap until these conditions hold:

- [ ] Persistra 3.2.0 is tagged and published.
- [ ] The native currency columns exist and carry back-filled USD values.
- [ ] The native opening amount model exists.
- [ ] The benchmark harness records runtime, query count, and peak memory.
- [ ] The 3.0.2 baseline fixtures cover both simulation engines.

## Why the order changed

The first roadmap draft rewrote both simulation engines, then changed their ledgers in a
later branch. Each engine would receive two rewrites.

Persistra 3.1.0 lands the native currency columns additively. A shared ledger branch
writes those columns with current USD behavior. Both engine branches use that boundary.
The currency branch then turns on non-USD behavior.

## Branch sequence

| Wave | Branch | Prerequisites |
| --- | --- | --- |
| 0 | `refactor/3.3-simulation-ledger-boundary` | None |
| 0 | `feat/3.3-vintage-acquisition` | An approved 3.2.0 deferral |
| 1 | `refactor/3.3-vector-simulation` | Simulation ledger boundary |
| 1 | `feat/3.3-event-strategy-engine` | Simulation ledger boundary |
| 1 | `refactor/3.3-large-callables` | None |
| 2 | `feat/3.3-multi-currency-accounting` | Both simulation branches |
| 3 | `docs/3.3-execution-guides` | All implementation branches |
| 4 | `release/3.3.0` | All prior branches |

The vintage branch is conditional. Start it only for work that 3.2.0 assigned to this
exact branch. The two engine branches can proceed together after the shared ledger
boundary merges. Coordinate changes to shared simulation exports and models.

## Wave 0: Shared boundaries and conditional acquisition

### `refactor/3.3-simulation-ledger-boundary`

This branch creates one typed ledger boundary for both simulation engines. It preserves
current USD behavior and writes the native columns that 3.1.0 added.

#### Design decisions

- [ ] Define typed posting commands for fills, fees, settlements, and actions.
- [ ] Define transaction ownership between simulation and accounting.
- [ ] Define reconciliation checkpoints and failure behavior.
- [ ] Define the actual USD compatibility projection.
- [ ] Define native amount and currency requirements.

#### Implementation

- [ ] Add one typed internal ledger interface.
- [ ] Route both simulation engines through the interface.
- [ ] Write native currency columns with current USD values.
- [ ] Keep each USD-specific column equal to the actual USD amount.
- [ ] Keep non-USD requests unavailable.
- [ ] Remove direct private accounting calls from both engines.
- [ ] Lower the private-usage ceiling by the removed suppressions.

#### Tests

- [ ] Compare both engines with the 3.0.2 baseline fixtures.
- [ ] Test each posting command and reconciliation checkpoint.
- [ ] Inject failure at each ledger transaction boundary.
- [ ] Test that native and USD columns agree for current behavior.

#### Exit criteria

- [ ] Both engines use one typed ledger boundary.
- [ ] Current results and identities remain unchanged.
- [ ] No USD-specific column contains a non-USD amount.

### `feat/3.3-vintage-acquisition`

This branch exists only for a provider family that 3.2.0 assigned here.

#### Entry gate

- [ ] The 3.2.0 deferral names this branch and the provider family.
- [ ] The source and license decision is approved.
- [ ] Offline fixtures and credential rules are available.

#### Implementation

- [ ] Complete the assigned scope from `feat/3.2-vintage-acquisition`.
- [ ] Keep unrelated provider families outside this branch.
- [ ] Update the capability registry and deferral register.
- [ ] Move unresolved external work to a named 3.4.0 owner.

#### Exit criteria

- [ ] The assigned provider family has maintained revision-aware acquisition.
- [ ] Each unresolved family has a named 3.4.0 owner.

## Wave 1: Bounded and reactive execution

### `refactor/3.3-vector-simulation`

This branch removes repeated scans and database reads from vectorized simulation. It also
divides the engine into explicit phases.

The method `VectorizedSimulationService._execute` has 520 lines. Inside the decision loop
it calls `_position_map` twice for each decision. It calls the private accounting cash
method once for each decision. It filters the complete weights frame once for each
decision, which costs one full scan for each decision.

#### Design decisions

- [ ] Set runtime, query-count, and peak-memory budgets in the shared harness.
- [ ] Define in-memory state and reconciliation checkpoints.
- [ ] Define persistence batch sizes.
- [ ] Define incremental manifest identity behavior.
- [ ] Define request cardinality limits before input indexing.
- [ ] Record expected memory growth for each indexed input.

#### Implementation

- [ ] Normalize and sort all inputs once.
- [ ] Enforce request limits before complete input indexing.
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
- [ ] Use the shared simulation ledger boundary for each posting.
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
- [ ] Vary each request limit at and above its boundary.
- [ ] Compare results and identities with the 3.0.2 baseline fixtures.
- [ ] Test each reconciliation checkpoint.
- [ ] Inject failure at each persistence boundary.

#### Exit criteria

- [ ] Query count has no repeated state lookup for each decision.
- [ ] Runtime growth meets the recorded complexity budget.
- [ ] Peak memory agrees with the recorded input-size model.
- [ ] Results preserve accounting and identity invariants.
- [ ] No vector simulation callable is longer than 120 lines.

### `feat/3.3-event-strategy-engine`

This branch makes event simulation scalable and reactive. It preserves declarative order
replay as a deterministic mode.

The method `EventSimulationService._execute` has 747 lines. It is the largest function in
the project.

#### Design decisions

- [ ] Define a canonical immutable strategy state and event protocol.
- [ ] Define the command types that a strategy can return.
- [ ] Set limits for orders, bars, instruments, and emitted events.
- [ ] Define equal-timestamp phase order.
- [ ] Define corporate-action entitlement and cash-in-lieu policies.
- [ ] Define strategy failure and cancellation behavior.
- [ ] Define strategy implementation, configuration, state, and seed identities.
- [ ] Define the trust boundary for user Python code.
- [ ] Limit determinism claims to engine ordering and canonical command replay.

#### Implementation

- [ ] Preserve current `OrderSpec` replay behavior as a supported mode.
- [ ] Partition replay orders by instrument and activation timestamp.
- [ ] Use per-instrument cursors or heaps for order activation.
- [ ] Stop scanning every order for every bar.
- [ ] Enforce request limits before execution.
- [ ] Enforce emitted-event limits during execution.
- [ ] Stream ordered bars where practical.
- [ ] Add a stateful strategy protocol.
- [ ] Give strategies immutable market, fill, position, cash, and strategy state.
- [ ] Let strategies return new canonical state and typed commands.
- [ ] Reject state that cannot use canonical serialization.
- [ ] Record the explicit random seed when a strategy uses one.
- [ ] Process market events in one deterministic phase.
- [ ] Apply corporate actions in one deterministic phase.
- [ ] Run strategy decisions in one deterministic phase.
- [ ] Activate orders and generate fills in separate phases.
- [ ] Run accounting and reconciliation in separate phases.
- [ ] Handle splits and dividends.
- [ ] Handle symbol changes and delistings.
- [ ] Handle fractional cash-in-lieu results.
- [ ] Divide the large execution method into typed phases.
- [ ] Use the shared simulation ledger boundary for each posting.
- [ ] Record phase order and strategy identity in results.
- [ ] Record the canonical emitted command stream.
- [ ] Stop same-timestamp feedback when the event limit is reached.

#### Tests

- [ ] Test equal timestamps with deterministic ordering.
- [ ] Test partial fills and rejected orders.
- [ ] Test action and order collisions.
- [ ] Test strategy commands after fills.
- [ ] Test strategy commands after position and cash changes.
- [ ] Test each order, bar, instrument, and event limit.
- [ ] Test replay compatibility with the 3.0.2 baseline fixtures.
- [ ] Test a conforming seeded strategy twice.
- [ ] Test canonical state serialization and rejection.
- [ ] Test seeded strategy behavior.
- [ ] Test the same-timestamp feedback limit.
- [ ] Test deterministic replay of a recorded command stream.
- [ ] Test each supported corporate-action lifecycle.
- [ ] Inject failure at each execution and persistence phase.
- [ ] Benchmark bars and orders independently.

#### Exit criteria

- [ ] Event replay does not scan every order for every bar.
- [ ] Strategies can react to new managed state.
- [ ] Replay mode and recorded command replay remain deterministic.
- [ ] Engine phase ordering remains deterministic for strategy mode.
- [ ] Documentation does not claim to sandbox user Python code.
- [ ] No event simulation callable is longer than 120 lines.

### `refactor/3.3-large-callables`

This work divides the remaining oversized callables outside research, catalog, and
simulation. The 3.2.0 roadmap reduced its named research and catalog targets.

The current inventory contains more callables than the earlier six-item list. Generate
the complete inventory from the 3.2.0 release commit before branch work starts.

#### Design decisions

- [ ] Group inventory entries by ownership area and shared files.
- [ ] Split this work into child branches when ownership areas do not overlap.
- [ ] Add each child branch to the sequence table before implementation.
- [ ] Define the phase contract for each divided callable.
- [ ] Define which callables stay long with a recorded reason.
- [ ] Keep the enforced limit at 120 physical lines.

#### Implementation

- [ ] Run `callable-size-check` against the 3.2.0 release commit.
- [ ] Assign an owner and target branch to each baseline entry.
- [ ] Divide database inspection into topology, ledger, and reporting phases.
- [ ] Divide portfolio construction into planning, solving, and persistence phases.
- [ ] Divide the dashboard run query into loading, shaping, and rendering phases.
- [ ] Divide market ingestion into normalization, validation, and persistence phases.
- [ ] Divide project open into resolution, locking, and service assembly phases.
- [ ] Divide trade application into matching, posting, and reconciliation phases.
- [ ] Divide universe evaluation into selection and classification phases.
- [ ] Review every other callable in the generated inventory.
- [ ] Record an approved exception with reason, owner, and review date.
- [ ] Replace private cross-layer access with typed internal interfaces.
- [ ] Lower the private-usage ceiling by the number of removed suppressions.

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Compare unchanged legacy identities and rows with the baseline fixtures.
- [ ] Test each approved identity mapping.
- [ ] Test that `callable-size-check` fails on a long callable.
- [ ] Test that the public surface did not change.

#### Exit criteria

- [ ] No callable is longer than 120 lines without a recorded exception.
- [ ] Every exception has a reason, owner, and review date.
- [ ] The private-usage ceiling is lower than the 3.2.0 ceiling.
- [ ] Equivalent input preserves behavior and identity.

## Wave 2: Multi-currency behavior

### `feat/3.3-multi-currency-accounting`

This branch turns on multi-currency behavior. Persistra 3.1.0 added the columns. Both
engines already write them through the shared ledger boundary.

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
- [ ] Define deterministic source priority and FX path selection.
- [ ] Define direct, inverse, and multi-leg path rules.
- [ ] Define cycle rejection and deterministic tie handling.
- [ ] Define bid, ask, midpoint, and staleness policies.
- [ ] Define currency precision and rounding at each posting boundary.
- [ ] Define settlement and action conversion times.
- [ ] Define the strict point-in-time FX policy and its data requirement.
- [ ] Require `_usd` fields to contain actual USD values.

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
- [ ] Compute actual USD compatibility values when reporting currency is not USD.
- [ ] Record separate provenance for reporting and USD compatibility conversions.
- [ ] Reject a posting when its necessary reporting or USD path is unavailable.
- [ ] Separate local-asset profit from FX profit.
- [ ] Expose currency exposures.
- [ ] Expose conversion staleness.
- [ ] Reject missing or stale FX paths with typed errors.
- [ ] Prevent non-USD assets from entering unsupported operations.
- [ ] Update accounting reconciliation for each currency.
- [ ] Update result metrics, reports, exports, and dashboard views.
- [ ] Keep each deprecated USD column populated with its actual USD value.
- [ ] Never write a non-USD reporting value into a USD-specific field.

#### Tests

- [ ] Test same-currency and cross-currency trades.
- [ ] Test native-currency dividends.
- [ ] Test fees and commissions in different currencies.
- [ ] Test settlement across currencies.
- [ ] Test splits and cash-in-lieu across currencies.
- [ ] Test cash transfers across currencies.
- [ ] Test direct and multi-leg FX paths.
- [ ] Test inverse paths, path ties, and cycle rejection.
- [ ] Test bid, ask, midpoint, precision, and rounding policies.
- [ ] Test stale and missing FX data.
- [ ] Test point-in-time FX availability.
- [ ] Test local and FX profit decomposition.
- [ ] Test balance by ledger and currency.
- [ ] Test actual USD compatibility values with a non-USD reporting currency.
- [ ] Test that a USD-only project produces 3.0.2 identities.

#### Exit criteria

- [ ] Non-USD assets cannot silently use USD values.
- [ ] Each translated amount contains complete FX provenance.
- [ ] Each USD-specific field contains an actual USD amount.
- [ ] Accounting remains balanced in native and reporting views.
- [ ] A USD-only project keeps its 3.0.2 results and identities.

#### Gated exit criterion

- [ ] Strict point-in-time FX marks use revision-aware data.

Close this criterion only when a vintage acquisition branch shipped a revision-aware FX
source. If that source is absent, register strict point-in-time FX as `unavailable`.
Assign the unavailable capability to a named 3.4.0 owner.

## Wave 3: Documentation

### `docs/3.3-execution-guides`

#### Implementation

- [ ] Add a strategy authoring guide.
- [ ] Document the user Python trust boundary.
- [ ] Limit determinism claims to engine and command replay behavior.
- [ ] Add a currency and FX concept page.
- [ ] Add an FX provenance concept page.
- [ ] Document the equal-timestamp phase order.
- [ ] Document the corporate-action entitlement policy.
- [ ] Document actual USD compatibility-field semantics.
- [ ] Document each recorded performance budget.
- [ ] Extend the quickstart with a strategy example.
- [ ] Republish the generated capability matrix.
- [ ] Publish a machine-readable deprecation manifest.
- [ ] Publish the 4.0.0 deprecation notice.
- [ ] Apply ASD-STE100 controlled language.

#### Tests

- [ ] Validate every Python example.
- [ ] Execute the extended quickstart against an installed wheel.
- [ ] Run strict MkDocs build.

#### Exit criteria

- [ ] A user can write and run a stateful strategy from the guide alone.
- [ ] Every deprecated field carries a documented removal target.
- [ ] No guide describes a non-USD value as a USD compatibility value.

## Wave 4: Release preparation

### `release/3.3.0`

Follow the release procedure in `ROADMAP-3.1.0.md`. Change each version string to 3.3.0.

Confirm that each conditional provider family either merged or has a named 3.4.0 owner.
Confirm that strict point-in-time FX has an executable or unavailable registry status.

## Release acceptance criteria

- [ ] Vectorized simulation avoids repeated state queries for each decision.
- [ ] Event replay avoids a complete order scan for each bar.
- [ ] Strategies can react to fills, positions, and cash.
- [ ] Recorded strategy command streams replay deterministically.
- [ ] Non-USD assets cannot enter USD-only accounting silently.
- [ ] Each translated amount contains complete FX provenance.
- [ ] Each USD-specific field contains an actual USD amount.
- [ ] A USD-only project keeps its 3.0.2 results and identities.
- [ ] No callable is longer than 120 lines without a recorded exception.
- [ ] Each callable exception has a reason, owner, and review date.
- [ ] Every changed execution path has a recorded benchmark measurement.
- [ ] The private-usage ceiling is lower than the 3.2.0 ceiling.

## Evidence

Record release evidence at `docs/releases/3.3.0-evidence.md`. Use the artifact list from
`ROADMAP-3.1.0.md`. Add these artifacts:

- [ ] The simulation benchmark measurements for each varied dimension.
- [ ] The query-count measurements for both engines.
- [ ] The accounting balance report for each tested currency.
- [ ] The FX provenance sample for a cross-currency trade.
- [ ] The actual USD compatibility sample for a non-USD report.
- [ ] The recorded strategy command replay sample.
- [ ] The callable-size exception report.

## Risks

| Risk | Effect | Response |
| --- | --- | --- |
| FX mark plumbing needs a new relation | The currency branch grows | Resolve the design decision before code starts |
| Engine rewrites change identities | Baseline comparison fails | Treat any identity change as a defect until reviewed |
| User Python reads external state | Strategy output changes between runs | Guarantee only engine ordering and command replay |
| Benchmarks regress on new hardware | Budgets look breached | Rebase budgets once and record the reason |
| Revision-aware FX never arrives | Strict point-in-time FX cannot ship | Register it as unavailable with a 3.4.0 owner |
| USD fields receive reporting values | Stored data has false currency labels | Require actual USD conversion and provenance |

## Finding traceability

| Review finding | Priority | Size | Confidence | Owning branch |
| --- | --- | --- | --- | --- |
| Vectorized simulation scans | P1 | XL | Medium | `refactor/3.3-vector-simulation` |
| Static event simulation | P1 | XL | Low | `feat/3.3-event-strategy-engine` |
| USD accounting boundary | P1 | XL | Medium | `feat/3.3-multi-currency-accounting` |
| Shared simulation ledger access | P1 | M | High | `refactor/3.3-simulation-ledger-boundary` |
| Remaining large callables | P2 | L | High | `refactor/3.3-large-callables` |
| Execution documentation gaps | P2 | M | High | `docs/3.3-execution-guides` |

## Deferral register

Add a row for each capability that remains unavailable at release time.
Create `ROADMAP-3.4.0.md` before approving either 3.4.0 row.

| Finding | Target release | Owning branch | Condition |
| --- | --- | --- | --- |
| Strict point-in-time FX | 3.4.0 | `feat/3.4-vintage-acquisition` | No revision-aware FX source shipped |
| Blocked provider families | 3.4.0 | `feat/3.4-vintage-acquisition` | The named 3.3.0 family remains blocked |
| USD field removal | 4.0.0 | `release/4.0.0` | The removal rule passes |

## Persistra 4.0.0 plan

Persistra 4.0.0 removes what the 3.x line deprecated. It adds no new capability.

### Removal rule

A public element is removable only when all of these conditions hold:

- [ ] The element carried a deprecated or unavailable status for two minor releases.
- [ ] The capability matrix or deprecation manifest showed that status.
- [ ] A replacement exists and has documentation.
- [ ] Each serialized value has a migration or a retained compatibility tombstone.
- [ ] The changelog announced the removal target.

### Planned removals

| Element | Deprecated in | Replacement |
| --- | --- | --- |
| The `cash_usd` column | 3.1.0 | Native cash columns |
| The `signed_cash_usd` column | 3.1.0 | Native signed cash columns |
| The `opening_cash_usd` field | 3.1.0 | A native opening amount |

Unavailable enum members remain unless a replacement and serialized migration both
exist. A typed capability error alone is not a replacement.

### Planned work

- [ ] Remove each deprecated column and add the migration.
- [ ] Remove each deprecated model field.
- [ ] Review each unavailable enum member against the removal rule.
- [ ] Keep a compatibility tombstone when no safe serialized migration exists.
- [ ] Raise the minimum supported Python version if the support policy allows it.
- [ ] Publish a 3.3 to 4.0 migration guide.
- [ ] Test migration from a 3.3.0 baseline project.
- [ ] Test every serialized migration and compatibility tombstone.

Callable-size exceptions are internal maintenance items. Remove them when their
refactors pass. Do not wait for a major release.

### Open question for 4.0.0

The removal of `cash_usd` changes stored identities for projects that keep USD data. The
release must choose one of two paths. Either it preserves identities through a
compatibility hash, or it declares an identity break and documents the effect. Resolve
this in the 4.0.0 interview.

## Completion rule

Persistra 3.3.0 is ready only when every release acceptance criterion has recorded
evidence. A version change alone does not make the release ready.
