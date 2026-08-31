# Performance benchmarks

Persistra measures five operations that carry the highest runtime or memory risk:

- cumulative DuckDB bar queries;
- time-series factor regressions;
- constrained portfolio optimization;
- incremental Trading Engine journal parsing; and
- inspector table preparation.

Each workload uses deterministic small, medium, and large data. The result records wall-time
samples, their median, peak Python allocation tracked by `tracemalloc`, total process peak resident
memory, workload dimensions, the Python runtime, the platform, and direct dependency versions.
Each case runs in a fresh process so memory high-water marks do not leak between operations.

Run the complete informational suite locally:

```bash
make benchmark
```

The command writes JSON to standard output. Redirect it when you want to compare runs. These local
results are informational because hardware, system load, and Python builds vary.

## Stable regression gate

The controlled Linux job runs weekly, can be started manually, and also runs when benchmark code or
a measured implementation changes on `develop`. It stores `benchmark-results.json` as a workflow
artifact for 30 days. Run the same threshold check locally with:

```bash
make benchmark-check
```

Only medium profiles are hard gates. Small profiles are dominated by startup noise, while large
profiles are useful for observing scaling but are more sensitive to shared-runner variance. The
versioned ceilings in `performance-thresholds.toml` cover median wall time, total process peak
resident memory, and peak traced Python allocation. Change a ceiling only with benchmark evidence
from the controlled job and explain the reason in review.
