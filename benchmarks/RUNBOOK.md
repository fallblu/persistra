# Daily equity 1,000 × 10 benchmark

`persistra.benchmark.daily_equity_1000x10@1` is the formal v3 release benchmark: 1,000
instruments over ten years of XNYS daily sessions with an 8 GiB peak-resident-set gate,
sized to run on the supported local development host.

Generate the deterministic fixture outside the measured boundary:

```bash
uv run python -m benchmarks.daily_equity_1000x10 \
  --generate --fixture /local/fixture.duckdb
```

Verify the fixture with the independent validator, establish a cold-cache state, and
invoke the measured run:

```bash
/usr/bin/time -v uv run python -m benchmarks.daily_equity_1000x10 \
  --fixture /local/fixture.duckdb \
  --output /local/new-output \
  --manifest benchmarks/manifests/daily_equity_1000x10-v1.json
```

The run is valid when it completes with `Maximum resident set size` at or below
8 GiB (8,589,934,592 bytes) and the runner's printed feature/decision counts match the
generator manifest. The repository smoke target
(`make benchmark-smoke`) scales only cardinality and date range; it is correctness
evidence for the generator/runner/validator protocol, not memory evidence. Record the
formal `/usr/bin/time -v` output alongside the release evidence when the gate is claimed.
