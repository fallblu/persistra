# Multi-asset support — implementation guide (TEMPORARY)

> **Temporary working document.** This guide drives the `feat/multi-asset` effort and is
> **removed before the PR is opened** (Phase 11.3). It is deliberately placed under
> `notes/` — outside `docs/` — so `scripts/check_docs.py` and the strict mkdocs build
> ignore it. Do not add it to `mkdocs.yml`.

## Context

Persistra today is a point-in-time research/backtesting library whose canonical data
model is **USD-equity-shaped**: the reference chain is `Issuer → Security → Listing →
Instrument` bound to a 4-letter MIC and an exchange calendar; `InstrumentDefinition`,
`DailyBar`, `TradeObservation`, `QuoteObservation`, and corporate-action terms all reject
non-USD; `SecurityKind` enumerates only equity kinds. We want to use persistra for general
**multi-asset research** sourced from **Alpha Vantage** (premium key, 75 req/min).

This branch unlocks multi-asset **data and research** (not multi-currency accounting) with
a working live Alpha Vantage ingestion path.

Two facts from codebase exploration shape everything:
- The canonical market tables already store `currency` as a free `VARCHAR`, so de-gating
  the market families is **code-only** (drop `!= "USD"` guards, thread `Currency`). USD is
  only hard-baked deeper, in the research/accounting/results layer (`*_usd DECIMAL` columns)
  — explicitly **out of scope** here.
- All 13 existing families ingest **typed-direct** (`bars.ingest(DailyBar)` →
  `canonical.bars`). The generic `SourceDefinition`/batch/conformance pipeline projects to
  no typed table. The AV adapter therefore feeds **typed services directly**.

## Locked decisions

| Decision | Choice |
|---|---|
| Branch scope | Foundations + fitting categories (equities/core-stock, macro, commodities, index, crypto, FX). **Options/futures deferred** to a future branch. |
| Sequencing | **Foundations-first**: land currency/asset-class/calendar/reference generalization before any category. |
| AV adapter | **Included** on this branch (live HTTP). |
| Ingest path | **Typed services directly** (AV JSON → domain objects → existing `.ingest()`), consistent with all existing families. Generic pipeline untouched. |
| HTTP client | **stdlib `urllib`**, zero new dependencies (preserve local-first, curated deps). |
| Credentials | **Env var only** (`PERSISTRA_ALPHAVANTAGE_API_KEY`); no config-schema change. |
| Currency depth | **Market/reference layer only**; valuation/accounting stays single reporting currency. Full multi-currency accounting = later epic. |
| Fundamentals | **Deferred.** AV's pre-normalized fundamentals do not fit the strict filing/XBRL model; keep that path high-fidelity. Not ingested this branch. |
| Pair modeling | **Extend the existing chain**: add an `AssetClass`, new kinds (`fx_pair`, `crypto_pair`), base/quote currency columns, a synthetic "market-convention" issuer, relax MIC/currency gates. |
| Base branch | `feat/multi-asset` cut from `v3/release-hardening` (68 commits ahead of `main`; holds the v3 codebase this builds on). |

## Gates every commit must pass

Run `make lint type test docs-check` before each commit; add `make schema-check` and
`make docs-build` on any commit touching migrations or `docs/`.
- **ruff** (line-length 100; `E,F,I,B,UP,TC,RUF`)
- **pyright** strict (src + tests)
- **pytest** with `--cov-fail-under=85` (branch coverage) — **each commit ships its own
  tests and stays ≥85%**; this dictates commit granularity.
- **docs-check** (`scripts/check_docs.py`) — required pages present, in nav, links + python
  snippets valid (scans `docs/` only).
- **schema-check** (`scripts/check_schema.py`) — DB at `CURRENT_SCHEMA_VERSION`, contiguous
  migration ledger `1..N`, required research tables present.

Commit style: conventional, subject-only (`feat:`/`fix:`/`refactor:`/`test:`/`docs:`),
no trailers, no AI attribution. One coherent green unit per commit. Never push/tag/release.

---

## Phase 0 — Branch + guide

