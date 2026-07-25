# Persistra 3.2.0 roadmap

## Purpose

This roadmap defines the work for Persistra 3.2.0. The theme is research depth.

Persistra 3.1.0 makes the public contract honest. Every research capability that cannot
execute becomes a registry entry with a typed error and a target release. This roadmap
implements those capabilities and the governance around them.

This roadmap starts from `develop` after the `release/3.1.0` merge.

## Inherited rules

This roadmap inherits these sections from `ROADMAP-3.1.0.md`:

- The release principles.
- The capability deferral rule.
- The branch rules.
- The verification gate.

Read those sections before work starts. This document records only the changes and
additions.

## Additional branch rules

- [ ] Add user-facing changes to the 3.2.0 section of `CHANGELOG.md`.
- [ ] Change a registry entry to `stable` only after its capability tests pass.
- [ ] Compare each unchanged legacy path against the 3.0.2 baseline fixtures.
- [ ] Record an approved mapping for each intentional legacy identity change.
- [ ] Record a numerical reference for each new formula.
- [ ] Update the callable-size baseline after each approved reduction.

## Entry gate

Do not start this roadmap until these conditions hold:

- [ ] Persistra 3.1.0 is tagged and published.
- [ ] The capability registry controls validation and documentation status.
- [ ] The benchmark harness records runtime, query count, and peak memory.
- [ ] The 3.0.2 baseline fixtures exist and pass in CI.
- [ ] Streaming readers keep peak memory flat as relation size increases.

## Branch sequence

| Wave | Branch | Prerequisites |
| --- | --- | --- |
| 1 | `refactor/3.2-research-workflows` | None |
| 1 | `refactor/3.2-catalog-decomposition` | None |
| 2 | `feat/3.2-feature-sql-relations` | Research workflows |
| 2 | `feat/3.2-managed-operators` | Research workflows |
| 2 | `feat/3.2-alpha-metrics` | Research workflows |
| 2 | `feat/3.2-nested-validation` | Research workflows |
| 2 | `docs/3.2-vintage-source-decision` | Catalog decomposition |
| 3 | `feat/3.2-vintage-acquisition` | Approved source decision |
| 3 | `feat/3.2-final-holdouts` | Nested validation |
| 4 | `docs/3.2-research-guides` | All implementation branches |
| 5 | `release/3.2.0` | All prior branches |

The two wave 1 branches touch different modules. They can proceed together.
The four research capability branches have separate public contracts and tests.

## Wave 1: Maintainable research and catalog execution

### `refactor/3.2-research-workflows`

This branch divides large research workflows into explicit phases. It must preserve
public behavior before later capability work starts.

The current callable inventory contains four primary workflow targets. They are analysis
calculation, component materialization, dataset enrichment, and dataset construction.
The inventory also records nested callables separately.

#### Design decisions

- [ ] Define typed inputs and outputs for each phase.
- [ ] Define transaction ownership across phase boundaries.
- [ ] Define shared temporal-boundary and manifest services.
- [ ] Select failure-injection points.
- [ ] Confirm the qualified callable names from `callable-size-check`.

#### Implementation

- [ ] Divide analysis into validation, loading, calculation, and persistence phases.
- [ ] Divide component materialization into planning, execution, identity, and persistence phases.
- [ ] Divide dataset enrichment into planning, resolution, mutation, and finalization phases.
- [ ] Keep one simple public orchestration entry point for each workflow.
- [ ] Isolate pure planning from storage mutation.
- [ ] Replace large nested closures with one transaction coordinator.
- [ ] Centralize temporal-boundary enforcement.
- [ ] Centralize manifest creation.
- [ ] Give each phase a typed immutable contract.
- [ ] Preserve current content identities for equivalent input.
- [ ] Preserve current database output for equivalent input.
- [ ] Replace private cross-layer access with typed internal interfaces.
- [ ] Lower the private-usage ceiling by the number of removed suppressions.
- [ ] Reduce each named callable to 120 physical lines or less.
- [ ] Update the callable-size baseline without adding an exception.

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Add integration tests for each orchestration entry point.
- [ ] Inject failure at each phase boundary.
- [ ] Test rollback and retry after each injected failure.
- [ ] Compare identities and rows with the 3.0.2 baseline fixtures.
- [ ] Test each intentional identity change against its approved mapping.

