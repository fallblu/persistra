# Snippet cookbook

Use this page when you know the task and want a compact pattern. Synthetic examples are
deterministic and offline. Provider examples require an Alpha Vantage key and can make
network requests.

## Synthetic data

### Create daily bars

```python
from persistra.data import synthetic

bars = synthetic.bars(
    "DEMO",
    periods=90,
    seed=7,
    interval="daily",
    adjusted=False,
)

print(bars.frame[["date", "open", "high", "low", "close", "volume"]])
```

### Create empty bars with the exact schema

```python
from persistra.data import synthetic

empty = synthetic.bars("EMPTY", periods=0)

assert empty.frame.empty
print(empty.frame.dtypes)
```

### Create pair and index bars

```python
from persistra.data import synthetic
from persistra.model import InstrumentKind

fx = synthetic.bars(
    "EUR/USD",
    kind=InstrumentKind.FIAT_PAIR,
    seed=1,
)
crypto = synthetic.bars(
    "BTC/USD",
    kind=InstrumentKind.CRYPTO_PAIR,
    seed=2,
)
index = synthetic.bars(
    "INDEX",
    kind=InstrumentKind.INDEX,
    seed=3,
)
```

### Create latest quotes

```python
from persistra.data import synthetic

quotes = synthetic.quotes(("AAA", "BBB", "CCC"))
print(quotes.frame[["provider_symbol", "price", "volume"]])
```

### Create top-of-book snapshots

```python
from persistra.data import synthetic

book = synthetic.top_of_book(("AAA", "BBB"))
print(book.frame[["provider_symbol", "bid_price", "ask_price"]])
```

### Create a historical option chain

```python
from datetime import date

from persistra.data import synthetic

chain = synthetic.option_chain(
    "DEMO",
    chain_date=date(2025, 1, 17),
)

print(chain.contracts)
print(chain.observations)
```

### Create commodity and economic series

```python
from persistra.data import synthetic
from persistra.model import SeriesKind

commodity = synthetic.series(
    "WTI",
    periods=24,
    frequency="monthly",
    kind=SeriesKind.COMMODITY,
    unit="USD per barrel",
)
economic = synthetic.series(
    "CPI",
    periods=24,
    frequency="monthly",
    kind=SeriesKind.ECONOMIC,
    unit="index",
)
```

### Create scalar quotes

```python
from persistra.data import synthetic

fx_rate = synthetic.exchange_rate("EUR", "USD")
crypto_rate = synthetic.exchange_rate("BTC", "USD", crypto=True)
gold = synthetic.commodity_spot("gold")

print(fx_rate.exchange_rate)
print(crypto_rate.exchange_rate)
print(gold.value, gold.unit)
```

### Create reference results

```python
from persistra.data import synthetic

matches = synthetic.search("DEMO")
markets = synthetic.market_status()
indices = synthetic.index_catalog()

print(matches.frame)
print(markets.frame)
print(indices.frame)
```

### Create an observed Treasury curve set

```python
from persistra.data import synthetic

treasuries = synthetic.treasury_curve(
    maturities=("3month", "2year", "10year", "30year"),
    periods=12,
)

for series in treasuries:
    print(series.definition.maturity, series.frame["value"].iloc[-1])
```

## Identity and provenance

### Generate provider-scoped identities

```python
from persistra.model import (
    InstrumentKind,
    provider_instrument_id,
    provider_series_id,
)

instrument_id = provider_instrument_id(
    "my_provider",
    InstrumentKind.EQUITY,
    "DEMO",
)
series_id = provider_series_id(
    "my_provider",
    "CPI",
    "monthly",
)

print(instrument_id, series_id)
```

### Build an explicit provider-symbol catalog