- **0.1 `docs: add temporary multi-asset implementation guide`** — create branch
  `feat/multi-asset` off `v3/release-hardening`. Write this file.
  Acceptance: gates pass (markdown-only; no code impact).

---

## Phase 1 — Domain: asset-class taxonomy

Introduce the vocabulary every later phase depends on, with zero behavior change yet.

- **1.1 `feat: add AssetClass taxonomy to domain`** — add `AssetClass(StrEnum)` (e.g.
  `EQUITY`, `FX`, `CRYPTO`, `COMMODITY`, `INDEX`, `RATE`, `MACRO`) in a new
  `src/persistra/domain/assets.py`; export from `domain/__init__.py`. Pure value type + a
  small classification helper (which asset classes are "pair-shaped", which are OTC/24×7).
  Tests: `tests/unit/test_assets.py` exhaustively covering members + helpers (keeps
  coverage on the new module at 100%).
- **1.2 `feat: extend SecurityKind with non-equity kinds`** — add `FX_PAIR`, `CRYPTO_PAIR`,
  `COMMODITY`, `INDEX` to `SecurityKind` in `reference/models.py`; add a
  `SecurityKind → AssetClass` mapping. Do **not** yet change any gate. Tests extend
  `tests/unit/test_*reference*`/model-validation to cover the new mapping.

Acceptance: new enums/mappings fully covered; no existing test changes needed.

---

## Phase 2 — Currency de-gating of market families (code-only)

Schema already permits any currency; remove the Python guards and thread `Currency`.

- **2.1 `refactor: accept any Currency in market bar/trade/quote contracts`** — in
  `market/models.py`, replace the `currency != "USD"` rejections in `DailyBar`
  (~line 314), `TradeObservation` (~438), `QuoteObservation` (~498) with validation via
  `domain.Currency` (registered ISO code). Keep `"USD"` as the default so existing callers
  and fixtures are unchanged. Update the corporate-action cash/leg currency checks (~703,
  ~768) to accept any registered currency while preserving the paired-field invariants.
- **2.2 `test: multi-currency market contract validation`** — add unit tests asserting a
  `DailyBar`/`Trade`/`Quote` in EUR/JPY/GBP validates, and an unregistered code still
  raises. Confirm `market/frames.py` `currency` columns already carry it (no frame change
  expected; assert via `build_frame`).

Acceptance: existing USD tests unchanged and green; new non-USD tests green. No migration.

---

## Phase 3 — Calendars: OTC / 24×7 / FX

Reference calendars currently require an `exchange-calendars` name + a real venue. FX is
24×5, crypto 24×7.

- **3.1 `feat: support always-open and FX trading calendars`** — in `reference/models.py`
  `CalendarDefinition`, allow synthetic calendars (24×7, FX 24×5). **Verification item:**
  determine whether `exchange-calendars` already exposes a usable always-open ("24/7")
  and/or FX calendar; if yes, register by name; if not, add a small synthetic schedule
  generator behind the existing `ResolvedCalendarRef`/`Session` contracts. Relax the
  requirement that a calendar names an equity venue MIC.
- **3.2 `test: 24×7 and FX calendar sessions`** — cover session generation across
  weekends/holidays for both, plus that bar/session-decision logic (`reference/services.py`
  calendars) resolves them. Register default calendars (e.g.
  `persistra.calendar.always_open@1`, `persistra.calendar.fx_24x5@1`).

Acceptance: calendars resolve and produce sessions; existing exchange calendars unaffected.
May require a **migration** if default calendars are seeded into `canonical.calendar_*` —
if so, bump `CURRENT_SCHEMA_VERSION` and run `make schema-check`.

---

## Phase 4 — Reference model generalization (migration)

Make instruments express non-equity, issuer-less, pair-shaped assets.

- **4.1 `feat: add asset-class + base/quote columns to reference schema`** — append a new
  `MigrationStep` to `db/migrations.py` adding nullable `asset_class`, `base_currency`,
  `quote_currency` to `canonical.instruments`/`instrument_observations` (and a synthetic
  issuer sentinel convention). Bump `CURRENT_SCHEMA_VERSION`; keep ledger contiguous.
  `make schema-check` must pass.
