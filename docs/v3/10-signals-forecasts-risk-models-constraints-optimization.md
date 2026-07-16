# Focused specification 10: Signals, forecasts, risk models, constraints, and optimization

**Status:** implementation plan
**Target:** Persistra 3.0
**Primary package:** `persistra.portfolio`

## 1. Purpose and relationship to the umbrella specification

This plan makes the strategy and portfolio-construction direction in the
[v3 umbrella specification](v3-spec.md) implementable. It defines typed signal and
forecast meaning, point-in-time fitted-model releases, risk estimates, expected costs,
constraints, deterministic constructors, convex optimization, and immutable target-
portfolio results. The output is a portfolio intent at a decision instant; it is not an
order, fill, journal entry, or performance result.

Focused specifications 01 through 09 remain normative. This plan reuses:

- plan-01 typed IDs, canonical serialization, content IDs, numeric rules, UTC instants,
  durations, injected clocks, money/quantity values, and lifecycle events;
- plan-02 project modes, research-database ownership, leases, transactions, migrations,
  verified copies, optional-capability diagnostics, and recovery;
- plan-03 immutable composite snapshots, provenance, safety, licensing, and source
  availability;
- plan-04 instrument/listing/group identity, calendars, universes, benchmark membership,
  and decision schedules;
- plans 05 and 06 exact market, corporate-action, fundamental, estimate, macro,
  benchmark, and risk-free semantics;
- plan-07 exact decision/analysis datasets, dual cutoffs, row/input audit, temporal
  contracts, SQL/workspace lineage, safety findings, bounded frames, and information
  classes;
- plan-08 registered features/labels, exact materializations, availability, output states,
  dependency scope, implementation identity, conformance, and structural label
  separation; and
- plan-09 exact validation membership, role capabilities, nested selection, and sealed
  final-holdout behavior.

Signals and forecasts consume exact decision-safe inputs. Training may consume historical
labels only inside the fit service through an exact plan-09 membership capability. A fit
retains its label ancestry and is never itself a strategy input. A prediction becomes
decision-eligible only through the causal-fit release contract in section 8, which proves
that every training/selection observation was available by that prediction's cutoff.

Plans 11 through 13 own accounting state, target-to-order rebalance behavior, simulation,
execution, and realized costs. Plan 14 owns studies, trials, search, scenarios, retries,
and compatible reuse at the orchestration layer; this plan still owns exact occurrence
retry/verification. Plan 15 may analyze/export completed portfolio results but cannot
change their identities, constraint outcomes, or solver evidence.

## 2. Scope

### 2.1 In scope

- Versioned signal, forecast, risk-model, expected-cost, constraint-set, and portfolio-
  constructor definitions
- Exact immutable signal, forecast, risk, expected-cost, and target-portfolio
  materializations
- Rank, direction, probability, expected-return, standardized-score, and allocation-score
  signal meaning
- Direct forecasts, fitted forecasts, and explicitly separate forecast combination
- Point-in-time forecast/risk fitting, preprocessing, selection, refit, release, inference,
  and training audit over exact validation membership
- Sample, EWMA, shrinkage, user-supplied covariance, and user-supplied factor risk models
- Positive-semidefinite validation/repair, horizon/frequency conversion, and risk states
- Ex-ante fees, spread, linear impact, square-root impact, and user-supplied expected costs
- Long/short, position, gross/net, group/factor/benchmark, turnover, liquidity/capacity,
  borrow, cash, leverage/margin, and tracking-error constraints
- Equal-weight, score-proportional, quantile long-short, inverse-volatility, risk-parity,
  minimum-variance, mean-variance, maximum-diversification, and benchmark-relative
  constructors with an explicit support matrix
- CVXPY-backed convex optimization through the required `optimize` extra
- Solver capabilities, tolerances, independent post-solve verification, visible failure,
  and configured/recorded fallbacks
- Current-state and benchmark input capabilities, target weights/cash, multi-strategy
  intents, immutable identity, schemas, APIs, events, resources, and acceptance tests

### 2.2 Out of scope

- A general machine-learning framework, estimator registry, prediction service, or model
  deployment platform
- Automatic feature engineering, hyperparameter search, trial scheduling, Bayesian
  optimization, or model-comparison orchestration
- Using outer-test or final-holdout labels for ordinary fitting or selection
- Arbitrary user dataframes, mutable estimator objects, pickles, or physical SQL relation
  names as persisted execution inputs
- Tax-aware optimization, tax lots, options Greeks, nonlinear derivatives portfolios, or
  general stochastic/dynamic programming
- FX conversion, cross-currency cash/optimization, or non-USD implemented workflows
- Guaranteed cardinality, round-lot, minimum-trade, or other mixed-integer optimization in
  the initial 3.0 surface
- Rebalance schedules, threshold/buffer/open-order policy, quantity rounding, order
  generation, fills, settlement, journal accounting, realized costs, or performance
- Simulation-time sequencing of endogenous current portfolio state or run-result storage
- Claiming that a target-weight optimizer enforces venue/broker margin or borrow rules
  that require plans 11 and 13
- Silent covariance repair, silent unit/horizon conversion, silent solver substitution,
  or silent fallback

## 3. Normative decisions

1. Every definition is immutable and versioned. Every materialization/result binds exact
   definitions, input occurrences, snapshot, schedule, cutoffs, code, environment,
   policies, limits, and output manifests. Friendly names and `latest` never remain in an
   execution identity.
2. Signal numeric meaning is mandatory. A rank, probability, direction, standardized
   score, or allocation score is not silently interpreted as an expected return.
3. Forecast target, unit, horizon, reference currency, compounding, and uncertainty
   semantics are explicit. Forecast combination is a separate registered transform and
   portfolio optimization does not opportunistically combine predictions.
4. Direct label, retrospective, unresolved, or unmediated label-derived ancestry cannot
   enter a signal, forecast inference, constructor, optimizer, strategy, or simulator.
   No unsafe override weakens this structural rule.
5. Fitting is the sole typed exception for historical labels. A fit retains label class,
   exact sample membership, label intervals/availability, preprocessing, selection, code,
   and parameter manifests and exposes no decision-data adapter.
6. A causal-fit release is row-relative evidence, not a blanket declassification. A
   prediction is causal only when the fit's logical availability and every inference input
   availability are no later than that row's public cutoff and, when project knowledge is
   enabled, all governing artifact/source evidence was recorded by its project cutoff.
7. Validation membership is authoritative. Fitting and selection use only roles permitted
   by an exact plan-09 capability; outer-test and final-holdout labels remain inaccessible
   except to their evaluation owners.
8. Preprocessing learned from data is part of the fit. Means, scales, imputation values,
   encodings, clipping levels, PCA loadings, and similar state cannot be computed over an
   inference, test, or holdout population.
9. Risk estimates are point-in-time artifacts. Estimation window, return definition,
   missing policy, weights, regularization, annualization/horizon conversion, asset order,
   and availability are identity-bearing.
10. Covariance validity is checked before portfolio construction. Repair occurs only under
    a declared algorithm/tolerance, records before/after diagnostics, and changes identity.
11. Ex-ante expected cost and realized execution cost are different typed contracts. A
    portfolio optimizer's expected cost is not reported as a realized expense.
12. Constraint meaning, scope, units, hardness, bounds, tolerance, missing-data policy, and
    required capabilities are registered. Unsupported constructor/constraint combinations
    reject before numerical work.
13. Constraint inputs are point-in-time. Sector, factor, benchmark, liquidity, borrow, and
    margin data use exact available-at evidence rather than current classifications.
14. Portfolio construction is a pure one-decision transform that emits target risky-asset
    weights plus cash and diagnostic intent. It does not emit quantities or orders and
    cannot mutate accounting state. A precomputed multi-decision sequence either requires
    no current state or binds one exact external current-state view per decision; it never
    predicts its own state path.
15. Simple constructors and optimizers share one normalized input and target contract.
    Bypassing a risk model, cost model, benchmark, or current state is allowed only when the
    selected constructor/constraint/objective contract does not require it.
16. Initial general optimization problems are convex. Nonconvex or mixed-integer requests
    reject unless a separately registered solver/problem capability explicitly supports
    their exact formulation.
17. Solver name/version, problem form, tolerances, options, warm-start policy, status,
    iterations, residuals, objective components, and independent constraint violations are
    persisted. Solver-reported success alone is insufficient.
    Iteration limits are deterministic; a wall-time-triggered outcome is recorded as
    ineligible for deterministic replay.
18. Failure is visible by default. A fallback has its own registered constructor, trigger
    set, inputs, result status, and audit; it never overwrites the failed attempt.
19. Deterministic asset ordering, tie-breaking, matrix construction, reductions, solver
    selection, and numeric normalization are part of the contract. Insertion/hash order
    cannot change a target; only a visibly wall-time-limited attempt lacks a deterministic
    re-execution claim.
20. Completed definitions, fits, materializations, attempts, violations, and targets are
    append-only. Exact retry verifies stored content; it does not recompute and compare only
    a friendly summary.
21. All paths are bounded. Oversized universes, matrices, fit memberships, solver output,
    and dataframe requests fail explicitly rather than sample, truncate, or weaken checks.

## 4. Identity, versions, enums, and public values

### 4.1 Typed IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `SignalDefinitionId` | `signal_definition` | Stable lineage for one qualified signal |
| `SignalMaterializationId` | `signal_materialization` | One immutable signal execution occurrence |
| `ForecastDefinitionId` | `forecast_definition` | Stable lineage for one qualified forecast/combiner |
| `ForecastFitId` | `forecast_fit` | One immutable label-derived forecast fit occurrence |
| `ForecastMaterializationId` | `forecast_materialization` | One immutable forecast inference occurrence |
| `RiskModelDefinitionId` | `risk_model_definition` | Stable lineage for one risk-model contract |
| `RiskModelFitId` | `risk_model_fit` | One immutable historical risk-estimation occurrence |
| `RiskMaterializationId` | `risk_materialization` | One immutable sequence of point-in-time risk estimates |
| `ExpectedCostModelId` | `expected_cost_model` | Stable lineage for one ex-ante cost contract |
| `ExpectedCostMaterializationId` | `expected_cost_materialization` | One immutable point-in-time ex-ante cost-surface occurrence |
| `ConstraintSetId` | `constraint_set` | Stable lineage for one ordered constraint set |
| `PortfolioConstructorId` | `portfolio_constructor` | Stable lineage for one allocation/optimization contract |
| `PortfolioConstructionResultId` | `portfolio_construction_result` | One immutable target sequence and attempt audit |

Stable definitions use plan-08 `ResearchComponentVersion`. Each qualified name has one
stable typed ID, immutable semantic versions, and a positive gap-free registration
sequence. Fits, materializations, and construction results are occurrence IDs. Plan-01
`ContentId` values separately identify definitions, parameters, training memberships,
causal releases, matrices, constraints, execution, and outputs; a content ID never replaces
a typed UUID.

### 4.2 Stable enums

| Enum | Values |
| --- | --- |
| `SignalMeaning` | `rank`, `direction`, `probability`, `expected_return`, `standardized_score`, `allocation_score` |
| `SignalTransformKind` | `identity`, `rank`, `direction`, `probability_calibration`, `standardize`, `winsorize`, `combine`, `custom` |
| `ForecastKind` | `direct`, `fitted`, `combined` |
| `ForecastTargetKind` | `simple_return`, `log_return`, `excess_return`, `probability`, `volatility`, `price_change`, `custom` |
| `ForecastUncertaintyKind` | `none`, `standard_error`, `standard_deviation`, `quantiles` |
| `FitPurpose` | `fold_training`, `inner_selection`, `selected_refit`, `final_holdout_refit`, `historical_production` |
| `TrainingPreprocessorKind` | `none`, `standardize`, `median_impute`, `winsorize`, `one_hot`, `custom` |
| `FitState` | `completed`, `insufficient_samples`, `singular`, `invalid_numeric`, `failed_convergence` |
| `SignalValueState` | `computed`, `input_missing`, `upstream_noncomputed`, `not_scheduled`, `outside_scope`, `invalid_numeric` |
| `PredictionState` | `computed`, `input_missing`, `fit_unavailable`, `not_scheduled`, `outside_scope`, `invalid_numeric` |
| `DecisionEligibilityKind` | `direct_causal`, `causal_fit_release`, `causal_noncomputed`, `research_override_acknowledged` |
| `RiskModelKind` | `sample_covariance`, `ewma_covariance`, `fixed_shrinkage`, `ledoit_wolf`, `user_covariance`, `user_factor` |
| `RiskReturnKind` | `simple_return`, `log_return`, `excess_return` |
| `RiskMissingPolicy` | `complete_case`, `pairwise` |
| `ShrinkageTargetKind` | `diagonal`, `scaled_identity` |
| `PsdPolicy` | `fail`, `eigenvalue_clip` |
| `RiskEstimateState` | `computed`, `insufficient_observations`, `asset_missing`, `fit_unavailable`, `not_scheduled`, `outside_scope`, `non_psd`, `invalid_numeric` |
| `ExpectedCostKind` | `none`, `fees`, `half_spread`, `linear_impact`, `square_root_impact`, `composite`, `user_supplied` |
| `ExpectedCostState` | `computed`, `input_missing`, `outside_domain`, `not_scheduled`, `invalid_numeric` |
| `ConstraintKind` | `long_short_bounds`, `position_bounds`, `gross_exposure`, `net_exposure`, `group_exposure`, `factor_exposure`, `benchmark_relative`, `turnover`, `liquidity_capacity`, `borrow`, `cash`, `leverage`, `margin`, `tracking_error` |
| `ConstraintHardness` | `hard`, `soft` |
| `ConstraintScopeKind` | `portfolio`, `asset`, `group`, `factor`, `benchmark_active` |
| `ConstraintMissingAction` | `exclude_asset`, `use_declared_bound`, `disable_with_warning`, `fail` |
| `ConstructorKind` | `equal_weight`, `score_proportional`, `quantile_long_short`, `inverse_volatility`, `risk_parity`, `minimum_variance`, `mean_variance`, `maximum_diversification`, `benchmark_relative`, `custom` |
| `OptimizationObjectiveKind` | `minimum_variance`, `mean_variance`, `maximum_diversification`, `benchmark_relative` |
| `OptimizationAttemptStatus` | `optimal`, `optimal_inaccurate`, `infeasible`, `unbounded`, `iteration_limit`, `solver_error`, `timeout`, `invalid_result`, `unsupported` |
| `ConstructionAttemptStatus` | `constructed`, `construction_failed`, plus every `OptimizationAttemptStatus` value |
| `ConstructionAttemptKind` | `primary`, `solver_fallback`, `constructor_fallback` |
| `OptimizationReplayStatus` | `eligible`, `wall_time_limited` |
| `ConstructionStatus` | `completed`, `completed_with_fallback`, `failed` |
| `FallbackKind` | `none`, `retain_current`, `registered_constructor` |
| `TargetWeightState` | `targeted`, `fixed_zero`, `excluded`, `liquidate`, `retained_ineligible`, `input_missing`, `fallback_retained` |
| `ConstraintEvaluationState` | `satisfied`, `violated`, `softened`, `not_applicable`, `input_missing` |
| `PortfolioIntentKind` | `absolute_weights`, `benchmark_relative_weights`, `child_strategy_weights` |

`optimal_inaccurate` is never automatically accepted. The registered solver policy must
name it as an allowable candidate status and independent verification must still pass.
`disable_with_warning` is legal only for an explicitly optional constraint and always
makes the result unsafe for production simulation by default. Structural constraints and
label boundaries cannot use it.

### 4.3 Units, horizons, and value domains

Every scalar output uses a plan-01 `UnitSpec`. Dimensionless values still declare their
meaning. Initial domains are:

- rank: finite `[0, 1]`, with the singleton convention `0.5`;
- direction: exactly `-1`, `0`, or `1` unless the version declares continuous direction
  on `[-1, 1]`;
- probability: finite `[0, 1]` with a named event/class definition;
- expected/simple/excess return: finite decimal return for one declared horizon;
- log return: finite natural-log return for one declared horizon;
- standardized score: finite dimensionless value with exact center/scale definition; and
- allocation score: finite dimensionless value whose sign and normalization are explicit.

Expected returns, covariance, risk aversion, costs, and tracking error must use a common
optimization horizon. A conversion is permitted only through a registered
`HorizonConversionSpec` naming source/target horizon, calendar/schedule, return kind, and
assumption. Means scale by the declared independent-increment count; covariance scales by
that count; volatility scales by its square root. No conversion is implied from column
frequency or annualization labels.

Price-change forecasts require currency and price basis. Volatility is nonnegative and
declares whether it is standard deviation of simple/log/excess return. Quantile
uncertainty uses strictly increasing probabilities in `(0, 1)` and nondecreasing values.
Confidence is not a synonym for probability or one minus a p-value; a custom confidence
field requires its own bounded definition.

The implemented 3.0 portfolio workflow accepts only the plan-04 US-listed equity/ETF
instrument scope with USD benchmarks, forecasts, prices, costs, NAV, and cash. Currency
remains explicit so an unsupported currency fails rather than being treated as USD.
References to FX conversion in forward interfaces are unavailable capability points until
later focused contracts add point-in-time FX and cross-currency accounting; this plan
never synthesizes an FX rate.

### 4.4 Public limits

```python no-run
@dataclass(frozen=True, slots=True)
class PortfolioResearchLimits:
    max_input_rows: int = 25_000_000
    max_assets_per_decision: int = 20_000
    max_signal_outputs: int = 256
    max_forecast_outputs: int = 256
    max_fits: int = 100_000
    max_training_rows_per_fit: int = 25_000_000
    max_features_per_fit: int = 4_096
    max_covariance_assets: int = 20_000
    max_covariance_entries: int = 100_000_000
    max_factor_count: int = 2_048
    max_constraints: int = 100_000
    max_constraint_coefficients: int = 100_000_000
    max_solver_attempts_per_decision: int = 8
    max_output_rows: int = 25_000_000
    partition_rows: int = 100_000
    direct_pandas_rows: int = 2_000_000
    timeout: Duration = Duration(1_800_000_000)
```

All values are positive. The covariance-entry limit counts the stored triangle, factor
loadings, and any dense work matrix before allocation. Project memory, temporary-storage,
and wall-time ceilings may be lower. An effective limit change enters execution identity.
No limit authorizes sampling or sparse approximation unless the registered algorithm
itself declares that exact approximation.

## 5. Project, database, and lifecycle ownership

