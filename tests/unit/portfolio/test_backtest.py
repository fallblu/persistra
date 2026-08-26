"""Tests for portfolio-level vectorized backtesting."""

import warnings
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from persistra.errors import AnalysisError
from persistra.portfolio import (
    BacktestPolicies,
    BacktestTiming,
    BorrowPolicy,
    CorporateAction,
    MarketImpactModel,
    MultiCurrencyPolicy,
    PortfolioConstraints,
    backtest_portfolio,
    construct_portfolio,
)


def market_returns() -> pd.DataFrame:
    """Return a deterministic two-asset market panel."""
    return pd.DataFrame(
        [[0.01, 0.0], [0.10, -0.02], [-0.05, 0.03], [0.02, 0.01], [0.0, -0.01]],
        index=pd.date_range("2025-01-01", periods=5),
        columns=["a", "b"],
    )


def test_backtest_lags_targets_and_reconciles_holdings_cash_returns_and_costs() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)

    result = backtest_portfolio(
        targets,
        returns=returns,
        transaction_cost_bps=pd.Series({"a": 10.0, "b": 20.0}),
        cash_returns=0.001,
        initial_equity=100.0,
    )

    assert result.realized_weights.iloc[0].tolist() == [0.0, 0.0]
    assert result.cash.iloc[0] == 1.0
    assert result.returns.iloc[0] == pytest.approx(0.001)
    assert result.realized_weights.iloc[1].tolist() == [1.0, 0.0]
    assert result.turnover.iloc[1] == pytest.approx(1.0)
    assert result.cost_attribution.iloc[1].tolist() == pytest.approx([0.001, 0.0])
    assert result.returns.iloc[1] == pytest.approx(0.099)
    pd.testing.assert_series_equal(
        result.asset_return_attribution.sum(axis="columns").add(
            result.cash_return_attribution
        ),
        result.gross_returns,
        check_names=False,
    )
    pd.testing.assert_series_equal(
        result.gross_returns.sub(result.costs),
        result.returns,
        check_names=False,
    )
    assert np.allclose(result.realized_weights.sum(axis="columns").add(result.cash), 1.0)
    assert np.allclose(result.ending_weights.sum(axis="columns").add(result.ending_cash), 1.0)
    assert result.equity.iloc[-1] == pytest.approx(
        100.0 * np.prod(1.0 + result.returns.to_numpy())
    )
    assert result.drawdown.le(0).all()
    assert result.rebalance_log.iloc[0]["signal_observation"] == returns.index[0]
    assert result.rebalance_log.iloc[0]["holding_start"] == returns.index[1]
    assert result.rebalance_log.iloc[0]["holding_end"] == returns.index[-1]


def test_dated_asymmetric_costs_report_components_and_coverage() -> None:
    returns = market_returns().mul(0.0)
    targets = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0]],
        index=returns.index[:2],
        columns=returns.columns,
    )
    buy = pd.DataFrame(20.0, index=returns.index, columns=returns.columns)
    sell = pd.DataFrame(30.0, index=returns.index, columns=returns.columns)
    result = backtest_portfolio(
        targets,
        returns=returns,
        buy_cost_bps=buy,
        sell_cost_bps=sell,
    )

    expected = (
        result.trades.clip(lower=0.0).mul(buy / 10_000.0)
        + result.trades.clip(upper=0.0).abs().mul(sell / 10_000.0)
    )
    pd.testing.assert_frame_equal(result.trade_cost_attribution, expected)
    pd.testing.assert_series_equal(
        result.trade_cost_attribution.sum(axis="columns"),
        result.trade_costs,
        check_names=False,
    )
    assert result.cost_input_coverage[["buy_cost", "sell_cost"]].eq(1.0).all(axis=None)


def test_market_impact_is_nonlinear_and_rejects_zero_liquidity() -> None:
    returns = market_returns().mul(0.0)
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    liquidity = pd.DataFrame(0.1, index=returns.index, columns=returns.columns)
    result = backtest_portfolio(
        targets,
        returns=returns,
        market_impact=MarketImpactModel(coefficient_bps=10.0, exponent=0.5),
        liquidity=liquidity,
    )

    assert result.impact_costs.iloc[1] == pytest.approx(0.001 * np.sqrt(10.0))
    assert result.trade_costs.eq(0.0).all()
    zero = liquidity.copy()
    zero.loc[returns.index[1], "a"] = 0.0
    with pytest.raises(AnalysisError, match="zero liquidity"):
        backtest_portfolio(
            targets,
            returns=returns,
            market_impact=MarketImpactModel(10.0),
            liquidity=zero,
        )