- **4.2 `feat: generalize InstrumentDefinition for non-equity instruments`** — in
  `reference/models.py`, add `asset_class`, optional `base_currency`/`quote_currency`;
  replace the `currency != "USD"` gate (~308) and the 4-letter-uppercase MIC requirement
  with asset-class-aware validation (equities keep MIC + issuer; FX/crypto allow a
  synthetic issuer, optional/absent MIC, and require base/quote). Update
  `reference/services.py` `register_instrument` INSERTs to persist the new columns.
- **4.3 `feat: allow non-equity kinds in universe definitions`** — extend
  `UniverseDefinition.allowed_security_kinds` handling and `_evaluate_candidate`
  (`reference/universes.py`) so pair instruments can be selected; default equity universes
  unchanged.
- **4.4 `test: non-equity instrument reference round-trip`** — integration test registering
  an FX pair and a crypto pair instrument and reading them back through
  `reference.instruments(...)`; unit tests for the new validation branches.

Acceptance: equity path byte-for-byte unchanged; FX/crypto instruments register + resolve;
schema-check green at the new head.

---

## Phase 5 — Alpha Vantage adapter framework

Infrastructure shared by every category. Typed-direct, stdlib-only, env-var key.

- **5.1 `feat: add Alpha Vantage HTTP client`** — new subpackage
  `src/persistra/sources/alphavantage/` with a `client.py`: stdlib `urllib` GET wrapper,
  base URL + `function`/params, **token-bucket rate limiter** (default 75/min, configurable),
  timeout, bounded retry/backoff on 429/5xx, JSON decode, and AV "Note"/"Error Message"
  envelope handling. Key from `PERSISTRA_ALPHAVANTAGE_API_KEY`; **never logged** (verify
  against `logging.py` redaction). No network in tests — inject a transport/opener seam so
  tests feed canned JSON.
- **5.2 `feat: add AV source/dataset registration helpers`** — a `registration.py` that
  builds the `SourceDefinition` (provider name, licensing class, redistributable=False) and
  the per-family `DatasetDefinition`s, registering via
  `services.catalog.sources.register(...)`/`datasets.register(...)`. (These describe
  provenance/licensing even though ingestion is typed-direct.)
- **5.3 `feat: define the AV parse→ingest boundary`** — a small `ingest.py` defining the
  clean boundary: each endpoint parser returns canonical **domain objects** (`DailyBar`,
  `MacroRelease`, …) which a thin coordinator hands to the matching typed service. This
  boundary is what a future generic-pipeline projector could slot behind.
- **5.4 `test: AV client rate-limit, retry, redaction, error envelopes`** — unit tests with
  a fake opener: rate limiter paces calls, retries on 429, raises typed errors on AV error
  envelopes, redacts the key. Add `persistra.errors` entries as needed.

Acceptance: client + framework fully covered offline; no live network in the suite.

Docs: extend `docs/how-to/ingest-market-data.md` with an AV section (keep nav valid;
python snippets must pass `check_docs.py`).

---

## Phase 6 — Core stock via Alpha Vantage

First live category. Prices as **raw OHLCV + corporate actions**, letting persistra's
adjustment engine compute adjusted series (do **not** ingest AV's pre-adjusted close as
canonical).

- **6.1 `feat: AV daily/intraday equity bar parsers`** — parse `TIME_SERIES_DAILY`
  (+adjusted fields) and `TIME_SERIES_INTRADAY` → `DailyBar` (session + fixed-grid
  `BarSpec`). Map to existing `bars.ingest`. Tests use canned AV JSON fixtures under
  `tests/fixtures/source/alphavantage/`.
- **6.2 `feat: AV splits & dividends → corporate actions`** — parse split coefficients +
  dividend amounts (adjusted daily, or `SPLITS`/`DIVIDENDS` endpoints) → `CorporateAction`
  (`SPLIT`, `ORDINARY_CASH_DIVIDEND`); ingest via `actions.ingest`. Assert the adjustment
  engine then produces correct adjusted bars.
