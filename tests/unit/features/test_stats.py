"""Tests for persistra.features.stats — rolling statistics transformers."""

from __future__ import annotations

import math
from typing import cast

import numpy as np
import pytest

from persistra.features.stats import (
    RollingKurt,
    RollingMean,
    RollingQuantile,
    RollingSkew,
    RollingStd,
    RollingZScore,
)

# ---------------------------------------------------------------------------
# RollingMean
# ---------------------------------------------------------------------------


def test_rolling_mean_shape_and_value():
    # Window of 3 over 5 values: first two rows are NaN, then the mean is
    # independently computed.
    X = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = RollingMean(window=3).transform(X)
    assert out.shape == (5, 1)
    # Rows 0 and 1 should be NaN (window not yet filled)
    assert math.isnan(out[0, 0])
    assert math.isnan(out[1, 0])
    # Row 2: mean(1, 2, 3) = 2.0
    assert out[2, 0] == pytest.approx(2.0)
    # Row 4: mean(3, 4, 5) = 4.0
    assert out[4, 0] == pytest.approx(4.0)


def test_rolling_mean_fit_is_noop():
    t = RollingMean(window=2)
    assert t.fit([1.0, 2.0]) is t


# ---------------------------------------------------------------------------
# RollingStd
# ---------------------------------------------------------------------------


def test_rolling_std_shape_and_value():
    # Window of 3; ddof=1 (pandas default)
    X = [2.0, 4.0, 6.0, 8.0]
    out = RollingStd(window=3).transform(X)
    assert out.shape == (4, 1)
    assert math.isnan(out[0, 0])
    assert math.isnan(out[1, 0])
    # Row 2: std([2, 4, 6], ddof=1) = 2.0
    expected = float(np.std([2.0, 4.0, 6.0], ddof=1))
    assert out[2, 0] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# RollingZScore
# ---------------------------------------------------------------------------


def test_rolling_zscore_first_valid_row_is_zero():
    # At the first full window the value equals the mean, so z-score is 0.
    X = [5.0, 5.0, 5.0, 10.0]
    out = RollingZScore(window=3).transform(X)
    assert out.shape == (4, 1)
    assert math.isnan(out[0, 0])
    assert math.isnan(out[1, 0])
    # Row 2: all values equal → std=0 → NaN (zero std replaced by NaN)
    assert math.isnan(out[2, 0])


def test_rolling_zscore_known_value():
    # Window=3 over [1, 2, 3, 4].
    # At row 3: window=[2,3,4], mean=3, std=1 (ddof=1), z=(4-3)/1=1.
    X = [1.0, 2.0, 3.0, 4.0]
    out = RollingZScore(window=3).transform(X)
    assert out[3, 0] == pytest.approx(1.0)


def test_rolling_zscore_min_periods_allows_shorter_window():
    # With min_periods=2 the z-score should be available one row earlier
    # than with the default min_periods=window (where window=3, default min_periods=3).
    X = [1.0, 3.0, 5.0, 7.0]
    out_default = RollingZScore(window=3).transform(X)
    out_min2 = RollingZScore(window=3, min_periods=2).transform(X)
    # Default: rows 0 and 1 are NaN
    assert math.isnan(out_default[1, 0])
    # min_periods=2: row 1 should have a finite value (2-point window [1,3])
    assert math.isfinite(out_min2[1, 0])


# ---------------------------------------------------------------------------
# RollingQuantile
# ---------------------------------------------------------------------------


def test_rolling_quantile_median():
    # window=3, q=0.5 (default)
    X = [10.0, 20.0, 30.0, 40.0]
    out = RollingQuantile(window=3).transform(X)
    assert out.shape == (4, 1)
    assert math.isnan(out[0, 0])
    # Row 2: median([10, 20, 30]) = 20.0
    assert out[2, 0] == pytest.approx(20.0)
    # Row 3: median([20, 30, 40]) = 30.0
    assert out[3, 0] == pytest.approx(30.0)


def test_rolling_quantile_custom_q():
    X = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = RollingQuantile(window=3, q=0.0).transform(X)
    # Row 4: min([3, 4, 5]) = 3.0
    assert out[4, 0] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# RollingSkew / RollingKurt (smoke: correct shape, NaN before window fills)
# ---------------------------------------------------------------------------


def test_rolling_skew_shape_and_nan_prefix():
    X = [1.0, 2.0, 4.0, 3.0, 5.0]
    out = RollingSkew(window=4).transform(X)
    assert out.shape == (5, 1)
    assert math.isnan(out[0, 0])
    assert math.isnan(out[2, 0])
    # Row 3 onward should be finite
    assert math.isfinite(out[3, 0])


def test_rolling_skew_symmetric_window_is_zero():
    # Input [1, 2, 4, 3, 5]: first full window at row 3 is [1, 2, 4, 3].
    # pandas.Series([1, 2, 4, 3]).skew() == 0.0 (symmetric about 2.5).
    import pandas as pd

    X = [1.0, 2.0, 4.0, 3.0, 5.0]
    out = RollingSkew(window=4).transform(X)
    expected = float(cast("float", pd.Series([1.0, 2.0, 4.0, 3.0]).skew()))  # == 0.0
    assert out[3, 0] == pytest.approx(expected, abs=1e-9)


def test_rolling_kurt_shape_and_nan_prefix():
    X = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = RollingKurt(window=4).transform(X)
    assert out.shape == (5, 1)
    assert math.isnan(out[0, 0])
    assert math.isfinite(out[3, 0])


def test_rolling_kurt_first_full_window_value():
    # window=4 on [1, 2, 3, 4, 5]: first full window is [1, 2, 3, 4] at row 3.
    # pandas rolling excess kurtosis of a uniform-spaced 4-point sequence is -1.2.
    X = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = RollingKurt(window=4).transform(X)
    assert out[3, 0] == pytest.approx(-1.2)
