"""Global test isolation rules."""

from __future__ import annotations

import os
import socket
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True)
def prohibit_unmarked_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject socket connections from every test not marked as live."""
    if os.environ.get("PERSISTRA_RUN_LIVE") == "1":
        return

    def blocked(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError("network access is disabled in normal tests")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