```python
from persistra.model import Catalog, Instrument, InstrumentKind, ProviderSymbol

instrument = Instrument("demo-company", InstrumentKind.EQUITY, "Demo Company")
mapping = ProviderSymbol(
    provider="my_provider",
    kind=InstrumentKind.EQUITY,
    symbol="DEMO",
    instrument_id=instrument.instrument_id,
)

catalog = Catalog()
catalog.add_instrument(instrument)
catalog.map_provider_symbol(mapping)

assert catalog.resolve("my_provider", "equity", "DEMO") == instrument
```

### Inspect result metadata

```python
from persistra.data import synthetic

result = synthetic.bars("DEMO")
metadata = result.metadata

print(metadata.provider)
print(metadata.operation)
print(metadata.request_parameters)
print(metadata.retrieved_at)
print(metadata.provider_as_of)
print(metadata.entitlement)
print(metadata.cache_status)
print(metadata.diagnostics)
```

## Reshaping and alignment

### Pivot bar fields

```python
from persistra.data import pivot_bars, synthetic

first = synthetic.bars("FIRST", seed=1)
second = synthetic.bars("SECOND", seed=2)

close = pivot_bars([first, second], field="close")
volume = pivot_bars([first, second], field="volume")
```

### Pivot scalar series

```python
from persistra.data import pivot_series, synthetic

first = synthetic.series("FIRST", frequency="monthly")
second = synthetic.series("SECOND", frequency="monthly")

wide = pivot_series([first, second])
```

### Align on common labels

```python
import pandas as pd

from persistra.data import align

left = pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-01-01", "2025-01-02"]))
right = pd.Series([3.0, 4.0], index=pd.to_datetime(["2025-01-02", "2025-01-03"]))

aligned = align({"left": left, "right": right}, how="intersection")
```

### Preserve all labels

```python
import pandas as pd

from persistra.data import align

left = pd.Series([1.0, 2.0], index=pd.to_datetime(["2025-01-01", "2025-01-02"]))
right = pd.Series([3.0, 4.0], index=pd.to_datetime(["2025-01-02", "2025-01-03"]))

aligned = align({"left": left, "right": right}, how="union")
assert aligned["left"].isna().sum() == 1
assert aligned["right"].isna().sum() == 1
```

### Perform a bounded as-of join

```python
import pandas as pd

from persistra.data import asof_align

left = pd.DataFrame(
    {"observation": [1.0, 2.0]},
    index=pd.to_datetime(["2025-01-02T14:31:00Z", "2025-01-02T14:36:00Z"]),
)
right = pd.DataFrame(
    {"signal": [0.1, 0.2]},
    index=pd.to_datetime(["2025-01-02T14:30:00Z", "2025-01-02T14:35:00Z"]),
)

matched = asof_align(
    left,
    right,
    maximum_staleness=pd.Timedelta(minutes=2),
)
```

### Resample selected intraday sessions

```python
from persistra.data import resample_bars, synthetic

intraday = synthetic.bars(
    "DEMO",
    periods=120,
    interval="5min",
    session="regular",
)
hourly = resample_bars(
    intraday,
    frequency="1h",
    timezone="America/New_York",
    sessions={"regular"},
)
```

## General analysis

### Calculate return variants

```python
from persistra.analysis import log_returns, simple_returns
from persistra.data import pivot_bars, synthetic

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
simple = simple_returns(prices)
logged = log_returns(prices)
```

### Rebase and compound

```python
from persistra.analysis import cumulative_returns, rebase, simple_returns
from persistra.data import pivot_bars, synthetic

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
rebased = rebase(prices, base=100)
returns = simple_returns(prices).dropna()
compounded = cumulative_returns(returns)
```

### Calculate drawdowns

```python
from persistra.analysis import drawdowns, simple_returns
from persistra.data import pivot_bars, synthetic

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
returns = simple_returns(prices).dropna()
underwater = drawdowns(returns)
```

### Calculate rolling volatility

```python
from persistra.analysis import rolling_volatility, simple_returns
from persistra.data import pivot_bars, synthetic

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
returns = simple_returns(prices)
volatility = rolling_volatility(
    returns,
    window=20,
    periods_per_year=252,
)
```

