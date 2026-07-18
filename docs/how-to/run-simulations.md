# Run simulations

Persistra provides two engines with deliberately different fidelity. Both publish the
same normalized result tables and are queried through the engine-independent
`project.services.results` handles.

## Vectorized engine

The vectorized engine converts precomputed portfolio targets into synthetic fractional
fills under a declared capacity/cost policy. Plan and run a
`VectorizedSimulationRequest` through `project.services.simulation.vectorized`. It is a
research approximation: no order book, no intrabar path, T0 settlement, and it records
`simulation.vectorized.no_orders` in its fidelity findings.

Execution policy controls commissions and slippage in basis points, the fractional
quantity quantum or whole-share rounding, causal participation limits, and the
insufficient-cash action (`pro_rata` scaling or `fail`).

## Event engine

The event engine replays a complete, predeclared set of orders against completed bars
under a causal observation clock — an order cannot consume the bar that precedes its
eligibility boundary. Build an `EventSimulationRequest` with `OrderSpec` entries and
run it through `project.services.simulation.event`.

Supported order surface:

- order types: market, market-on-open, market-on-close, limit, stop, stop-limit (bar
  references under the coarse observation clock, not tick claims);
- time in force: `DAY`, `GTC`, `IOC`, `FOK`, plus cancellation and replacement by
  client key;
- causal per-bar capacity from lagged volume and the declared participation limit;
- spread/slippage/impact/fee cost attribution per fill;
- borrow authorization for shorting;
- deterministic T+N market-session settlement proxy (`settlement_sessions=0` settles on
  the fill session);
- OHLC ambiguity policies: conservative, reject-ambiguous, or seeded-randomized.

The per-bar decision logic (reference eligibility, IOC/DAY/FOK outcomes, remainder
handling) lives in the pure kernels of `persistra.simulation.order_kernels`.

The event engine does not call a stateful strategy, expose observation/portfolio
contexts, resume strategy state, generate forced margin orders, or process the full
corporate-action entitlement surface. These capabilities are unavailable rather than
inferred from the presence of event/order tables.

## Choosing an engine

Use the vectorized engine for fast target-level research iteration; use the event
engine when order lifecycle, partial fills, time-in-force semantics, or settlement
timing are material. Compare economics only under the restricted common profile, and
read the fidelity findings attached to every run before treating differences as
signal.