- **6.3 `feat: AV market + listing status`** — `MARKET_STATUS` → `TradingStatusObservation`;
  `LISTING_STATUS` → reference listing status. Optional `GLOBAL_QUOTE` deferred/skipped.
- **6.4 `test: AV core-stock end-to-end`** — integration test mirroring
  `tests/integration/test_daily_market_research.py`: register source/dataset + instrument →
  ingest bars+actions from fixtures under `MARKET_WRITE` → snapshot → reopen `READ_ONLY` →
  `bars.query` + adjusted materialization assertions.

Acceptance: AV JSON fixtures round-trip to queryable adjusted equity bars.

---

## Phase 7 — Economic indicators + commodities via Alpha Vantage

Best fit to existing `MacroSeries`/`RiskFreeCurve` contracts; no new families.

- **7.1 `feat: AV macro series parsers`** — `REAL_GDP`, `CPI`, `INFLATION`, `UNEMPLOYMENT`,
  `RETAIL_SALES`, `NONFARM_PAYROLL`, etc. → `MacroSeriesDefinition` + `MacroRelease`/
  `MacroObservation` (units, frequency, geography). AV has no vintages →
  `vintage_completeness = LATEST_ONLY`, `availability_quality = ingestion_bounded`.
- **7.2 `feat: AV treasury yield + fed funds → rate curve`** — `TREASURY_YIELD` (per
  maturity) → `RiskFreeCurveDefinition` + `RiskFreePoint` with `Tenor`s;
  `FEDERAL_FUNDS_RATE` → `OVERNIGHT_RATE`.
- **7.3 `feat: AV commodity price series`** — `WTI`, `BRENT`, `NATURAL_GAS`, `COPPER`,
  `WHEAT`, `CORN`, `ALL_COMMODITIES`, … → `MacroSeries` (price series; not tradeable
  futures). Register under a `commodity` asset-class label.
- **7.4 `test: AV macro/rate/commodity round-trip`** — integration test mirroring
  `tests/integration/test_economic_market_data.py`.

Acceptance: macro/rate/commodity series ingest and query with honest availability quality.

---

## Phase 8 — Index data via Alpha Vantage

- **8.1 `feat: AV index series → benchmark source-series`** — map available AV index series
  to `BenchmarkDefinition` (`SOURCE_SERIES`, `PRICE_INDEX`/`TOTAL_RETURN_INDEX`) +
  `BenchmarkSeriesObservation`. **Note the AV limitation** (index coverage is thin) in the
  guide and docs; scope to what AV actually serves.
- **8.2 `test: AV index → benchmark query`** — integration round-trip via `benchmarks.series`.

Acceptance: available indices queryable as benchmarks; limitations documented.

---

## Phase 9 — Cryptocurrencies via Alpha Vantage

First consumer of the pair/asset-class + 24×7-calendar foundations.

- **9.1 `feat: AV crypto pair instruments`** — register `crypto_pair` instruments
  (base/quote, synthetic issuer, always-open calendar) via the Phase-4 reference path.
- **9.2 `feat: AV crypto bar parsers`** — `DIGITAL_CURRENCY_DAILY/WEEKLY/MONTHLY`,
  `CRYPTO_INTRADAY` → `DailyBar` in the quote currency (often USD, sometimes EUR/BTC).
- **9.3 `test: AV crypto end-to-end`** — integration round-trip (24×7 sessions, non-USD
  quote) → `bars.query`.

Acceptance: crypto pairs ingest/query on a 24×7 calendar, non-USD quote currencies work.

---

## Phase 10 — Foreign exchange via Alpha Vantage

- **10.1 `feat: AV FX pair instruments`** — register `fx_pair` instruments (base/quote,
  synthetic issuer, FX 24×5 calendar).
- **10.2 `feat: AV FX bar parsers`** — `FX_DAILY/WEEKLY/MONTHLY`, `FX_INTRADAY` → `DailyBar`
  (no volume for spot FX → `volume = 0` / appropriate `BarState`; verify against `DailyBar`
  invariants and adjust the parser, not the contract). `CURRENCY_EXCHANGE_RATE` for latest.
