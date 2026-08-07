# Getting started

Install Persistra in a Python 3.12 or later environment.

```python
from persistra.data import synthetic

bars = synthetic.bars("DEMO", periods=30)
print(bars.frame[["date", "close"]].tail())
```

Synthetic results use the same normalized contracts as provider data. They require no
credentials or network access.
