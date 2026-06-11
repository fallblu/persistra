"""Tests for persistra.features.structural — PCA, cointegration, Kalman transformers."""

from __future__ import annotations

import numpy as np
import pytest

from persistra.features.structural import (
    CointegrationCoefficients,
    KalmanHedgeRatio,
    RollingPCA,
)

# ---------------------------------------------------------------------------
# RollingPCA
# ---------------------------------------------------------------------------


def test_rolling_pca_output_shape():
    # (T=10, n_sym=3), n_components=1  → shape (3, 1)
    rng = np.random.default_rng(42)
    X = rng.standard_normal((10, 3)) + 100
    out = RollingPCA(n_components=1).transform(X)
    assert out.shape == (3, 1)


def test_rolling_pca_returns_zeros_for_single_row():
    # Fewer than 2 rows → all-zero output
    out = RollingPCA(n_components=1).transform([[1.0, 2.0, 3.0]])
    assert out.shape == (3, 1)
    np.testing.assert_array_equal(out, 0.0)


def test_rolling_pca_rejects_zero_components():
    with pytest.raises(ValueError):
        RollingPCA(n_components=0)


def test_rolling_pca_loadings_unit_norm():
    # For a 1-component PCA the loading vector should be unit-norm.
    rng = np.random.default_rng(7)
    X = rng.standard_normal((20, 4))
    out = RollingPCA(n_components=1).transform(X)
    # out[:,0] is the first PC loading vector (V^T row)
    norm = float(np.linalg.norm(out[:, 0]))
    assert norm == pytest.approx(1.0, abs=1e-9)


def test_rolling_pca_dominant_direction_known():
    # Construct two columns where col1 ≈ 2 * col0 (strong positive correlation).
    # The first PC must load with the same sign on both columns since the
    # dominant variance direction is the shared one.
    #
    # We test the relative sign (robust to the SVD sign ambiguity) and that
    # both loadings are clearly non-zero (absolute value > 0.1).
    rng = np.random.default_rng(42)
    col0 = rng.standard_normal(50)
    col1 = 2.0 * col0 + rng.standard_normal(50) * 0.01
    X = np.column_stack([col0, col1])
    out = RollingPCA(n_components=1).transform(X)
    loading = out[:, 0]
    # Both loadings should have the same sign (relative sign == +1).
    assert np.sign(loading[0]) == np.sign(loading[1])
    # Both loadings should be clearly non-zero.
    assert abs(loading[0]) > 0.1
    assert abs(loading[1]) > 0.1


# ---------------------------------------------------------------------------
# CointegrationCoefficients
# ---------------------------------------------------------------------------


def test_cointegration_reference_col_is_one():
    # Reference symbol always gets ratio=1.0
    X = [[100.0, 200.0], [110.0, 220.0], [120.0, 240.0]]
    out = CointegrationCoefficients(reference_index=0).transform(X)
    assert out.shape == (2, 1)
    assert out[0, 0] == pytest.approx(1.0)


def test_cointegration_exact_ratio_proportional_prices():
    # If col1 = k * col0 in log space (log(p1) = log(p0) + const),
    # the OLS beta of log(p1) on log(p0) is 1.0 regardless of the constant.
    prices = np.array([[10.0, 20.0], [20.0, 40.0], [30.0, 60.0]])
    out = CointegrationCoefficients(reference_index=0).transform(prices)
    # col1 = 2 * col0 always, so log(p1) = log(p0) + log(2) → beta = 1.0
    assert out[1, 0] == pytest.approx(1.0, abs=1e-9)


def test_cointegration_returns_zeros_for_single_row():
    out = CointegrationCoefficients().transform([[100.0, 200.0]])
    assert out.shape == (2, 1)
    np.testing.assert_array_equal(out, 0.0)


# ---------------------------------------------------------------------------
# KalmanHedgeRatio
# ---------------------------------------------------------------------------


def test_kalman_hedge_ratio_output_shape():
    rng = np.random.default_rng(3)
    X = rng.standard_normal((50, 3)) + 100
    out = KalmanHedgeRatio(reference_index=0).transform(X)
    assert out.shape == (3, 1)


def test_kalman_hedge_ratio_reference_is_one():
    prices = np.column_stack([np.linspace(100, 120, 20), np.linspace(200, 240, 20)])
    out = KalmanHedgeRatio(reference_index=0).transform(prices)
    assert out[0, 0] == pytest.approx(1.0)


def test_kalman_hedge_ratio_rejects_invalid_delta():
    with pytest.raises(ValueError):
        KalmanHedgeRatio(delta=0.0)
    with pytest.raises(ValueError):
        KalmanHedgeRatio(delta=1.0)


def test_kalman_hedge_ratio_returns_zeros_for_single_row():
    out = KalmanHedgeRatio().transform([[100.0, 200.0]])
    assert out.shape == (2, 1)
    np.testing.assert_array_equal(out, 0.0)


def test_kalman_hedge_ratio_converges_to_power_ratio():
    # Construct prices where log(col1) = 1.5 * log(col0) exactly, i.e.
    # col1 = col0 ** 1.5.  The Kalman filter estimates beta in
    # log(col1) ≈ beta * log(col0), so the true beta is 1.5.
    # With 200 data points and default delta=1e-4 the estimate converges
    # within 30% of the true value.
    col0 = np.linspace(100.0, 200.0, 200)
    col1 = col0**1.5
    prices = np.column_stack([col0, col1])
    out = KalmanHedgeRatio(reference_index=0, delta=1e-4).transform(prices)
    assert out[0, 0] == pytest.approx(1.0)  # reference column always 1
    assert out[1, 0] == pytest.approx(1.5, rel=0.3)  # non-reference converges near 1.5
