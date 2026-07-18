from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from persistra.analysis import MetricInputs
from persistra.analysis.services import (
    _compute,  # pyright: ignore[reportPrivateUsage]
    _money_weighted_return,  # pyright: ignore[reportPrivateUsage]
)


def test_standard_metric_catalog_uses_normative_var_and_turnover_formulas() -> None:
    start = datetime(2025, 1, 1, tzinfo=UTC)
    returns = pd.DataFrame(
        {
            "state": ["computed"] * 20,
            "return_value": [index / 100 for index in range(20)],
        }
    )
    equity = pd.DataFrame(
        {
            "valued_at": [start + timedelta(days=index) for index in range(21)],
            "nav_usd": [100.0] * 21,
        }
    )
    positions = pd.DataFrame(
        {
            "sample_ordinal": [1, 1],
            "market_value_usd": [75.0, 25.0],
        }
    )
    fills = pd.DataFrame({"quantity": [10.0], "fill_price_usd": [2.0]})
    costs = pd.DataFrame({"amount_usd": [1.25]})

    results = {
        result.metric_name: result
        for result in _compute(equity, returns, positions, fills, costs)
    }

    assert len(results) == 26
    assert results["persistra.metric.var_historical"].estimate == pytest.approx(
        0.0095
    )
    assert results["persistra.metric.expected_shortfall"].estimate == 0.0
    assert results["persistra.metric.turnover"].estimate == pytest.approx(1.82625)
    assert results["persistra.metric.concentration"].estimate == pytest.approx(0.625)
    assert results["persistra.metric.cost_total"].estimate == 1.25
    assert results["persistra.metric.beta"].state.value == "missing_input"

    benchmark_results = {
        result.metric_name: result
        for result in _compute(
            equity,
            returns,
            positions,
            fills,
            costs,
            MetricInputs(
                risk_free_returns=(0.0,) * 20,
                benchmark_returns=tuple(index / 200 for index in range(20)),
            ),
        )
    }
    assert benchmark_results["persistra.metric.beta"].estimate == pytest.approx(2.0)
    assert benchmark_results["persistra.metric.active_return"].state.value == "computed"


def test_money_weighted_participation_and_holding_period_inputs() -> None:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2025, 1, 1, tzinfo=UTC)
    equity = pd.DataFrame(
        {"valued_at": [start, end], "nav_usd": [100.0, 121.0]}
    )
    cash_flows = pd.DataFrame(
        {
            "effective_at": [start + (end - start) / 2],
            "amount_usd": [10.0],
        }
    )
    money_weighted = _money_weighted_return(equity, cash_flows)
    assert money_weighted is not None
    years = (end - start).total_seconds() / (365.25 * 24 * 60 * 60)
    residual = (
        -100
        - 10 / (1 + money_weighted) ** (years / 2)
        + 121 / (1 + money_weighted) ** years
    )
    assert residual == pytest.approx(0.0, abs=1e-9)

    results = {
        result.metric_name: result
        for result in _compute(
            equity,
            pd.DataFrame({"state": ["computed"], "return_value": [0.21]}),
            pd.DataFrame(),
            pd.DataFrame(
                {"quantity": [10.0, 20.0], "fill_price_usd": [1.0, 1.0]}
            ),
            pd.DataFrame({"amount_usd": [1.0]}),
            MetricInputs(
                eligible_volume_by_fill=(100.0, 100.0),
                closed_lot_holding_periods=((2.0, 100.0), (4.0, 300.0)),
            ),
            cash_flows=cash_flows,
        )
    }
    assert results["persistra.metric.money_weighted_return"].estimate == pytest.approx(
        money_weighted
    )
    assert results["persistra.metric.holding_period"].estimate == 3.5
    assert results["persistra.metric.participation_mean"].estimate == pytest.approx(
        0.15
    )
    assert results["persistra.metric.participation_p95"].estimate == pytest.approx(
        0.195
    )
