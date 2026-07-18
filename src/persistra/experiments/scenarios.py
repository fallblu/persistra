"""Deterministic numeric scenario transformations for worker inputs."""

from __future__ import annotations

import random
from decimal import Decimal

from persistra.errors import ExperimentRequestError
from persistra.experiments.models import ScenarioExecution, ScenarioKind


def apply_scenario(
    scenario: ScenarioExecution, values: tuple[Decimal, ...]
) -> tuple[Decimal, ...]:
    """Apply a resolved scenario to a finite numeric path."""
    if not values or any(not value.is_finite() for value in values):
        raise ExperimentRequestError("scenario input path is invalid")
    parameters = dict(scenario.parameters)
    if scenario.kind is ScenarioKind.BASELINE:
        return values
    if scenario.kind is ScenarioKind.HISTORICAL_STRESS:
        start = _integer(parameters, "start")
        stop = _integer(parameters, "stop")
        if start < 0 or stop <= start or stop > len(values):
            raise ExperimentRequestError("historical stress interval is invalid")
        return values[start:stop]
    if scenario.kind is ScenarioKind.HYPOTHETICAL:
        result = values
        if "multiply" in parameters:
            factor = _decimal(parameters, "multiply")
            result = tuple(value * factor for value in result)
        if "add" in parameters:
            shift = _decimal(parameters, "add")
            result = tuple(value + shift for value in result)
        lower = _optional_decimal(parameters, "clip_lower")
        upper = _optional_decimal(parameters, "clip_upper")
        if lower is not None or upper is not None:
            if lower is not None and upper is not None and lower >= upper:
                raise ExperimentRequestError("scenario clip bounds are invalid")
            if lower is not None:
                result = tuple(max(lower, value) for value in result)
            if upper is not None:
                result = tuple(min(upper, value) for value in result)
        return result
    if scenario.derived_seed is None:
        raise ExperimentRequestError("randomized scenario seed is missing")
    rng = random.Random(scenario.derived_seed)
    count = _integer(parameters, "count")
    if count < 1:
        raise ExperimentRequestError("scenario output count is invalid")
    if scenario.kind is ScenarioKind.MONTE_CARLO:
        mean = _decimal(parameters, "mean")
        standard_deviation = _decimal(parameters, "standard_deviation")
        if standard_deviation <= 0:
            raise ExperimentRequestError("Monte Carlo standard deviation is invalid")
        return tuple(
            Decimal(repr(rng.gauss(float(mean), float(standard_deviation))))
            for _ in range(count)
        )
    if scenario.kind is ScenarioKind.BOOTSTRAP:
        block_length = _integer(parameters, "block_length")
        method = parameters.get("method")
        if method not in {"moving", "stationary"} or block_length < 1:
            raise ExperimentRequestError("bootstrap method is invalid")
        output: list[Decimal] = []
        while len(output) < count:
            length = block_length
            if method == "stationary":
                length = 1
                while length < count and rng.random() > 1 / block_length:
                    length += 1
            start = rng.randrange(len(values))
            output.extend(values[(start + offset) % len(values)] for offset in range(length))
        return tuple(output[:count])
    raise ExperimentRequestError("scenario kind is unsupported")


def validate_scenario_parameters(scenario: ScenarioExecution) -> None:
    """Validate a scenario by applying it to a small representative path."""
    apply_scenario(scenario, (Decimal("1"), Decimal("2"), Decimal("3")))


def _integer(parameters: dict[str, str], name: str) -> int:
    try:
        return int(parameters[name])
    except (KeyError, ValueError) as error:
        raise ExperimentRequestError(f"scenario parameter {name} is invalid") from error


def _decimal(parameters: dict[str, str], name: str) -> Decimal:
    try:
        value = Decimal(parameters[name])
    except (KeyError, ValueError) as error:
        raise ExperimentRequestError(f"scenario parameter {name} is invalid") from error
    if not value.is_finite():
        raise ExperimentRequestError(f"scenario parameter {name} is invalid")
    return value


def _optional_decimal(parameters: dict[str, str], name: str) -> Decimal | None:
    return None if name not in parameters else _decimal(parameters, name)
