from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from persistra.cli import main
from persistra.errors import ProjectConfigError
from persistra.logging import StructuredLogEntry, safe_error, safe_log_context

if TYPE_CHECKING:
    from pathlib import Path

    from pytest import CaptureFixture


def test_structured_log_context_is_bounded_and_redacted() -> None:
    context = safe_log_context(
        {
            "api_token": "do-not-log",
            "database_path": "/private/customer/project.duckdb",
            "request_payload": {"licensed": [1, 2, 3]},
            "safe_count": 7,
            "description": "x" * 300,
            "nested": {"password": "hidden", "status": "complete"},
        }
    )
    assert context["api_token"] == "[REDACTED]"
    assert context["database_path"] == "[PATH]"
    assert context["request_payload"] == "[OMITTED]"
    assert context["safe_count"] == 7
    assert len(str(context["description"])) == 256
    assert context["nested"] == {
        "password": "[REDACTED]",
        "status": "complete",
    }
    encoded = json.dumps(context)
    assert "do-not-log" not in encoded
    assert "/private/customer" not in encoded


def test_long_context_keys_truncate_without_colliding() -> None:
    first = "shared_prefix_" + "a" * 80 + "_one"
    second = "shared_prefix_" + "a" * 80 + "_two"
    context = safe_log_context({first: 1, second: 2})
    assert len(context) == 2
    assert all(len(key) <= 64 for key in context)
    assert set(context.values()) == {1, 2}


def test_safe_error_omits_messages_and_redacts_context() -> None:
    error = ProjectConfigError(
        "credential abc and /private/path must not escape",
        context={"password": "abc", "config_path": "/private/path"},
    )
    evidence = safe_error(error)
    assert evidence == {
        "error_type": "ProjectConfigError",
        "reason_code": "project.config.invalid",
        "context": {"config_path": "[PATH]", "password": "[REDACTED]"},
    }
    assert "credential" not in json.dumps(evidence)


def test_log_entry_and_cli_failure_are_typed_and_safe(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    with pytest.raises(ValueError):
        StructuredLogEntry("fatal", "component", "event", "reason", {})
    missing = tmp_path / "private-customer-project"
    assert main(["project", "inspect", str(missing)]) == 2
    output = json.loads(capsys.readouterr().err)
    assert output["error"]["reason_code"] == "project.config.not_found"
    assert str(missing) not in json.dumps(output)