#### Exit criteria

- [ ] Each named phase has direct deterministic tests.
- [ ] Storage mutation has one clear transaction owner.
- [ ] Equivalent input preserves behavior and identity.
- [ ] Each named workflow callable is 120 physical lines or less.
- [ ] No callable-size baseline entry grows.

### `refactor/3.2-catalog-decomposition`

This branch divides catalog ingestion into explicit phases. The first roadmap draft named
only the commit method. Three more methods in the same module need the same treatment.

The module `catalog/services.py` has 3,359 lines. The callable inventory records commit,
validation, staging, and snapshot material selection as the primary targets. It also
records their nested transaction callables.

#### Design decisions

- [ ] Define the module split for the catalog package.
- [ ] Define typed inputs and outputs for each ingestion phase.
- [ ] Define transaction ownership across phase boundaries.
- [ ] Define the precedence and revision service boundaries.
- [ ] Confirm every catalog baseline entry from `callable-size-check`.

#### Implementation

- [ ] Divide ingestion commit into planning, normalization, mutation, and finalization phases.
- [ ] Divide ingestion validation into structural, temporal, and precedence phases.
- [ ] Divide staging into resolution, transformation, and persistence phases.
- [ ] Divide snapshot material selection into planning and execution phases.
- [ ] Split `catalog/services.py` into ingestion, validation, and snapshot modules.
- [ ] Keep the current public catalog service surface unchanged.
- [ ] Isolate pure planning from storage mutation.
- [ ] Give each phase a typed immutable contract.
- [ ] Preserve current content identities for equivalent input.
- [ ] Replace private cross-layer access with typed internal interfaces.
- [ ] Lower the private-usage ceiling by the number of removed suppressions.
- [ ] Reduce each named callable to 120 physical lines or less.
- [ ] Reduce or document each other catalog baseline entry.

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Inject failure at each phase boundary.
- [ ] Test rollback and retry after each injected failure.
- [ ] Compare identities and rows with the 3.0.2 baseline fixtures.
- [ ] Test that the public catalog surface did not change.

#### Exit criteria

- [ ] Each primary catalog callable is 120 physical lines or less.
- [ ] No catalog module is longer than 1,200 lines.
- [ ] Each remaining catalog exception has a recorded reason and owner.
- [ ] Equivalent input preserves behavior and identity.

## Wave 2: Declared capabilities and real vintages

Nineteen of thirty-five `ManagedOperator` values execute today. Five of twelve
`AlphaMetricKind` values execute today. The value `ValidationSchemeKind.NESTED` raises at
construction. The variant `FeatureSqlRelation` has no resolver.

### `feat/3.2-feature-sql-relations`

This branch adds the missing managed resolver for `FeatureSqlRelation`.

#### Design decisions

- [ ] Define feature dependency and materialization behavior.
- [ ] Define feature and label relation compatibility.
- [ ] Define ancestry and safety folding for feature dependencies.

#### Implementation

- [ ] Resolve `FeatureSqlRelation` dependencies.
- [ ] Execute feature relations in materialized SQL reads.
- [ ] Execute feature relations in streaming SQL reads.
- [ ] Apply the same limits as other SQL relations.
- [ ] Apply the same function allowlist as other SQL relations.
- [ ] Record feature ancestry in SQL result provenance.
- [ ] Change the registry entry only after public execution passes.

#### Tests

- [ ] Test feature SQL limits and ancestry.
- [ ] Test materialized and streaming reads.
- [ ] Test request-time rejection before the registry change.
- [ ] Test execution through the public SQL service.

#### Exit criteria

- [ ] Feature SQL relations resolve through each supported read path.
- [ ] Feature ancestry participates in the safety result.
- [ ] The registry and executable tests agree.

