# Persistra

Persistra is a typed Python toolkit for acquiring, storing, exploring, and plotting
primary market and economic data. Version 4 uses provider-neutral contracts and starts
with broad Alpha Vantage support.

The rewrite is in progress on this branch. The stable foundation currently provides
catalog identities, normalized pandas contracts, capability protocols, and deterministic
synthetic data.

```python
from persistra.data import synthetic

result = synthetic.bars("DEMO")
print(result.frame.tail())
```

Persistra requires Python 3.12 or later. See the [documentation](docs/index.md) and the
[4.0 roadmap](ROADMAP-4.0.0.md).
