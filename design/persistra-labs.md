# Persistra Labs bootstrap

This development decision specifies the initial `persistra-labs` research program. The Labs
repository does not exist yet. This specification records its charter and the first vertical
study before repository creation or implementation begins.

## Charter

Labs turns explicit research questions into reproducible artifacts. It uses released Persistra
interfaces and immutable Kernel artifacts. It does not become a second general-purpose library.

Labs owns:

- study questions, hypotheses, and limitations;
- study-specific features, regimes, universes, and benchmarks;
- acquisition recipes and retained-input descriptions;
- experiment configuration, reports, tables, and narrative figures;
- notebooks used as views over scripted computations;
- run manifests, artifact identities, and reproduction instructions; and
- bounded Python and Agda integration demonstrations.

Labs does not own reusable provider-neutral calculations, canonical trading transitions,
broker connectivity, durable execution state, or production services. Reusable research code
moves to Persistra. Canonical exact trading transitions with meaningful invariants move to
Kernel. Operational effects move to Runtime. Formal research demonstrations remain in Labs.
The Labs copy is deleted after promotion.

A canonical study must run from a clean clone with one documented command. Its fast path uses
small deterministic fixtures without credentials or network access. Its full-data path uses
explicit acquisition recipes and retained inputs whose redistribution is permitted. Notebooks
may present results, but scripts or a small study package remain the source of truth.

## LAB-001: macro revision bias

The first study quantifies how revised macroeconomic data change a simple historical allocation
when compared with information actually available at each decision date.

Success means measuring the difference reproducibly. It does not mean finding a profitable
strategy or establishing that one timing rule is economically optimal.

### Research question

How much do future revisions to a monthly macroeconomic series change feature values, regime
classifications, trades, and portfolio results relative to first-release and real-time vintage
data?

The study tests two predetermined empirical hypotheses and one required reconciliation property:

1. Final-vintage and real-time feature values differ on at least one historical decision date.
2. Those value differences may change regime classifications or transition dates.
3. Any classification change can be traced through target weights, turnover, costs, returns,
   and drawdowns without an unexplained residual.

Either empirical hypothesis is allowed to fail. A zero value, classification, or performance
difference is a valid result. The reconciliation property must hold. The study must report every
configured comparison and must not search for an alternative feature after seeing the result.

### Fixed comparison policies

The study constructs three histories from the same vintage source:

| Policy | Value used for an observation | When it becomes visible |
|---|---|---|
| Final vintage | Last retained version, deliberately using future revision information | First recorded release date plus the configured operational lag |
| First release | Earliest retained version; later revisions are ignored | First recorded release date plus the configured operational lag |
| Real time | Version active at the decision cutoff | That version's availability date plus the configured operational lag |

All three policies use the same observation dates, market data, feature definition, portfolio
rule, costs, and execution timing. This isolates data-version policy rather than permitting each
case to become a different strategy.

The final-vintage policy is intentionally biased. It respects the original release date so that
the primary difference is future revision content rather than an additional publication-date
error.

### Initial full-data configuration

The initial full study uses:

- ALFRED monthly `PAYEMS` vintage levels;
- Alpha Vantage adjusted daily bars for `SPY`;
- a one-calendar-day operational lag after a source availability date;
- a 45-calendar-day maximum staleness limit;
- the three-month percentage change in the latest eligible payroll observations;
- a long-SPY target when the change is nonnegative and a cash target otherwise;
- one market-period delay between signal observation and target effectiveness;
- five basis points of linear cost per traded notional; and
- one initial unit of equity with zero cash return.

These choices are a deliberately small case study, not library defaults. Any change to them
creates a new configured run and must appear in the manifest. Sensitivity analysis may use only
values declared before the full-data result is examined.

### Preregistered mechanics

The canonical full-data run fixes these boundaries before acquisition:

