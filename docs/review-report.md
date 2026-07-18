# V3 pre-release review report

- Branch: `v3/release-hardening` at `7d64eed` (working tree clean).
- Review date: 2026-07-18.
- Scope: the full documentation set (`docs/*.md`, `docs/v3/*`, `mkdocs.yml`, `README.md`,
  `CHANGELOG.md`), the public API surface, the v3 packages under `src/persistra`, CI and
  release tooling (`.github/workflows/ci.yml`, `scripts/`, `benchmarks/`), and repository
  hygiene. Deep code review focused on the release-hardening commits (metrics, exports,
  event publication, experiments, dashboard sources, logging) plus the project lifecycle
  and domain layers; the remaining services were reviewed by outline, targeted reads, and
  pattern sweeps.

## Verification evidence

| Gate | Result |
|---|---|
| `make lint` (ruff) | Pass, no findings |
| `make type` (pyright strict) | Pass, 0 errors / 0 warnings |
| `make test` (pytest, full suite) | Pass — 174 tests, 196.9 s |
| Coverage | 82.42 % branch-aware (gate ≥ 80 % passes; the documented 90 % release goal is not met) |
| `make docs-check` | **Fail** — `docs/implementation-status.md: missing link target v3-release-review.md` |
| `make docs-build` (strict mkdocs) | **Fail** — 2 warnings: nav entry and page link both reference the deleted `v3-release-review.md` |
| `uv lock --check` | Pass |

## Overall assessment

The v3 rewrite is in strong shape for pre-release code. The layering is disciplined
(`Project` lifecycle → `project.services` → typed namespace contracts), the error taxonomy
is uniform (110 typed exceptions with stable `reason_code`s), atomic-write/fsync patterns
in `src/persistra/project.py` and the export writers are careful, export/backup
verification is genuinely defense-in-depth, and the documentation is unusually honest
about what is and is not supported. Lint, strict typing, and the full test suite are
clean.