Registration, fitting, materialization, and construction require
`ProjectMode.RESEARCH_WRITE`. They write only the research database under its exclusive
plan-02 lease and hold shared leases on every exact market database in the transitive
composite snapshot. They never mutate attached market files. Immutable handles and bounded
inspection are available in `read_only` and `research_write`.

This ownership describes standalone precomputed research occurrences. The side-effect-free
one-decision construction kernel in section 15.5 may run inside plans 12–13; the run owner
persists its evidence in the isolated run/result transaction and does not acquire a second
research writer per decision.

Research migrations create:

- definition, version, fit, materialization, construction, attempt, and constraint metadata
  in schema `portfolio`;
- immutable controlled signal relations in schema `signal_data`;
- immutable controlled forecast relations in schema `forecast_data`;
- immutable fit-state/training-audit relations in schema `model_data`;
- immutable controlled covariance/factor relations in schema `risk_data`; and
- immutable controlled cost and target-weight relations in schema `portfolio_data`.

Shared lineage and safety evidence remains in the plan-07 research-owned relations, and
lifecycle events remain in plan-02 `_persistra.domain_events`; plan 10 stores their exact
manifest/event references rather than creating competing local stores.

These are capability boundaries as well as organization. Callers never receive physical
names or raw connections. Fit executors receive a bounded training capability that can
bind permitted labels; inference, signal, risk-consumer, constructor, strategy, and
simulation repositories do not install label adapters. Controlled/generated relations are
reachable only by typed occurrence handles whose owner, schema, manifest, and project
lifecycle are verified.

Definitions, versions, completed/terminal fit evidence, materializations, attempts,
violations, and targets are append-only. A failed definition registration publishes
nothing. A normal numerical fit failure may publish a terminal fit state because it is
useful evidence, but it publishes no causal release or predictions. Infrastructure,
transaction, safety, or corruption failure publishes no occurrence. A construction result
may contain a failed primary optimization plus a successful configured fallback; both
attempts and the final target publish atomically.

Large work uses deterministic decision/asset partitions and transaction-local staging.
Only verified metadata and physical relations become visible at commit. Stale internal
staging is diagnosed and removed under plan-02 recovery only when no completed occurrence
references it. Exact execution retries verify all normalized rows, dynamic manifests,
findings, and event evidence before returning the existing occurrence.

## 6. Exact inputs, information safety, and licensing

### 6.1 Decision input bundle

Every signal/forecast inference or construction starts from an immutable
`DecisionInputBundle` containing:

- exact completed plan-07 decision-role `ResearchDatasetBuildId` and base-key manifest;
- exact composite snapshot, universe evaluation, schedule, public-cutoff policy, and
  optional project cutoff;
- selected canonical fields and exact plan-08 feature materialization/output references;
- optional exact signal/forecast/risk/cost occurrences from this plan;
- direct `instrument_id`, `decision_at`, `public_cutoff_at`, optional
  `project_cutoff_at`, row state, and availability for every selected value;
- complete dependency-root, safety, lineage, licensing, schema, and row-audit manifests;
  and
- deterministic row/asset ordering and effective resource limits.

Input occurrences must share compatible base keys, snapshot, schedule, cutoff mode,
instrument/listing meaning, currency policy, and output availability. Compatibility is
proved by typed adapters, not joins on friendly columns. An exact subset is allowed only
through a persisted subset manifest whose keys all belong to the common base.

Under `PUBLIC_AND_PROJECT`, every consumed occurrence plus its definition, parameter,
implementation, conformance, selection, constraint, solver/fallback, and dependency
evidence must have been registered/created by the fixed project cutoff under the plan-08
project-knowledge rule. Later portfolio research can remain an explicitly project-
knowledge-unsafe comparison, but it cannot claim the earlier project knew it.
The wall-clock publication time of a plan-12/13 run-endogenous accounting state or target
is not treated as new research knowledge during deterministic replay; its governing
definitions/parameters and every external source root must satisfy the cutoff, and its
run-local derivation must be complete. A caller-supplied external future state path does
not receive that exception.

Direct `InformationClass.LABEL`/`RETROSPECTIVE` dependency roots and unreleased fits reject
structurally; section 6.3 is the only typed fit boundary. Opaque/unsafe causal inputs may
execute only through the plan-07 acknowledged research override; their
descendants remain opaque/unsafe, record the finding, and are rejected by simulation by
default. Projection, renaming, aggregation, custom code, a fit object, or a new definition
cannot erase a root.

### 6.2 Training input capability

A plan-09 `ValidationTrainingCapability` is issued for one exact:

- completed plan-09 `ValidationPlanId` and, where applicable, fold/child-plan ordinal;
- fit purpose and permitted role set;
- feature and label output selections over the same exact base build;
- selected sample-key/membership content roots and exclusion-reason roots;
- frozen parameter/preprocessor/model selection manifest when required;
- outer-test, final-holdout, and contamination state; and
- caller operation, expiry within the open project, and one noncircular
  `planned_fit_content_id`.

The planned-fit ID freezes the complete fit recipe and, where required, the already-frozen
selection-manifest root. It excludes the capability that will bind it, future fit
occurrence ID, publication metadata, fitted-state/output roots, and causal release. It is
therefore computable before issuance without hashing itself through the capability. The
capability is nonserializable, nontransferable, and does not expose arbitrary SQL or a
label repository. The fit service resolves exact bounded rows internally and records every
selected key. The capability cannot be converted to a decision handle.

The persisted capability content ID identifies only the stable authorization scope:
planned-fit ID, plan/fold/purpose/roles, membership/selection/holdout roots, and issuer
policy. The runtime bearer token, caller/session handle, and expiry enforce access but do
not enter economic execution identity; they are bounded security audit, so renewing an
otherwise identical authorization cannot manufacture a second fit occurrence.

| Fit purpose | Label-bearing fit rows | Label-bearing score rows | Required evidence |
| --- | --- | --- | --- |
| `fold_training` | `train` | none | exact nonnested/nested training capability |
| `inner_selection` | inner `train` | inner `validation` | exact inner plan and candidate manifest |
| `selected_refit` | outer `train` plus declared `validation` | none | frozen inner-selection manifest; outer test sealed |
| `final_holdout_refit` | exact non-holdout development membership | none | frozen final selection; holdout unopened and clean |
| `historical_production` | exact samples whose labels were available by each fit cutoff | none | matching fold in a predeclared rolling/expanding fit schedule |

Outer-test labels may be opened only by plan-09/14 evaluation and never become ordinary
fit rows. `final_holdout_refit` may include previously evaluated development test rows only
when the final selection manifest was frozen before the managed holdout opened; it still
cannot inspect holdout labels. Any external label use reported against the plan prevents a
clean final-holdout release.

### 6.3 Safety propagation and causal-fit exception

A fit's summary `information_class` is `label`. Its dependency closure contains all
training feature and label roots and remains unavailable to decision repositories.
`CausalFitRelease` is a separate immutable manifest containing:

- fit ID/state and exact selected parameter/model/preprocessor state roots;
- training and scoring membership roots, maximum label interval end, maximum source
  availability, and logical fit cutoff;
- declared fit delay and computed `fit_available_at`;
- fit-purpose/role proof, selection capability, and holdout-disjointness proof;
- inference input schema and accepted parameter ranges;
- implementation/environment/numeric policy and complete root closure; and
- release status plus bounded reason evidence.

The release is valid only for a release-eligible fit purpose, `FitState.COMPLETED`, complete
lineage, a safe fit executor, permitted roles, exact disjointness, and finite validated
state. It does not change the fit's information class. Instead, each prediction row cites
the release and proves:

```text
fit_available_at <= public_cutoff_at
and every inference_input.available_at <= public_cutoff_at
and, when project knowledge is enabled,
    every training/scoring/inference source recorded_at <= project_cutoff_at
    and fit/release/definition/parameter/selection evidence created_at <= project_cutoff_at
```

The prediction dependency manifest contains the causal release as a typed root and keeps
the separate training-label root manifest for audit. The plan-07 classifier recognizes
only this exact adapter; unmediated label roots, missing release fields, incomplete closure,
or a failed inequality remain structural. A passing prediction row is
`InformationClass.CAUSAL`. A noncomputed row may omit fit/release while remaining causal
when its state/reason was itself derived without future evidence and exposes no fitted
value; its proof kind is `causal_noncomputed`. A materialization may summarize as safe
causal only when every computed fitted row passes release and every noncomputed audit row
satisfies that causal-state rule.

A direct causal signal, forecast, user-supplied risk estimate, or cost estimate has no
fit/release. Its separate decision-eligibility proof binds the exact causal input closure,
transform/adapter, fixed parameter content/provenance/logical availability, row
availability, and cutoff. With project knowledge enabled, definition/parameter evidence
must also have been recorded by the project cutoff. A parameter calibrated from labels is
not “fixed” merely because the caller supplies a number: it must use the fit/release path
or remain opaque/unsafe. An acknowledged unsafe and/or opaque research input uses the same
proof shape with `research_override_acknowledged`, retains its exact information class and
unsafe findings, and remains simulation-ineligible by default. A
`DecisionEligibilityKind` never converts retrospective/direct-label input.

`fit_available_at` is logical research availability, not artifact publication wall time:

```text
fit_available_at = max(
    maximum training/scoring input availability,
    maximum training/scoring label availability,
    declared fit anchor
) + declared fit delay
```

The actual `created_at` remains separate provenance. Zero fit delay is explicit and may be
used only when the implementation contract claims the computation would have completed at
the anchor. Plan-04 decision schedules and source calendars resolve the anchor; a caller
cannot backdate it.

### 6.4 Licensing and sensitive state

Output licensing is the most restrictive transitive source classification plus registered
model/solver restrictions. A derived target cannot shed source redistribution limits.
Export and dataframe services evaluate exact roots before exposing values.

Estimator parameters, custom-source manifests, and solver text may be sensitive. Ordinary
events/logs contain bounded IDs, counts, status, and content roots, not coefficients,
training rows, exception messages, SQL, paths, credentials, or vendor data. Access-
controlled model inspection may expose typed coefficient/state frames when licensing and
project policy allow it; raw pickles and arbitrary deserialization are never a public
storage contract.

## 7. Definition and registration contracts

### 7.1 Shared version fields

Every version declares:

- stable qualified name/typed ID, semantic version, owner, description, tags, and a
  nonempty `Assumptions and limitations` section;
- kind-specific input schema and ordered typed dependency references;
- parameters/defaults/validation and canonical encoding;
- instrument/decision grain, schedule behavior, cross-sectional/group scope, and
  availability transform;
- deterministic output schema, unit, state, nullability, and missing/invalid policy;
- implementation identity, trust/conformance requirement, numeric/runtime policy, and
  required installation capability;
- default limits, licensing/export policy, schema version, registration sequence/content
  ID, and registration instant.

No version contains a mutable estimator, callable closure, dataframe, `latest` reference,
physical name, solver auto-selection, or arbitrary JSON extension bag. Built-ins are
installed from a versioned package manifest. Custom implementations are explicitly
registered through the open project; imports never mutate a process-global registry.

Exact registration retry returns the existing version without another event. Equal
name/version with different content conflicts. Later versions retain the stable ID and
increase both semantic version and gap-free registration sequence. Plan-08 semantic
version intent applies: changed economic meaning, timing, missing policy, output unit, or
constraint interpretation requires a major version.

### 7.2 Signal and forecast versions

A signal version additionally declares signal meaning, unit/domain, source outputs,
transform graph, cross-sectional grouping, direction, tie policy, clipping/winsorization,
normalization population, minimum valid count, availability propagation, and output names.
An `expected_return` signal also declares the same return target/horizon/currency/basis as
a direct forecast; a `probability` signal declares its exact event/class and horizon. Those
fields permit only an explicitly compatible stage bypass, not inference from numeric dtype.

A forecast version declares direct/fitted/combined kind, target/event definition, return
or value kind, horizon, currency/basis, expected-value output, uncertainty contract,
confidence diagnostics, model/preprocessor schema where fitted, combination weights/
availability where combined, refit schedule, fit delay, and prediction state policy.

Fitted versions declare an estimator protocol, not a general registry. Initial managed
adapters may cover deterministic linear models and explicitly reviewed scikit-learn
estimators. An adapter must implement canonical parameter validation, fresh construction,
bounded fit/predict, typed state extraction, deterministic seeding, implementation capture,
and output-schema validation. An arbitrary fitted Python object is not accepted.

### 7.3 Risk, cost, constraint, and constructor versions

A risk-model version declares kind, input return definition, estimation window, update
schedule, observation weights/decay, minimum observations, missing policy, centering,
regularization/shrinkage, PSD policy/tolerance, frequency/horizon conversion, factor
meaning when applicable, asset eligibility, output schema, and logical availability delay.

An expected-cost version declares each component, inputs/units, direction symmetry,
participation domain, fixed-coefficient provenance or user-supplied point-in-time
coefficient relation, aggregation, currency/NAV normalization, extrapolation/missing
behavior, and logical availability. `none` is an explicit zero-cost model and cannot
coexist with other components.

A constraint-set version is an ordered nonempty list of typed constraint terms. Each term
has a positive ordinal, stable term name, kind, hardness, lower/upper bound or typed
function, scope/selector, unit/horizon, tolerance, soft penalty, missing action, required
input capabilities, and assumptions. Duplicate semantic terms conflict unless their
intersection is intentionally named and proven nonempty.

A constructor version declares kind, required signal/forecast/risk/cost/current-state/
benchmark inputs, eligibility policy, gross/net/cash budget, normalization/tie policy,
constraint-set reference, objective/formulation, solver policy, fallback, output intent,
and a `ConstructionTimingSpec` with explicit nonnegative logical delays for primary and
fallback attempts. It pins exact version/content of referenced definitions at registration
or declares typed version parameters that must resolve before execution identity freezes.

## 8. Fitting, selection, release, and inference

### 8.1 Fit schedule and membership

A fitted forecast or fitted risk model uses an explicit sequence of `FitAnchor` values.
Each anchor contains a decision/schedule instant, a logical knowledge cutoff no later than
that instant, an expanding/rolling/explicit training selector, fit delay, and the first
prediction decision eligible to use the fit.
Anchors are resolved before values are inspected. Training membership then intersects the
selector with the exact capability membership and applies only registered row-state and
complete-case/preprocessing policies.

Overlapping label intervals are legal training observations but remain in the membership
and inference audit. Random row shuffling is never introduced implicitly. If an estimator
requires randomness, the service first hashes a seed-basis manifest that contains the
registered namespace/policy but excludes the derived seed, derives and stores the seed,
and then includes that resolved seed in the planned-fit content ID. The seed never derives
from a content ID that already contains itself, and worker order is irrelevant.

Every excluded candidate receives one stable reason. Minimum sample, entity, decision,
class, and feature-variance requirements are checked before construction. A numerical
insufficiency publishes the terminal fit state and bounded aggregate diagnostics, not an
empty successful model.

### 8.2 Preprocessing and model selection

The preprocessing graph is fitted only on permitted fit rows. Transform state is stored in
typed, bounded, implementation-specific relations with content roots. At scoring/inference,
the frozen state is applied without recomputing population statistics. Unknown categories,
missing values, clipping, and invalid numerics follow declared policies and produce row
states where appropriate.

Candidate parameters/models are predeclared and ordered. Inner selection evaluates only
inner validation membership, uses a registered metric/direction/aggregation, and applies
an exact deterministic tie-break: metric, complexity key, canonical parameter bytes, then
candidate ordinal. Candidate scores are label-classified selection evidence. The frozen
selection manifest names every candidate, fit, score state/value, aggregation, selected
ordinal, and exact selected-refit recipe content before an outer-test or final-development
refit capability may open. That recipe excludes the enclosing selection manifest,
capability, occurrence, and outputs. Once the selection root exists, the service computes
the planned-fit content ID from both and obtains the capability against it. The selected-
refit occurrence ID may be allocated later, but its planned content cannot change.

This plan executes one supplied selection manifest/candidate set; plan 14 owns generating
search trials and distributed scheduling. A plan-14 selected parameter may enter here only
through the same immutable selection capability and exact content manifest.

### 8.3 Fit state and causal release

Managed model state uses typed numeric/string/array fields with declared shape, dtype,
ordering, and finite-value rules. Portable safe formats are preferred; Python pickle,
joblib, cloudpickle, and executable bytecode are not persisted public contracts. A custom
adapter may store opaque implementation bytes only in a nonexportable restricted blob
with an exact implementation/runtime identity, and such state cannot claim cross-
environment portability.

After validating a completed fit that is eligible for decision inference, the service
computes the causal-release manifest described in section 6.3. Only `selected_refit`,
`final_holdout_refit`, and `historical_production` may receive a release; `fold_training`
and `inner_selection` fits remain evaluation-only even when their model state is complete.
Release rejects when any fit/scoring role is unauthorized, membership or root closure is
incomplete, a training label was unavailable at the fit cutoff, selection was not frozen
where required, the final holdout was opened/contaminated too early, or output state is
invalid. Fit completion and any eligible release publish in one transaction; absence of a
release is immutable and a fit never has a mutable “approved” flag.

### 8.4 Managed evaluation, inference, and fit selection

Completed model state is usable for label-aware evaluation only inside the plan-09/14
owner with the exact matching fold, frozen-selection outer-test, or final-holdout-use
capability. That owner supplies bounded feature keys, invokes the adapter without exposing
model/label repositories, and persists prediction states plus metrics as label-classified
analysis/trial evidence. These evaluation predictions are not
`ForecastMaterializationId` outputs, strategy handles, or causal releases. In particular,
completed `fold_training`/`inner_selection` state can be scored through this path but cannot
be selected below for decision inference.

For each prediction key, the service selects the latest registered fit anchor satisfying
`fit_available_at <= row cutoff`, breaking equal availability by anchor ordinal then fit
UUID bytes only after detecting that equal anchors have identical execution meaning.
There is no look-ahead to the next refit. A missing eligible fit yields
`fit_unavailable`, not a backfilled future model.

Inference input columns are aligned by exact typed output identity and schema, never
positional coincidence or friendly name alone. Rows are ordered by decision, instrument,
and output ordinal. Prediction, uncertainty, diagnostics, selected fit ID, input-state
root, value availability, and causal-release root are persisted for every targeted row.

Prediction availability is:

```text
max(fit_available_at, all inference input availability) + inference delay
```

