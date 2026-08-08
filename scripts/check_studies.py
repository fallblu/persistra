"""Validate the committed cross-asset study notebooks without executing them."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

EXPECTED_NOTEBOOKS = (
    "01_growth_inflation_quadrants.ipynb",
    "02_labor_deterioration.ipynb",
    "03_yield_curve_inversion.ipynb",
    "04_inflation_momentum.ipynb",
    "05_revision_risk.ipynb",
)

ALLOWED_STUDY_FILES = frozenset(
    {"README.md", "__init__.py", "_support.py", *EXPECTED_NOTEBOOKS}
)
IGNORED_RUNTIME_DIRECTORIES = frozenset({".cache", ".executed", "__pycache__"})

REQUIRED_NARRATIVE = (
    "hypothesis",
    "point-in-time",
    "baseline",
    "uncertainty",
    "sensitivity",
    "latest-revised",
    "limitations",
    "interpretation",
)

FORBIDDEN_SOURCE = (
    "persistra.data.synthetic",
    "from persistra.data import synthetic",
    "apikey=",
    "api_key=",
)

_SECRET_ASSIGNMENT = re.compile(
    r"PERSISTRA_(?:ALPHAVANTAGE|FRED)_API_KEY\s*=\s*['\"][^'\"]+['\"]"
)


def main() -> None:
    """Report every structural or publication-safety failure."""
    failures = check_studies(Path("studies"))
    if failures:
        raise SystemExit("\n".join(failures))


def check_studies(directory: Path) -> list[str]:
    """Return deterministic failures for the expected notebook suite."""
    failures: list[str] = []
    tracked_runtime = subprocess.run(
        [
            "git",
            "ls-files",
            "--",
            "studies/.cache",
            "studies/.executed",
        ],
        cwd=directory.parent,
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked_runtime.returncode == 0 and tracked_runtime.stdout.strip():
        failures.append("tracked provider caches or executed outputs are forbidden")
    unexpected_files = sorted(
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file()
        and not set(path.relative_to(directory).parts).intersection(
            IGNORED_RUNTIME_DIRECTORIES
        )
        and str(path.relative_to(directory)) not in ALLOWED_STUDY_FILES
    )
    if unexpected_files:
        failures.append(
            "studies contains unapproved artifacts: " + ", ".join(unexpected_files)
        )
    actual = tuple(path.name for path in sorted(directory.glob("*.ipynb")))
    if actual != EXPECTED_NOTEBOOKS:
        failures.append(
            "study notebook set differs: expected "
            + ", ".join(EXPECTED_NOTEBOOKS)
            + "; found "
            + (", ".join(actual) if actual else "none")
        )
        return failures
    for name in EXPECTED_NOTEBOOKS:
        failures.extend(check_notebook(directory / name))
    return failures


def check_notebook(path: Path) -> list[str]:
    """Validate one notebook's structure, source, and cleared-output policy."""
    failures: list[str] = []
    try:
        notebook = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{path}: invalid notebook JSON: {error}"]
    if notebook.get("nbformat") != 4:
        failures.append(f"{path}: notebook format must be version 4")
    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return [*failures, f"{path}: cells must be a list"]
    markdown_sources: list[str] = []
    code_sources: list[str] = []
    cell_ids: set[str] = set()
    for number, value in enumerate(cells, 1):
        if not isinstance(value, dict):
            failures.append(f"{path}: cell {number} is not an object")
            continue
        cell = value
        cell_id = cell.get("id")
        if not isinstance(cell_id, str) or not cell_id or cell_id in cell_ids:
            failures.append(f"{path}: cell {number} has a missing or duplicate id")
        else:
            cell_ids.add(cell_id)
        source = _source_text(cell.get("source"))
        cell_type = cell.get("cell_type")
        if cell_type == "markdown":
            markdown_sources.append(source)
            if cell.get("attachments"):
                failures.append(f"{path}: markdown cell {number} embeds an attachment")
        elif cell_type == "code":
            code_sources.append(source)
            if cell.get("execution_count") is not None:
                failures.append(f"{path}: code cell {number} retains an execution count")
            if cell.get("outputs") != []:
                failures.append(f"{path}: code cell {number} retains saved output")
            try:
                compile(source, f"{path}:cell-{number}", "exec")
            except SyntaxError as error:
                failures.append(f"{path}: code cell {number} is invalid: {error.msg}")
        else:
            failures.append(f"{path}: cell {number} has unsupported type {cell_type!r}")
    markdown_count = len(markdown_sources)
    code_count = len(code_sources)
    if markdown_count < 10 or code_count < 10:
        failures.append(f"{path}: requires at least ten markdown and ten code cells")
    if abs(markdown_count - code_count) > 3:
        failures.append(
            f"{path}: markdown/code cell balance is {markdown_count}/{code_count}"
        )
    markdown = "\n".join(markdown_sources).lower()
    code = "\n".join(code_sources)
    combined = f"{markdown}\n{code.lower()}"
    raw = path.read_text(encoding="utf-8")
    for phrase in REQUIRED_NARRATIVE:
        if phrase not in markdown:
            failures.append(f"{path}: narrative omits {phrase!r}")
    for phrase in FORBIDDEN_SOURCE:
        if phrase in combined:
            failures.append(f"{path}: forbidden source fragment {phrase!r}")
    if _SECRET_ASSIGNMENT.search(raw):
        failures.append(f"{path}: serialized provider credential is forbidden")
    if code.count("plt.show()") < 6:
        failures.append(f"{path}: requires at least six explicit plot displays")
    for required_code in (
        "open_live_session",
        "acquire_monthly_prices",
        "forward_labels",
        "regime_statistics",
        "session.close()",
    ):
        if required_code not in code:
            failures.append(f"{path}: code omits {required_code!r}")
    return failures


def _source_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(part, str) for part in value):
        return "".join(value)
    return ""


if __name__ == "__main__":
    main()
