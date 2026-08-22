# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportArgumentType=false
"""Trace- and layout-level tests for Trading Engine execution diagnostics."""

from dataclasses import replace

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from persistra.integrations.trading_engine import analyze_execution
from persistra.integrations.trading_engine.model import ExecutionReplayResult
from persistra.viz import plot_execution_diagnostics, plot_execution_performance


def test_execution_performance_uses_event_timestamps_and_linked_subplots(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)

    chart = plot_execution_performance(analysis)

    assert isinstance(chart, go.Figure)
    assert chart.layout.yaxis.title.text == "Equity"
    assert chart.layout.yaxis2.title.text == "Drawdown"
    assert chart.layout.xaxis.matches == "x2"
    assert np.asarray(chart.data[0].x).size == 4
    assert pd.api.types.is_datetime64_any_dtype(np.asarray(chart.data[0].x).dtype)
    assert chart.layout.shapes[0].y0 == 0


def test_execution_diagnostics_distinguishes_quantity_and_price_references(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)

    chart = plot_execution_diagnostics(analysis)

    assert isinstance(chart, go.Figure)
    assert {trace.name for trace in chart.data[:2]} == {"Requested", "Filled"}
    assert {trace.name for trace in chart.data[2:]} == {
        "Decision close",
        "Fill-slice open",
    }
    assert chart.data[1].marker.pattern.shape == "/"
    assert chart.data[3].marker.pattern.shape == "."
    assert chart.layout.yaxis.title.text == "Quantity"
    assert chart.layout.yaxis2.title.text == "Adverse slippage (bps)"


def test_execution_diagnostics_compacts_identifiers_without_mutating_inputs(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)
    order_ids = [
        "portfolio-comparison-order-000000000001",
        "portfolio-comparison-order-000000000002",
        "portfolio-comparison-order-000000000003",
    ]
    fill_ids = [
        "portfolio-comparison-fill-000000000001",
        "portfolio-comparison-fill-000000000002",
    ]
    orders = analysis.order_diagnostics.copy(deep=True)
    orders["order_id"] = order_ids
    fills = analysis.fill_diagnostics.copy(deep=True)
    fills["fill_id"] = fill_ids
    compacted = replace(analysis, order_diagnostics=orders, fill_diagnostics=fills)

    chart = plot_execution_diagnostics(compacted)

    assert list(chart.data[0].x) == ["O1", "O2", "O3"]
    assert list(chart.data[2].x) == ["F1", "F2"]
    assert compacted.order_diagnostics["order_id"].tolist() == order_ids
    assert compacted.fill_diagnostics["fill_id"].tolist() == fill_ids


def test_execution_diagnostics_annotates_an_empty_fill_panel(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)
    empty = replace(analysis, fill_diagnostics=analysis.fill_diagnostics.iloc[:0])

    chart = plot_execution_diagnostics(empty)

    assert len(chart.data) == 2
    assert chart.layout.annotations[-1].text == "No fill events"


def test_execution_plots_reject_empty_required_observations(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)
    empty_performance = replace(
        analysis,
        performance_path=analysis.performance_path.iloc[:0],
    )
    empty_orders = replace(
        analysis,
        order_diagnostics=analysis.order_diagnostics.iloc[:0],
    )

    with pytest.raises(ValueError, match="no performance"):
        plot_execution_performance(empty_performance)
    with pytest.raises(ValueError, match="no order"):
        plot_execution_diagnostics(empty_orders)