The value is computed only when that availability satisfies the row's cutoff. A forecast
whose release becomes available after decision `d` may be used at a later compatible
decision through an explicit backward-as-of age policy; it is never rewritten onto `d`.

### 8.5 Direct and combined forecasts

A direct forecast is a registered causal transformation whose inputs already have forecast
meaning or whose formula explicitly maps a signal to a target/horizon/unit. Mapping a rank
or z-score to expected return requires registered fixed calibration parameters or a fitted
forecast calibration; a cast/rename is invalid.

A combined forecast consumes exact component forecasts with the same target/event,
horizon, USD/basis, and return convention, or registered horizon conversions. Static
weights are versioned parameters. Learned weights are a fit with the same training/release
rules. The registered combination formula fixes weight sign/normalization and target-
domain validation; a weighted expected value is not silently substituted for a probability
pool or another target-specific rule.

Missing-component renormalization is permitted only when declared, requires a minimum
component count, and records the exact participating set per row. Combined uncertainty
declares the exact component covariance/dependence input or a reviewed conservative bound;
it cannot assume independence, average standard errors, or take a square root of weighted
variances implicitly. Without sufficient joint evidence, uncertainty is explicitly absent
or noncomputed under the version contract. Combination precedes and is independent from
portfolio optimization.

## 9. Signal semantics and managed transforms

### 9.1 Ranking, ties, and direction

Rank operates independently at each decision within the declared full cross section or
exact plan-04 group root. Only computed, eligible finite values participate. Values sort by
numeric value then instrument ID; equal numeric values receive their average ordinal rank
before normalization to `[0, 1]`. With `n > 1`, normalized rank is
`(average_rank - 1) / (n - 1)`; with `n = 1`, it is `0.5`. Ascending/descending orientation
is identity-bearing. Missing rows remain present with state.

Discrete direction uses registered negative/positive thresholds with an explicit closed-
boundary convention and emits `-1`, `0`, or `1`. Continuous direction validates `[-1, 1]`.
Probability calibration is a direct fixed registered mapping. Learned calibration is a
fitted forecast under section 8; clipping arbitrary values to `[0, 1]` does not create a
probability.

### 9.2 Standardization, winsorization, and scores

Cross-sectional standardization declares population/sample dispersion, minimum count,
centering, zero-dispersion state, and group scope. Time-series standardization uses a
causal plan-08 feature/history definition; this layer cannot silently inspect future rows.
Signal winsorization uses fixed registered thresholds. Learned quantiles/scales are fitted
forecast preprocessing under section 8; they are not hidden state on a signal definition.
A contemporaneous cross-sectional transform may use only causally available values at that
decision and records the exact population root.

Availability follows the actual dependency scope. A row-local transform takes the maximum
availability of that row's used inputs; a rank/standardization/group transform takes the
maximum across every participating value and membership fact in the exact cross section;
a combination takes the maximum of its participating components. The registered signal
delay is then added. It never reports a row-local instant for a cross-sectional result.

Allocation scores declare sign meaning and positive/negative leg behavior but carry no
expected-return semantics. Signal combination declares component meanings and refuses
incompatible types unless an explicit transform maps each to one common meaning.

### 9.3 Signal materialization

A signal materialization resolves exact version/parameters/inputs, validates complete
lineage and structural safety, partitions by decision/group, applies the transform,
reconciles one row per targeted base key/output, computes availability and state, validates
domain/unit/schema, hashes the relation, records findings, and publishes atomically.

Execution identity includes definition/version/content, exact parameter bytes, all input
occurrences/selected outputs, base build/snapshot/schedule/cutoffs, cross-section/group
roots, implementation/environment/numeric policy, limits, and output schema. It excludes
occurrence UUID, publication instant, physical name, event ID, and own output root.

## 10. Risk-model contracts

### 10.1 Common estimation contract

Each risk estimate applies at one decision and covers a deterministic ordered asset set.
Historical returns are exact plan-08 return-label outputs with closed intervals/
availability and are accessed only through the risk-fit capability; a risk adapter cannot
read bars directly or synthesize untracked training membership. The fit retains label
ancestry; its point-in-time released covariance/factor estimate may be consumed by a
constructor only when its logical availability satisfies the decision cutoff under
section 6.3.

Return observations declare simple/log/excess kind, horizon, adjusted-price policy,
currency, risk-free/benchmark reference, and closed information intervals. Asset
eligibility, lookback, minimum observations, centering, missing policy, weights,
regularization, and annualization/horizon conversion are fixed before data access.

`complete_case` retains dates on which every selected asset return is computed. `pairwise`
uses the exact intersection for each covariance pair, stores every pair count, and requires
the declared PSD policy because pairwise output need not be PSD. It never fills an absent
covariance with zero. Sample denominators and EWMA weights/effective sample size are
recomputed on each pair's exact included observations; full-series weights are not reused
without pairwise renormalization.

### 10.2 Sample and EWMA covariance

For a complete-case matrix `R` with `T >= 2`, sample covariance uses the two-pass centered
formula with denominator `T - 1`; numeric accumulation follows plan-01 deterministic
extended-precision reduction and stores finite double output. A declared population
denominator is a different risk-model version and is not the built-in sample estimator.

EWMA uses strictly positive weights proportional to
`decay ** age_ordinal`, where age zero is the newest included observation and
`0 < decay < 1`. Weights normalize to one. The weighted mean is subtracted and the
covariance denominator is `1 - sum(weight**2)`; an insufficient effective sample size is a
typed state. The exact schedule determines age ordinals, including holidays and missing
observations.

### 10.3 Shrinkage covariance

`fixed_shrinkage` computes
`(1 - alpha) * sample_covariance + alpha * target` for finite
`0 <= alpha <= 1`. Initial targets are diagonal sample variance and scaled identity, with
the target choice and scale definition explicit. `ledoit_wolf` uses the reviewed
scikit-learn implementation through the `research` extra; package version, algorithm
adapter, centering, matrix ordering, and returned shrinkage coefficient enter identity.
It requires the declared complete-case matrix; pairwise Ledoit-Wolf is unsupported rather
than approximated. No implementation substitution occurs when the extra is unavailable.

### 10.4 User covariance and factor models

A user covariance input is a typed point-in-time relation with exact asset IDs, symmetric
entries, unit/horizon, availability, schema, lineage, and safety—not a caller ndarray.
The service canonicalizes the lower triangle and rejects missing diagonal/asymmetry beyond
tolerance.

A user factor model supplies ordered factor IDs, asset exposures `B`, factor covariance
`F`, and nonnegative idiosyncratic variances `D`, with
`Sigma = B F B' + diag(D)`. Every component has availability/lineage. Factor names alone
do not establish identity. Missing asset exposures follow the model's explicit exclude or
fail policy; zero exposure is never an implicit fill. `F` must itself satisfy the declared
symmetry/PSD policy before assembly.

### 10.5 PSD validation and repair

The service symmetrizes only by validating `abs(a_ij - a_ji) <= symmetry_tolerance` and
then using their deterministic average. It computes eigenvalues in canonical asset order.
A matrix is accepted when its minimum eigenvalue is at least
`-psd_tolerance * max(1, max_abs_eigenvalue)`.

With `PsdPolicy.FAIL`, any lower value yields `non_psd`. With
`EIGENVALUE_CLIP`, the symmetric eigendecomposition replaces eigenvalues below the
declared nonnegative floor, reconstructs the matrix, restores symmetry, and revalidates.
Before/after minimum eigenvalue, Frobenius adjustment, diagonal change, tolerances, and
algorithm/library identity are persisted. Repair never silently preserves a `safe`
summary if finite/diagonal/unit checks fail.

Every variance diagonal must be nonnegative. A raw value below the declared negative-
variance tolerance fails even if the eigenvalue test would otherwise accept it; a value
within tolerance may become exact zero only through the registered normalization, with raw/
normalized roots and diagonal adjustment persisted, followed by full revalidation.

For a factor model, eigenvalue repair applies to `F` before `Sigma` is assembled. The
assembled matrix is then revalidated and must pass tolerance; an independent dense clip
that would make stored `B`, `F`, and `D` inconsistent is not permitted in the initial
factor contract.

Volatility is the nonnegative square root of the corresponding covariance diagonal after
the declared repair. Correlation divides by positive volatility products; zero-variance
assets receive a typed state rather than arbitrary zero correlation.

## 11. Expected-cost contracts

### 11.1 Meaning and normalization

Expected costs estimate the cost of moving from current risky weights `w0` to target
weights `w` at one decision. The canonical risky trade-weight vector is `delta = w - w0`;
gross traded-notional fraction is `sum(abs(delta))`. Cost output is a nonnegative fraction
of decision NAV at the optimization horizon. At construction-time evaluation, inputs
expressed in money, price, shares, spread, or volume require exact USD decision prices,
NAV, and quantity/weight conversion evidence from the current-state capability.

The standalone cost materialization is a state-independent point-in-time native-unit
surface `C_decision(delta; NAV, prices, multipliers)`. It freezes schedules, coefficients,
domains, market inputs, and conversion formulas but does not bind a particular NAV, current
portfolio, or target. Construction supplies those arguments and persists their exact roots;
the same surface can therefore be evaluated against different legitimate state paths
without pretending the resulting expected costs are the same occurrence.

The ex-ante estimate is an objective/input artifact. Plans 12–13 may use the same
calibration definition but realized fees, spread, slippage, impact, and timing are computed
from actual orders/fills and stored separately. Neither value overwrites or reconciles by
identity with the other.

### 11.2 Built-in components

- `fees` applies a registered per-notional/per-unit/tier schedule to absolute proposed
  trade, with currency, venue, and minimum/maximum rules declared;
- `half_spread` applies one half of a causal bid/ask spread or registered spread estimate
  to absolute notional;
- `linear_impact` applies a nonnegative coefficient times absolute trade weight;
- `square_root_impact` applies a nonnegative coefficient times volatility times
  `sqrt(abs(trade_notional) / eligible_volume_notional)` times absolute trade weight; and
- `composite` sums ordered compatible components after unit/NAV normalization.

The exact square-root formula, annualized-to-horizon volatility conversion, ADV window,
USD price basis, participation cap, and zero/missing-volume behavior are versioned. Initial
coefficients are fixed registered values or come from a user-supplied point-in-time cost
relation with exact keys, availability, units, supported trade domain, lineage, and safety.
Managed calibration from historical fills/returns is deferred until plans 13–15 define a
typed cost-fit artifact and membership/release contract; caller-fitted mutable state is not
accepted here.

For a convex optimization, the registered cost formulation must be convex on its declared
domain and represented by the exact canonical expression. A nonconvex user cost can be
reported diagnostically or used by a compatible specialized constructor, but the general
CVXPY path rejects it. Linearization point and approximation bounds are identity-bearing;
an undocumented approximation is prohibited.

In particular, zero-trade discontinuities, capped charges, and nonconvex tier/minimum-fee
schedules are not automatically placed in the convex objective. They remain exact post-
candidate diagnostics or require a separately registered convex upper-bound/formulation
whose changed economics is explicit.

### 11.3 Missing, extrapolation, and audit

An absent spread, price, volatility, or volume follows the explicit action: exclude asset,
use a registered conservative bound, or fail. Zero volume is not missing and normally
prevents increasing exposure. Extrapolation beyond calibrated trade/participation range
either fails or applies a declared conservative extension. Each decision/asset/component
row stores input states, coefficient/domain availability, and reason; construction-time
evaluation additionally stores proposed delta and expected cost. Surface availability is
the maximum of every used schedule/coefficient/market input plus the registered delay, and
a composite takes the maximum across participating components.

## 12. Constraint contracts

### 12.1 Common normalization

Constraints operate on risky-asset target weights `w`, current weights `w0`, benchmark
weights `b`, cash weight `c`, and an optional risk matrix at one decision. Weights are
fractions of positive decision NAV. Assets follow the exact construction-asset manifest in
canonical instrument-ID order. The target budget is:

```text
c + sum(w_i) = 1
```

unless a version explicitly models an external capital sleeve. Gross exposure is
`sum(abs(w_i))`; net risky exposure is `sum(w_i)`; one-way turnover is
`0.5 * (sum(abs(w_i - w0_i)) + abs(c - c0))`, including current/target cash so a
cash-to-asset investment is not halved; active weight is `w - b`; and tracking error is
`sqrt((w - b)' Sigma (w - b))` at the declared horizon.

Every term compiles to a canonical typed expression and also has an independent evaluator.
Lower/upper bounds are closed after the registered numeric tolerance. A hard violation
larger than tolerance makes a candidate target invalid. A soft term introduces a
nonnegative named slack with declared unit and finite positive penalty; the slack/value/
penalty are persisted.

### 12.2 Position, exposure, cash, and leverage

- long-only is `w_i >= 0`; long-short uses explicit per-asset/default lower and upper
  bounds;
- position bounds may vary by exact point-in-time classification or instrument selector;
- gross and net exposure use declared portfolio-level bounds;
- group constraints apply `sum(w_i)` or active `sum(w_i - b_i)` over exact plan-04
  membership roots for sector, industry, or a registered grouping;
- cash constrains `c`, including whether borrowing/negative cash is permitted; and
- leverage constrains a named measure from the plan-11 pretrade leverage-measure registry
  (initially `persistra.leverage.gross_market_value_over_equity@1`), not an ambiguous
  synonym for gross exposure.

Conflicting lower/upper bounds, impossible cash/net combinations, and group roots that do
not cover required assets reject in symbolic preflight where provable. Classification
membership is evaluated as of the decision cutoff. Current sector labels cannot be applied
retrospectively.

Margin constraints require a point-in-time margin-requirement view from plan 11 and can
only provide pretrade target feasibility. They do not guarantee broker acceptance,
intraday maintenance, forced liquidation, or settlement behavior. When the accounting
capability or required exact view is unavailable, such a term is an unavailable capability,
not an approximate gross bound.

### 12.3 Factor and benchmark-relative constraints

Factor exposure uses a point-in-time matrix `B`; portfolio exposure is `B' w`, and active
exposure is `B' (w - b)`. Factor IDs/order, units, scaling, availability, missing policy,
and exposure root are exact. A missing loading cannot default to zero unless the registered
factor model itself defines zero as an observed value.

Benchmark-relative position/group/factor terms require one exact plan-06 benchmark
composition at the decision, with weights normalized under its declared policy. Assets
outside the benchmark have explicit zero benchmark weight only after the benchmark adapter
proves nonmembership. Missing benchmark coverage or incompatible currency/schedule fails.

Tracking error requires a compatible PSD risk estimate and nonnegative upper bound. The
optimizer uses the equivalent convex quadratic/SOC form; the independent evaluator reports
the square-root measure. It never squares a bound without checking units and finiteness.

### 12.4 Turnover, liquidity, capacity, and borrow

Turnover binds exact current weights and may have portfolio/group/asset bounds. It is
target turnover, not filled turnover. An absent current position is zero only when the
current-state capability proves the instrument is not held; an omitted instrument is not
evidence.

Liquidity/capacity constrains absolute target trade notional against a declared fraction
of causally available volume/ADV or a typed capacity relation. Conversion uses exact USD
NAV, prices, contract multipliers, and decision availability. It does not enforce order-
level participation through time; plan 13 owns that realized rule.

Short-side bounds may require a point-in-time borrow-availability/rate view from plan 11.
If no borrow capability exists, a constructor may either forbid new negative weights or
fail as declared. An unconstrained short target cannot claim borrow feasibility.

### 12.5 Missing actions and optional terms

`exclude_asset` adds exact zero/current-only bounds as declared and records the reason. A
nonheld asset still required in the effective vector is `fixed_zero`; a held current-only
asset is `retained_ineligible`; an audit-only nonheld asset may remain `excluded` with no
target value.
`use_declared_bound` uses a conservative finite value registered in the term.
`disable_with_warning` is allowed only for a term explicitly marked optional, records
`not_applicable`/finding, changes the effective constraint-manifest root, and makes the
result unsafe for simulation unless separately acknowledged. `fail` is the default.

A hard term cannot be disabled by solver behavior. Constraints that disappear through
presolve remain in the independent evaluator and output audit. Every target decision has
one evaluation row per registered term, including not-applicable terms.

## 13. Portfolio constructors

### 13.1 Common input and eligibility

A construction request resolves:

- exact constructor/constraint/cost versions and parameters;
- one decision bundle and ordered target decisions;
- selected signal or forecast outputs with declared meaning;
- optional point-in-time risk, expected-cost surface, benchmark, factor, group, current-state,
  margin, and borrow capabilities, including an exact per-decision state path when more
  than one state-dependent decision is precomputed;
- gross/net/cash/risk budgets and parent-capital allocation where applicable;
- safety/licensing, implementation/environment/numeric policy, solver capability, limits,
  construction timing, and fallback; and
- requested target intent and output schema.

The target-decision selector is nonempty and contains unique decisions in schedule order.
If no selected term/component requires current state, the request uses a canonical empty
state manifest. If any does, every target decision has exactly one compatible view; a
single view cannot be reused across multiple decisions by implication. Any nonzero
expected-cost objective requires current state because it evaluates `w - w0`; the explicit
zero-cost model does not.

Asset eligibility is the intersection of the base universe and every required input's
computed/available domain after registered missing actions. Each excluded asset and input
gets a stable reason. Assets held currently but newly ineligible remain in the normalized
input with explicit liquidate, retain, or fail behavior; they cannot vanish from turnover
or exposure calculations. `liquidate` has target weight zero; `retained_ineligible` has the
exact current weight. A nonheld `excluded` asset has no target value.

The ordered construction-asset manifest is the exact union of base-universe audit assets,
current holdings, and nonzero benchmark constituents required by active constraints/
diagnostics. Every required nonzero benchmark constituent must already have exact base-key
coverage at that decision; the union notation prevents eligibility filtering from dropping
it, not a join to an unrelated universe. A nonheld ineligible asset that must remain in the
full target/active vector uses `fixed_zero` with exact target zero; this includes a covered
benchmark constituent that cannot be purchased. Such an asset remains in benchmark,
factor, group, and risk evaluation. `excluded` is reserved for an audit asset not required
in the effective vector. An unknown held/benchmark instrument or missing required base,
covariance, or exposure coverage fails rather than disappearing.

Mandatory liquidate/retain weights are fixed before allocation. Every constructor solves
or normalizes only the residual risky/net/gross/cash budget after those fixed weights and
their exposure/constraint contributions; it does not allocate a full budget and append
retained holdings afterward. An infeasible residual budget fails in preflight or common
evaluation. A retained holding remains in every risk/factor/group/benchmark input required
to evaluate the full target; missing exposure is not replaced with zero.

