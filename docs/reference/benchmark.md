# Release benchmark

`persistra.benchmark.daily_equity_1000x10@1` is the formal v3 performance benchmark:
1,000 instruments over ten years of XNYS daily sessions, sized to run on the supported
local development host with an 8 GiB peak-resident-set gate.

## Generate the fixture

The deterministic fixture is produced outside the measured boundary:

```bash
uv run python -m benchmarks.daily_equity_1000x10 \
  --generate --fixture /local/fixture.duckdb
```

The generator is seeded (`SEED = 20250300`); its raw-bar draws are reproducible and
independently checkable with `benchmarks.validator.validate_fixture`.

## Measured run

```bash
/usr/bin/time -v uv run python -m benchmarks.daily_equity_1000x10 \
  --fixture /local/fixture.duckdb \
  --output /local/new-output \
  --manifest benchmarks/manifests/daily_equity_1000x10-v1.json
```

The run computes the bounded feature/universe workload (returns, momentum windows,
realized volatility, dollar volume, cross-sectional percentile and sector z-score) into
a new output directory. It is valid when `Maximum resident set size` is at or below
8 GiB (8,589,934,592 bytes) and the printed feature/decision counts match the manifest.

## Smoke target

`make benchmark-smoke` runs the generator, validator, and runner on a tiny scaled shape
inside the test suite. It is correctness evidence for the protocol, not memory evidence.

See `benchmarks/RUNBOOK.md` for the full cold-cache protocol and the release-evidence
requirement recorded on the [release governance page](../explanation/release-governance.md).
