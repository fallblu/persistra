# Round 2 — Reviewer C (adversarial reading)

**Scope:** ambiguity, unstated assumptions, silent edge cases, and underspecified behavior
in `docs/v3/`, with particular attention to the round-1 resolutions and the behavior they
newly specify. Cross-file naming/schema consistency and wholly missing interfaces remain
the other reviewers' scope.

**General assessment:** round 1 closed the previously reported behavioral gaps cleanly.
The residual findings below are narrower, but several still affect deterministic content
roots or finance outputs because two conforming implementations could choose different
boundary conventions.

---

## C14 — Seed-stream counter origin is not specified

- **Severity:** major
- **Where:** `01-domain-identity-time-money-events.md`, §9 "Deterministic ordering"
- **Quote:** "draw `k` of the stream named by ordered labels ... is the first eight bytes ...
  of `SHA-256(canonical_bytes(root, l1, …, ln, k))`."
- **Divergent readings:** the contract defines the digest for a supplied `k`, but never
  defines whether the first draw uses `k = 0` or `k = 1` (nor explicitly constrains `k` to
  nonnegative integers). Both conventions are common. Every stochastic consumer can
  therefore be deterministic and use the named generator while producing a completely
  different stream, defeating the shared generator contract and exact replay.
- **Fix:** State that `k` is an unsigned integer in `[0, 2**64)` and the first draw of every
  named stream is `k = 0`, incrementing by one without gaps for successive draws.

## C15 — A same-instant external-flow group that nets to zero may split returns or disappear

- **Severity:** minor
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §7.3 "Core
  series schema" (`persistra.flow_timing.pre_flow_valuation@1`)
- **Quote:** "each external flow closes the current return subperiod ... Multiple flows at
  one instant aggregate into one signed amount."
- **Edge case:** a USD 100 deposit and USD 100 withdrawal have the same effective instant.
  Reading (a) treats the group as an external-flow boundary whose signed amount is zero and
  emits two return subperiods; reading (b) nets the group to zero before boundary planning
  and emits no split. Both preserve the economic NAV and the individual Plan-11 cash-flow
  rows, but produce different `result_data.returns` rows, source roots, and observation
  counts for downstream metrics.
- **Fix:** State explicitly whether a nonempty same-instant flow group remains a return
  boundary when its net signed amount is zero (recommended: retain the boundary and its
  gross-flow evidence).

## C16 — Historical VaR's "linear interpolation" does not identify a quantile estimator

- **Severity:** major
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §10.4 "Initial
  catalog: `persistra.standard@1`"
- **Quote:** "empirical `(1 - c)` quantile of `r_i`, linear interpolation."
- **Divergent readings:** "linear interpolation" specifies how to interpolate between two
  selected order statistics, but not the plotting-position/index formula that selects
  them. Hyndman–Fan type 7, type 6, and other linearly interpolated empirical quantiles
  differ at finite `N`; plan 08 §17.1 pins type 7 for the analogous feature, but plan 15
  does not import that rule. VaR, expected shortfall membership, and golden roots can all
  diverge.
- **Fix:** Name the estimator explicitly, e.g. "Hyndman–Fan type 7 linear interpolation,"
  for VaR and every percentile in the catalog (including participation p95).

## C17 — Historical VaR's required sign is ambiguous when the entire left tail is positive

- **Severity:** minor
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §10.4 "Initial
  catalog: `persistra.standard@1`"
- **Quote:** "left tail, reported as a (negative) rate."
- **Divergent readings:** for a sample in which every return is positive, the empirical
  fifth percentile is positive. Reading (a) returns that signed positive quantile because
  VaR is expressed on the return axis; reading (b) negates it or forces a nonpositive value
  because the contract says the result is "negative." The same ambiguity propagates to the
  expected-shortfall threshold.
- **Fix:** State that the result is the raw signed return quantile and may be positive (or
  instead define a nonnegative loss convention and give its exact transformation).

## C18 — Drawdown recovery at exact equality is not pinned

- **Severity:** minor
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §10.2 "Return
  and performance rules" and §10.4 "Initial catalog: `persistra.standard@1`"
- **Quote:** "depth, peak/trough/recovery instants, duration basis, and unrecovered state
  are stored"; `drawdown_duration` is "elapsed days peak→recovery."
- **Edge case:** after a drawdown, the index returns exactly to the prior peak and later
  exceeds it. One implementation marks equality as recovery (`index >= peak`); another
  requires a new high (`index > peak`). The duration and unrecovered state differ, and the
  existing "earliest peak wins ties" rule does not resolve the recovery comparison.
- **Fix:** Define recovery as the first later observation with `index >= peak` (or choose
  strict `>` explicitly), including behavior when the final observation equals the peak.

## C19 — Scalar metric unavailability still has two unspecified control-flow contracts