All constructors produce risky weights/cash, objective/diagnostic components, constraint
evaluations, and states through the same target schema. A simple constructor does not gain
permission to skip constraints: it constructs a candidate and the common evaluator either
accepts it or invokes the configured failure policy.

A non-solver constructor records a `constructed` attempt only after its candidate passes
independent evaluation; a structural/numeric candidate failure records
`construction_failed` with its stable reason. It never uses solver-native `optimal` or
`infeasible` labels. Solver-backed attempts retain the exact
`OptimizationAttemptStatus` vocabulary. Simple attempts use the same logical-availability
sequence in section 14.3.

### 13.2 Equal weight

Long-only equal weight assigns the residual risky net budget equally across eligible
assets. A market-neutral long-short form requires explicit long and short sets and residual
gross leg budgets after fixed holdings; it assigns equal absolute weights within each leg.
Empty required legs, overlap, or incompatible budgets fail. Benchmark-relative equal active
weight is a different constructor version.

### 13.3 Score-proportional and quantile long-short

Score-proportional allocation accepts `allocation_score` or an explicit mapping from a
compatible signal. Positive and negative scores normalize separately to declared long and
short gross budgets using deterministic extended-precision sums. A zero-sum required leg
fails or follows a registered cash/retain fallback; it never divides silently.

Quantile long-short uses the exact rank/tie semantics in section 9 and predeclares
`0 <= short_cutoff < long_cutoff <= 1`. The short leg contains ranks no greater than
`short_cutoff`; the long leg contains ranks no less than `long_cutoff`. Boundary ties use
the signal's average rank and may make realized leg counts unequal; middle ranks are
unselected. Each selected leg then applies equal or absolute-score weighting. This is a
true target portfolio, unlike plan-09 quantile-label diagnostics, and still has no fills or
returns.

### 13.4 Inverse volatility and risk parity

Inverse-volatility accepts positive point-in-time volatility from a compatible risk
estimate. Raw weight is `1 / volatility`; a declared floor may cap the inverse and enters
identity. Zero/noncomputed volatility follows explicit exclusion/fail behavior. Weights
normalize to the supported long-only risky budget before common constraint evaluation.

Initial risk parity supports long-only positive risk budgets with a PSD covariance and no
constraints that invalidate the registered convex log-barrier formulation. It solves:

```text
minimize 0.5 * x' Sigma x - sum_i(budget_i * log(x_i))
subject to x_i >= positive_floor
```

then normalizes `x` to the risky budget and independently verifies relative risk
contributions against tolerance. General long-short/equality-risk-contribution and
arbitrary constrained risk parity are unsupported, not approximated. A nonzero fixed
retained sleeve invalidates this initial formulation and therefore rejects; it is not
silently excluded from the contribution check.

### 13.5 Optimization constructors

Minimum-variance, mean-variance, maximum-diversification, and benchmark-relative
constructors use section 14 and require `optimize`. Their exact formulation and supported
constraint families are registered. A request whose constraint/cost/objective violates
disciplined convex programming or declared solver capabilities rejects before solve.

Maximum diversification initially supports the long-only conic reformulation with
positive asset volatility and homogeneous compatible constraints:

```text
minimize x' Sigma x
subject to volatility' x = 1
           x >= 0
```

The solution is normalized to the risky budget and then checked against the original
diversification-ratio objective/constraints. Nonhomogeneous constraints that cannot be
mapped through normalization are unsupported for this constructor.

### 13.6 Constructor/constraint support matrix

The implementation publishes a versioned machine-readable support matrix. At minimum:

| Constructor | Required capability | Initial supported constraints |
| --- | --- | --- |
| equal weight | eligible set | all compatible terms are independent post-checks; no constraint-aware adjustment |
| score proportional | allocation score | all compatible terms are post-checks; cap/renormalize requires a separate algorithm |
| quantile long-short | rank/score | all compatible terms are post-checks after explicit leg budgets |
| inverse volatility | risk diagonal | all compatible terms are post-checks after residual-budget normalization |
| risk parity | PSD covariance, conic solver | positive long-only bounds and compatible homogeneous gross/cash budget |
| minimum variance | PSD covariance, CVXPY | convex hard/soft terms from section 12 |
| mean variance | forecast/compatible expected-return signal, PSD covariance, CVXPY | convex hard/soft terms and convex expected cost |
| maximum diversification | PSD covariance/volatility, conic solver | long-only homogeneous terms only |
| benchmark relative | forecast/compatible expected-return signal, risk/benchmark, CVXPY | convex active, tracking-error, turnover, cost, and ordinary terms |

Simple-constructor cap redistribution is not implied. If implemented, its deterministic
water-filling algorithm, infeasibility behavior, and supported term set receive their own
constructor version and tests.

## 14. Convex optimization

### 14.1 Canonical problem forms

Mean-variance uses horizon-compatible values and the canonical minimization form:

```text
minimize
    - expected_return' w
    + risk_aversion * quad_form(w - risk_reference, Sigma)
    + expected_cost(w - w0)
    + sum(soft_penalty_j * slack_j)
subject to registered hard constraints and soft relaxations
```

`risk_reference` is zero for absolute risk and benchmark weights for active risk.
`risk_aversion` is finite and nonnegative; a zero value is legal only when the remaining
problem is bounded. Because expected return/cost are horizon returns while quadratic risk
has squared-return units, `risk_aversion` declares the matching inverse-return unit (or an
equivalent fully specified objective normalization) rather than masquerading as an
unqualified scalar. Minimum variance omits return/cost unless explicitly registered.
Benchmark-relative optimization uses active expected return/risk and persists absolute as
well as active target weights.

The `expected_return` vector must come from a forecast, or an explicitly compatible
`SignalMeaning.EXPECTED_RETURN` stage bypass, whose target is simple/excess return at the
optimization horizon. Rank, direction, probability, standardized score, allocation score,
log return, volatility, and price change reject here unless a separate registered direct/
fitted forecast has already mapped them to that expected-return contract.

Objective terms are recorded separately in canonical units at the returned candidate.
Scaling used for numerical conditioning is deterministic, bounded, persisted, and exactly
undone for diagnostics. An optimizer cannot compare a daily mean to annual covariance or
currency cost to fractional return.

### 14.2 Solver capability and selection

A `SolverPolicy` pins:

- solver qualified name, installed package/version/build, and supported cone/problem
  capabilities;
- deterministic-thread settings, random seed where relevant, warm-start setting, maximum
  iterations/time, absolute/relative/feasibility tolerances, and solver-specific bounded
  options;
- accepted candidate statuses and independent verification tolerances; and
- ordered fallback solvers, if any, each named explicitly.

There is no environment-dependent “best available” selection after execution identity
freezes. Preflight reports an actionable missing-`optimize` or missing-solver capability.
Optional solver fallback creates another attempt row and never hides the first status.

An iteration limit is a deterministic solver option. A wall-time limit is an operational
safety bound whose trigger may vary with machine load. Any published attempt whose outcome
depends on that bound has `OptimizationReplayStatus.WALL_TIME_LIMITED`; every result
containing such an attempt is ineligible for deterministic replay even though exact reuse
of the already verified stored artifact remains valid.

CVXPY expression graph, CVXPY version, canonicalization backend, solver adapter, solver
version, and numerical options enter execution identity. Warm starts are disabled by
default. If enabled, the warm-start source is an exact compatible prior result and the
final target must still satisfy deterministic output tolerances; the source ID/root is
recorded.

### 14.3 Solve and independent verification

Attempt timing is logical domain evidence, separate from wall-clock runtime. The primary
attempt starts no earlier than `max(decision_at, required input/current-state
availability)` and adds its explicit `Duration`. A triggered fallback starts at the prior
attempt's logical availability and adds its own delay. Every attempt stores the resulting
`logical_available_at`; zero delay is explicit. A solver wall-time timeout uses the
registered timeout boundary for this logical sequence and remains replay-ineligible; its
observed wall duration is provenance and never silently substitutes for the timing spec.

The optimizer:

1. resolves and freezes exact inputs;
2. runs symbolic capability/dimension/unit/convexity and obvious-infeasibility preflight;
3. constructs variables/expressions in canonical asset/term order;
4. captures matrix/vector/problem content roots before solve;
5. invokes one pinned solver attempt under resource limits;
6. validates status, shape, finiteness, and imaginary-part tolerance;
7. applies only declared deterministic near-zero normalization;
8. independently recomputes budget, objective components, every constraint/slack, risk,
   expected cost, gross/net/turnover/cash, and target states outside solver expressions;
9. accepts only if all required tolerances pass; otherwise marks `invalid_result`;
10. runs configured solver/constructor fallback if triggered; and
11. publishes every attempt, violations, final target, findings, manifests, and event in
    one transaction.

A solver may return a candidate on infeasible/unbounded/error status; it is never accepted.
NaN/Inf, wrong dimension, excessive asymmetry/residual, constraint violation, or objective
recalculation mismatch yields `invalid_result`. Tiny negative long-only weights may be set
to zero only under a declared normalization tolerance and only if budget renormalization
and all independent checks then pass; raw and normalized roots are retained.

### 14.4 Failure and fallback

Default `FallbackKind.NONE` publishes a failed construction result with attempt evidence
and no effective target rows for that failed decision. `retain_current` requires an exact
current-state capability and produces current risky/cash weights with `fallback_retained`
states after independently checking every constraint. Any hard violation makes the
fallback fail rather than claim success; a permitted soft violation records its exact
slack/penalty, and optional-term behavior remains explicit.

`registered_constructor` invokes one exact constructor version/parameter set with its own
support preflight. Recursive fallback is forbidden in 3.0. Trigger statuses are explicit;
for example, a timeout fallback need not run on structural `unsupported`. A successful
fallback yields `completed_with_fallback`, retains all failed attempts, and records the
fallback target as the only effective target. Reports/simulators must display the status.

Fallback definition, parameters, required input occurrences, and capabilities are resolved
and frozen before the primary attempt. Triggering cannot resolve `latest`, inspect a new
dataset, or acquire a capability that was absent from execution identity.

## 15. Target portfolios, current state, and multi-strategy intent

### 15.1 Current portfolio capability and external state paths

Plan 11 owns and synthesizes the `CurrentPortfolioView` capability from a reconciled
journal and complete point-in-time valuation. It supplies one exact decision-time state
identity, positive USD NAV, risky weights/quantities, USD cash, prices/contract
multipliers, unsettled/restricted state needed by declared constraints, and availability/
lineage.
A research fixture may implement the same typed interface from immutable hand-authored
opening state; it cannot masquerade as a completed accounting projection.

The capability distinguishes an absent position from an omitted/unknown asset and pins
valuation policy. More than one currency or any non-USD value is an unavailable capability
in 3.0. The initial listed-equity/ETF contract multiplier is the exact constant one; a
different multiplier requires a future typed instrument/accounting capability. Negative/
zero NAV rejects weight construction. Stale prices follow the declared valuation policy
and remain visible findings.

`CurrentPortfolioPath` is an immutable ordered map from each requested decision to one
exact `CurrentPortfolioView`. It may come from a hand-authored opening/path scenario or a
completed plan-11 projection available by those decisions. It is an external input whose
entire manifest enters construction identity; it is not inferred by applying prior targets.
Using a completed historical state path for counterfactual research retains that path's
provenance and does not claim a newly simulated path.

Only an opening-state fixture is safe by declaration at its one initial decision. A hand-
authored future path is an explicit opaque scenario unless a managed causal accounting
projection proves every transition; acknowledging it never relabels it safe. A completed
path retains its originating strategy/run/safety and cannot be presented as the endogenous
state of a different counterfactual run.

Each view is the reconciled state immediately before its decision and its state/valuation
evidence must be logically available by that decision's public cutoff; external governing
evidence must also satisfy the project cutoff when enabled. Later end-of-day, settlement,
correction, or run state cannot be backfilled into an earlier target.

A multi-decision precomputation may omit the path only when its constructor, constraints,
cost, fallback, and output diagnostics are all current-state-independent. Turnover,
expected trade cost, retain/liquidate handling, leverage/margin/borrow checks, and retain-
current fallback each require a view at every decision.

### 15.2 Target contract

At every targeted decision, a completed construction stores:

- exact decision/cutoff, attempt/outcome logical availability, and input occurrence roots;
- exact current-state ID for that decision when required, or an explicit no-state marker;
- every ordered construction-manifest asset with target weight/state/reason and optional
  current/benchmark/active weight;
- cash target, risky sum, gross/net, one-way turnover, expected return/risk/cost, and
  constructor-specific diagnostics;
- one evaluation row per constraint and one component row per objective/cost term;
- effective primary/fallback attempt and construction status; and
- safety, lineage, licensing, schema, and output content roots.

The `expected_risk` summary is never unitless generic “risk”: the constructor/output schema
declares whether it is variance, volatility, tracking error, or another registered measure,
with its exact horizon, return kind, reference, and unit. Objective rows separately retain
the quadratic or conic term actually optimized.

Target weights are desired post-rebalance economic exposures, not executable quantities.
No price rounding, lot size, minimum trade, open-order reconciliation, or cash reservation
is applied here. Plans 12–13 consume the same target under a separate rebalance policy and
record any implementation shortfall.

A target sequence has one row set for every scheduled construction decision, including
failed decisions. A materialization cannot omit a hard case and still call the interval
complete. `ConstructionStatus.FAILED` decisions have diagnostics but no effective weights;
downstream default behavior is fail, not implicit carry-forward.

The target at a nonfailed decision becomes usable only at its effective attempt's
`logical_available_at`; a failed outcome uses the final attempted instant. Plans 12–13 must
not submit/rebalance from a target before that instant, even when every market input was
available at the original decision cutoff.

### 15.3 Rebalance-policy boundary

This plan may use current weights for turnover/cost/constraint calculations, but it does
not decide whether or when to trade. Thresholds, buffers, minimum trade size, open-order
interaction, quantity rounding, order type, timing, and submission are plan-12/13 rebalance
and execution contracts. “Retain current” here is an explicit failed-construction fallback
target, not a rebalance no-op inferred by the simulator.

### 15.4 Multi-strategy intent

A child strategy may emit a `PortfolioIntentKind.CHILD_STRATEGY_WEIGHTS` artifact using the
same target schema plus child strategy identity and requested capital sleeve. A parent
constructor aligns exact decision keys and compatible instrument/currency/horizon meaning,
requires every child intent to be available by the parent input cutoff, then applies
registered capital, risk, exposure, correlation/diversification, and constraint rules.
Parent output is one ordinary absolute/benchmark-relative target and retains exact child
contribution roots.

Child weights are not independently booked portfolios; plan 11 deliberately does not
define strategy subledgers in the initial 3.0 surface. The simulator consumes only the
resolved parent target, so multi-strategy behavior needs no special fill/accounting path.
Recursive parent graphs are acyclic and bounded; missing/
failed child intent follows an explicit fail, zero-allocation, or retain-prior-child policy.
`retain_prior_child` is not hidden sequence state: each affected decision receives one
exact compatible prior-child-intent view available by its cutoff. A standalone sequence
binds that complete external view manifest, while a simulator supplies the endogenous
prior intent to the one-decision kernel. A missing first-decision prior intent fails.

### 15.5 Simulation-time construction

Plans 12–13 may invoke the same one-decision construction kernel after their accounting
owner supplies the endogenous current view. The kernel is side-effect free and
deterministic for replay-eligible policies; a wall-time-limited attempt retains the explicit
exception in its returned evidence. It returns the complete target/attempt/constraint
evidence for the run owner to persist in its isolated run/result transaction. It does not
open a research writer or publish a standalone `PortfolioConstructionResultId` during each
simulated decision.

A standalone result in this plan is therefore a precomputed research occurrence over
state-independent decisions or an exact external state path. A simulation-time target is
a run-owned decision artifact that retains constructor execution content, per-decision
input/current-state roots, and the same target schema. Plan 12 defines its typed run target
identity and atomic storage; it may consume a standalone complete result when compatible.

## 16. Execution identity, exact retry, concurrency, and completeness

### 16.1 Materialization identities

Signal, forecast, risk, and expected-cost execution content IDs hash canonical manifests
for:

- exact definition ID/version/content and resolved parameters;
- base build/composite snapshot/universe/schedule/cutoffs/base-key root;
- selected input occurrence/output/schema/availability/state roots;
- fit/release/training/selection roots where applicable;
- risk/cost windows, matrices, units, horizon conversions, and policies;
- implementation/environment/numeric/determinism/seed identities;
- safety/lineage/licensing roots and effective limits; and
- expected output schema and partition plan.

For a fit, `planned_fit_content_id` hashes the definition/parameters, exact build and
training/scoring membership roots, fit purpose/anchor/cutoff, preprocessing/model recipe,
selection/refit-recipe roots, implementation/environment/limits, resolved seed, and
expected fitted-state schema. It excludes the later capability, fit occurrence,
publication metadata, fitted-state roots, causal release, and event. The issued training
capability binds that planned ID. The actual fit `execution_content_id` then hashes the
planned ID plus the exact capability/authorization proof, without any fit UUID or output/
release root. This two-stage identity is acyclic and remains computable before allocation.

Construction execution identity additionally hashes constructor/constraint/cost versions,
the construction-asset manifest, exact empty or per-decision current-state manifest,
benchmark/risk/forecast/signal roots, child/prior-child intent roots, solver policy/
capability/problem form and any warm-start source root, construction timing, fallback,
target decisions, and intent. It excludes new occurrence IDs, publication times, physical/
staging names, lifecycle event IDs, solver wall-clock duration, logs, and its own output
root.

For replay-eligible work, equal execution identity must reproduce equal normalized rows/
content roots. A wall-time-limited result identifies the same exact request but makes no
fresh re-execution equality claim; exact retry returns and verifies the one stored
occurrence without rerunning it. Equal economic values reached through a different
definition, fit, covariance repair, solver, tolerance, constraint, or fallback are
different executions.

### 16.2 Exact retry and concurrent requests

The service computes execution identity before durable output allocation. An existing
occurrence is returned only after verifying metadata, controlled rows, dynamic schema,
row/count/content manifests, safety/findings, and event. Missing/extra/changed evidence is
corruption. It does not allocate another UUID or event.