### `feat/3.2-managed-operators`

This branch implements the sixteen unavailable managed operators.

#### Design decisions

- [ ] Specify formulas, units, missing-data rules, and minimum samples.
- [ ] Specify lookback, availability, and leakage rules for each operator.
- [ ] Specify tie handling for label operators.
- [ ] Select the reference implementation for each numerical check.
- [ ] Define memory growth against window, cross-section, and output size.

#### Implementation

- [ ] Implement `AMIHUD_ILLIQUIDITY`.
- [ ] Implement `DOWNSIDE_DEVIATION`.
- [ ] Implement `ESTIMATE_DISPERSION`.
- [ ] Implement `EVENT_RETURN`.
- [ ] Implement `EXPECTED_SHORTFALL`.
- [ ] Implement `MAXIMUM_ADVERSE_EXCURSION`.
- [ ] Implement `MAXIMUM_FAVORABLE_EXCURSION`.
- [ ] Implement `REGIME_THRESHOLD`.
- [ ] Implement `RETURN_SKEWNESS`.
- [ ] Implement `ROLLING_BETA`.
- [ ] Implement `ROLLING_CORRELATION`.
- [ ] Implement `ROLLING_COVARIANCE`.
- [ ] Implement `TRADE_ACTIVITY`.
- [ ] Implement `TRIPLE_BARRIER`.
- [ ] Implement `TURNOVER`.
- [ ] Implement `VOLUME_ACTIVITY`.
- [ ] Change each registry entry only after its public execution test passes.

#### Tests

- [ ] Add a numerical reference test for each operator.
- [ ] Add a temporal cutoff property for each applicable operator.
- [ ] Add formula-specific scaling or invariance properties.
- [ ] Test missing, constant, sparse, and short input.
- [ ] Test each operator through its public service.
- [ ] Measure memory against each applicable input dimension.

#### Exit criteria

- [ ] Each stable operator has documented numerical and temporal semantics.
- [ ] Each stable operator agrees with an independent numerical reference.
- [ ] Each memory result agrees with its recorded complexity model.

### `feat/3.2-alpha-metrics`

This branch implements the seven unavailable alpha metrics.

#### Design decisions

- [ ] Specify formulas, units, missing-data rules, and minimum samples.
- [ ] Specify tie handling for exposure and rank diagnostics.
- [ ] Select the reference implementation for each numerical check.
- [ ] Define memory growth against rows, groups, and output size.

#### Implementation

- [ ] Implement `AUTOCORRELATION`.
- [ ] Implement `CATEGORICAL_EXPOSURE`.
- [ ] Implement `DECAY`.
- [ ] Implement `JOINT_EXPOSURE`.
- [ ] Implement `NUMERIC_EXPOSURE`.
- [ ] Implement `PERSISTENCE`.
- [ ] Implement `TURNOVER`.
- [ ] Change each registry entry only after its public execution test passes.

#### Tests

- [ ] Add a numerical reference test for each alpha metric.
- [ ] Add formula-specific scaling or invariance properties.
- [ ] Test missing, constant, sparse, and short input.
- [ ] Test each metric through its public service.
- [ ] Measure memory against each applicable input dimension.

#### Exit criteria

- [ ] Each stable alpha metric has documented numerical semantics.
- [ ] Each stable alpha metric agrees with an independent numerical reference.
- [ ] Each memory result agrees with its recorded complexity model.

### `feat/3.2-nested-validation`

This branch adds public nested validation assembly and fold isolation.

#### Design decisions

- [ ] Define nested validation assembly and identity rules.
- [ ] Define outer and inner plan ownership.
- [ ] Define selection-result handoff between validation levels.
- [ ] Define failure behavior for incomplete child plans.

#### Implementation

- [ ] Implement `ValidationSchemeKind.NESTED` construction.
- [ ] Add a public nested validation assembly API.
- [ ] Preserve outer and inner fold ancestry.
- [ ] Enforce purging and embargo rules at both levels.
- [ ] Prevent inner selection data from reaching outer evaluation.
- [ ] Change the registry entry only after public assembly passes.

