# Focused specification 09: Alpha diagnostics and finance-aware validation

**Status:** implementation plan
**Target:** Persistra 3.0
**Primary packages:** `persistra.research.alpha` and
`persistra.research.validation`

## 1. Purpose and relationship to the umbrella specification

This plan makes the alpha-analysis and temporal-validation direction in the
[v3 umbrella specification](v3-spec.md) implementable. It defines reproducible
pre-simulation diagnostics over exact point-in-time features and future labels, plus
splitters whose membership is based on timestamps, closed label-information intervals,
and declared panel relationships rather than shuffled/equally spaced row positions.

Focused specifications 01 through 08 remain normative. This plan reuses:

- plan-01 typed IDs, UTC instants/durations, canonical serialization, content IDs,
  numeric rules, injected clocks, and lifecycle events;
- plan-02 project modes, research-database ownership, leases, migrations, transactions,
  copies, and recovery;
- plan-03 immutable source/snapshot, safety, provenance, and licensing semantics;
- plan-04 calendars, universe evaluations, decision schedules, instruments, and groups;
- plans 05 and 06 exact market/fundamental/estimate/macro/benchmark/rate meaning;
- plan-07 immutable analysis datasets, row/input audit, SQL/workspace lineage, information
  classes, safety findings, limits, and dataframe rules; and
- plan-08 exact feature/label materializations, per-output states/availability, closed
  label intervals, dependency scope, execution trust, and structural label separation.

Alpha analysis consumes one exact completed plan-07 analysis-role dataset whose selected
columns resolve to exact plan-08 feature and label outputs. It never reconstructs a label
horizon, temporal join, or missing decision from column names. A validation plan consumes
the same exact sample keys and label intervals and later supplies immutable fold membership
to plans 10 and 14. Plan 15 may wrap/export these results through the general analysis-
artifact architecture but cannot rewrite their identities or statistics.

## 2. Scope

### 2.1 In scope

- Versioned alpha-analysis definitions and immutable completed results
- Pearson and Spearman cross-sectional information coefficients
- IC time series, coverage, stability, HAC inference, and moving-block bootstrap intervals
- Quantile label-return diagnostics, top-minus-bottom spreads, monotonicity, and turnover
- Feature coverage/missingness, persistence, decay, and autocorrelation
- Categorical/numeric/joint sector, industry, style, market, and custom exposure diagnostics
- Predeclared subperiod, regime, universe, and categorical slices
- Holm family-wise and Benjamini-Hochberg false-discovery p-value adjustment
- Exact expanding-window and rolling-window split plans
- Closed-interval purging with entity/group/panel dependency relationships
- Decision-step or elapsed-time embargo
- Combinatorial purged cross-validation
- Nested inner-selection/outer-evaluation capabilities
- A sealed final untouched holdout with immutable use/contamination records
- Exact split membership/audit, bounded iterators/dataframes, persistence, events, and tests

### 2.2 Out of scope

- Signals, forecasts, trained model definitions, model registries, or prediction serving
- Portfolio construction, transaction costs, execution, accounting, or backtests
- General study/trial/search scheduling, retries, compatible reuse, or worker coordination
- General result metrics/attribution/reporting or self-contained exports
- Random row shuffling, ordinary IID k-fold over panel rows, or implicit stratification
- Automated feature selection, hyperparameter optimization, or estimator cloning
- Probability-of-backtest-overfitting, probabilistic/deflated Sharpe, or general Monte Carlo
  release requirements; later plans may add them to the typed artifact surface
- A secrecy boundary preventing a local user from separately querying an analysis dataset

## 3. Normative decisions

1. An alpha result or validation plan binds exact immutable dataset, feature, label,
   snapshot, schedule, cutoff, state, code, policy, and limit identities. Friendly names,
   “latest,” or caller dataframes never remain in execution identity.
2. Alpha diagnostics are label-aware analysis artifacts and are never strategy inputs.
   A quantile spread is a mean realized-label diagnostic, not a simulated portfolio.
3. Every analysis declares `exploratory`, `validation`, or
   `confirmatory_holdout` intent. Post-hoc slices/horizons/hypothesis families cannot be
   mislabeled confirmatory.
4. Cross-sectional diagnostics keep all eligible instruments at one decision together.
   Missing/state policies determine usable pairs explicitly; row deletion is audited.
5. Statistical inference accounts for serial dependence from overlapping labels through
   an explicit HAC or block-bootstrap policy. An IID standard error is never silently used.
6. Multiple-testing adjustment operates on a predeclared hypothesis family. Unadjusted,
   adjusted, and family identities are stored separately.
7. Splitters assign unique decision instants to raw temporal roles before sample-level
   purging. They do not split instruments at the same decision between raw train/test roles.
8. Purging removes a candidate training/validation sample when its closed label interval
   overlaps an evaluation sample's interval under the strongest required entity/group/panel
   relationship. A user may strengthen but never weaken derived scope.
9. Embargo removes related later training samples after each evaluation segment's latest
   information end. It uses the pinned schedule or exact UTC duration, not row arithmetic.
10. Nested validation generates inner plans solely from each outer training membership.
    An outer test capability is opened only after the inner selection manifest is frozen.
11. A final holdout boundary is resolved from schedule/base keys before feature/label
    summaries are inspected. Managed APIs expose it once for one frozen selection identity;
    later/different access is permanently marked contaminated.
12. “Untouched” is a managed-workflow provenance guarantee, not DRM. Direct external
    inspection cannot be prevented; users can and must record contamination.
13. Censored/ambiguous/noncomputed labels are not supervised targets. Their states/counts
    remain audit data and cannot be silently converted to ordinary returns/classes.
14. Completed definitions, results, split plans, memberships, and access records are
    immutable and append-only. Exact retries verify stored content before reuse.
15. All computation is bounded and partitioned. No initial diagnostic or splitter requires
    a 5,000-instrument by 20-year panel in pandas.

## 4. Identity, enums, and public values

### 4.1 Typed IDs

| Type | Kind token | Meaning |
| --- | --- | --- |
| `AlphaAnalysisDefinitionId` | `alpha_analysis_definition` | Stable versioned alpha-analysis lineage |
| `AlphaAnalysisResultId` | `alpha_analysis_result` | One immutable completed diagnostic execution |
| `ValidationSchemeId` | `validation_scheme` | Stable versioned splitter-definition lineage |
| `ValidationPlanId` | `validation_plan` | One immutable resolved split/membership occurrence |
| `FinalHoldoutUseId` | `final_holdout_use` | One immutable managed holdout access/evaluation occurrence |

Analysis/scheme versions are positive integers scoped to the stable ID and contiguous.
Results, plans, and holdout uses are occurrence IDs. Content IDs identify definitions,
inputs, inference policies, memberships, execution, and outputs; none replaces a typed UUID.

### 4.2 Stable enums

| Enum | Values |
| --- | --- |
| `AnalysisIntent` | `exploratory`, `validation`, `confirmatory_holdout` |
| `AlphaMetricKind` | `pearson_ic`, `spearman_ic`, `quantile_labels`, `coverage`, `monotonicity`, `turnover`, `persistence`, `decay`, `autocorrelation`, `categorical_exposure`, `numeric_exposure`, `joint_exposure` |
| `MetricValueState` | `computed`, `insufficient_observations`, `zero_dispersion`, `rank_deficient`, `invalid_numeric`, `empty_membership` |
| `InferenceKind` | `none`, `hac`, `moving_block_bootstrap` |
| `PValueAdjustment` | `none`, `holm`, `benjamini_hochberg` |
| `CoverageDenominator` | `universe_eligible`, `included`, `row_usable` |
| `CoverageState` | `included`, `dataset_row_usable`, `feature_computed`, `feature_noncomputed`, `label_computed`, `label_noncomputed`, `weight_valid`, `weight_invalid`, `exposure_valid`, `exposure_invalid`, `paired_usable`, `metric_computed`, `metric_noncomputed` |
| `QuantileWeighting` | `equal`, `dataset_weight` |
| `FeatureDirection` | `ascending`, `descending` |
| `SliceKind` | `all`, `subperiod`, `regime`, `universe_group`, `category` |
| `ExposureKind` | `categorical`, `numeric_univariate`, `numeric_joint` |
| `AnalysisRowState` | `usable`, `row_unusable`, `feature_noncomputed`, `label_noncomputed`, `weight_invalid`, `exposure_invalid`, `slice_excluded` |
| `ValidationSchemeKind` | `expanding`, `rolling`, `combinatorial_purged`, `nested` |
| `TemporalWidthKind` | `decision_steps`, `elapsed`, `explicit_interval` |
| `LeakageScope` | `entity`, `group`, `panel` |
| `EmbargoKind` | `none`, `decision_steps`, `elapsed` |
| `ValidationRole` | `train`, `validation`, `test`, `final_holdout`, `excluded` |
| `EligibilityPolicy` | `complete_case`, `label_complete` |
| `ValidationSampleState` | `eligible`, `dataset_unusable`, `feature_noncomputed`, `label_noncomputed`, `interval_missing`, `interval_invalid` |
| `HoldoutUseStatus` | `confirmatory`, `contaminated` |
| `HoldoutOpenOutcome` | `opened_confirmatory`, `exact_retry`, `opened_contaminated` |

`label_complete` requires a computed label but retains noncomputed feature fields/states
for a later explicitly compatible estimator/preprocessor. `complete_case` requires every
selected feature and label output computed. Neither policy imputes.

### 4.3 Public limits and window values

`DecisionWidth` is a positive count of unique base decisions under the pinned schedule.
`ElapsedWidth` is a positive plan-01 duration. They are distinct types; neither claims
equally spaced rows. A zero embargo uses `EmbargoSpec.none()` rather than a zero width.

```python no-run
@dataclass(frozen=True, slots=True)
class AlphaAnalysisLimits:
    max_input_rows: int = 25_000_000
    max_features: int = 256
    max_labels: int = 64
    max_slices: int = 256
    max_hypotheses: int = 100_000
    max_output_rows: int = 25_000_000
    partition_rows: int = 100_000
    direct_pandas_rows: int = 2_000_000
    max_bootstrap_repetitions: int = 10_000
    timeout: Duration = Duration(1_800_000_000)


@dataclass(frozen=True, slots=True)
class ValidationPlanLimits:
    max_input_rows: int = 25_000_000
    max_folds: int = 10_000
    max_segments_per_fold: int = 256
    max_membership_rows: int = 250_000_000
    max_reason_rows: int = 250_000_000
    max_relationship_edges: int = 250_000_000
    partition_rows: int = 100_000
    direct_pandas_rows: int = 2_000_000
    timeout: Duration = Duration(1_800_000_000)
```

All limits are positive and cannot exceed project/deployment hard ceilings. Raising a
permitted limit changes execution identity; crossing one fails rather than sampling,
shortening windows, reducing hypotheses, dropping folds, or disabling audit.

## 5. Project, database, and lifecycle ownership

Definition registration, alpha execution, split-plan creation, and holdout-use recording
require `ProjectMode.RESEARCH_WRITE`. They mutate only the research database under its
exclusive plan-02 lease and read exact dataset/component relations through repository
handles. Market databases remain attached read-only under shared leases.

Read-only inspection of definitions, results, plans, memberships, findings, and bounded
dataframes is available in `read_only` and `research_write`. Migrations install metadata,
normalized output tables, and controlled dynamic membership relations in the existing
plan-02 `analysis` schema. They extend plan-07 safety-finding subjects with
`alpha_analysis_result` and `validation_plan`; callers receive no raw connection,
physical relation name, or DDL capability.

Definitions/results/plans/memberships/holdout uses are append-only in 3.0. Large operations
use transaction-local staging and publish verified metadata, normalized/dynamic outputs,
findings, and events in one research transaction. Failure/cancellation exposes none.
Stale staging is diagnosed by the shared managed recovery path and never inferred complete.

## 6. Exact input, eligibility, safety, and licensing

### 6.1 Analysis input

An `AlphaInputSpec` pins:

- one exact completed plan-07 `ResearchDatasetBuildId` with role `analysis`;
- ordered selected feature outputs resolving to exact plan-08 feature materializations;
- ordered selected label outputs resolving to exact plan-08 label materializations;
- optional causal dataset weight, group, regime, categorical, and numeric exposure fields;
- one explicit coverage denominator and row-eligibility policy; and
- required row/input audit, safety, lineage, licensing, and schema manifests.

The build must preserve direct unique `(decision_at, instrument_id)` keys and the selected
label's closed interval/availability/state columns. A bare dataframe, workspace name,
definition name, label-looking column, or reconstructed horizon is invalid. Selected
features and labels may share the same base build through an enriched analysis dataset;
every exact occurrence and selected output remains in input identity.

An alpha request contains at least one feature and one label. Decay may select several
exact label outputs/horizons. Every numeric value has a compatible unit/meaning; a
classification label cannot enter IC, quantile-mean/spread, monotonicity, decay, or
exposure-mean analysis by numeric-code coercion. In the initial catalog it participates in
coverage/state diagnostics only; a later typed classification metric must declare its own
formula/output schema.

### 6.2 Candidate and usable rows

The engine first constructs one rectangular key audit from the dataset row/input audit:

1. choose the declared denominator keys;
2. retain the dataset's included/usable/state facts without rewriting them;
3. resolve every selected feature/label state at the exact key;
4. require computed labels for supervised metric membership;
5. apply `complete_case` or `label_complete` to features;
6. validate optional weights/exposures/slices; and
7. record one final `AnalysisRowState` plus ordered reasons.

`label_complete` rows with missing features remain in coverage/state outputs but a metric
requiring that feature excludes them with `feature_noncomputed`. Censored/ambiguous/
invalid labels remain in denominator/audit counts but not target pairs. No state becomes
zero, no pairwise deletion lacks a count, and no filtered row disappears from coverage.

### 6.3 Information, safety, and licensing

An alpha result is `InformationClass.LABEL` because it consumes outcomes. A validation
plan is also label-classified because its membership/purge logic depends on closed label
intervals, even though it stores no analytical label values. Neither can become a
decision/simulation input.

Safe diagnostics require complete root lineage and exact inputs; inherited unsafe/opaque
findings remain. Alpha execution or validation-plan creation may proceed with
`allow_unsafe_analysis=True`, which is persisted and taints the result/plan; unknown scope
still folds panel-wide. This is not a simulation override and cannot admit a label to
decision data. Structural key/interval/root-identity failures always reject.

Licensing folds to the most restrictive selected input. Aggregation, ranks, correlations,
p-values, memberships, and confidence intervals are not automatically exportable.
Diagnostic metadata/events/errors contain bounded IDs/counts/statistics only where the
licensing manifest permits them.

## 7. Alpha-analysis definition

An immutable `AlphaAnalysisDefinition` declares:

- qualified name, positive version, owner, description, and assumptions/limitations;
- `AnalysisIntent` and optional exact `ValidationPlanId`/fold/selection-capability/holdout
  role;
- ordered feature/label output selectors and economic direction;
- requested metric families and their typed parameters;
- row eligibility, coverage denominator, weights, minimum cross-section/time counts;
- predeclared slices/exposures and hypothesis-family grouping;
- inference, confidence, bootstrap seed, p-value adjustment, and missing policies;
- deterministic ordering/math/solver identities and output schema;
- default limits, licensing/export policy, schema/content IDs, and registration instant.

