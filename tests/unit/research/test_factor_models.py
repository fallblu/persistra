from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.research import (
    FactorPortfolioForecastSuccess,
    FactorPortfolioForecastUnavailable,
    ForwardReturnLabels,
    attribute_factor_portfolio,
    build_factor_portfolio_forecast,
    build_factor_risk_model,
    create_research_manifest,
    estimate_cross_sectional_factor_returns,
    fama_macbeth_regression,
    fit_time_series_factor_model,
    rolling_factor_portfolio_forecasts,
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


def test_factor_risk_model_uses_one_aligned_point_in_time_sample() -> None:
    dates = pd.DatetimeIndex(
        ["2024-12-02", "2025-01-02", "2025-01-07", "2025-01-31"]
    )
    exposures = pd.DataFrame({"factor": [1.0]}, index=pd.Index(["AAA"]))
    factor_returns = pd.DataFrame({"factor": [100.0, 1.0, np.nan, 3.0]}, index=dates)
    residuals = pd.DataFrame({"AAA": [100.0, 1.0, np.nan, 5.0]}, index=dates)

    risk = build_factor_risk_model(
        exposures,
        factor_returns,
        residuals,
        window=3,
    )

    assert risk.as_of == dates[-1]
    assert risk.factor_covariance.loc["factor", "factor"] == pytest.approx(2.0)
    assert risk.idiosyncratic_variance["AAA"] == pytest.approx(8.0)

    later_boundary = pd.Timestamp("2025-02-01")
    later = build_factor_risk_model(
        exposures,
        factor_returns,
        residuals,
        window=3,
        as_of=later_boundary,
    )
    assert later.as_of == later_boundary
    forecast = build_factor_portfolio_forecast(
        later,
        pd.Series({"factor": 0.01}),
    )
    assert forecast.as_of == later_boundary


def test_factor_risk_model_rejects_temporal_misalignment_and_lookahead() -> None:
    dates = pd.DatetimeIndex(["2025-01-02", "2025-01-07", "2025-01-31"])
    exposures = pd.DataFrame({"factor": [1.0]}, index=pd.Index(["AAA"]))
    factor_returns = pd.DataFrame({"factor": [1.0, 2.0, 3.0]}, index=dates)
    residuals = pd.DataFrame({"AAA": [1.0, 2.0, 3.0]}, index=dates)

    shifted = residuals.set_axis(pd.DatetimeIndex(["2025-01-02", "2025-01-08", "2025-01-31"]))
    with pytest.raises(ValueError, match="same date index"):
        build_factor_risk_model(exposures, factor_returns, shifted)

    for future_value in (3.0, 3_000.0):
        future_residuals = residuals.copy()
        future_residuals.iloc[-1, 0] = future_value
        with pytest.raises(ValueError, match="must not precede"):
            build_factor_risk_model(
                exposures,
                factor_returns,
                future_residuals,
                as_of=dates[-2],
            )


def test_factor_risk_model_validates_as_of_timezone_and_missingness() -> None:
    dates = pd.date_range("2025-01-01", periods=2, tz="America/New_York")
    exposures = pd.DataFrame({"factor": [1.0]}, index=pd.Index(["AAA"]))
    factor_returns = pd.DataFrame({"factor": [1.0, 2.0]}, index=dates)
    residuals = pd.DataFrame({"AAA": [1.0, 2.0]}, index=dates)

    compatible = dates[-1].tz_convert("UTC") + pd.Timedelta(hours=1)
    risk = build_factor_risk_model(
        exposures,
        factor_returns,
        residuals,
        as_of=compatible,
    )
    assert risk.as_of == compatible

    with pytest.raises(ValueError, match="timezone awareness"):
        build_factor_risk_model(
            exposures,
            factor_returns,
            residuals,
            as_of=dates[-1].tz_localize(None),
        )
    with pytest.raises(ValueError, match="must not be missing"):
        build_factor_risk_model(
            exposures,
            factor_returns,
            residuals,
            as_of=cast("pd.Timestamp", pd.NaT),
        )


def test_established_covariance_estimators_are_explicit_and_condition_singular_samples() -> None:
    dates = _dates(8)
    exposures = pd.DataFrame(
        {"market": [1.0, 0.5], "quality": [0.2, 1.0]},
        index=pd.Index(["AAA", "BBB"]),
    )
    common = np.linspace(-0.03, 0.04, len(dates))
    factors = pd.DataFrame({"market": common, "quality": common}, index=dates)
    residuals = pd.DataFrame(
        {"AAA": np.linspace(-0.01, 0.01, len(dates)), "BBB": common / 3.0},
        index=dates,
    )

    sample = build_factor_risk_model(exposures, factors, residuals, covariance="sample")
    ledoit_wolf = build_factor_risk_model(
        exposures,
        factors,
        residuals,
        covariance="ledoit_wolf",
    )
    constant = build_factor_risk_model(
        exposures,
        factors.assign(quality=common[::-1] + np.linspace(0.0, 0.01, len(dates))),
        residuals,
        covariance="constant_correlation",
        shrinkage=0.5,
    )
    ewma = build_factor_risk_model(
        exposures,
        factors.assign(quality=np.square(common)),
        residuals,
        covariance="ewma",
        ewma_decay=0.8,
    )

    assert np.linalg.eigvalsh(sample.factor_covariance).min() == pytest.approx(0.0, abs=1e-12)
    assert np.linalg.eigvalsh(ledoit_wolf.factor_covariance).min() > 0.0
    assert ledoit_wolf.covariance_estimator == "ledoit_wolf"
    assert 0.0 < ledoit_wolf.shrinkage <= 1.0
    assert ledoit_wolf.manifest_parameters["covariance_estimator"] == "ledoit_wolf"
    manifest = create_research_manifest(
        [],
        feature_parameters={},
        label_parameters={},
        split_parameters={},
        benchmark_parameters={},
        model_parameters={"factor_risk": ledoit_wolf.manifest_parameters},
        manifest_version=2,
        environment={"persistra": "4"},
        include_runtime=False,
    )
    assert manifest.model_parameters["factor_risk"]["covariance_estimator"] == "ledoit_wolf"
    assert constant.covariance_parameters == {"shrinkage": 0.5}
    assert ewma.covariance_parameters == {"decay": 0.8}
    assert not constant.factor_covariance.equals(ewma.factor_covariance)


def test_factor_risk_model_accepts_validated_caller_covariance() -> None:
    dates = _dates(3)
    exposures = pd.DataFrame(
        {"market": [1.0, 0.5], "quality": [0.2, 1.0]},
        index=pd.Index(["AAA", "BBB"]),
    )
    factors = pd.DataFrame(
        {"market": [0.01, -0.02, 0.03], "quality": [0.02, 0.0, -0.01]},
        index=dates,
    )
    residuals = pd.DataFrame(
        {"AAA": [0.01, -0.01, 0.0], "BBB": [0.0, 0.01, -0.01]},
        index=dates,
    )
    supplied = pd.DataFrame(
        [[0.04, 0.01], [0.01, 0.09]],
        index=factors.columns,
        columns=factors.columns,
    )

    risk = build_factor_risk_model(exposures, factors, residuals, covariance=supplied)

    assert risk.covariance_estimator == "supplied"
    pd.testing.assert_frame_equal(risk.factor_covariance, supplied)
    assert risk.factor_observations == 3
    assert risk.residual_observations.to_dict() == {"AAA": 3, "BBB": 3}
    asymmetric = supplied.copy()
    asymmetric.iloc[0, 1] = 0.0
    with pytest.raises(AnalysisError, match="symmetric"):
        build_factor_risk_model(
            exposures,
            factors,
            residuals,
            covariance=asymmetric,
        )


def test_rolling_factor_forecasts_retain_unavailable_steps_without_lookahead() -> None:
    dates = _dates(7)
    assets = pd.Index(["AAA", "BBB"], name="asset")
    factors = pd.DataFrame(
        {
            "market": np.linspace(-0.02, 0.03, len(dates)),
            "quality": [0.01, -0.01, 0.02, 0.0, -0.02, 0.01, 0.03],
        },
        index=dates,
    )
    residuals = pd.DataFrame(
        {
            "AAA": [0.01, -0.01, 0.005, 0.0, -0.005, 0.01, -0.01],
            "BBB": [-0.005, 0.0, 0.01, -0.01, 0.005, 0.0, 0.01],
        },
        index=dates,
    )
    exposure_index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    exposures = pd.DataFrame(
        np.tile([[1.0, 0.2], [0.5, 1.0]], (len(dates), 1)),
        index=exposure_index,
        columns=factors.columns,
    )
    premia = pd.DataFrame(
        {"market": np.linspace(0.01, 0.02, len(dates)), "quality": 0.005},
        index=dates,
    )

    result = rolling_factor_portfolio_forecasts(
        exposures,
        factors,
        residuals,
        premia,
        window=4,
        minimum_observations=3,
        covariance="ewma",
        ewma_decay=0.8,
    )
    changed_factors = factors.copy()
    changed_factors.iloc[-1] = 1000.0
    changed = rolling_factor_portfolio_forecasts(
        exposures,
        changed_factors,
        residuals,
        premia,
        window=4,
        minimum_observations=3,
        covariance="ewma",
        ewma_decay=0.8,
    )

    assert isinstance(result.steps[0], FactorPortfolioForecastUnavailable)
    assert isinstance(result.steps[1], FactorPortfolioForecastUnavailable)
    assert result.steps[0].covariance_estimator == "ewma"
    assert result.steps[0].covariance_parameters == {"decay": 0.8}
    assert isinstance(result.steps[4], FactorPortfolioForecastSuccess)
    assert isinstance(changed.steps[4], FactorPortfolioForecastSuccess)
    pd.testing.assert_frame_equal(
        result.steps[4].forecast.asset_covariance,
        changed.steps[4].forecast.asset_covariance,
    )
    assert result.steps[4].forecast.covariance_estimator == "ewma"
    assert result.steps[4].forecast.covariance_parameters == {"decay": 0.8}
    assert result.diagnostics["status"].tolist() == ["unavailable", "unavailable"] + ["ok"] * 5


def test_expanding_factor_forecasts_record_missing_point_in_time_inputs() -> None:
    dates = _dates(4)
    assets = pd.Index(["AAA"], name="asset")
    factors = pd.DataFrame({"market": [0.01, -0.01, 0.02, 0.03]}, index=dates)
    residuals = pd.DataFrame({"AAA": [0.001, -0.001, 0.002, 0.0]}, index=dates)
    exposures = pd.DataFrame(
        {"market": [1.0] * len(dates)},
        index=pd.MultiIndex.from_product([dates, assets], names=["date", "asset"]),
    )
    premia = pd.DataFrame({"market": [0.01, 0.01, np.nan, 0.02]}, index=dates)

    result = rolling_factor_portfolio_forecasts(
        exposures,
        factors,
        residuals,
        premia,
        window=None,
        minimum_observations=2,
    )

    assert result.window is None
    assert isinstance(result.steps[0], FactorPortfolioForecastUnavailable)
    assert isinstance(result.steps[1], FactorPortfolioForecastSuccess)
    assert isinstance(result.steps[2], FactorPortfolioForecastUnavailable)
    assert result.steps[2].reason == "factor premia are unavailable"
    assert isinstance(result.steps[3], FactorPortfolioForecastSuccess)


def test_factor_covariance_policies_reject_invalid_parameters_and_samples() -> None:
    dates = _dates(3)
    exposures = pd.DataFrame({"factor": [1.0]}, index=pd.Index(["AAA"]))
    factors = pd.DataFrame({"factor": [0.01, -0.01, 0.02]}, index=dates)
    residuals = pd.DataFrame({"AAA": [0.001, -0.001, 0.002]}, index=dates)
    supplied = pd.DataFrame([[0.04]], index=factors.columns, columns=factors.columns)

    invalid_calls = [
        ({"covariance": "unknown"}, "unsupported"),
        ({"covariance": "sample", "shrinkage": 0.1}, "must be zero"),
        ({"covariance": "ewma", "ewma_decay": 1.0}, "strictly between"),
        ({"covariance": supplied, "shrinkage": 0.1}, "must be zero"),
        ({"covariance": supplied.rename(index={"factor": "wrong"})}, "factor axes"),
        ({"covariance": supplied.mask(supplied.eq(0.04))}, "complete"),
        ({"covariance": supplied.mul(-1)}, "positive semidefinite"),
    ]
    for kwargs, message in invalid_calls:
        with pytest.raises((ValueError, AnalysisError), match=message):
            build_factor_risk_model(exposures, factors, residuals, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(AnalysisError, match="at least two"):
        build_factor_risk_model(exposures, factors.iloc[:1], residuals.iloc[:1])
    incomplete_residuals = residuals.copy()
    incomplete_residuals.iloc[1:] = np.nan
    with pytest.raises(AnalysisError, match="residual observations"):
        build_factor_risk_model(exposures, factors, incomplete_residuals)


def test_rolling_factor_forecasts_validate_axes_windows_and_unavailable_inputs() -> None:
    dates = _dates(3)
    assets = pd.Index(["AAA"], name="asset")
    factors = pd.DataFrame({"factor": [0.01, -0.01, 0.02]}, index=dates)
    residuals = pd.DataFrame({"AAA": [0.001, -0.001, 0.002]}, index=dates)
    premia = pd.DataFrame({"factor": [0.01, 0.01, 0.01]}, index=dates)
    exposure_index = pd.MultiIndex.from_product([dates, assets], names=["date", "asset"])
    exposures = pd.DataFrame({"factor": [1.0] * 3}, index=exposure_index)

    with pytest.raises(ValueError, match="residual returns"):
        rolling_factor_portfolio_forecasts(
            exposures, factors, residuals.iloc[:-1], premia
        )
    with pytest.raises(ValueError, match="factor premia"):
        rolling_factor_portfolio_forecasts(
            exposures, factors, residuals, premia.rename(columns={"factor": "wrong"})
        )
    with pytest.raises(ValueError, match="alpha"):
        rolling_factor_portfolio_forecasts(
            exposures,
            factors,
            residuals,
            premia,
            alpha=residuals.rename(columns={"AAA": "wrong"}),
        )
    with pytest.raises(ValueError, match="date, asset"):
        rolling_factor_portfolio_forecasts(
            exposures.reset_index(drop=True), factors, residuals, premia
        )
    with pytest.raises(ValueError, match="must not exceed"):
        rolling_factor_portfolio_forecasts(
            exposures,
            factors,
            residuals,
            premia,
            window=2,
            minimum_observations=3,
        )
    with pytest.raises(ValueError, match="must be zero"):
        rolling_factor_portfolio_forecasts(
            exposures,
            factors,
            residuals,
            premia,
            covariance="sample",
            shrinkage=0.1,
        )

    missing_residual = residuals.copy()
    missing_residual.iloc[1] = np.nan
    residual_result = rolling_factor_portfolio_forecasts(
        exposures,
        factors,
        missing_residual,
        premia,
        minimum_observations=2,
    )
    assert isinstance(residual_result.steps[1], FactorPortfolioForecastUnavailable)
    assert residual_result.steps[1].reason == "insufficient residual observations"

    missing_exposure = exposures.copy()
    missing_exposure.loc[(dates[1], "AAA"), "factor"] = np.nan
    exposure_result = rolling_factor_portfolio_forecasts(
        missing_exposure,
        factors,
        residuals,
        premia,
        minimum_observations=2,
    )
    assert isinstance(exposure_result.steps[1], FactorPortfolioForecastUnavailable)
    assert exposure_result.steps[1].reason == "factor exposures are unavailable"

    alpha = residuals.copy()
    alpha.iloc[1] = np.nan
    alpha_result = rolling_factor_portfolio_forecasts(
        exposures,
        factors,
        residuals,
        premia,
        alpha=alpha,
        minimum_observations=2,
    )
    assert isinstance(alpha_result.steps[1], FactorPortfolioForecastUnavailable)
    assert alpha_result.steps[1].reason == "asset alpha is unavailable"


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
