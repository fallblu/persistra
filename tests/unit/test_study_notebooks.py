from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = (
    "01_growth_inflation_quadrants.ipynb",
    "02_labor_deterioration.ipynb",
    "03_yield_curve_inversion.ipynb",
    "04_inflation_momentum.ipynb",
    "05_revision_risk.ipynb",
)


@pytest.mark.parametrize("name", NOTEBOOKS)
def test_study_notebook_has_no_committed_execution_artifacts(name: str) -> None:
    notebook = json.loads((ROOT / "studies" / name).read_text(encoding="utf-8"))

    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]

    assert code_cells
    assert all(cell["execution_count"] is None for cell in code_cells)
    assert all(cell["outputs"] == [] for cell in code_cells)


def test_study_notebooks_match_reviewable_source() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_studies.py", "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_study_static_policy_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/check_studies.py"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
