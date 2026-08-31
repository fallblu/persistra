"""Shared failure redaction for live provider certification."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


def redacted_call(label: str, stage: str, acquire: Callable[[], Any]) -> Any:
    """Run one live operation without rendering provider exception content."""
    try:
        return acquire()
    except Exception as error:
        raise AssertionError(
            f"{label} {stage} failed with {type(error).__name__}"
        ) from None