- **10.3 `test: AV FX end-to-end`** — integration round-trip (24×5 sessions, cross rates).

Acceptance: FX pairs ingest/query on a 24×5 calendar.

> **Verification item:** spot-FX bars have no trade volume; confirm how `DailyBar`'s
> positive-volume invariant interacts and choose the faithful representation (likely a
> volume-less bar state) at Phase 2/10 — resolve here before coding Phase 10.

---

## Phase 11 — Finalization

- **11.1 `docs: multi-asset ingestion + assumptions`** — update
  `docs/how-to/ingest-market-data.md` and
  `docs/explanation/assumptions-and-limitations.md` (AV = `ingestion_bounded`, no
  vintages/as-reported history, fundamentals deferred, index coverage thin). Keep nav +
  snippets valid; run `make docs-build`.
- **11.2 `test: cross-asset conformance + integration sweep`** — one integration test
  exercising equity + macro + crypto + FX in a single project; ensure the provider
  conformance suite still passes for any declared AV source descriptor.
- **11.3 `chore: remove temporary multi-asset implementation guide`** — delete this file
  before opening the PR.

Then open a PR (`gh`, Summary + Test plan). **Do not merge without explicit approval.**

---

## Key design notes

- **Adjusted prices:** ingest raw OHLCV + splits/dividends; persistra's adjustment engine
  produces adjusted series. AV's pre-adjusted close is not treated as canonical (would
  bypass provenance). If wanted later, model it as a separate low-trust source series.
- **Synthetic issuer:** FX/crypto have no issuer; use one reserved sentinel
  "market-convention" issuer id per asset class rather than nullable issuer FKs, minimizing
  schema churn.
- **Availability honesty:** every AV family ingests as `ingestion_bounded` — persistra is a
  point-in-time engine and AV serves latest snapshots; this is a source property, recorded
  faithfully, not a bug to paper over.
- **Ingest boundary (Phase 5.3):** parsers emit domain objects behind a seam so a future
  generic-pipeline projector can be introduced without rewriting parsers.
- **Out of scope (future branches):** options/futures (net-new derivative asset class);
  full multi-currency valuation/accounting (`*_usd` research/accounting/results layer);
  AV fundamentals; technical indicators (derive via `research/features.py`, don't ingest).

## Risks / verification items (resolve here before the relevant phase)

1. `exchange-calendars` availability of 24×7 / FX-24×5 calendars vs. a synthetic generator
   (Phase 3).
2. Spot-FX volume-less bars vs. `DailyBar` positive-volume invariant (Phase 2/10).
3. Whether seeding default calendars/instruments requires a migration + `schema-check` bump
   (Phases 3–4).
4. AV index-endpoint coverage — confirm what is actually retrievable (Phase 8).
5. Coverage ≥85% per commit — each phase's tests must land in the same commit as its code.

## Verification (end-to-end)

- **Per commit:** `make lint type test docs-check` (+ `schema-check`/`docs-build` when
  touching migrations/docs); coverage ≥85%.
- **Live smoke (manual, real key):** with `PERSISTRA_ALPHAVANTAGE_API_KEY` set, run a
  small script per category (equity bars, a macro series, a crypto pair, an FX pair)
  ingesting a few symbols into a scratch project and querying them back — confirming the
  live HTTP path, rate limiter, and typed-service ingestion work against the real API.
  (Kept out of the automated suite; suite uses canned fixtures only.)
- **Branch close:** full `make lint type test docs-check schema-check docs-build`, guide
  removed, PR opened for review.

## Progress log

- [x] Phase 0.1 — branch `feat/multi-asset` created off `v3/release-hardening`; guide written.
- [ ] Phase 1 — asset-class taxonomy
- [ ] Phase 2 — currency de-gating
- [ ] Phase 3 — calendars
- [ ] Phase 4 — reference generalization
- [ ] Phase 5 — AV adapter framework
- [ ] Phase 6 — core stock
- [ ] Phase 7 — macro + commodities
- [ ] Phase 8 — index
- [ ] Phase 9 — crypto
- [ ] Phase 10 — FX
- [ ] Phase 11 — finalization