def test_missing_dated_costs_require_an_explicit_zero_policy() -> None:
    returns = market_returns().mul(0.0)
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    costs = pd.DataFrame(10.0, index=returns.index, columns=returns.columns)
    costs.loc[returns.index[1], "b"] = np.nan

    with pytest.raises(AnalysisError, match="must be finite"):
        backtest_portfolio(targets, returns=returns, transaction_cost_bps=costs)
    allowed = backtest_portfolio(
        targets,
        returns=returns,
        transaction_cost_bps=costs,
        missing_cost="zero",
    )
    assert allowed.cost_input_coverage.at[returns.index[1], "buy_cost"] == 0.5


def test_borrow_fees_accrue_separately_and_long_only_is_unchanged() -> None:
    returns = market_returns().mul(0.0)
    same_period = BacktestTiming(
        decision_lag=0,
        execution_lag=0,
        signal_available_before_trade=True,
    )
    short = pd.DataFrame([[-0.5, 0.0]], index=returns.index[:1], columns=returns.columns)
    result = backtest_portfolio(
        short,
        returns=returns,
        timing=same_period,
        borrow_rates=pd.Series({"a": 0.01, "b": 0.02}),
    )

    assert result.borrow_costs.iloc[0] == pytest.approx(0.005)
    assert result.borrow_cost_attribution.iloc[0].tolist() == pytest.approx([0.005, 0.0])
    pd.testing.assert_series_equal(
        result.trade_costs.add(result.impact_costs).add(result.borrow_costs),
        result.costs,
        check_names=False,
    )
    long = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    baseline = backtest_portfolio(long, returns=returns, timing=same_period)
    costly_borrow = backtest_portfolio(
        long,
        returns=returns,
        timing=same_period,
        borrow_rates=1.0,
    )
    pd.testing.assert_series_equal(baseline.returns, costly_borrow.returns)


def test_unavailable_existing_short_is_forced_to_cover_or_errors() -> None:
    returns = market_returns().mul(0.0)
    timing = BacktestTiming(0, 0, signal_available_before_trade=True)
    targets = pd.DataFrame([[-0.5, 0.0]], index=returns.index[:1], columns=returns.columns)
    shortable = pd.DataFrame(True, index=returns.index, columns=returns.columns)
    shortable.loc[returns.index[1]:, "a"] = False

    with pytest.raises(AnalysisError, match="unavailable shorts"):
        backtest_portfolio(
            targets,
            returns=returns,
            timing=timing,
            shortable=shortable,
        )
    covered = backtest_portfolio(
        targets,
        returns=returns,
        timing=timing,
        shortable=shortable,
        borrow_policy=BorrowPolicy(unavailable="cover"),
    )
    assert covered.realized_weights.at[returns.index[1], "a"] == 0.0
    assert covered.trades.at[returns.index[1], "a"] == pytest.approx(0.5)
    assert covered.borrow_events.iloc[0]["action"] == "forced_cover"


def test_unavailable_short_target_and_missing_borrow_rates_are_explicit() -> None:
    returns = market_returns().mul(0.0)
    timing = BacktestTiming(0, 0, signal_available_before_trade=True)
    targets = pd.DataFrame([[-0.5, 0.0]], index=returns.index[:1], columns=returns.columns)
    shortable = pd.DataFrame(False, index=returns.index, columns=returns.columns)
    rates = pd.DataFrame(0.01, index=returns.index, columns=returns.columns)
    rates.iloc[0, 0] = np.nan

    with pytest.raises(AnalysisError, match="borrow_rates must be finite"):
        backtest_portfolio(targets, returns=returns, borrow_rates=rates)
    blocked = backtest_portfolio(
        targets,
        returns=returns,
        timing=timing,
        shortable=shortable,
        borrow_rates=rates,
        borrow_policy=BorrowPolicy(unavailable="cover", missing_rate="zero"),
    )
    assert blocked.realized_weights.iloc[0].eq(0.0).all()
    assert blocked.rebalance_log.iloc[0]["blocked_assets"] == "a"
    assert blocked.borrow_events.iloc[0]["action"] == "blocked_target"
    assert blocked.cost_input_coverage.iloc[0]["borrow_rate"] == 0.5


