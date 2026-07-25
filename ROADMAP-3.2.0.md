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
- [ ] Compare each identity against the 3.0.2 baseline fixtures.
- [ ] Record a numerical reference for each new formula.

## Entry gate

Do not start this roadmap until these conditions hold:

- [ ] Persistra 3.1.0 is tagged and published.
- [ ] The capability registry controls validation and documentation status.
- [ ] The benchmark harness records runtime, query count, and peak memory.
- [ ] The 3.0.2 baseline fixtures exist and pass in CI.
- [ ] Bounded readers keep peak memory flat as relation size increases.

## Branch sequence

| Wave | Branch | Prerequisites |
| --- | --- | --- |
| 1 | `refactor/3.2-research-workflows` | None |
| 1 | `refactor/3.2-catalog-decomposition` | None |
| 2 | `feat/3.2-research-capabilities` | `refactor/3.2-research-workflows` |
| 2 | `feat/3.2-vintage-acquisition` | `refactor/3.2-catalog-decomposition` |
| 3 | `feat/3.2-final-holdouts` | `feat/3.2-research-capabilities` |
| 4 | `docs/3.2-research-guides` | All implementation branches |
| 5 | `release/3.2.0` | All prior branches |

The two wave 1 branches touch different modules. They can proceed together.

## Wave 1: Maintainable research and catalog execution

### `refactor/3.2-research-workflows`

This branch divides large research workflows into explicit phases. It must preserve
public behavior before later capability work starts.

The method `AnalysisService._compute` has 465 lines. The method
`ComponentService.materialize` has 277 lines. The method `ResearchService.enrich` has 251
lines. The method `ResearchService.build` has 175 lines.

#### Design decisions

- [ ] Define typed inputs and outputs for each phase.
- [ ] Define transaction ownership across phase boundaries.
- [ ] Define shared temporal-boundary and manifest services.
- [ ] Select failure-injection points.

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

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Add integration tests for each orchestration entry point.
- [ ] Inject failure at each phase boundary.
- [ ] Test rollback and retry after each injected failure.
- [ ] Compare identities and rows with the 3.0.2 baseline fixtures.

#### Exit criteria

- [ ] Each named phase has direct deterministic tests.
- [ ] Storage mutation has one clear transaction owner.
- [ ] Equivalent input preserves behavior and identity.
- [ ] No research workflow method is longer than 120 lines.

### `refactor/3.2-catalog-decomposition`

This branch divides catalog ingestion into explicit phases. The first roadmap draft named
only the commit method. Three more methods in the same module need the same treatment.

The module `catalog/services.py` has 3,359 lines. The method `commit` has 436 lines. The
method `validate` has 310 lines. The method `stage` has 251 lines. The method
`_snapshot_material` has 196 lines.

#### Design decisions

- [ ] Define the module split for the catalog package.
- [ ] Define typed inputs and outputs for each ingestion phase.
- [ ] Define transaction ownership across phase boundaries.
- [ ] Define the precedence and revision service boundaries.

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

#### Tests

- [ ] Add focused tests for each pure phase.
- [ ] Inject failure at each phase boundary.
- [ ] Test rollback and retry after each injected failure.
- [ ] Compare identities and rows with the 3.0.2 baseline fixtures.
- [ ] Test that the public catalog surface did not change.

#### Exit criteria

- [ ] No catalog method is longer than 120 lines.
- [ ] No catalog module is longer than 1,200 lines.
- [ ] Equivalent input preserves behavior and identity.

## Wave 2: Declared capabilities and real vintages

### `feat/3.2-research-capabilities`

This branch implements every declared research capability that cannot execute today. It
changes registry entries to stable only after their tests pass.

Nineteen of thirty-five `ManagedOperator` values execute today. Five of twelve
`AlphaMetricKind` values execute today. The value `ValidationSchemeKind.NESTED` raises at
construction. The variant `FeatureSqlRelation` has no resolver.

#### Design decisions

- [ ] Specify formulas, units, missing-data rules, and minimum samples.
- [ ] Specify lookback, availability, and leakage rules for each operator.
- [ ] Specify tie handling for labels and rank diagnostics.
- [ ] Define nested validation assembly and identity rules.
- [ ] Define feature SQL relation dependency and materialization behavior.
- [ ] Select the reference implementation for each numerical check.

#### SQL relations

- [ ] Resolve `FeatureSqlRelation` dependencies.
- [ ] Execute feature relations in managed SQL reads.
- [ ] Apply the same limits as other SQL relations.
- [ ] Apply the same function allowlist as other SQL relations.
- [ ] Record feature ancestry in SQL result provenance.

#### Managed operators

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

#### Alpha metrics

- [ ] Implement `AUTOCORRELATION`.
- [ ] Implement `CATEGORICAL_EXPOSURE`.
- [ ] Implement `DECAY`.
- [ ] Implement `JOINT_EXPOSURE`.
- [ ] Implement `NUMERIC_EXPOSURE`.
- [ ] Implement `PERSISTENCE`.
- [ ] Implement `TURNOVER`.

#### Validation

- [ ] Implement `ValidationSchemeKind.NESTED` construction.
- [ ] Add a public nested validation assembly API.
- [ ] Preserve outer and inner fold ancestry.
- [ ] Enforce purging and embargo rules at both levels.
- [ ] Prevent inner selection data from reaching outer evaluation.

#### Tests

- [ ] Add numerical reference tests for each operator.
- [ ] Add numerical reference tests for each alpha metric.
- [ ] Add property tests for temporal cutoffs.
- [ ] Add property tests for units and monotonic transformations.
- [ ] Test missing, constant, sparse, and short input.
- [ ] Test feature SQL limits and ancestry.
- [ ] Test nested fold isolation and identity.
- [ ] Test each capability through its public service.
- [ ] Test bounded materialization for large input.
- [ ] Measure peak memory for each new operator.

