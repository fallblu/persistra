# Design reference: simulation and accounting

This page describes the implemented behavior of the accounting core and the two
simulation engines.

## Accounting core

The accounting core is an immutable double-entry journal with exact per-commodity
balancing. Fills, cash flows, fees, accruals, borrow authorization, settlement, splits,
and dividends are recorded as source-idempotent facts; every fact validates its shape at
construction (see `persistra.accounting` model contracts). FIFO long/short lots track
inventory, including cross-zero transitions. Pure transition kernels compute state, and
managed persistence rebuilds normalized projections (positions, cash, NAV) and reconciles
them against the journal.

The complete entitlement/collateral/correction/liquidation design is not yet exposed as a
single policy surface; the borrow, margin, and corporate-action support present is the
subset the simulators exercise.

## Vectorized simulation

The vectorized engine converts precomputed targets into synthetic fractional fills under
a declared capacity/cost policy: commission and slippage in basis points, a fractional
quantum or whole-share rounding, causal participation limits from lagged volume, and an
insufficient-cash action. It posts to the accounting journal, publishes normalized
results, and declares fidelity findings — including `simulation.vectorized.no_orders`,
because it never invents order-lifecycle rows. Its settlement is T0.

## Event simulation

The event engine replays a complete, predeclared set of orders against completed bars
under a total effective-priority clock with a fixed same-timestamp priority contract. An
order cannot consume the bar that precedes its eligibility boundary. The per-bar decision
logic is factored into pure kernels (`persistra.simulation.order_kernels`):

- `eligible_reference` resolves the bar reference price for market, market-on-open,
  market-on-close, limit, stop, and stop-limit orders, applying the OHLC ambiguity policy
  (conservative, reject-ambiguous, or seeded-randomized) to the stop-limit path;
- `unavailable_reference_outcome` and `remainder_outcome` map IOC/DAY time-in-force to the
  correct terminal transition when a bar is not executable or leaves a remainder;
- `fok_capacity_rejected` cancels fill-or-kill orders against causal bar capacity.

Fills attribute spread, slippage, impact, and fees, drive borrow for shorts, and schedule
deterministic T+N market-session settlement (`settlement_sessions=0` settles on the fill
session). Order histories capture creation, acceptance, partial fills, fill, cancellation,
replacement, and expiration.

This is a bounded static bar-order engine. It does not call a stateful strategy, expose
observation/portfolio contexts, resume strategy state, generate forced margin orders, or
process the full corporate-action entitlement surface — these are unavailable rather than
inferred from the presence of event/order tables.

## Fidelity

Both engines publish the same normalized result tables and attach fidelity findings that
travel with results, exports, and reports. Compare vectorized and event economics only
under the restricted common profile, and read the findings before treating differences as
signal.