Version 1 creates a stable ID/name. Later versions are contiguous; exact re-registration
returns the stored definition, while changed content under the same version conflicts.
Convenience “latest” resolution occurs before execution identity. Registration executes
no data query and does not inspect a sealed holdout.

For `confirmatory_holdout`, the definition and every metric/slice/hypothesis parameter must
be registered before the final holdout is opened. `validation` binds an accessible test
fold. `exploratory` may analyze any explicitly selected analysis interval but its output
cannot later be relabeled confirmatory.

## 8. Information coefficients, coverage, and stability

### 8.1 Per-decision Pearson IC

For one feature `x` and numeric label `y` at decision `d`, use only paired usable rows.
With `n >= min_cross_section` (default 20), compute sample covariance and sample standard
deviations in instrument UUID-byte order:

```text
IC_d = sum((x_i - mean(x)) * (y_i - mean(y)))
       / sqrt(sum((x_i - mean(x))^2) * sum((y_i - mean(y))^2))
```

The algebra is equivalent to sample Pearson correlation; common divisors cancel. Zero
dispersion, nonfinite arithmetic, or too few pairs yields a typed noncomputed IC state,
not zero. A finite result beyond `[-1, 1]` by more than the registered numeric tolerance is
invalid; a tolerance-only overshoot is clamped to the nearest endpoint with a warning.
Output stores `n`, denominator count, feature/label state counts, and membership content
ID.

### 8.2 Per-decision Spearman IC

Spearman IC assigns average ranks independently to `x` and `y` within the same usable
cross-section, using exact numeric equality for ties, then applies section 8.1 to ranks.
Ascending rank 1 is lowest. Instrument UUID order makes row association deterministic but
does not break ties.

### 8.3 IC time-series summary

For computed decision IC values `z_1 ... z_T` in decision order, report:

- arithmetic mean, sample standard deviation, minimum, maximum, and median;
- positive/negative/zero proportions;
- HAC or bootstrap standard error/confidence/p-value under section 12;
- first/last decision, computed/missing decision counts, and coverage distribution; and
- optional fixed-window rolling mean/std using explicit decision or elapsed windows.

“Stability” is this declared set of dispersion/sign/rolling statistics; no undocumented
stability score is invented. Equal weighting across decisions is the initial default.
A later weighting policy is a new definition version.

### 8.4 Coverage and missingness

For every decision, feature, label, and slice, coverage reconciles:

- denominator keys;
- included and dataset-row-usable keys;
- feature computed/noncomputed states by exact reason;
- label computed/censored/ambiguous/other states;
- valid/invalid weight and exposure keys;
- paired usable keys; and
- metric-computed versus insufficient/zero-dispersion outcomes.

Ratios always name their denominator. Empty denominators yield null ratios with state, not
NaN/zero. Coverage summaries include distribution across decisions and never infer future
candidate existence from a causal feature's `not_available` state.

## 9. Quantile labels, spreads, monotonicity, and turnover

### 9.1 Quantile assignment

For one decision, sort usable feature values and assign average tie rank `r` among `n`.
For `q` requested quantiles (initial `2 <= q <= 20`), assign:

```text
bucket = min(q, floor((r - 1) * q / n) + 1)
```

All exactly tied values receive the same bucket, so bucket sizes may differ or an interior
bucket may be empty. The engine never splits ties by UUID to force equal counts. Feature
direction determines which bucket is economically high; raw bucket numbering remains
ascending feature value.

`equal` weighting assigns `1 / n_bucket`. `dataset_weight` requires positive finite causal
weights and normalizes within each nonempty bucket. Invalid weights are audited/excluded;
negative/zero weights do not silently become equal weights.

### 9.2 Quantile label series and spread

For each decision/bucket, compute the weighted arithmetic mean of the exact selected label
and store count, total raw weight, feature bounds, label-state counts, and membership root.
The top-minus-bottom spread is:

```text
spread_d = mean_label(high_direction_bucket) - mean_label(low_direction_bucket)
```

Both endpoint buckets must meet `min_quantile_count`; otherwise the spread is noncomputed.
The spread row stores both endpoint counts (and their sum separately from each bucket row)
so insufficiency and membership reconcile without reconstructing buckets.
Overlapping labels remain overlapping realized outcomes. No holdings persist between
decisions, no cash/costs/actions are modeled, and the result is never called a backtest.
The spread's temporal mean, confidence interval, and two-sided significance use the exact
section-12 dependence policy and predeclared hypothesis family.

### 9.3 Monotonicity

At each decision with at least three nonempty buckets:

- compute Spearman correlation between ascending bucket ordinal and bucket mean label;
- count adjacent bucket pairs whose mean label increases with bucket ordinal for
  `ascending` direction or decreases for `descending` direction; and
- compute the unweighted least-squares slope of bucket mean label on bucket ordinal.

The summary reports mean correlation/slope, directional-adjacency proportion, and
computed-decision count under the same temporal inference policy. Empty buckets are omitted
but recorded; fewer than three is noncomputed.

### 9.4 Diagnostic turnover

Quantile diagnostic weights are defined on the union of instruments at decisions `t-1`
and `t`, with absent membership weight zero. One-way turnover is:

```text
turnover_t = 0.5 * sum_i(abs(w_i,t - w_i,t-1))
```

For one requested bucket, section-9.1 weights are positive and sum to 1. For the signed
top/bottom diagnostic, high-direction weights are `+0.5` times their within-bucket weights
and low-direction weights are `-0.5` times theirs, giving net 0 and gross 1 at each valid
decision. It is computed separately for each requested bucket or that signed diagnostic.
Entries/exits caused by universe, missingness, or ties retain reason counts. The first
decision is noncomputed. Turnover has no costs, fills, capacity, or rebalance timing claim.

## 10. Persistence, decay, autocorrelation, and exposure diagnostics

### 10.1 Signal persistence

At each adjacent selected decision pair, persistence is Pearson or Spearman correlation of
feature values across the intersection of instruments with computed values at both times.
It requires the declared minimum pair count. Calendar gaps remain visible; “adjacent”
means adjacent selected base decisions, not one civil day.

### 10.2 Entity autocorrelation

For explicit positive lag `k` in base-decision positions, compute per-instrument Pearson
correlation between `x_t` and `x_(t-k)` using exact paired positions. Require
`min_entity_observations`, then report the equal-instrument mean/distribution and number of
eligible entities. A separately named `pooled` policy may correlate all entity-time pairs
but cannot masquerade as the equal-entity estimator.

### 10.3 Decay by forecast horizon

Decay selects one feature and two or more exact label outputs whose definitions expose
distinct horizon/interval identities. It computes the same IC/quantile statistic for each
without manufacturing shifted labels. Output orders horizons by their canonical endpoint
policy then declared duration/decision count, and records overlapping sample counts.

A slope or half-life is reported only when the definition explicitly requests a registered
fit and at least three horizons are compatible. Horizon labels with different return kinds,
endpoint policies, or units are separate series rather than silently combined.

### 10.4 Categorical exposure

Sector/industry/category inputs must be causal fields at each decision. For every category,
report usable count, feature mean/std, cross-sectional share, and optional mean label for
analysis. Unknown categories are an explicit bucket. Present-day classifications cannot
be applied retrospectively.

### 10.5 Numeric and joint exposure

Numeric exposure reports per-decision Pearson/Spearman association and univariate slope of
the feature on each causal style/market field. Joint exposure fits unweighted OLS with an
explicit intercept and ordered columns using the pinned rank-revealing QR/tolerance policy,
reporting coefficients, residual dispersion, rank, condition diagnostic, and membership.
Rank deficiency follows a declared fail/drop policy and never a library default.

Exposure diagnostics describe association, not causal factor attribution or portfolio
risk. A label field cannot be used as a supposedly causal feature exposure.

## 11. Slices and hypothesis families

Slices are registered in the analysis definition before execution:

- `all`: the complete eligible analysis interval;
- `subperiod`: exact half-open UTC/base-decision interval;
- `regime`: exact causal plan-08 regime-feature category at the row;
- `universe_group`: plan-04 causal membership/group identity; or
- `category`: exact causal dataset category such as sector/industry.

Slice predicates operate only on typed fields/states and cannot contain SQL/Python. Slices
may overlap; every result carries its exact membership content ID. Empty slices publish
typed empty summaries. A result created after inspecting outputs with a new slice is a new
`exploratory` definition/version, never a revision of a confirmatory result.

Each inferential statistic belongs to one predeclared hypothesis family, normally all
selected features × labels/horizons × slices for one metric/economic question. Families
cannot be split after seeing p-values. Raw and adjusted p-values, hypothesis count, family
content ID, and adjustment method are persisted.

## 12. Temporal inference and multiple testing

### 12.1 HAC estimator

For ordered computed decision statistics `z_t`, let `u_t = z_t - mean(z)` and:

```text
gamma_l = (1 / T) * sum_(t=l+1..T)(u_t * u_(t-l))
w_l = 1 - l / (L + 1)
variance(mean) = (gamma_0 + 2 * sum_(l=1..L)(w_l * gamma_l)) / T
```

`L` is an explicit nonnegative decision lag smaller than `T`. For confirmatory analyses it
must be at least the maximum decision-position overlap implied by selected label intervals,
or the definition must use the block bootstrap. The engine may derive that lower bound
from exact intervals; callers may increase but not decrease it. A negative numerical
variance beyond registered tolerance is invalid; a tiny negative is clamped to zero with a
warning. Two-sided p-values use the pinned standard-normal CDF and exact implementation
identity. For declared two-sided level `1 - alpha`, the HAC confidence interval is
`mean(z) +/- normal_quantile(1 - alpha / 2) * standard_error`; it is not silently changed
to a t interval or clipped to a metric's natural range.

For positive standard error, `p = 2 * (1 - normal_cdf(abs(mean(z) / se)))`, capped to
`[0, 1]` only for registered floating tolerance. If the verified standard error is zero,
the two-sided p-value is 1 when the mean is exactly zero and 0 otherwise, with an explicit
zero-variance inference warning.

### 12.2 Moving-block bootstrap

The initial bootstrap resamples complete decision cross-sections, never individual panel
rows. Given explicit block width `B`, repetition count `R`, and plan-01 seed:

1. enumerate every contiguous circular block of `B` computed decision statistics;
2. sample block starts with the pinned counter-based generator until at least `T` values;
3. truncate the resampled series to `T`;
4. recompute the declared statistic; and
5. take type-7 percentile bounds at `alpha/2` and `1-alpha/2`.

The initial contract requires `1 <= B <= T` and a positive successful-replicate threshold
declared by the inference policy. For a two-sided null that a temporal mean is zero, the
engine uses the same block starts on the centered series `z_t - mean(z)` and reports:

```text
p = (1 + count(abs(centered_bootstrap_mean_r) >= abs(observed_mean)))
    / (successful_repetitions + 1)
```

Percentile confidence bounds use the uncentered bootstrap statistics; the null p-value
uses centered statistics. Failed replicates count toward the audit and follow the declared
minimum-success/fail policy rather than being silently replaced.

All features/horizons in one family share the same repetition/block-start plan to preserve
their dependence. The manifest stores seed/generator, starts content ID, successful/failed
replicate counts, and failure policy. `B` must meet the label-overlap lower bound for
confirmatory use. Studentized/BCa intervals and cross-sectional/entity resampling are
future methods, not aliases for this percentile interval.

### 12.3 P-value adjustment

For finite raw p-values `p_(1) <= ... <= p_(m)` with stable hypothesis-ID tie ordering:

- Holm adjusted values are the monotone cumulative maximum of
  `(m-i+1) * p_(i)`, capped at 1, then restored to original order.
- Benjamini-Hochberg adjusted values are the reverse cumulative minimum of
  `m * p_(i) / i`, capped at 1, then restored.

Noncomputed hypotheses remain in the family audit but have null adjusted p-values; the
definition states whether `m` counts all planned hypotheses (confirmatory default) or only
computed hypotheses (exploratory only). No p-value correction changes the estimate or
confidence interval.

## 13. Alpha execution, identity, and immutable output

### 13.1 Execution algorithm

The service:

1. resolves the exact definition/version, analysis dataset, selected component outputs,
   validation/holdout capability if any, safety/licensing, code/environment, and limits;
2. rejects role/key/schema/root/intent/holdout conflicts before analytical value access;
3. preflights input/metric/slice/hypothesis/bootstrap/output/lineage/resource counts;
4. creates the rectangular key/state audit and deterministic decision partitions;
5. computes cross-sectional primitives once per exact membership and reuses them across
   declared metrics without changing identity;
6. writes typed time-series/coverage/quantile/exposure staging in canonical order;
7. computes temporal summaries, bootstrap/HAC inference, and hypothesis adjustment;
8. verifies reconciliation, formulas, output schemas, chunk/content roots, findings, and
   licensing; and
9. publishes the result, normalized outputs, audit, findings, and event atomically.

No full panel enters pandas. Metric order, slice order, partition size, worker order, and
hash-map order cannot change values or manifests.

### 13.2 Execution identity and exact retry

`execution_content_id` uses schema `persistra.alpha.execution@1` and includes:

- definition ID/version/content, intent, parameters, slices, hypothesis families;
- exact dataset build/execution/output/audit and selected feature/label occurrences;
- snapshot/universe/schedule/cutoffs/base keys and all component interval/state manifests;
- eligibility, weights, directions, metric formulas, minimum counts, and inference policy;
- bootstrap seed/generator/plan, solver/numeric/order, implementation/environment identity;
- validation plan/fold/frozen-selection-capability/holdout-use identity when applicable;
- safety/lineage/licensing policies, limits, and explicit unsafe-analysis authorization.

It excludes result UUID, publication instant, physical names, event ID, and own output
root. An exact retry recomputes and verifies all stored normalized/dynamic outputs and
returns the existing result without another event. Equal statistics under a different
input, policy, code, or hypothesis family are not exact reuse.

### 13.3 Output interpretation

Every result records assumptions/limitations:

- labels are realized outcomes, often overlapping;
- IC/spreads are associations, not trading profits or causal estimates;
- quantile series omit execution/cost/accounting;
- exposure association is not causal attribution;
- statistical significance depends on the declared dependence/multiple-testing policy; and
- exploratory results remain exploratory.

## 14. Validation input and dependency relationships

### 14.1 Exact supervised sample contract

A `ValidationInputSpec` pins one exact completed analysis-role dataset build, its exact
base-key/audit manifests, ordered feature outputs, and one or more exact label outputs.
It also declares the label outputs that are actual targets, the eligibility policy,
optional causal groups, the requested leakage scope, and any terminal holdout. It cannot
select a label by display name or accept caller-provided interval columns.

The logical sample key is `(decision_at, instrument_id)`. For each eligible supervised
sample, the splitter derives one closed information interval:

```text
sample_start = min(selected target label_interval_start)
sample_end   = max(selected target label_interval_end)
sample_interval = [sample_start, sample_end]
```

Using the hull is deliberately conservative when a model has multiple targets. A scheme
may instead name exactly one target output and thereby use only that output's exact
interval. An interval with either endpoint missing, `start > end`, a noncomputed label,
or a label output absent from the exact materialization is ineligible and audited; it is
never inferred from horizon text. Censored/ambiguous labels remain denominator/audit rows
but cannot become supervised fold members.

