# Ecosystem boundaries

Persistra is the Python data and quantitative-research foundation of a planned ecosystem.
Standalone studies, formal trading semantics, and operational trading have separate product
boundaries. This keeps ordinary research use independent of Agda tooling, broker connectivity,
and long-running services.

Only Persistra exists as a released product today. The other products described here are
approved boundaries for future work, not shipped capabilities.

## Products

| Product | Responsibility |
|---|---|
| `persistra` | Provider acquisition, normalized market and economic contracts, research-data persistence, transforms, analysis, reusable research methods, portfolio construction, vectorized backtesting, and generic visualization |
| `persistra-labs` | Standalone studies, narrative demonstrations, experimental integrations, and reproducible research artifacts |
| `persistra-kernel` | Pure Agda domain types, deterministic trading transitions, proofs, canonical trading protocols, and conformance traces |
| `persistra-runtime` | Future durable replay orchestration, journals, checkpoints, broker and streaming adapters, paper and live trading, reconciliation, monitoring, and recovery |

Runtime is intentionally deferred until a supported operational requirement triggers its
creation. Before then, Labs may contain bounded offline integration experiments, but it must
not connect to a paper or live account.

## Ownership

Persistra owns historical and batch providers. Runtime owns broker connections and streaming
feeds because they require connection lifecycle, sequencing, credentials, reconciliation, and
recovery.

Persistra owns normalized observation, dataset, research, target-portfolio, and vectorized-
backtest contracts. Kernel owns order, fill, trading-event, position, accounting, and exact
risk-transition semantics. Runtime owns production mappings between those domains.

Persistra retains raw-response caching and normalized research datasets. Runtime owns
append-only event journals, processed offsets, command deduplication and delivery, checkpoints,
broker state, and execution reconciliation. Kernel performs no network or persistence
operations.

Reusable research calculations and plots belong in Persistra. Study-specific factors, reports,
notebooks, and figures belong in Labs. Execution monitoring and operational alerts belong in
Runtime.

Portfolio construction and vectorized backtesting remain in Persistra. The vectorized
simulator is the fast portfolio-level model. It is a differential-test oracle only under
explicitly matched timing, immediate-fill, tradeability, and linear-cost assumptions; otherwise,
it is a comparison baseline. Kernel owns the pure event reducer. Runtime owns event-source
orchestration, durable replay, and historical, paper, or live adapters.

## Dependency direction

Dependencies point toward stable foundations:

```text
persistra-labs -------> persistra
        |------------> persistra-kernel protocol or executable
        `------------> persistra-runtime, after Runtime exists

persistra-runtime ---> persistra public contracts or exports
        `------------> persistra-kernel protocol or executable
```

Persistra and Kernel do not depend on each other. Their integration crosses explicit,
versioned artifacts. Neither foundation depends on Labs or Runtime. Cyclic repository or
package dependencies are not allowed.

Persistra users do not need Agda or a Kernel executable. Kernel does not depend on Python,
pandas, DuckDB, providers, brokers, or visualization libraries.

Each product versions independently. The Kernel wire protocol has its own explicit version.
Runtime records compatible Persistra and Kernel protocol versions. Labs pins every product,
dataset identity, and executable digest used by a reproducible study.

## Kernel trust boundary

Kernel is a small, pure, total transition engine rather than an operational trading platform.
The conventional host parses bytes into weak raw values. Kernel's safe entry point validates
their semantic constraints and either rejects them or constructs domain values. The transition
engine accepts those validated facts, configuration, and intents. It returns a rejection or a
new state, commands, and audit facts.

Kernel owns exact domain validation, operational accounting, order lifecycle, pure replay,
duplicate-event transition semantics, deterministic command identities, exact pre-trade checks,
small deterministic simulation models, and stated invariants. It does not own data acquisition,
signals, statistical optimization, JSON parsing, storage, networking, clocks, calendars,
concurrency, broker connectivity, credentials, supervision, visualization, or deployment.

Strategies propose intents. Kernel validates proposed orders and state transitions. Once a fill
is validated, nonduplicate, and matched as an observed broker fact, Kernel applies it even when
it creates a limit breach. Risk policy cannot erase a valid fill. An unknown-order, duplicate,
late, correction, or overfill report produces an explicit discrepancy outcome instead of an
ordinary order transition. Runtime journals and reconciles discrepancies without discarding the
external fact.

Every module in the proved Agda core uses safe mode. Foreign-function bindings and the
conventional host remain visibly outside the proof boundary. Proofs can cover properties of
validated state transitions, including determinism, accounting reconciliation, legal order
states, duplicate handling, replay, causality, and encoded limits. They cannot prove that
external events are true, complete, or correctly ordered, or that brokers, networks,
persistence, deployment, or real markets behave correctly. Causality, replay, and duplicate
properties are conditional on the supplied event order, stable identities, and explicit clock
and mark facts. Executable behavior additionally trusts the Agda compiler and backend, GHC, and
the conventional host's field mapping.

## Promotion rules

Code remains in Labs while it is study-specific, exploratory, or coupled to one dataset.

A capability can move from Labs to Persistra when it is provider-neutral, useful to independent
research workflows, has a stable public contract, and includes documentation, deterministic
tests, and explicit missing-data and provenance behavior.

A capability can move from Labs to Kernel when it is a pure deterministic state transition,
belongs to canonical trading state, accounting, execution, or exact risk semantics, depends only
on exact domain values, and has an invariant worth expressing or proving. Formal research
experiments remain in Labs. Network, storage, scheduling, logging, and visualization never move
into Kernel.

A capability belongs in Runtime when it touches an external system, owns durable operational
state, performs recovery or reconciliation, or coordinates commands and events over time.

Promotion moves ownership and tests to the destination. Labs then consumes the released public
interface and deletes its duplicate implementation. A successful demonstration alone does not
broaden Persistra or Kernel.

## Runtime creation triggers

Create Runtime before implementing any of these capabilities:

- a broker or external paper-venue connection;
- a streaming market-data connection;
- an event journal that must survive a process restart;
- durable command idempotency, inbox or outbox processing, or broker reconciliation;
- credentials, account state, or order submission;
- a long-running scheduler or service;
- operational monitoring, alerts, or a kill switch; or
- durable supported event replay rather than a bounded demonstration.

Before Runtime exists, Labs must not hold live credentials or submit orders to an external
paper or live account.

## Protocol ownership

No separate protocol repository is needed initially. Persistra publishes versioned observation
and research-export contracts. Kernel publishes its trading protocol, semantic validators, and
golden traces. Runtime maps between them and records both versions.

Extract a separate protocol product only after multiple independent runtimes need to consume
the trading protocol separately from Kernel releases.