### Summarize coverage and statistics

```python
from persistra.analysis import coverage_summary, summary_statistics
from persistra.data import pivot_bars, synthetic

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
coverage = coverage_summary(prices)
statistics = summary_statistics(prices)
```

### Calculate covariance and correlation

```python
from persistra.analysis import correlation_matrix, covariance_matrix, simple_returns
from persistra.data import pivot_bars, synthetic

prices = pivot_bars(
    [synthetic.bars("FIRST", seed=1), synthetic.bars("SECOND", seed=2)],
    field="close",
)
returns = simple_returns(prices)
covariance = covariance_matrix(returns)
correlation = correlation_matrix(returns)
```

## Market analysis

### Calculate bid-ask measures

```python
from persistra.analysis import absolute_spread, midprice, relative_spread
from persistra.data import synthetic

book = synthetic.top_of_book(("AAA", "BBB"))
midpoints = midprice(book)
absolute = absolute_spread(book)
relative = relative_spread(book)
```

### Calculate ranges and volume summary

```python
from persistra.analysis import bar_range, true_range, volume_summary
from persistra.data import synthetic

bars = synthetic.bars("DEMO")
ranges = bar_range(bars)
true_ranges = true_range(bars)
volume = volume_summary(bars)
```

### Describe observed sessions

```python
from persistra.analysis import session_coverage
from persistra.data import synthetic

bars = synthetic.bars("DEMO")
coverage = session_coverage(bars)
```

## Historical option analysis

### Filter contracts

```python
from persistra.analysis import filter_chain
from persistra.data import synthetic
from persistra.model import OptionType

chain = synthetic.option_chain("DEMO")
calls = filter_chain(
    chain,
    option_type=OptionType.CALL,
    minimum_strike=95,
    maximum_strike=105,
)
```

### Calculate moneyness and value components

```python
from persistra.analysis import intrinsic_value, moneyness, time_value
from persistra.data import synthetic

chain = synthetic.option_chain("DEMO")
ratios = moneyness(chain, underlying_price=102.0)
intrinsic = intrinsic_value(chain, underlying_price=102.0)
extrinsic = time_value(chain, underlying_price=102.0, option_value="mark")
```

### Prepare a volatility smile

```python
from persistra.analysis import implied_volatility_smile
from persistra.data import synthetic

chain = synthetic.option_chain("DEMO")
expiration = chain.contracts["expiration"].dt.date.min()
smile = implied_volatility_smile(
    chain,
    expiration=expiration,
    option_type="call",
)
```

### Prepare a supplied Greek profile

```python
from persistra.analysis import greek_profile
from persistra.data import synthetic

chain = synthetic.option_chain("DEMO")
delta = greek_profile(chain, "delta", option_type="call")
```

## Economic analysis

### Calculate lagged growth

```python
from persistra.analysis import growth_rate
from persistra.data import pivot_series, synthetic

series = synthetic.series("CPI", periods=36)
levels = pivot_series([series])
growth = growth_rate(levels, lag=12)
```

### Convert rate changes to basis points

```python
from persistra.analysis import basis_point_change
from persistra.data import pivot_series, synthetic

rates = pivot_series(synthetic.treasury_curve(periods=12))
changes = basis_point_change(rates, rate_unit="percent")
```

### Build a curve and curve history

```python
from persistra.analysis import yield_curve, yield_curve_history
from persistra.data import synthetic

treasuries = synthetic.treasury_curve(periods=12)
period_label = treasuries[0].frame["period_label"].iloc[-1]
curve = yield_curve(treasuries, period_label=period_label)
history = yield_curve_history(treasuries)
```

## Visualization

### Use caller-owned axes

