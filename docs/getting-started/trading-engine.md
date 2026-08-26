# Set up Trading Engine

[Trading Engine](https://github.com/fallblu/trading-engine) is the separate deterministic replay
runtime used with Persistra. Add it only when research inputs are ready for event-driven execution
testing.

Clone the repositories beside each other and build the engine:

```bash
git clone https://github.com/fallblu/trading-engine.git
cd trading-engine
opam install . --deps-only --with-test
dune build
dune runtest
```

Confirm the executable and current contract:

```bash
_build/default/bin/main.exe --version
_build/default/bin/main.exe --capabilities
python test/validate_schemas.py contracts/v1
```

Trading Engine owns execution semantics and writes the audit journal. Persistra owns research data,
typed v1 scenario adapters, schema validation, provenance, and reconciliation of retained
artifacts. Neither project connects to a broker or places live orders.

Continue with [Build Trading Engine scenarios](../guides/trading-engine.md).