The engine enumerates the pinned schedule's unique, strictly increasing UTC decisions and
instruments in UUID-byte order. All candidate instruments at a decision receive
the same raw temporal role before eligibility, purging, or embargo. Thus missingness may
exclude an individual sample, but the splitter never randomly assigns peers at one
decision to opposing raw roles.

### 14.2 Derived relationship scope

Leakage relationships come from exact plan-07 input lineage plus each selected plan-08
output's `ComponentDependencyScope` and `relationship_root_manifest_content_id`, not user
labels such as “independent.” Each sample has a canonical set of relationship roots:

- its `entity` root is its instrument ID;
- a `group` root is an exact typed causal group/membership root actually used by a selected
  feature or label; and
- the `panel` root is the exact input panel/base-key manifest shared by every sample.

Two samples are entity-related when their instrument IDs match, group-related when their
canonical group-root sets intersect, and panel-related when they share the panel root.
Group membership is the point-in-time membership used by the selected occurrence; a
group root hashes the exact scheme/definition version, group node/value, and grouping
policy, while each sample separately retains the assignment lineage proving membership at
its anchor. A present-day category is not substituted. A component using an all-market
cross-section, panel block, global series, cross-entity lag, unresolved dynamic dependency,
opaque dependency closure, or incomplete group lineage derives `panel` scope. Pure
row-local or entity-time dependencies derive at least `entity`. A bounded cross-section
over complete causal group roots may derive `group`.

The derived scope is the strongest scope across every selected feature and target label,
under `entity < group < panel`. A caller may strengthen it or supply additional causal
group roots, but cannot remove derived roots or request a weaker scope. Unknown scope is
`panel`, not `entity`. The resolved scope/root-edge manifest is stored and bounded by
`max_relationship_edges`; exceeding the limit fails before fold publication.

### 14.3 Candidate eligibility and role precedence

`complete_case` and `label_complete` have the section-4 meaning. Every candidate receives
one initial state and all ordered exclusion reasons. The final role precedence is:

```text
final_holdout > test > validation > train > excluded
```

Higher-precedence membership is never removed to make a lower-precedence set larger. For
a fold with validation and test segments, validation is first purged/embargoed against
test; train is then purged/embargoed against the retained validation and test samples.
For a terminal holdout, every development role is purged against holdout first. Raw and
final roles are both persisted so reductions reconcile exactly.

## 15. Closed-interval purging and embargo

### 15.1 Purging predicate

For lower-precedence candidate `a` and evaluation sample `b`, their closed label intervals
overlap exactly when:

```text
a.sample_start <= b.sample_end
and b.sample_start <= a.sample_end
```

If they overlap and are related under the resolved entity/group/panel scope, `a` becomes
`excluded` with reason `purged_label_overlap` and the deterministic evaluation segment/root
that caused exclusion. Endpoint equality therefore overlaps. A half-open shortcut is
nonconforming.

Purging is evaluated against every retained higher-precedence evaluation sample. An
implementation may use interval indexes/range joins, but its membership must equal the
logical pairwise predicate. Multiple causes are folded in canonical role, segment, root,
decision, and instrument order. Evaluation samples are not removed merely because their
own labels overlap each other; dependence is handled by validation/inference semantics.

### 15.2 Embargo semantics

An `EmbargoSpec` is `none`, a positive number of pinned-schedule decision steps, or a
positive plan-01 elapsed duration. Embargo operates after purging and independently for
each maximal contiguous evaluation segment and relationship root. Its origin is the
latest `sample_end` among retained evaluation samples for that root/segment—not the last
row, civil date, or nominal horizon.

For a decision-step embargo of `n`, the embargo set is the first `n` base decisions
strictly after the origin. For elapsed embargo `delta`, it is every base decision `d` with:

```text
origin < d <= origin + delta
```

A related lower-precedence sample anchored at an embargoed decision becomes `excluded`
with reason `embargoed_after_evaluation`. Decisions absent from the schedule do not count;
DST, holidays, early closes, and irregular observations do not create synthetic steps.
Origins at/after the plan end yield an empty embargo. Overlapping embargoes union their
causes without duplicating membership rows.

Purging protects against overlapping target information; embargo is an additional
declared separation policy. An embargo never restores a purged row, shifts an evaluation
window, or silently shortens a later fold.

### 15.3 Reconciliation

For every fold and raw role, the plan records candidate, eligible, retained, purged,
embargoed, noncomputed, and other-excluded counts. Each candidate sample has exactly one
final role and zero or more ordered reasons. Counts reconcile to the input key audit,
including decisions whose final train/test cross-section is empty. A minimum retained
sample/decision policy may invalidate the fold or whole plan as declared; it never drops
an invalid fold after inspecting labels without recording the failure.

## 16. Expanding-window and rolling-window schemes

### 16.1 Common window construction

After resolving/removing a terminal holdout, let `D = (d_0, ..., d_(T-1))` be the remaining
ordered unique decisions. A window scheme declares typed train, optional validation, test,
and step widths, `allow_short_final`, minimum retained counts, purge scope, and embargo.

Construction chains exact selectors around each test start `s`: the optional validation
selector takes its width immediately before `s`; the train end is validation start (or
`s` when absent); and the test selector starts at `s`. Rolling train takes its declared
width immediately before that train end; expanding train starts at the development
boundary and must satisfy its declared minimum width. A backward `DecisionWidth(n)` takes
the last `n` decisions strictly before its end, while a forward one takes the first `n`
at/after its start. Elapsed selectors use section 16.2. This defines mixed widths without
row-distance inference.

For `DecisionWidth` values, an expanding scheme with minimum train `M`, validation `V`
(zero only through an absent validation spec), test `H`, and step `S` uses test starts:

```text
s_j = M + V + j * S
raw expanding train      = D[0 : s_j - V]
raw validation (if any)  = D[s_j - V : s_j]
raw test                 = D[s_j : min(s_j + H, T)]
```

A rolling scheme replaces the train slice with
`D[s_j - V - M : s_j - V]` and requires exactly `M` raw train decisions. The first start
must fit the complete train and validation windows. A final test shorter than `H` exists
only when `allow_short_final=True`; otherwise it is omitted deterministically. Test starts
at/after `T` are never emitted.

### 16.2 Elapsed windows and steps

For elapsed widths, backward window `W` ending at instant `e` selects decisions in
`[e-W, e)`; forward test width `H` beginning at `s` selects decisions in `[s, s+H)`.
The first test start is the earliest base decision for which the complete elapsed train
and optional validation intervals lie within the development interval. Elapsed step `S`
advances the prior nominal start by `S` and chooses the first base decision at or after
that instant; duplicate chosen starts are skipped. Decision and elapsed widths may be
mixed because each boundary rule is typed and persisted.

An elapsed window is complete by interval boundary, not by a minimum row count. Separately
declared retained-count checks still apply after purging. Explicit final interval bounds
are half-open plan-selection bounds; label information intervals remain closed.

### 16.3 Fold ordering and outputs

Folds are numbered from one by increasing raw test start, then end, independent of worker
completion. Each stores all nominal/actual temporal bounds, decision counts, sample counts,
purge/embargo manifests, and invalidity state. Expanding raw train sets are nested before
purging; rolling raw train sets have fixed declared width. Because relationship-scoped
purging may differ by fold/sample, neither scheme falsely promises equal final row counts.

## 17. Combinatorial purged cross-validation

`CombinatorialPurgedSpec` declares `N` contiguous decision groups and `K` test groups with
`2 <= N <= 32` and `1 <= K < N`. Groups either use explicit increasing half-open temporal
boundaries or deterministic equal-decision-count boundaries:

```text
group g contains decision indices
floor(g * T / N) <= i < floor((g + 1) * T / N)
```

Every group must be nonempty, so `T >= N`. Explicit groups must cover every development
decision exactly once without overlap/gap. Grouping uses decisions, never panel-row counts.

The raw test group combinations are all `C(N, K)` increasing group-index tuples in
lexicographic order; remaining groups are raw train. The requested combination count must
not exceed `max_folds`. Discontiguous chosen groups become separate maximal contiguous test
segments for purge/embargo. Membership is then resolved under sections 14 and 15.

The plan stores group boundaries, each combination, each decision's test multiplicity,
each sample's train/test multiplicity, and retained counts. Folds are dependent and are
not presented as IID replicates. Version 3.0 does not silently stitch backtest paths,
estimate probability of backtest overfitting, or compute probabilistic/deflated Sharpe;
later typed analysis artifacts may consume this exact plan and declare those algorithms.

## 18. Nested validation and the final holdout

### 18.1 Nested selection

A `NestedValidationSpec` contains one outer and one inner nonnested resolved split spec;
each is `expanding`, `rolling`, or `combinatorial_purged` with its own canonical content
ID. Recursive `nested` specs are invalid. The root plan applies the outer resolved split.
For each valid outer fold it creates an immutable child plan applying the inner resolved
split whose entire candidate universe is exactly that fold's final outer-train membership.
No outer validation, test, final-holdout, purged, embargoed, or otherwise excluded key may
appear in an inner candidate/audit relation.

Any terminal final holdout belongs only to the nested root and is removed before outer
construction. Child plans record `NoFinalHoldout`; an inner template cannot reserve or
reopen part of outer-train membership as the project's confirmatory holdout.

Inner plans retain the parent plan/fold, candidate-root, and exclusion proof. The outer
test membership is sealed from managed evaluation until a `SelectionManifest` freezes:

- exact inner plan/result identities and fold aggregation;
- exact plan-10 estimator/model/feature/preprocessing/parameter identities and any
  plan-14 trial/search identities;
- one exact selected-refit recipe content ID and permitted refit role set, when a later fit
  will precede outer-test/final-holdout evaluation; the recipe freezes every fit field but
  excludes the enclosing selection manifest, later capability, occurrence ID, and outputs;
- objective, tie-breaking, random seeds, code/environment, and selected candidate; and
- all failures, overrides, and unsafe-analysis acknowledgements.

The same selection manifest authorizes the same outer-test capability idempotently, subject
to completion of any declared refit. A changed selection is a distinct evaluation and
cannot reuse a supposedly untouched outer result. When a refit recipe is present, plan 10
combines the frozen selection root with that recipe to compute a noncircular planned-fit
content ID, then plan 09 issues a capability bound to that ID. The refit occurrence UUID
may be allocated later, but its inputs, roles, parameters, preprocessing, code, and
resolved seed cannot change. The completed refit must verify the recipe, planned-fit ID,
and issued capability before the outer-test capability opens.
This plan owns membership/capability provenance, not estimator cloning, parameter search,
or study/trial scheduling; plan 14 binds those artifacts to these child-plan identities.

### 18.2 Resolving a terminal final holdout

A `FinalHoldoutSpec` is one exact half-open base-decision interval, the last positive
`DecisionWidth` decisions, or a terminal positive `ElapsedWidth`. It is resolved from the
pinned schedule, plan interval, and base keys before feature/label values, summaries,
statistics, or candidate comparisons are inspected. Its boundary/root enters scheme and
plan identity. A bounded `HoldoutCleanlinessAttestation` identifies the workflow and
asserts that the still-unresolved terminal rows have not been inspected. Plan creation
rejects a clean claim when already-persisted managed alpha/workspace/export provenance
proves that the resolved holdout was previously included. Unjournaled direct/local access
remains the user's responsibility under the no-DRM boundary.

Every holdout decision receives raw `final_holdout`. No development fold contains those
keys. Development samples whose closed target intervals overlap related holdout samples
are purged before ordinary fold construction; the plan records this boundary purge even
when it leaves earlier decisions empty. The holdout must be terminal, nonempty, and leave
enough development data for the declared scheme.

Ordinary plan handles reveal only the holdout boundary, aggregate counts, schema/root
content IDs, and contamination status. They do not expose holdout label values, per-row
membership, coverage, or summaries. This is a managed-capability rule; a local user with
direct database access can bypass it and must record contamination.

### 18.3 Managed holdout use and contamination

`open_final_holdout(plan, selection_manifest)` requires `research_write` and validates
that all feature/model/analysis definitions, hypotheses, transformations, parameters,
seeds, scoring rules, and any final-development refit recipe were frozen before access.
When such a refit is declared, opening additionally verifies its exact completed plan-10
fit/release, planned-fit ID, and clean pre-open role capability. In one transaction it
records a `FinalHoldoutUseId` and returns a bounded holdout capability for exactly the
declared evaluations. The first clean use has status `confirmatory`. An exact retry with
the same use execution identity verifies it and returns outcome `exact_retry`, but does not
create another row or event.

A later or differently frozen use is rejected by default. With explicit
`allow_contaminated=True` it records a new `contaminated` use and permanently marks the
plan contaminated; its outputs cannot claim confirmatory status. The append-only
`mark_holdout_contaminated(plan, reason, evidence)` API records known direct/external
inspection without exposing data. Contamination is monotone and can never be cleared by a
new plan version, copy, renamed definition, or changed selection manifest.

A confirmatory alpha definition binds the exact clean holdout use and may evaluate only
its predeclared hypothesis family. Creating a capability is access for provenance purposes
even if later computation fails; failure cannot restore “untouched” status.

## 19. Validation-plan execution, identity, and retry

### 19.1 Creation algorithm

The validation service:

1. resolves the exact scheme/version, input build, selected target outputs, schedule,
   interval, eligibility, relationship, safety/licensing, implementation, and limits;
2. resolves a terminal holdout solely from schedule/base-key metadata and freezes its
   boundary before analytical values or summaries are made available;
3. constructs the candidate/key/state audit, exact closed target-interval hulls, and
   canonical relationship-root edges from component lineage;
4. preflights decision, group, combination/fold, segment, relationship-edge, membership,
   reason, storage, memory, temporary-disk, and time ceilings;
5. assigns every decision/sample its raw temporal role under the exact scheme;
6. applies terminal-holdout boundary purge, then fold-local role-precedence purge and
   embargo in canonical order;
7. validates retained counts and writes folds, segments, multiplicities, membership,
   reasons, and reconciliation data to transaction-local staging;
8. for nested schemes, creates child plans solely from each final outer-train root and
   proves disjointness from every sealed outer role;
9. hashes ordered chunks and verifies raw/final role, interval, relationship, exclusion,
   fold, segment, and total-count roots; and
10. publishes the immutable plan, controlled relations, findings, and event atomically.

No implementation may materialize the complete fold-by-sample product in pandas. It may
use interval/range joins, but partition boundaries, indexes, parallelism, and join plans
cannot alter logical membership or cause order.

### 19.2 Plan identity

`execution_content_id` uses canonical schema `persistra.validation.plan_execution@1` and
includes:

- scheme stable ID/version/content, exact resolved outer/inner split kind/content, and every
  typed window/group/nesting parameter;
- exact dataset build/execution/output/audit, selected feature/target-label occurrence,
  snapshot, universe, schedule, cutoff, base-key, and plan interval identities;
- target interval-hull, eligibility, missing/state, raw-role, role-precedence, minimum-count,
  and invalid-fold policies;
- derived/requested/resolved relationship scopes and complete relationship-root manifest;
- purge predicate/version, embargo kind/width/origin/boundary policy, and ordering;
- resolved holdout boundary/root and parent plan/fold/candidate root for nested children;
- holdout cleanliness attestation and any persisted managed prior-access audit;
- safety, lineage, licensing, implementation/environment, numeric/time-zone, and limits;
- canonical fold/group/combination construction policy; and
- explicit unsafe-analysis authorization, when permitted.

