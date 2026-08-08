# Cross-asset regime studies

This directory contains five executable, output-free notebooks. Each notebook asks one
predeclared question about associations between macroeconomic information and subsequent
cross-asset outcomes. The notebooks use live Alpha Vantage and FRED or ALFRED data through
Persistra's public API. They never use synthetic data.

The committed notebooks contain no provider observations, derived tables, figures, execution
counts, or empirical conclusions. Their narrative explains concepts and procedures without
describing the values returned by a particular execution. Live execution creates a temporary
raw-response directory, uses it only for the running kernel, and removes it before the process
exits. This keeps the public artifacts focused on reviewable procedures without redistributing
provider data.

This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of
St. Louis. Alpha Vantage and FRED or ALFRED terms, entitlements, and source-owner restrictions
govern every execution.

## Shared analysis policy

The analysis window starts in March 2008 and ends at the last complete calendar month available
during execution. Price acquisition starts in March 2007 to give the first analysis decisions a
complete trailing twelve-month momentum baseline. Every study uses adjusted daily Alpha Vantage
bars for this core universe:

- `SPY`: broad United States equities
- `IEF`: intermediate United States Treasury bonds
- `GLD`: a liquid gold proxy
- `DBC`: a diversified commodity proxy
- `UUP`: a liquid United States dollar proxy

Individual notebooks may add `TIP`, `TLT`, or `SHY` when inflation compensation or Treasury
duration is central to the question. The fixed contemporary ETF universe is intentional. It
does not reproduce a historically investable selection process and does not remove inception,
survivorship, or product-design bias.

Each decision date is the last common ETF close in a complete calendar month. The macro
information cutoff is measured from that actual trading date, not the later calendar month end.
The primary outcome is the next one-calendar-month simple return between common closes. Three-
and twelve-month forward returns are secondary outcomes. The runner asserts consecutive monthly
price periods and exact calendar label horizons. Forward returns remain separate from macro
features.

Every study reports unconditional outcomes and a trailing twelve-month price-momentum split over
the same macro-eligible decisions. Regime-conditioned means and contrasts use a Bartlett-kernel
heteroskedasticity-and-autocorrelation-consistent standard error. Its lag is at least the overlap
floor and can be longer under a fixed automatic bandwidth rule. Pointwise intervals describe the
full tables. Bonferroni simultaneous intervals cover each predeclared one-month hypothesis family.
Larger sensitivity grids receive a separate exploratory whole-family adjustment. A gray or blank
estimate has fewer than twelve outcomes or two outcome-eligible episodes on one side; this is a
display warning, not a statistical significance filter. The notebooks report coverage, counts,
episodes, positive-return shares, horizon-return dispersion, episode-aware drawdowns, and every
predeclared comparison.

All revised macroeconomic series have two views:

1. The point-in-time view selects only observations and versions available by the actual
   decision-date cutoff, applies a one-calendar-day operational lag, and rejects stale matches.
2. The latest-revised diagnostic uses current values for the exact source periods selected by the
   real-time construction. It is deliberately unavailable to the primary classification.

Year-over-year, rolling, and momentum transforms are calculated inside one as-of vintage
snapshot. Their components use explicit source-period offsets rather than shifts across decision
rows. Component-level provenance records the expected and actual periods and the complete
availability interval. This avoids mixing releases, revisions, or rebased levels across vintage
snapshots. The revised view is a bias diagnostic, not an alternative research policy.

The daily yield-curve study requests only its exact zero-, one-, and two-day cutoff sets. When
bounded responses repeat a revision with query-scoped interval ends, the combiner verifies all
economic fields and reconstructs inclusive intervals from the ordered selected revision starts.
The result supports those declared cutoffs; it is not a retained or complete daily vintage
archive.

## Predeclared studies

### 1. Growth and inflation quadrants

**Question:** How do fixed cross-asset proxies behave after combinations of positive or
nonpositive industrial-production growth and high or lower consumer-price inflation?

The macro series are industrial production (`INDPRO`) and the consumer price index
(`CPIAUCSL`). Growth is the year-over-year percent change in industrial production. Inflation
is the year-over-year percent change in the price index. The primary boundaries are zero percent
for growth and three percent for inflation. This creates expanding/lower-inflation,
expanding/high-inflation, contracting/lower-inflation, and contracting/high-inflation states.

The four primary estimands come from saturated effect-coded growth-by-inflation models. They are
average inflation effects for `GLD` and `DBC`, and average growth effects for `SPY` and `IEF`,
with the other macro factor and interaction retained. Sensitivity uses inflation boundaries of
2.5, 3.0, and 3.5 percent and growth boundaries of -1, 0, and 1 percent. No quadrant is assumed
to produce a profitable strategy.

### 2. Labor-market deterioration

**Question:** How do cross-asset outcomes differ after a real-time labor deterioration alert?

The feature uses the unemployment rate (`UNRATE`). It calculates the three-month mean of the
latest rate known at each decision date, then subtracts the lowest three-month mean observed
during the preceding twelve months. The primary alert begins at a 0.5 percentage-point increase.
This is a Sahm-rule-like construction, not the official recession indicator and not a claim that
the notebook dates recessions.

