# Tutorial: explore historical options

This tutorial explores one deterministic historical option chain. You will inspect its two
normalized tables, filter contracts, calculate moneyness and value components, prepare
implied-volatility data, and create plots.

Persistra analyzes observed values. It does not price contracts, calculate Greeks, infer an
underlying price, or fit a volatility surface.

## 1. Create a chain

```python
from datetime import date

from persistra.data import synthetic

chain = synthetic.option_chain(
    "DEMO",
    chain_date=date(2025, 1, 17),
)

print(chain.underlying_instrument_id)
print(chain.chain_date)
print(chain.contracts.head())
print(chain.observations.head())
```

An `OptionChain` separates stable contract terms from dated observations:

- `contracts` contains expiration, strike, option type, and provider identity.
- `observations` contains historical prices, sizes, activity, implied volatility, and
  provider-supplied Greeks.
- `metadata` contains acquisition provenance for the result.

This avoids repeating contract terms in every observation while keeping both frames exact
and independently understandable.

## 2. Summarize available contracts

```python
from persistra.analysis import chain_summary, days_to_expiration

summary = chain_summary(chain)
calendar_time = days_to_expiration(chain)

print(summary)
print(calendar_time.head())
```

Days to expiration are whole calendar days from the chain date. They are not trading days or
a year-fraction convention.

## 3. Filter the chain

Select calls within a strike range:

```python
from persistra.analysis import filter_chain
from persistra.model import OptionType

calls = filter_chain(
    chain,
    option_type=OptionType.CALL,
    minimum_strike=95,
    maximum_strike=105,
)

print(calls.contracts[["expiration", "strike", "option_type"]])
```

The result remains a validated `OptionChain`; its observations are restricted to the
remaining contract IDs. You can also filter by one expiration or an explicit collection of
contract IDs.

## 4. Supply the underlying price explicitly

Moneyness and value decomposition require a positive underlying price. The chain does not
fetch, backfill, or infer one.

```python
from persistra.analysis import intrinsic_value, moneyness, time_value

underlying_price = 102.0

moneyness_frame = moneyness(chain, underlying_price=underlying_price)
intrinsic = intrinsic_value(chain, underlying_price=underlying_price)
extrinsic = time_value(
    chain,
    underlying_price=underlying_price,
    option_value="mark",
)

print(moneyness_frame.head())
print(intrinsic.head())
print(extrinsic.head())
```

Moneyness is spot divided by strike for both calls and puts. Interpret the ratio together
with `option_type`. Intrinsic value applies the correct call or put payoff, and time value
subtracts it from the selected observed value field.

## 5. Inspect quoted spreads

```python
from persistra.analysis import (
    option_absolute_spread,
    option_midprice,
    option_relative_spread,
)

midpoints = option_midprice(chain)
absolute = option_absolute_spread(chain)
relative = option_relative_spread(chain)

print(midpoints.head())
print(absolute.head())
print(relative.head())
```

These functions preserve missing bid or ask values. A missing side does not become zero.

## 6. Prepare volatility and Greek profiles

Choose one observed expiration:

```python
from persistra.analysis import (
    greek_profile,
    implied_volatility_smile,
    implied_volatility_surface,
)

expiration = chain.contracts["expiration"].dt.date.min()

smile = implied_volatility_smile(
    chain,
    expiration=expiration,
    option_type=OptionType.CALL,
)
surface = implied_volatility_surface(chain)
delta = greek_profile(
    chain,
    "delta",
    expiration=expiration,
    option_type=OptionType.CALL,
)

print(smile)
print(surface)
print(delta)
```

The surface is a preparation table of observed points. Missing strike-expiration cells remain
missing. Greek profiles use values supplied by the provider; Persistra does not calculate
them from a pricing model.

## 7. Plot observed option data

```python
import matplotlib.pyplot as plt

from persistra.viz import (
    plot_greek_profile,
    plot_implied_volatility_smile,
    plot_implied_volatility_surface,
    plot_option_chain_prices,
)

figure, axes = plt.subplots(2, 2, figsize=(12, 8))

plot_option_chain_prices(chain, ax=axes[0, 0])
plot_implied_volatility_smile(
    chain,
    expiration=expiration,
    option_type="call",
    ax=axes[0, 1],
)
plot_implied_volatility_surface(chain, ax=axes[1, 0])
plot_greek_profile(
    chain,
    "delta",
    expiration=expiration,
    option_type="call",
    ax=axes[1, 1],
)

figure.tight_layout()
plt.show()
```

The heatmap does not interpolate across missing observations.

## 8. Store and restore the chain

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.data import DuckDBStore

with TemporaryDirectory() as directory:
    path = Path(directory) / "options.duckdb"
    with DuckDBStore.create(path) as store:
        store.save(chain)
        restored = store.load_options(
            chain.underlying_instrument_id,
            chain.chain_date,
        )

    assert restored is not None
    assert restored.contracts.equals(chain.contracts)
    assert restored.observations.equals(chain.observations)
```

For provider-backed chains, see the historical-options section of
[Acquire data](../guides/acquisition.md).
