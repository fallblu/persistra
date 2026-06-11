import pandas as pd
import pytest

from persistra.core.timeframe import parse_timeframe, timeframe_duration


@pytest.mark.parametrize(
    "tf, mult, unit",
    [("1d", 1, "d"), ("5m", 5, "m"), ("1h", 1, "h"), ("2w", 2, "w")],
)
def test_parse_timeframe(tf, mult, unit):
    assert parse_timeframe(tf) == (mult, unit)


def test_parse_timeframe_rejects_garbage():
    with pytest.raises(ValueError):
        parse_timeframe("banana")


def test_timeframe_duration_orders_finest_first():
    assert timeframe_duration("1h") < timeframe_duration("1d")
    assert timeframe_duration("1d") == pd.Timedelta(days=1)
