"""Normative requirement identifiers used by contract tests.

IDs follow ``V3-P<plan>-<section>-<slug>`` (spec 18 §4). Tests declare one or more
through the ``contract_id`` marker; the contracts conftest validates every declared
ID against :data:`ID_PATTERN` during collection.
"""

from __future__ import annotations

import re

import pytest

ID_PATTERN = re.compile(r"^V3-P\d{2}-\d+(?:\.\d+)?-[A-Z0-9][A-Z0-9-]*$")


def is_valid_id(value: str) -> bool:
    """Return whether a requirement ID matches the normative grammar."""
    return ID_PATTERN.fullmatch(value) is not None


def contract_id(*ids: str) -> pytest.MarkDecorator:
    """Return a ``contract_id`` marker carrying one or more validated IDs."""
    for value in ids:
        if not is_valid_id(value):
            raise ValueError(f"invalid contract requirement id: {value!r}")
    return pytest.mark.contract_id(*ids)