def test_cost_and_borrow_policy_contracts_are_strict() -> None:
    returns = market_returns().mul(0.0)
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    with pytest.raises(ValueError, match="impact exponent"):
        MarketImpactModel(10.0, exponent=0.0)
    with pytest.raises(ValueError, match="unavailable-short"):
        BorrowPolicy(unavailable="hold")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing borrow-rate"):
        BorrowPolicy(missing_rate="hold")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing-cost"):
        backtest_portfolio(targets, returns=returns, missing_cost="hold")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="requires liquidity"):
        backtest_portfolio(
            targets,
            returns=returns,
            market_impact=MarketImpactModel(10.0),
        )


def test_multicurrency_returns_reconcile_local_fx_and_base_cash() -> None:
    index = pd.date_range("2025-01-01", periods=3)
    returns = pd.DataFrame({"euro_asset": [0.0, 0.10, 0.0]}, index=index)
    targets = pd.DataFrame({"euro_asset": [1.0]}, index=index[:1])
    fx = pd.DataFrame({"EUR/USD": [1.0, 1.2, 1.2]}, index=index)
    policy = MultiCurrencyPolicy(
        base_currency="USD",
        asset_currencies=pd.Series({"euro_asset": "EUR"}),
    )
    result = backtest_portfolio(
        targets,
        returns=returns,
        timing=BacktestTiming(0, 0, signal_available_before_trade=True),
        fx_rates=fx,
        multi_currency=policy,
    )

    assert result.returns.iloc[1] == pytest.approx(0.32)
    assert result.local_return_attribution.iloc[1, 0] == pytest.approx(0.10)
    assert result.fx_return_attribution.iloc[1, 0] == pytest.approx(0.22)
    pd.testing.assert_frame_equal(
        result.local_return_attribution.add(result.fx_return_attribution),
        result.asset_return_attribution,
    )
    assert result.currency_cash.columns.tolist() == ["USD", "EUR"]
    pd.testing.assert_series_equal(
        result.currency_cash.sum(axis="columns"), result.cash, check_names=False
    )
    assert result.currency_cash["EUR"].eq(0.0).all()


def test_fx_pairs_triangulate_and_base_currency_assets_are_invariant() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[0.5, 0.5]], index=returns.index[:1], columns=returns.columns)
    fx = pd.DataFrame(
        {
            "EUR/GBP": [0.8, 0.88, 0.88, 0.88, 0.88],
            "GBP/USD": [1.25, 1.25, 1.25, 1.25, 1.25],
        },
        index=returns.index,
    )
    triangulated = backtest_portfolio(
        targets,
        returns=returns,
        fx_rates=fx,
        multi_currency=MultiCurrencyPolicy(
            base_currency="USD",
            asset_currencies=pd.Series({"a": "EUR", "b": "USD"}),
        ),
    )
    assert triangulated.fx_rates["EUR"].iloc[:2].tolist() == pytest.approx([1.0, 1.1])
    assert triangulated.fx_rates["USD"].eq(1.0).all()

    base = backtest_portfolio(targets, returns=returns)
    all_base = backtest_portfolio(
        targets,
        returns=returns,
        fx_rates=fx,
        multi_currency=MultiCurrencyPolicy(
            base_currency="USD",
            asset_currencies=pd.Series({"a": "USD", "b": "USD"}),
        ),
    )
    pd.testing.assert_series_equal(all_base.returns, base.returns)
    assert all_base.fx_return_attribution.eq(0.0).all(axis=None)


def test_missing_fx_requires_explicit_bounded_forward_fill() -> None:
    returns = market_returns().iloc[:3]
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    currencies = pd.Series({"a": "EUR", "b": "USD"})
    fx = pd.DataFrame({"EUR/USD": [1.0, np.nan, np.nan]}, index=returns.index)

    with pytest.raises(AnalysisError, match="missing FX rate"):
        backtest_portfolio(
            targets,
            returns=returns,
            fx_rates=fx,
            multi_currency=MultiCurrencyPolicy("USD", currencies),
        )
    allowed_fx = fx.iloc[:2]
    allowed_returns = returns.iloc[:2]
    allowed = backtest_portfolio(
        targets,
        returns=allowed_returns,
        fx_rates=allowed_fx,
        multi_currency=MultiCurrencyPolicy(
            "USD", currencies, missing_fx="ffill", maximum_staleness=1
        ),
    )
    assert allowed.fx_staleness["EUR"].tolist() == [0, 1]
    with pytest.raises(AnalysisError, match="maximum staleness"):
        backtest_portfolio(
            targets,
            returns=returns,
            fx_rates=fx,
            multi_currency=MultiCurrencyPolicy(
                "USD", currencies, missing_fx="ffill", maximum_staleness=1
            ),
        )