- PAYEMS observation periods run from 1999-10-01 through 2025-12-01. The retained ALFRED
  revision window is 1999-10-01 through 2026-06-30.
- SPY acquisition uses ETF kind, daily interval, adjusted prices, and full output. Bars run from
  2000-01-03 through 2025-12-31. Reported results begin on 2000-04-03 after the warm-up interval
  and end on 2025-12-31.
- The acquisition instant and raw-response identities are recorded before calculation. Every
  policy uses the same immutable acquisition. No refresh occurs after calculation begins.
- Every retained SPY market date is a decision date. For decision date `D`, the macro knowledge
  cutoff is `D - 1` calendar day. A release on a weekend or market holiday first becomes usable
  on the first market date whose cutoff is on or after its availability date.
- Observation identity uses PAYEMS `period_start`. For each decision, the feature numerator is
  the latest eligible monthly observation. The denominator is the observation whose period start
  is exactly three calendar months earlier, selected under the same policy and cutoff.
- The feature is `numerator / denominator - 1`. It is missing unless both selected values are
  present and finite and the denominator is positive. The 45-day staleness limit applies to the
  latest numerator observation. It does not apply to the deliberately older denominator.
- A missing, deleted, stale, or unavailable numerator or denominator produces a missing feature
  without fallback. A missing feature targets cash. A nonnegative feature targets 100 percent
  SPY; a negative feature targets 100 percent cash. Shorts and leverage are forbidden.
- Market levels use `adjusted_close`. Returns are consecutive close-to-close simple returns with
  no filling. A duplicate market date, missing held return, or nonpositive level fails the run.
- A signal observed on market date `D` uses `BacktestTiming(decision_lag=0,
  execution_lag=1)`. Its target first earns the close-to-close return from `D` to the next market
  date. Transaction costs apply when that beginning target differs from the preceding ending
  portfolio.
- The fixed benchmarks are continuously all-cash and static 100 percent SPY. The same return,
  cost, and sample conventions apply to every policy and benchmark.

Before the full provider-backed acquisition, Labs must commit a machine-readable configuration
containing these values and its own identity. The run manifest records that configuration
identity. A changed boundary, policy, or parameter is a different run, never a silent amendment
to the canonical result.

The fast CI path uses synthetic vintage and market data with forced initial releases, revisions,
deletions, missing observations, regime changes, and known expected outputs. It requires no
network or provider credentials. Provider data, credentials, caches, and licensed observations
are never committed.

### Required outputs

Every run produces:

- a decision-date table containing the selected vintage, value state, age, and policy;
- feature values and regime classifications for all three policies;
- disagreement dates and transition-date differences;
- target and realized portfolio weights;
- gross and net returns, turnover, costs, equity, and drawdowns;
- direct performance and classification comparisons;
- a limitations section that separates lookahead bias from empirical efficacy;
- a machine-readable run manifest; and
- hashes for every retained table, figure, and report.

The report must make missing, deleted, stale, and unavailable observations visible. It must not
silently substitute an older nonmissing observation.

### Reproducibility requirements

The run manifest records at least:

- the Persistra version and source revision;
- the Labs source revision and dirty state;
- Python, operating system, architecture, and lockfile identity;
- dataset scope, schema, acquisition snapshot, and content identities;
- every feature, lag, staleness, signal, portfolio, cost, and timing parameter;
- random seeds;
- execution status; and
- output names, byte sizes, and SHA-256 identities.

The synthetic path must reproduce from a clean clone in CI. The full path must reproduce from a
clean environment when the identified retained inputs and required credentials are supplied.
A notebook-only result, an unrecorded manual edit, or reliance on an editable sibling checkout
does not satisfy the study contract.

### Acceptance criteria

LAB-001 is complete when:

