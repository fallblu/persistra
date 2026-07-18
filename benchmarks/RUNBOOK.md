# Daily equity 5,000 × 20 benchmark

Generate the deterministic fixture outside the measured boundary:

```bash
uv run python -m benchmarks.daily_equity_5000x20 \
  --generate --fixture /local/fixture.duckdb
```

On the controlled host described in focused specification 18, verify the fixture with the
independent validator, establish the required cold-cache state, and invoke:

```bash
/usr/bin/time -v uv run python -m benchmarks.daily_equity_5000x20 \
  --fixture /local/fixture.duckdb \
  --output /local/new-output \
  --manifest benchmarks/manifests/daily_equity_5000x20-v1.json
```

The formal run remains invalid unless the host, swap, parent timing process, clean source,
fixture logical root, output roots, telemetry, and 24 GiB RSS evidence are independently
attested. The repository smoke target scales only cardinality and date range; it is correctness
evidence for the generator/runner/validator protocol, not formal memory evidence.