def test_multicurrency_contracts_reject_ambiguous_fx_inputs() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    currencies = pd.Series({"a": "EUR", "b": "USD"})
    with pytest.raises(ValueError, match="require multi_currency"):
        backtest_portfolio(
            targets,
            returns=returns,
            fx_rates=pd.DataFrame(index=returns.index),
        )
    with pytest.raises(ValueError, match="requires fx_rates"):
        backtest_portfolio(
            targets,
            returns=returns,
            multi_currency=MultiCurrencyPolicy("USD", currencies),
        )
    with pytest.raises(ValueError, match="asset columns"):
        backtest_portfolio(
            targets,
            returns=returns,
            fx_rates=pd.DataFrame({"EUR/USD": 1.0}, index=returns.index),
            multi_currency=MultiCurrencyPolicy("USD", currencies[::-1]),
        )
    with pytest.raises(ValueError, match="currency pairs"):
        backtest_portfolio(
            targets,
            returns=returns,
            fx_rates=pd.DataFrame({"EURUSD": 1.0}, index=returns.index),
            multi_currency=MultiCurrencyPolicy("USD", currencies),
        )
    with pytest.raises(ValueError, match="positive"):
        backtest_portfolio(
            targets,
            returns=returns,
            fx_rates=pd.DataFrame({"EUR/USD": 0.0}, index=returns.index),
            multi_currency=MultiCurrencyPolicy("USD", currencies),
        )
    with pytest.raises(ValueError, match="missing-FX"):
        MultiCurrencyPolicy("USD", currencies, missing_fx="zero")  # type: ignore[arg-type]


def test_cash_dividends_are_separate_cashflows_and_adjusted_inputs_skip_them() -> None:
    returns = market_returns().mul(0.0)
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    dividend = CorporateAction(
        returns.index[1], "a", "cash_dividend", 0.05, "vendor:distribution-42"
    )
    unadjusted = backtest_portfolio(
        targets,
        returns=returns,
        corporate_actions=[dividend],
    )

    assert unadjusted.returns.iloc[1] == pytest.approx(0.05)
    assert unadjusted.corporate_action_cashflows.at[returns.index[1], "a"] == 0.05
    assert unadjusted.corporate_action_attribution.at[returns.index[1], "a"] == 0.05
    assert unadjusted.ending_cash.iloc[1] == pytest.approx(0.05 / 1.05)
    assert unadjusted.corporate_action_log.iloc[0]["source"] == "vendor:distribution-42"

    adjusted = backtest_portfolio(
        targets,
        returns=returns,
        corporate_actions=[dividend],
        return_adjustment="adjusted",
    )
    assert adjusted.returns.eq(0.0).all()
    assert adjusted.corporate_action_cashflows.eq(0.0).all(axis=None)
    assert adjusted.corporate_action_log.iloc[0]["applied"] == np.False_


def test_split_normalizes_unadjusted_return_without_double_counting_adjusted_data() -> None:
    returns = market_returns().mul(0.0)
    returns.loc[returns.index[1], "a"] = -0.5
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    split = CorporateAction(returns.index[1], "a", "split", 2.0, "exchange:split-7")

    unadjusted = backtest_portfolio(targets, returns=returns, corporate_actions=[split])
    assert unadjusted.returns.iloc[1] == pytest.approx(0.0)
    assert unadjusted.corporate_action_attribution.iloc[1, 0] == pytest.approx(0.5)

    already_adjusted = returns.copy()
    already_adjusted.loc[returns.index[1], "a"] = 0.0
    adjusted = backtest_portfolio(
        targets,
        returns=already_adjusted,
        corporate_actions=[split],
        return_adjustment="adjusted",
    )
    assert adjusted.returns.iloc[1] == 0.0
    assert adjusted.corporate_action_attribution.eq(0.0).all(axis=None)


