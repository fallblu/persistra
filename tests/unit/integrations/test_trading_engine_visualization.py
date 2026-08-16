"""Artist-level tests for Trading Engine execution diagnostics."""

from dataclasses import replace

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.axes import Axes
from matplotlib.dates import ConciseDateFormatter

from persistra.integrations.trading_engine import analyze_execution
from persistra.integrations.trading_engine.model import ExecutionReplayResult
from persistra.viz import (
    plot_execution_diagnostics,
    plot_execution_performance,
)


def test_execution_performance_plot_uses_event_timestamps_and_caller_axes(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)
    _, supplied = plt.subplots(2, 1)

    axes = plot_execution_performance(
        analysis,
        equity_ax=supplied[0],
        drawdown_ax=supplied[1],
    )

    assert axes.equity is supplied[0]
    assert axes.drawdown is supplied[1]
    assert axes.equity.get_ylabel() == "Equity"
    assert axes.drawdown.get_ylabel() == "Drawdown"
    assert isinstance(axes.drawdown.xaxis.get_major_formatter(), ConciseDateFormatter)
    assert np.asarray(axes.equity.lines[0].get_xdata()).size == 4
    plt.close("all")


def test_execution_diagnostics_plot_distinguishes_quantity_and_price_references(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)

    axes = plot_execution_diagnostics(analysis)

    assert isinstance(axes.quantities, Axes)
    assert len(axes.quantities.patches) == 6
    quantity_legend = axes.quantities.get_legend()
    slippage_legend = axes.slippage.get_legend()
    assert quantity_legend is not None
    assert slippage_legend is not None
    assert {text.get_text() for text in quantity_legend.get_texts()} == {
        "Requested",
        "Filled",
    }
    assert len(axes.slippage.patches) == 4
    assert {text.get_text() for text in slippage_legend.get_texts()} == {
        "Decision close",
        "Fill-slice open",
    }
    assert axes.slippage.get_ylabel() == "Adverse slippage (bps)"
    plt.close("all")


def test_execution_diagnostics_compacts_engine_identifiers(
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

    axes = plot_execution_diagnostics(compacted)

    assert [label.get_text() for label in axes.quantities.get_xticklabels()] == [
        "O1",
        "O2",
        "O3",
    ]
    assert [label.get_text() for label in axes.slippage.get_xticklabels()] == [
        "F1",
        "F2",
    ]
    assert compacted.order_diagnostics["order_id"].tolist() == order_ids
    assert compacted.fill_diagnostics["fill_id"].tolist() == fill_ids
    plt.close("all")


def test_execution_plots_require_complete_axis_pairs(
    execution_replay: ExecutionReplayResult,
) -> None:
    analysis = analyze_execution(execution_replay)
    _, supplied = plt.subplots()

    try:
        plot_execution_performance(analysis, equity_ax=supplied)
    except ValueError as error:
        assert "provide both" in str(error)
    else:
        raise AssertionError("incomplete performance axes must fail")

    try:
        plot_execution_diagnostics(analysis, quantities_ax=supplied)
    except ValueError as error:
        assert "provide both" in str(error)
    else:
        raise AssertionError("incomplete diagnostic axes must fail")
    plt.close("all")
