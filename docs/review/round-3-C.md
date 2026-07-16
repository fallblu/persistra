# Round 3 — Reviewer C (adversarial reading)

**Scope:** ambiguity, unstated assumptions, edge cases, and underspecified behavior in
`docs/v3/`. This pass concentrated on behavior added or exposed by the round-2 fixes and
rechecked the owning prose before reporting each issue.

**General assessment:** no blocker was found. The new typed surfaces close many earlier
gaps, but several fields still admit materially different deterministic implementations.
The most consequential gaps affect temporal source selection, stochastic study planning,
adaptive-objective ranking, study stopping, and scalar metric lookup.

---

## C24 — A retraction does not say whether a lower-priority provider may take over

- **Severity:** major
- **Where:** `03-catalog-ingestion-quarantine-snapshots.md`, §12.4 "Revision selection
  primitive"; `07-research-datasets-temporal-joins-sql-workspaces-safety.md`, §9
  "Snapshot, revision, and source selection"
- **Ambiguity:** Plan 03 says a selected retracted head contributes no domain value, while
  source precedence chooses the lowest provider priority. Plan 07 orders retraction handling
  before provider precedence. If the highest-priority provider retracts a key while a lower-
  priority provider still has an eligible upsert, one implementation can return `retracted`
  and let the retraction mask every fallback provider; another can remove that provider's
  candidate and select the lower-priority value. Both follow the stated order, but they
  produce different research inputs and safety/audit roots.
- **One-line fix:** State explicitly whether a selected provider retraction is a precedence-
  participating tombstone that masks lower providers or an inapplicable candidate that permits
  fallback (and require that rule in every source-precedence policy).

## C25 — `interval_contains.max_age` has no defined age origin

- **Severity:** major
- **Where:** `07-research-datasets-temporal-joins-sql-workspaces-safety.md`, §6.2 "Ordered
  input contract" and §10.2 "Join kinds"
- **Ambiguity:** `TemporalJoinSpec` requires `interval_contains` to choose a positive
  `max_age` or explicit unbounded mode, but the join algorithm only defines containment
  (`valid_from <= anchor < valid_to`) and never applies the age bound. Age could be measured
  from `valid_from`, the adapter's `value_time`, the row's `available_at`, or another domain
  anchor. Long-lived reference, classification, and membership intervals therefore can be
  accepted or rejected differently by conforming implementations.
- **One-line fix:** Define bounded interval age as one exact expression (for example
  `anchor - valid_from <= max_age`) or remove `max_age` from `interval_contains` and give it
  a separately named staleness policy.

## C26 — `FallbackSpec.max_attempts` is behaviorally undefined

- **Severity:** major
- **Where:** `10-signals-forecasts-risk-models-constraints-optimization.md`, §18.2 "Typed
  registration and requests" and §14.4 "Failure and fallback"
- **Ambiguity:** the public fallback value adds `max_attempts`, but §14.4 says a registered
  fallback invokes "one exact constructor" and forbids recursive fallback. Nothing says
  whether the count includes the primary attempt, repeats the same fallback after transient
  statuses, limits solver attempts inside the fallback constructor, or must always equal one.
  Attempt rows, logical availability, terminal status, and potentially the effective target
  can diverge.
- **One-line fix:** Define `max_attempts` as an exact count over named attempt kinds with retry
  triggers/delays, or remove it and require one primary plus at most one constructor fallback.

## C27 — Random-search distributions do not define an exact sampling algorithm

- **Severity:** major
- **Where:** `14-experiment-identity-reuse-parallel-search-resume-scenarios.md`, §5 "Study
  hierarchy and public requests" and §§6.1–6.2 "Parameter domains and search"
- **Ambiguity:** Plan 14 names `uniform`, `log_uniform`, and `normal` distributions and says
  random search uses a suggestion-ordinal seed stream, but it does not define the mapping
  from Plan-01 64-bit draws to values, endpoint rules, integer/choice rejection versus modulo,
  normal parameters or transform, decimal quantization, or how many draws a duplicate consumes.
  It also does not state which domain kinds are legal for grid versus random search. Identical
  seeds and definitions can therefore yield different trials and downstream artifacts.
- **One-line fix:** Register and version an exact sampler contract per domain kind, including
  field grammar, legal search-kind matrix, draw labels/counters, transforms, endpoint and
  quantization rules, and duplicate/exhaustion draw consumption.

## C28 — Objective aggregation is not mathematically pinned

- **Severity:** major
- **Where:** `14-experiment-identity-reuse-parallel-search-resume-scenarios.md`, §5 "Study
  hierarchy and public requests" (`ObjectiveSpec`) and §6.4 "Objective and validation safety"