Concurrent identical requests serialize through the research lease/unique execution key.
The loser verifies and returns the winner. Different requests never share staging or
physical relations. Readers observe either the prior state or the complete committed
occurrence. Cancellation or process failure before publication exposes no partial target;
a terminal numerical attempt and fallback, when published, commit as one complete result.

### 16.3 Completeness invariants

For each occurrence:

- signal/forecast targeted base-key counts equal their state/audit counts, while every
  construction decision reconciles its target/audit rows to the exact construction-asset
  manifest including current-held and benchmark-only additions;
- every computed signal/forecast row has exact input availability and domain evidence;
- every direct prediction row names no fit/release and has one direct eligibility proof;
  every fitted computed prediction names exactly one eligible fit and passing causal
  release;
- risk asset/triangle/factor/pair-count manifests reconcile to their declared dimensions;
- every proposed trade/cost component and every registered constraint term has an audit
  state per applicable decision/scope;
- every accepted target has one effective attempt, exact cash/budget reconciliation, and
  no hard violation beyond tolerance; and
- summary counts and roots match dynamic relations, findings, and lifecycle payload.

An empty eligible universe may publish a typed failed/no-target decision only when the
constructor definition declares empty behavior. An empty relation has the plan-01 canonical
empty content root; missing output is not an empty success.

## 17. Metadata and physical schemas

The following DDL fixes logical columns and constraints. Migration code adds foreign keys,
indexes, generated-relation ownership, and DuckDB compatibility checks described below.
Canonical JSON fields are bounded reproduction evidence validated by typed constructors;
they are not caller extension bags.

### 17.1 Registered component versions

```sql
CREATE TABLE portfolio.component_definitions (
    component_definition_id UUID PRIMARY KEY,
    component_kind VARCHAR NOT NULL CHECK (
        component_kind IN (
            'signal', 'forecast', 'risk_model', 'expected_cost_model',
            'constraint_set', 'portfolio_constructor'
        )
    ),
    qualified_name VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (component_kind, qualified_name)
);

CREATE TABLE portfolio.component_versions (
    component_definition_id UUID NOT NULL,
    component_kind VARCHAR NOT NULL CHECK (
        component_kind IN (
            'signal', 'forecast', 'risk_model', 'expected_cost_model',
            'constraint_set', 'portfolio_constructor'
        )
    ),
    semantic_version VARCHAR NOT NULL,
    registration_sequence INTEGER NOT NULL CHECK (registration_sequence >= 1),
    description VARCHAR NOT NULL,
    assumptions_and_limitations VARCHAR NOT NULL,
    input_schema_content_id VARCHAR NOT NULL,
    parameter_schema_content_id VARCHAR NOT NULL,
    output_schema_content_id VARCHAR NOT NULL,
    availability_policy_content_id VARCHAR NOT NULL,
    missing_policy_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    numeric_policy_content_id VARCHAR NOT NULL,
    default_limits_content_id VARCHAR NOT NULL,
    required_capability_manifest_content_id VARCHAR NOT NULL,
    licensing_policy_content_id VARCHAR NOT NULL,
    definition_schema_version INTEGER NOT NULL CHECK (definition_schema_version >= 1),
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (component_definition_id, semantic_version),
    UNIQUE (component_definition_id, registration_sequence),
    CHECK (length(semantic_version) BETWEEN 5 AND 32),
    CHECK (length(description) <= 65536),
    CHECK (
        length(assumptions_and_limitations) > 0
        AND length(assumptions_and_limitations) <= 65536
    )
);

CREATE TABLE portfolio.constraint_terms (
    constraint_set_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    term_ordinal INTEGER NOT NULL CHECK (term_ordinal >= 1),
    term_name VARCHAR NOT NULL,
    constraint_kind VARCHAR NOT NULL CHECK (
        constraint_kind IN (
            'long_short_bounds', 'position_bounds', 'gross_exposure',
            'net_exposure', 'group_exposure', 'factor_exposure',
            'benchmark_relative', 'turnover', 'liquidity_capacity', 'borrow',
            'cash', 'leverage', 'margin', 'tracking_error'
        )
    ),
    hardness VARCHAR NOT NULL CHECK (hardness IN ('hard', 'soft')),
    missing_action VARCHAR NOT NULL CHECK (
        missing_action IN (
            'exclude_asset', 'use_declared_bound', 'disable_with_warning', 'fail'
        )
    ),
    term_content_id VARCHAR NOT NULL,
    term_json JSON NOT NULL,
    PRIMARY KEY (constraint_set_id, semantic_version, term_ordinal),
    UNIQUE (constraint_set_id, semantic_version, term_name),
    UNIQUE (constraint_set_id, semantic_version, term_content_id)
);
```

The repository proves that definition/version `component_kind` values agree and that each
typed ID kind matches its expected repository. It parses/validates exact plan-08 semantic
versions, enforces monotonic versions and contiguous registration sequence, validates the
kind-specific JSON against its schema, and reconciles every ordered child manifest. The
required-capability manifest is an ordered set of installation/runtime capabilities, not a
single environment-dependent package string.
Constraint ordinals are contiguous from one and their ordered root equals the version's
constraint manifest. A constructor stores an exact referenced constraint-set version/
content in its typed definition JSON.

### 17.2 Signal and forecast occurrences

```sql
CREATE TABLE portfolio.signal_materializations (
    signal_materialization_id UUID PRIMARY KEY,
    signal_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    decision_eligibility_manifest_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque')
    ),
    targeted_row_count BIGINT NOT NULL CHECK (targeted_row_count >= 0),
    computed_row_count BIGINT NOT NULL CHECK (computed_row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (computed_row_count <= targeted_row_count),
    CHECK (
        safety_status <> 'safe'
        OR (
            information_class = 'causal'
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);

CREATE TABLE portfolio.forecast_fits (
    forecast_fit_id UUID PRIMARY KEY,
    forecast_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    decision_input_manifest_content_id VARCHAR NOT NULL,
    label_input_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    planned_fit_content_id VARCHAR NOT NULL,
    validation_plan_id UUID NOT NULL,
    validation_fold_ordinal INTEGER,
    fit_purpose VARCHAR NOT NULL CHECK (
        fit_purpose IN (
            'fold_training', 'inner_selection', 'selected_refit',
            'final_holdout_refit', 'historical_production'
        )
    ),
    fit_anchor_at TIMESTAMPTZ NOT NULL,
    fit_cutoff_at TIMESTAMPTZ NOT NULL,
    fit_delay_us BIGINT NOT NULL CHECK (fit_delay_us >= 0),
    maximum_label_end_at TIMESTAMPTZ,
    maximum_input_available_at TIMESTAMPTZ,
    maximum_label_available_at TIMESTAMPTZ,
    fit_available_at TIMESTAMPTZ,
    training_membership_content_id VARCHAR NOT NULL,
    scoring_membership_content_id VARCHAR NOT NULL,
    training_capability_content_id VARCHAR NOT NULL,
    selection_capability_content_id VARCHAR,
    selection_manifest_content_id VARCHAR,
    holdout_state_content_id VARCHAR NOT NULL,
    training_root_manifest_content_id VARCHAR NOT NULL,
    state_schema_manifest_content_id VARCHAR NOT NULL,
    preprocessor_state_content_id VARCHAR,
    model_state_content_id VARCHAR,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    fit_state VARCHAR NOT NULL CHECK (
        fit_state IN (
            'completed', 'insufficient_samples', 'singular',
            'invalid_numeric', 'failed_convergence'
        )
    ),
    causal_release_content_id VARCHAR,
    information_class VARCHAR NOT NULL CHECK (information_class = 'label'),
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    training_row_count BIGINT NOT NULL CHECK (training_row_count >= 0),
    scoring_row_count BIGINT NOT NULL CHECK (scoring_row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (fit_purpose = 'final_holdout_refit' AND validation_fold_ordinal IS NULL)
        OR
        (fit_purpose <> 'final_holdout_refit'
         AND validation_fold_ordinal IS NOT NULL
         AND validation_fold_ordinal >= 1)
    ),
    CHECK (fit_cutoff_at <= fit_anchor_at),
    CHECK (maximum_label_end_at IS NULL OR maximum_label_end_at <= fit_cutoff_at),
    CHECK (
        maximum_input_available_at IS NULL
        OR maximum_input_available_at <= fit_cutoff_at
    ),
    CHECK (
        maximum_label_available_at IS NULL
        OR maximum_label_available_at <= fit_cutoff_at
    ),
    CHECK (fit_available_at IS NULL OR fit_anchor_at <= fit_available_at),
    CHECK (
        (fit_state = 'completed'
         AND training_row_count > 0
         AND maximum_label_end_at IS NOT NULL
         AND maximum_input_available_at IS NOT NULL
         AND maximum_label_available_at IS NOT NULL
         AND fit_available_at IS NOT NULL
         AND preprocessor_state_content_id IS NOT NULL
         AND model_state_content_id IS NOT NULL)
        OR
        (fit_state <> 'completed'
         AND fit_available_at IS NULL
         AND preprocessor_state_content_id IS NULL
         AND model_state_content_id IS NULL
         AND causal_release_content_id IS NULL)
    ),
    CHECK (
        causal_release_content_id IS NULL
        OR (
            fit_state = 'completed'
            AND fit_purpose IN (
                'selected_refit', 'final_holdout_refit', 'historical_production'
            )
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
            AND safety_status = 'safe'
        )
    )
);

CREATE TABLE portfolio.forecast_materializations (
    forecast_materialization_id UUID PRIMARY KEY,
    forecast_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    fit_manifest_content_id VARCHAR NOT NULL,
    causal_release_manifest_content_id VARCHAR NOT NULL,
    decision_eligibility_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    training_root_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque')
    ),
    targeted_row_count BIGINT NOT NULL CHECK (targeted_row_count >= 0),
    computed_row_count BIGINT NOT NULL CHECK (computed_row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (computed_row_count <= targeted_row_count),
    CHECK (
        safety_status <> 'safe'
        OR (
            information_class = 'causal'
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);
```

`validation_plan_id` is mandatory even for `historical_production`: its expanding/rolling
plan is the exact time-resolved training-membership authority, and each fit anchor binds
the matching fold while its test rows remain inaccessible to fitting. Only the plan-wide
`final_holdout_refit` has no fold ordinal. The repository additionally proves the role/
capability and holdout conditions not expressible in checks, including exact planned-fit/
capability agreement.
`maximum_input_available_at` covers selected feature inputs and
`maximum_label_available_at` covers labels; both must be no later than the logical fit
cutoff, which itself cannot follow the anchor. The logical delay computes
`fit_available_at` exactly from `fit_delay_us` using the plan-01 checked `Duration` rule.

Direct/combined-static forecast manifests use canonical empty fit, causal-release, and
training-root manifests while retaining a nonempty decision-eligibility manifest. Learned
combination uses the ordinary fit/release fields. A completed fitted value must have both
fit and release IDs; a noncomputed fitted row may have neither when no eligible released
fit exists. Completed fold-training/inner-selection fits retain model state for managed
evaluation but have no causal release and can never be selected by this inference path.

The controlled value relations have these exact logical columns and primary keys:

```sql
CREATE TABLE signal_data.signal_values (
    signal_materialization_id UUID NOT NULL,
    output_ordinal INTEGER NOT NULL CHECK (output_ordinal >= 1),
    instrument_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'input_missing', 'upstream_noncomputed',
            'not_scheduled', 'outside_scope', 'invalid_numeric'
        )
    ),
    value DOUBLE,
    available_at TIMESTAMPTZ,
    reason_code VARCHAR,
    input_state_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        signal_materialization_id, output_ordinal, decision_at, instrument_id
    ),
    CHECK (
        (state = 'computed'
         AND value IS NOT NULL
         AND available_at IS NOT NULL
         AND reason_code IS NULL)
        OR
        (state <> 'computed'
         AND value IS NULL
         AND available_at IS NULL
         AND reason_code IS NOT NULL)
    )
);

CREATE TABLE forecast_data.forecast_values (
    forecast_materialization_id UUID NOT NULL,
    output_ordinal INTEGER NOT NULL CHECK (output_ordinal >= 1),
    instrument_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'input_missing', 'fit_unavailable',
            'not_scheduled', 'outside_scope', 'invalid_numeric'
        )
    ),
    expected_value DOUBLE,
    uncertainty_value DOUBLE,
    lower_value DOUBLE,
    upper_value DOUBLE,
    forecast_fit_id UUID,
    causal_release_content_id VARCHAR,
    decision_eligibility_content_id VARCHAR NOT NULL,
    available_at TIMESTAMPTZ,
    reason_code VARCHAR,
    input_state_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        forecast_materialization_id, output_ordinal, decision_at, instrument_id
    ),
    CHECK (
        (state = 'computed'
         AND expected_value IS NOT NULL
         AND available_at IS NOT NULL
         AND reason_code IS NULL)
        OR
        (state <> 'computed'
         AND expected_value IS NULL
         AND uncertainty_value IS NULL
         AND lower_value IS NULL
         AND upper_value IS NULL
         AND available_at IS NULL
         AND reason_code IS NOT NULL)
    ),
    CHECK ((forecast_fit_id IS NULL) = (causal_release_content_id IS NULL)),
    CHECK (
        (lower_value IS NULL AND upper_value IS NULL)
        OR (
            lower_value IS NOT NULL
            AND upper_value IS NOT NULL
            AND lower_value <= upper_value
        )
    )
);
```

Signals use their distinct stable value-state vocabulary; a forecast input that did not
compute yields `upstream_noncomputed` with the upstream reason in its input-state root.
The repository enforces each definition's allowed state subset and value domain. A direct
forecast stores a decision-eligibility proof and has neither fit nor causal-release ID; a
fitted computed forecast stores both. Quantile uncertainty with more than one interval
uses a child controlled relation keyed by quantile ordinal rather than overloading the two
display columns. Supporting diagnostics use another versioned child relation keyed by
declared diagnostic ordinal/name/state; they are never free-form JSON columns.

### 17.3 Risk fits and materializations

```sql
CREATE TABLE portfolio.risk_model_fits (
    risk_model_fit_id UUID PRIMARY KEY,
    risk_model_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    decision_input_manifest_content_id VARCHAR NOT NULL,
    label_input_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    planned_fit_content_id VARCHAR NOT NULL,
    validation_plan_id UUID NOT NULL,
    validation_fold_ordinal INTEGER,
    fit_purpose VARCHAR NOT NULL CHECK (
        fit_purpose IN (
            'fold_training', 'inner_selection', 'selected_refit',
            'final_holdout_refit', 'historical_production'
        )
    ),
    fit_anchor_at TIMESTAMPTZ NOT NULL,
    fit_cutoff_at TIMESTAMPTZ NOT NULL,
    fit_delay_us BIGINT NOT NULL CHECK (fit_delay_us >= 0),
    maximum_label_end_at TIMESTAMPTZ,
    maximum_input_available_at TIMESTAMPTZ,
    maximum_label_available_at TIMESTAMPTZ,
    fit_available_at TIMESTAMPTZ,
    training_membership_content_id VARCHAR NOT NULL,
    scoring_membership_content_id VARCHAR NOT NULL,
    training_capability_content_id VARCHAR NOT NULL,
    selection_capability_content_id VARCHAR,
    selection_manifest_content_id VARCHAR,
    holdout_state_content_id VARCHAR NOT NULL,
    asset_manifest_content_id VARCHAR NOT NULL,
    pair_count_manifest_content_id VARCHAR NOT NULL,
    training_root_manifest_content_id VARCHAR NOT NULL,
    state_schema_manifest_content_id VARCHAR NOT NULL,
    raw_matrix_content_id VARCHAR,
    repair_diagnostic_content_id VARCHAR,
    fitted_state_content_id VARCHAR,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    fit_state VARCHAR NOT NULL CHECK (
        fit_state IN (
            'completed', 'insufficient_samples', 'singular',
            'invalid_numeric', 'failed_convergence'
        )
    ),
    causal_release_content_id VARCHAR,
    information_class VARCHAR NOT NULL CHECK (information_class = 'label'),
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    asset_count BIGINT NOT NULL CHECK (asset_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (
        (fit_purpose = 'final_holdout_refit' AND validation_fold_ordinal IS NULL)
        OR
        (fit_purpose <> 'final_holdout_refit'
         AND validation_fold_ordinal IS NOT NULL
         AND validation_fold_ordinal >= 1)
    ),
    CHECK (fit_cutoff_at <= fit_anchor_at),
    CHECK (maximum_label_end_at IS NULL OR maximum_label_end_at <= fit_cutoff_at),
    CHECK (
        maximum_input_available_at IS NULL
        OR maximum_input_available_at <= fit_cutoff_at
    ),
    CHECK (
        maximum_label_available_at IS NULL
        OR maximum_label_available_at <= fit_cutoff_at
    ),
    CHECK (fit_available_at IS NULL OR fit_anchor_at <= fit_available_at),
    CHECK (
        (fit_state = 'completed'
         AND observation_count > 0
         AND asset_count > 0
         AND maximum_label_end_at IS NOT NULL
         AND maximum_input_available_at IS NOT NULL
         AND maximum_label_available_at IS NOT NULL
         AND fit_available_at IS NOT NULL
         AND fitted_state_content_id IS NOT NULL)
        OR
        (fit_state <> 'completed'
         AND fit_available_at IS NULL
         AND fitted_state_content_id IS NULL
         AND causal_release_content_id IS NULL)
    ),
    CHECK (
        causal_release_content_id IS NULL
        OR (
            fit_state = 'completed'
            AND fit_purpose IN (
                'selected_refit', 'final_holdout_refit', 'historical_production'
            )
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
            AND safety_status = 'safe'
        )
    )
);

CREATE TABLE portfolio.risk_materializations (
    risk_materialization_id UUID PRIMARY KEY,
    risk_model_definition_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    fit_manifest_content_id VARCHAR NOT NULL,
    causal_release_manifest_content_id VARCHAR NOT NULL,
    decision_eligibility_manifest_content_id VARCHAR NOT NULL,
    horizon_conversion_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque')
    ),
    targeted_decision_count BIGINT NOT NULL CHECK (targeted_decision_count >= 1),
    computed_decision_count BIGINT NOT NULL CHECK (computed_decision_count >= 0),
    covariance_entry_count BIGINT NOT NULL CHECK (covariance_entry_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (computed_decision_count <= targeted_decision_count),
    CHECK (
        safety_status <> 'safe'
        OR (
            information_class = 'causal'
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);
```

