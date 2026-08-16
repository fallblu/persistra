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
| [Point-in-time research](research.md) | Features, labels, factor regressions, factor forecasts and attribution, splits, and evaluation |
| [Portfolio research](portfolio.md) | Objectives, constraints, solver boundary, rolling optimization, target construction, and backtesting |
| [Trading Engine integration](trading-engine.md) | Strategy lifecycle and composition, scenarios, subprocess replay, journals, and execution analysis |
| [Visualization](visualization.md) | General, market, option, economic, research, portfolio, and execution Matplotlib helpers |
| [Normalized schemas](schemas.md) | Exact frame columns and pandas dtypes |
| [Exceptions](errors.md) | The public exception hierarchy |

Public imports are available from the shortest documented namespace in normal use:

```python
from persistra.analysis import simple_returns
from persistra.data import AlphaVantageClient, DuckDBStore, FredClient, synthetic
from persistra.errors import ProviderError
from persistra.integrations.trading_engine import BaseStrategy, CompositeStrategy, run_scenario
from persistra.model import BarSet, InstrumentKind
from persistra.portfolio import PortfolioProblem, backtest_portfolio, optimize_portfolio_path
from persistra.research import build_factor_portfolio_forecast, fit_time_series_factor_model
from persistra.viz import plot_returns
```

Provider namespace classes appear in their provider references because their methods are the
client attributes' callable surface. Most applications construct a client rather than an
individual namespace or transport.

The reference is generated from the installed package during a strict MkDocs build. If a
signature conflicts with prose elsewhere, treat the generated signature as authoritative and
report the documentation mismatch.