It excludes the new plan UUID, publication instant, physical relation/staging names, event
ID, and the plan's own membership/output roots. Those are independently recomputed and
verified. An exact retry verifies metadata plus every controlled relation/chunk/root and
every nested child occurrence/event, then returns the existing root without another event.
Identical folds under different selected targets, component occurrences, scope, code,
policy, limits, or holdout boundary are not exact reuse.

### 19.3 Failure, concurrency, and later orchestration

Research writers serialize under the plan-02 exclusive lease. Concurrent identical
requests resolve to one verified occurrence per root/child and one event for each newly
published occurrence. Validation, interval, relationship, resource, timeout, cancellation,
staging, nested-proof, hash, or commit failure publishes no plan or partial child tree.
Readers see the prior state or the complete parent/child publication.

Plan 14 may attach study/trial/attempt/fold artifacts and compatible-reuse edges. It does
not replace `ValidationPlanId` with a mutable study identity, reinterpret membership, or
assign this plan a general `FoldId`. In this plan, folds have immutable one-based ordinals
scoped to a validation plan.

Plan 14's `ExperimentFoldId` is only a study-owned binding to the exact tuple
`(ValidationPlanId, fold_ordinal, membership_content_id, role_content_id)`. It neither
creates a general validation `FoldId` nor permits the same ordinal to be rebound to new
membership. Design identity includes the complete bound tuple.

## 20. Metadata and physical schemas

### 20.1 Alpha definitions and results

```sql
CREATE TABLE analysis.alpha_analysis_definitions (
    alpha_analysis_definition_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analysis.alpha_analysis_versions (
    alpha_analysis_definition_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    description VARCHAR NOT NULL,
    assumptions_and_limitations VARCHAR NOT NULL,
    analysis_intent VARCHAR NOT NULL CHECK (
        analysis_intent IN ('exploratory', 'validation', 'confirmatory_holdout')
    ),
    input_selector_content_id VARCHAR NOT NULL,
    metric_manifest_content_id VARCHAR NOT NULL,
    slice_manifest_content_id VARCHAR NOT NULL,
    hypothesis_family_manifest_content_id VARCHAR NOT NULL,
    inference_policy_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    definition_schema_version INTEGER NOT NULL CHECK (definition_schema_version >= 1),
    definition_content_id VARCHAR NOT NULL UNIQUE,
    definition_json JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (alpha_analysis_definition_id, version),
    CHECK (length(description) <= 65536),
    CHECK (
        length(assumptions_and_limitations) > 0
        AND length(assumptions_and_limitations) <= 65536
    )
);

CREATE TABLE analysis.alpha_analysis_results (
    alpha_analysis_result_id UUID PRIMARY KEY,
    alpha_analysis_definition_id UUID NOT NULL,
    definition_version INTEGER NOT NULL CHECK (definition_version >= 1),
    research_dataset_build_id UUID NOT NULL,
    validation_plan_id UUID,
    validation_fold_ordinal INTEGER,
    selection_capability_content_id VARCHAR,
    final_holdout_use_id UUID,
    analysis_intent VARCHAR NOT NULL CHECK (
        analysis_intent IN ('exploratory', 'validation', 'confirmatory_holdout')
    ),
    input_manifest_content_id VARCHAR NOT NULL,
    component_manifest_content_id VARCHAR NOT NULL,
    row_audit_content_id VARCHAR NOT NULL,
    hypothesis_family_manifest_content_id VARCHAR NOT NULL,
    inference_manifest_content_id VARCHAR NOT NULL,
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
    information_class VARCHAR NOT NULL CHECK (information_class = 'label'),
    input_row_count BIGINT NOT NULL CHECK (input_row_count >= 0),
    usable_pair_count BIGINT NOT NULL CHECK (usable_pair_count >= 0),
    time_series_row_count BIGINT NOT NULL CHECK (time_series_row_count >= 0),
    coverage_row_count BIGINT NOT NULL CHECK (coverage_row_count >= 0),
    summary_row_count BIGINT NOT NULL CHECK (summary_row_count >= 0),
    hypothesis_count BIGINT NOT NULL CHECK (hypothesis_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (validation_fold_ordinal IS NULL OR validation_plan_id IS NOT NULL),
    CHECK (validation_fold_ordinal IS NULL OR validation_fold_ordinal >= 1),
    CHECK (summary_row_count >= hypothesis_count),
    CHECK (
        analysis_intent <> 'validation'
        OR (
            validation_plan_id IS NOT NULL
            AND validation_fold_ordinal IS NOT NULL
        )
    ),
    CHECK (
        analysis_intent <> 'confirmatory_holdout'
        OR (
            validation_plan_id IS NOT NULL
            AND validation_fold_ordinal IS NULL
            AND final_holdout_use_id IS NOT NULL
        )
    ),
    CHECK (
        safety_status <> 'safe'
        OR (
            lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);
```

Version numbers are contiguous per stable definition ID. Canonical JSON is bounded and
validated by typed domain constructors; it is reproduction evidence, not an arbitrary
extension bag. The repository validates exact foreign identities, role capabilities,
intent, definition/result content equality, and one clean confirmatory use. A validation
result may bind a plan/fold; an exploratory result may bind one for diagnostics but cannot
claim validation intent without the appropriate capability. A confirmatory-holdout result
stores the owning plan and exact use with no ordinary fold ordinal; the repository proves
that the use belongs to that plan and remains clean. A nested outer-test result also stores
and verifies the exact frozen-selection capability content; nonnested validation does not
invent one.

`input_row_count` counts unique denominator keys once. `usable_pair_count` sums each exact
feature/label/slice/decision paired membership once before Pearson/Spearman or other metric
reuse; it is not a unique-row claim. Time-series, coverage, and summary counts are exact
output-table totals. `hypothesis_count` counts the contiguous positive inferential
hypothesis ordinals within the larger summary table; all counts reconcile to the output
manifest.

### 20.2 Typed alpha output tables

```sql
CREATE TABLE analysis.alpha_ic_series (
    alpha_analysis_result_id UUID NOT NULL,
    feature_ordinal INTEGER NOT NULL CHECK (feature_ordinal >= 1),
    label_ordinal INTEGER NOT NULL CHECK (label_ordinal >= 1),
    slice_ordinal INTEGER NOT NULL CHECK (slice_ordinal >= 1),
    metric_kind VARCHAR NOT NULL CHECK (
        metric_kind IN ('pearson_ic', 'spearman_ic')
    ),
    decision_at TIMESTAMPTZ NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'insufficient_observations', 'zero_dispersion',
            'invalid_numeric', 'empty_membership'
        )
    ),
    value DOUBLE,
    pair_count BIGINT NOT NULL CHECK (pair_count >= 0),
    denominator_count BIGINT NOT NULL CHECK (denominator_count >= 0),
    membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        alpha_analysis_result_id, feature_ordinal, label_ordinal,
        slice_ordinal, metric_kind, decision_at
    ),
    CHECK (
        (state = 'computed'
            AND value IS NOT NULL
            AND isfinite(value)
            AND value >= -1.0
            AND value <= 1.0)
        OR (state <> 'computed' AND value IS NULL)
    ),
    CHECK (pair_count <= denominator_count)
);

CREATE TABLE analysis.alpha_quantile_series (
    alpha_analysis_result_id UUID NOT NULL,
    feature_ordinal INTEGER NOT NULL CHECK (feature_ordinal >= 1),
    label_ordinal INTEGER NOT NULL CHECK (label_ordinal >= 1),
    slice_ordinal INTEGER NOT NULL CHECK (slice_ordinal >= 1),
    decision_at TIMESTAMPTZ NOT NULL,
    row_kind VARCHAR NOT NULL CHECK (row_kind IN ('bucket', 'spread')),
    bucket_ordinal INTEGER,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'insufficient_observations',
            'invalid_numeric', 'empty_membership'
        )
    ),
    mean_label DOUBLE,
    member_count BIGINT NOT NULL CHECK (member_count >= 0),
    low_member_count BIGINT,
    high_member_count BIGINT,
    raw_weight_sum DOUBLE,
    feature_min DOUBLE,
    feature_max DOUBLE,
    membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        alpha_analysis_result_id, feature_ordinal, label_ordinal,
        slice_ordinal, decision_at, row_kind, bucket_ordinal
    ),
    CHECK (
        (row_kind = 'bucket'
            AND bucket_ordinal >= 1
            AND low_member_count IS NULL
            AND high_member_count IS NULL)
        OR (row_kind = 'spread'
            AND bucket_ordinal = 0
            AND low_member_count >= 0
            AND high_member_count >= 0
            AND member_count = low_member_count + high_member_count)
    ),
    CHECK (
        (state = 'computed' AND mean_label IS NOT NULL AND isfinite(mean_label))
        OR (state <> 'computed' AND mean_label IS NULL)
    ),
    CHECK (
        raw_weight_sum IS NULL
        OR (isfinite(raw_weight_sum) AND raw_weight_sum >= 0.0)
    ),
    CHECK (
        (feature_min IS NULL AND feature_max IS NULL)
        OR (
            feature_min IS NOT NULL
            AND feature_max IS NOT NULL
            AND isfinite(feature_min)
            AND isfinite(feature_max)
            AND feature_min <= feature_max
        )
    )
);

CREATE TABLE analysis.alpha_diagnostic_series (
    alpha_analysis_result_id UUID NOT NULL,
    feature_ordinal INTEGER NOT NULL CHECK (feature_ordinal >= 1),
    label_ordinal INTEGER NOT NULL CHECK (label_ordinal >= 0),
    slice_ordinal INTEGER NOT NULL CHECK (slice_ordinal >= 1),
    metric_code VARCHAR NOT NULL CHECK (
        metric_code IN (
            'monotonicity_spearman', 'monotonicity_slope',
            'monotonicity_adjacency', 'turnover',
            'persistence_pearson', 'persistence_spearman'
        )
    ),
    decision_at TIMESTAMPTZ NOT NULL,
    variant_ordinal INTEGER NOT NULL CHECK (variant_ordinal >= 0),
    metric_variant_content_id VARCHAR NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'insufficient_observations', 'zero_dispersion',
            'invalid_numeric', 'empty_membership'
        )
    ),
    value DOUBLE,
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        alpha_analysis_result_id, feature_ordinal, label_ordinal, slice_ordinal,
        metric_code, decision_at, variant_ordinal
    ),
    CHECK (
        (metric_code LIKE 'monotonicity_%' AND label_ordinal >= 1)
        OR (metric_code NOT LIKE 'monotonicity_%' AND label_ordinal = 0)
    ),
    CHECK (
        (state = 'computed' AND value IS NOT NULL AND isfinite(value))
        OR (state <> 'computed' AND value IS NULL)
    ),
    CHECK (
        state <> 'computed'
        OR metric_code = 'monotonicity_slope'
        OR (
            metric_code IN (
                'monotonicity_spearman',
                'persistence_pearson', 'persistence_spearman'
            )
            AND value >= -1.0
            AND value <= 1.0
        )
        OR (metric_code = 'monotonicity_adjacency' AND value >= 0.0 AND value <= 1.0)
        OR (metric_code = 'turnover' AND value >= 0.0)
    )
);

CREATE TABLE analysis.alpha_exposure_series (
    alpha_analysis_result_id UUID NOT NULL,
    feature_ordinal INTEGER NOT NULL CHECK (feature_ordinal >= 1),
    label_ordinal INTEGER NOT NULL CHECK (label_ordinal >= 0),
    slice_ordinal INTEGER NOT NULL CHECK (slice_ordinal >= 1),
    decision_at TIMESTAMPTZ NOT NULL,
    exposure_kind VARCHAR NOT NULL CHECK (
        exposure_kind IN ('categorical', 'numeric_univariate', 'numeric_joint')
    ),
    exposure_ordinal INTEGER NOT NULL CHECK (exposure_ordinal >= 1),
    category_ordinal INTEGER NOT NULL CHECK (category_ordinal >= 0),
    metric_schema_content_id VARCHAR NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'insufficient_observations', 'zero_dispersion',
            'rank_deficient', 'invalid_numeric', 'empty_membership'
        )
    ),
    association DOUBLE,
    coefficient DOUBLE,
    feature_mean DOUBLE,
    feature_std DOUBLE,
    mean_label DOUBLE,
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    design_rank INTEGER,
    condition_diagnostic DOUBLE,
    membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        alpha_analysis_result_id, feature_ordinal, label_ordinal, slice_ordinal,
        decision_at, exposure_kind, exposure_ordinal, category_ordinal
    ),
    CHECK (
        (exposure_kind = 'categorical' AND category_ordinal >= 1)
        OR (exposure_kind <> 'categorical' AND category_ordinal = 0)
    ),
    CHECK (feature_std IS NULL OR (isfinite(feature_std) AND feature_std >= 0.0)),
    CHECK (design_rank IS NULL OR design_rank >= 0),
    CHECK (
        condition_diagnostic IS NULL
        OR (isfinite(condition_diagnostic) AND condition_diagnostic >= 0.0)
    ),
    CHECK (
        (state = 'computed'
            AND (
                association IS NOT NULL
                OR coefficient IS NOT NULL
                OR feature_mean IS NOT NULL
            ))
        OR (state <> 'computed'
            AND association IS NULL
            AND coefficient IS NULL
            AND feature_mean IS NULL
            AND feature_std IS NULL
            AND mean_label IS NULL
            AND design_rank IS NULL
            AND condition_diagnostic IS NULL)
    ),
    CHECK (
        association IS NULL
        OR (isfinite(association) AND association >= -1.0 AND association <= 1.0)
    ),
    CHECK (coefficient IS NULL OR isfinite(coefficient)),
    CHECK (feature_mean IS NULL OR isfinite(feature_mean)),
    CHECK (mean_label IS NULL OR isfinite(mean_label))
);

CREATE TABLE analysis.alpha_coverage (
    alpha_analysis_result_id UUID NOT NULL,
    feature_ordinal INTEGER NOT NULL CHECK (feature_ordinal >= 1),
    label_ordinal INTEGER NOT NULL CHECK (label_ordinal >= 1),
    slice_ordinal INTEGER NOT NULL CHECK (slice_ordinal >= 1),
    decision_at TIMESTAMPTZ NOT NULL,
    coverage_state VARCHAR NOT NULL CHECK (
        coverage_state IN (
            'included', 'dataset_row_usable', 'feature_computed',
            'feature_noncomputed', 'label_computed', 'label_noncomputed',
            'weight_valid', 'weight_invalid', 'exposure_valid',
            'exposure_invalid', 'paired_usable',
            'metric_computed', 'metric_noncomputed'
        )
    ),
    row_count BIGINT NOT NULL CHECK (row_count >= 0),
    denominator_kind VARCHAR NOT NULL CHECK (
        denominator_kind IN ('universe_eligible', 'included', 'row_usable')
    ),
    denominator_count BIGINT NOT NULL CHECK (denominator_count >= 0),
    ratio DOUBLE,
    PRIMARY KEY (
        alpha_analysis_result_id, feature_ordinal, label_ordinal,
        slice_ordinal, decision_at, coverage_state
    ),
    CHECK (
        (denominator_count = 0 AND ratio IS NULL)
        OR (
            denominator_count > 0
            AND ratio IS NOT NULL
            AND isfinite(ratio)
            AND ratio >= 0.0
            AND ratio <= 1.0
        )
    ),
    CHECK (row_count <= denominator_count)
);
```

