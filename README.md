# Persistra

Persistra is a Python toolkit for reproducible, point-in-time financial research. It provides
normalized market and economic data, local DuckDB storage, leakage-aware research tools,
portfolio construction, backtesting, and adapters for Trading Engine v1.

```bash
uv add persistra
```

```python
from persistra.analysis import simple_returns
from persistra.data import synthetic

bars = synthetic.bars(periods=252)
prices = bars.frame.set_index("timestamp")[["close"]]
daily_returns = simple_returns(prices)
```

Use the [documentation](https://fallblu.github.io/persistra/) for installation, data providers,
research workflows, portfolio tools, and the Trading Engine integration. The
[API reference](https://fallblu.github.io/persistra/reference/) documents the complete public
surface.

Persistra supports Python 3.12 or later on Linux. It is a research library, not a broker
connection or live-trading system.