def test_terminal_return_liquidates_holding_and_rejects_future_targets() -> None:
    returns = market_returns().mul(0.0)
    returns.loc[returns.index[2], "a"] = np.nan
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    terminal = CorporateAction(
        returns.index[2], "a", "terminal_return", -0.5, "exchange:delisting-9"
    )
    result = backtest_portfolio(targets, returns=returns, corporate_actions=[terminal])

    assert result.returns.iloc[2] == pytest.approx(-0.5)
    assert result.ending_weights.at[returns.index[2], "a"] == 0.0
    assert result.ending_cash.at[returns.index[2]] == 1.0
    assert result.realized_weights.at[returns.index[3], "a"] == 0.0

    retargeted = pd.DataFrame(
        [[1.0, 0.0], [1.0, 0.0]],
        index=returns.index[[0, 2]],
        columns=returns.columns,
    )
    with pytest.raises(AnalysisError, match="targets contain delisted assets"):
        backtest_portfolio(retargeted, returns=returns, corporate_actions=[terminal])


def test_corporate_action_contracts_require_provenance_and_valid_keys() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    with pytest.raises(ValueError, match="source"):
        CorporateAction(returns.index[1], "a", "split", 2.0, "")
    with pytest.raises(ValueError, match="positive"):
        CorporateAction(returns.index[1], "a", "cash_dividend", 0.0, "vendor")
    with pytest.raises(ValueError, match="less than -1"):
        CorporateAction(returns.index[1], "a", "terminal_return", -1.1, "vendor")
    with pytest.raises(ValueError, match="dates must belong"):
        backtest_portfolio(
            targets,
            returns=returns,
            corporate_actions=[CorporateAction(pd.Timestamp("2024-01-01"), "a", "split", 2.0, "x")],
        )
    with pytest.raises(ValueError, match="assets must belong"):
        backtest_portfolio(
            targets,
            returns=returns,
            corporate_actions=[CorporateAction(returns.index[1], "missing", "split", 2.0, "x")],
        )
    action = CorporateAction(returns.index[1], "a", "split", 2.0, "x")
    with pytest.raises(ValueError, match="unique"):
        backtest_portfolio(
            targets, returns=returns, corporate_actions=[action, action]
        )
    with pytest.raises(ValueError, match="return-adjustment"):
        backtest_portfolio(
            targets,
            returns=returns,
            return_adjustment="unknown",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="shortable columns must be boolean"):
        backtest_portfolio(
            targets,
            returns=returns,
            shortable=pd.DataFrame(1.0, index=returns.index, columns=returns.columns),
        )


def test_same_period_signals_require_pretrade_availability_proof() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    same_period = BacktestTiming(decision_lag=0, execution_lag=0)

    with pytest.raises(AnalysisError, match="same-period signal use"):
        backtest_portfolio(targets, returns=returns, timing=same_period)

    proved = backtest_portfolio(
        targets,
        returns=returns,
        timing=BacktestTiming(
            decision_lag=0,
            execution_lag=0,
            signal_available_before_trade=True,
        ),
    )
    assert proved.realized_weights.iloc[0].tolist() == [1.0, 0.0]
    assert proved.returns.iloc[0] == pytest.approx(0.01)


def test_fixed_holding_period_exits_to_cash_and_records_period() -> None:
    returns = market_returns().mul(0.0)
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)

    result = backtest_portfolio(
        targets,
        returns=returns,
        timing=BacktestTiming(holding_period=2),
    )

    assert result.realized_weights["a"].tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]
    assert result.turnover.tolist() == pytest.approx([0.0, 1.0, 0.0, 1.0, 0.0])
    assert result.rebalance_log.iloc[0]["holding_start"] == returns.index[1]
    assert result.rebalance_log.iloc[0]["holding_end"] == returns.index[2]


def test_nontradeable_assets_raise_or_remain_at_previous_holdings() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    tradeable = pd.DataFrame(True, index=returns.index, columns=returns.columns)
    tradeable.loc[returns.index[1], "a"] = False

    with pytest.raises(AnalysisError, match="nontradeable assets"):
        backtest_portfolio(targets, returns=returns, tradeable=tradeable)

    held = backtest_portfolio(
        targets,
        returns=returns,
        tradeable=tradeable,
        policies=BacktestPolicies(nontradeable="hold"),
    )
    assert held.realized_weights.iloc[1].tolist() == [0.0, 0.0]
    assert held.cash.iloc[1] == 1.0
    assert held.rebalance_log.iloc[0]["blocked_assets"] == "a"