```python
import matplotlib.pyplot as plt

from persistra.data import pivot_bars, synthetic
from persistra.viz import plot_series

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
figure, ax = plt.subplots(figsize=(8, 4))
plot_series(prices, ax=ax, ylabel="Price")
ax.set_title("Demo")
figure.tight_layout()
```

### Plot candlesticks

```python
from persistra.data import synthetic
from persistra.viz import plot_candlesticks

bars = synthetic.bars("DEMO", periods=30)
axes = plot_candlesticks(bars)
axes.price.set_title("Synthetic bars")
```

### Save a plot

```python
from persistra.data import pivot_bars, synthetic
from persistra.viz import plot_rebased

prices = pivot_bars([synthetic.bars("DEMO")], field="close")
ax = plot_rebased(prices)
ax.figure.savefig("rebased.png", dpi=150, bbox_inches="tight")
```

## DuckDB storage

### Save and load bars

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore, synthetic

bars = synthetic.bars("DEMO")

with TemporaryDirectory() as directory:
    path = Path(directory) / "research.duckdb"
    with DuckDBStore.create(path) as store:
        store.save(bars)
        restored = store.load_bars(bars.instrument.instrument_id)

    assert restored is not None
```

### Query an inclusive date range

```python
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore, synthetic

bars = synthetic.bars("DEMO")

with TemporaryDirectory() as directory:
    path = Path(directory) / "research.duckdb"
    with DuckDBStore.create(path) as store:
        store.save(bars)
        frame = store.query_bars(
            bars.instrument.instrument_id,
            start=date(2025, 1, 10),
            end=date(2025, 1, 20),
        )
```

### Load by retrieval-time cutoff

```python
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore, synthetic

cutoff = datetime(2025, 2, 1, tzinfo=UTC)
bars = synthetic.bars("DEMO")

with TemporaryDirectory() as directory:
    path = Path(directory) / "research.duckdb"
    with DuckDBStore.create(path) as store:
        store.save(bars)
        result = store.load_bars(
            bars.instrument.instrument_id,
            retrieved_before=cutoff,
        )

assert result is not None
```

## Alpha Vantage acquisition

### Construct a client from the environment

```python
from pathlib import Path

from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env(
    cache_directory=Path(".cache/persistra"),
    requests_per_minute=150,
    timeout=30,
)
```

### Acquire adjusted daily security bars

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env()
bars = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    adjusted=True,
    outputsize="full",
)
```

### Acquire a delayed latest quote

```python
from persistra.data import AlphaVantageClient
from persistra.model import EntitlementMode

client = AlphaVantageClient.from_env()
quote = client.quotes.latest(
    "IBM",
    entitlement=EntitlementMode.DELAYED,
)
```

### Acquire an economic series

```python
from persistra.data import AlphaVantageClient

client = AlphaVantageClient.from_env()
treasury = client.economics.series(
    "TREASURY_YIELD",
    frequency="daily",
    maturity="10year",
)
```

### Require cached offline data

```python
from persistra.data import AlphaVantageClient
from persistra.model import InstrumentKind

client = AlphaVantageClient.from_env()
bars = client.securities.bars(
    "IBM",
    kind=InstrumentKind.EQUITY,
    interval="daily",
    offline=True,
)
```

## Error handling

### Handle provider outcomes separately

```python
from persistra.errors import NoDataError, ProviderError

try:
    result = acquire_result()
except NoDataError:
    result = None
except ProviderError as error:
    raise RuntimeError("provider acquisition failed") from error
```

### Handle an offline cache miss

```python
from persistra.errors import CacheError

try:
    result = acquire_offline_result()
except CacheError as error:
    raise RuntimeError("the required raw response is not cached") from error
```

### Inspect schema diagnostics

```python
from persistra.data import synthetic

result = synthetic.bars("DEMO")

for diagnostic in result.metadata.diagnostics:
    print(diagnostic.field, diagnostic.message)
```

For the reasoning behind these patterns, use the tutorials and how-to guides. For complete
signatures, see the [API reference](../reference/index.md).
