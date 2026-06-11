import dataclasses

import pytest

from persistra.core.state import PortfolioState


def test_portfolio_state_is_frozen():
    s = PortfolioState(
        equity=1.0, cash=1.0, positions={}, weights={}, gross_exposure=0.0, net_exposure=0.0
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.equity = 2.0  # type: ignore[misc]
