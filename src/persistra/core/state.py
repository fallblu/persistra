from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioState:
    """Immutable portfolio snapshot handed to strategies each bar."""

    equity: float
    cash: float
    positions: dict[str, float]  # symbol -> shares
    weights: dict[str, float]  # symbol -> fraction of equity (mark-to-market)
    gross_exposure: float  # sum(|weight|)
    net_exposure: float  # sum(weight)