`alpha_diagnostic_series` stores the declared monotonicity, turnover, and persistence
time series under closed metric codes/variants. Decay reuses exact IC/quantile rows across
label ordinals; autocorrelation distributions/fits use typed summary metric codes.
`alpha_exposure_series` stores categorical rows and ordered univariate/joint exposure
coefficients with rank/condition/state and exact membership. Metric/variant schema content
IDs fix which nullable typed fields are required. Repositories return typed unions rather
than unchecked name/value maps; no table accepts arbitrary user metric names in 3.0.

```sql
CREATE TABLE analysis.alpha_metric_summaries (
    alpha_analysis_result_id UUID NOT NULL,
    summary_ordinal INTEGER NOT NULL CHECK (summary_ordinal >= 1),
    summary_content_id VARCHAR NOT NULL,
    hypothesis_ordinal INTEGER NOT NULL CHECK (hypothesis_ordinal >= 0),
    hypothesis_content_id VARCHAR,
    family_content_id VARCHAR,
    metric_code VARCHAR NOT NULL,
    metric_schema_content_id VARCHAR NOT NULL,
    state VARCHAR NOT NULL CHECK (
        state IN (
            'computed', 'insufficient_observations', 'zero_dispersion',
            'rank_deficient', 'invalid_numeric', 'empty_membership'
        )
    ),
    estimate DOUBLE,
    standard_error DOUBLE,
    confidence_lower DOUBLE,
    confidence_upper DOUBLE,
    raw_p_value DOUBLE,
    adjusted_p_value DOUBLE,
    observation_count BIGINT NOT NULL CHECK (observation_count >= 0),
    inference_manifest_content_id VARCHAR NOT NULL,
    PRIMARY KEY (alpha_analysis_result_id, summary_ordinal),
    UNIQUE (alpha_analysis_result_id, summary_content_id),
    CHECK (
        (hypothesis_ordinal = 0
            AND hypothesis_content_id IS NULL
            AND family_content_id IS NULL)
        OR (hypothesis_ordinal >= 1
            AND hypothesis_content_id IS NOT NULL
            AND family_content_id IS NOT NULL)
    ),
    CHECK (
        (state = 'computed' AND estimate IS NOT NULL AND isfinite(estimate))
        OR (state <> 'computed' AND estimate IS NULL)
    ),
    CHECK (
        standard_error IS NULL
        OR (isfinite(standard_error) AND standard_error >= 0.0)
    ),
    CHECK (
        (confidence_lower IS NULL AND confidence_upper IS NULL)
        OR (
            confidence_lower IS NOT NULL
            AND confidence_upper IS NOT NULL
            AND isfinite(confidence_lower)
            AND isfinite(confidence_upper)
            AND confidence_lower <= confidence_upper
        )
    ),
    CHECK (
        raw_p_value IS NULL
        OR (isfinite(raw_p_value) AND raw_p_value >= 0.0 AND raw_p_value <= 1.0)
    ),
    CHECK (
        adjusted_p_value IS NULL
        OR (
            isfinite(adjusted_p_value)
            AND adjusted_p_value >= 0.0
            AND adjusted_p_value <= 1.0
        )
    ),
    CHECK (adjusted_p_value IS NULL OR raw_p_value IS NOT NULL),
    CHECK (
        state = 'computed'
        OR (
            standard_error IS NULL
            AND confidence_lower IS NULL
            AND confidence_upper IS NULL
            AND raw_p_value IS NULL
            AND adjusted_p_value IS NULL
        )
    ),
    CHECK (
        hypothesis_ordinal >= 1
        OR (
            standard_error IS NULL
            AND confidence_lower IS NULL
            AND confidence_upper IS NULL
            AND raw_p_value IS NULL
            AND adjusted_p_value IS NULL
        )
    )
);
```

Summary ordinals are contiguous across every descriptive/inferential statistic.
`hypothesis_ordinal=0` marks a descriptive row; positive hypothesis ordinals are
separately unique and contiguous in canonical family/hypothesis order. The repository
enforces those cross-row rules and permits standard errors/intervals/p-values only on
hypothesis rows.

Additional state/reason and bootstrap/chunk-manifest tables use exact migration-owned
schemas. All shown/companion row counts reconcile to `alpha_analysis_results` and its
output manifest. Null is allowed only for a typed noncomputed/not-requested field;
NaN/infinity is rejected at publication.

### 20.3 Validation schemes and completed plans

```sql
CREATE TABLE analysis.validation_schemes (
    validation_scheme_id UUID PRIMARY KEY,
    qualified_name VARCHAR NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analysis.validation_scheme_versions (
    validation_scheme_id UUID NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    scheme_kind VARCHAR NOT NULL CHECK (
        scheme_kind IN ('expanding', 'rolling', 'combinatorial_purged', 'nested')
    ),
    description VARCHAR NOT NULL,
    assumptions_and_limitations VARCHAR NOT NULL,
    window_manifest_content_id VARCHAR NOT NULL,
    purge_policy_content_id VARCHAR NOT NULL,
    embargo_policy_content_id VARCHAR NOT NULL,
    holdout_policy_content_id VARCHAR NOT NULL,
    minimum_count_policy_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    scheme_schema_version INTEGER NOT NULL CHECK (scheme_schema_version >= 1),
    scheme_content_id VARCHAR NOT NULL UNIQUE,
    scheme_json JSON NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (validation_scheme_id, version),
    CHECK (length(description) <= 65536),
    CHECK (
        length(assumptions_and_limitations) > 0
        AND length(assumptions_and_limitations) <= 65536
    )
);

CREATE TABLE analysis.validation_plans (
    validation_plan_id UUID PRIMARY KEY,
    validation_scheme_id UUID NOT NULL,
    scheme_version INTEGER NOT NULL CHECK (scheme_version >= 1),
    scheme_kind VARCHAR NOT NULL CHECK (
        scheme_kind IN ('expanding', 'rolling', 'combinatorial_purged', 'nested')
    ),
    resolved_split_kind VARCHAR NOT NULL CHECK (
        resolved_split_kind IN ('expanding', 'rolling', 'combinatorial_purged')
    ),
    resolved_split_content_id VARCHAR NOT NULL,
    research_dataset_build_id UUID NOT NULL,
    parent_validation_plan_id UUID,
    parent_fold_ordinal INTEGER,
    input_manifest_content_id VARCHAR NOT NULL,
    target_manifest_content_id VARCHAR NOT NULL,
    base_key_manifest_content_id VARCHAR NOT NULL,
    relationship_manifest_content_id VARCHAR NOT NULL,
    derived_leakage_scope VARCHAR NOT NULL CHECK (
        derived_leakage_scope IN ('entity', 'group', 'panel')
    ),
    resolved_leakage_scope VARCHAR NOT NULL CHECK (
        resolved_leakage_scope IN ('entity', 'group', 'panel')
    ),
    plan_start_at TIMESTAMPTZ NOT NULL,
    plan_end_at TIMESTAMPTZ NOT NULL,
    holdout_start_at TIMESTAMPTZ,
    holdout_end_at TIMESTAMPTZ,
    holdout_boundary_content_id VARCHAR NOT NULL,
    holdout_cleanliness_attestation_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    limits_content_id VARCHAR NOT NULL,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    candidate_audit_relation_name VARCHAR NOT NULL UNIQUE,
    candidate_reason_relation_name VARCHAR NOT NULL UNIQUE,
    membership_relation_name VARCHAR NOT NULL UNIQUE,
    membership_reason_relation_name VARCHAR NOT NULL UNIQUE,
    relationship_relation_name VARCHAR NOT NULL UNIQUE,
    holdout_relation_name VARCHAR NOT NULL UNIQUE,
    output_manifest_content_id VARCHAR NOT NULL,
    lineage_manifest_content_id VARCHAR NOT NULL,
    lineage_completeness VARCHAR NOT NULL CHECK (
        lineage_completeness IN ('complete', 'partial', 'opaque')
    ),
    dependency_root_closure_complete BOOLEAN NOT NULL,
    safety_manifest_content_id VARCHAR NOT NULL,
    safety_status VARCHAR NOT NULL CHECK (safety_status IN ('safe', 'unsafe')),
    licensing_manifest_content_id VARCHAR NOT NULL,
    information_class VARCHAR NOT NULL CHECK (information_class = 'label'),
    input_sample_count BIGINT NOT NULL CHECK (input_sample_count >= 0),
    development_sample_count BIGINT NOT NULL CHECK (development_sample_count >= 0),
    holdout_sample_count BIGINT NOT NULL CHECK (holdout_sample_count >= 0),
    fold_count INTEGER NOT NULL CHECK (fold_count >= 0),
    valid_fold_count INTEGER NOT NULL CHECK (valid_fold_count >= 0),
    membership_row_count BIGINT NOT NULL CHECK (membership_row_count >= 0),
    relationship_edge_count BIGINT NOT NULL CHECK (relationship_edge_count >= 0),
    candidate_reason_count BIGINT NOT NULL CHECK (candidate_reason_count >= 0),
    exclusion_reason_count BIGINT NOT NULL CHECK (exclusion_reason_count >= 0),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK (plan_start_at < plan_end_at),
    CHECK (
        (parent_validation_plan_id IS NULL AND parent_fold_ordinal IS NULL)
        OR (parent_validation_plan_id IS NOT NULL AND parent_fold_ordinal >= 1)
    ),
    CHECK (
        (holdout_start_at IS NULL AND holdout_end_at IS NULL)
        OR (
            holdout_start_at IS NOT NULL
            AND holdout_end_at IS NOT NULL
            AND plan_start_at <= holdout_start_at
            AND holdout_start_at < holdout_end_at
            AND holdout_end_at <= plan_end_at
        )
    ),
    CHECK (development_sample_count + holdout_sample_count = input_sample_count),
    CHECK (valid_fold_count <= fold_count),
    CHECK (membership_row_count = development_sample_count * fold_count),
    CHECK (
        safety_status <> 'safe'
        OR (
            lineage_completeness = 'complete'
            AND dependency_root_closure_complete
        )
    )
);
```

For a nonnested scheme, `resolved_split_kind`/content identify that scheme's own split. A
nested root stores its outer split and each child stores the inner split while all retain
the registered nested scheme/version and parent/fold proof.

`holdout_boundary_content_id` identifies either `NoFinalHoldout` or the exact resolved
boundary/root, so it is always nonnull. The cleanliness field likewise identifies either
`NoFinalHoldoutAttestation` or the exact bounded attestation/prior-managed-access audit.
Nested child plans have their parent's final-train candidate root in
`input_manifest_content_id` and retain the original build ID for lineage.
The repository enforces scope strength, contiguous versions, exact parent disjointness,
and scheme-specific fold/count rules that local checks cannot express.

### 20.4 Folds, segments, groups, and controlled membership

```sql
CREATE TABLE analysis.validation_folds (
    validation_plan_id UUID NOT NULL,
    fold_ordinal INTEGER NOT NULL CHECK (fold_ordinal >= 1),
    fold_state VARCHAR NOT NULL CHECK (fold_state IN ('valid', 'invalid')),
    raw_train_decision_count BIGINT NOT NULL CHECK (raw_train_decision_count >= 0),
    raw_validation_decision_count BIGINT NOT NULL CHECK (
        raw_validation_decision_count >= 0
    ),
    raw_test_decision_count BIGINT NOT NULL CHECK (raw_test_decision_count >= 0),
    retained_train_sample_count BIGINT NOT NULL CHECK (
        retained_train_sample_count >= 0
    ),
    retained_validation_sample_count BIGINT NOT NULL CHECK (
        retained_validation_sample_count >= 0
    ),
    retained_test_sample_count BIGINT NOT NULL CHECK (
        retained_test_sample_count >= 0
    ),
    purged_sample_count BIGINT NOT NULL CHECK (purged_sample_count >= 0),
    embargoed_sample_count BIGINT NOT NULL CHECK (embargoed_sample_count >= 0),
    other_excluded_sample_count BIGINT NOT NULL CHECK (
        other_excluded_sample_count >= 0
    ),
    membership_content_id VARCHAR NOT NULL,
    exclusion_manifest_content_id VARCHAR NOT NULL,
    invalid_reason_code VARCHAR,
    PRIMARY KEY (validation_plan_id, fold_ordinal),
    CHECK (
        (fold_state = 'valid' AND invalid_reason_code IS NULL)
        OR (fold_state = 'invalid' AND invalid_reason_code IS NOT NULL)
    )
);

CREATE TABLE analysis.validation_fold_segments (
    validation_plan_id UUID NOT NULL,
    fold_ordinal INTEGER NOT NULL CHECK (fold_ordinal >= 1),
    segment_ordinal INTEGER NOT NULL CHECK (segment_ordinal >= 1),
    raw_role VARCHAR NOT NULL CHECK (raw_role IN ('validation', 'test')),
    group_ordinal INTEGER,
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    latest_information_end TIMESTAMPTZ,
    embargo_end_at TIMESTAMPTZ,
    segment_membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (validation_plan_id, fold_ordinal, segment_ordinal),
    CHECK (start_at < end_at),
    CHECK (group_ordinal IS NULL OR group_ordinal >= 1),
    CHECK (
        embargo_end_at IS NULL
        OR (
            latest_information_end IS NOT NULL
            AND embargo_end_at >= latest_information_end
        )
    )
);

CREATE TABLE analysis.validation_segment_embargo_roots (
    validation_plan_id UUID NOT NULL,
    fold_ordinal INTEGER NOT NULL CHECK (fold_ordinal >= 1),
    segment_ordinal INTEGER NOT NULL CHECK (segment_ordinal >= 1),
    root_ordinal INTEGER NOT NULL CHECK (root_ordinal >= 1),
    relationship_root_content_id VARCHAR NOT NULL,
    latest_information_end TIMESTAMPTZ NOT NULL,
    embargo_last_decision_at TIMESTAMPTZ,
    embargo_decision_count BIGINT NOT NULL CHECK (embargo_decision_count >= 0),
    embargo_membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (
        validation_plan_id, fold_ordinal, segment_ordinal, root_ordinal
    ),
    UNIQUE (
        validation_plan_id, fold_ordinal, segment_ordinal,
        relationship_root_content_id
    ),
    CHECK (
        (embargo_decision_count = 0 AND embargo_last_decision_at IS NULL)
        OR (
            embargo_decision_count > 0
            AND embargo_last_decision_at > latest_information_end
        )
    )
);

CREATE TABLE analysis.validation_group_assignments (
    validation_plan_id UUID NOT NULL,
    group_ordinal INTEGER NOT NULL CHECK (group_ordinal >= 1),
    start_at TIMESTAMPTZ NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    decision_count BIGINT NOT NULL CHECK (decision_count > 0),
    decision_membership_content_id VARCHAR NOT NULL,
    PRIMARY KEY (validation_plan_id, group_ordinal),
    CHECK (start_at < end_at)
);

CREATE TABLE analysis.validation_fold_test_groups (
    validation_plan_id UUID NOT NULL,
    fold_ordinal INTEGER NOT NULL CHECK (fold_ordinal >= 1),
    combination_ordinal INTEGER NOT NULL CHECK (combination_ordinal >= 1),
    group_ordinal INTEGER NOT NULL CHECK (group_ordinal >= 1),
    PRIMARY KEY (validation_plan_id, fold_ordinal, combination_ordinal),
    UNIQUE (validation_plan_id, fold_ordinal, group_ordinal)
);
```

