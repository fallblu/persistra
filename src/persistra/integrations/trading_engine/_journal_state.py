"""Mutable reducer state used while reconciling audit journals."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(slots=True)
class PositionState:
    """Exact position accounting accumulated from journal events."""

    quantity: int = 0
    cost_basis: int = 0
    realized_pnl: int = 0
    dividend_pnl: int = 0
    execution_fees: int = 0
    borrow_fees: int = 0


def copy_positions(states: Mapping[str, PositionState]) -> dict[str, PositionState]:
    """Copy reducer state before testing a proposed transition."""
    return {
        instrument_id: PositionState(
            quantity=state.quantity,
            cost_basis=state.cost_basis,
            realized_pnl=state.realized_pnl,
            dividend_pnl=state.dividend_pnl,
            execution_fees=state.execution_fees,
            borrow_fees=state.borrow_fees,
        )
        for instrument_id, state in states.items()
    }


def ceil_div(numerator: int, denominator: int) -> int:
    """Divide integers toward positive infinity."""
    if numerator < 0 or denominator <= 0:
        raise ValueError("ceil division requires nonnegative numerator and positive denominator")
    return 0 if numerator == 0 else (numerator - 1) // denominator + 1


def trunc_div(numerator: int, denominator: int) -> int:
    """Divide integers toward zero."""
    if denominator <= 0:
        raise ValueError("truncating division requires a positive denominator")
    magnitude = abs(numerator) // denominator
    return -magnitude if numerator < 0 else magnitude


def round_toward_zero(value: int, multiple: int) -> int:
    """Round a signed integer toward zero to an exact multiple."""
    if multiple <= 0:
        raise ValueError("rounding multiple must be positive")
    return trunc_div(value, multiple) * multiple
