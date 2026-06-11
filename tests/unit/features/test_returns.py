import math

import numpy as np
import pytest

from persistra.features.returns import CumReturn, LogReturn, SimpleReturn, VolScaledReturn


def test_log_return_values():
    out = LogReturn().transform([100.0, 110.0, 121.0])
    assert out.shape == (2, 1)
    assert out[0, 0] == pytest.approx(math.log(110 / 100))
    assert out[1, 0] == pytest.approx(math.log(121 / 110))


def test_log_return_empty_for_single_row():
    assert LogReturn().transform([100.0]).shape == (0, 1)


def test_simple_return_values():
    out = SimpleReturn().transform([100.0, 110.0])
    assert out[0, 0] == pytest.approx(0.10)


def test_cum_return_sums_log_returns():
    out = CumReturn(input_is_price=True).transform([100.0, 110.0, 121.0])
    assert out.shape == (1, 1)
    assert out[0, 0] == pytest.approx(math.log(121 / 100))


def test_cum_return_skip_last_drops_recent():
    # skip_last=1 drops the most recent return.
    out = CumReturn(skip_last=1, input_is_price=True).transform([100.0, 110.0, 121.0])
    assert out[0, 0] == pytest.approx(math.log(110 / 100))


def test_cum_return_rejects_negative_skip():
    with pytest.raises(ValueError):
        CumReturn(skip_last=-1)


# ---------------------------------------------------------------------------
# VolScaledReturn
# ---------------------------------------------------------------------------


def test_vol_scaled_return_output_shape():
    # Price array of shape (T, n_symbols) → output shape (T-1, n_symbols).
    rng = np.random.default_rng(0)
    prices = rng.standard_normal((10, 3)) * 0.01 + 100.0
    out = VolScaledReturn(window=3).transform(prices)
    assert out.shape == (9, 3)


def test_vol_scaled_return_zero_vol_guard_and_finite_value():
    # Construct a single-column input where the first window of returns is all
    # zeros (constant prices → vol == 0) and then prices increase so the last
    # return has non-zero vol.
    #
    # Prices: [5, 5, 5, 6]  (window=2)
    # Log returns: [0, 0, log(6/5)]
    # Rolling std(window=2):
    #   row 0: NaN  (window not filled)
    #   row 1: std([0, 0]) == 0.0  → guard returns nan
    #   row 2: std([0, log(6/5)]) > 0  → finite
    prices = np.array([[5.0], [5.0], [5.0], [6.0]])
    out = VolScaledReturn(window=2).transform(prices)

    assert out.shape == (3, 1)
    assert np.isnan(out[0, 0])  # window not yet filled → NaN
    assert np.isnan(out[1, 0])  # vol == 0 → zero-vol guard fires
    assert math.isfinite(out[2, 0])  # non-zero vol → finite

    # Independent computation of the expected finite value.
    import pandas as pd

    log_ret = float(np.log(6.0 / 5.0))
    rolling_std = float(pd.Series([0.0, log_ret]).std())  # ddof=1, pandas default
    expected = log_ret / rolling_std  # == sqrt(2) ≈ 1.4142…
    assert out[2, 0] == pytest.approx(expected, rel=1e-9)
