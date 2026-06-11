import pandas as pd
import pytest

from persistra.core.result import Result
from persistra.metrics.realized import realized_pnl


def _result(trades: pd.DataFrame) -> Result:
    return Result(equity_curve=pd.DataFrame(), trades=trades, positions=pd.DataFrame(), meta={})


def test_realized_round_trip_long():
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-01-03", "2022-01-04"]),
            "symbol": ["AAA", "AAA"],
            "quantity": [10.0, -10.0],
            "fill_price": [100.0, 110.0],
            "commission": [0.0, 0.0],
        }
    )
    pnl = realized_pnl(_result(trades))
    assert len(pnl) == 1
    assert pnl.iloc[0] == pytest.approx(100.0)  # (110-100)*10


def test_realized_empty_when_no_closing_trade():
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-01-03"]),
            "symbol": ["AAA"],
            "quantity": [10.0],
            "fill_price": [100.0],
            "commission": [0.0],
        }
    )
    assert realized_pnl(_result(trades)).empty


def test_realized_commission_reduces_pnl():
    trades = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2022-01-03", "2022-01-04"]),
            "symbol": ["AAA", "AAA"],
            "quantity": [10.0, -10.0],
            "fill_price": [100.0, 110.0],
            "commission": [5.0, 5.0],
        }
    )
    pnl = realized_pnl(_result(trades))
    # gross 100 minus per-unit commissions (0.5+0.5)*10 = 10
    assert pnl.iloc[0] == pytest.approx(90.0)