#### Tests

- [ ] Test nested fold isolation and identity.
- [ ] Test purging and embargo at both levels.
- [ ] Test incomplete, overlapping, and empty child plans.
- [ ] Test public construction and execution.

#### Exit criteria

- [ ] Nested validation uses real parent and child plans.
- [ ] Inner selection data cannot reach outer evaluation.
- [ ] The registry and executable tests agree.

### `docs/3.2-vintage-source-decision`

This branch selects maintained sources before adapter implementation starts.

#### Design decisions

- [ ] Select at least one revision-aware provider.
- [ ] Review provider licenses and redistribution limits.
- [ ] Define credential and offline-test requirements.
- [ ] Select maintained data families for 3.2.0.
- [ ] Define strict point-in-time adapter requirements.
- [ ] Define a decision date for each provider family.
- [ ] Name a 3.3.0 carry-forward branch for each approved deferral.
- [ ] Use 3.4.0 when no 3.3.0 branch can own the work.
- [ ] Create `ROADMAP-3.4.0.md` before approving a 3.4.0 deferral.

#### Exit criteria

- [ ] Each selected source has an approved license record.
- [ ] Each selected family has an implementation owner.
- [ ] Each blocked family has an approved target and owner.

### `feat/3.2-vintage-acquisition`

This branch adds true historical vintages and broader first-party market data.

This branch has an external dependency. Provider licensing is outside the control of the
project. Defer only the blocked provider family. Do not defer implemented families.

#### Design decisions

- [ ] Confirm the approved source decision.
- [ ] Define one adapter boundary for each selected family.
- [ ] Define raw payload retention and redaction rules.
- [ ] Define correction and deletion semantics.

#### Implementation

- [ ] Ingest macro observations with release and revision timestamps.
- [ ] Record observation, release, availability, and revision timestamps.
- [ ] Add first-party fundamental ingestion.
- [ ] Record filing date and acceptance timestamp.
- [ ] Preserve restatements and effective availability.
- [ ] Preserve raw provider payload identity.
- [ ] Record provider and adapter versions.
- [ ] Broaden maintained price and corporate-action acquisition.
- [ ] Broaden maintained reference data acquisition.
- [ ] Add historical index membership acquisition.
- [ ] Preserve each membership change and its availability.
- [ ] Mark latest-only adapters in machine-readable metadata.
- [ ] Mark each adapter vintage capability in the registry.
- [ ] Reject latest-only adapters for strict point-in-time requests.
- [ ] Connect provider fixtures to the conformance suite.

#### Tests

- [ ] Add offline fixtures with revisions.
- [ ] Add offline fixtures with late arrivals.
- [ ] Add offline fixtures with corrections.
- [ ] Add offline fixtures with provider restatements.
- [ ] Test as-of queries before and after each revision.
- [ ] Test filing acceptance boundaries.
- [ ] Test historical membership boundaries.
- [ ] Test raw payload and managed output identities.
- [ ] Run provider conformance for each new adapter family.
- [ ] Test latest-only rejection for strict research.

#### Exit criteria

- [ ] One first-party path verifies revisions and historical availability.
- [ ] Fundamentals and membership history have maintained acquisition paths.
- [ ] Machine-readable metadata states each adapter limitation.
- [ ] Each blocked family has an approved carry-forward owner.

## Wave 3: Research governance

### `feat/3.2-final-holdouts`

This branch adds managed final-holdout assets and audited confirmatory access.

The types exist today without a subsystem. The class `FinalHoldoutUseId` has a kind
constant. The value `ValidationRole.FINAL_HOLDOUT` is declared. The value
`AnalysisIntent.CONFIRMATORY_HOLDOUT` raises at construction.

#### Design decisions

