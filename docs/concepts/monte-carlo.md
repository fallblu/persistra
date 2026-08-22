# Monte Carlo research

Persistra treats Monte Carlo analysis as an explicit research boundary. An experiment combines a
path model, output axes, time increments, a path count, a root seed, and scalar path metrics. The
runner supplies managed random generators and returns paths, summaries, confidence intervals,
convergence diagnostics, and portable provenance.

## Reproducibility contract

Every path has a random stream derived only from the experiment root seed and its zero-based path
number. Changing the batch size, switching between serial and threaded execution, or extending
the total path count does not change an existing path prefix. The runner never reads or mutates
NumPy's global random state.

Execution controls are deliberately absent from experiment identity. A manifest records the
model, model parameters, axes, metrics, evaluator, seed, path count, retention policy, confidence
level, convergence checkpoints, and runtime versions. Execution diagnostics separately record
the backend, worker count, batch size, and batch count.

## Component boundaries

`MonteCarloModel`, `Distribution`, `PathMetric`, and `PathEvaluator` are structural protocols.
Custom implementations need no registration or base class. Models receive one managed NumPy
generator and the validated time-step array. Metrics return one finite scalar. Evaluators return
a declared, bounded mapping of finite scalar outcomes.

Built-in models cover correlated normal returns, geometric Brownian motion, and joint moving-block
bootstrap sampling. Built-in distributions support normal, Student-t, empirical, and multivariate
normal draws for custom models. Calibration is a separate, pure call so the caller chooses the
sample, return definition, frequency, annualization, and initial state.

## Memory and execution

Path generation is batched. `retain_paths=False` avoids the three-dimensional path result while
still retaining one scalar row per path for metrics, summaries, confidence intervals, and
convergence. A `PathEvaluator` runs inside each batch, so portfolio evaluation does not retain a
`BacktestResult` for every scenario. Use retained paths only when later path inspection or a new
post-run evaluator is required.

Threading changes scheduling, not random streams or result ordering. It is an execution option,
not a promise of faster numerical work for every model.

## Deliberate non-goals

Monte Carlo research does not acquire data, choose a historical sample, infer a calibration
window, persist experiments, or register models globally. It does not manufacture a `BarSet` from
close-only simulated prices. A normalized bar contract needs open, high, low, close, volume,
identity, and provenance semantics that a price-path model cannot honestly supply.

`persistra.data.synthetic` remains deterministic fixture data for tests and offline examples. It
is not a calibrated scenario source. Monte Carlo paths remain ordinary arrays and frames with
explicit model semantics.

Portfolio evaluation uses the vectorized portfolio backtester and therefore models portfolio
rebalances, holdings, returns, and linear costs. It is not order-level execution. To study causal
orders, fills, or exchange behavior, select explicit scenarios and pass them through the separate
Trading Engine integration.
