"""Point-in-time factor forecasts and portfolio attribution."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError
from persistra.research.model import (
    FactorPortfolioAttribution,
    FactorPortfolioForecast,
    FactorRiskModel,
)


def build_factor_portfolio_forecast(
    risk_model: FactorRiskModel,
    factor_premia: pd.Series,
    *,
    alpha: pd.Series | None = None,
    as_of: pd.Timestamp | None = None,
) -> FactorPortfolioForecast:
    """Combine supplied factor premia and a factor risk model without hidden scaling."""
    exposures = risk_model.exposures.copy(deep=True)
    assets = exposures.index
    factors = exposures.columns
    premia = _aligned_series(factor_premia, factors, name="factor premia")
    intercept = (
        pd.Series(0.0, index=assets, name="alpha")
        if alpha is None
        else _aligned_series(alpha, assets, name="alpha").rename("alpha")
    )
    factor_contributions = exposures.mul(premia, axis="columns")
    contributions = pd.concat([intercept, factor_contributions], axis="columns")
    contributions.columns = pd.Index(["alpha", *factors.tolist()])
    expected = contributions.sum(axis="columns").rename("expected_return")
    effective_as_of = _forecast_as_of(risk_model.as_of, as_of)
    return FactorPortfolioForecast(
        expected_returns=expected,
        expected_return_contributions=contributions,
        exposures=exposures,
        factor_premia=premia,
        alpha=intercept,
        factor_covariance=risk_model.factor_covariance,
        idiosyncratic_variance=risk_model.idiosyncratic_variance,
        asset_covariance=risk_model.asset_covariance,
        as_of=effective_as_of,
    )


def attribute_factor_portfolio(
    forecast: FactorPortfolioForecast,
    weights: pd.Series,
    *,
    benchmark_weights: pd.Series | None = None,
) -> FactorPortfolioAttribution:
    """Attribute a portfolio, or its active weights, to factor and specific components."""
    checked_weights = _aligned_series(weights, forecast.exposures.index, name="weights")
    if benchmark_weights is not None:
        benchmark = _aligned_series(
            benchmark_weights,
            forecast.exposures.index,
            name="benchmark weights",
        )
        checked_weights = checked_weights.subtract(benchmark).rename("active_weight")
    exposure_values = forecast.exposures.to_numpy(dtype=float).T @ checked_weights.to_numpy(
        dtype=float
    )
    factor_exposures = pd.Series(
        exposure_values,
        index=forecast.exposures.columns.copy(),
        name="exposure",
    )
    factor_expected = pd.Series(
        exposure_values * forecast.factor_premia.to_numpy(dtype=float),
        index=forecast.exposures.columns.copy(),
    )
    alpha_expected = float(
        checked_weights.to_numpy(dtype=float) @ forecast.alpha.to_numpy(dtype=float)
    )
    expected_contributions = pd.concat(
        [pd.Series({"alpha": alpha_expected}), factor_expected]
    ).rename("expected_return_contribution")

    factor_covariance = forecast.factor_covariance.to_numpy(dtype=float)
    factor_marginal = factor_covariance @ exposure_values
    factor_variance = pd.Series(
        exposure_values * factor_marginal,
        index=forecast.exposures.columns.copy(),
    )
    weight_values = checked_weights.to_numpy(dtype=float)
    specific_variance = float(
        np.square(weight_values) @ forecast.idiosyncratic_variance.to_numpy(dtype=float)
    )
    variance_contributions = pd.concat(
        [factor_variance, pd.Series({"idiosyncratic": specific_variance})]
    ).rename("variance_contribution")
    variance = float(
        weight_values @ forecast.asset_covariance.to_numpy(dtype=float) @ weight_values
    )
    expected_return = float(
        checked_weights.to_numpy(dtype=float)
        @ forecast.expected_returns.to_numpy(dtype=float)
    )
    return FactorPortfolioAttribution(
        weights=checked_weights,
        factor_exposures=factor_exposures,
        expected_return_contributions=expected_contributions,
        variance_contributions=variance_contributions,
        expected_return=expected_return,
        variance=variance,
        volatility=math.sqrt(max(0.0, variance)),
        as_of=forecast.as_of,
    )


def _aligned_series(values: pd.Series, index: pd.Index, *, name: str) -> pd.Series:
    if not values.index.equals(index):
        raise ValueError(f"{name} must use the required index")
    try:
        checked = values.astype(float)
    except (TypeError, ValueError) as exc:
        raise AnalysisError(f"{name} must be numeric") from exc
    if not np.isfinite(checked.to_numpy(dtype=float)).all():
        raise AnalysisError(f"{name} must be finite")
    return checked.copy(deep=True)


def _forecast_as_of(
    risk_as_of: pd.Timestamp | None,
    requested: pd.Timestamp | None,
) -> pd.Timestamp | None:
    if risk_as_of is not None and requested is not None:
        if pd.Timestamp(risk_as_of) != pd.Timestamp(requested):
            raise ValueError("forecast as_of must match the factor risk model")
    selected = risk_as_of if requested is None else requested
    return None if selected is None else pd.Timestamp(selected)