#### Exit criteria

- [ ] Every preserved public research choice has an executable path.
- [ ] Each capability has documented numerical and temporal semantics.
- [ ] The registry and executable tests agree.
- [ ] No new capability grows peak memory with total relation size.

### `feat/3.2-vintage-acquisition`

This branch adds true historical vintages and broader first-party market data. It must
select sources before implementation.

This branch has an external dependency. Provider licensing is outside the control of the
project. The deferral rule applies to this branch in full. See the risk table.

#### Design decisions

- [ ] Select at least one revision-aware provider.
- [ ] Review provider licenses and redistribution limits.
- [ ] Define credential and offline-test requirements.
- [ ] Select maintained data families for 3.2.0.
- [ ] Define strict point-in-time adapter requirements.
- [ ] Set the decision date after which the branch defers to 3.3.0.

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

## Wave 3: Research governance

### `feat/3.2-final-holdouts`

This branch adds managed final-holdout assets and audited confirmatory access.

The types exist today without a subsystem. The class `FinalHoldoutUseId` has a kind
constant. The value `ValidationRole.FINAL_HOLDOUT` is declared. The value
`AnalysisIntent.CONFIRMATORY_HOLDOUT` raises at construction.

#### Design decisions

- [ ] Define the holdout asset schema and content identity.
- [ ] Define single-use, bounded-use, and administrator reuse policies.
- [ ] Define authorization and administrator boundaries.
- [ ] Define which metadata exploratory services can reveal.
- [ ] Define result behavior after a failed confirmatory use.

#### Implementation

- [ ] Add an immutable final-holdout asset.
- [ ] Bind each asset to dataset, label, universe, temporal boundary, and split policy.
- [ ] Seal membership and content identity before exploratory analysis.
- [ ] Add managed holdout tables and migrations.
- [ ] Require `FinalHoldoutUseId` for access.
- [ ] Require `AnalysisIntent.CONFIRMATORY_HOLDOUT` for analysis access.
- [ ] Record each access attempt.
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

#### Exit criteria

- [ ] Confirmatory access is sealed, authorized, and audited.
- [ ] Exploratory paths cannot reveal holdout rows or summaries.
- [ ] Experiments cannot bypass managed holdout policy.

## Wave 4: Documentation

### `docs/3.2-research-guides`

This branch documents the new research capabilities and governance.

#### Implementation

- [ ] Add a revisions concept page.
- [ ] Add a holdout governance concept page.
- [ ] Add a nested validation concept page.
- [ ] Document the numerical semantics of each new operator.
- [ ] Document the numerical semantics of each new alpha metric.
- [ ] Extend the metric catalog reference.
- [ ] Extend the quickstart with a confirmatory evaluation step.
- [ ] Republish the generated capability matrix.
- [ ] Update the deferral register in this document.
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
- [ ] No research or catalog method is longer than 120 lines.
- [ ] The private-usage ceiling is lower than the 3.1.0 ceiling.
- [ ] Every new capability has a numerical reference test.
- [ ] Identities match the 3.0.2 baseline for equivalent input.

## Evidence

Record release evidence at `docs/releases/3.2.0-evidence.md`. Use the artifact list from
`ROADMAP-3.1.0.md`. Add these artifacts:

- [ ] The numerical reference results for each operator.
- [ ] The numerical reference results for each alpha metric.
- [ ] The holdout access audit sample.
- [ ] The provider conformance reports for each new adapter family.

## Risks

| Risk | Effect | Response |
| --- | --- | --- |
| Provider licensing does not complete | Vintage acquisition cannot ship | Defer the branch to 3.3.0 under the deferral rule |
| Operator semantics need research input | The capability branch stalls | Fix semantics in the interview before code starts |
| Nested validation identity design is hard | Validation work slips | Split the branch and ship operators first |
| Catalog split changes public behavior | Users break | Compare the public surface against 3.1.0 in CI |
| Holdout policy conflicts with experiments | Rework late in the wave | Interview the experiment owner before wave 3 |

## Finding traceability

| Review finding | Priority | Size | Confidence | Owning branch |
| --- | --- | --- | --- | --- |
| Unimplemented managed operators | P1 | XL | Medium | `feat/3.2-research-capabilities` |
| Unimplemented alpha metrics | P1 | L | Medium | `feat/3.2-research-capabilities` |
| Nested validation assembly | P1 | M | Low | `feat/3.2-research-capabilities` |
| Feature SQL relation execution | P1 | M | High | `feat/3.2-research-capabilities` |
| Final-holdout governance | P1 | XL | Low | `feat/3.2-final-holdouts` |
| Point-in-time acquisition gaps | P1 | XL | Low | `feat/3.2-vintage-acquisition` |
| Large research methods | P2 | L | High | `refactor/3.2-research-workflows` |
| Large catalog methods | P2 | L | High | `refactor/3.2-catalog-decomposition` |
| Research documentation gaps | P2 | M | High | `docs/3.2-research-guides` |

## Deferral register

| Finding | Target release | Reason |
| --- | --- | --- |
| Vectorized simulation scans | 3.3.0 | Large engine change |
| Static event simulation | 3.3.0 | Large engine change |
| Multi-currency behavior | 3.3.0 | Follows the 3.1.0 schema branch |
| Remaining large methods | 3.3.0 | Outside the research and catalog packages |
| USD column removal | 4.0.0 | Breaking public change |

## Completion rule

Persistra 3.2.0 is ready only when every release acceptance criterion has recorded
evidence. A version change alone does not make the release ready.
