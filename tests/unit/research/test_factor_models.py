from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.research import (
    ForwardReturnLabels,
    attribute_factor_portfolio,
    build_factor_portfolio_forecast,
    build_factor_risk_model,
    estimate_cross_sectional_factor_returns,
    fama_macbeth_regression,
    fit_time_series_factor_model,
    rolling_time_series_factor_model,
    summarize_factor_premia,
)


def _dates(periods: int = 12) -> pd.DatetimeIndex:
    return pd.date_range("2025-01-01", periods=periods, freq="D")


def test_time_series_factor_model_recovers_supplied_factors_and_inference() -> None:
    dates = _dates()
    market = np.linspace(-0.03, 0.04, len(dates))
    quality = np.array([0.01, -0.02, 0.03, -0.01] * 3)
    factors = pd.DataFrame({"market": market, "quality": quality}, index=dates)
    noise = np.array([0.001, -0.001, 0.0] * 4)
    assets = pd.DataFrame(
        {
            "AAA": 0.002 + (1.5 * market) - (0.4 * quality) + noise,
            "BBB": -0.001 + (0.5 * market) + (0.8 * quality) - noise,
        },
        index=dates,
    )

    result = fit_time_series_factor_model(assets, factors, covariance="hc3")

    assert result.factor_names == ("market", "quality")
    assert result.coefficients.loc["AAA", "intercept"] == pytest.approx(0.002, abs=5e-4)
    assert result.coefficients.loc["AAA", "market"] == pytest.approx(1.5, abs=0.03)
    assert result.coefficients.loc["BBB", "quality"] == pytest.approx(0.8, abs=0.03)
    assert all(result.diagnostics["status"].eq("ok").tolist())
    assert np.isfinite(result.standard_errors.to_numpy()).all()
    pd.testing.assert_frame_equal(result.fitted_values.add(result.residuals), assets)


def test_time_series_factor_model_reports_rank_and_missing_observations() -> None:
    dates = _dates(6)
    factor = np.arange(6, dtype=float)
    factors = pd.DataFrame({"first": factor, "duplicate": factor}, index=dates)
    assets = pd.DataFrame({"AAA": factor, "BBB": [np.nan] * 5 + [1.0]}, index=dates)

    result = fit_time_series_factor_model(assets, factors)

    assert result.diagnostics.loc["AAA", "status"] == "rank_deficient"
    assert result.diagnostics.loc["BBB", "status"] == "insufficient_observations"
    errors = cast("pd.Series", result.standard_errors.loc["AAA"])
    assert all(errors.isna().tolist())


def test_rolling_factor_model_is_causal_and_supports_expanding_windows() -> None:
    dates = _dates(10)
    factor = np.arange(1.0, 11.0)
    factors = pd.DataFrame({"factor": factor}, index=dates)
    original = pd.DataFrame({"AAA": 2.0 * factor}, index=dates)
    changed = original.copy()
    changed.iloc[8:] = -1000.0

    first = rolling_time_series_factor_model(
        original,
        factors,
        window=None,
        minimum_observations=3,
    )
    second = rolling_time_series_factor_model(
        changed,
        factors,
        window=None,
        minimum_observations=3,
    )

    cutoff = dates[7]
    first_cutoff = cast("pd.Series", first.coefficients.xs(cutoff, level="date").loc["AAA"])
    second_cutoff = cast("pd.Series", second.coefficients.xs(cutoff, level="date").loc["AAA"])
    pd.testing.assert_series_equal(first_cutoff, second_cutoff)
    assert first.coefficients.loc[(cutoff, "AAA"), "factor"] == pytest.approx(2.0)
    assert first.diagnostics.loc[(dates[1], "AAA"), "status"] == ("insufficient_observations")


def _cross_sectional_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = _dates(6)
    assets = pd.Index(["A", "B", "C", "D", "E"], name="asset")
    value = np.array([-2.0, -1.0, 0.0, 1.0, 2.0])
    size = np.array([1.0, -1.0, 1.0, -1.0, 0.5])
    exposure_rows: list[dict[str, float | str | pd.Timestamp]] = []
    returns = pd.DataFrame(index=dates, columns=assets, dtype=float)
    for position, date in enumerate(dates):
        value_premium = 0.01 + (0.001 * position)
        size_premium = -0.005 + (0.0005 * position)
        returns.loc[date] = 0.002 + (value * value_premium) + (size * size_premium)
        for asset, value_exposure, size_exposure in zip(assets, value, size, strict=True):
            exposure_rows.append(
                {
                    "date": date,
                    "asset": asset,
                    "value": value_exposure,
                    "size": size_exposure,
                }
            )
    exposures = pd.DataFrame(exposure_rows).set_index(["date", "asset"])
    return returns, exposures


def test_cross_sectional_and_fama_macbeth_models_use_supplied_exposures() -> None:
    returns, exposures = _cross_sectional_inputs()
    cross_sectional = estimate_cross_sectional_factor_returns(returns, exposures)

    assert cross_sectional.factor_returns.iloc[0].to_dict() == pytest.approx(
        {"intercept": 0.002, "value": 0.01, "size": -0.005}
    )
    assert np.nanmax(np.abs(cross_sectional.residuals.to_numpy(dtype=float))) < 1e-12

    ends = pd.Series(index=returns.index, dtype=returns.index.dtype)
    ends.iloc[:-1] = returns.index[1:]
    labels = ForwardReturnLabels(returns, ends, horizon=1)
    fama_macbeth = fama_macbeth_regression(labels, exposures, hac_lags=1)

    assert fama_macbeth.cross_sectional.label_horizon == 1
    assert fama_macbeth.premia.statistics.loc["value", "premium"] == pytest.approx(0.012)
    assert fama_macbeth.premia.statistics.loc["size", "periods"] == 5


