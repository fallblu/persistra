"""Regression-based factor models with explicit panel alignment."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

import numpy as np
import pandas as pd
from scipy.stats import t as student_t  # pyright: ignore[reportMissingTypeStubs]

from persistra._validation import require_integer
from persistra.errors import AnalysisError
from persistra.research._validation import (
    aligned_panel,
    cross_sectional_frame,
    datetime_index,
    numeric_frame,
)
from persistra.research.model import (
    CrossSectionalFactorModelResult,
    FactorCovarianceEstimator,
    FactorPremiaResult,
    FactorRegressionResult,
    FactorRiskModel,
    FamaMacBethResult,
    ForwardReturnLabels,
    RegressionCovariance,
    RollingFactorRegressionResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

type CrossSectionalCovariance = Literal["classical", "hc3"]
type _SurvivalFunction = Callable[[np.ndarray, float], np.ndarray]

_INTERCEPT = "intercept"
_DIAGNOSTIC_COLUMNS = [
    "observations",
    "rank",
    "degrees_of_freedom",
    "r_squared",
    "adjusted_r_squared",
    "condition_number",
    "status",
]


@dataclass(frozen=True, slots=True)
class _Fit:
    coefficients: np.ndarray
    standard_errors: np.ndarray
    t_statistics: np.ndarray
    p_values: np.ndarray
    fitted: np.ndarray
    residuals: np.ndarray
    observations: int
    rank: int
    degrees_of_freedom: int
    r_squared: float
    adjusted_r_squared: float
    condition_number: float
    status: str


def fit_time_series_factor_model(
    asset_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    *,
    weights: pd.DataFrame | None = None,
    intercept: bool = True,
    covariance: RegressionCovariance = "classical",
    hac_lags: int | None = None,
) -> FactorRegressionResult:
    """Fit one factor-return regression for each asset.

    The two return panels must use the same sorted date index. Missing observations are
    removed independently for each asset. ``weights`` enables weighted least squares and
    must use the asset-return axes. A rank-deficient design retains its least-norm
    coefficients but reports unavailable inference and an explicit diagnostic status.
    """
    assets, factors, checked_weights = _time_series_inputs(
        asset_returns,
        factor_returns,
        weights=weights,
    )
    _validate_covariance(covariance, hac_lags=hac_lags)
    terms = _terms(factors.columns, intercept=intercept)
    coefficients = _term_frame(assets.columns, terms)
    standard_errors = coefficients.copy()
    t_statistics = coefficients.copy()
    p_values = coefficients.copy()
    fitted = pd.DataFrame(np.nan, index=assets.index, columns=assets.columns, dtype=float)
    residuals = fitted.copy()
    diagnostic_rows: list[dict[str, float | int | str]] = []

    factor_values = factors.to_numpy(dtype=float, na_value=np.nan)
    for position, asset in enumerate(assets.columns):
        y = assets.iloc[:, position].to_numpy(dtype=float, na_value=np.nan)
        weight = _weight_values(checked_weights, position)
        valid = np.isfinite(y) & np.isfinite(factor_values).all(axis=1)
        if weight is not None:
            valid &= np.isfinite(weight) & (weight > 0.0)
        x = _design(factor_values[valid], intercept=intercept)
        fit = _fit_regression(
            y[valid],
            x,
            None if weight is None else weight[valid],
            covariance=covariance,
            hac_lags=hac_lags,
        )
        coefficients.loc[asset] = fit.coefficients
        standard_errors.loc[asset] = fit.standard_errors
        t_statistics.loc[asset] = fit.t_statistics
        p_values.loc[asset] = fit.p_values
        fitted.loc[valid, asset] = fit.fitted
        residuals.loc[valid, asset] = fit.residuals
        diagnostic_rows.append(_diagnostics(fit))

    diagnostics = pd.DataFrame(
        diagnostic_rows,
        index=assets.columns.copy(),
        columns=_DIAGNOSTIC_COLUMNS,
    )
    return FactorRegressionResult(
        coefficients=coefficients,
        standard_errors=standard_errors,
        t_statistics=t_statistics,
        p_values=p_values,
        fitted_values=fitted,
        residuals=residuals,
        diagnostics=diagnostics,
        factor_names=tuple(cast("Sequence[str]", factors.columns)),
        intercept=intercept,
        covariance=covariance,
        hac_lags=hac_lags,
    )


def rolling_time_series_factor_model(
    asset_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    *,
    window: int | None,
    minimum_observations: int | None = None,
    weights: pd.DataFrame | None = None,
    intercept: bool = True,
    covariance: RegressionCovariance = "classical",
    hac_lags: int | None = None,
) -> RollingFactorRegressionResult:
    """Fit causal rolling or expanding asset factor regressions.

    A positive ``window`` selects a rolling observation window. ``None`` selects an
    expanding window. Every estimate dated ``t`` uses observations no later than ``t``.
    Rows before the required history remain present with an ``insufficient_observations``
    status.
    """
    assets, factors, checked_weights = _time_series_inputs(
        asset_returns,
        factor_returns,
        weights=weights,
    )
    _validate_covariance(covariance, hac_lags=hac_lags)
    if window is not None:
        window = require_integer(window, name="window", minimum=1)
    term_count = len(factors.columns) + int(intercept)
    minimum = term_count + 1 if minimum_observations is None else minimum_observations
    minimum = require_integer(minimum, name="minimum_observations", minimum=1)
    if minimum <= term_count:
        raise ValueError("minimum_observations must exceed the number of regression terms")
    if window is not None and minimum > window:
        raise ValueError("minimum_observations must not exceed window")

    terms = _terms(factors.columns, intercept=intercept)
    result_index = pd.MultiIndex.from_product(
        [assets.index, assets.columns],
        names=["date", "asset"],
    )
    coefficients = pd.DataFrame(np.nan, index=result_index, columns=terms, dtype=float)
    standard_errors = coefficients.copy()
    t_statistics = coefficients.copy()
    p_values = coefficients.copy()
    diagnostics = pd.DataFrame(index=result_index, columns=_DIAGNOSTIC_COLUMNS)
    factor_values = factors.to_numpy(dtype=float, na_value=np.nan)

    for end in range(len(assets.index)):
        start = 0 if window is None else max(0, end + 1 - window)
        factor_window = factor_values[start : end + 1]
        for asset_position, asset in enumerate(assets.columns):
            y = assets.iloc[start : end + 1, asset_position].to_numpy(
                dtype=float,
                na_value=np.nan,
            )
            weight = _weight_values(checked_weights, asset_position)
            weight_window = None if weight is None else weight[start : end + 1]
            valid = np.isfinite(y) & np.isfinite(factor_window).all(axis=1)
            if weight_window is not None:
                valid &= np.isfinite(weight_window) & (weight_window > 0.0)
            x = _design(factor_window[valid], intercept=intercept)
            fit = _fit_regression(
                y[valid],
                x,
                None if weight_window is None else weight_window[valid],
                covariance=covariance,
                hac_lags=hac_lags,
                minimum_observations=minimum,
            )
            key = (assets.index[end], asset)
            coefficients.loc[key] = fit.coefficients
            standard_errors.loc[key] = fit.standard_errors
            t_statistics.loc[key] = fit.t_statistics
            p_values.loc[key] = fit.p_values
            diagnostics.loc[key] = list(_diagnostics(fit).values())

    diagnostics = diagnostics.infer_objects()
    return RollingFactorRegressionResult(
        coefficients=coefficients,
        standard_errors=standard_errors,
        t_statistics=t_statistics,
        p_values=p_values,
        diagnostics=diagnostics,
        factor_names=tuple(cast("Sequence[str]", factors.columns)),
        intercept=intercept,
        covariance=covariance,
        hac_lags=hac_lags,
        window=window,
        minimum_observations=minimum,
    )


def estimate_cross_sectional_factor_returns(
    asset_returns: pd.DataFrame | ForwardReturnLabels,
    exposures: pd.DataFrame,
    *,
    weights: pd.DataFrame | None = None,
    intercept: bool = True,
    covariance: CrossSectionalCovariance = "hc3",
) -> CrossSectionalFactorModelResult:
    """Estimate one cross-sectional factor-return regression per date.

    ``exposures`` uses a unique, sorted ``(date, asset)`` MultiIndex and one column per
    caller-defined factor. Forward labels retain their horizon in the result. Missing
    returns, exposures, or nonpositive weights are removed for that date only.
    """
    label_horizon = (
        asset_returns.horizon if isinstance(asset_returns, ForwardReturnLabels) else None
    )
    if isinstance(asset_returns, ForwardReturnLabels):
        raw_returns = asset_returns.frame.mask(asset_returns.label_ends.isna(), axis="index")
    else:
        raw_returns = asset_returns
    returns = cross_sectional_frame(raw_returns, name="asset returns")
    exposure_frame = _exposure_frame(exposures, returns=returns)
    checked_weights = _regression_weights(weights, returns)
    if covariance not in {"classical", "hc3"}:
        raise ValueError("cross-sectional covariance must be classical or hc3")
    terms = _terms(exposure_frame.columns, intercept=intercept)
    factor_returns = pd.DataFrame(np.nan, index=returns.index, columns=terms, dtype=float)
    standard_errors = factor_returns.copy()
    t_statistics = factor_returns.copy()
    p_values = factor_returns.copy()
    fitted = pd.DataFrame(np.nan, index=returns.index, columns=returns.columns, dtype=float)
    residuals = fitted.copy()
    diagnostic_rows: list[dict[str, float | int | str]] = []

    for date_position, date in enumerate(returns.index):
        day = exposure_frame.xs(date, level="date").reindex(returns.columns)
        y = returns.iloc[date_position].to_numpy(dtype=float, na_value=np.nan)
        x_values = day.to_numpy(dtype=float, na_value=np.nan)
        weight = (
            None
            if checked_weights is None
            else checked_weights.iloc[date_position].to_numpy(dtype=float, na_value=np.nan)
        )
        valid = np.isfinite(y) & np.isfinite(x_values).all(axis=1)
        if weight is not None:
            valid &= np.isfinite(weight) & (weight > 0.0)
        x = _design(x_values[valid], intercept=intercept)
        fit = _fit_regression(
            y[valid],
            x,
            None if weight is None else weight[valid],
            covariance=covariance,
            hac_lags=None,
        )
        factor_returns.loc[date] = fit.coefficients
        standard_errors.loc[date] = fit.standard_errors
        t_statistics.loc[date] = fit.t_statistics
        p_values.loc[date] = fit.p_values
        fitted.loc[date, valid] = fit.fitted
        residuals.loc[date, valid] = fit.residuals
        diagnostic_rows.append(_diagnostics(fit))

    diagnostics = pd.DataFrame(
        diagnostic_rows,
        index=returns.index.copy(),
        columns=_DIAGNOSTIC_COLUMNS,
    )
    return CrossSectionalFactorModelResult(
        factor_returns=factor_returns,
        standard_errors=standard_errors,
        t_statistics=t_statistics,
        p_values=p_values,
        fitted_values=fitted,
        residuals=residuals,
        diagnostics=diagnostics,
        factor_names=tuple(cast("Sequence[str]", exposure_frame.columns)),
        intercept=intercept,
        covariance=covariance,
        label_horizon=label_horizon,
    )


def summarize_factor_premia(
    factor_returns: pd.DataFrame,
    *,
    covariance: Literal["classical", "newey_west"] = "newey_west",
    hac_lags: int | None = None,
) -> FactorPremiaResult:
    """Estimate average premia and classical or Newey-West inference."""
    factors = _factor_return_frame(
        factor_returns,
        name="factor returns",
        allow_intercept=True,
    )
    _validate_covariance(covariance, hac_lags=hac_lags)
    rows: list[dict[str, float | int | str]] = []
    for factor in factors.columns:
        values = factors[factor].to_numpy(dtype=float, na_value=np.nan)
        valid = np.isfinite(values)
        y = values[valid]
        x = np.ones((len(y), 1), dtype=float)
        fit = _fit_regression(
            y,
            x,
            None,
            covariance=covariance,
            hac_lags=hac_lags,
        )
        rows.append(
            {
                "premium": fit.coefficients[0],
                "standard_error": fit.standard_errors[0],
                "t_statistic": fit.t_statistics[0],
                "p_value": fit.p_values[0],
                "periods": fit.observations,
                "status": fit.status,
            }
        )
    statistics = pd.DataFrame(rows, index=factors.columns.copy())
    return FactorPremiaResult(
        statistics=statistics,
        factor_returns=factors,
        covariance=covariance,
        hac_lags=hac_lags,
    )


def fama_macbeth_regression(
    labels: ForwardReturnLabels,
    exposures: pd.DataFrame,
    *,
    weights: pd.DataFrame | None = None,
    intercept: bool = True,
    cross_sectional_covariance: CrossSectionalCovariance = "hc3",
    hac_lags: int | None = None,
) -> FamaMacBethResult:
    """Run cross-sectional regressions and summarize their factor premia."""
    cross_sectional = estimate_cross_sectional_factor_returns(
        labels,
        exposures,
        weights=weights,
        intercept=intercept,
        covariance=cross_sectional_covariance,
    )
    premia = summarize_factor_premia(
        cross_sectional.factor_returns,
        covariance="newey_west",
        hac_lags=hac_lags,
    )
    return FamaMacBethResult(cross_sectional=cross_sectional, premia=premia)


def build_factor_risk_model(
    exposures: pd.DataFrame,
    factor_returns: pd.DataFrame,
    residual_returns: pd.DataFrame,
    *,
    shrinkage: float = 0.0,
    covariance: FactorCovarianceEstimator | pd.DataFrame = "diagonal_shrinkage",
    ewma_decay: float = 0.94,
    window: int | None = None,
    as_of: pd.Timestamp | None = None,
) -> FactorRiskModel:
    """Build an asset covariance matrix with one explicit factor covariance policy."""
    exposure_frame = numeric_frame(exposures)
    if exposure_frame.empty:
        raise AnalysisError("factor exposures must not be empty")
    _plain_axis(exposure_frame.index, name="factor exposure asset index")
    _factor_columns(exposure_frame.columns)
    if exposure_frame.isna().any(axis=None):
        raise AnalysisError("factor exposures must be complete")
    factors = _factor_return_frame(factor_returns, name="factor returns")
    if not factors.columns.equals(exposure_frame.columns):
        raise ValueError("factor returns must match factor exposure columns")
    residuals = cross_sectional_frame(residual_returns, name="residual returns")
    if not residuals.columns.equals(exposure_frame.index):
        raise ValueError("residual-return columns must match factor exposure assets")
    if not residuals.index.equals(factors.index):
        raise ValueError("factor and residual returns must use the same date index")
    shrink = _unit_interval(shrinkage, name="shrinkage")
    if window is not None:
        window = require_integer(window, name="window", minimum=2)
    factor_sample = factors if window is None else factors.iloc[-window:]
    residual_sample = residuals if window is None else residuals.iloc[-window:]
    effective_as_of = _factor_risk_as_of(
        cast("pd.DatetimeIndex", factor_sample.index),
        as_of,
    )
    complete_factor_sample = factor_sample.dropna()
    if not isinstance(covariance, pd.DataFrame) and len(complete_factor_sample) < 2:
        raise AnalysisError("factor covariance requires at least two complete observations")
    shrunk, estimator, parameters, effective_shrinkage = _estimate_factor_covariance(
        complete_factor_sample,
        covariance=covariance,
        shrinkage=shrink,
        ewma_decay=ewma_decay,
        factors=exposure_frame.columns,
    )
    factor_covariance = pd.DataFrame(
        shrunk,
        index=exposure_frame.columns.copy(),
        columns=exposure_frame.columns.copy(),
    )
    idiosyncratic = residual_sample.var(axis="index", ddof=1)
    residual_observations = residual_sample.count().astype("int64")
    if idiosyncratic.isna().any() or (idiosyncratic < 0.0).any():
        raise AnalysisError(
            "idiosyncratic variance requires two residual observations for every asset"
        )
    beta = exposure_frame.to_numpy(dtype=float)
    asset_values = beta @ shrunk @ beta.T + np.diag(idiosyncratic.to_numpy(dtype=float))
    asset_covariance = pd.DataFrame(
        asset_values,
        index=exposure_frame.index.copy(),
        columns=exposure_frame.index.copy(),
    )
    return FactorRiskModel(
        exposures=exposure_frame,
        factor_covariance=factor_covariance,
        idiosyncratic_variance=idiosyncratic,
        asset_covariance=asset_covariance,
        shrinkage=effective_shrinkage,
        covariance_estimator=estimator,
        covariance_parameters=parameters,
        factor_observations=len(complete_factor_sample),
        residual_observations=residual_observations,
        as_of=effective_as_of,
    )


def _estimate_factor_covariance(
    sample: pd.DataFrame,
    *,
    covariance: FactorCovarianceEstimator | pd.DataFrame,
    shrinkage: float,
    ewma_decay: float,
    factors: pd.Index,
) -> tuple[np.ndarray, FactorCovarianceEstimator, dict[str, float | str], float]:
    if isinstance(covariance, pd.DataFrame):
        if shrinkage != 0.0:
            raise ValueError("shrinkage must be zero with supplied covariance")
        supplied = _supplied_covariance(covariance, factors)
        return supplied, "supplied", {"source": "caller"}, 0.0
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
    values = sample.to_numpy(dtype=float)
    if covariance == "ewma":
        decay = _unit_interval(ewma_decay, name="ewma_decay")
        if decay == 0.0 or decay == 1.0:
            raise ValueError("ewma_decay must be strictly between zero and one")
        weights = np.power(decay, np.arange(len(values) - 1, -1, -1, dtype=float))
        weights /= weights.sum()
        mean = np.average(values, axis=0, weights=weights)
        centered = values - mean
        estimated = centered.T @ (centered * weights[:, None])
        return estimated, covariance, {"decay": decay}, 0.0
    sample_covariance = np.cov(values, rowvar=False, ddof=1)
    sample_covariance = np.atleast_2d(np.asarray(sample_covariance, dtype=float))
    if covariance == "sample":
        return sample_covariance, covariance, {}, 0.0
    if covariance == "diagonal_shrinkage":
        diagonal = np.diag(np.diag(sample_covariance))
        estimated = ((1.0 - shrinkage) * sample_covariance) + (shrinkage * diagonal)
        return estimated, covariance, {"shrinkage": shrinkage}, shrinkage
    if covariance == "constant_correlation":
        target = _constant_correlation_target(sample_covariance)
        estimated = ((1.0 - shrinkage) * sample_covariance) + (shrinkage * target)
        return estimated, covariance, {"shrinkage": shrinkage}, shrinkage
    estimated, intensity = _ledoit_wolf(values)
    return estimated, covariance, {"shrinkage": intensity}, intensity


def _constant_correlation_target(covariance: np.ndarray) -> np.ndarray:
    standard_deviation = np.sqrt(np.maximum(np.diag(covariance), 0.0))
    denominator = np.outer(standard_deviation, standard_deviation)
    correlation = np.divide(
        covariance,
        denominator,
        out=np.zeros_like(covariance),
        where=denominator > 0.0,
    )
    off_diagonal = correlation[~np.eye(len(correlation), dtype=bool)]
    average = float(off_diagonal.mean()) if len(off_diagonal) else 0.0
    target = average * denominator
    np.fill_diagonal(target, np.diag(covariance))
    return target


def _ledoit_wolf(values: np.ndarray) -> tuple[np.ndarray, float]:
    centered = values - values.mean(axis=0)
    observations = len(centered)
    empirical = centered.T @ centered / observations
    mean_variance = float(np.trace(empirical) / empirical.shape[0])
    target = np.eye(empirical.shape[0]) * mean_variance
    delta = float(np.square(empirical - target).sum())
    if delta <= np.finfo(float).eps:
        return empirical, 0.0
    beta = sum(
        float(np.square(np.outer(row, row) - empirical).sum()) for row in centered
    ) / (observations**2)
    intensity = min(max(beta / delta, 0.0), 1.0)
    return ((1.0 - intensity) * empirical) + (intensity * target), intensity


def _supplied_covariance(covariance: pd.DataFrame, factors: pd.Index) -> np.ndarray:
    supplied = numeric_frame(covariance)
    if not supplied.index.equals(factors) or not supplied.columns.equals(factors):
        raise ValueError("supplied covariance must use the factor axes")
    if supplied.isna().any(axis=None):
        raise AnalysisError("supplied covariance must be complete")
    values = supplied.to_numpy(dtype=float)
    if not np.allclose(values, values.T, rtol=1e-10, atol=1e-12):
        raise AnalysisError("supplied covariance must be symmetric")
    if np.linalg.eigvalsh(values).min() < -1e-12:
        raise AnalysisError("supplied covariance must be positive semidefinite")
    return values


def _factor_risk_as_of(
    sample_index: pd.DatetimeIndex,
    as_of: pd.Timestamp | None,
) -> pd.Timestamp:
    """Validate and return the point-in-time boundary for an aligned sample."""
    sample_end = sample_index[-1]
    if as_of is None:
        return sample_end
    result = pd.Timestamp(as_of)
    if pd.isna(result):
        raise ValueError("as_of must not be missing")
    if (result.tz is None) != (sample_index.tz is None):
        raise ValueError("as_of must use the same timezone awareness as the return history")
    if result < sample_end:
        raise ValueError("as_of must not precede the return history boundary")
    return result


def _time_series_inputs(
    asset_returns: pd.DataFrame,
    factor_returns: pd.DataFrame,
    *,
    weights: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    assets = cross_sectional_frame(asset_returns, name="asset returns")
    factors = _factor_return_frame(factor_returns, name="factor returns")
    if not assets.index.equals(factors.index):
        raise ValueError("asset and factor returns must use the same date index")
    return assets, factors, _regression_weights(weights, assets)


def _factor_return_frame(
    frame: pd.DataFrame,
    *,
    name: str,
    allow_intercept: bool = False,
) -> pd.DataFrame:
    result = numeric_frame(frame)
    datetime_index(result.index, name=f"{name} index")
    _factor_columns(result.columns, allow_intercept=allow_intercept)
    if result.empty or len(result.columns) == 0:
        raise AnalysisError(f"{name} must not be empty")
    return result


def _factor_columns(columns: pd.Index, *, allow_intercept: bool = False) -> None:
    if columns.hasnans or not columns.is_unique:
        raise ValueError("factor columns must be unique and nonmissing")
    if any(not isinstance(value, str) or not value for value in columns):
        raise TypeError("factor names must be nonempty strings")
    if not allow_intercept and _INTERCEPT in columns:
        raise ValueError(f"factor name {_INTERCEPT!r} is reserved")


def _plain_axis(index: pd.Index, *, name: str) -> None:
    if index.hasnans or not index.is_unique:
        raise ValueError(f"{name} must be unique and nonmissing")


def _regression_weights(
    weights: pd.DataFrame | None,
    returns: pd.DataFrame,
) -> pd.DataFrame | None:
    if weights is None:
        return None
    result = numeric_frame(aligned_panel(weights, returns, name="regression weights"))
    values = result.to_numpy(dtype=float, na_value=np.nan)
    if (values[np.isfinite(values)] <= 0.0).any():
        raise AnalysisError("observed regression weights must be positive")
    return result


def _exposure_frame(exposures: pd.DataFrame, *, returns: pd.DataFrame) -> pd.DataFrame:
    result = numeric_frame(exposures)
    if not isinstance(result.index, pd.MultiIndex) or result.index.nlevels != 2:
        raise TypeError("factor exposures must use a (date, asset) MultiIndex")
    if list(result.index.names) != ["date", "asset"]:
        raise ValueError("factor exposure index levels must be named date and asset")
    if result.index.has_duplicates or not result.index.is_monotonic_increasing:
        raise ValueError("factor exposure index must be unique and sorted")
    dates = pd.DatetimeIndex(result.index.get_level_values("date").unique())
    if not dates.equals(returns.index):
        raise ValueError("factor exposure dates must match the return index")
    assets = pd.Index(result.index.get_level_values("asset").unique())
    unknown = [asset for asset in assets if asset not in returns.columns]
    if unknown:
        raise ValueError("factor exposures contain assets outside the return universe")
    _factor_columns(result.columns)
    return result


def _terms(factors: pd.Index, *, intercept: bool) -> pd.Index:
    values = ([_INTERCEPT] if intercept else []) + [str(value) for value in factors]
    return pd.Index(values, name="term")


def _term_frame(index: pd.Index, terms: pd.Index) -> pd.DataFrame:
    return pd.DataFrame(np.nan, index=index.copy(), columns=terms, dtype=float)


def _weight_values(weights: pd.DataFrame | None, position: int) -> np.ndarray | None:
    if weights is None:
        return None
    return weights.iloc[:, position].to_numpy(dtype=float, na_value=np.nan)


def _design(factors: np.ndarray, *, intercept: bool) -> np.ndarray:
    if not intercept:
        return factors
    return np.column_stack((np.ones(len(factors), dtype=float), factors))


def _fit_regression(
    y: np.ndarray,
    x: np.ndarray,
    weights: np.ndarray | None,
    *,
    covariance: RegressionCovariance,
    hac_lags: int | None,
    minimum_observations: int | None = None,
) -> _Fit:
    observations = len(y)
    terms = x.shape[1]
    required = terms if minimum_observations is None else minimum_observations
    empty = np.full(terms, np.nan, dtype=float)
    if observations < required or observations < terms:
        return _Fit(
            coefficients=empty.copy(),
            standard_errors=empty.copy(),
            t_statistics=empty.copy(),
            p_values=empty.copy(),
            fitted=np.full(observations, np.nan),
            residuals=np.full(observations, np.nan),
            observations=observations,
            rank=int(np.linalg.matrix_rank(x)) if observations else 0,
            degrees_of_freedom=max(0, observations - terms),
            r_squared=math.nan,
            adjusted_r_squared=math.nan,
            condition_number=math.nan,
            status="insufficient_observations",
        )
    sqrt_weight = np.ones(observations) if weights is None else np.sqrt(weights)
    x_weighted = x * sqrt_weight[:, None]
    y_weighted = y * sqrt_weight
    coefficients, _sum, rank, singular = np.linalg.lstsq(x_weighted, y_weighted, rcond=None)
    fitted = x @ coefficients
    residuals = y - fitted
    degrees = observations - int(rank)
    condition = _condition_number(singular)
    r_squared = _weighted_r_squared(y, residuals, sqrt_weight)
    adjusted = (
        math.nan
        if degrees <= 0 or not math.isfinite(r_squared)
        else 1.0 - ((1.0 - r_squared) * (observations - 1) / degrees)
    )
    if rank < terms:
        inference = empty.copy()
        return _Fit(
            coefficients=coefficients,
            standard_errors=inference.copy(),
            t_statistics=inference.copy(),
            p_values=inference.copy(),
            fitted=fitted,
            residuals=residuals,
            observations=observations,
            rank=int(rank),
            degrees_of_freedom=degrees,
            r_squared=r_squared,
            adjusted_r_squared=adjusted,
            condition_number=condition,
            status="rank_deficient",
        )
    if degrees <= 0:
        inference = empty.copy()
        return _Fit(
            coefficients=coefficients,
            standard_errors=inference.copy(),
            t_statistics=inference.copy(),
            p_values=inference.copy(),
            fitted=fitted,
            residuals=residuals,
            observations=observations,
            rank=int(rank),
            degrees_of_freedom=degrees,
            r_squared=r_squared,
            adjusted_r_squared=adjusted,
            condition_number=condition,
            status="no_residual_degrees_of_freedom",
        )
    covariance_matrix = _coefficient_covariance(
        x_weighted,
        residuals * sqrt_weight,
        covariance=covariance,
        degrees_of_freedom=degrees,
        hac_lags=hac_lags,
    )
    standard_errors = np.sqrt(np.maximum(np.diag(covariance_matrix), 0.0))
    t_statistics = np.divide(
        coefficients,
        standard_errors,
        out=np.full_like(coefficients, np.nan),
        where=standard_errors > 0.0,
    )
    survival = cast(
        "_SurvivalFunction",
        student_t.sf,  # pyright: ignore[reportUnknownMemberType]
    )
    p_values = np.asarray(
        2.0 * survival(np.abs(t_statistics), float(max(degrees, 1))),
        dtype=float,
    )
    return _Fit(
        coefficients=coefficients,
        standard_errors=standard_errors,
        t_statistics=t_statistics,
        p_values=p_values,
        fitted=fitted,
        residuals=residuals,
        observations=observations,
        rank=int(rank),
        degrees_of_freedom=degrees,
        r_squared=r_squared,
        adjusted_r_squared=adjusted,
        condition_number=condition,
        status="ok",
    )


def _coefficient_covariance(
    x: np.ndarray,
    residuals: np.ndarray,
    *,
    covariance: RegressionCovariance,
    degrees_of_freedom: int,
    hac_lags: int | None,
) -> np.ndarray:
    bread = np.linalg.inv(x.T @ x)
    if covariance == "classical":
        scale = np.dot(residuals, residuals) / degrees_of_freedom
        return bread * scale
    scores = x * residuals[:, None]
    if covariance == "hc3":
        leverage = np.einsum("ij,jk,ik->i", x, bread, x)
        adjusted = np.divide(
            scores,
            np.maximum(1.0 - leverage, np.finfo(float).eps)[:, None],
        )
        return bread @ (adjusted.T @ adjusted) @ bread
    lag_count = _resolved_hac_lags(len(x), hac_lags)
    meat = scores.T @ scores
    for lag in range(1, lag_count + 1):
        weight = 1.0 - (lag / (lag_count + 1.0))
        cross = scores[lag:].T @ scores[:-lag]
        meat += weight * (cross + cross.T)
    return bread @ meat @ bread


def _weighted_r_squared(y: np.ndarray, residuals: np.ndarray, sqrt_weight: np.ndarray) -> float:
    centered = (y - np.average(y, weights=np.square(sqrt_weight))) * sqrt_weight
    total = float(centered @ centered)
    if total <= np.finfo(float).eps:
        return math.nan
    return 1.0 - (float((residuals * sqrt_weight) @ (residuals * sqrt_weight)) / total)


def _condition_number(singular_values: np.ndarray) -> float:
    if len(singular_values) == 0 or singular_values[-1] <= np.finfo(float).eps:
        return math.inf
    return float(singular_values[0] / singular_values[-1])


def _diagnostics(fit: _Fit) -> dict[str, float | int | str]:
    return {
        "observations": fit.observations,
        "rank": fit.rank,
        "degrees_of_freedom": fit.degrees_of_freedom,
        "r_squared": fit.r_squared,
        "adjusted_r_squared": fit.adjusted_r_squared,
        "condition_number": fit.condition_number,
        "status": fit.status,
    }


def _validate_covariance(covariance: str, *, hac_lags: int | None) -> None:
    if covariance not in {"classical", "hc3", "newey_west"}:
        raise ValueError("unsupported regression covariance")
    if hac_lags is not None:
        require_integer(hac_lags, name="hac_lags", minimum=0)
    if covariance != "newey_west" and hac_lags is not None:
        raise ValueError("hac_lags requires newey_west covariance")


def _resolved_hac_lags(observations: int, hac_lags: int | None) -> int:
    if hac_lags is not None:
        return min(hac_lags, max(0, observations - 1))
    automatic = math.floor(4.0 * ((observations / 100.0) ** (2.0 / 9.0)))
    return min(automatic, max(0, observations - 1))


def _unit_interval(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be between zero and one")
    return result
