# Portfolio Accounting

`Portfolio` tracks cash, positions, and equity through fills and corporate actions.

## Target Weights

Strategies emit target weights, not orders. The engine compares target weights with the
current portfolio state and creates fills through the configured `ExecutionModel`.

Positive weights are long exposure. Negative weights are short exposure when your
execution and portfolio assumptions permit it.

## Equity Curve

`result.equity_curve` includes:

- `equity`
- `cash`
- `gross_exposure`
- `net_exposure`

Gross exposure is the sum of absolute position exposures divided by equity. Net exposure
is signed exposure divided by equity.

## Positions

`result.positions` is a sparse weight log. Symbols with zero shares are omitted. Treat it
as a tradeable-state audit trail rather than a dense holdings matrix.

## Trades

`result.trades` records executed fills. Columns include `order_timestamp`, `timestamp`,
`symbol`, `quantity`, `fill_price`, and `commission`. `order_timestamp` is when the
strategy generated the order; `timestamp` is when the fill occurred.

## Corporate Actions

Split and dividend records are loaded separately from bars. The engine applies corporate
actions before processing that session's bars.