def test_missing_returns_raise_or_are_treated_as_zero_explicitly() -> None:
    returns = market_returns()
    returns.loc[returns.index[1], "a"] = np.nan
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)

    with pytest.raises(AnalysisError, match="missing returns"):
        backtest_portfolio(targets, returns=returns)

    zero = backtest_portfolio(
        targets,
        returns=returns,
        policies=BacktestPolicies(missing_return="zero"),
    )
    assert zero.returns.iloc[1] == 0.0
    assert zero.realized_weights.iloc[1]["a"] == 1.0


def test_price_input_preserves_missing_price_policy_and_rejects_bad_levels() -> None:
    index = pd.date_range("2025-01-01", periods=4)
    prices = pd.DataFrame(
        [[100.0, 50.0], [np.nan, 50.0], [110.0, 51.0], [121.0, 52.0]],
        index=index,
        columns=["a", "b"],
    )
    targets = pd.DataFrame([[1.0, 0.0]], index=index[:1], columns=prices.columns)
    with pytest.raises(AnalysisError, match="missing returns"):
        backtest_portfolio(targets, prices=prices)
    zero = backtest_portfolio(
        targets,
        prices=prices,
        policies=BacktestPolicies(missing_return="zero"),
    )
    assert zero.returns.iloc[1] == 0.0
    bad = prices.copy()
    bad.iloc[0, 0] = 0.0
    with pytest.raises(AnalysisError, match="prices must be positive"):
        backtest_portfolio(targets, prices=bad)


def test_cash_and_leverage_accounting_support_negative_residual_cash() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.5, 0.0]], index=returns.index[:1], columns=returns.columns)
    result = backtest_portfolio(
        targets,
        returns=returns,
        cash_returns=0.01,
        timing=BacktestTiming(execution_lag=0, signal_available_before_trade=True),
    )

    assert result.exposures.iloc[0]["gross"] == pytest.approx(1.5)
    assert result.exposures.iloc[0]["net"] == pytest.approx(1.5)
    assert result.cash.iloc[0] == pytest.approx(-0.5)
    assert result.cash_return_attribution.iloc[0] == pytest.approx(-0.005)
    assert result.returns.iloc[0] == pytest.approx(0.01)


def test_static_and_naive_benchmarks_use_explicit_weight_definitions() -> None:
    returns = market_returns()
    targets = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0]],
        index=returns.index[[0, 2]],
        columns=returns.columns,
    )
    static = pd.Series([0.5, 0.5], index=returns.columns)
    naive = pd.DataFrame(
        [[0.5, -0.5], [-0.5, 0.5]],
        index=targets.index,
        columns=returns.columns,
    )

    result = backtest_portfolio(
        targets,
        returns=returns,
        benchmarks={"static_equal_weight": static, "naive_signal": naive},
    )

    assert result.benchmark_returns.columns.tolist() == [
        "static_equal_weight",
        "naive_signal",
    ]
    assert result.benchmark_equity.columns.equals(result.benchmark_returns.columns)
    assert result.benchmark_comparison.index.tolist() == [
        "static_equal_weight",
        "naive_signal",
    ]
    assert result.benchmark_comparison["count"].eq(len(returns)).all()
    assert result.benchmark_comparison.columns.tolist() == [
        "count",
        "mean_return",
        "benchmark_mean_return",
        "mean_difference",
        "tracking_error",
        "win_rate",
        "correlation",
    ]


def test_constant_benchmark_has_undefined_correlation_without_warning() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        result = backtest_portfolio(
            targets,
            returns=returns,
            benchmarks={"all_cash": pd.Series(0.0, index=returns.columns)},
        )

    assert pd.isna(result.benchmark_comparison.loc["all_cash", "correlation"])


def test_outside_sample_targets_are_recorded_without_lookahead() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[-1:], columns=returns.columns)

    result = backtest_portfolio(targets, returns=returns)

    assert result.realized_weights.eq(0).all(axis=None)
    assert result.cash.eq(1).all()
    assert result.rebalance_log.iloc[0]["status"] == "outside_sample"
    assert pd.isna(result.rebalance_log.iloc[0]["holding_start"])