The risk output schema includes estimate headers keyed by
`(risk_materialization_id, decision_at)` with a nullable `risk_model_fit_id` and release;
ordered asset rows for volatility/state; canonical lower-triangle covariance rows
`(asset_i_ordinal, asset_j_ordinal)` with `i >= j`, value, pair count, unit, and state; and,
for factors, factor headers/covariance, asset-factor loadings, and idiosyncratic variance.
Every computed header records minimum eigenvalue before/after, PSD policy/tolerance,
adjustment norm, horizon/frequency, availability, decision-eligibility root, and optional
causal-fit release. User-supplied covariance/factor estimates use canonical empty fit/
release manifests and a direct eligibility proof. Fitted estimates use the same
fit-purpose, fold, training/scoring capability, selection, and holdout rules as forecast
fits. Completed fold-training/inner-selection risk fits retain fitted state for managed
evaluation but have no causal release and cannot back a decision estimate. Count/root
checks prove triangle size `n * (n + 1) / 2` for every dense computed estimate.

### 17.4 Costs, construction results, attempts, targets, and constraints

```sql
CREATE TABLE portfolio.expected_cost_materializations (
    expected_cost_materialization_id UUID PRIMARY KEY,
    expected_cost_model_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    decision_eligibility_manifest_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque')
    ),
    targeted_row_count BIGINT NOT NULL CHECK (targeted_row_count >= 0),
    computed_row_count BIGINT NOT NULL CHECK (computed_row_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (computed_row_count <= targeted_row_count),
    CHECK (
        safety_status <> 'safe'
        OR (
            information_class = 'causal'
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);

CREATE TABLE portfolio.construction_results (
    portfolio_construction_result_id UUID PRIMARY KEY,
    portfolio_constructor_id UUID NOT NULL,
    semantic_version VARCHAR NOT NULL,
    constraint_set_id UUID NOT NULL,
    constraint_set_semantic_version VARCHAR NOT NULL,
    expected_cost_materialization_id UUID,
    expected_cost_model_id UUID,
    expected_cost_model_semantic_version VARCHAR,
    research_dataset_build_id UUID NOT NULL,
    composite_snapshot_id UUID NOT NULL,
    universe_evaluation_id UUID NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    construction_asset_manifest_content_id VARCHAR NOT NULL,
    current_state_manifest_content_id VARCHAR NOT NULL,
    input_manifest_content_id VARCHAR NOT NULL,
    parameter_content_id VARCHAR NOT NULL,
    schedule_content_id VARCHAR NOT NULL,
    cutoff_manifest_content_id VARCHAR NOT NULL,
    construction_timing_content_id VARCHAR NOT NULL,
    solver_policy_content_id VARCHAR NOT NULL,
    fallback_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    output_schema_content_id VARCHAR NOT NULL,
    output_manifest_content_id VARCHAR NOT NULL,
    attempt_manifest_content_id VARCHAR NOT NULL,
    constraint_evaluation_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (
        information_class IN ('causal', 'opaque')
    ),
    construction_status VARCHAR NOT NULL CHECK (
        construction_status IN ('completed', 'completed_with_fallback', 'failed')
    ),
    replay_status VARCHAR NOT NULL CHECK (
        replay_status IN ('eligible', 'wall_time_limited')
    ),
    nondeterminism_reason_code VARCHAR,
    targeted_decision_count BIGINT NOT NULL CHECK (targeted_decision_count >= 1),
    completed_decision_count BIGINT NOT NULL CHECK (completed_decision_count >= 0),
    target_row_count BIGINT NOT NULL CHECK (target_row_count >= 0),
    attempt_count BIGINT NOT NULL CHECK (attempt_count >= 1),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (completed_decision_count <= targeted_decision_count),
    CHECK (attempt_count >= targeted_decision_count),
    CHECK (
        (replay_status = 'eligible' AND nondeterminism_reason_code IS NULL)
        OR
        (replay_status = 'wall_time_limited' AND nondeterminism_reason_code IS NOT NULL)
    ),
    CHECK (
        (expected_cost_model_id IS NULL) =
        (expected_cost_model_semantic_version IS NULL)
    ),
    CHECK (
        (expected_cost_materialization_id IS NULL) =
        (expected_cost_model_id IS NULL)
    ),
    CHECK (
        safety_status <> 'safe'
        OR (
            information_class = 'causal'
            AND lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);

CREATE TABLE portfolio.optimization_attempts (
    portfolio_construction_result_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    attempt_ordinal INTEGER NOT NULL CHECK (attempt_ordinal >= 1),
    logical_available_at TIMESTAMPTZ NOT NULL,
    attempt_kind VARCHAR NOT NULL CHECK (
        attempt_kind IN ('primary', 'solver_fallback', 'constructor_fallback')
    ),
    constructor_content_id VARCHAR NOT NULL,
    solver_name VARCHAR,
    solver_version VARCHAR,
    problem_content_id VARCHAR NOT NULL,
    matrix_manifest_content_id VARCHAR NOT NULL,
    solver_options_content_id VARCHAR NOT NULL,
    warm_start_source_content_id VARCHAR,
    status VARCHAR NOT NULL CHECK (
        status IN (
            'constructed', 'construction_failed', 'optimal', 'optimal_inaccurate',
            'infeasible', 'unbounded', 'iteration_limit', 'solver_error', 'timeout',
            'invalid_result', 'unsupported'
        )
    ),
    replay_status VARCHAR NOT NULL CHECK (
        replay_status IN ('eligible', 'wall_time_limited')
    ),
    raw_candidate_content_id VARCHAR,
    normalized_candidate_content_id VARCHAR,
    objective_component_content_id VARCHAR NOT NULL,
    violation_content_id VARCHAR NOT NULL,
    solver_diagnostic_content_id VARCHAR NOT NULL,
    iteration_count BIGINT CHECK (iteration_count IS NULL OR iteration_count >= 0),
    solver_wall_duration_us BIGINT CHECK (
        solver_wall_duration_us IS NULL OR solver_wall_duration_us >= 0
    ),
    accepted BOOLEAN NOT NULL,
    reason_code VARCHAR,
    PRIMARY KEY (
        portfolio_construction_result_id, decision_at, attempt_ordinal
    ),
    CHECK (decision_at <= logical_available_at),
    CHECK (NOT accepted OR normalized_candidate_content_id IS NOT NULL),
    CHECK (
        NOT accepted
        OR status IN ('constructed', 'optimal', 'optimal_inaccurate')
    ),
    CHECK (status <> 'constructed' OR accepted),
    CHECK ((status = 'timeout') = (replay_status = 'wall_time_limited'))
);

CREATE TABLE portfolio.constraint_evaluations (
    portfolio_construction_result_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    attempt_ordinal INTEGER NOT NULL CHECK (attempt_ordinal >= 1),
    term_ordinal INTEGER NOT NULL CHECK (term_ordinal >= 1),
    scope_ordinal INTEGER NOT NULL CHECK (scope_ordinal >= 1),
    evaluation_state VARCHAR NOT NULL CHECK (
        evaluation_state IN (
            'satisfied', 'violated', 'softened', 'not_applicable', 'input_missing'
        )
    ),
    actual_value DOUBLE,
    lower_bound DOUBLE,
    upper_bound DOUBLE,
    violation DOUBLE,
    slack_value DOUBLE,
    penalty_value DOUBLE,
    reason_code VARCHAR,
    PRIMARY KEY (
        portfolio_construction_result_id, decision_at,
        attempt_ordinal, term_ordinal, scope_ordinal
    ),
    CHECK (violation IS NULL OR violation >= 0),
    CHECK (slack_value IS NULL OR slack_value >= 0),
    CHECK (penalty_value IS NULL OR penalty_value >= 0)
);
```

Plan 11 defines the typed per-decision `current_portfolio_state_id` and path-manifest
adapter. Versioned opening/path fixtures remain distinct from reconciled endogenous state.
A cost materialization is the point-in-time native-unit surface
`C_decision(delta; NAV, prices, multipliers)`: its controlled rows store component
coefficients/domains/market-input availability and conversion formulas, not a current
portfolio, NAV, or target. Construction binds the current-state arguments, evaluates that
surface inside the objective and at the accepted target, and stores the resulting expected-
cost components and conversion roots with its attempt.

Target and summary output use fixed relations:

```sql
CREATE TABLE portfolio_data.target_weights (
    portfolio_construction_result_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'targeted', 'fixed_zero', 'excluded', 'input_missing',
            'liquidate', 'retained_ineligible', 'fallback_retained'
        )
    ),
    target_weight DOUBLE,
    current_weight DOUBLE,
    benchmark_weight DOUBLE,
    active_weight DOUBLE,
    reason_code VARCHAR,
    effective_attempt_ordinal INTEGER,
    PRIMARY KEY (
        portfolio_construction_result_id, decision_at, instrument_id
    ),
    CHECK (effective_attempt_ordinal IS NULL OR effective_attempt_ordinal >= 1),
    CHECK (
        (state = 'targeted' AND reason_code IS NULL)
        OR (state <> 'targeted' AND reason_code IS NOT NULL)
    ),
    CHECK (
        (state IN (
            'targeted', 'fixed_zero', 'liquidate',
            'retained_ineligible', 'fallback_retained'
        )) = (target_weight IS NOT NULL)
    )
);

CREATE TABLE portfolio_data.target_summaries (
    portfolio_construction_result_id UUID NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    outcome_available_at TIMESTAMPTZ NOT NULL,
    intent_kind VARCHAR NOT NULL CHECK (
        intent_kind IN (
            'absolute_weights', 'benchmark_relative_weights',
            'child_strategy_weights'
        )
    ),
    construction_status VARCHAR NOT NULL CHECK (
        construction_status IN ('completed', 'completed_with_fallback', 'failed')
    ),
    effective_attempt_ordinal INTEGER,
    cash_weight DOUBLE,
    current_cash_weight DOUBLE,
    current_portfolio_state_id UUID,
    risky_weight_sum DOUBLE,
    gross_exposure DOUBLE,
    net_exposure DOUBLE,
    one_way_turnover DOUBLE,
    expected_return DOUBLE,
    expected_risk DOUBLE,
    expected_cost DOUBLE,
    target_manifest_content_id VARCHAR,
    PRIMARY KEY (portfolio_construction_result_id, decision_at),
    CHECK (decision_at <= outcome_available_at),
    CHECK (effective_attempt_ordinal IS NULL OR effective_attempt_ordinal >= 1),
    CHECK (
        (current_portfolio_state_id IS NULL) = (current_cash_weight IS NULL)
    ),
    CHECK (
        (construction_status = 'failed'
         AND effective_attempt_ordinal IS NULL
         AND cash_weight IS NULL
         AND risky_weight_sum IS NULL
         AND gross_exposure IS NULL
         AND net_exposure IS NULL
         AND one_way_turnover IS NULL
         AND expected_return IS NULL
         AND expected_risk IS NULL
         AND expected_cost IS NULL
         AND target_manifest_content_id IS NULL)
        OR
        (construction_status <> 'failed'
         AND effective_attempt_ordinal IS NOT NULL
         AND cash_weight IS NOT NULL
         AND risky_weight_sum IS NOT NULL
         AND gross_exposure IS NOT NULL
         AND net_exposure IS NOT NULL
         AND target_manifest_content_id IS NOT NULL
         AND (
             (current_portfolio_state_id IS NULL AND one_way_turnover IS NULL)
             OR
             (current_portfolio_state_id IS NOT NULL AND one_way_turnover IS NOT NULL)
         ))
    )
);
```

The repository additionally enforces `fixed_zero.target_weight = 0`,
`liquidate.target_weight = 0`,
`retained_ineligible.target_weight = current_weight`, and
`fallback_retained.target_weight = current_weight`. These are exact state invariants, not
display conventions. `excluded` and `input_missing` rows have no target weight and do not
enter target budget/exposure sums; their reasons remain visible. For a nonfailed decision
whose effective constructor contract requires current state, the summary has a
`current_portfolio_state_id`/`current_cash_weight` matching the result's path manifest and a
computed turnover. A nonfailed state-independent decision has null state fields/turnover
and uses the canonical empty state manifest. A failed summary may retain its input current-
state ID/cash for diagnostics but has no effective target metrics or manifest.

Nonzero cost-surface rows are keyed by cost occurrence/decision/instrument/component and
contain trade domain, coefficients, input state/availability, and reason. Construction
cost-evaluation rows are keyed by result/decision/attempt/instrument/component and
additionally store delta/value for applicable nonzero components. The explicit `none`
model instead has one portfolio-scoped canonical zero component per decision occurrence and
per construction attempt, with no per-asset delta or current-state requirement. Objective-
component rows are keyed by result/decision/attempt/component and store canonical unscaled/
scaled values. Multi-strategy contribution rows key each parent target asset to child
intent and contribution; their sum reconciles to the pre-constraint and final target under
the registered attribution rule.

The repository enforces contiguous attempt/term/scope ordinals, exactly one accepted
attempt per completed decision, none per failed decision, monotone attempt logical
availability, outcome/effective-or-final-attempt availability agreement, effective-attempt
agreement, target/summary/budget/constraint/count/root reconciliation, and one final status
over the complete requested decision interval. Per decision, `completed` means its primary
attempt was accepted, `completed_with_fallback` means a later configured attempt was
accepted, and `failed` means no attempt was accepted. Top-level `completed` requires every
decision to complete on its primary attempt; `completed_with_fallback` requires every
decision to have an effective target and at least one fallback; any decision without an
effective target makes the top level `failed`. A sequence may retain successful decisions
beside failures only when the version declares partial-sequence publication; no downstream
simulation adapter is then issued until an explicit policy supplies every missing target.

For a simple-constructor attempt, `solver_name`/`solver_version`/warm-start/iteration/wall-
duration fields are null and solver option/diagnostic manifests are canonical empty. A
solver-native status produced by invocation requires the exact installed solver identity
and bounded diagnostics. A preflight `unsupported` attempt may instead retain the requested
solver policy/name with no installed version and a typed capability reason. `constructed`
is always accepted; `construction_failed` is never accepted.

Top-level replay status is `wall_time_limited` when any constituent attempt is wall-time-
limited; no counterfactual claim about whether the timeout would have changed a target can
restore eligibility. Otherwise it is `eligible`. Plan 14 must preserve that status and
cannot claim deterministic replay for a wall-time-limited construction.

Attempt solver diagnostics are a bounded typed manifest of native status, primal/dual
residuals, gap, iterations, wall duration, and available solver-specific counters. Missing
native fields are explicit states; raw unbounded logs are not stored there. Wall duration
is provenance only and is excluded from execution identity.

### 17.5 Model state, training audit, lineage, and safety

`model_data` contains migration-owned generated relations for each registered adapter's
typed state schema plus controlled common relations for fit candidate/score rows and
training sample audit. Every training-audit row stores fit ID, sample key, validation role,
fold/child ordinal, feature/label state roots, label interval/end/availability, inclusion,
and reason. Generated state relation names are resolved only by an internal UUID token;
public metadata/events never expose them.

Plan-07 safety findings attach to subject kinds:

- `signal_materialization`;
- `forecast_fit`;
- `forecast_materialization`;
- `risk_model_fit`;
- `risk_materialization`;
- `expected_cost_materialization`; and
- `portfolio_construction_result`.

Definition-only registration diagnostics are version validation, not decision-safety
findings. Occurrence root closure includes all ordinary decision roots and, for released
fits, a separately classified complete training-root manifest plus exact causal-release
proof. The same finding cannot be downgraded by a descendant. Structural label-access,
unauthorized role, incomplete causal release, invalid temporal inequality, or holdout
violation rejects without an override.

## 18. Public APIs and capability boundaries

### 18.1 Services and handles

The open project exposes narrow services:

```python no-run
project.services.portfolio.signals.register(definition)
project.services.portfolio.signals.materialize(request)
project.services.portfolio.forecasts.register(definition)
forecast_fit_plan = project.services.portfolio.forecasts.plan_fit(request)
forecast_training = project.services.research.validation.authorize_training(
    forecast_fit_plan.authorization_request
)
project.services.portfolio.forecasts.fit(forecast_fit_plan, capability=forecast_training)
project.services.portfolio.forecasts.materialize(request)
project.services.portfolio.risk_models.register(definition)
risk_fit_plan = project.services.portfolio.risk_models.plan_fit(request)
risk_training = project.services.research.validation.authorize_training(
    risk_fit_plan.authorization_request
)
project.services.portfolio.risk_models.fit(risk_fit_plan, capability=risk_training)
project.services.portfolio.risk_models.materialize(request)
project.services.portfolio.cost_models.register(definition)
project.services.portfolio.cost_models.materialize(request)
project.services.portfolio.constraints.register(definition)
project.services.portfolio.constructors.register(definition)
project.services.portfolio.construct(request)
```

Registration/materialization/fit/construction services are absent or reject in read-only
mode; repositories for exact immutable handles remain. Lookup by qualified name may resolve
a version before request freezing, but every returned fit/materialization/result handle
contains exact typed ID/version/content and never follows later registration.

`plan_fit()` performs no label-value access or durable allocation. It resolves the exact
definition, validation scope/membership roots, selection/refit recipe, anchor, code/
environment, limits, seed basis/resolved seed, state schema, and noncircular planned-fit
content ID, then returns a bounded authorization request. Plan 09 derives roles and issues
only the matching capability; `fit()` rejects any field/root mismatch before value access.

Handles support bounded metadata, schema, row-count/state summaries, safety/lineage,
training/solver/constraint diagnostics under access policy, chunk iteration, and explicit
preview/frame requests. They do not expose a connection, relation name, arbitrary SQL,
mutable model, CVXPY object, or solver object. Closing the project invalidates lazy
iterators/capabilities but not already copied small immutable value objects.

### 18.2 Typed registration and requests

Public definitions/requests are frozen, slotted, canonically serializable dataclasses with
discriminated unions. A representative surface is:

```python no-run
@dataclass(frozen=True, slots=True)
class SignalDefinition:
    name: QualifiedName
    version: ResearchComponentVersion
    meaning: SignalMeaning
    inputs: tuple[DecisionInputRef, ...]
    transform: SignalTransformSpec
    outputs: OutputSchema
    assumptions_and_limitations: str


@dataclass(frozen=True, slots=True)
class ForecastFitRequest:
    definition: ForecastDefinitionRef
    parameters: ParameterValues
    validation_scope: ValidationTrainingScope
    fit_anchor: FitAnchor
    purpose: FitPurpose
    limits: PortfolioResearchLimits


@dataclass(frozen=True, slots=True)
class ConstructionRequest:
    constructor: PortfolioConstructorRef
    decision_inputs: DecisionInputBundleRef
    target_decisions: DecisionSelector
    current_states: CurrentPortfolioViewRef | CurrentPortfolioPathRef | None
    constraints: ConstraintSetRef
    expected_cost: ExpectedCostMaterializationRef | None
    fallback: FallbackSpec
    limits: PortfolioResearchLimits
```