- [ ] Define the holdout asset schema and content identity.
- [ ] Define single-use, bounded-use, and administrator reuse policies.
- [ ] Define actor identity and administrator boundaries.
- [ ] Define the managed-API trust boundary.
- [ ] State that direct database and filesystem access is outside this boundary.
- [ ] Define the threat model and the claims that the subsystem does not make.
- [ ] Define which metadata exploratory services can reveal.
- [ ] Define result behavior after a failed confirmatory use.
- [ ] Define atomic consumption under the project lease model.

#### Implementation

- [ ] Add an immutable final-holdout asset.
- [ ] Bind each asset to dataset, label, universe, temporal boundary, and split policy.
- [ ] Seal membership and content identity before exploratory analysis.
- [ ] Add managed holdout tables and migrations.
- [ ] Require `FinalHoldoutUseId` for access.
- [ ] Require an actor identity for each access attempt.
- [ ] Require `AnalysisIntent.CONFIRMATORY_HOLDOUT` for analysis access.
- [ ] Record each access attempt.
- [ ] Record the actor, policy decision, and reason for each attempt.
- [ ] Record each successful use and derived result.
- [ ] Enforce single-use policies.
- [ ] Enforce bounded-use policies.
- [ ] Enforce administrator-authorized reuse.
- [ ] Block exploratory row access.
- [ ] Block exploratory summary statistics.
- [ ] Make experiments use managed holdout IDs for confirmatory evaluation.
- [ ] Reject arbitrary fold IDs for confirmatory evaluation.
- [ ] Include holdout identity and use identity in result provenance.
- [ ] Keep sealed membership immutable after creation.

#### Tests

- [ ] Test creation, sealing, and immutable identity.
- [ ] Test each use policy.
- [ ] Test authorized and unauthorized reuse.
- [ ] Test complete access audit records.
- [ ] Test experiments with managed holdouts.
- [ ] Test rejection of arbitrary confirmatory fold IDs.
- [ ] Test exploratory dataset services against sealed rows.
- [ ] Test exploratory SQL services against sealed rows.
- [ ] Test exploratory feature and analysis services against summary disclosure.
- [ ] Test concurrent attempts to consume one single-use holdout.
- [ ] Test rollback after failed confirmatory execution.
- [ ] Test migration from the 3.1.0 baseline project.
- [ ] Test that audit records do not reveal sealed membership.
- [ ] Test the documented direct-file-access boundary.

#### Exit criteria

- [ ] Confirmatory access is sealed, authorized, and audited.
- [ ] Exploratory paths cannot reveal holdout rows or summaries.
- [ ] Experiments cannot bypass managed holdout policy.
- [ ] Documentation does not claim protection from direct file access.

## Wave 4: Documentation

### `docs/3.2-research-guides`

This branch documents the new research capabilities and governance.

#### Implementation

- [ ] Add a revisions concept page.
- [ ] Add a holdout governance concept page.
- [ ] Add a nested validation concept page.
- [ ] Document the numerical semantics of each new operator.
- [ ] Document the numerical semantics of each new alpha metric.
- [ ] Document the holdout trust boundary and non-goals.
- [ ] Extend the metric catalog reference.
- [ ] Extend the quickstart with a confirmatory evaluation step.
- [ ] Republish the generated capability matrix.
- [ ] Update the deferral register in this document.
- [ ] Name the owner and target for each blocked provider family.
- [ ] Apply ASD-STE100 controlled language.

#### Tests

- [ ] Validate every Python example.
- [ ] Execute the extended quickstart against an installed wheel.
- [ ] Test generated capability data against registry data.
- [ ] Run strict MkDocs build.

#### Exit criteria

- [ ] Every capability that became stable has documented semantics.
- [ ] The published matrix agrees with the registry.

## Wave 5: Release preparation

### `release/3.2.0`

Follow the release procedure in `ROADMAP-3.1.0.md`. Change each version string to 3.2.0.

#### Entry gate

- [ ] Confirm that every prior branch merged into `develop`.
- [ ] Confirm that every checklist exit criterion has evidence.
- [ ] Confirm that no stable capability lacks an executable path.
- [ ] Confirm that every remaining deferral has an approved register entry.
- [ ] Confirm that all performance budgets pass.
- [ ] Confirm that the documented workflow passes against the built wheel.

