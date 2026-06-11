# Metrics and Visualization

Metrics and visuals operate on `Result`, so they can be used with single runs,
parameter-sweep winners, walk-forward folds, or loaded artifacts.

## Metrics

Benchmark-free helpers summarize standalone performance:

- annualized return
- annualized volatility
- Sharpe and Sortino
- max drawdown and Calmar
- hit rate
- VaR and CVaR
- turnover and exposure statistics

Benchmark-aware helpers add:

- alpha
- beta
- active annualized return
- tracking error
- information ratio

## Visualization

Plot helpers return Plotly figures. They cover performance, drawdowns, exposure,
weights, returns heatmaps, trade PnL, market charts, and recorded diagnostics.

## Research Outputs

Experiment helpers build on the same result shape. A grid-search run, a walk-forward
fold, and a saved artifact can all be summarized with the same metrics and visual tools.