The predeclared one-month outcomes are `SPY`, `DBC`, `TLT`, and the paired `TLT` minus `SHY`
return spread. Expected contrast signs are weaker risk-asset outcomes and stronger Treasury
outcomes during alerts. Sensitivity uses 0.3, 0.5, and 0.7 percentage-point alert boundaries.

### 3. Yield-curve inversion

**Question:** How do cross-asset outcomes differ after the ten-year minus two-year Treasury
spread is inverted at a month end?

The feature is the daily Treasury spread (`T10Y2Y`) selected from historical views requested for
the decision dates. The primary boundary is zero percentage points. A one-day operational lag
and a seven-day maximum staleness rule prevent a weekend or holiday from creating a forward
lookup. `TLT` and `SHY` extend the core universe.

The four predeclared one-month outcomes are `SPY`, `TLT`, and the paired `TLT` minus `SHY` and
`TLT` minus `IEF` return spreads. They use two-sided contrasts without treating inversion as a
deterministic recession timer. Sensitivity crosses spread boundaries of -0.25, 0, and 0.25
percentage points with operational lags of zero, one, and two days. The zero-day row is an
explicitly optimistic, noncausal diagnostic because day-resolution availability cannot establish
that the rate was known before the ETF close.

### 4. Inflation acceleration and deceleration

**Question:** How do inflation-sensitive assets behave after changes in real-time inflation
momentum?

The primary feature uses `CPIAUCSL`. Inflation momentum is the current year-over-year inflation
rate minus the rate for the source month six months earlier, with both rates computed from one
as-of vintage. Acceleration is above 0.25 percentage points, deceleration is below -0.25
percentage points, and the middle band is stable. `CPILFESL` provides a core-inflation sensitivity
check, and `TIP` extends the asset universe.

The three primary outcomes are paired return spreads: `TIP` minus `IEF`, `DBC` minus `IEF`, and
`GLD` minus `IEF`. This directly tests whether inflation-sensitive exposures differ from nominal
intermediate Treasuries across acceleration states. Sensitivity uses symmetric bands of 0.10,
0.25, and 0.50 percentage points and repeats the construction with core inflation.

### 5. Macroeconomic revision risk

**Question:** Does classifying growth with latest-revised data materially change the apparent
cross-asset differences obtained from information available in real time?

The primary feature is year-over-year real GDP growth from `GDPC1`. Faster growth is above two
percent and slower growth is at or below two percent. The current latest-revised history is used
only to measure classification instability and changes in the descriptive outcome summaries.
Payroll employment (`PAYEMS`) is a monthly sensitivity series with positive versus nonpositive
year-over-year growth.

The predeclared signed estimand is the latest-revised faster-minus-slower return contrast minus
the real-time faster-minus-slower contrast on dates classified in both views. It does not claim
that revisions make separation larger in absolute value. A separate total estimate and component
summary distinguish reclassification from availability changes. Sensitivity uses real-GDP
boundaries of 0, 1, 2, and 3 percent. Revision size and classification changes remain
retrospective diagnostics rather than tradable features.

## Execution

Set the provider variables outside the notebook:

```bash
export PERSISTRA_ALPHAVANTAGE_API_KEY="your-key"
export PERSISTRA_FRED_API_KEY="your-key"
```

Install the study tools and execute every notebook without modifying the committed files:

```bash
uv sync --frozen --group studies
make studies-run
```

Execute one notebook by filename:

```bash
uv run --frozen --group studies python scripts/run_studies.py \
  03_yield_curve_inversion.ipynb
```

For interactive review, copy the canonical notebooks to a temporary directory before opening
JupyterLab. Outputs and checkpoints then remain outside the repository:

```bash
study_work=$(mktemp -d)
study_repo=$(pwd)
trap 'rm -rf -- "$study_work"' EXIT
cp studies/*.ipynb "$study_work/"
PYTHONPATH="$study_repo" uv run --frozen --group studies jupyter lab \
  --ServerApp.root_dir="$study_work"
```

Close JupyterLab when the review is complete; the shell trap removes the temporary directory. Do
not copy an executed notebook back into `studies/`.

Run the static safeguards without provider access:

```bash
make studies-check
```

The live runner fails on a notebook error and discards the executed in-memory copy. It reports
only execution status. It does not save cell outputs. Each execution displays a temporary run
manifest with package versions, source series, policies, thresholds, and analysis dates. Exact
empirical results cannot be reconstructed later because provider snapshots are intentionally not
retained. Reruns may therefore reflect provider revisions.

The canonical `.ipynb` files are generated from reviewable cell definitions. Edit
`scripts/build_studies.py`, regenerate the notebooks, and run both checks:

```bash
uv run python scripts/build_studies.py
make studies-check
```

Provider quotas apply to every live run. The notebooks request fresh responses and do not offer a
persistent cache or offline replay path.

## Interpretation boundary

These studies estimate conditional associations in a small, fixed sample. They do not establish
causality, forecast skill, portfolio profitability, or implementation feasibility. Overlapping
horizons, repeated comparisons, stale macro releases, ETF inception, revised history,
survivorship, transaction costs, taxes, and unavailable intramonth information all limit the
inferences. A null, unstable, or contrary result is a valid result and must remain visible during
live review.
