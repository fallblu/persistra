from __future__ import annotations

import math
from typing import cast

import numpy as np
import pandas as pd


def _to_returns(returns: pd.Series) -> pd.Series:
    return returns.dropna().astype(float)


def annualized_return(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Compound annualized return from a periodic return series.

    Args:
        returns: Per-period returns (e.g. daily).
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        Annualized return as a decimal, or ``nan`` if the series is empty or
        the compounded total is non-positive.
    """
    r = _to_returns(returns)
    if r.empty:
        return float("nan")
    total_growth = float(cast("float", (1.0 + r).prod()))
    if total_growth <= 0.0:
        return float("nan")
    return total_growth ** (periods_per_year / len(r)) - 1.0


def annualized_volatility(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Annualized standard deviation of periodic returns.

    Args:
        returns: Per-period returns.
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        Annualized volatility as a decimal, or ``nan`` for fewer than 2 observations.
    """
    r = _to_returns(returns)
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1) * math.sqrt(periods_per_year))


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized Sharpe ratio (excess-return / vol).

    Args:
        returns: Per-period returns.
        risk_free_rate: Annual risk-free rate (default 0.0).
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        Sharpe ratio, or ``nan`` if fewer than 2 observations or zero volatility.
    """
    r = _to_returns(returns)
    if len(r) < 2:
        return float("nan")
    per_period_rf = risk_free_rate / periods_per_year
    excess = r - per_period_rf
    std = float(excess.std(ddof=1))
    if std < 1e-12:
        return float("nan")
    return float(excess.mean() / std * math.sqrt(periods_per_year))


def sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized Sortino ratio (excess-return / downside-deviation).

    Args:
        returns: Per-period returns.
        risk_free_rate: Annual risk-free rate (default 0.0).
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        Sortino ratio, or ``nan`` if fewer than 2 observations or zero downside dev.
    """
    r = _to_returns(returns)
    if len(r) < 2:
        return float("nan")
    per_period_rf = risk_free_rate / periods_per_year
    excess = r - per_period_rf
    downside = excess.clip(upper=0.0)
    downside_dev = float(math.sqrt((downside**2).mean()))
    if downside_dev == 0.0:
        return float("nan")
    return float(excess.mean() / downside_dev * math.sqrt(periods_per_year))


def max_drawdown(
    equity_curve: pd.Series,
) -> tuple[float, pd.Timestamp, pd.Timestamp]:
    """Peak-to-trough maximum drawdown of an equity curve.

    Args:
        equity_curve: Series of equity values (not returns).

    Returns:
        Tuple of ``(depth, peak_date, trough_date)`` where ``depth`` is negative
        (e.g. ``-0.20`` for a 20 % drawdown). Returns ``(nan, NaT, NaT)`` for an
        empty series.
    """
    s = equity_curve.dropna().astype(float)
    if s.empty:
        return (float("nan"), cast("pd.Timestamp", pd.NaT), cast("pd.Timestamp", pd.NaT))
    running_max = s.cummax()
    drawdown = s / running_max - 1.0
    trough_idx = drawdown.idxmin()
    depth = float(drawdown.loc[trough_idx])
    peak_idx = s.loc[:trough_idx].idxmax()
    return (depth, pd.Timestamp(peak_idx), pd.Timestamp(trough_idx))


def calmar_ratio(returns: pd.Series, periods_per_year: int = 252) -> float:
    """Calmar ratio: annualized return divided by absolute max drawdown.

    Args:
        returns: Per-period returns.
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        Calmar ratio, or ``nan`` if the series is empty or drawdown is zero/nan.
    """
    r = _to_returns(returns)
    if r.empty:
        return float("nan")
    equity = (1.0 + r).cumprod()
    depth, _, _ = max_drawdown(equity)
    if depth == 0.0 or math.isnan(depth):
        return float("nan")
    ann_ret = annualized_return(r, periods_per_year)
    return float(ann_ret / abs(depth))


def hit_rate(returns: pd.Series) -> float:
    """Fraction of periods with a positive return.

    Args:
        returns: Per-period returns.

    Returns:
        Win rate in [0, 1], or ``nan`` for an empty series.
    """
    r = _to_returns(returns)
    if r.empty:
        return float("nan")
    return float((r > 0).mean())


def turnover(positions: pd.DataFrame) -> pd.Series:
    """One-sided turnover from the positions frame (cols: bar_time, symbol, weight)."""
    if positions.empty:
        return pd.Series(dtype=float, name="turnover")
    pivot = positions.pivot_table(
        index="bar_time", columns="symbol", values="weight", aggfunc="sum"
    ).fillna(0.0)
    pivot = pivot.sort_index()
    diffs = pivot.diff().abs().sum(axis=1)
    diffs.iloc[0] = float("nan")
    diffs.name = "turnover"
    return diffs


def exposure_stats(equity_curve_df: pd.DataFrame) -> dict[str, float]:
    """Mean and standard deviation of gross and net exposure over the backtest.

    Args:
        equity_curve_df: DataFrame with ``gross_exposure`` and ``net_exposure``
            columns (one row per bar).

    Returns:
        Dictionary with keys ``"gross_mean"``, ``"gross_std"``, ``"net_mean"``,
        and ``"net_std"``.  All values are ``nan`` when the DataFrame is empty;
        ``gross_std`` and ``net_std`` are ``nan`` when fewer than 2 rows are
        present.
    """
    if equity_curve_df.empty:
        return {
            "gross_mean": float("nan"),
            "gross_std": float("nan"),
            "net_mean": float("nan"),
            "net_std": float("nan"),
        }
    gross = equity_curve_df["gross_exposure"].astype(float)
    net = equity_curve_df["net_exposure"].astype(float)
    return {
        "gross_mean": float(gross.mean()),
        "gross_std": float(gross.std(ddof=1)) if len(gross) > 1 else float("nan"),
        "net_mean": float(net.mean()),
        "net_std": float(net.std(ddof=1)) if len(net) > 1 else float("nan"),
    }