- **Severity:** minor
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §10.1 "Metric
  registry and output"
- **Quote:** "Convenience scalar access raises/returns structured unavailable by explicit
  caller policy."
- **Divergent readings:** no named policy values, default, or scalar method signature pins
  which calls raise and which return a structured unavailable value. Implementers can expose
  identical stored metric rows but incompatible public control flow for the common scalar
  access path, exactly at insufficient-sample/invalid-denominator cases.
- **Fix:** Define a closed `UnavailableScalarPolicy` (for example `return_state` and
  `raise`) and state the default for every convenience scalar method.

## C20 — Min/max envelope bucket construction is underspecified

- **Severity:** major
- **Where:** `16-plotly-visualization-html-reports.md`, §5.2 "Theme and render values" and
  §8 "Visual reduction and large outputs"
- **Quote:** "`min_max_envelope(buckets: int)` (per-bucket min/max/first/last over the
  canonical order)"; §8 calls it "per fixed time bucket."
- **Divergent readings:** `buckets` can mean a requested count of equal-row buckets, a count
  of equal elapsed-time buckets, or a time-width unit despite its integer type. The spec
  also does not define alignment/origin, empty buckets, partial final buckets, or output
  ordering/deduplication when one source point is simultaneously first/min/max/last. Each
  choice preserves the advertised values but emits different figure JSON and reduction
  evidence.
- **Fix:** Define one exact bucket algorithm: UTC-aligned equal-width intervals (or exact
  equal-count slices), endpoint membership, empty/final-bucket behavior, and stable
  first/min/max/last deduplication order.

## C21 — `top_n` does not define ranking direction, null handling, or `other` aggregation

- **Severity:** major
- **Where:** `16-plotly-visualization-html-reports.md`, §5.2 "Theme and render values"
- **Quote:** "`top_n(n: int, rank_by: str)` (deterministic top-`n` series by the named
  ranking column ... remainder aggregated into one labeled `other` series)."
- **Divergent readings:** "top" does not say ascending versus descending or whether
  absolute magnitude is used; null/unavailable rank values have no placement; and
  "aggregated" does not say sum, mean, weighted mean, pointwise aggregation, or unavailable
  propagation. For signed attribution/exposure series, these choices select different
  traces and can even reverse the meaning of `other` while all satisfying the prose.
- **Fix:** Make ranking a registered typed rule with direction/absolute/null semantics and
  require each eligible figure model to declare the exact pointwise `other` aggregation
  and unavailable-state rule.

## C22 — It is unclear which figure limits a reduction policy is allowed to rescue

- **Severity:** major
- **Where:** `16-plotly-visualization-html-reports.md`, §5.2 "Theme and render values",
  §6.1 "Input resolution," and §8 "Visual reduction and large outputs"
- **Quote:** `none()` will "fail when a limit would be exceeded," while §8 says reduction
  operates on "already computed values" and discusses the figure point limit.
- **Divergent readings:** reading (a) treats `max_input_rows` as a hard pre-reduction safety
  ceiling and allows reduction only for rendered points/traces; reading (b) lets an explicit
  reduction consume more than `max_input_rows` (perhaps streaming) because the policy is the
  alternative to failing "a limit." Similar uncertainty applies to JSON bytes and trace
  count. The readings have different safety and availability behavior for the same request.
- **Fix:** Partition limits into unconditional input/resource ceilings and reducible render
  ceilings, and list which reduction variants may satisfy each reducible ceiling.

## C23 — Dashboard limit overflow does not say whether to reject, paginate, or truncate

- **Severity:** major
- **Where:** `17-streamlit-dashboard-prototype.md`, §5.1 "Launch request" and §12
  "Resources and failure behavior"
- **Quote:** "A query or figure exceeding a limit shows a structured truncation notice with
  original counts"; the edge table instead requires a "Structured panel with narrower-filter/
  pagination guidance."
- **Divergent readings:** an over-limit query may (a) fail without rows and show guidance,
  (b) return the first `max_rows_per_query` rows in canonical order, or (c) automatically
  paginate and show a complete logical result page by page. The word "truncation" suggests
  (b), the edge table suggests (a) or (c), and no rule specifies which rows/points survive if
  truncation occurs. This can make the same dashboard view display materially different
  subsets.
- **Fix:** Pin behavior per limit: hard query overflow returns no partial frame and offers
  explicit pagination/filtering; display-only caps may show the first canonical page with
  exact returned/total counts and a visible notice.

---

## Deliberately not reported

Round-1 findings C1–C13 were rechecked and remain resolved. I did not re-report schema/
interface completeness questions introduced by the round-1 additions (for example custom-unit
registry storage or restore/fork destination parameters), because those belong to the
completeness reviewer. I also did not treat repeated prose/headings in plans 14, 16, and 17 as
behavioral findings; they are editorial nits unless they change the normative reading.