Actual values use typed references/unions rather than the abbreviated protocol labels
above. Constructors reject unknown dictionary keys and subclasses with undeclared fields.
Definitions are data; custom behavior enters through separately captured registered
implementation adapters.

### 18.3 Strategy and simulator adapters

A strategy decision context may bind exact computed signal/forecast/risk handles and
target summaries only after the repository verifies:

- decision key/snapshot/schedule/cutoff compatibility;
- value availability by the context cutoff;
- causal or opaque information class, complete root closure, safe status or an exact
  acknowledged research override for every unsafe/opaque finding, and licensing;
- no label/retrospective/direct fit handle or forbidden training state; and
- exact selected output meaning/unit/horizon/schema.

The strategy cannot inspect future rows in a materialization; the adapter returns only the
current key and declared causal history. Plan 12 receives a complete target sequence or a
bounded streaming adapter that enforces the same row-relative visibility. Unsafe opaque
and unsafe causal outputs are rejected by default and visibly taint an acknowledged
simulation. Structural label/causal-release failures are always rejected.

## 19. Dataframe, matrix, and optional-dependency behavior

### 19.1 Frame schemas

Signal frames order by `decision_at`, `instrument_id`, `output_ordinal`; forecast frames use
the same order and include fit/release IDs; risk frames order by decision, estimate,
asset/factor ordinals; target frames order by decision, instrument; attempt/constraint
frames order by decision and positive ordinals. IDs use the plan-01 typed wire form as
pandas `string` dtype, UTC timestamps use the project-wide `datetime64[us, UTC]` contract,
enum/state/reason fields use documented strings, ordinals/counts use nullable 64-bit
integers, and numeric values use finite `float64` (with explicit state/reason rows rather
than nulls) unless a domain type requires decimal/string representation.

Default frames retain state and reason rows. `computed_only=True` is explicit, does not
change the occurrence, and reports original/returned counts. Empty frames retain exact
columns/dtypes/order. Preview truncation is labeled with requested/returned/total counts;
ordinary `to_pandas()` fails above `direct_pandas_rows`. Iterators are bounded, stable, and
equivalent to concatenating full output in canonical order.

Dense covariance conversion requires an explicit decision/estimate-header selector and a
fit ID when that header is fitted. It checks `max_covariance_assets`, entry count, memory,
symmetry, asset order, and state. It returns the ordered asset IDs with the matrix; a matrix
alone is never returned. Sparse/factor views use typed bounded iterators and cannot
silently densify.

### 19.2 Installation extras

Base installation implements registration, signal transforms, simple constructors,
constraint evaluation, user-supplied point-in-time risk/cost adapters, and immutable
target contracts. The required `research` extra supplies reviewed statistical/fitted-model
adapters such as Ledoit-Wolf. The required `optimize` extra supplies CVXPY and selected
open-source solvers for convex constructors.

Importing `persistra` or `persistra.portfolio` is safe without either extra. Invoking a
missing capability raises an actionable error naming the extra and requested definition;
registration may retain a definition whose capability is absent, but execution preflight
fails before staging. Exact package/solver lower bounds are selected and release-tested
during implementation, not guessed in this plan.

No optional dependency changes an already frozen request to another implementation.
Optional solver integrations may extend the machine-readable support matrix only through
a versioned adapter and conformance suite.

## 20. Determinism, numeric behavior, resources, and security

### 20.1 Deterministic ordering and math

Canonical order is UTC decision instant, instrument UUID bytes, output/factor/term ordinal.
Cross-sectional ties use section 9. Matrix rows/columns use the persisted asset manifest;
BLAS/library threading follows the environment policy. All sums used for weights, budgets,
costs, objective diagnostics, and independent verification use the plan-01 deterministic
extended-precision reduction before validated conversion to finite double.

Random estimator/solver seeds are resolved before final execution identity. Explicit seeds
are stored directly; derived seeds use a registered namespace and seed-basis manifest that
excludes the derived value, then the resolved value enters planned/execution identity.
Worker count, chunking, mapping insertion order, locale, timezone environment, or
concurrent request ordering cannot change roots or targets on the supported platform for
`OptimizationReplayStatus.ELIGIBLE` work. A wall-time-limited result retains its explicit
ineligibility. A library/solver version, architecture-sensitive algorithm, or changed
thread policy changes environment/execution identity rather than claiming reuse.

Decimal monetary/quantity/current-state values remain plan-01 domain values until an
explicit, recorded conversion to optimization weights/doubles. Conversion error bounds and
USD NAV/price roots are persisted. Negative zero is canonicalized to positive zero only at
the registered normalization boundary; NaN and infinity never persist as computed values.

### 20.2 Resource enforcement

Preflight estimates input rows, fits, training rows/features, decision/asset sizes,
covariance triangle and work matrices, factor loadings, constraint coefficients, cone/
variable counts, solver attempts/output, partitions, dataframe memory, temporary storage,
and time. It rejects known excess before allocation. Runtime counters enforce all limits
again because missingness/solver canonicalization may change work size.

Crossing a limit cancels bounded work and publishes no normal occurrence. A solver timeout
may become a recorded terminal attempt only when the construction transaction can safely
validate/publish complete bounded diagnostics and its configured fallback; its attempt and
the containing result are marked `wall_time_limited`. Otherwise the request fails without
publication. No path responds by reducing assets, shortening history, sparsifying
covariance, dropping constraints, loosening tolerances, or switching solvers unless that
action is the exact registered fallback.

### 20.3 Custom-code and solver security

Managed/custom implementations reuse plan-08 bounded execution and conformance rules.
During fitting, a reviewed fit adapter may receive only the bounded feature/label
training/scoring partitions authorized by its plan-09 capability; it receives no label
repository, arbitrary SQL, or caller-chosen keys. Feature, signal, inference, constructor,
and solver adapters never receive that capability. Unrestricted Python/SQL remains opaque
and cannot access label or fit repositories at inference. A temporally conforming adapter
receives only bounded typed partitions and cannot return a model object that later opens
files/network/SQL during prediction.

Solver invocation uses an allowlisted in-process/subprocess adapter with bounded options,
environment, files, and captured diagnostics. User strings are never shell commands;
solver option keys/types/ranges are schema-validated. Temporary model files use project
temp ownership, restrictive permissions, content verification where supported, and
guaranteed cleanup/recovery. Logs and exceptions scrub paths, coefficient/value dumps,
vendor data, credentials, and unbounded solver output.

## 21. Events, exceptions, and stable reason codes

### 21.1 Lifecycle events

Successful registration/publication emits exactly one matching event:

| Event type | Aggregate | Meaning |
| --- | --- | --- |
| `persistra.signal.registered@1` | signal definition / registration sequence | New immutable signal version |
| `persistra.signal.materialized@1` | signal materialization / 1 | Completed immutable signal output |
| `persistra.forecast.registered@1` | forecast definition / registration sequence | New immutable forecast version |
| `persistra.forecast.fit_recorded@1` | forecast fit / 1 | Completed or terminal numerical fit evidence |
| `persistra.forecast.materialized@1` | forecast materialization / 1 | Completed immutable forecast output |
| `persistra.risk_model.registered@1` | risk definition / registration sequence | New immutable risk-model version |
| `persistra.risk_model.fit_recorded@1` | risk fit / 1 | Completed or terminal numerical risk-fit evidence |
| `persistra.risk_model.materialized@1` | risk materialization / 1 | Completed immutable point-in-time risk output |
| `persistra.expected_cost.registered@1` | cost-model definition / registration sequence | New immutable ex-ante cost version |
| `persistra.expected_cost.materialized@1` | cost materialization / 1 | Completed immutable expected-cost surface |
| `persistra.constraint_set.registered@1` | constraint-set definition / registration sequence | New immutable ordered constraint version |
| `persistra.portfolio_constructor.registered@1` | constructor definition / registration sequence | New immutable constructor version |
| `persistra.portfolio.constructed@1` | construction result / 1 | Complete primary/fallback attempt and target outcome |

Definition event payloads contain typed ID/kind/name/version/sequence/content root and
registration instant. Occurrence payloads contain typed occurrence/definition/version,
input/execution/output or terminal-state roots, bounded counts/status/safety, and creation
instant. Construction payload includes top-level status, decision/attempt/target counts,
effective fallback kind, replay status, and constraint-evaluation root. It does not include
weights,
coefficients, covariance, objective values, solver logs, physical names, or reasons with
source values.

Events and their authoritative metadata/output commit together. All use the publication
transaction's one injected-clock instant for `event_at`, `available_at`, and `recorded_at`;
logical fit/value/attempt/target availability remains domain metadata. Exact retry emits no
event. Definition aggregate sequence is the registration sequence; occurrence aggregates
use one. Peer events for a graph publish in deterministic dependency order, with fits
before materializations and all inputs before construction.

### 21.2 Public exceptions

All derive from the project-wide typed error root and carry bounded structured fields:

- `PortfolioDefinitionError`: invalid version, meaning, unit, horizon, formulation, term,
  output schema, or unsupported registration;
- `PortfolioInputError`: wrong occurrence/type/project, incompatible keys/snapshot/
  schedule/cutoff/unit/horizon, missing capability, or corrupt current state;
- `PortfolioSafetyError`: label/retrospective ancestry, unauthorized role, incomplete
  lineage/release, temporal inequality, holdout violation, or unacknowledged unsafe input;
- `PortfolioMaterializationExecutionError`: signal/forecast/risk/cost infrastructure or
  adapter failure that cannot publish a complete bounded occurrence;
- `FitCapabilityError`: absent/mismatched/expired training or selection capability;
- `FitExecutionError`: infrastructure/custom-adapter failure distinct from a persisted
  normal numerical fit state;
- `RiskModelError`: invalid return sample, covariance/factor structure, PSD, or conversion;
- `ConstraintError`: invalid/conflicting/unsupported term or missing required input;
- `PortfolioConstructionExecutionError`: simple/custom constructor infrastructure or
  adapter failure that cannot become a complete bounded attempt;
- `OptimizationCapabilityError`: missing `optimize`, solver, cone, deterministic option, or
  registered problem support;
- `OptimizationExecutionError`: infrastructure/adapter failure that cannot become a
  complete attempt result;
- `PortfolioResourceLimitError`: preflight/runtime row, matrix, coefficient, memory,
  temporary, dataframe, solver-output, or time excess;
- `PortfolioConflictError`: same version/execution identity with different stored content;
  and
- `PortfolioCorruptionError`: missing/extra/changed metadata, state, target, attempt,
  constraint, manifest, finding, or event evidence.

Normal fit insufficiency, infeasible optimization, solver timeout/error, missing row input,
or failed configured fallback is represented by immutable state/result evidence when the
request can publish a complete bounded outcome. Definition/safety/schema/capability/
corruption/resource errors are exceptions and do not publish partial occurrences.

### 21.3 Stable row and fit reasons

Initial signal/forecast/fit reasons are:

- `input_missing`, `input_noncomputed`, `input_not_available`, `input_unsafe`;
- `outside_universe`, `outside_schedule`, `group_membership_missing`;
- `minimum_cross_section`, `zero_dispersion`, `invalid_numeric`, `domain_violation`;
- `no_eligible_fit`, `fit_after_cutoff`, `inference_schema_mismatch`;
- `training_role_forbidden`, `selection_not_frozen`, `holdout_not_clean`;
- `training_label_after_cutoff`, `training_input_after_cutoff`, `release_incomplete`;
- `insufficient_training_rows`, `insufficient_decisions`, `insufficient_entities`,
  `single_class`, `singular_fit`, `fit_nonconvergence`; and
- `unknown_category`, `preprocessor_input_missing`, `prediction_invalid`.

The fit audit records a reason for every candidate sample excluded after capability
membership. Capability rejection itself does not manufacture membership rows.

### 21.4 Risk, cost, construction, and optimization reasons

Initial reasons are:

- `risk_insufficient_observations`, `risk_asset_missing`, `risk_pair_missing`,
  `risk_non_psd`, `risk_repair_failed`, `risk_zero_variance`, `risk_horizon_incompatible`;
- `cost_price_missing`, `cost_spread_missing`, `cost_volume_missing`,
  `cost_zero_volume`, `cost_domain_exceeded`, `cost_nonconvex`;
- `current_state_missing`, `current_state_path_incomplete`, `current_asset_unknown`,
  `prior_child_intent_missing`, `benchmark_missing`, `benchmark_base_coverage_missing`,
  `factor_loading_missing`, `classification_missing`, `borrow_missing`, `margin_missing`;
- `empty_eligible_set`, `empty_long_leg`, `empty_short_leg`, `zero_score_sum`,
  `constructor_unsupported`, `constraint_unsupported`, `problem_nonconvex`;
- `symbolic_infeasible`, `solver_missing`, `solver_status`, `solver_iteration_limit`,
  `solver_timeout`,
  `solver_exception`, `candidate_nonfinite`, `candidate_shape`,
  `objective_mismatch`, `constraint_violation`, `budget_violation`;
- `fallback_not_configured`, `fallback_trigger_not_matched`,
  `fallback_current_infeasible`, `fallback_constructor_failed`; and
- `resource_preflight`, `resource_runtime`, `result_corrupt`.

Reason codes are stable ASCII values and may gain additions within 3.x. Human messages are
presentation text, not identity or program logic. Bounded details name IDs, ordinals,
counts, ranges, tolerances, and content roots—not data values or unbounded solver output.

## 22. Required edge-case behavior

### 22.1 Signal and forecast cases

- An all-null cross section retains every targeted row as noncomputed and does not create
  ranks, directions, or a successful empty signal.
- A singleton rank is exactly `0.5`; tied values receive average normalized rank independent
  of instrument order.
- Positive/negative zero, decimal-to-double conversion, extreme finite scores, NaN, and
  infinity follow canonical numeric/domain rules.
- A probability below zero or above one fails output validation; clipping is allowed only
  as an explicitly registered calibration transform.
- A forecast meaning/horizon/unit mismatch rejects before combination or optimization even
  if shapes and numeric values match.
- Missing combined components follow exact minimum-count/renormalization policy and record
  the participating component root per row.
- A direct expected-return transform from rank without calibration rejects semantic
  validation.
- A cross-sectional transform cannot include an instrument whose contemporaneous input
  was unavailable at that decision cutoff.

### 22.2 Fit and release cases

- A training sample whose label interval ends by the fit cutoff but whose label revision
  becomes available later rejects from that fit.
- A fit logically available exactly at the inclusive public cutoff may be used; one
  microsecond later may not. Under project knowledge, fit/release evidence created exactly
  at that inclusive cutoff is admitted and evidence created later is not.
- A fit with zero declared delay records zero; absence of a delay field is invalid.
- When no prior fit is eligible, inference yields `fit_unavailable`; it never uses the first
  future fit or an unregistered global model.
- Multiple eligible fits choose the latest logical availability/anchor deterministically;
  conflicting equal anchors reject instead of UUID tie-breaking unequal content.
- Learned imputation/scaling over full data, outer test, or holdout is caught by membership
  and state-root sentinel tests.
- A selected refit cannot open outer-test labels and a final-holdout refit cannot occur
  after a contaminated/open holdout while claiming confirmatory status.
- Exact retry after a final-holdout fit/evaluation does not create another holdout use or
  recompute training membership.
- Direct external label inspection recorded as contamination prevents a clean holdout
  capability but does not pretend to erase already published development fits.
- A completed fold-training/inner-selection fit retains managed evaluation state but has no
  causal release and cannot be selected for decision inference.
- A numerical terminal fit has no model state/release/prediction adapter; an infrastructure
  crash has no fit row/event.
- Reordered training rows, worker counts, and chunk sizes preserve state/content roots;
  inserted/deleted/duplicated keys conflict.

### 22.3 Risk and cost cases

- One return observation is insufficient for sample covariance; zero observations do not
  create a zero matrix.
- Pairwise counts differ visibly and absent pairs do not become zero covariance.
- A covariance exactly within negative-eigenvalue tolerance accepts without repair;
  outside it follows declared fail/clip behavior.
- Eigenvalue clipping records a nonzero adjustment and cannot change asset order or unit.
- A zero-variance asset has a typed volatility/correlation state and cannot enter inverse-
  volatility/risk-parity unless a declared floor/exclusion resolves it.
- An asymmetric user covariance within tolerance is averaged deterministically; beyond
  tolerance rejects.
- Factor covariance/exposure/idiosyncratic inputs with mismatched factor IDs/order,
  availability, horizon, or units reject.
- An asset with absent benchmark membership is zero only after exact nonmembership is
  proved; an unavailable composition is different.
- A noninvestable nonzero benchmark constituent remains in the construction-asset manifest
  as `fixed_zero`, contributes active weight/risk/exposure, and cannot disappear through
  universe intersection.
- Zero ADV prevents exposure increase under the normal capacity policy; null ADV follows
  the missing action.
- Expected square-root impact outside calibration range fails or uses the registered
  extension and never extrapolates silently.
- A zero-cost model produces explicit zero components and identity; omitting a required
  cost model is not the same execution.

### 22.4 Constraints and target cases

- Ineligible currently held assets follow explicit liquidate/retain/fail behavior and stay
  in turnover/gross/net/group checks.
- Inconsistent position bounds or impossible cash/net/gross relationships reject in
  preflight when provable.
- Group memberships changing on a decision use the point-in-time root for that decision;
  current classifications do not rewrite history.
- Soft constraint slack is nonnegative, penalized, stored, and reported; it never turns a
  hard constraint soft.
- A constraint removed by CVXPY presolve is still independently evaluated.
- Long and short score sums normalize separately; a required zero leg fails without
  dividing or reallocating its budget.
- Cash plus risky weights reconciles to one within the registered tolerance after any
  normalization. Residual cash is explicit, not a missing asset.
- Negative/zero NAV, non-USD input, unavailable current state, or an unknown current
  position prevents weight conversion.
- Target values are never rounded to lots/quantities and no estimated trade is reported as
  an order.
- A target-sequence decision failure is retained in the sequence; default downstream
  behavior is not carry-forward.