The blocking problem is simple: the last commit (`7d64eed`, "docs: remove previous
report") broke the docs gate, so the repository currently fails its own verification gate
and pre-commit hook. Beyond that, the most important findings are divergences between the
normative metric catalog in focused spec 15 and the implementation, an unreconciled gap
between the spec's §37 acceptance criteria and the recorded release gate, and a handful of
robustness and typing issues in recently added hardening code. Details, citations, and fix
requirements follow, ordered by severity.

---

## Blocking findings

### B-1. Docs gate is broken: dangling references to the deleted `v3-release-review.md`

Commit `7d64eed` deleted `docs/v3-release-review.md` but left two references behind:

- `mkdocs.yml:13` — nav entry `V3 implementation audit: v3-release-review.md`;
- `docs/implementation-status.md:29` — the sentence "The v3 release review is the
  original implementation audit", whose link target is the removed `v3-release-review.md`.

`make docs-check` exits non-zero and `make docs-build` aborts in strict mode on both
references. Because pre-commit runs docs-check, any commit that touches docs will fail,
and CI's `verify` job fails on every push.

**Fix required:** remove the `mkdocs.yml:13` nav entry and rewrite or delete the sentence
at `docs/implementation-status.md:29` (or re-point both at a current report). Re-run
`make docs-check docs-build` to confirm both gates pass.

---

## High-severity findings

### H-1. Standard metric catalog diverges from the normative spec 15 definitions

`docs/v3/15-results-analysis-metrics-attribution-comparison-export.md` §10.4 states the
built-in set "contains exactly the definitions below", and
`docs/implementation-status.md` lists standard metrics as supported without a recorded
boundary. The implementation in `src/persistra/analysis/services.py` diverges in several
places:

1. **`cost_total` shape.** Spec: "per `component_kind`: total USD and total over mean NAV
   (two rows)". Implementation (`analysis/services.py:265-267,563-568`): one aggregate row
   in `usd` only — no per-component breakdown and no NAV-relative rate row.
2. **`max_drawdown` basis.** Spec: "`min_t(index_t / peak_t - 1)` on the TWR index".
   Implementation (`analysis/services.py:211-218,356-389`): computed on raw `nav_usd`.
   With external cash flows (the event engine publishes a `cash_flows` table, and commit
   `0a4497b` made MWR cash-flow-aware for exactly this reason), a deposit masks a
   drawdown and a withdrawal fabricates one. `drawdown_duration` inherits the same basis.
3. **`turnover` sign robustness.** Spec formula uses `sum(abs(fill notional))`.
   Implementation (`analysis/services.py:249-257`) sums `quantity * fill_price_usd`
   without `abs()`. This is currently correct only because both engines emit unsigned
   quantities with a separate `side` column, but nothing enforces that:
   `result_data.fills` (`db/migrations.py:2176-2193`) has no `CHECK (quantity > 0)`, and
   the participation metric at `analysis/services.py:284-291` defensively applies `abs()`
   while turnover does not.
4. **`active_return` minimum N.** Spec: min N = 1. Implementation: gated behind
   `factor is not None`, which requires N ≥ 2 (`analysis/services.py:174,322,355`), so an
   N = 1 run reports `undefined` instead of a computed value.

**Fix required:** either conform the implementation to spec 15 §10.4 (preferred for the
items above — emit per-component `cost_total` rows, compute drawdown on the compounded TWR
index, add `abs()` to the turnover notional, and align `active_return`'s minimum), or
amend spec 15/`implementation-status.md` to record each divergence as an explicit
boundary. Silent divergence from a document labeled normative is not an acceptable
release state. Add golden-fixture tests for a run with nonzero external cash flows (spec
15 §10.3 requires golden fixtures per definition).

### H-2. Misaligned optional metric inputs degrade silently instead of reporting alignment

`docs/assumptions-and-limitations.md:47-49` promises: "Fill participation and closed-lot
holding period require exact typed aligned inputs …; otherwise their state is
`missing_input`." And the benchmark path indeed reports
`analysis.benchmark.missing_or_unaligned`. But:

- **`risk_free_returns` misalignment** (`analysis/services.py:177-195`): when the supplied
  series length differs from the return count, `excess` silently becomes `[]`, so
  `sharpe` and `sortino` surface as `undefined` with the generic
  `analysis.metric.undefined` reason and *no* warning that the user's risk-free input was
  discarded. `beta`/`alpha`/`tracking_error`/`information_ratio` are also gated on
  `risk_free_aligned` (`analysis/services.py:322`), so a misaligned risk-free series
  degrades benchmark metrics to `undefined` as well — with the benchmark branch still
  reporting them as if computed inputs were merely insufficient.
- **`eligible_volume_by_fill` misalignment** (`analysis/services.py:281-291,569-599`):
  the participation list stays empty and the metrics report
  `INSUFFICIENT_OBSERVATIONS` (count 0), not `missing_input` with an alignment reason.

**Fix required:** treat misaligned `MetricInputs` the way the benchmark path does — either
raise a request-validation error (consistent with "unavailable capabilities fail during
definition/request validation", `docs/implementation-status.md:24-25`) or emit
`MISSING_INPUT` with explicit reasons such as `analysis.risk_free.unaligned` and
`analysis.eligible_volume.unaligned`. Update `assumptions-and-limitations.md` if the
chosen behavior differs from what it currently promises. Add unit tests for each
misalignment path.

### H-3. Undocumented metric set `persistra.standard.phase4@1` accepted by the public API

`analysis/services.py:51-55` accepts `metric_set` values `persistra.standard@1` and
`persistra.standard.phase4@1`. The phase4 name appears nowhere else in the repository —
not in the specs, not in the docs, not in tests. Both names run the identical catalog, but
`metric_set` participates in the execution content id
(`analysis/services.py:58-66`), so the same run computed under the two names produces two
distinct "immutable" artifacts with identical outputs — undermining the exact-reuse story.

**Fix required:** remove the `persistra.standard.phase4@1` alias (it looks like a leftover
from the phase-4 slice). If any persisted artifact may reference it, keep parsing stored
values but reject it for new requests.

### H-4. Release governance documents do not reconcile

Three documents describe release eligibility and they disagree without cross-referencing:

- `docs/v3/v3-spec.md` §37 ("Draft 3.0 acceptance criteria", lines 2357-2422) requires,
  among other things: nested validation and auditable final-holdout use, IOC/FOK/latency/
  forced-liquidation order simulation, fitted forecasts with causal release, the 24 GiB
  benchmark run, and "the agreed coverage gate".
- `docs/implementation-status.md` records that nested selection, the final-holdout ledger,
  fitted estimators, factor risk, the stateful event engine, the formal benchmark, and the
  90 % coverage gate are all *not* satisfied.
- `docs/release-readiness.md:8-17` defines a six-item release gate that omits the
  benchmark and coverage criteria entirely.

The spec self-describes as normative (`docs/index.md:7-12` softens this with "planned
capabilities that are not current API promises", but §37 is not a capability list — it is
the release definition).

**Fix required:** before any release, revise v3-spec §37 (or add a scoping preamble) so
the 3.0 acceptance criteria match the actually intended v3.0 scope, and make
`release-readiness.md` enumerate every remaining criterion it inherits (benchmark
evidence, coverage target, deferred capabilities) rather than a subset. There must be
exactly one authoritative definition of "ready".

---

## Medium-severity findings

### M-1. Quadratic beta/alpha computation

`analysis/services.py:333-344` recomputes `statistics.mean(excess)` and
`statistics.mean(benchmark_excess)` inside the covariance summation generator — once per
observation, making beta O(N²). At the bounded maximum of 2,000,000 return rows this is
effectively a hang.

**Fix required:** hoist both means (and reuse them for the alpha computation at
`analysis/services.py:345-348`) before the summation.

### M-2. TOML injection in the dashboard backup source configuration

`dashboard/source.py:129-132` interpolates `source.path.resolve()` directly into a TOML
basic string: `path = "{source.path.resolve()}"`. A path containing `"` or `\` produces
invalid TOML or, worse, a parsed config whose `path` differs from the verified backup
(the checksum and copy verification at `dashboard/source.py:105-118` ran against the
*original* path). The same pattern risk exists anywhere paths are templated into config
text; `Project.init` (`project.py:207-213`) is safe today because it only writes fixed
relative paths and a regex-validated name.

**Fix required:** escape the interpolated path as a TOML basic string (`json.dumps(str(p))`
produces a valid TOML basic string for this purpose) or reject paths containing `"` or
`\` with a `DashboardSecurityError`. Add a test with a quote-bearing directory name.

### M-3. Export writers leave partial artifacts behind and cannot retry

- `results/exports.py:183` (`_write_duckdb`) and `results/exports.py:212-213`
  (`_write_bundle`) create `.{name}.partial` staging files/directories but have no
  cleanup on failure: an exception mid-write strands the partial artifact.
- On retry, `_write_bundle`'s `staging.mkdir()` then raises `FileExistsError`, and
  `_write_duckdb`'s `duckdb.connect` on the leftover partial file fails or, worse,
  appends to stale content before `os.replace` publishes it.

**Fix required:** wrap both writers so the staging path is removed on failure (and remove
any pre-existing staging leftover before starting, since the `.partial` name is
deterministic). Mirror the cleanup discipline already present in `Project.init`
(`project.py:219-225`).

### M-4. `PortableRunSummary.decision_count` underflows on an empty equity table

`results/exports.py:317` computes `decision_count` as `equity row_count - 1`. A verified
export whose equity table is empty yields `decision_count == -1`. Nothing in
`_validate_semantic_manifest` requires `row_count >= 1` for equity.

**Fix required:** clamp to zero or validate `tables.equity.row_count >= 1` during manifest
validation, whichever matches the publication invariant.

### M-5. Weakly typed public returns in a strict-typed codebase

Pyright runs in strict mode, but several public result surfaces are typed `Any`:

- `VectorizedRun.result() -> Any` (`simulation/services.py:1053`);
- `EventRun.result() -> Any` (`simulation/event_services.py:1092`);
- `AnalysisService.list(..., run_record_id: Any | None)` (`analysis/services.py:812`) —
  the body calls `.value`, so this should be `RunRecordId | None`.

(The `viz` functions returning `Any` are acceptable — Plotly is untyped and optional.)

**Fix required:** type `result()` with the concrete handle type (`RunHandle` via
`TYPE_CHECKING` import) and `run_record_id` as `RunRecordId | None`.

### M-6. `tests/compatibility/support.toml` has no consumer

`pyproject.toml:105` declares a `compatibility` pytest marker and
`docs/v3/phase-plan.md:103` requires recording validated bounds in
`tests/compatibility/support.toml`, but no test, script, or CI step reads that file
(verified by repository-wide search). Its bands can silently drift from
`pyproject.toml` (they already omit `pytz` and `structlog`, and record nothing for
`numpy`/`scipy`/`scikit-learn`/`jinja2`).

**Fix required:** add a `compatibility`-marked test that parses `support.toml` and asserts
its bands match the constraints in `pyproject.toml` (and that installed versions in the CI
band jobs fall inside them), or delete the file and the marker if the CI
`dependency-bands` job is the intended sole mechanism.

### M-7. CI does not run the full recorded release gate

`docs/release-readiness.md:12` includes `uv lock --check` in the release gate, but
`.github/workflows/ci.yml` never runs it (it passes locally today). The `verify` job also
omits `make docs-build`'s prerequisite ordering issue-free — it does run docs-build — but
nothing runs `scripts/check_schema.py` (`make schema-check`) or the benchmark smoke
(`make benchmark-smoke`) in CI, both of which exist as named targets and are cited in the
testing spec.

**Fix required:** add `uv lock --check`, `make schema-check`, and (at least on one Python
version) `make benchmark-smoke` to the CI `verify` job so the automated gate matches the
documented one.

### M-8. Redaction is key-based only; documented claim slightly overstates it

`logging.py:74-81` claims "secrets, paths, and payloads removed", but `_safe_value`
(`logging.py:143-173`) redacts only by *key* fragment. A secret stored under an innocuous
key (`note`, `detail`) survives into persisted run logs truncated to 256 characters, and
the `str(value)[:256]` fallback at `logging.py:173` can embed filesystem paths from
arbitrary objects' reprs. Additionally, the 64-character key truncation at
`logging.py:77,160` can collide two long keys, silently dropping one.

**Fix required:** at minimum, document the key-based boundary in the docstring and in
`docs/assumptions-and-limitations.md` (which currently says nothing about log redaction
scope); optionally add value-pattern scrubbing for high-entropy strings. Make key
truncation collision-safe (e.g., suffix with a short hash when truncating).

### M-9. Monolithic simulation executors are the least-covered code in the release

- `EventSimulationService._execute` spans ~754 lines
  (`simulation/event_services.py:165-919`); the module has the suite's second-lowest
  coverage (76 %, with the large uncovered spans concentrated inside `_execute`).
- `VectorizedSimulationService._execute` spans ~520 lines
  (`simulation/services.py:205-726`).
- `catalog/services.py` is 3,359 lines in one module.

This is where the financial-correctness risk lives, and single-function scope makes the
uncovered branches (`simulation/event_services.py:386-418,498-516,582-595,942-973`) hard
to exercise in isolation.

**Fix required (pre-release, incremental):** extract the order-eligibility, fill, and
settlement phases into pure functions (the codebase already does this well elsewhere, e.g.
`simulation/result_kernels.py`), then add targeted unit tests for the currently uncovered
branches. Treat this as the primary workstream for closing the 82.4 % → 90 % coverage
gap, together with `research/sql_services.py` (74 %) and `viz/_core.py` (44 %).

### M-10. Experiment batch execution: head-of-line blocking and retry-order determinism

`experiments/services.py:590-634` (`_execute_plan_ids`):

- A fresh spawn-context `ProcessPoolExecutor` is created per batch
  (`experiments/services.py:603-606`), paying full interpreter spawn cost every
  `policy.workers` plans, and the batch completes only when its slowest member finishes
  (results are consumed in schedule order), so one straggler idles the whole pool.
- A failed plan is retried by `pending.insert(0, ...)`
  (`experiments/services.py:628`), which moves it ahead of previously scheduled work.
  The determinism contract in `docs/guide.md:39-51` and spec 14 promises stable
  identities across completion order; verify a retry cannot change *assignment*
  identities (schedule ordinals) between an interrupted and a resumed execution, and add
  a contract test for retry-then-resume ordering if one does not exist.

**Fix required:** reuse one executor across batches (determinism comes from the sorted
consumption at `experiments/services.py:614`, not from pool lifetime), and document or
test the retry-ordering guarantee.

---

## Low-severity findings and polish

### L-1. `docs/v3/phase-plan.md` ordered-list markup is broken

Items 10-14 restart numbering as literal `1.` (`docs/v3/phase-plan.md:58,65,72,79,87`)
and their sub-bullets are unindented, so they render as separate lists with orphaned
bullets rather than phases 10-14. Renumber and indent to match items 1-9.

### L-2. Stale v2 bytecode directories inside the v3 tree

`src/persistra/{core,data,features,metrics,pipeline,providers,strategies,strategy,utils}`
and `src/persistra/market/instruments`, plus `tests/unit/{alphavantage,core,data,features,
massive,metrics,pipeline,strategies,strategy,utils,viz}`, exist on disk containing only
v2-era `__pycache__` leftovers (untracked; ignored via the `__pycache__/` pattern). Spec
§37's first acceptance criterion is "the v2 implementation and its native artifacts are
absent from the v3 codebase". Delete them (`find src tests -type d -empty` after removing
`__pycache__` dirs will confirm nothing else remains).

### L-3. `api-reference.md` namespace table is incomplete

`docs/api-reference.md:7-23` omits public namespaces that other docs rely on:

- `persistra.flagship` (used by `docs/index.md:46-52`);
- `persistra.conformance` (required by `docs/implementation-status.md:10` — "Provider
  adapters must pass the conformance kit");
- `persistra.ingestion` (a public re-export shim, `src/persistra/ingestion/__init__.py`,
  named in `docs/v3/phase-plan.md:98`);
- `persistra.errors` and `persistra.logging` (public typed exceptions and the structured
  logging helpers).

Add rows (or explicitly mark the shims as aliases of their parent namespaces).

### L-4. Duplicated fsync helpers

`project.py:632-645`: `_fsync_path` and `_fsync_directory` are byte-identical. Collapse to
one helper.

### L-5. `Project.init` creates the root directory before validating the name

`project.py:162-170`: `root.mkdir(parents=True, exist_ok=True)` runs before the
name-validation `ProjectConfigError`, so a failed init can leave a newly created empty
directory behind. Validate first, or remove the directory in the failure path.

### L-6. Minor dead code and ordering nits in `analysis/services.py`

- `max(len(equity), 0)` at `analysis/services.py:397` — `len` is never negative.
- `MetricsHandle.results()` orders by `metric_name` (`analysis/services.py:761`), so the
  returned order differs from the registry order `_STANDARD_METRIC_NAMES` enforced at
  compute time (`analysis/services.py:602-603`). Harmless, but ordering by insertion
  ordinal would make round-trips deterministic in catalog order.

### L-7. Docs copyedits

- `docs/index.md:38-42`: the namespace list is malformed ("… and `persistra.research`,
  `persistra.portfolio`, … and `persistra.reports`" — a stray `and` mid-list).
- `docs/guide.md:60-74`: the experiments snippet references `project` and `study` that are
  only explained by a comment; `scripts/check_docs.py` merely `compile()`s fences
  (`scripts/check_docs.py:66-71`), so undefined names pass. Consider making snippets
  self-contained or extending the checker to flag undefined top-level names.

### L-8. Toolchain watch items

- The mkdocs-material build banner warns about MkDocs 2.0 breaking the plugin/theme
  system; `mkdocs-material>=9.6,<10` and the strict build protect you today, but record a
  plan (the ADR pattern used for Streamlit fits).
- `pyright>=1.1.400,<2` floats in CI; a pyright minor release can break the gate
  unrelated to any change. Pin the working version (currently 1.1.410) and bump
  deliberately.
- `pyproject.toml:7` still says `version = "2.0.0"`; this is intentional per
  `docs/migration-guide.md:42-44` (human-controlled release), noted here only so the
  release owner remembers the bump is part of the release operation.

---

## Opportunities worth considering before 3.0 (non-defects)

1. **Vectorize the metric engine.** `_compute` (`analysis/services.py:142-604`) runs pure
   Python loops over up to 2 M rows. The `research` extra already carries numpy; an
   optional numpy fast path (with the pure-Python path kept as the base-install fallback
   and a golden-fixture equivalence test) would make large-run analysis materially
   faster without changing the dependency policy.
2. **Schema-level sign invariants.** Add `CHECK (quantity > 0)` to
   `result_data.fills` and the `simulation_data` fill tables
   (`db/migrations.py:1875-1893,2176-2193`) so the unsigned-quantity-plus-side convention
   H-1.3 relies on is enforced by the database, not by engine discipline.
3. **Export re-verification cost.** `PortableRunHandle._table`
   (`results/exports.py:410-453`) re-hashes the full table on every query; `open_export`
   already verifies all tables up front. A verified-once flag per handle (documented as
   trusting the handle's lifetime) would remove redundant O(table) hashing in dashboard
   page queries, which open a fresh handle per query by design.
4. **Executable docs snippets.** The doc gate compiles fences but never runs them. A
   deterministic fixture project (the integration suite already builds one) could execute
   the `guide.md` snippets end-to-end, turning the public workflow page into a tested
   contract.
5. **Coverage ratchet.** Raise `--cov-fail-under` stepwise (82 → 85 → 88 → 90) as M-9's
   extraction work lands, so the release goal is enforced mechanically rather than
   remembered.
6. **Benchmark evidence plan.** `benchmarks/RUNBOOK.md` is honest that the 24 GiB formal
   run cannot execute on this WSL2 host. Since spec §37 makes it an acceptance
   criterion, record in `release-readiness.md` *where* the formal run will happen (or
   descope it per H-4) — today the gap is only acknowledged in
   `docs/implementation-status.md:22`.

## What was checked and found sound

For completeness, areas verified without findings: the public API map matches reality
(every symbol in the `guide.md` snippets exists with the documented signatures, including
`RunRecordId.parse`, `run.equity(max_rows=...)`, `viz.performance.equity`,
`reports.verify_bundle`, `WorkerOutcome`, `apply_scenario`, and the
`persistra dashboard --project/--export` and `persistra db` CLI surfaces); the
event-fill → normalized-fill column remapping (`simulation/event_services.py:855-875`
against `db/migrations.py:1875-1893,2176-2193`) is correct including the non-obvious
spread/slippage/impact/fee reordering; the eight dashboard page keys match the docs; the
domain time/duration primitives are exact and overflow-guarded; `Project.open`'s
lease/connection unwind on failure is correct; export verification enforces table
closure, view absence, manifest uniqueness, and content ids; and the flagship profile
constants match their description in `docs/index.md`.
