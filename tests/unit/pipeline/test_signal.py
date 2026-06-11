import pandas as pd
import pytest

from persistra.pipeline.signal import LinearSignal


def test_linear_signal_weighted_sum_of_columns():
    features = pd.DataFrame({"mom": [1.0, 2.0], "val": [3.0, 1.0]}, index=["A", "B"])
    out = LinearSignal({"mom": 2.0, "val": 1.0}).combine(features)
    assert out["A"] == pytest.approx(2 * 1.0 + 1 * 3.0)
    assert out["B"] == pytest.approx(2 * 2.0 + 1 * 1.0)


def test_linear_signal_skips_missing_columns():
    features = pd.DataFrame({"mom": [1.0]}, index=["A"])
    out = LinearSignal({"mom": 1.0, "absent": 5.0}).combine(features)
    assert out["A"] == pytest.approx(1.0)
