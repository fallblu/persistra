from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from persistra.analysis import MetricInputs
from persistra.analysis.services import _compute  # pyright: ignore[reportPrivateUsage]


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