The segment row's latest/embargo fields are segment-level bounded summaries. The
`validation_segment_embargo_roots` rows are authoritative for relationship-scoped origins
and exact embargo decisions; their roots/counts reconcile to exclusion causes.

Each plan owns controlled dynamic relations with canonical names generated from its UUID,
never accepted from callers. Their logical schemas are:

```sql
CREATE TABLE analysis.validation_candidates_<plan_token> (
    candidate_ordinal BIGINT PRIMARY KEY,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    eligibility_state VARCHAR NOT NULL CHECK (
        eligibility_state IN (
            'eligible', 'dataset_unusable', 'feature_noncomputed',
            'label_noncomputed', 'interval_missing', 'interval_invalid'
        )
    ),
    sample_start TIMESTAMPTZ,
    sample_end TIMESTAMPTZ,
    primary_reason_code VARCHAR,
    reason_count INTEGER NOT NULL CHECK (reason_count >= 0),
    relationship_edge_content_id VARCHAR NOT NULL,
    row_lineage_content_id VARCHAR NOT NULL,
    UNIQUE (decision_at, instrument_id),
    CHECK (candidate_ordinal >= 1),
    CHECK (
        (sample_start IS NULL AND sample_end IS NULL)
        OR (sample_start IS NOT NULL AND sample_end IS NOT NULL AND sample_start <= sample_end)
    ),
    CHECK (
        (eligibility_state = 'eligible'
            AND sample_start IS NOT NULL
            AND primary_reason_code IS NULL
            AND reason_count = 0)
        OR (eligibility_state <> 'eligible'
            AND primary_reason_code IS NOT NULL
            AND reason_count > 0)
    )
);

CREATE TABLE analysis.validation_candidate_reasons_<plan_token> (
    candidate_region VARCHAR NOT NULL CHECK (
        candidate_region IN ('development', 'final_holdout')
    ),
    candidate_ordinal BIGINT NOT NULL,
    reason_ordinal INTEGER NOT NULL,
    reason_code VARCHAR NOT NULL,
    evidence_content_id VARCHAR NOT NULL,
    PRIMARY KEY (candidate_region, candidate_ordinal, reason_ordinal),
    CHECK (candidate_ordinal >= 1 AND reason_ordinal >= 1)
);

CREATE TABLE analysis.validation_membership_<plan_token> (
    fold_ordinal INTEGER NOT NULL,
    membership_ordinal BIGINT NOT NULL,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    raw_role VARCHAR NOT NULL,
    final_role VARCHAR NOT NULL,
    eligibility_state VARCHAR NOT NULL CHECK (
        eligibility_state IN (
            'eligible', 'dataset_unusable', 'feature_noncomputed',
            'label_noncomputed', 'interval_missing', 'interval_invalid'
        )
    ),
    sample_start TIMESTAMPTZ,
    sample_end TIMESTAMPTZ,
    primary_reason_code VARCHAR,
    reason_count INTEGER NOT NULL,
    relationship_edge_content_id VARCHAR NOT NULL,
    row_lineage_content_id VARCHAR NOT NULL,
    PRIMARY KEY (fold_ordinal, membership_ordinal),
    UNIQUE (fold_ordinal, decision_at, instrument_id),
    CHECK (fold_ordinal >= 1 AND membership_ordinal >= 1),
    CHECK (
        raw_role IN ('train', 'validation', 'test')
        AND final_role IN ('train', 'validation', 'test', 'excluded')
    ),
    CHECK (
        (sample_start IS NULL AND sample_end IS NULL)
        OR (sample_start IS NOT NULL AND sample_end IS NOT NULL AND sample_start <= sample_end)
    ),
    CHECK (
        (eligibility_state = 'eligible'
            AND sample_start IS NOT NULL
            AND (final_role = raw_role OR final_role = 'excluded'))
        OR (eligibility_state <> 'eligible' AND final_role = 'excluded')
    ),
    CHECK (
        (final_role = raw_role AND primary_reason_code IS NULL AND reason_count = 0)
        OR (final_role = 'excluded' AND primary_reason_code IS NOT NULL AND reason_count > 0)
    )
);

CREATE TABLE analysis.validation_membership_reasons_<plan_token> (
    fold_ordinal INTEGER NOT NULL,
    membership_ordinal BIGINT NOT NULL,
    reason_ordinal INTEGER NOT NULL,
    reason_code VARCHAR NOT NULL,
    causing_role VARCHAR,
    causing_segment_ordinal INTEGER,
    causing_relationship_root_content_id VARCHAR,
    evidence_content_id VARCHAR NOT NULL,
    PRIMARY KEY (fold_ordinal, membership_ordinal, reason_ordinal),
    CHECK (fold_ordinal >= 1 AND membership_ordinal >= 1 AND reason_ordinal >= 1)
);

CREATE TABLE analysis.validation_relationships_<plan_token> (
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    root_ordinal INTEGER NOT NULL,
    leakage_scope VARCHAR NOT NULL,
    relationship_root_content_id VARCHAR NOT NULL,
    lineage_content_id VARCHAR NOT NULL,
    PRIMARY KEY (decision_at, instrument_id, root_ordinal),
    UNIQUE (decision_at, instrument_id, relationship_root_content_id),
    CHECK (root_ordinal >= 1 AND leakage_scope IN ('entity', 'group', 'panel'))
);

CREATE TABLE analysis.validation_holdout_<plan_token> (
    candidate_ordinal BIGINT PRIMARY KEY,
    decision_at TIMESTAMPTZ NOT NULL,
    instrument_id UUID NOT NULL,
    eligibility_state VARCHAR NOT NULL CHECK (
        eligibility_state IN (
            'eligible', 'dataset_unusable', 'feature_noncomputed',
            'label_noncomputed', 'interval_missing', 'interval_invalid'
        )
    ),
    sample_start TIMESTAMPTZ,
    sample_end TIMESTAMPTZ,
    primary_reason_code VARCHAR,
    reason_count INTEGER NOT NULL CHECK (reason_count >= 0),
    relationship_edge_content_id VARCHAR NOT NULL,
    row_lineage_content_id VARCHAR NOT NULL,
    UNIQUE (decision_at, instrument_id),
    CHECK (candidate_ordinal >= 1),
    CHECK (
        (sample_start IS NULL AND sample_end IS NULL)
        OR (sample_start IS NOT NULL AND sample_end IS NOT NULL AND sample_start <= sample_end)
    ),
    CHECK (
        (eligibility_state = 'eligible'
            AND sample_start IS NOT NULL
            AND primary_reason_code IS NULL
            AND reason_count = 0)
        OR (eligibility_state <> 'eligible'
            AND primary_reason_code IS NOT NULL
            AND reason_count > 0)
    )
);
```

The repository constrains actual identifiers to generated `analysis` names, verifies
catalog ownership/schema/column types before every read, and never returns relation names
to public callers. Holdout relations require a live matching capability. Membership
ordinals follow decision then instrument order within a fold; reasons follow section 15.
The plan manifest hashes every canonical chunk plus all normalized fold/group rows.

The development candidate audit and sealed plan-wide holdout relation partition every
input sample exactly once; holdout rows are not duplicated into folds. Candidate reasons
cover both regions with separate ordinal namespaces. Every development candidate appears
exactly once in every fold membership so its decision-level raw role remains auditable;
ineligible samples have final role `excluded`, while eligible samples are retained or
excluded by fold policy. Thus each plan's membership-row count equals its own exact
development candidate count times fold count, including for a nested child's narrower
candidate root.

### 20.5 Holdout uses and monotone contamination

```sql
CREATE TABLE analysis.final_holdout_uses (
    final_holdout_use_id UUID PRIMARY KEY,
    validation_plan_id UUID NOT NULL,
    selection_manifest_content_id VARCHAR NOT NULL,
    evaluation_manifest_content_id VARCHAR NOT NULL,
    implementation_identity_content_id VARCHAR NOT NULL,
    environment_manifest_content_id VARCHAR NOT NULL,
    selection_frozen_at TIMESTAMPTZ NOT NULL,
    use_status VARCHAR NOT NULL CHECK (use_status IN ('confirmatory', 'contaminated')),
    confirmatory_slot INTEGER,
    execution_content_id VARCHAR NOT NULL UNIQUE,
    capability_scope_content_id VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (validation_plan_id, confirmatory_slot),
    CHECK (
        (use_status = 'confirmatory' AND confirmatory_slot = 1)
        OR (use_status = 'contaminated' AND confirmatory_slot IS NULL)
    ),
    CHECK (selection_frozen_at <= created_at)
);

CREATE TABLE analysis.final_holdout_contamination (
    validation_plan_id UUID NOT NULL,
    contamination_ordinal INTEGER NOT NULL CHECK (contamination_ordinal >= 1),
    final_holdout_use_id UUID,
    source_kind VARCHAR NOT NULL CHECK (
        source_kind IN ('managed_reuse', 'external_inspection', 'user_report', 'other')
    ),
    reason_code VARCHAR NOT NULL,
    detail_content_id VARCHAR NOT NULL,
    evidence_content_id VARCHAR NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (validation_plan_id, contamination_ordinal)
);
```

`exact_retry` is a service return outcome; it does not mutate a stored clean use from
`confirmatory` or create another row. The nullable unique slot enforces at most one clean
use per plan; the repository additionally rejects a clean insert when any earlier
contaminated use or contamination fact exists. Contamination is derived from the
append-only use/contamination rows and is therefore monotone; `validation_plans` is not
updated. Detail/evidence is bounded, credential-free, and licensing-aware.

## 21. Public APIs, frames, resources, and operational behavior

### 21.1 Alpha and validation services

```python no-run
alpha_definition = project.services.research.alpha.register(definition)
alpha_result = project.services.research.alpha.analyze(
    definition=alpha_definition,
    input=AlphaInputSpec(
        dataset_build=analysis_build.id,
        features=(feature_output,),
        labels=(forward_return_output,),
        eligibility=EligibilityPolicy.COMPLETE_CASE,
        coverage_denominator=CoverageDenominator.INCLUDED,
    ),
    limits=AlphaAnalysisLimits(),
)

scheme = project.services.research.validation.register(validation_definition)
plan = project.services.research.validation.create_plan(
    scheme=scheme,
    input=ValidationInputSpec(
        dataset_build=analysis_build.id,
        features=(feature_output,),
        targets=(forward_return_output,),
    ),
    limits=ValidationPlanLimits(),
)

for fold in plan.iter_folds():
    train = fold.membership(ValidationRole.TRAIN, max_rows=2_000_000)
    test = fold.membership(ValidationRole.TEST, max_rows=2_000_000)
```

Registration returns an exact version reference; analysis/creation never resolves a
floating name after execution identity begins. Handles are immutable repository-backed
values and revalidate project/database state. They expose summaries, bounded rows,
provenance, lineage, safety/licensing, and exact IDs—not connections or SQL relation names.

`AlphaAnalysisResult` has no feature/dataset/strategy/simulation adapter. A result can be
referenced by later analysis/reporting artifacts only. A nonnested plan's test role is an
ordinary validation-evaluation role and is accessible to `AnalysisIntent.VALIDATION`.
Nested inner roles are accessible inside the outer-train selection workflow, while every
nested outer test remains sealed until its exact selection manifest freezes. A final
holdout always requires its separate one-use capability.

### 21.2 Estimator interoperability

This plan does not implement a general estimator interface. A
`FinanceAwareSklearnAdapter` may translate one exact plan/fold into positional arrays for
scikit-learn-compatible estimators only after binding a `SampleIndexMap`:

```python no-run
sample_index = plan.bind_sample_index(
    keys=training_keys,
    source_dataset_build=analysis_build.id,
)
splitter = plan.sklearn_adapter(sample_index)
for train_positions, test_positions in splitter.split():
    fit_and_score(train_positions, test_positions)
```

The key frame must contain unique exact `decision_at`/`instrument_id` keys, preserve its
source-build/content identity, and match the declared complete or explicitly audited
subset. Reordering is allowed because positions are mapped by keys; duplicates, untracked
omissions/extras, changed timestamp precision, or another build reject. The adapter only
maps already-persisted final membership and never infers folds from array length, row
spacing, labels, estimator state, or `y`. Validation roles can be returned separately;
excluded rows are never yielded. A nested outer-test adapter additionally requires its
matching frozen-selection capability; final-holdout positions are available only through
the matching holdout-use capability and are never mixed into ordinary `split()` output.

Plan 10 requests a nonserializable `ValidationTrainingCapability` for one exact plan/fold,
fit purpose, role set, selected feature/label outputs, and `planned_fit_content_id`. The
planned-fit ID freezes the complete recipe plus the already-frozen selection-manifest root
where required, but excludes the capability that will bind it, the future fit occurrence,
publication metadata, model-state/output roots, and causal release. The issuer derives
membership; the caller cannot submit keys or broaden roles:

`project.services.research.validation.authorize_training(request)` accepts only the bounded
authorization request produced by plan-10 `plan_fit()`. It independently resolves the
referenced plan/fold/selection state, recomputes permitted roles and membership roots,
verifies the planned-fit ID, and returns the scoped capability; it does not accept caller-
supplied membership rows or role overrides. Its stable authorization content proof excludes
the runtime bearer token/session/expiry, which enforce access but do not alter fit execution
identity; renewed issuance revalidates current holdout/contamination state before reusing
that proof.

| Fit purpose | Fit membership | Score membership | Gate |
| --- | --- | --- | --- |
| `fold_training` | final `train` | none | ordinary fold-training capability |
| `inner_selection` | inner `train` | inner `validation` | exact inner candidate/selection workflow |
| `selected_refit` | declared outer `train` plus `validation` | none | frozen selection with the same planned refit; outer test remains sealed |
| `final_holdout_refit` | exact non-holdout development membership | none | frozen final selection/planned refit; holdout unopened and clean |
| `historical_production` | chronological `train` whose labels are available by each fit cutoff | none | matching fold in a predeclared expanding/rolling plan and fit schedule |

No capability includes ordinary outer-test or final-holdout labels. A final-holdout refit
may include already evaluated non-holdout development test rows only when the frozen final
selection declares that exact membership before holdout access. The capability is scoped
to one open project/operation and planned execution, expires without becoming a persisted
label handle, and is reproduced as an exact content proof in the plan-10 fit. It exposes
bounded internal training/scoring partitions, never arbitrary label SQL or ordinary
`split()` positions.

The existing fold, frozen-selection outer-test, and final-holdout-use capabilities may
also authorize plan 10 to run a completed fit on their exact bounded feature membership for
managed scoring. Resulting predictions and metrics remain label-classified evidence owned
by this plan or plan 14; the capability cannot publish a forecast materialization or causal
decision adapter.

Plan 10 owns registered forecast/risk estimator definitions, parameters, preprocessing,
fits, releases, and one supplied selection manifest. Plan 14 owns study/trial/search/
attempt identities and search-result aggregation. Scikit-learn can be a bounded consumer,
but Persistra continues to own financial membership, purge/embargo provenance, temporal
capabilities, and exact fold aggregation.

### 21.3 Dataframe contracts

Normal dataframe methods never truncate. Crossing `max_rows` raises the relevant result
limit error. `preview(rows=N)` is a separately named, explicitly truncated, analysis-only
surface; it is unavailable for a sealed holdout. Iterators yield complete deterministic
chunks and hold no write transaction while caller code runs.

