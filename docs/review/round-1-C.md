# Round 1 — Reviewer C (adversarial reading)

**Scope:** ambiguity, unstated assumptions, silent edge cases, and underspecified behavior
in text that is present in the spec. Cross-file contradictions and missing
schemas/signatures are out of scope (covered by other reviewers).

**Coverage:** focused specifications 01–18 read in full. The umbrella `v3-spec.md` was
sampled rather than exhaustively read: it frames itself as design intent whose exact
behavior is delegated to the focused specifications ("each major subsystem must receive a
focused specification with exact schemas, APIs, algorithms, edge cases"), so
ambiguity-of-behavior findings against it would be resolved (or duplicated) by the focused
specs reviewed here.

**General assessment:** the specs are unusually disciplined about pinning boundary
behavior (half-open intervals, tie-breakers, singleton-rank conventions, closed-interval
overlap, deterministic ordering). Findings below are the residual places where an
implementer still has two defensible readings.

---

## C1 — Same-process duplicate *exclusive* lease acquisition is reference-counted or refused?

- **Severity:** major
- **Where:** `02-project-databases-leases-copies-migrations.md`, §11.2 "Kernel lock" (and §19 edge-case table)
- **Quote:** "An in-process registry keyed by canonical database path owns one guard
  descriptor and reference count… Reentrant acquisition of the same mode increments the
  count." Edge table: "Two shared readers in one process | In-process lock entry is
  reference counted".
- **Divergent readings:** (a) *any* same-process acquisition of the same mode increments
  the count — so two independent `Project` instances in one process can both "hold" the
  exclusive research lease simultaneously (the kernel `flock` is per-process, so nothing
  external stops this), silently defeating the single-writer invariant that the lease
  exists to enforce; (b) reference counting applies only to shared mode / reentrant use
  within one `Project`, and a second exclusive acquisition in the same process fails with
  `DatabaseLeaseConflictError`. The edge table blesses only the shared-reader case; the
  exclusive case is not addressed anywhere, and mode *conversion* (`LeaseUpgradeError`) is
  the only refusal specified.
- **Fix:** State that same-mode reference counting applies to shared leases only; a second
  exclusive acquisition of the same canonical path from any `Project` in the same process
  fails with `DatabaseLeaseConflictError` regardless of timeout.

## C2 — Scope of "last locally persisted `recorded_at`" for clock-regression detection

- **Severity:** minor
- **Where:** `01-domain-identity-time-money-events.md`, §6.7 "Clocks and deterministic time"
- **Quote:** "If the injected wall clock returns an instant earlier than the last locally
  persisted `recorded_at`, the writer preserves the observed instant, allocates the next
  authoritative sequence, and persists warning code `domain.time.clock_regression`."
- **Divergent readings:** the comparison population for "last locally persisted" is
  undefined: (a) the maximum `recorded_at` across the whole database; (b) the maximum
  within the writer's own aggregate/sequence stream; (c) the maximum within the current
  service's session. These produce different warning behavior whenever independent writers
  or tables carry timestamps from different wall-clock moments (e.g., after a restore or a
  worker-file merge, reading (a) fires spuriously; reading (b) does not).
- **Fix:** Define the regression check as: within one writer service, compare against the
  maximum `recorded_at` that this writer previously committed to the same database's
  authoritative sequence stream (per aggregate stream where a sequence exists).

## C3 — Calendar version fallback: structured unavailability *or* exception, unresolved per API

- **Severity:** minor
- **Where:** `04-reference-identifiers-calendars-universes.md`, §10.3 "Availability and revisions"
- **Quote:** "…no qualifying full-range version returns structured unavailability or
  raises `CalendarCoverageError` according to the API contract."
- **Divergent readings:** the sentence defers to "the API contract," but §10.4 (the API
  section) never assigns return-vs-raise per method. Implementer A makes
  `calendar.schedule(range)` raise `CalendarCoverageError`; implementer B returns a
  structured unavailability result; both cite this sentence. Callers (universe evaluation,
  bar validation, settlement) then diverge in control flow on missing coverage.
- **Fix:** Pin it per method: `session()`/`schedule()`/`next_session()` raise
  `CalendarCoverageError`; batch/range resolution used by universe evaluation returns
  structured unavailability — and delete "according to the API contract."

## C4 — Cash-distribution reference price: "immediately preceding *eligible* session" — strict previous session, or walk back?

- **Severity:** major
- **Where:** `05-market-bars-trades-quotes-actions-adjustments.md`, §14.4 "Cash-distribution factor" (and §20 edge table)
- **Quote:** "resolve raw regular-session close `P` from the immediately preceding
  eligible session under the same snapshot, bar-source policy, dual cutoffs, and terms
  basis… Missing/no-trade/partial/unsafe reference price… makes the affected history
  `unavailable`; the policy never clips or substitutes a *later* close."
- **Divergent readings:** (a) "immediately preceding" = exactly the one session before the
  ex boundary; if its bar is no-trade/missing, the factor is unavailable (the
  missing-price clause only makes sense under this reading); (b) "eligible session" = the
  most recent *earlier* session whose complete close is eligible — i.e., walk backward
  past no-trade/missing sessions (only *later* closes are explicitly forbidden). The two
  readings produce different dividend factors and different unavailability sets for any
  instrument with sparse trading around an ex date. §14.1 delegates "prior-close
  reference-price query and missing-price behavior" to the policy, but the built-in
  `persistra.adjustment.total_return_pit@1` behavior is never pinned to one reading.
- **Fix:** Define the built-in policy as: `P` is the close of the single session
  immediately preceding the ex boundary; any noncomplete/ineligible close there makes the
  factor unavailable with no backward or forward substitution.

## C5 — Partial-bar revision chains: must `observed_through_at` be monotone?

- **Severity:** minor
- **Where:** `05-market-bars-trades-quotes-actions-adjustments.md`, §7.3 "Interval and session rules"
- **Quote:** "Valid state progression is partial to later partial/complete/no-trade, or
  final complete/no-trade to an explicitly evidenced final correction; a final row cannot
  regress to partial."
- **Edge case:** two successive `partial` revisions where the later revision has an
  *earlier* `observed_through_at` (provider republishes a shorter horizon). The
  "nonregressing revision state" rule in §8 constrains only the state enum, not the
  activity horizon. Implementer A accepts it as a valid linear revision (later ordinal
  wins with a shorter horizon); implementer B quarantines it as regression. Neither
  behavior is derivable from the text.
- **Fix:** Require each successive partial revision's `observed_through_at` to be strictly
  greater than its predecessor's; otherwise quarantine as
  `bar.availability.before_observed` (or a new dedicated code).

## C6 — Intrabar limit/stop fills: the fill *reference price* is never specified for the non-gap case

- **Severity:** major
- **Where:** `13-event-clock-orders-bar-execution-costs-fidelity.md`, §9.2 "OHLC reachability" and §11 "Price and realized costs"
- **Quote:** §9.2: "buy limit is touched when `low <= limit`… a market order uses the
  policy's exact open/close/reference point; a favorable opening gap executes a limit at
  the open under the configured price-improvement rule, never worse than its limit before
  modeled costs; a stop gapping through its level uses the open/reference…" §11:
  "`fill_price = observed_reference + …`".
- **Divergent readings:** for a bar whose open is on the non-executable side and the limit
  is touched *intrabar* (`low <= limit <= high`, no ambiguity with other levels), the
  `observed_reference` for the fill is unspecified. Reading (a): fill at the limit price
  (the standard convention); reading (b): fill at the policy's generic reference point
  (e.g., close), which can be *better or worse* than the limit; reading (c): the
  ambiguity policy governs price too (but the touch itself is not ambiguous, so
  `conservative` arguably doesn't apply). The same gap exists for a stop triggered
  intrabar that then "behaves as a market order from the trigger point" — at the stop
  price, or at some later reference? Only the *gap* cases pin a price. P&L for every limit
  and stop strategy diverges materially between readings.
- **Fix:** State that a non-gap intrabar touch uses the limit price (respectively the stop
  price for the market phase of a triggered stop) as `observed_reference`, before modeled
  cost components; gaps keep the already-specified open/reference rule.

## C7 — Triple-barrier "touching": closed or open comparison at exact barrier equality

- **Severity:** minor
- **Where:** `08-features-labels-bounded-execution-temporal-conformance-provenance.md`, §17.5 "Triple-barrier outcome"
- **Quote:** "the first bar touching only upper yields class `1`; the first bar touching
  only lower yields class `-1`… if both are touched first in the same bar, intrabar order
  is unknowable…"
- **Edge case:** a bar whose `high` equals the upper barrier price exactly (or `low`
  equals lower exactly). "Touching" is never defined as `>=`/`<=` versus strict
  inequality, so implementer A classifies `high == upper` as a touch while implementer B
  requires penetration. The acceptance tests mention "exact boundary equality" cases but
  the spec never states the answer they should assert. Plan 13 §9.2 uses closed
  comparisons (`low <= limit`) for the analogous order question, but that convention is
  not imported here.
- **Fix:** Define touch with closed comparisons — upper is touched when
  `high >= P_start * (1 + upper)` and lower when `low <= P_start * (1 - lower)` —
  matching plan-13 §9.2's convention.

## C8 — Simplified US margin policy: no defined source for "margin-eligible" vs "nonmarginable"

- **Severity:** major
- **Where:** `11-journal-accounting-valuation-settlement-margin-borrow-corporate-actions.md`, §12.2 "Simplified US-equity research default" (with §12.1)
- **Quote:** "margin-eligible long and short positions require 50% initial equity… 
  nonmarginable long and short positions require 100%." §12.1: "Unknown marks, instrument
  marginability, or rules return unavailable rather than assuming zero requirement."
- **Unstated assumption:** the built-in `simplified_us_reg_t_v1` requirement formula
  branches on marginability, but no dataset, instrument-terms field (plan 04 terms carry
  currency/quanta/lot/settlement only), or policy input is defined to supply it.
  Implementer A treats every supported US-listed equity/ETF as margin-eligible (making
  the nonmarginable branch dead code); implementer B requires an explicit
  marginability view and returns `rule_unavailable` for every evaluation, making the
  default policy unusable out of the box. These produce entirely different margin
  requirements and breach behavior for the same book.
- **Fix:** Declare that the simplified policy classifies every supported listed
  equity/ETF as margin-eligible by default, with an optional registered point-in-time
  nonmarginable override view, and record that default as a fidelity assumption.

## C9 — `day` time-in-force: which session bounds an order activated outside any session

- **Severity:** minor
- **Where:** `13-event-clock-orders-bar-execution-costs-fidelity.md`, §8 "Activation, expiration, and order-type semantics"
- **Quote:** "`day` expires after the owning venue's eligible session execution cycle."
- **Edge case:** a callback after the close (e.g., a decision at session close plus
  latency) submits a `day` order that activates between sessions. Reading (a): the order's
  "session" is the next eligible session, so it lives through tomorrow's execution cycle;
  reading (b): its session is the (already ended) session containing submission, so it
  expires immediately without any eligibility cycle. Similar ambiguity for an order
  activated mid-halt whose "cycle" never occurs that day ("a halt or missing required
  observation yields no cycle until policy says the venue opportunity has passed" governs
  the cycle, not the expiry session choice).
- **Fix:** Define `day` expiry as the end of the first eligible session at or after the
  order's activation instant.

## C10 — Filing mode `original` when the true original is withdrawn

- **Severity:** minor
- **Where:** `06-fundamentals-estimates-macro-benchmarks-rates.md`, §7.2 "Filing/fact query modes"
- **Quote:** "`original`: earliest eligible nonwithdrawn filing in a `ReportId`."
- **Divergent readings:** if the `is_amendment=false` filing is withdrawn as of the
  cutoff, reading (a) — follow the definition literally — returns the earliest
  nonwithdrawn *amendment* and labels it "original"; reading (b) — follow the mode's name
  — restricts `original` to the non-amendment filing and returns a structured
  withdrawn/unavailable state. The two return different statements (an amendment can
  restate figures) under a mode whose whole point is "the statement as first filed."
- **Fix:** Define `original` as the earliest accepted filing with `is_amendment=false`;
  if that filing is withdrawn at the cutoff, return a structured
  withdrawn/unavailable result rather than promoting an amendment.

## C11 — Annualized return: `year_duration` constant is never defined

- **Severity:** minor
- **Where:** `15-results-analysis-metrics-attribution-comparison-export.md`, §10.2 "Return and performance rules" (with §3.9)
- **Quote:** "Annualized return uses `(1 + total_return) ** (year_duration /
  elapsed_duration) - 1`… Actual elapsed UTC time is the default performance
  annualization basis."
- **Divergent readings:** `elapsed_duration` is pinned (actual elapsed UTC time), but
  `year_duration` is not: 365 days, 365.25 days, or 365.2425 days are all defensible
  "actual elapsed time" year lengths, and each yields a different annualized return and
  therefore different metric content roots. §10.3 says each metric definition "owns exact
  formula," but the only formula the spec gives leaves its central constant open.
- **Fix:** Pin `year_duration` to exactly 365.25 days of elapsed UTC time in the standard
  metric definitions (or whichever constant is chosen — name one).

## C12 — Benchmark price recurrence: is the prior close `p` the stored quantized value or the unrounded value?

- **Severity:** minor
- **Where:** `18-testing-conformance-properties-benchmark.md`, §14.3 "Raw daily bars and actions"
- **Quote:** "Thereafter, with prior raw close `p`… raw `close = base*exp(r)`. … Each is
  rounded half-even to USD 0.000001… OHLC validation uses these stored values."
- **Divergent readings:** the recurrence consumes "prior raw close `p`" — reading (a):
  `p` is the *stored* (half-even-rounded) close of the prior session; reading (b): `p` is
  the unrounded precision-80 close, with rounding applied only to stored output. The two
  chains drift apart over 20 years, producing different fixture content roots. Because the
  spec requires an *independent validator* to reproduce generation "not inferred only from
  the generator implementation," the text itself must disambiguate — the generator and
  validator could each pick a different reading and both claim conformance to this
  section.
- **Fix:** State that `p` is the stored half-even-quantized close of the prior session
  (rounding participates in the recurrence), and similarly that the split-basis divisor
  applies to that stored value.

## C13 — Dataframe row ceiling: behavior exactly *at* the limit

- **Severity:** nit
- **Where:** `05-market-bars-trades-quotes-actions-adjustments.md`, §6 "Point-in-time query context"
- **Quote:** "The default dataframe ceiling is 5,000,000 rows… Crossing the ceiling raises
  before unbounded materialization…" (acceptance tests: "Run queries just below/at/above
  row ceilings").
- **Edge case:** a result of exactly 5,000,000 rows: "crossing" reads as strictly greater
  (succeeds at the limit), but "ceiling" is also commonly enforced as `>=` in
  preflight-estimate implementations. The acceptance test enumerates the at-limit case
  without stating the expected outcome. Same wording pattern recurs in plans 06/07
  (`max_rows` there is stated as "exceeding … raises", which is unambiguous — align 05's
  wording with it).
- **Fix:** State that a result with row count equal to the ceiling succeeds and only a
  count strictly greater raises `MarketDataLimitError`.

---

## Deliberately not reported

Searched-and-resolved candidates (recorded so they are not re-raised): union/intersection
`unavailable` semantics (04 §13.1 — fully specified); label-interval endpoint overlap
(09 §15.1 — explicitly closed with endpoint equality overlapping); singleton rank
convention (08/09/10 — pinned to 0.5 everywhere); analysis-role `conflict` default
(07 §11 — falls to the input's declared missing action; decision role overridden to
fail); HAC zero-variance p-value (09 §12.1 — explicitly defined); accrual boundary
membership (11 §10.2 — explicitly `(prior, boundary]`); expanding/rolling window index
arithmetic (09 §16.1 — exact slice formulas); equal fit anchors (10 §8.4/§22.2 —
UUID tie-break only after proving identical execution meaning, else reject); settlement
schedule interval boundaries (11 §9.1 — contiguous date intervals); `snapshots.latest()`
tie-breaker (03 §16.3 — dead code given the `(database_id, catalog_sequence)` uniqueness,
but harmless). Cross-file interval-convention and enum-range tensions (e.g., plan-11
`(a, b]` accruals vs plan-01 `[a, b)` default; plan-12 `stable_source_sequence >= 0` vs
plan-13 `stable_sequence >= 1`) were left to the cross-file reviewer.
