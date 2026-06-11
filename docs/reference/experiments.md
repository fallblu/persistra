# experiments

Use `grid_search`, `random_search`, and `bayes_search` for ordinary parameter sweeps.
Use `walk_forward` for fixed-parameter train/test windows. Use
`walk_forward_grid_search` when each fold should select parameters on its training
window before evaluating the next out-of-sample test window.

::: persistra.experiments