| Frame | Schema | Required fields |
| --- | --- | --- |
| IC series | `persistra.dataframe.alpha_ic_series@1` | result/feature/label/slice/metric, decision, state/value, pair/denominator counts, membership ID |
| Quantile series | `persistra.dataframe.alpha_quantile_series@1` | result/feature/label/slice, decision, bucket/spread, state/value/bucket and endpoint counts/weight/bounds, membership ID |
| Alpha coverage | `persistra.dataframe.alpha_coverage@1` | result/dimensions/decision, denominator/state counts and ratio |
| Alpha diagnostics | `persistra.dataframe.alpha_diagnostics@1` | typed metric dimensions, decision/lag/horizon/exposure, state/value/count, membership ID |
| Alpha summaries | `persistra.dataframe.alpha_summaries@1` | summary and optional hypothesis/family/metric identities, estimate/inference/CI/raw and adjusted p-value/count/state |
| Alpha provenance | `persistra.dataframe.alpha_provenance@1` | definition/input/component/snapshot/schedule/cutoff/validation/code/inference/execution/output/safety/licensing IDs |
| Validation folds | `persistra.dataframe.validation_folds@1` | plan/fold/state, nominal/actual bounds, raw/retained/excluded counts and roots |
| Validation segments | `persistra.dataframe.validation_segments@1` | plan/fold/segment/role/group, interval, latest-information/embargo end, root |
| Validation candidates | `persistra.dataframe.validation_candidates@1` | plan/development key, eligibility/state/reasons, closed interval, relationship and lineage roots |
| Validation membership | `persistra.dataframe.validation_membership@1` | plan/fold/key, raw/final role, eligibility, closed interval, primary reason/count, lineage/root |
| Validation exclusions | `persistra.dataframe.validation_exclusions@1` | plan/fold/key/reason ordinal/code, causing role/segment/root, evidence ID |
| Validation relationships | `persistra.dataframe.validation_relationships@1` | plan/key/root ordinal/scope/root and lineage IDs |
| Holdout summary | `persistra.dataframe.validation_holdout_summary@1` | plan, exact boundary, aggregate counts/roots and contamination state only |

Frames use explicit columns, typed-wire IDs, `datetime64[us, UTC]`, pandas nullable dtypes,
finite `float64`, and stable ordinals. Semantic keys are columns rather than hidden indexes.
Empty frames preserve exact dtypes and dynamic schemas. Membership frames order by fold,
decision, instrument; metric frames use slice, feature, label, metric, decision, then typed
subdimension order.

### 21.4 Resource enforcement

The section-4 limits apply at estimate and runtime. Additional deployment hard ceilings
are: 1 MiB per canonical cell, 16 MiB per canonical row, 1 GiB per analytical partition,
4 GiB temporary state per worker, 32 combinatorial groups, 256 slices/features as declared,
100,000 hypotheses, and 10,000 bootstrap repetitions/folds. Project configuration may
lower them. A permitted increase enters execution identity and cannot exceed the hard
ceiling.

Crossing any ceiling—including candidate or reason rows—fails rather than sampling
entities/decisions, truncating lineage, reducing bootstrap repetitions, merging groups,
dropping combinations/folds/hypotheses, weakening relationship scope, shortening label
intervals, or disabling audit. Runtime counters are authoritative when estimates
understate range-join or bootstrap work.

Cross-sectional statistics operate on one bounded decision/slice partition. Temporal
summaries stream typed series; bootstrap retains/resamples bounded decision statistics,
not panel rows. Split construction partitions by folds/decision ranges and persists
ordered chunks. A single cross-section or relationship expansion above its hard bound
fails explicitly rather than being split in a way that changes ranks/scope.

### 21.5 Determinism and numeric behavior

Canonical ordering is:

1. exact dependency/output/slice/hypothesis ordinals;
2. the pinned schedule's unique increasing decision instant;
3. instrument UUID bytes, group/root content ID, and typed subdimension ordinal; and
4. fold group combinations lexicographically, then fold/segment/membership ordinal.

Floating computation uses finite `float64`, the registered deterministic reduction tree,
and pinned NumPy/BLAS/LAPACK/math-kernel identities. Pair counts and sums are accumulated
in canonical chunks and merged by a fixed tree; worker completion order cannot change the
last bit. Quantile ties use exact normalized values and average ranks. OLS uses the pinned
QR/tolerance contract. Nonfinite inputs/states are excluded or fatal by declared policy,
never silently coerced.

Bootstrap randomness is solely the explicit plan-01 seed plus a registered counter-based
generator and hypothesis/repetition/block counter. It does not read process-global RNG
state. Shared family block starts are reproducible independent of worker count. Calendar
and UTC behavior binds the exact schedule/time-zone database identity.

### 21.6 Security, licensing, and observability

All analytical SQL is library-owned parameterized SQL over repository-validated relation
handles. Definition/scheme JSON, slice names, reason details, metric codes, and physical
tokens cannot become identifiers or SQL fragments. No callback, estimator, or user SQL is
executed by this plan. Credentials, raw licensed values, arbitrary exception text,
physical names, complete key lists, and holdout membership are absent from ordinary
events/logs/metrics.

Row-level output and holdout access enforce the most restrictive input license. An
aggregate statistic is not presumed exportable. Safety and licensing are orthogonal:
`allow_unsafe_analysis` does not override export restrictions, and a safe result may still
be nonexportable.

Observability distinguishes registration, exact verification, input/state exclusion,
metric computation/noncomputation, HAC/bootstrap, hypothesis adjustment, fold/group/
segment construction, purging by scope, embargo, sealed-access rejection, clean use,
contamination, resource/cancellation, and atomic publication. Labels are bounded enums and
ID prefixes, never user names, instrument IDs, hypothesis text, data values, or complete
content IDs.

## 22. Events, exceptions, and stable reason codes

### 22.1 Lifecycle events

| Event type | Aggregate kind | Published when |
| --- | --- | --- |
| `persistra.alpha.definition_registered@1` | `persistra.aggregate.alpha_analysis_definition` | A contiguous definition version commits |
| `persistra.alpha.analysis_completed@1` | `persistra.aggregate.alpha_analysis_result` | A verified immutable alpha result commits |
| `persistra.validation.scheme_registered@1` | `persistra.aggregate.validation_scheme` | A contiguous scheme version commits |
| `persistra.validation.plan_created@1` | `persistra.aggregate.validation_plan` | Each verified immutable root or child plan occurrence commits |
| `persistra.validation.final_holdout_used@1` | `persistra.aggregate.final_holdout_use` | A clean or explicitly contaminated managed use commits |
| `persistra.validation.final_holdout_contamination_recorded@1` | `persistra.aggregate.final_holdout_contamination` | An external/user contamination fact commits |

Definition/scheme aggregate sequence equals their positive contiguous version. Result,
plan, and holdout-use occurrence aggregates have sequence 1. Contamination aggregates use
the plan ID with sequence equal to `contamination_ordinal`. Exact registration, result,
plan, or use retries emit no duplicate event. A nested tree publishes one plan event per
new occurrence in root then outer-fold/child order, all in the same transaction/captured
instant.

Events carry typed IDs/versions, intent/scheme kind, content/manifests, bounded counts,
scope/status/safety/licensing classifications, and the injected publication instant. They
contain no analytical values, p-values, feature/label values, membership keys, hypotheses,
selection parameters marked sensitive, physical relations, arbitrary detail/evidence, or
credentials. Metadata/output/use/fact and its event commit together.

All events use one transaction-captured instant for `event_at`, `available_at`, and
`recorded_at`. That publication time does not replace decisions, label intervals, input
availability, selection freeze, or holdout boundary time.

### 22.2 Public exceptions

| Exception | Stable reason code | Trigger |
| --- | --- | --- |
| `AlphaAnalysisDefinitionError` | `alpha.definition.invalid` | Definition, metric, slice, intent, or family contract is invalid |
| `AlphaInputError` | `alpha.input.invalid` | Dataset/component/role/key/state/unit input is incompatible |
| `AlphaAnalysisExecutionError` | `alpha.execution.failed` | Diagnostic execution cannot complete |
| `AlphaInferenceError` | `alpha.inference.invalid` | HAC/bootstrap/confidence/adjustment contract cannot be satisfied |
| `AlphaResultLimitError` | `alpha.resource.limit` | Alpha rows, partitions, hypotheses, bootstrap, memory, temp, or time exceeds a limit |
| `ValidationSchemeError` | `validation.scheme.invalid` | Window/group/nesting/holdout definition is invalid |
| `ValidationPlanError` | `validation.plan.invalid` | Exact input cannot yield the declared plan |
| `ValidationMembershipError` | `validation.membership.invalid` | Role, interval, relationship, purge, embargo, or reconciliation violates contract |
| `FinalHoldoutAccessError` | `validation.holdout.access_denied` | Capability, frozen selection, clean-use, or contamination rule rejects access |
| `ValidationPlanLimitError` | `validation.resource.limit` | Fold, edge, membership, partition, memory, temp, or time exceeds a limit |
| `AnalysisExactReuseError` | `analysis.reuse.corrupt` | Stored exact definition/result/plan/use fails verification |

They inherit the plan-01 hierarchy and carry bounded structured IDs, phases, counts,
ranges, and reason codes. An orchestration error preserves its causal typed exception;
arbitrary library/solver/estimator text is not copied into public diagnostics.

### 22.3 Alpha row/metric/inference reasons

| Reason code | Meaning/default disposition |
| --- | --- |
| `alpha.row.usable` | Paired row is eligible for the requested metric |
| `alpha.row.dataset_unusable` | Plan-07 row audit excludes the row |
| `alpha.row.feature_noncomputed` | Exact feature output state is noncomputed |
| `alpha.row.label_noncomputed` | Exact label is censored/ambiguous/otherwise noncomputed |
| `alpha.row.weight_invalid` | Required weight is missing, nonfinite, zero, or negative |
| `alpha.row.exposure_invalid` | Required exposure/category is invalid under policy |
| `alpha.row.slice_excluded` | Row is outside the predeclared slice |
| `alpha.metric.insufficient_cross_section` | Pair/bucket count is below its declared minimum |
| `alpha.metric.zero_dispersion` | Feature, label, ranks, or required regressor has zero dispersion |
| `alpha.metric.rank_deficient` | Joint exposure design violates its declared rank policy |
| `alpha.metric.nonfinite` | Deterministic arithmetic yields an invalid nonfinite result |
| `alpha.metric.empty_slice` | A predeclared slice has no eligible rows/decisions |
| `alpha.inference.insufficient_decisions` | Too few computed temporal observations exist |
| `alpha.inference.overlap_lag_too_short` | Confirmatory HAC/block width is below interval-implied dependence |
| `alpha.inference.bootstrap_replicate_failed` | A declared replicate cannot compute the statistic |
| `alpha.inference.family_invalid` | Hypothesis-family/adjustment membership is inconsistent |

### 22.4 Validation membership and holdout reasons

| Reason code | Meaning/default disposition |
| --- | --- |
| `validation.sample.eligible` | Sample may receive its raw role |
| `validation.sample.dataset_unusable` | Plan-07 row audit excludes the sample |
| `validation.sample.feature_noncomputed` | `complete_case` rejects a feature state |
| `validation.sample.label_noncomputed` | Target label is noncomputed and cannot be supervised |
| `validation.sample.interval_missing` | Exact target interval endpoint is absent |
| `validation.sample.interval_invalid` | Target interval is reversed/incompatible |
| `validation.scope.strengthened` | Requested or derived dependencies use a stronger scope |
| `validation.scope.unknown_panel` | Unknown/opaque/incomplete dependency conservatively resolves panel-wide |
| `validation.sample.purged_label_overlap` | Related lower-role closed interval overlaps evaluation |
| `validation.sample.embargoed_after_evaluation` | Related lower-role anchor lies in declared embargo |
| `validation.fold.insufficient_train` | Retained train decisions/samples miss the declared minimum |
| `validation.fold.insufficient_validation` | Retained validation membership misses the minimum |
| `validation.fold.insufficient_test` | Retained test membership misses the minimum |
| `validation.fold.short_final_omitted` | Incomplete final test is deterministically not emitted |
| `validation.nested.outer_membership_forbidden` | Inner candidates include a non-train outer key |
| `validation.holdout.sealed` | Ordinary API cannot reveal terminal holdout data |
| `validation.holdout.selection_not_frozen` | Selection/evaluation manifest is incomplete or mutable |
| `validation.holdout.selection_mismatch` | Later use differs from the one clean frozen selection |
| `validation.holdout.used` | One clean managed use has been recorded |
| `validation.holdout.contaminated` | Managed/external inspection permanently removes confirmatory claim |
| `validation.resource.limit` | Bounded construction/access limit is exceeded |

Inherited plan-07/08 source, component-state, safety, lineage, and licensing reasons retain
their names and strength. New reason codes append. A definition may make a nonstructural
case fatal, but cannot weaken structural label separation, relationship scope, holdout
contamination, or a resource limit.

## 23. Required edge-case behavior

Implementations and reviews must preserve at least these cases:

- Pearson/Spearman with too few pairs, all-equal features, all-equal labels, tied ranks,
  missing pairs, and finite values near numeric tolerance produce the declared values or
  typed noncomputed state with exact counts.
- Quantile ties spanning nominal boundaries remain one bucket; empty/interior buckets and
  insufficient endpoints make only the affected bucket/spread noncomputed. UUID order
  never splits equal feature values.
- A direction reversal changes economic high/low spread interpretation, not raw ranks or
  bucket numbering. Dataset weights normalize only within nonempty buckets.
- Coverage with an empty denominator has null ratio/state; censored labels and unavailable
  features stay in their declared denominator counts without becoming zeros.
- Turnover over an entry/exit union, the first decision, missing buckets, persistence over
  irregular adjacent decisions, and entity autocorrelation with sparse histories reconcile
  their exact memberships.
- Decay rejects manufactured shifts and incompatible horizon kinds; exposure diagnostics
  preserve point-in-time categories, unknown buckets, OLS column order, and rank policy.
- HAC with `L=0`, `L >= T`, interval-implied overlap above `L`, tiny negative variance,
  and too few decisions follows section 12 exactly. Bootstrap rejects `B < 1`, `B > T`,
  insufficient overlap width, zero repetitions, or excessive failures under policy.
- Holm/BH tie ordering, null hypotheses, planned-versus-computed `m`, and all-null families
  reproduce the predeclared family audit without inventing adjusted values.
- Two closed label intervals touching at one endpoint overlap. Microsecond precision is
  preserved; a half-open SQL range implementation must compensate exactly.
- Multiple target intervals use their conservative hull. Missing/reversed target endpoints
  are audited and never reconstructed from decision count or elapsed horizon metadata.
- Entity scope purges the same instrument only; exact causal group roots purge intersecting
  groups; cross-section/global/opaque dependencies purge panel-wide. A caller's weaker
  request is upgraded or rejected, never honored.
- Point-in-time group changes use the exact roots actually consumed. Unknown membership or
  incomplete cross-entity lineage becomes panel scope.
- A decision's raw cross-section remains one role even when instruments are absent,
  censored, purged, or embargoed later. Empty final cross-sections stay in fold audit.
- Decision-step windows/embargo count exact scheduled decisions across holidays, early
  closes, and gaps. Elapsed windows use UTC half-open boundaries across DST and may contain
  unequal decision counts.