## Release acceptance criteria

- [ ] Every `ManagedOperator` value executes or reports an honest status.
- [ ] Every `AlphaMetricKind` value executes or reports an honest status.
- [ ] Nested validation assembles from real parent and child plans.
- [ ] Feature SQL relations resolve and execute under managed limits.
- [ ] Final-holdout access is sealed, authorized, and audited.
- [ ] Each named research and catalog target is 120 physical lines or less.
- [ ] Each remaining callable exception has a reason and owner.
- [ ] The private-usage ceiling is lower than the 3.1.0 ceiling.
- [ ] Every new formula has a numerical reference test.
- [ ] Unchanged legacy identities match the 3.0.2 baseline.
- [ ] Intentional legacy identity changes have approved mappings.
- [ ] One maintained first-party path supports historical revisions.
- [ ] Each blocked provider family has an approved target and owner.

## Evidence

Record release evidence at `docs/releases/3.2.0-evidence.md`. Use the artifact list from
`ROADMAP-3.1.0.md`. Add these artifacts:

- [ ] The numerical reference results for each operator.
- [ ] The numerical reference results for each alpha metric.
- [ ] The holdout access audit sample.
- [ ] The provider conformance reports for each new adapter family.
- [ ] The provider source and license decision records.
- [ ] The callable-size exception report.

## Risks

| Risk | Effect | Response |
| --- | --- | --- |
| Provider licensing does not complete | One data family cannot ship | Defer that family with a named 3.3.0 or 3.4.0 owner |
| Operator semantics need research input | The capability branch stalls | Fix semantics in the interview before code starts |
| Nested validation identity design is hard | Validation work slips | Keep it independent from operator and metric branches |
| Catalog split changes public behavior | Users break | Compare the public surface against 3.1.0 in CI |
| Holdout policy conflicts with experiments | Rework late in the wave | Interview the experiment owner before wave 3 |
| Holdout wording implies file security | Users trust a false boundary | Publish the managed-API threat model |

## Finding traceability

| Review finding | Priority | Size | Confidence | Owning branch |
| --- | --- | --- | --- | --- |
| Unimplemented managed operators | P1 | XL | Medium | `feat/3.2-managed-operators` |
| Unimplemented alpha metrics | P1 | L | Medium | `feat/3.2-alpha-metrics` |
| Nested validation assembly | P1 | M | Low | `feat/3.2-nested-validation` |
| Feature SQL relation execution | P1 | M | High | `feat/3.2-feature-sql-relations` |
| Final-holdout governance | P1 | XL | Low | `feat/3.2-final-holdouts` |
| Point-in-time acquisition gaps | P1 | XL | Low | `feat/3.2-vintage-acquisition` |
| Large research methods | P2 | L | High | `refactor/3.2-research-workflows` |
| Large catalog methods | P2 | L | High | `refactor/3.2-catalog-decomposition` |
| Research documentation gaps | P2 | M | High | `docs/3.2-research-guides` |

## Deferral register

| Finding | Target release | Owning branch | Reason |
| --- | --- | --- | --- |
| Vectorized simulation scans | 3.3.0 | `refactor/3.3-vector-simulation` | Large engine change |
| Static event simulation | 3.3.0 | `feat/3.3-event-strategy-engine` | Large engine change |
| Multi-currency behavior | 3.3.0 | `feat/3.3-multi-currency-accounting` | Follows the 3.1.0 schema branch |
| Remaining large callables | 3.3.0 | `refactor/3.3-large-callables` | Outside research and catalog |
| USD field removal | 4.0.0 | `release/4.0.0` | Breaking public change |

Add each blocked provider family to this table before `3.2.0` releases. Name a `3.3.0`
carry-forward branch or a `3.4.0` owner.

## Completion rule

Persistra 3.2.0 is ready only when every release acceptance criterion has recorded
evidence. A version change alone does not make the release ready.
