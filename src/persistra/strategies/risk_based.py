from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from persistra.pipeline import VolTarget
from persistra.strategy.base import Strategy

if TYPE_CHECKING:
    from persistra.strategy.context import StrategyContext


class VolTargetedEqualWeight(Strategy):
    """Equal-weight directional signal, sized to a volatility target.

    Emits a long, equal-direction signal over the whole universe and runs it
    through the existing :class:`~persistra.pipeline.sizing.VolTarget` sizer so
    each leg's standalone volatility hits ``annual_vol / n``.

    Args:
        annual_vol: Target portfolio annualized volatility.
        lookback: Bars of history used to estimate realized vol; sets warmup.
    """

    timeframes = ("1d",)

    def __init__(self, annual_vol: float = 0.10, lookback: int = 60) -> None:
        if annual_vol <= 0:
            raise ValueError("annual_vol must be > 0")
        if lookback < 2:
            raise ValueError("lookback must be >= 2")
        self.annual_vol = annual_vol
        self.lookback = lookback
        self.warmup = lookback
        self._sizer = VolTarget(annual_vol=annual_vol, lookback=lookback)

    def on_bar(self, ctx: StrategyContext) -> None:
        """Emit a unit long signal over the full universe, sized to the vol target.

        Assigns a direction of ``1.0`` to every symbol in ``ctx.universe`` and
        passes it through the ``VolTarget`` sizer so that each leg's standalone
        annualized volatility equals ``annual_vol / n``. Returns early if the
        universe is empty.

        Args:
            ctx: Point-in-time context providing universe membership and signal
                emission.
        """
        universe = ctx.universe
        if not universe:
            return
        direction = pd.Series({sym: 1.0 for sym in universe})
        ctx.signal(direction, sizer=self._sizer)
