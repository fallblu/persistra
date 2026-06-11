from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from persistra.core.history import HistoryView
    from persistra.core.state import PortfolioState
    from persistra.pipeline.allocation import AllocationRule
    from persistra.pipeline.risk import RiskConstraint
    from persistra.pipeline.sizing import Sizer


class StrategyContext:
    """Single object handed to every strategy hook.

    ``signal()`` is the sole emit method. Pass allocation/sizer/risk to run the
    pipeline inline; omit all three to treat scores as direct target weights.
    ``_fork()`` returns a sibling context with a clean emission state, used by
    CompositeStrategy to isolate child emissions.
    """

    def __init__(
        self,
        timestamp: pd.Timestamp,
        timeframe: str,
        histories: dict[str, HistoryView],
        portfolio: PortfolioState,
        universe: frozenset[str],
    ) -> None:
        self._timestamp = timestamp
        self._timeframe = timeframe
        self._histories = histories
        self._portfolio = portfolio
        self._universe = universe
        self._emitted_weights: dict[str, float] | None = None
        self._recorded: list[dict[str, object]] = []

    @property
    def timestamp(self) -> pd.Timestamp:
        """The close time of the bar that just fired."""
        return self._timestamp

    @property
    def timeframe(self) -> str:
        """The timeframe whose bar just closed."""
        return self._timeframe

    @property
    def portfolio(self) -> PortfolioState:
        """Point-in-time portfolio state (positions and cash) at bar open."""
        return self._portfolio

    @property
    def universe(self) -> frozenset[str]:
        """The set of tradable symbol names active on this bar."""
        return self._universe

    def history(self, timeframe: str | None = None) -> HistoryView:
        """Rolling view for a subscribed timeframe; defaults to the firing one."""
        if timeframe is None:
            timeframe = self._timeframe
        return self._histories[timeframe]

    def signal(
        self,
        scores: pd.Series | dict[str, float],
        *,
        allocation: AllocationRule | None = None,
        sizer: Sizer | None = None,
        risk: RiskConstraint | None = None,
    ) -> None:
        """Emit target weights, optionally running them through pipeline steps.

        ``scores`` may be a ``pd.Series`` (e.g. from ``SignalCombiner.combine``)
        or a plain ``dict``. With no pipeline args, values are stored as-is.
        """
        if isinstance(scores, dict):
            score_series = pd.Series(scores)
        else:
            score_series = scores
        weights: dict[str, float]
        if allocation is not None:
            weights = allocation.allocate(score_series)
        else:
            weights = {str(k): float(v) for k, v in score_series.to_dict().items()}
        if sizer is not None:
            weights = sizer.size(weights, self._portfolio, self._histories[self._timeframe])
        if risk is not None:
            weights = risk.project(weights)
        self._emitted_weights = dict(weights)

    def record(self, name: str, value: float | dict[str, float] | pd.Series) -> None:
        """Record a per-bar diagnostic for later inspection/plotting.

        ``value`` may be a scalar (portfolio-level diagnostic; ``symbol`` null),
        a ``dict[str, float]``, or a ``pd.Series`` indexed by symbol. Recording
        the same ``name`` twice in one bar overwrites earlier rows for that name
        (last wins). Rows are drained by the engine after ``on_bar``.
        """
        if isinstance(value, dict):
            items: list[tuple[str | None, float]] = [(str(s), float(v)) for s, v in value.items()]
        elif isinstance(value, pd.Series):
            items = [(str(s), float(v)) for s, v in value.items()]
        else:
            items = [(None, float(value))]
        # Last-wins: drop any existing rows for this name recorded this bar.
        self._recorded = [r for r in self._recorded if r["name"] != name]
        for symbol, v in items:
            self._recorded.append(
                {
                    "bar_time": self._timestamp,
                    "timeframe": self._timeframe,
                    "name": name,
                    "symbol": symbol,
                    "value": v,
                }
            )

    @property
    def recorded(self) -> list[dict[str, object]]:
        """Diagnostic rows recorded during the current hook. Read by the engine."""
        return self._recorded

    def _fork(self) -> StrategyContext:
        """Return a sibling context with a clean emission state."""
        return StrategyContext(
            timestamp=self._timestamp,
            timeframe=self._timeframe,
            histories=self._histories,
            portfolio=self._portfolio,
            universe=self._universe,
        )

    @property
    def emitted_weights(self) -> dict[str, float] | None:
        """Weights emitted during the current hook, or None. Read by the engine."""
        return self._emitted_weights
