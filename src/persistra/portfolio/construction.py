"""Transparent target-weight construction for portfolio research."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal, cast

import numpy as np
import pandas as pd

from persistra.errors import AnalysisError
from persistra.portfolio._validation import asset_panel, datetime_index, finite_scalar
from persistra.portfolio.model import (
    PortfolioConfiguration,
    PortfolioConstraints,
    PortfolioConstructionResult,
    PortfolioRiskControl,
    WeightingMethod,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def rebalance_schedule(
    index: pd.DatetimeIndex,
    *,
    frequency: Literal["daily", "weekly", "monthly", "quarterly"] | int,
    anchor: Literal["start", "end"] = "end",
) -> pd.DatetimeIndex:
    """Select deterministic observation dates for a rebalance schedule.

    Calendar schedules choose the first or last supplied observation in each calendar
    bucket. An integer schedule chooses every ``frequency`` observations starting with the
    first observation; its anchor must be ``"start"``.
    """
    dates = datetime_index(index, name="schedule index")
    if anchor not in {"start", "end"}:
        raise ValueError("anchor must be start or end")
    if isinstance(frequency, bool):
        raise TypeError("frequency must be a supported name or positive integer")
    if isinstance(frequency, int):
        if frequency <= 0:
            raise ValueError("integer frequency must be positive")
        if anchor != "start":
            raise ValueError("integer schedules require anchor='start'")
        return dates[::frequency].copy()
    if frequency not in {"daily", "weekly", "monthly", "quarterly"}:
        raise ValueError("unsupported rebalance frequency")
    if frequency == "daily" or len(dates) == 0:
        return dates.copy()

    keys: list[tuple[int, ...]] = []
    if frequency == "weekly":
        calendar = dates.isocalendar()
        keys = list(zip(calendar["year"].astype(int), calendar["week"].astype(int), strict=True))
    elif frequency == "monthly":
        keys = list(zip(dates.year, dates.month, strict=True))
    else:
        keys = list(zip(dates.year, ((dates.month - 1) // 3) + 1, strict=True))

    positions: list[int] = []
    group_start = 0
    for position in range(1, len(dates) + 1):
        if position == len(dates) or keys[position] != keys[group_start]:
            positions.append(group_start if anchor == "start" else position - 1)
            group_start = position
    return dates.take(positions)


def construct_portfolio(
    signals: pd.DataFrame,
    *,
    weighting: WeightingMethod = "equal",
    configuration: PortfolioConfiguration = "long_only",
    gross_target: float = 1.0,
    net_target: float | None = None,
    constraints: PortfolioConstraints | None = None,
    covariances: Mapping[pd.Timestamp, pd.DataFrame] | None = None,
    risk_control: PortfolioRiskControl | None = None,
    initial_weights: pd.Series | None = None,
) -> PortfolioConstructionResult:
    """Construct date-by-asset targets from an explicit signal panel.

    Equal weighting ignores signal magnitude. In long-only mode, every observed asset is
    eligible. In long-short mode, signal signs define sides. Signal-proportional weighting
    uses positive signals for long-only portfolios and absolute signal magnitude within each
    side for long-short portfolios.

    Position limits use deterministic capped redistribution within each side. Volatility
    controls scale the whole risky portfolio and never change relative asset weights. A
    turnover limit blends each desired target with the preceding target. Infeasible exposure,
    side-capacity, covariance, or interacting risk constraints raise ``AnalysisError``.
    """
    panel = asset_panel(signals, name="signal panel")
    if weighting not in {"equal", "signal_proportional"}:
        raise ValueError("unsupported weighting method")
    if configuration not in {"long_only", "long_short"}:
        raise ValueError("unsupported portfolio configuration")
    gross = finite_scalar(gross_target, name="gross_target", minimum=0.0)
    if net_target is None:
        net = gross if configuration == "long_only" else 0.0
    else:
        net = finite_scalar(net_target, name="net_target")
    limits = constraints or PortfolioConstraints()
    _validate_requested_exposure(
        gross,
        net,
        configuration=configuration,
        constraints=limits,
    )
    if risk_control is not None and covariances is None:
        raise ValueError("risk_control requires covariances")
    effective_risk = risk_control
    if covariances is not None and effective_risk is None:
        effective_risk = PortfolioRiskControl()

    previous = _initial_weights(initial_weights, panel.columns, constraints=limits)
    raw_rows: list[np.ndarray] = []
    final_rows: list[np.ndarray] = []
    cash_values: list[float] = []
    turnover_values: list[float] = []
    volatility_values: list[float] = []
    contribution_rows: list[np.ndarray] = []
    exposure_rows: list[dict[str, float]] = []
    utilization_rows: list[dict[str, float]] = []

    for position in range(len(panel.index)):
        date = cast("pd.Timestamp", panel.index[position])
        row = panel.iloc[position]
        raw = _unconstrained_row(
            row.to_numpy(dtype=float),
            weighting=weighting,
            configuration=configuration,
            gross=gross,
            net=net,
            date=date,
        )
        desired = _constrained_sides(
            raw,
            gross=gross,
            net=net,
            position_limit=limits.position_limit,
            tolerance=limits.tolerance,
            date=date,
        )
        covariance: np.ndarray | None = None
        if covariances is not None:
            try:
                supplied = covariances[date]
            except KeyError as error:
                raise ValueError(f"covariance is missing for {date}") from error
            assert effective_risk is not None
            covariance = _covariance_matrix(
                supplied,
                panel.columns,
                tolerance=effective_risk.covariance_tolerance,
                date=date,
            )
            desired = _apply_risk_control(
                desired,
                covariance,
                constraints=limits,
                risk_control=effective_risk,
                date=date,
            )

        desired_cash = 1.0 - float(desired.sum())
        previous_cash = 1.0 - float(previous.sum())
        requested_turnover = _turnover(previous, desired, previous_cash, desired_cash)
        if limits.turnover_limit is not None and requested_turnover > limits.turnover_limit:
            blend = limits.turnover_limit / requested_turnover
            final = previous + blend * (desired - previous)
        else:
            final = desired
        final_cash = 1.0 - float(final.sum())
        turnover = _turnover(previous, final, previous_cash, final_cash)
        _validate_final_constraints(final, constraints=limits, date=date)

        predicted = np.nan
        contributions = np.full(len(panel.columns), np.nan, dtype=float)
        if covariance is not None:
            assert effective_risk is not None
            predicted = _annualized_volatility(
                final,
                covariance,
                periods_per_year=effective_risk.periods_per_year,
            )
            if (
                effective_risk.volatility_limit is not None
                and predicted > effective_risk.volatility_limit + limits.tolerance
            ):
                raise AnalysisError(
                    f"turnover and volatility constraints are infeasible on {date}"
                )
            variance = float(final @ covariance @ final)
            if variance > effective_risk.covariance_tolerance:
                contributions = final * (covariance @ final) / variance

        exposures = _exposures(final, final_cash)
        raw_rows.append(raw)
        final_rows.append(final)
        cash_values.append(final_cash)
        turnover_values.append(turnover)
        volatility_values.append(predicted)
        contribution_rows.append(contributions)
        exposure_rows.append(exposures)
        utilization_rows.append(
            _constraint_utilization(
                final,
                exposures=exposures,
                turnover=turnover,
                predicted_volatility=predicted,
                constraints=limits,
                risk_control=effective_risk,
            )
        )
        previous = final

    index = panel.index
    columns = panel.columns
    weights = pd.DataFrame(final_rows, index=index, columns=columns)
    raw_weights = pd.DataFrame(raw_rows, index=index, columns=columns)
    cash = pd.Series(cash_values, index=index, name="cash", dtype=float)
    turnover_series = pd.Series(turnover_values, index=index, name="turnover", dtype=float)
    predicted_series = pd.Series(
        volatility_values,
        index=index,
        name="predicted_volatility",
        dtype=float,
    )
    risk_contributions = pd.DataFrame(contribution_rows, index=index, columns=columns)
    exposures_frame = pd.DataFrame(exposure_rows, index=index)
    utilization = pd.DataFrame(utilization_rows, index=index)
    return PortfolioConstructionResult(
        weights=weights,
        unconstrained_weights=raw_weights,
        cash=cash,
        exposures=exposures_frame,
        turnover=turnover_series,
        predicted_volatility=predicted_series,
        risk_contributions=risk_contributions,
        constraint_utilization=utilization,
        weighting=weighting,
        configuration=configuration,
        gross_target=gross,
        net_target=net,
        constraints=limits,
        risk_control=effective_risk,
    )


def _validate_requested_exposure(
    gross: float,
    net: float,
    *,
    configuration: PortfolioConfiguration,
    constraints: PortfolioConstraints,
) -> None:
    tolerance = constraints.tolerance
    if abs(net) > gross + tolerance:
        raise AnalysisError("absolute net target must not exceed gross target")
    if configuration == "long_only" and (
        net < -tolerance or not np.isclose(net, gross, atol=tolerance, rtol=0.0)
    ):
        raise AnalysisError("long-only portfolios require net_target equal to gross_target")
    if gross > constraints.gross_limit + tolerance:
        raise AnalysisError("gross target exceeds gross limit")
    if net < constraints.net_minimum - tolerance or net > constraints.net_maximum + tolerance:
        raise AnalysisError("net target is outside the net constraints")


def _initial_weights(
    initial: pd.Series | None,
    columns: pd.Index,
    *,
    constraints: PortfolioConstraints,
) -> np.ndarray:
    if initial is None:
        return np.zeros(len(columns), dtype=float)
    if not initial.index.equals(columns):
        raise ValueError("initial_weights must use the signal columns")
    values = initial.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise AnalysisError("initial_weights must be finite")
    _validate_final_constraints(values, constraints=constraints, date=None)
    return values.copy()


def _unconstrained_row(
    signals: np.ndarray,
    *,
    weighting: WeightingMethod,
    configuration: PortfolioConfiguration,
    gross: float,
    net: float,
    date: pd.Timestamp,
) -> np.ndarray:
    result = np.zeros(len(signals), dtype=float)
    if gross == 0:
        return result
    observed = ~np.isnan(signals)
    long_budget = gross if configuration == "long_only" else (gross + net) / 2.0
    short_budget = 0.0 if configuration == "long_only" else (gross - net) / 2.0
    if configuration == "long_only":
        long_mask = observed if weighting == "equal" else observed & (signals > 0)
    else:
        long_mask = observed & (signals > 0)
    short_mask = observed & (signals < 0)
    if long_budget > 0:
        long_scores = np.ones(len(signals)) if weighting == "equal" else np.maximum(signals, 0)
        result += _allocate_uncapped(
            long_scores,
            long_mask,
            budget=long_budget,
            side="long",
            date=date,
        )
    if short_budget > 0:
        short_scores = np.ones(len(signals)) if weighting == "equal" else np.maximum(-signals, 0)
        result -= _allocate_uncapped(
            short_scores,
            short_mask,
            budget=short_budget,
            side="short",
            date=date,
        )
    return result


def _allocate_uncapped(
    scores: np.ndarray,
    mask: np.ndarray,
    *,
    budget: float,
    side: str,
    date: pd.Timestamp,
) -> np.ndarray:
    result = np.zeros(len(scores), dtype=float)
    total = float(scores[mask].sum())
    if not mask.any() or total <= 0:
        raise AnalysisError(f"{side} side has no eligible assets on {date}")
    result[mask] = budget * scores[mask] / total
    return result


def _constrained_sides(
    raw: np.ndarray,
    *,
    gross: float,
    net: float,
    position_limit: float,
    tolerance: float,
    date: pd.Timestamp,
) -> np.ndarray:
    long_budget = (gross + net) / 2.0
    short_budget = (gross - net) / 2.0
    result = np.zeros(len(raw), dtype=float)
    if long_budget > tolerance:
        result += _capped_allocation(
            np.maximum(raw, 0),
            budget=long_budget,
            limit=position_limit,
            tolerance=tolerance,
            side="long",
            date=date,
        )
    if short_budget > tolerance:
        result -= _capped_allocation(
            np.maximum(-raw, 0),
            budget=short_budget,
            limit=position_limit,
            tolerance=tolerance,
            side="short",
            date=date,
        )
    return result


def _capped_allocation(
    scores: np.ndarray,
    *,
    budget: float,
    limit: float,
    tolerance: float,
    side: str,
    date: pd.Timestamp,
) -> np.ndarray:
    result = np.zeros(len(scores), dtype=float)
    active = np.flatnonzero(scores > 0)
    if len(active) * limit < budget - tolerance:
        raise AnalysisError(f"{side} position capacity is infeasible on {date}")
    remaining = budget
    while len(active) > 0 and remaining > tolerance:
        active_scores = scores[active]
        proposal = remaining * active_scores / float(active_scores.sum())
        capped = proposal > limit + tolerance
        if not capped.any():
            result[active] = proposal
            remaining = 0.0
            break
        capped_positions = active[capped]
        result[capped_positions] = limit
        remaining -= limit * len(capped_positions)
        active = active[~capped]
    if remaining > tolerance:
        raise AnalysisError(f"{side} position capacity is infeasible on {date}")
    return result


def _covariance_matrix(
    covariance: pd.DataFrame,
    columns: pd.Index,
    *,
    tolerance: float,
    date: pd.Timestamp,
) -> np.ndarray:
    if not covariance.index.equals(columns) or not covariance.columns.equals(columns):
        raise ValueError(f"covariance axes differ from the signal columns on {date}")
    if any(not pd.api.types.is_numeric_dtype(dtype) for dtype in covariance.dtypes):
        raise AnalysisError(f"covariance must be numeric on {date}")
    values = covariance.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise AnalysisError(f"covariance must be finite on {date}")
    if not np.allclose(values, values.T, atol=tolerance, rtol=0.0):
        raise AnalysisError(f"covariance must be symmetric on {date}")
    eigenvalues = np.linalg.eigvalsh((values + values.T) / 2.0)
    if float(eigenvalues.min()) < -tolerance:
        raise AnalysisError(f"covariance must be positive semidefinite on {date}")
    return values


def _apply_risk_control(
    weights: np.ndarray,
    covariance: np.ndarray,
    *,
    constraints: PortfolioConstraints,
    risk_control: PortfolioRiskControl,
    date: pd.Timestamp,
) -> np.ndarray:
    volatility = _annualized_volatility(
        weights,
        covariance,
        periods_per_year=risk_control.periods_per_year,
    )
    desired_scale = 1.0
    if risk_control.target_volatility is not None:
        if volatility <= risk_control.covariance_tolerance:
            if risk_control.target_volatility > risk_control.covariance_tolerance:
                raise AnalysisError(f"positive volatility target is infeasible on {date}")
            desired_scale = 0.0
        else:
            desired_scale = risk_control.target_volatility / volatility
    if risk_control.volatility_limit is not None and volatility * desired_scale > (
        risk_control.volatility_limit
    ):
        desired_scale = risk_control.volatility_limit / volatility
    lower, upper = _scale_bounds(weights, constraints=constraints)
    if lower > upper + constraints.tolerance:
        raise AnalysisError(f"exposure constraints are infeasible on {date}")
    scale = min(max(desired_scale, lower), upper)
    result = weights * scale
    achieved = _annualized_volatility(
        result,
        covariance,
        periods_per_year=risk_control.periods_per_year,
    )
    if (
        risk_control.volatility_limit is not None
        and achieved > risk_control.volatility_limit + constraints.tolerance
    ):
        raise AnalysisError(f"net and volatility constraints are infeasible on {date}")
    return result


def _scale_bounds(
    weights: np.ndarray,
    *,
    constraints: PortfolioConstraints,
) -> tuple[float, float]:
    gross = float(np.abs(weights).sum())
    net = float(weights.sum())
    maximum = np.inf
    if gross > constraints.tolerance:
        maximum = min(maximum, constraints.gross_limit / gross)
    largest = float(np.abs(weights).max(initial=0.0))
    if largest > constraints.tolerance:
        maximum = min(maximum, constraints.position_limit / largest)
    minimum = 0.0
    if net > constraints.tolerance:
        minimum = max(minimum, constraints.net_minimum / net)
        maximum = min(maximum, constraints.net_maximum / net)
    elif net < -constraints.tolerance:
        minimum = max(minimum, constraints.net_maximum / net)
        maximum = min(maximum, constraints.net_minimum / net)
    elif not (constraints.net_minimum <= 0 <= constraints.net_maximum):
        return 1.0, 0.0
    return max(0.0, minimum), maximum


def _annualized_volatility(
    weights: np.ndarray,
    covariance: np.ndarray,
    *,
    periods_per_year: float,
) -> float:
    variance = max(0.0, float(weights @ covariance @ weights))
    return float(np.sqrt(variance * periods_per_year))


def _validate_final_constraints(
    weights: np.ndarray,
    *,
    constraints: PortfolioConstraints,
    date: pd.Timestamp | None,
) -> None:
    suffix = "" if date is None else f" on {date}"
    gross = float(np.abs(weights).sum())
    net = float(weights.sum())
    position = float(np.abs(weights).max(initial=0.0))
    if gross > constraints.gross_limit + constraints.tolerance:
        raise AnalysisError(f"gross limit is violated{suffix}")
    if net < constraints.net_minimum - constraints.tolerance:
        raise AnalysisError(f"net minimum is violated{suffix}")
    if net > constraints.net_maximum + constraints.tolerance:
        raise AnalysisError(f"net maximum is violated{suffix}")
    if position > constraints.position_limit + constraints.tolerance:
        raise AnalysisError(f"position limit is violated{suffix}")


def _turnover(
    previous: np.ndarray,
    target: np.ndarray,
    previous_cash: float,
    target_cash: float,
) -> float:
    return 0.5 * (float(np.abs(target - previous).sum()) + abs(target_cash - previous_cash))


def _exposures(weights: np.ndarray, cash: float) -> dict[str, float]:
    long = float(np.maximum(weights, 0).sum())
    short = float(np.maximum(-weights, 0).sum())
    return {
        "long": long,
        "short": short,
        "gross": long + short,
        "net": long - short,
        "cash": cash,
    }


def _constraint_utilization(
    weights: np.ndarray,
    *,
    exposures: dict[str, float],
    turnover: float,
    predicted_volatility: float,
    constraints: PortfolioConstraints,
    risk_control: PortfolioRiskControl | None,
) -> dict[str, float]:
    gross = exposures["gross"] / constraints.gross_limit if constraints.gross_limit else 0.0
    position = (
        float(np.abs(weights).max(initial=0.0)) / constraints.position_limit
        if constraints.position_limit
        else 0.0
    )
    net = exposures["net"]
    if net >= 0 and constraints.net_maximum > 0:
        net_usage = net / constraints.net_maximum
    elif net < 0 and constraints.net_minimum < 0:
        net_usage = net / constraints.net_minimum
    else:
        net_usage = 0.0
    turnover_usage = (
        turnover / constraints.turnover_limit if constraints.turnover_limit else np.nan
    )
    volatility_usage = np.nan
    if (
        risk_control is not None
        and risk_control.volatility_limit is not None
        and risk_control.volatility_limit > 0
    ):
        volatility_usage = predicted_volatility / risk_control.volatility_limit
    return {
        "gross": gross,
        "net": net_usage,
        "position": position,
        "turnover": turnover_usage,
        "volatility": volatility_usage,
    }