### 22.5 Optimization and fallback cases

- Missing CVXPY/solver raises an actionable capability error before staging or fallback
  unless missing capability is itself an explicitly configured fallback trigger.
- A non-DCP objective/constraint rejects as unsupported; the service does not locally
  linearize it.
- Infeasible, unbounded, iteration-limit, wall-timeout, error, or nonfinite candidate
  statuses remain distinct; only wall-timeout makes replay status resource-limited.
- `optimal_inaccurate` is accepted only when policy allows it and independent verification
  passes every stricter registered tolerance.
- Solver success with budget/objective/constraint mismatch becomes `invalid_result`.
- Solver fallback records a new attempt with exact solver/options; constructor fallback
  records its own constructor content.
- Retain-current fallback fails on any hard target-constraint violation; permitted soft
  violations retain explicit slack/penalty evidence.
- A successful fallback produces `completed_with_fallback`, never `completed`, and failed
  primary evidence remains queryable.
- Fallback recursion, hidden auto-solver selection, environment-dependent solver order,
  or tolerance loosening rejects.
- Warm-start source mismatch or unavailable source rejects; the final candidate still
  undergoes full independent verification.
- Primary/fallback logical availability follows the registered sequential timing spec;
  zero is explicit, observed wall duration cannot backdate a target, and downstream use
  before the effective/final outcome instant rejects.

### 22.6 Persistence and concurrency cases

- Empty outputs use canonical empty roots and exact schemas; absent output roots are only
  legal for failed results.
- Duplicate/missing/extra signal/forecast/risk/target/attempt/constraint rows are detected
  by count/root reconciliation on retry/open/copy.
- Transaction failure at each staging/state/hash/finding/event boundary exposes no partial
  occurrence.
- Concurrent identical requests produce one occurrence/event; different requests cannot
  alias generated model state.
- Read-only open, verified copy, migration, export eligibility, stale-stage recovery, and
  project close preserve capability/ownership boundaries.
- Physical generated model-state names never appear in public handles, events, logs,
  exceptions, dataframe metadata, or result exports.

## 23. Migration, compatibility, and extension policy

### 23.1 Clean v3 migration boundary

This is a greenfield v3 schema. No v2 strategy, pipeline, optimizer, model pickle,
dataframe, cache, or backtest artifact is imported in place. Users rebuild exact v3
decision datasets, features, fits, signals/forecasts, risk estimates, constraints, and
targets. Exporting plain user-authored parameters/weights for explicit validation and
re-registration is an application workflow, not a compatibility guarantee.

Research-role migrations add the managed `portfolio`, `signal_data`, `forecast_data`,
`model_data`, `risk_data`, and `portfolio_data` schemas/tables without changing market
databases. Migration fixtures validate clean create, supported prior v3 schemas, typed
kind checks, foreign ownership, all constraints/indexes, generated relation registry,
copy/reopen, and exact schema introspection. Downgrade and in-place rollback remain out of
scope under plan 02.

### 23.2 Versioning and reuse

Changed signal meaning, forecast target/horizon, fit membership/preprocessing, risk-return
definition, covariance/PSD policy, cost formula, constraint meaning/tolerance, constructor
algorithm, objective, solver policy, fallback, output schema, safety rule, or numeric
normalization changes definition/execution identity. Cosmetic display changes may use a
compatible semantic version but never exact reuse across content IDs.

This plan supports exact reuse only. Plan 14 may explicitly record compatibility reuse for
a trial/study after comparing declared compatibility, but it cannot relabel one fit,
materialization, matrix, attempt, or target as another exact occurrence. Plan 15 comparison
may align compatible outputs while preserving every original identity and warning.

### 23.3 Extension contracts

Custom signal transforms, forecast/risk adapters, costs, constraints, and constructors
register through typed entry points and the plan-08 bounded implementation/conformance
system. Registration never grants safety. Each extension declares input/output meaning,
temporal behavior, permitted fit access for forecast/risk adapters, convexity/support
capabilities, deterministic state, resource bounds, and acceptance fixtures. Expected-cost
extensions remain fixed/direct point-in-time surfaces in this plan; custom registration
cannot bypass the deferred learned cost-fit contract.

New solver adapters publish a machine-readable cone/problem/options/status capability and
pass deterministic, infeasible/unbounded/error, residual, resource, and malicious-option
tests. New mixed-integer/cardinality/round-lot support requires a new formulation/result
capability, explicit nondeterminism/runtime semantics, and plan-13 handoff; it is not added
by accepting a solver string.

New target instruments/currencies/derivatives require exact valuation, exposure, risk,
quantity, multiplier, margin, and accounting contracts in dependent plans. The initial
instrument-weight schema cannot be stretched with an opaque metadata field.

## 24. Implementation sequence

1. Add typed IDs/enums/value objects, semantic-version registries, definition schemas, and
   migrations for the portfolio metadata/output capability boundaries.
2. Implement exact decision-input alignment, shared safety/licensing/root closure, limits,
   deterministic ordering/math, handles, frames, and lifecycle events.
3. Implement managed signal transforms/domain validation and immutable materialization.
4. Implement training capabilities, fit audit, deterministic preprocessing/model adapters,
   selection/refit, typed state, causal release, and forecast inference/combination.
5. Implement sample/EWMA/fixed/Ledoit-Wolf/user covariance/factor risk models, pair counts,
   horizon conversion, PSD diagnostics/repair, and risk materialization.
6. Implement expected-cost components and the common current/benchmark/group/factor/
   liquidity capability adapters.
7. Implement constraint registration/compilation plus independent evaluation and the four
   required base simple constructors.
8. Add the `optimize` extra, pinned CVXPY/solver adapters, canonical convex problems,
   attempts, verification, risk parity/minimum/mean/maximum-diversification/benchmark-
   relative constructors, and visible fallback.
9. Implement target/current-state/multi-strategy/rebalance handoff contracts for plans
   11–13 without adding order or accounting behavior here.
10. Complete conformance, property/fault/resource/determinism/optional-extra tests,
    documentation workflow, strict docs build, and cumulative plans 01–10 review.

Each checkpoint is an independently coherent migration/API/test unit. A later step cannot
temporarily expose labels, physical relations, unchecked solver targets, or partial
targets. Fixtures use small deterministic source data and hand-computed portfolios before
the flagship workflow.

## 25. Acceptance tests and exit criteria

### 25.1 Identity, registration, and input tests

- All thirteen typed IDs round-trip through canonical JSON, SQL UUID storage, event
  payloads, repositories, and kind-mismatch rejection.
- Semantic versions, registration sequence, exact retry/conflict/concurrency, reserved
  names, assumptions, schemas, implementations, capabilities, and definition roots pass
  property/golden tests for every component kind.
- Decision inputs reject wrong project/build/snapshot/schedule/cutoff/base keys, duplicate
  rows, unavailable values, label/retrospective roots, incomplete closure, incompatible
  units/horizons, and hidden workspace/SQL ancestry.
- Acknowledged unsafe and/or opaque input remains unsafe through signal/forecast/risk/cost/
  target and is rejected by simulator adapters by default; structural violations never
  override.
- Licensing and sensitive-state fixtures prevent unauthorized value/parameter/export
  access without removing metadata/provenance.

### 25.2 Signal and forecast tests

- Golden rank tests cover ascending/descending, singleton, ties, group roots, missing/
  invalid values, stable asset order, and exact availability.
- Direction/probability/standardization/winsorization/score combination tests cover domain,
  thresholds, zero dispersion, cross-sectional minimum, learned-state boundary, and units.
- Direct forecast tests require exact target/horizon/calibration; combined forecasts cover
  compatibility, static/learned weights, missing renormalization, component roots, and
  uncertainty.
- Materialization tests reconcile every targeted/computed/state row, schema/content root,
  safety/licensing/lineage, execution identity, empty output, retry, and event.

### 25.3 Fit, validation, and causal-release tests

- Training capability fixtures cover every fit purpose/role table row, exact sample-key
  membership, nested inner selection, selected/final refit, nonnested production schedule,
  outer-test sealing, final-holdout clean use/contamination, expiry, and wrong caller.
- Sentinel labels/features available immediately before/at/after fit cutoffs prove closed
  availability and project-knowledge comparisons; later revisions never enter earlier fit.
- Preprocessor sentinels detect full-panel/test/holdout imputation, scaling, winsorization,
  encoding, and PCA leakage.
- Candidate selection freezes complete ordered scores and deterministic ties before outer
  test; changed metric/aggregation/parameter/code/seed cannot reuse capability.
- Fit state/storage tests cover sample/class/variance insufficiency, singular/nonconverged/
  invalid state, typed parameter schemas, prohibited pickle public contracts, and terminal
  versus infrastructure failure, plus completed evaluation-only fits with no release.
- Managed evaluation tests require the exact fold/selection/holdout-use capability, keep
  predictions/metrics label-classified under the analysis/trial owner, and expose no
  forecast materialization or decision adapter.
- Causal-release tests prove the fit remains label-classified, releases are separate and
  immutable, only the three release-eligible purposes can receive one, every inequality/
  root/role/holdout condition gates each prediction, and no unmediated fit/label handle
  reaches decision APIs.
- Rolling/refit tests cover equal boundaries, missing eligible fit, latest eligible fit,
  inference delay, backward-as-of age, reordered partitions, and exact prediction roots.

### 25.4 Risk and expected-cost tests

- Hand-computed sample and EWMA covariance fixtures validate centering, denominator,
  weights/effective sample, pairwise counts, asset order, simple/log/excess units, and
  horizon conversion.
- Fixed diagonal/scaled-identity and reviewed Ledoit-Wolf fixtures validate shrinkage,
  package/adapter identity, missing extra, and lower-bound installation tests.
- User covariance/factor fixtures cover triangle/symmetry, missing diagonal/loadings,
  factor order, idiosyncratic variance, availability, lineage, and reconstruction.
- PSD fixtures cover tolerance boundary, fail, eigen clip, repeated eigenvalues,
  before/after diagnostics, adjustment root, zero variance, and independent revalidation.
- Cost fixtures hand-check fees/spread/linear/square-root/composite values, USD units/NAV,
  symmetry, zero/missing volume, domain extrapolation, convexity, coefficient availability,
  and separation from realized cost.

### 25.5 Constructor, constraint, and optimization tests

- Hand-computed long-only/long-short equal, score, quantile, and inverse-volatility targets
  cover empty legs, zero sums, gross/net/cash budgets, held-ineligible assets, and common
  post-check failure/fallback; their attempts use `constructed`/`construction_failed` with
  canonical empty solver evidence rather than fake optimal statuses.
- Multi-decision tests reject one implicitly reused current view, require exact path
  coverage for every state-dependent decision, permit canonical empty state only for fully
  state-independent contracts, and distinguish an external historical path from endogenous
  simulation state; hand-authored future paths remain opaque scenarios. Multi-strategy
  `retain_prior_child` likewise requires an exact per-decision prior-intent view and fails
  when the first required prior is absent.
- Constraint fixtures cover every kind, absolute/active/group/factor scope, point-in-time
  membership, current/benchmark/margin/borrow capability, hard/soft/missing actions,
  tolerances, symbolic conflicts, and one audit row per term/scope/attempt.
- Small analytic risk-parity/minimum-variance/mean-variance/maximum-diversification/
  benchmark-relative problems match hand or high-precision references under supported
  formulations.
- CVXPY/solver tests cover DCP/support preflight, missing extra/solver, exact options,
  deterministic selection, optimal/inaccurate/infeasible/unbounded/iteration-limit/error/
  timeout statuses, replay eligibility, malformed/nonfinite candidates, residuals, and
  objective/constraint recomputation.
- Fallback tests cover exact triggers, solver attempts, retain-current feasibility,
  registered constructor, recursive rejection, visible top-level status, and retained
  primary failure.
- Target tests reconcile weights/cash/gross/net/turnover/active exposure/risk/cost/objective,
  construction-asset manifests including benchmark-only fixed-zero/current-held assets,
  per-decision current-state IDs, attempt/outcome logical availability, states/reasons,
  effective attempt, failed decisions, child contributions, and no order/quantity/
  accounting semantics.

### 25.6 Persistence, API, resources, and documentation

- Fresh migration, supported migration, reopen/read-only, verified copy, stale recovery,
  generated model-state ownership, schema introspection, and physical-name hiding pass.
- Fault injection at every metadata/state/output/hash/finding/attempt/constraint/event/
  commit boundary leaves no partial publication; concurrent identical writers produce one
  occurrence/event and readers see before/after states.
- Frame/iterator/matrix tests validate exact dtypes/order/empty/computed-only/preview,
  bounded conversion, dense refusal, factor views, licensing, close invalidation, and
  concatenation equivalence.
- Worker/partition/hash order, locale, supported BLAS thread settings, and insertion order
  preserve fit/value/matrix/target roots for replay-eligible work; wall-time-limited work is
  visibly ineligible, and changed code/library/solver environment changes execution identity.
- Preflight/runtime tests cross every row/fit/training/feature/asset/matrix/factor/
  constraint/coefficient/attempt/output/dataframe/memory/temp/time limit and prove explicit
  failure without sampling, constraint loss, solver substitution, or partial target.
- Base/research/optimize extras install independently, namespaces import safely, missing
  capabilities are actionable, and claimed lower bounds are tested on supported Linux.
- API/docs snippets compile or execute under the docs harness and strict MkDocs builds
  without internal-link/schema-name errors.

### 25.7 End-to-end exit

A documented workflow must:

1. build one exact causal decision dataset and exact plan-09 temporal memberships;
2. materialize rank/allocation signals;
3. fit and causally release an expected-return forecast without outer-test/holdout leakage;
4. build sample/EWMA/shrinkage risk estimates and an ex-ante cost surface;
5. register long-only and long-short constraint sets;
6. produce simple and CVXPY-optimized targets with full attempt/constraint diagnostics;
7. demonstrate visible infeasibility and a configured fallback;
8. combine two child intents through a parent constructor; and
9. hand the same immutable target contract to plan-12 fixtures without private SQL,
   quantities, orders, fills, accounting, or notebook-only logic, and invoke the pure
   one-decision kernel once with an endogenous fixture state.

Plan 10 is complete only when all tests above pass with `make lint type test`, the docs
checks, strict docs build, optional-extra installation matrix, and the cumulative review
finds no contradiction with the umbrella specification or focused plans 01–09.

## 26. Review checklist for dependent plans

Plans 11 through 15 and 18 must preserve:

- signal/forecast meaning, unit, target, horizon, uncertainty, and availability rather than
  treating arbitrary numerics as expected return;
- the fit/causal-release distinction: fits remain label-classified and prediction rows are
  decision-eligible only through exact role/membership/availability/holdout proof;
- plan-09 split/selection/final-holdout capabilities and prohibition on ordinary outer-
  test/final-holdout fitting;
- exact point-in-time risk/cost/group/factor/benchmark/current-state inputs, covariance PSD
  evidence, and horizon conversion;
- expected versus realized cost separation;
- registered constraint meaning/hardness/tolerance/missing behavior and independent
  post-construction evaluation;
- solver/problem/options/status/attempt/violation evidence, visible fallback, and no silent
  substitution or tolerance relaxation, plus wall-time replay ineligibility;
- target weights/cash as desired intent rather than quantities/orders/journal state;
- registered construction timing and prohibition on target/rebalance use before the
  effective attempt's logical availability;
- plan-11 ownership of reconciled current state, NAV, settlement, margin, and borrow;
- no implicit multi-decision current-state reuse: standalone state-dependent sequences bind
  exact external views, while plans 12–13 call the pure one-decision kernel with endogenous
  state and persist evidence in the run transaction;
- plan-12/13 ownership of rebalance/order/fill/realized-cost/fidelity behavior and explicit
  implementation shortfall from target;
- multi-strategy resolution to one ordinary parent target before simulation, with any
  retain-prior-child behavior supplied as an exact causal prior-intent view;
- plan-14 ownership of studies/trials/search/scenarios/compatible reuse without
  reinterpreting exact fits, attempts, or targets;
- plan-15 immutable analysis/export preserving failed attempts/fallback/safety/provenance;
  and
- bounded handles/frames, physical-name hiding, append-only atomic publication, licensing,
  deterministic ordering, and complete root/count reconciliation.

If a dependent plan needs tax lots, integer/round-lot/cardinality optimization, nonlinear
derivative risk, intraday broker margin, online live fitting, a new solver, or a new target
intent, it defines a new typed capability and acceptance suite rather than adding untyped
fields or silently changing these results.

## 27. Consistency statement

This plan preserves the umbrella pipeline from causal features through declared signals/
forecasts, portfolio constructors, risk, constraints, expected costs, and target portfolio.
It specifies every planned built-in constructor while limiting each to a mathematically
declared supported formulation. It preserves CVXPY as the required convex optimization
implementation in the `optimize` extra, makes failure/fallback visible, and keeps forecast
combination separate from portfolio optimization.

The causal-fit release is the required bridge between plans 08–09 and legitimate fitted
forecast/risk use. It does not weaken label separation: model fits and selection evidence
remain label-classified and inaccessible to decisions, while each prediction/risk row must
prove that historical training evidence and inference inputs were available by its exact
cutoff. The cumulative review now aligns that typed adapter with plan-07 ordinary folding,
plan-08's still-label-free feature DAG, and plan-09's membership/refit/holdout capabilities
rather than treating it as an opaque exception.

Fit planning now uses an acyclic recipe/planned-fit/authorization identity sequence, and
completed fold/inner state stays on a separate label-classified evaluation path. Portfolio
construction preserves covered benchmark and current-only assets in one exact manifest,
evaluates state-independent native-unit cost surfaces against explicit current-state
arguments, and gives every primary/fallback outcome a logical availability before any
rebalance handoff.

Rebalance policy, orders, fills, realized costs, simulations, studies, and general result
analysis remain with plans 12–15. Plan 11 now concretely owns the reconciled journal,
valuation, settlement, margin, borrow, and `CurrentPortfolioView` side of the target
handoff without giving accounting target/order/fill authority. No open project-level
conflict remains: plan 02 records the new research schemas, the umbrella states the
release/target/accounting boundaries, and shared safety subjects include every plan-10
occurrence.
Initial construction remains USD-only, and managed learned cost calibration is explicitly
deferred pending a later typed cost-fit contract. Standalone state-dependent sequences now
bind exact external views while simulators own endogenous state/per-decision persistence;
wall-time solver outcomes remain exactly reusable as stored but visibly replay-ineligible.