def test_backtest_rejects_ambiguous_inputs_and_misaligned_policies() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    with pytest.raises(ValueError, match="exactly one"):
        backtest_portfolio(targets)
    with pytest.raises(ValueError, match="exactly one"):
        backtest_portfolio(targets, returns=returns, prices=returns.add(100.0))
    with pytest.raises(ValueError, match="return columns"):
        backtest_portfolio(targets.rename(columns={"a": "x"}), returns=returns)
    with pytest.raises(ValueError, match="asset columns"):
        backtest_portfolio(
            targets,
            returns=returns,
            transaction_cost_bps=pd.Series([1.0, 1.0], index=["b", "a"]),
        )
    bad_tradeable = pd.DataFrame(1, index=returns.index, columns=returns.columns)
    with pytest.raises(TypeError, match="boolean"):
        backtest_portfolio(targets, returns=returns, tradeable=bad_tradeable)
    with pytest.raises(ValueError, match="positive"):
        BacktestTiming(holding_period=0)


def test_backtest_accepts_construction_results_and_validates_scalar_inputs() -> None:
    returns = market_returns()
    signals = pd.DataFrame(
        [[1.0, 2.0]],
        index=returns.index[:1],
        columns=returns.columns,
    )
    construction = construct_portfolio(
        signals,
        constraints=PortfolioConstraints(
            net_minimum=0.0,
            net_maximum=1.0,
            position_limit=1.0,
        ),
    )
    result = backtest_portfolio(construction, returns=returns)
    assert result.target_weights.equals(construction.weights)

    with pytest.raises(ValueError, match="at least one observation"):
        backtest_portfolio(construction.weights.iloc[:0], returns=returns)
    with pytest.raises(ValueError, match="at least one observation"):
        backtest_portfolio(construction, returns=returns.iloc[:0])
    with pytest.raises(ValueError, match="dates must belong"):
        backtest_portfolio(
            construction.weights.set_axis(pd.DatetimeIndex(["2024-12-31"])),
            returns=returns,
        )
    with pytest.raises(AnalysisError, match="target weights must be finite"):
        backtest_portfolio(construction.weights.mul(np.nan), returns=returns)
    with pytest.raises(ValueError, match="initial_equity"):
        backtest_portfolio(construction, returns=returns, initial_equity=0.0)
    with pytest.raises(ValueError, match="tolerance"):
        backtest_portfolio(construction, returns=returns, tolerance=-1.0)


def test_backtest_validates_return_cost_cash_and_tradeability_contracts() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    impossible_return = returns.copy()
    impossible_return.iloc[1, 0] = -1.1
    with pytest.raises(AnalysisError, match="less than -1"):
        backtest_portfolio(targets, returns=impossible_return)
    with pytest.raises(ValueError, match="nonnegative"):
        backtest_portfolio(targets, returns=returns, transaction_cost_bps=-1.0)
    with pytest.raises(ValueError, match="cash_returns"):
        backtest_portfolio(
            targets,
            returns=returns,
            cash_returns=pd.Series(0.0, index=returns.index[::-1]),
        )
    with pytest.raises(AnalysisError, match="cash_returns must be finite"):
        backtest_portfolio(
            targets,
            returns=returns,
            cash_returns=pd.Series(np.nan, index=returns.index),
        )
    with pytest.raises(AnalysisError, match="cash_returns must not"):
        backtest_portfolio(targets, returns=returns, cash_returns=-1.1)
    mismatched_tradeable = pd.DataFrame(
        True,
        index=returns.index,
        columns=["b", "a"],
    )
    with pytest.raises(ValueError, match="index and columns"):
        backtest_portfolio(targets, returns=returns, tradeable=mismatched_tradeable)
    missing_tradeable = pd.DataFrame(
        True,
        index=returns.index,
        columns=returns.columns,
        dtype="boolean",
    )
    missing_tradeable.iloc[0, 0] = pd.NA
    with pytest.raises(ValueError, match="missing values"):
        backtest_portfolio(targets, returns=returns, tradeable=missing_tradeable)


def test_lag_and_policy_models_reject_invalid_values() -> None:
    with pytest.raises(ValueError, match="decision_lag"):
        BacktestTiming(decision_lag=-1)
    with pytest.raises(ValueError, match="execution_lag"):
        BacktestTiming(execution_lag=-1)
    with pytest.raises(ValueError, match="decision_lag"):
        BacktestTiming(decision_lag=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="holding_period"):
        BacktestTiming(holding_period=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="missing-return"):
        BacktestPolicies(missing_return="skip")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="nontradeable"):
        BacktestPolicies(nontradeable="liquidate")  # type: ignore[arg-type]


