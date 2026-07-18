"""Contract-test collection hooks, requirement-ID validation, and project fixture."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
if str(_FIXTURES) not in sys.path:
    sys.path.insert(0, str(_FIXTURES))

from support.env import make_project_root, open_market_project  # noqa: E402
from support.ids import is_valid_id  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

    from persistra import Project


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Fail collection if any declared ``contract_id`` violates the ID grammar."""
    invalid: list[str] = []
    for item in items:
        for marker in item.iter_markers(name="contract_id"):
            for value in marker.args:
                if not isinstance(value, str) or not is_valid_id(value):
                    invalid.append(f"{item.nodeid}: {value!r}")
    if invalid:
        raise pytest.UsageError("invalid contract requirement ids:\n" + "\n".join(invalid))


@pytest.fixture
def project(tmp_path: Path) -> Iterator[Project]:
    """Yield a fresh market-write project session at the deterministic clock."""
    root = make_project_root(tmp_path)
    with open_market_project(root) as opened:
        yield opened
