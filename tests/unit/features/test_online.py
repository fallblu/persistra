"""Tests for persistra.features.online — EWMA and EWVolatility transformers."""

from __future__ import annotations

import pytest

from persistra.features.online import EWMA, EWVolatility

# ---------------------------------------------------------------------------
# EWMA
# ---------------------------------------------------------------------------


def test_ewma_output_shape():
    out = EWMA(span=3).transform([10.0, 20.0, 30.0])
    assert out.shape == (3, 1)


def test_ewma_first_value_equals_first_observation():
    # With adjust=True the first output always equals the first input.
    out = EWMA(span=5).transform([42.0, 100.0, 200.0])
    assert out[0, 0] == pytest.approx(42.0)


def test_ewma_second_value_adjust_true():
    # With span=3, alpha=0.5, adjust=True:
    # EMA[1] = (0.5*10 + 20) / 1.5 = 16.666...
    # (verified independently via pd.Series([10, 20]).ewm(span=3, adjust=True).mean())
    out = EWMA(span=3, adjust=True).transform([10.0, 20.0])
    assert out[1, 0] == pytest.approx(50.0 / 3.0)


def test_ewma_rejects_non_positive_span():
    with pytest.raises(ValueError):
        EWMA(span=0)
    with pytest.raises(ValueError):
        EWMA(span=-1)


def test_ewma_partial_fit_updates_state():
    # span=3 → alpha=0.5
    # First partial_fit initialises state from first observation.
    # Second partial_fit: state = alpha*new + (1-alpha)*prior = 0.5*20 + 0.5*10 = 15.0
    ew = EWMA(span=3)
    ew.partial_fit([10.0])
    assert ew.latest()[0] == pytest.approx(10.0)
    ew.partial_fit([20.0])
    assert ew.latest()[0] == pytest.approx(15.0)


def test_ewma_latest_empty_before_partial_fit():
    assert EWMA(span=5).latest().size == 0


# ---------------------------------------------------------------------------
# EWVolatility
# ---------------------------------------------------------------------------


def test_ewvolatility_output_shape():
    # T prices → T-1 vol estimates
    out = EWVolatility(span=5).transform([100.0, 101.0, 102.0, 103.0, 104.0])
    assert out.shape == (4, 1)


def test_ewvolatility_empty_for_single_row():
    out = EWVolatility(span=5).transform([100.0])
    assert out.shape == (0, 1)


def test_ewvolatility_equal_log_returns_give_zero_vol():
    # Constant price ratio → identical log returns → EW variance = 0 after row 1
    # (row 0 is NaN since ewm variance needs ≥2 obs; row 1 onward is 0)
    prices = [100.0, 110.0, 121.0]  # log return = log(1.1) each step
    out = EWVolatility(span=3).transform(prices)
    assert out.shape == (2, 1)
    # Second row: EW var of two equal values → var=0, vol=0
    assert out[1, 0] == pytest.approx(0.0)


def test_ewvolatility_rejects_non_positive_span():
    with pytest.raises(ValueError):
        EWVolatility(span=0)


def test_ewvolatility_partial_fit_state_is_positive():
    # After partial_fit with varying prices, latest() should return positive vol.
    ev = EWVolatility(span=5)
    prices = [100.0, 105.0, 98.0, 110.0, 103.0]
    ev.partial_fit(prices)
    vol = ev.latest()
    assert vol.shape == (1,)
    assert vol[0] > 0.0
