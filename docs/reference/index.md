# API reference

The reference is organized by public module and supplements generated signatures with exact
normalized schema tables.

| Page | Contents |
|---|---|
| [Models](model.md) | Identity, metadata, normalized result classes, catalogs, and enums |
| [Data access and storage](data.md) | Synthetic data, caching, DuckDB, transforms, and capability protocols |
| [Alpha Vantage](alphavantage.md) | Client construction, namespace methods, transport, and rate limiter |
| [FRED and ALFRED](fred.md) | Series definitions, latest observations, revisions, vintage dates, and transport |
| [Analysis](analysis.md) | General, market, option, and economic calculations |
| [Point-in-time research](research.md) | Vintage selection, factor regressions, feature panels, forward labels, temporal splits, and regime summaries |
| [Portfolio research](portfolio.md) | Optimization, target weights, constraints, rebalance schedules, and vectorized backtesting |
| [Trading Engine integration](trading-engine.md) | Scenario construction, subprocess replay, terminal journal import, and execution analysis |
| [Visualization](visualization.md) | General, market, option, economic, research, portfolio, and execution Matplotlib helpers |
| [Normalized schemas](schemas.md) | Exact frame columns and pandas dtypes |
| [Exceptions](errors.md) | The public exception hierarchy |

Public imports are available from the shortest documented namespace in normal use:

```python
from persistra.analysis import simple_returns
from persistra.data import AlphaVantageClient, DuckDBStore, FredClient, synthetic
from persistra.errors import ProviderError
from persistra.integrations.trading_engine import BarClockPolicy, analyze_execution
from persistra.model import BarSet, InstrumentKind
from persistra.portfolio import PortfolioProblem, backtest_portfolio, optimize_portfolio
from persistra.research import FeatureSpec, build_feature_panel, fit_time_series_factor_model
from persistra.viz import plot_returns
```

Provider namespace classes appear in their provider references because their methods are the
client attributes' callable surface. Most applications construct a client rather than an
individual namespace or transport.

The reference is generated from the installed package during a strict MkDocs build. If a
signature conflicts with prose elsewhere, treat the generated signature as authoritative and
report the documentation mismatch.