def test_factor_premia_and_risk_model_reconcile_covariance() -> None:
    returns, exposures = _cross_sectional_inputs()
    cross_sectional = estimate_cross_sectional_factor_returns(returns, exposures)
    premia = summarize_factor_premia(
        cross_sectional.factor_returns.drop(columns="intercept"),
        covariance="classical",
    )
    assert premia.statistics.loc["value", "premium"] == pytest.approx(0.0125)

    current = cast("pd.DataFrame", exposures.xs(returns.index[-1], level="date"))
    residuals = pd.DataFrame(
        {
            asset: np.linspace(-0.002, 0.002, len(returns.index)) * (position + 1)
            for position, asset in enumerate(current.index)
        },
        index=returns.index,
    )
    risk = build_factor_risk_model(
        current,
        cross_sectional.factor_returns.drop(columns="intercept"),
        residuals,
        shrinkage=0.25,
    )

    beta = risk.exposures.to_numpy(dtype=float)
    expected = beta @ risk.factor_covariance.to_numpy(dtype=float) @ beta.T
    expected += np.diag(risk.idiosyncratic_variance.to_numpy(dtype=float))
    np.testing.assert_allclose(risk.asset_covariance, expected)
    np.testing.assert_allclose(risk.asset_covariance, risk.asset_covariance.T)


def test_factor_portfolio_forecast_and_active_attribution_reconcile() -> None:
    dates = _dates(4)
    exposures = pd.DataFrame(
        {"market": [1.0, 0.5], "quality": [-0.5, 1.0]},
        index=pd.Index(["AAA", "BBB"]),
    )
    factor_returns = pd.DataFrame(
        {"market": [-0.02, 0.01, 0.03, -0.01], "quality": [0.01, 0.0, -0.01, 0.02]},
        index=dates,
    )
    residuals = pd.DataFrame(
        {"AAA": [0.01, -0.01, 0.02, -0.02], "BBB": [0.005, -0.005, 0.01, -0.01]},
        index=dates,
    )
    risk = build_factor_risk_model(exposures, factor_returns, residuals)
    forecast = build_factor_portfolio_forecast(
        risk,
        pd.Series({"market": 0.02, "quality": 0.01}),
        alpha=pd.Series({"AAA": 0.001, "BBB": -0.001}),
    )

    assert forecast.expected_returns.to_dict() == pytest.approx(
        {"AAA": 0.016, "BBB": 0.019}
    )
    np.testing.assert_allclose(
        forecast.expected_return_contributions.sum(axis="columns"),
        forecast.expected_returns,
    )
    attribution = attribute_factor_portfolio(
        forecast,
        pd.Series({"AAA": 0.6, "BBB": 0.4}),
        benchmark_weights=pd.Series({"AAA": 0.5, "BBB": 0.5}),
    )
    assert attribution.weights.to_dict() == pytest.approx({"AAA": 0.1, "BBB": -0.1})
    assert attribution.expected_return_contributions.sum() == pytest.approx(
        attribution.expected_return
    )
    assert attribution.variance_contributions.sum() == pytest.approx(attribution.variance)


def test_factor_portfolio_forecast_rejects_misaligned_inputs() -> None:
    exposures = pd.DataFrame({"factor": [1.0]}, index=pd.Index(["AAA"]))
    dates = _dates(2)
    risk = build_factor_risk_model(
        exposures,
        pd.DataFrame({"factor": [0.01, -0.01]}, index=dates),
        pd.DataFrame({"AAA": [0.001, -0.001]}, index=dates),
        as_of=dates[-1],
    )
    with pytest.raises(ValueError, match="factor premia"):
        build_factor_portfolio_forecast(risk, pd.Series({"wrong": 0.01}))
    with pytest.raises(ValueError, match="as_of"):
        build_factor_portfolio_forecast(
            risk,
            pd.Series({"factor": 0.01}),
            as_of=dates[0],
        )


def test_factor_models_reject_misalignment_and_invalid_controls() -> None:
    returns, exposures = _cross_sectional_inputs()
    with pytest.raises(ValueError, match="same date index"):
        fit_time_series_factor_model(returns, returns.iloc[:-1, :2])
    with pytest.raises(ValueError, match="named date and asset"):
        estimate_cross_sectional_factor_returns(
            returns,
            exposures.rename_axis(index=["when", "asset"]),
        )
    with pytest.raises(ValueError, match="requires newey_west"):
        fit_time_series_factor_model(returns, returns.iloc[:, :2], hac_lags=1)
    with pytest.raises(AnalysisError, match="complete"):
        build_factor_risk_model(
            cast(
                "pd.DataFrame",
                exposures.xs(returns.index[-1], level="date"),
            ).mask(lambda frame: frame == 0.0),
            returns.iloc[:, :2].set_axis(["value", "size"], axis="columns"),
            returns,
        )
