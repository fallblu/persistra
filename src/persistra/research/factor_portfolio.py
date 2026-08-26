"""Point-in-time factor forecasts and portfolio attribution."""

from __future__ import annotations

import math
from typing import cast

import numpy as np
import pandas as pd

from persistra._validation import require_integer
from persistra.errors import AnalysisError
from persistra.research._validation import datetime_index, numeric_frame
from persistra.research.factor_models import build_factor_risk_model
from persistra.research.model import (
    FactorCovarianceEstimator,
    FactorPortfolioAttribution,
    FactorPortfolioForecast,
    FactorPortfolioForecastStep,
    FactorPortfolioForecastSuccess,
    FactorPortfolioForecastUnavailable,
    FactorRiskModel,
    RollingFactorPortfolioForecastResult,
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
        covariance_estimator=risk_model.covariance_estimator,
        covariance_parameters=risk_model.covariance_parameters,
        shrinkage=risk_model.shrinkage,
        as_of=effective_as_of,
    )


def rolling_factor_portfolio_forecasts(
    exposures: pd.DataFrame,
    factor_returns: pd.DataFrame,
    residual_returns: pd.DataFrame,
    factor_premia: pd.DataFrame,
    *,
    alpha: pd.DataFrame | None = None,
    window: int | None = None,
    minimum_observations: int = 2,
    covariance: FactorCovarianceEstimator | pd.DataFrame = "diagonal_shrinkage",
    shrinkage: float = 0.0,
    ewma_decay: float = 0.94,
) -> RollingFactorPortfolioForecastResult:
    """Build causal rolling or expanding factor forecasts for every supplied date."""
    factors = numeric_frame(factor_returns)
    dates = datetime_index(factors.index, name="factor return index")
    if factors.empty or factors.columns.empty:
        raise AnalysisError("factor returns must not be empty")
    residuals = numeric_frame(residual_returns)
    if not residuals.index.equals(dates):
        raise ValueError("residual returns must use the factor return index")
    premia = numeric_frame(factor_premia)
    if not premia.index.equals(dates) or not premia.columns.equals(factors.columns):
        raise ValueError("factor premia must use the factor return axes")
    alpha_frame = None if alpha is None else numeric_frame(alpha)
    if alpha_frame is not None and (
        not alpha_frame.index.equals(dates)
        or not alpha_frame.columns.equals(residuals.columns)
    ):
        raise ValueError("alpha must use the residual return axes")
    exposure_frame = _rolling_exposure_frame(
        exposures,
        dates=dates,
        assets=residuals.columns,
        factors=factors.columns,
    )
    if window is not None:
        window = require_integer(window, name="window", minimum=2)
    minimum = require_integer(
        minimum_observations,
        name="minimum_observations",
        minimum=2,
    )
    if window is not None and minimum > window:
        raise ValueError("minimum_observations must not exceed window")

    steps: list[FactorPortfolioForecastStep] = []
    diagnostic_rows: list[dict[str, object]] = []
    covariance_parameters = _declared_covariance_parameters(
        covariance,
        shrinkage=shrinkage,
        ewma_decay=ewma_decay,
    )
    estimator: FactorCovarianceEstimator = (
        "supplied" if isinstance(covariance, pd.DataFrame) else covariance
    )
    for end, date in enumerate(dates):
        start = 0 if window is None else max(0, end + 1 - window)
        factor_sample = factors.iloc[start : end + 1]
        residual_sample = residuals.iloc[start : end + 1]
        factor_count = int(factor_sample.dropna().shape[0])
        residual_count = residual_sample.count().astype("int64")
        current_exposures = cast("pd.DataFrame", exposure_frame.xs(date, level="date"))
        current_premia = cast("pd.Series", premia.loc[date])
        current_alpha = (
            None if alpha_frame is None else cast("pd.Series", alpha_frame.loc[date])
        )
        reason = _unavailable_forecast_reason(
            factor_count=factor_count,
            residual_count=residual_count,
            minimum=minimum,
            exposures=current_exposures,
            premia=current_premia,
            alpha=current_alpha,
        )
        if reason is not None:
            step = FactorPortfolioForecastUnavailable(
                date,
                reason,
                factor_count,
                minimum,
                estimator,
                covariance_parameters,
                shrinkage,
            )
        else:
            try:
                risk = build_factor_risk_model(
                    current_exposures,
                    factor_sample,
                    residual_sample,
                    covariance=covariance,
                    shrinkage=shrinkage,
                    ewma_decay=ewma_decay,
                    as_of=date,
                )
                forecast = build_factor_portfolio_forecast(
                    risk,
                    current_premia,
                    alpha=current_alpha,
                )
            except AnalysisError as exc:
                step = FactorPortfolioForecastUnavailable(
                    date,
                    str(exc),
                    factor_count,
                    minimum,
                    estimator,
                    covariance_parameters,
                    shrinkage,
                )
            else:
                step = FactorPortfolioForecastSuccess(date, forecast)
        effective_parameters = (
            step.forecast.covariance_parameters
            if isinstance(step, FactorPortfolioForecastSuccess)
            else step.covariance_parameters
        )
        effective_shrinkage = (
            step.forecast.shrinkage
            if isinstance(step, FactorPortfolioForecastSuccess)
            else step.shrinkage
        )
        steps.append(step)
        diagnostic_rows.append(
            {
                "date": date,
                "status": step.status,
                "reason": "" if isinstance(step, FactorPortfolioForecastSuccess) else step.reason,
                "factor_observations": factor_count,
                "minimum_residual_observations": (
                    int(residual_count.min()) if len(residual_count) else 0
                ),
                "covariance_estimator": estimator,
                "covariance_parameters": dict(effective_parameters),
                "shrinkage": effective_shrinkage,
            }
        )
    diagnostics = pd.DataFrame(diagnostic_rows).set_index("date")
    return RollingFactorPortfolioForecastResult(
        steps=tuple(steps),
        diagnostics=diagnostics,
        window=window,
        minimum_observations=minimum,
        covariance_estimator=estimator,
        covariance_parameters=covariance_parameters,
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


def _rolling_exposure_frame(
    exposures: pd.DataFrame,
    *,
    dates: pd.DatetimeIndex,
    assets: pd.Index,
    factors: pd.Index,
) -> pd.DataFrame:
    result = numeric_frame(exposures)
    if not isinstance(result.index, pd.MultiIndex) or list(result.index.names) != [
        "date",
        "asset",
    ]:
        raise ValueError("rolling exposures must use a (date, asset) index")
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError("rolling exposure index must be unique and sorted")
    if not result.columns.equals(factors):
        raise ValueError("rolling exposure factors must match factor returns")
    exposure_dates = pd.DatetimeIndex(result.index.get_level_values("date").unique())
    if not exposure_dates.equals(dates):
        raise ValueError("rolling exposure dates must match factor returns")
    for date in dates:
        if not result.xs(date, level="date").index.equals(assets):
            raise ValueError("rolling exposure assets must match residual returns on every date")
    return result


def _unavailable_forecast_reason(
    *,
    factor_count: int,
    residual_count: pd.Series,
    minimum: int,
    exposures: pd.DataFrame,
    premia: pd.Series,
    alpha: pd.Series | None,
) -> str | None:
    if factor_count < minimum:
        return "insufficient factor observations"
    if residual_count.lt(minimum).any():
        return "insufficient residual observations"
    if exposures.isna().any(axis=None):
        return "factor exposures are unavailable"
    if premia.isna().any():
        return "factor premia are unavailable"
    if alpha is not None and alpha.isna().any():
        return "asset alpha is unavailable"
    return None


def _declared_covariance_parameters(
    covariance: FactorCovarianceEstimator | pd.DataFrame,
    *,
    shrinkage: float,
    ewma_decay: float,
) -> dict[str, object]:
    if isinstance(shrinkage, bool) or not math.isfinite(shrinkage):
        raise ValueError("shrinkage must be a finite number")
    if not 0.0 <= shrinkage <= 1.0:
        raise ValueError("shrinkage must be between zero and one")
    if isinstance(covariance, pd.DataFrame):
        if shrinkage != 0.0:
            raise ValueError("shrinkage must be zero with supplied covariance")
        return {"source": "caller"}
    if covariance not in {
        "sample",
        "diagonal_shrinkage",
        "constant_correlation",
        "ledoit_wolf",
        "ewma",
    }:
        raise ValueError("unsupported factor covariance estimator")
    if covariance in {"sample", "ledoit_wolf", "ewma"} and shrinkage != 0.0:
        raise ValueError(f"shrinkage must be zero with {covariance} covariance")
    if covariance in {"diagonal_shrinkage", "constant_correlation"}:
        return {"shrinkage": shrinkage}
    if covariance == "ewma":
        if isinstance(ewma_decay, bool) or not math.isfinite(ewma_decay):
            raise ValueError("ewma_decay must be a finite number")
        if not 0.0 < ewma_decay < 1.0:
            raise ValueError("ewma_decay must be strictly between zero and one")
        return {"decay": ewma_decay}
    return {}


def _forecast_as_of(
    risk_as_of: pd.Timestamp | None,
    requested: pd.Timestamp | None,
) -> pd.Timestamp | None:
    if risk_as_of is not None and requested is not None:
        if pd.Timestamp(risk_as_of) != pd.Timestamp(requested):
            raise ValueError("forecast as_of must match the factor risk model")
    selected = risk_as_of if requested is None else requested
    return None if selected is None else pd.Timestamp(selected)