- **Ambiguity:** `aggregation` offers `single`, `mean`, `median`, and `worst`, but the spec
  does not identify the exact fold/scenario/slice observation set, weights, even-count median,
  `single` cardinality failure, or whether `worst` means the minimum for a maximization and
  maximum for a minimization. These choices alter Bayesian observations, stopping, and best-
  trial ordering.
- **One-line fix:** Define the exact ordered observation set and unavailable handling for each
  aggregation, pin equal-weight mean/type of median, require one observation for `single`, and
  define direction-aware `worst`.

## C29 — Frozen stop policy cannot select what happens to in-flight work

- **Severity:** major
- **Where:** `14-experiment-identity-reuse-parallel-search-resume-scenarios.md`, §5 "Study
  hierarchy and public requests" (`StudyStopPolicy`) and §11 "Failure and stopping policy"
- **Ambiguity:** §11 says running work is either allowed to finish or cooperatively cancelled
  "per frozen policy," but `StudyStopPolicy` has no such field. The same request can therefore
  finish and publish already-running plans in one implementation while cancelling them in
  another, producing different terminal counts and artifacts even though dispatch ordering is
  deterministic.
- **One-line fix:** Add a required closed in-flight action such as `finish_running` /
  `cancel_running` and specify the exact transition boundary and whether completed work racing
  with a committed stop intent is retained.

## C30 — Scalar metric lookup is not unique for multi-row metric definitions

- **Severity:** major
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §10.1 "Metric
  result" and §10.4 "Initial catalog: `persistra.standard@1`"
- **Ambiguity:** `scalar(metric_name, ...)` promises to copy one metric row but accepts no
  slice/component/unit selector. The initial `cost_total` definition explicitly emits two rows
  per `component_kind` (USD and NAV-rate), and the schema permits repeated metric names under
  different `slice_content_id` values. An implementation must either choose arbitrarily,
  aggregate, raise, or expose a hidden default.
- **One-line fix:** Require an exact slice/component/output selector in scalar access and raise
  a stable nonunique-result error whenever the selector does not resolve exactly one row.

## C31 — Stride reductions do not define which ordinals survive

- **Severity:** minor
- **Where:** `16-plotly-visualization-html-reports.md`, §5.2 "Theme and render values" and
  §8 "Visual reduction and large outputs"
- **Ambiguity:** `every_nth(stride)` and `event_preserving(stride)` are called deterministic
  and retain first/last, but the phase is not specified: keeping zero-based ordinals
  `0, stride, ...` differs from keeping every ordinal divisible by `stride` under a one-based
  convention or counting after the forced first point. Event union/deduplication ordering is
  also unstated. Canonical figure JSON and rendered counts can differ.
- **One-line fix:** Define the base set as zero-based source ordinals `0, stride, 2*stride, ...`,
  union first/last and declared events, deduplicate by source identity, and emit canonical
  source order.

## C32 — Custom-policy CPU limit has no aggregation or replay contract

- **Severity:** minor
- **Where:** `13-event-clock-orders-bar-execution-costs-fidelity.md`, §4.4 "Limits"
- **Ambiguity:** `max_custom_policy_cpu: Duration` could cap each call, each policy instance,
  each callback, or the cumulative event run. The text also does not say which CPU clock is
  authoritative or whether hitting this machine-dependent limit makes replay ineligible.
  A callback-heavy run can fail at different boundaries under the same execution content.
- **One-line fix:** Pin the CPU clock and cumulative scope (recommended: total charged CPU over
  all custom-policy calls per occurrence), safe-boundary comparison rule, and replay-eligibility
  consequence.

---

## Findings summary

| ID | Severity | File(s) | Summary |
| --- | --- | --- | --- |
| C24 | major | 03, 07 | Retraction masking versus lower-provider fallback is unspecified |
| C25 | major | 07 | `interval_contains` requires `max_age` without defining its origin |
| C26 | major | 10 | `FallbackSpec.max_attempts` has no attempt-count semantics |
| C27 | major | 14 | Seeded random-search distribution transforms are not exact |
| C28 | major | 14 | Objective aggregation set, weighting, median, and `worst` are undefined |
| C29 | major | 14 | Stop policy cannot choose finish-versus-cancel for running work |
| C30 | major | 15 | `scalar(metric_name)` is nonunique for multi-row metrics |
| C31 | minor | 16 | Stride reduction phase and event union ordering are unspecified |
| C32 | minor | 13 | Custom-policy CPU limit scope/clock/replay effect is unspecified |

No blockers were found.