- An elapsed step mapping twice to the same base decision emits it once. Short-final,
  zero/negative width, insufficient history, and no-test cases follow explicit policies.
- CPCV rejects empty groups and excess `C(N,K)`; combinations are lexicographic,
  discontiguous test groups create separate segments, and multiplicities reconcile.
- Purging precedes embargo, validation is protected from test before train is protected
  from both, and multiple exclusion causes have stable canonical ordering.
- Every inner candidate is a final outer-train key. Outer test/holdout/purged/embargoed keys
  cannot leak through a shared dataset handle, dataframe order, or estimator adapter.
- A terminal holdout is resolved before analytical inspection, excluded from all
  development folds, and protected by boundary purge. Empty/whole-plan/nonterminal
  holdouts reject.
- First frozen managed use is clean; exact retry is idempotent; a different use rejects or
  records contamination. Evaluation failure after opening remains a use. External
  inspection can be recorded without fabricating an access time or clearing contamination.
- Duplicate/reordered/skipped estimator key maps, another build, timestamp precision loss,
  or an unauthorized sealed role reject before positional arrays are yielded.
- Empty datasets/results publish typed empty diagnostics only when the definition permits
  them; a validation scheme requiring folds fails rather than publishing a misleading
  zero-fold success.
- Transaction failure at any staging/hash/event boundary exposes no partial result/plan;
  exact retry verifies complete normalized and dynamic content before reuse.
- Limits encountered during range joins, bootstrap, output writing, or dataframe access
  fail without sampling, truncation, weakened scope, or partial publication.

## 24. Migration, compatibility, and extension policy

### 24.1 Clean v3 migration boundary

Research-database migrations add the `analysis` metadata/normalized tables, generated
relation ownership rules, indexes, constraints, event schemas, and repository readers in
one ordered migration series. Migration is transactional and idempotent under plan 02.
Dynamic relations are created only by completed-result/plan staging and are included in
verified project copies/recovery manifests.

Version 2 alpha dataframes, notebook correlations, sklearn split arrays, arbitrary SQL
tables, or backtest quantile reports have no identity/interval/provenance contract and are
not imported as completed v3 results/plans. A user may rebuild them from exact v3 datasets
and definitions. Migration never guesses label horizons, availability, relationship
scope, hypothesis families, or final-holdout cleanliness.

The initial package layout adds bounded public/domain/repository/service modules under
`persistra.research.alpha` and `persistra.research.validation`. Optional sklearn imports
remain behind the appropriate adapter boundary; core validation-plan creation does not
require scikit-learn.

### 24.2 Versioning and compatibility

Definition/scheme content is immutable. A changed formula, tie rule, window boundary,
interval predicate, scope derivation, purge/embargo ordering, inference estimator,
hypothesis adjustment, output schema, or solver/numeric rule requires a new definition/
scheme version and usually a new canonical schema/policy version. Existing results/plans
remain readable under the published Persistra/DuckDB compatibility matrix.

New enum/reason/metric values append; stored meanings never change. Readers encountering
an unknown required value fail with a compatibility error rather than treating it as the
nearest known method. Copy migration verifies controlled dynamic relation schemas and
content roots rather than rewriting membership in place.

### 24.3 Future statistical extensions

Probabilistic Sharpe, deflated Sharpe, probability of backtest overfitting, stitched CPCV
paths, studentized/BCa bootstrap, cross-sectional resampling, and new exposure estimators
must arrive as typed versioned algorithms/artifacts. They consume exact
`AlphaAnalysisResultId`/`ValidationPlanId`/run identities, declare preserved dependence,
store implementation/inference/hypothesis identities, and use registered output schemas.
They cannot be inserted as free-form rows or retroactively appended to an old result.

Plan 15 may wrap an alpha result as an immutable general analysis artifact for reporting,
comparison, and export. The wrapper retains this result's exact ID/content roots and does
not recompute, declassify, or rename a quantile label spread as portfolio performance.

## 25. Acceptance tests and exit criteria

### 25.1 Domain, registration, and input tests

- All five typed IDs round-trip through canonical JSON, SQL UUID storage, event payloads,
  repositories, handles, equality/hash, and wrong-kind rejection.
- Definition/scheme versions are contiguous and immutable; exact registration is
  idempotent, changed same-version content conflicts, and “latest” resolves before identity.
- Enum/window/duration/limit constructors reject unknown, zero/negative, noncanonical, and
  over-ceiling values while preserving explicit `none` policies.
- Alpha/validation input rejects bare frames, wrong dataset role, missing direct keys,
  friendly/latest component references, label-like feature fields, incompatible units,
  incomplete output/state/interval manifests, and build/snapshot/schedule mismatches.
- Analysis results and validation plans are always label-classified, inherit complete
  safety/licensing folds, reject structural lineage failures, and persist explicit unsafe
  analysis authorization without creating a simulation override.

### 25.2 Alpha formula and state tests

- Hand-worked cross-sections verify Pearson, average-tie Spearman, sample counts, zero
  dispersion, insufficient pairs, canonical reduction order, and exact state/reason output.
- Classification labels remain valid coverage/validation inputs but reject every initial
  numeric alpha metric instead of being coerced from class codes.
- Coverage fixtures reconcile universe-eligible/included/row-usable denominators, missing
  features, censored/ambiguous labels, invalid weights/exposures, empty denominators, and
  metric-computed decisions.
- Quantile fixtures verify average-rank assignment, unsplit ties, unequal/empty buckets,
  equal/causal-weighted means, direction-aware spread, monotonicity slope/correlation, and
  union one-way turnover. They assert no holdings/orders/cost/accounting artifact exists.
- Persistence/autocorrelation fixtures cover irregular decisions, changing universes,
  sparse entity histories, exact lag positions, equal-entity versus pooled policies, and
  first/noncomputed cases.
- Decay uses exact distinct label occurrences/intervals and rejects shifts/incompatible
  endpoints; categorical/numeric/joint exposure fixtures verify causal categories,
  unknowns, coefficients, rank/condition, and failure/drop policy.
- Slice fixtures cover overlapping subperiod/regime/universe/category membership, empty
  slices, post-hoc exploratory versions, and confirmatory mutation rejection.

### 25.3 Inference tests

- HAC estimates match an independent high-precision reference for fixed series/lags,
  including `L=0`, overlap-derived lower bounds, tiny-negative tolerance, null inference,
  and invalid lags.
- Seeded circular moving-block fixtures verify exact block-start counters, truncation,
  shared family plans, type-7 percentile bounds, replicate failure policy, and identical
  output across partition/worker orders.
- Holm and Benjamini-Hochberg fixtures cover ties, original-order restoration, caps,
  monotonicity, planned-versus-computed family size, null hypotheses, and separate raw/
  adjusted storage.
- Intent tests prevent exploratory/post-hoc output from claiming validation/confirmatory
  status and require every confirmatory dependence/multiple-testing policy predeclared.

### 25.4 Purge, embargo, and window tests

- A small hand-worked panel proves the closed-overlap predicate, including endpoint
  equality, nonoverlap by one microsecond, multi-target hulls, and every exclusion cause.
- Entity/group/panel fixtures prove exact root relationships, changing group memberships,
  derived strongest scope, user strengthening, weak-scope rejection, and unknown/opaque
  panel fallback.
- Hierarchical role fixtures prove holdout > test > validation > train ordering,
  validation-against-test then train-against-both purging, and raw-role cross-section unity.
- Embargo fixtures verify origin at the latest actual information end, relationship-root
  specificity, unioned segments, decision steps over exchange holidays, elapsed UTC across
  DST, boundary inclusion, and purge-before-embargo ordering.
- Expanding/rolling fixtures assert exact decision slices, elapsed boundary selection,
  mixed widths, duplicate elapsed-step skipping, short-final policy, fold ordering, and
  invalid/empty retained membership.
- CPCV with `N=6, K=2` produces exactly 15 lexicographically ordered folds, correct equal/
  explicit groups, discontiguous segments, per-decision/sample multiplicities, scoped
  purge/embargo, bounded rejection, and no IID/PBO claim.

### 25.5 Nested and final-holdout tests

- Every inner candidate root equals a final outer-train root; injected outer validation,
  test, purged, embargoed, or holdout sentinel keys fail disjointness before publication.
- Nested roots persist the exact outer resolved split kind/content and every child persists
  the exact inner kind/content; recursive nesting and swapped/implicit specs reject.
- Outer test membership remains sealed until the exact selection manifest freezes, and a
  changed inner aggregation/model/parameter/seed/code identity cannot reuse capability.
- Plan-10 training capabilities derive the exact fit/score memberships in the role table,
  bind one noncircular planned-fit content ID, exclude outer-test/holdout labels, expire
  with the operation, and cannot be converted to label handles or ordinary split positions.
- Selected/final refit tests freeze the refit recipe and selection manifest before planned-
  fit computation/capability issuance, reject any changed roles/inputs/preprocessing/
  parameters/code/seed, and verify the exact completed refit before outer-test/final-
  holdout opening.
- Terminal exact/decision/elapsed holdout boundaries resolve from schedule/base metadata
  before analytical access, remain outside every fold, and purge preceding overlapping
  target intervals.
- Ordinary handles/events/logs expose only permitted boundary/count/root metadata. First
  managed use commits one clean row/event, exact retry verifies without duplication, later
  different use rejects by default, and explicit reuse/external reporting records monotone
  contamination.
- Fault injection after holdout-use commit but before evaluation completion proves the
  holdout remains used. No API/copy/new version clears the fact.

### 25.6 Persistence, API, determinism, and resource tests

- Fresh migration, reopen, read-only inspection, verified copy, stale-stage recovery, and
  compatibility fixtures validate every normalized/controlled schema and catalog owner.
- Golden output roots cover definitions/results/plans, IC/quantile/diagnostic/exposure/
  coverage/summary rows, development candidates/reasons, folds/segments/groups,
  relationship edges, membership/reasons, sealed holdout rows, and one event per nested
  plan occurrence.
- Exact retry detects changed/deleted/extra normalized or dynamic rows, schema drift,
  wrong physical ownership, count/root mismatch, or corrupt event/use metadata.
- Fault injection at every stage/write/hash/finding/event/commit boundary leaves no visible
  partial result/plan/child tree. Concurrent identical writers yield one exact occurrence/
  event per expected root/child; readers see only before/after states.
- Frame tests verify exact schema/dtypes/order/empty behavior, no silent truncation, bounded
  preview labeling, iterator equivalence, licensing denial, and sealed-holdout denial.
- Sklearn-adapter tests prove exact key-to-position mapping under reorder and rejection of
  duplicates, omissions, extras, build mismatch, timestamp loss, excluded roles, and
  missing capabilities. Nonnested test roles are available for validation; nested outer
  test and final-holdout roles reject without their distinct matching capabilities.
- Worker count, partition size, insertion/hash order, locale, and supported platform do not
  change values, states, folds, causes, manifests, or event order under the pinned
  environment identity.
- Preflight and runtime tests cross every row/fold/edge/reason/hypothesis/bootstrap/partition/
  dataframe/memory/temp/time limit and prove explicit failure without sampling, reduced
  inference, weakened leakage protection, truncation, or partial publication.

### 25.7 Documentation and workflow exit

- API/docs snippets compile or execute under the documentation harness, strict MkDocs
  builds without internal-link/schema-name errors, and assumptions/limitations are visible.
- A documented end-to-end workflow builds one exact analysis dataset, materializes causal
  features/future labels, runs IC/coverage/quantile/exposure diagnostics, creates expanding/
  rolling/purged/embargoed/CPCV/nested plans, freezes selection, and uses a final holdout.
- Sentinel leakage tests cover managed/custom/SQL/workspace ancestry plus entity/group/
  panel interval leakage through sklearn adapter and nested-plan boundaries.
- The workflow stays within the declared bounded partitions on the research-phase fixture,
  and no step requires a full multi-year panel in pandas.

Plan 09 is complete only when all tests above pass with `make lint type test` and the docs
checks, the public workflow uses no private SQL/relation names, and the cumulative review
finds no contradiction with the umbrella specification or focused plans 01–08.

## 26. Review checklist for dependent plans

Plans 10, 14, and 15 must preserve:

- exact `ValidationPlanId` plus fold/role/capability identity on every training, selection,
  evaluation, study, trial, attempt, model, and diagnostic consumer;
- plan-10 fit purpose/role mapping, one frozen noncircular planned-fit ID per training
  capability, label/source availability by fit cutoff, and exact refit verification before
  any sealed outer-test/final-holdout opening;
- feature/label structural separation and the fact that alpha/validation outputs are
  label-classified analysis artifacts, never signal/strategy inputs;
- decision-level raw roles, exact sample keys/closed target intervals, strongest derived
  entity/group/panel scope, purge precedence, and embargo boundaries;
- inner-plan final outer-train candidate roots and a frozen selection manifest before any
  outer-test access;
- terminal holdout boundary resolution before analytical inspection, one clean managed
  use, append-only contamination, and no claim of secrecy against direct local access;
- quantile/turnover/spread diagnostics as realized-label analysis rather than portfolio,
  execution, accounting, or performance results;
- predeclared hypothesis families, dependence-aware inference, raw/adjusted p-values, and
  exact algorithm/code/environment identities;
- plan-14 ownership of studies/trials/search/attempts/reuse/workers/scenarios without
  reinterpreting this plan's fold membership;
- plan-15 immutable analysis wrappers/advanced statistics/export without mutating or
  declassifying existing alpha results; and
- bounded repository/frame adapters, physical-name hiding, atomic publication, complete
  safety/lineage/licensing, deterministic order, and resource failure semantics.

If a dependent plan needs probabilistic/deflated Sharpe, PBO, stitched CPCV paths, new
bootstrap/resampling, compatible reuse, or post-run analysis, it defines a new typed
artifact and acceptance suite rather than extending a completed result with untyped rows.

## 27. Consistency statement

This plan preserves the umbrella direction for Pearson/rank IC, IC stability, coverage,
quantile spreads, monotonicity, turnover/persistence/decay/autocorrelation, causal exposure
and regime/universe slicing, dependence-aware significance, expanding/rolling/purged/
embargoed/combinatorial/nested validation, and a final untouched holdout. It makes explicit
that “quantile portfolios” at this phase are diagnostic realized-label buckets, because
plans 10–13 own portfolio construction and simulation fidelity.

It also preserves the umbrella boundary that Persistra owns financial splitting,
provenance, and aggregation while external estimators may be consumers. General search,
trial/attempt orchestration, compatible reuse, advanced PBO/Sharpe statistics, immutable
run-analysis architecture, and export remain with plans 14–15. These are scoped
refinements, not project-level reversals; no umbrella conflict remains open.

The cumulative review aligns plan-02 `analysis` ownership, the shared plan-07 safety
subjects, and plan-08 per-output `ComponentDependencyScope`/relationship roots with these
schemas. Nonnested test access, nested resolved splits/child events, complete candidate
role audit, and final-holdout capability semantics now have one cross-plan meaning.

The cumulative plan-10 review additionally assigns registered forecast/risk model and fit
identity to plan 10 while this plan remains authority for membership and sealed-role
capabilities. Frozen selection names a refit recipe; plan 10 then computes a planned-fit ID
from that recipe and the selection root before capability issuance or occurrence
allocation. Exact completion is verified before outer-test/final-holdout access. This
removes both identity and fit/holdout circularity without exposing test/holdout labels or
creating a general estimator registry here.