def test_large_decision_lag_and_overlapping_fixed_holds_remain_explicit() -> None:
    returns = market_returns().mul(0.0)
    late_target = pd.DataFrame([[1.0, 0.0]], index=returns.index[-2:-1], columns=returns.columns)
    outside = backtest_portfolio(
        late_target,
        returns=returns,
        timing=BacktestTiming(decision_lag=2, execution_lag=0),
    )
    assert pd.isna(outside.rebalance_log.iloc[0]["decision"])
    assert outside.rebalance_log.iloc[0]["status"] == "outside_sample"

    targets = pd.DataFrame(
        [[1.0, 0.0], [0.0, 1.0]],
        index=returns.index[:2],
        columns=returns.columns,
    )
    overlapping = backtest_portfolio(
        targets,
        returns=returns,
        timing=BacktestTiming(holding_period=3),
    )
    assert overlapping.rebalance_log["holding_end"].tolist() == [
        returns.index[1],
        returns.index[4],
    ]
    assert overlapping.realized_weights.iloc[2].tolist() == [0.0, 1.0]


def test_nonpositive_equity_is_rejected_before_weights_become_undefined() -> None:
    returns = market_returns().mul(0.0)
    returns.iloc[0, 0] = -1.0
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    with pytest.raises(AnalysisError, match="equity is nonpositive"):
        backtest_portfolio(
            targets,
            returns=returns,
            timing=BacktestTiming(execution_lag=0, signal_available_before_trade=True),
        )


def test_benchmark_contracts_reject_ambiguous_definitions() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    with pytest.raises(ValueError, match="names"):
        backtest_portfolio(targets, returns=returns, benchmarks={"": targets})
    with pytest.raises(ValueError, match="static benchmark"):
        backtest_portfolio(
            targets,
            returns=returns,
            benchmarks={"static": pd.Series([0.5, 0.5], index=["b", "a"])},
        )
    with pytest.raises(ValueError, match="asset columns"):
        backtest_portfolio(
            targets,
            returns=returns,
            benchmarks={"naive": targets.rename(columns={"a": "x"})},
        )
    with pytest.raises(AnalysisError, match="weights must be finite"):
        backtest_portfolio(
            targets,
            returns=returns,
            benchmarks={"naive": targets.mul(np.nan)},
        )
    with pytest.raises(ValueError, match="dates must belong"):
        backtest_portfolio(
            targets,
            returns=returns,
            benchmarks={
                "naive": targets.set_axis(pd.DatetimeIndex(["2024-12-31"])),
            },
        )


def test_result_contract_rejects_broken_accounting_relationships() -> None:
    returns = market_returns()
    targets = pd.DataFrame([[1.0, 0.0]], index=returns.index[:1], columns=returns.columns)
    result = backtest_portfolio(targets, returns=returns)
    short_index = returns.index[:-1]
    with pytest.raises(ValueError, match="realized-weight axes"):
        replace(result, ending_weights=result.ending_weights.iloc[:-1])
    with pytest.raises(ValueError, match="realized-weight index"):
        replace(result, costs=result.costs.iloc[:-1])
    with pytest.raises(ValueError, match="exposures"):
        replace(result, exposures=result.exposures.loc[short_index])
    with pytest.raises(ValueError, match="benchmark_returns"):
        replace(result, benchmark_returns=result.benchmark_returns.loc[short_index])
    with pytest.raises(ValueError, match="must sum to one"):
        replace(result, cash=result.cash.add(0.1))
    with pytest.raises(ValueError, match="ending asset"):
        replace(result, ending_cash=result.ending_cash.add(0.1))
    with pytest.raises(ValueError, match="gross returns"):
        replace(result, cash_return_attribution=result.cash_return_attribution.add(0.1))
    with pytest.raises(ValueError, match="net returns"):
        replace(result, returns=result.returns.add(0.1))
    with pytest.raises(ValueError, match="total costs"):
        replace(result, cost_attribution=result.cost_attribution.add(0.1))
    with pytest.raises(ValueError, match="trade cost attribution"):
        replace(result, trade_cost_attribution=result.trade_cost_attribution.add(0.1))
    with pytest.raises(ValueError, match="cost components"):
        replace(
            result,
            borrow_cost_attribution=result.borrow_cost_attribution.add(0.1),
            borrow_costs=result.borrow_costs.add(0.2),
        )
    with pytest.raises(ValueError, match="cost_input_coverage"):
        replace(result, cost_input_coverage=result.cost_input_coverage.iloc[:-1])
    with pytest.raises(ValueError, match="reconcile to equity"):
        replace(result, equity=result.equity.add(1.0))
