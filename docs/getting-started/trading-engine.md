# Set up Trading Engine

Trading Engine is the separately installed deterministic execution runtime used by Persistra.
You do not need it for factor modeling, portfolio optimization, vectorized backtests, strategy
class development, or scenario construction. Add it when you need order- and fill-level replay.

## Build the executable

Clone Trading Engine beside, rather than inside, the Persistra environment:

```bash
git clone https://github.com/fallblu/trading-engine.git
cd trading-engine
opam switch set .
opam install . --deps-only --with-test --locked
opam exec -- dune build
```

The default development executable is:

```text
trading-engine/_build/default/bin/main.exe
```

Use the repository's own contributor instructions if its build process changes.

## Inspect supported contracts

```bash
./_build/default/bin/main.exe --capabilities
```

Persistra queries capabilities before replay. It requires compatible scenario, journal, strategy
protocol, and execution-model versions. A successful local build alone does not make an
incompatible executable acceptable.

## Keep the boundary explicit

Persistra writes a deterministic JSON or JSON Lines scenario, invokes the executable without a
shell, and imports its JSON Lines audit journal. For external strategies, Trading Engine also
supervises a synchronous strategy subprocess and records the complete protocol transcript.

Trading Engine owns:

- order creation, matching, cancellation, and partial fills;
- target persistence and portfolio-to-quantity sizing;
- risk, margin, fees, borrow costs, corporate actions, and accounting;
- causal event ordering and terminal audit records.

Persistra owns:

- normalized source data and explicit bar clocks;
- research models and target construction;
- Python strategy lifecycle helpers;
- scenario serialization, process preflight, artifact verification, and journal analysis.

Neither project provides broker connectivity or a live-trading deployment system.

## Choose a first replay

Use precomputed target weights when you want to isolate execution behavior from strategy process
behavior. Use an external strategy when decisions must react to fills, rejections, working
orders, or marked portfolio state.

Continue with [Replay a strategy with Trading Engine](../guides/trading-engine.md) for both paths,
or start from the [replay examples](../examples/trading-engine-replay.md).