def tail_metrics(returns: pd.Series, alpha: float = 0.05) -> dict[str, float]:
    """Value-at-Risk and Conditional Value-at-Risk at a given tail level.

    Args:
        returns: Per-period returns.
        alpha: Tail probability (default 0.05 for the 5th-percentile VaR).

    Returns:
        Dictionary with keys ``"var"`` (the ``alpha``-quantile of returns,
        using the lower interpolation method) and ``"cvar"`` (mean of all
        returns at or below the VaR threshold).  Both are ``nan`` for an
        empty series.
    """
    r = _to_returns(returns)
    if r.empty:
        return {"var": float("nan"), "cvar": float("nan")}
    var = float(np.quantile(r.to_numpy(), alpha, method="lower"))
    tail = r[r <= var]
    cvar = float(tail.mean()) if not tail.empty else var
    return {"var": var, "cvar": cvar}


def benchmark_free_summary(equity_curve: pd.Series) -> dict[str, float]:
    """Summary metrics that require only a strategy equity curve."""
    equity = equity_curve.astype(float)
    returns = equity.pct_change().dropna()
    depth, _, _ = max_drawdown(equity)
    tail = tail_metrics(returns, alpha=0.05)
    return {
        "ann_return": annualized_return(returns),
        "ann_vol": annualized_volatility(returns),
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "calmar": calmar_ratio(returns),
        "max_drawdown": depth,
        "hit_rate": hit_rate(returns),
        "var_95": tail["var"],
        "cvar_95": tail["cvar"],
    }


def tracking_error(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """Annualized standard deviation of active returns.

    Args:
        returns: Strategy per-period returns.
        benchmark_returns: Benchmark per-period returns; inner-joined to
            ``returns`` on the index before computing active returns.
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        Annualized tracking error, or ``nan`` if fewer than 2 aligned
        observations are available.
    """
    aligned = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return float("nan")
    active = aligned.iloc[:, 0].astype(float) - aligned.iloc[:, 1].astype(float)
    return float(active.std(ddof=1) * math.sqrt(periods_per_year))


def information_ratio(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    periods_per_year: int = 252,
) -> float:
    """Annualized active return divided by tracking error.

    Args:
        returns: Strategy per-period returns.
        benchmark_returns: Benchmark per-period returns; inner-joined to
            ``returns`` on the index before computing active returns.
        periods_per_year: Trading periods in a year (default 252).

    Returns:
        The information ratio; ``nan`` if fewer than 2 aligned observations
        or tracking error is zero.
    """
    te = tracking_error(returns, benchmark_returns, periods_per_year)
    if math.isnan(te) or te == 0.0:
        return float("nan")
    aligned = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    active = aligned.iloc[:, 0].astype(float) - aligned.iloc[:, 1].astype(float)
    return float(active.mean() * periods_per_year / te)


def beta(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """CAPM beta of strategy returns versus benchmark returns."""
    aligned = pd.concat([returns, benchmark_returns], axis=1, join="inner").dropna()
    if len(aligned) < 2:
        return float("nan")
    r = aligned.iloc[:, 0].astype(float)
    b = aligned.iloc[:, 1].astype(float)
    bench_var = float(b.var(ddof=1))
    if bench_var == 0.0:
        return float("nan")
    cov = float(r.cov(b))
    return cov / bench_var


def alpha(
    returns: pd.Series,
    benchmark_returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Annualized CAPM alpha of strategy returns versus benchmark returns."""
    b = beta(returns, benchmark_returns)
    if math.isnan(b):
        return float("nan")
    ann_strategy = annualized_return(returns, periods_per_year)
    ann_benchmark = annualized_return(benchmark_returns, periods_per_year)
    if math.isnan(ann_strategy) or math.isnan(ann_benchmark):
        return float("nan")
    return float((ann_strategy - risk_free_rate) - b * (ann_benchmark - risk_free_rate))


def benchmark_summary(
    equity_curve: pd.Series,
    benchmark: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict[str, float]:
    """Benchmark-aware metrics for a strategy equity curve.

    Args:
        equity_curve: Strategy equity values.
        benchmark: Benchmark equity or price values on a comparable index.
        risk_free_rate: Annual risk-free rate used for alpha.
        periods_per_year: Trading periods per year.

    Returns:
        Dict with ``alpha``, ``beta``, ``tracking_error``,
        ``information_ratio``, and annualized active return.
    """
    strategy_returns = equity_curve.astype(float).pct_change().dropna()
    benchmark_returns = benchmark.astype(float).pct_change().dropna()
    strategy_ann = annualized_return(strategy_returns, periods_per_year)
    benchmark_ann = annualized_return(benchmark_returns, periods_per_year)
    active_ann = (
        strategy_ann - benchmark_ann
        if not math.isnan(strategy_ann) and not math.isnan(benchmark_ann)
        else float("nan")
    )
    return {
        "alpha": alpha(strategy_returns, benchmark_returns, risk_free_rate, periods_per_year),
        "beta": beta(strategy_returns, benchmark_returns),
        "tracking_error": tracking_error(strategy_returns, benchmark_returns, periods_per_year),
        "information_ratio": information_ratio(
            strategy_returns, benchmark_returns, periods_per_year
        ),
        "active_ann_return": active_ann,
    }
