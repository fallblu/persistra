# Portfolio Accounting

`Portfolio` tracks cash, positions, and equity through fills and corporate actions.
By default it enforces cash-account, long-only accounting: fills that would
create negative cash, short positions, gross exposure above 100%, or absolute
net exposure above 100% are rejected before they mutate the portfolio.

## Target Weights

Strategies emit target weights, not orders. The engine compares target weights with the
current portfolio state and creates fills through the configured `ExecutionModel`.

Positive weights are long exposure. Negative weights are short exposure when your
execution and portfolio assumptions permit it. Pipeline risk constraints project desired
target weights before order generation; portfolio policy is the final fill-time accounting
guardrail after fill price and commission are known.

## Portfolio Policy

Configure fill-time accounting with `PortfolioPolicy`:

```python
from persistra import Portfolio, PortfolioPolicy

portfolio = Portfolio(
    initial_capital=1_000_000.0,
    policy=PortfolioPolicy(
        allow_short=False,
        max_gross_exposure=1.0,
        max_net_exposure=1.0,
        min_cash=0.0,
    ),
)
```

Invalid orders are rejected by default, not clipped or partially filled. Rejections do not
appear in `result.trades` because that table contains executed fills only.

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

## Rejections

Rejected fills are auditable in `result.diagnostics` with portfolio-specific names:

- `portfolio_order_rejected`
- `portfolio_rejection_constraint`
- `portfolio_requested_quantity`
- `portfolio_post_cash`
- `portfolio_post_gross_exposure`
- `portfolio_post_net_exposure`

`portfolio_rejection_constraint` is a numeric reason code from `PortfolioConstraint`.

## Corporate Actions

Split and dividend records are loaded separately from bars. The engine applies corporate
actions before processing that session's bars.
