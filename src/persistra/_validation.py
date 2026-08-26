"""Shared validation for public scalar contracts."""

from __future__ import annotations

from numbers import Integral


def require_integer(value: object, *, name: str, minimum: int | None = None) -> int:
    """Return a normalized integer after enforcing an optional inclusive minimum."""
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if minimum is None or result >= minimum:
        return result
    if minimum == 0:
        requirement = "a nonnegative integer"
    elif minimum == 1:
        requirement = "a positive integer"
    else:
        requirement = f"an integer of at least {minimum}"
    raise ValueError(f"{name} must be {requirement}")