- one command rebuilds the synthetic report without network access;
- one documented command rebuilds the full report from retained or reacquired inputs;
- every pipeline uses the same fixed downstream strategy assumptions;
- point-in-time assertions fail if a future or unavailable version enters the real-time path;
- repeated runs over identical inputs produce identical tabular outputs and manifest identities;
- every reported portfolio return reconciles with asset return, cash, and cost attribution;
- a clean environment uses only released Persistra public interfaces; and
- the report states that the single-series, single-asset result is not evidence of general
  investment efficacy.

## PIT-001: verified point-in-time selector

The first Agda companion is a formal research demonstration in Labs, not a Kernel module or a
trading engine. It verifies the point-in-time selection rule used by LAB-001 for one vintage
series, one feature policy, and one decision date. Labs owns the Agda artifact and the
Persistra-to-Agda differential tests. Kernel begins later with canonical trading transitions.

Inputs use signed integer calendar-day ordinals. A version contains an observation identity,
optional period bounds, inclusive availability bounds, a present, missing, or deleted value
state, and opaque provenance. A query contains a decision day, nonnegative whole-day publication
lag, nonnegative maximum staleness, and a period-start or period-end observation basis.

The effective knowledge cutoff is the decision day minus publication lag. A version is active
when its availability start is no later than the cutoff and its absent or inclusive availability
end is no earlier than the cutoff. An active row is eligible only when its selected observation
date exists and is no later than the decision day.

The selector chooses the greatest eligible observation date. Multiple active candidates on that
date produce an ambiguity result. A candidate is stale only when its age is greater than the
maximum; equality is accepted. A missing or deleted latest candidate remains missing or deleted.
The selector never falls back to an older present value.

The result distinguishes:

```text
Selected candidate
NoCandidate
Stale candidate and age
Ambiguous date and candidates
```

A selected candidate retains its present, missing, or deleted state. Its age is the decision day
minus its selected observation day. Publication lag changes only the availability cutoff; it
does not change observation eligibility or age. Present values are opaque payloads. PIT-001
proves row selection, not floating-point or other numeric semantics.

The safe history validator requires every availability start, rejects a closed interval that
ends before it starts, rejects overlapping intervals or duplicate version starts for one
observation identity, and requires a deleted version to carry no value. Availability gaps are
valid. Input list order has no meaning. An intermediate `activeAt` operation returns the active
version set before observation-date eligibility and latest-date selection.

The safe Agda core must establish:

- soundness and completeness of the intermediate `activeAt` set;
- at most one active version for each observation identity;
- no selection of a future observation;
- latest eligible observation selection;
- correct inclusive staleness behavior;
- no fallback from a missing or deleted latest candidate;
- determinism and input-permutation invariance;
- irrelevance of retrieval metadata;
- noninterference when two valid histories agree on every row active at the cutoff whose
  observation date is no later than the decision; and
- earlier-cutoff monotonicity for each observation identity: when both cutoffs select a version,
  the earlier cutoff cannot select one with a later availability start.

The proved Agda modules use safe mode without postulates, foreign-function bindings, `COMPILE`
pragmas, unchecked termination, or incomplete matching. A thin versioned JSON Lines host is
explicitly outside the proof boundary.

Differential tests compare a compatibility projection with current Persistra behavior:

| PIT-001 result | Persistra projection |
|---|---|
| Selected present | Current value and selected-row provenance |
| Selected missing or deleted | `pd.NA` and selected-row provenance |
| No candidate | Current unmatched result |
| Stale | Current unmatched result after discarding the richer stale candidate |
| Ambiguous | `AnalysisError` |

PIT-001 is accepted when pinned Agda and standard-library versions type-check the proofs, golden
cases cover every boundary and value state, finite exhaustive checks agree over a small day
domain, and property-based differential tests agree with Persistra across all generated valid
histories after the compatibility projection. The report records theorem names, the trust
boundary, toolchain versions, fixture identities, differential results, and benchmark
measurements.

Multi-series joins, intraday instants, time zones, business calendars, imputation, labels,
provider fetching, and trading integration remain outside PIT-001.
