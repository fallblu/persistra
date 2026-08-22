"""Tests for incremental Trading Engine journal parsing."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from persistra.integrations.trading_engine._journal_parsing import iter_json_records

if TYPE_CHECKING:
    from pathlib import Path


def test_iter_json_records_preserves_lines_and_accepts_final_record_without_newline(
    tmp_path: Path,
) -> None:
    path = tmp_path / "records.jsonl"
    path.write_bytes(b'{"value":1}\r\n{"value":2}')

    assert list(iter_json_records(path)) == [
        (1, {"value": 1}),
        (2, {"value": 2}),
    ]


def test_iter_json_records_rejects_blank_records_with_exact_line(tmp_path: Path) -> None:
    path = tmp_path / "blank.jsonl"
    path.write_bytes(b'{"value":1}\n\n')

    with pytest.raises(ValueError, match="line 2: audit journal must not contain blank"):
        list(iter_json_records(path))


def test_iter_json_records_rejects_invalid_utf8_with_exact_line(tmp_path: Path) -> None:
    path = tmp_path / "invalid-utf8.jsonl"
    path.write_bytes(b'{"value":1}\n\xff\n')

    with pytest.raises(ValueError, match="line 2: audit journal must contain valid UTF-8"):
        list(iter_json_records(path))


def test_iter_json_records_rejects_duplicate_fields_without_payload_echo(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate.jsonl"
    path.write_bytes(b'{"secret":"first","secret":"second"}\n')

    with pytest.raises(ValueError) as captured:
        list(iter_json_records(path))

    assert "line 1: duplicate JSON field: secret" in str(captured.value)
    assert "first" not in str(captured.value)
    assert "second" not in str(captured.value)
