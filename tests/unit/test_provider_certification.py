"""Failure-redaction contracts for live provider certification."""

from __future__ import annotations

import pytest

from tests.live._redaction import redacted_call


def test_live_provider_failures_expose_only_operation_phase_and_error_class() -> None:
    secret_and_observation = "credential-and-licensed-observation"

    def fail() -> None:
        raise ValueError(secret_and_observation)

    with pytest.raises(AssertionError) as captured:
        redacted_call("operation", "refresh", fail)

    message = str(captured.value)
    assert message == "operation refresh failed with ValueError"
    assert secret_and_observation not in message
    assert captured.value.__cause__ is None
