"""Validate documentation structure, links, and Python snippets."""

from __future__ import annotations

import ast
import importlib
import io
import os
import re
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from persistra.model._frames import FRAME_CONTRACTS, FrameContract

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_SCHEMA_MARKER = re.compile(r"<!-- frame-contract: ([a-z0-9-]+) -->")
_SCHEMA_TARGET = re.compile(r"`([^`]+)` uses this schema:\s*$")


@dataclass(frozen=True, slots=True)
class _DocumentedSchema:
    """Machine-readable contract facts parsed from one schema-reference section."""

    name: str
    target: str
    dtypes: tuple[tuple[str, str], ...]
    required: tuple[str, ...]
    identity_key: tuple[str, ...]
    sort_by: tuple[str, ...]
    invariants: tuple[str, ...]

REQUIRED = (
    "index.md",
    "getting-started/installation.md",
    "getting-started/quickstart.md",
    "getting-started/trading-engine.md",
    "getting-started/alpha-vantage.md",
    "getting-started/fred.md",
    "guides/acquisition.md",
    "guides/cache-offline.md",
    "guides/inspection.md",
    "guides/storage.md",
    "guides/transforms.md",
    "guides/research.md",
    "guides/portfolio.md",
    "guides/projects.md",
    "guides/strategy-development.md",
    "guides/trading-engine.md",
    "guides/analysis.md",
    "guides/visualization.md",
    "guides/errors.md",
    "concepts/architecture.md",
    "concepts/data-model.md",
    "concepts/documentation-platform.md",
    "concepts/time-provenance.md",
    "examples/index.md",
    "examples/data-and-features.md",
    "examples/factor-models.md",
    "examples/portfolio-optimization.md",
    "examples/strategy-lifecycle.md",
    "examples/composite-strategies.md",
    "examples/trading-engine-replay.md",
    "examples/analysis-and-visualization.md",
    "reference/index.md",
    "reference/model.md",
    "reference/data.md",
    "reference/alphavantage.md",
    "reference/fred.md",
    "reference/analysis.md",
    "reference/research.md",
    "reference/portfolio.md",
    "reference/project.md",
    "reference/trading-engine.md",
    "reference/visualization.md",
    "reference/schemas.md",
    "reference/errors.md",
)

EXECUTABLE_PAGES = (
    "README.md",
    "docs/index.md",
    "docs/getting-started/quickstart.md",
    "docs/examples/factor-models.md",
    "docs/examples/portfolio-optimization.md",
    "docs/examples/strategy-lifecycle.md",
    "docs/guides/analysis.md",
    "docs/guides/research.md",
    "docs/guides/portfolio.md",
    "docs/guides/transforms.md",
    "docs/guides/visualization.md",
    "docs/concepts/architecture.md",
    "docs/concepts/data-model.md",
    "docs/reference/index.md",
)

EXECUTABLE_SECTIONS = {
    "docs/concepts/time-provenance.md": "## Retrieval-time revisions",
    "docs/examples/data-and-features.md": "## Provider-backed acquisition",
}


def main() -> None:
    """Validate page coverage, links, public imports, and offline examples."""
    os.environ["MPLBACKEND"] = "Agg"
    docs = Path("docs")
    failures: list[str] = []
    navigation = Path("mkdocs.yml").read_text(encoding="utf-8")
    for relative in REQUIRED:
        path = docs / relative
        if not path.is_file():
            failures.append(f"missing required documentation: {path}")
        if relative not in navigation:
            failures.append(f"documentation is absent from navigation: {relative}")
    discovered_pages = tuple(str(path.relative_to(docs)) for path in sorted(docs.rglob("*.md")))
    unexpected_pages = sorted(set(discovered_pages).difference(REQUIRED))
    if unexpected_pages:
        failures.append(
            "documentation pages are absent from the required set: "
            + ", ".join(unexpected_pages)
        )
    discovered_notebooks = sorted(docs.rglob("*.ipynb"))
    if discovered_notebooks:
        failures.append("Jupyter notebooks are not part of the documentation suite")
    for path in (Path("README.md"), *sorted(docs.rglob("*.md"))):
        text = path.read_text(encoding="utf-8")
        for target in _LINK.findall(text):
            clean = target.split("#", 1)[0]
            if not clean or "://" in clean or clean.startswith("mailto:"):
                continue
            if not (path.parent / clean).resolve().is_file():
                failures.append(f"{path}: missing link target {target}")
        for number, snippet in enumerate(_PYTHON_FENCE.findall(text), 1):
            try:
                compile(snippet, f"{path}:python-fence-{number}", "exec")
            except SyntaxError as error:
                failures.append(f"{path}: invalid Python fence {number}: {error.msg}")
                continue
            failures.extend(_public_import_failures(path, number, snippet))
    schema_path = docs / "reference/schemas.md"
    if schema_path.is_file():
        failures.extend(schema_reference_failures(schema_path.read_text(encoding="utf-8")))
    failures.extend(_executable_example_failures())
    if failures:
        raise SystemExit("\n".join(failures))


def schema_reference_failures(
    text: str,
    contracts: tuple[FrameContract, ...] = FRAME_CONTRACTS,
) -> list[str]:
    """Return actionable drift between runtime contracts and the schema reference."""
    documented, failures = _parse_documented_schemas(text)
    expected = {contract.name: contract for contract in contracts}
    observed = {schema.name: schema for schema in documented}
    duplicate_names = sorted(
        name for name in observed if sum(schema.name == name for schema in documented) > 1
    )
    if duplicate_names:
        failures.append(f"schema reference has duplicate contracts: {duplicate_names}")
    missing = sorted(set(expected).difference(observed))
    extra = sorted(set(observed).difference(expected))
    if missing:
        failures.append(f"schema reference is missing public families: {missing}")
    if extra:
        failures.append(f"schema reference has unknown public families: {extra}")
    for name in expected.keys() & observed.keys():
        contract = expected[name]
        schema = observed[name]
        prefix = f"docs/reference/schemas.md [{name}]"
        if schema.target != contract.target:
            failures.append(
                f"{prefix}: target differs: expected {contract.target!r}, got {schema.target!r}"
            )
        documented_columns = tuple(column for column, _dtype in schema.dtypes)
        expected_columns = tuple(contract.dtypes)
        if documented_columns != expected_columns:
            failures.append(
                f"{prefix}: column order differs: expected {expected_columns}, "
                f"got {documented_columns}"
            )
        documented_dtypes = dict(schema.dtypes)
        for column in expected_columns:
            if column not in documented_dtypes:
                continue
            expected_dtype = contract.dtypes[column]
            if documented_dtypes[column] != expected_dtype:
                failures.append(
                    f"{prefix}: {column} dtype differs: expected {expected_dtype!r}, "
                    f"got {documented_dtypes[column]!r}"
                )
        _append_sequence_difference(
            failures, prefix, "required values", contract.required, schema.required
        )
        _append_sequence_difference(
            failures, prefix, "identity key", contract.identity_key, schema.identity_key
        )
        _append_sequence_difference(
            failures, prefix, "sort order", contract.sort_by, schema.sort_by
        )
        _append_sequence_difference(
            failures, prefix, "invariants", contract.invariants, schema.invariants
        )
    return failures


def _append_sequence_difference(
    failures: list[str],
    prefix: str,
    label: str,
    expected: tuple[str, ...],
    documented: tuple[str, ...],
) -> None:
    if documented != expected:
        failures.append(f"{prefix}: {label} differ: expected {expected}, got {documented}")


def _parse_documented_schemas(text: str) -> tuple[list[_DocumentedSchema], list[str]]:
    """Parse annotated Markdown schema tables without evaluating Markdown or code."""
    markers = list(_SCHEMA_MARKER.finditer(text))
    schemas: list[_DocumentedSchema] = []
    failures: list[str] = []
    for index, marker in enumerate(markers):
        name = marker.group(1)
        target_match = _SCHEMA_TARGET.search(text[: marker.start()])
        target = "" if target_match is None else target_match.group(1)
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        block = text[marker.end() : end]
        facts_text = re.sub(r"\n  ", " ", block.split("| Column", 1)[0])
        facts: dict[str, tuple[str, ...]] = {}
        for line in facts_text.splitlines():
            if not line.startswith("- ") or ":" not in line:
                continue
            label, value = line[2:].split(":", 1)
            facts[label] = tuple(re.findall(r"`([^`]+)`", value))
        required_labels = {"Required values", "Identity key", "Sort order", "Invariant checks"}
        absent_labels = sorted(required_labels.difference(facts))
        if absent_labels:
            failures.append(
                f"docs/reference/schemas.md [{name}]: missing contract facts {absent_labels}"
            )
        table_match = re.search(
            r"\| Column \| pandas dtype \|[^\n]*\n\|[-| ]+\|\n((?:\|[^\n]+\|\n)+)",
            block,
        )
        dtypes: list[tuple[str, str]] = []
        if table_match is None:
            failures.append(f"docs/reference/schemas.md [{name}]: missing schema table")
        else:
            for row in table_match.group(1).splitlines():
                cells = [cell.strip().strip("`") for cell in row.strip("|").split("|")]
                if len(cells) >= 2:
                    dtypes.append((cells[0], cells[1]))
        schemas.append(
            _DocumentedSchema(
                name=name,
                target=target,
                dtypes=tuple(dtypes),
                required=facts.get("Required values", ()),
                identity_key=facts.get("Identity key", ()),
                sort_by=facts.get("Sort order", ()),
                invariants=facts.get("Invariant checks", ()),
            )
        )
    return schemas, failures


def _public_import_failures(path: Path, number: int, snippet: str) -> list[str]:
    """Return failures for documented imports absent from the installed package."""
    failures: list[str] = []
    tree = ast.parse(snippet)
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if node.module != "persistra" and not node.module.startswith("persistra."):
            continue
        try:
            module = importlib.import_module(node.module)
        except ImportError as error:
            failures.append(
                f"{path}: Python fence {number} cannot import {node.module}: {error}"
            )
            continue
        for alias in node.names:
            if alias.name != "*" and not hasattr(module, alias.name):
                failures.append(
                    f"{path}: Python fence {number} imports missing public name "
                    f"{node.module}.{alias.name}"
                )
    return failures


def _executable_example_failures() -> list[str]:
    """Run complete offline documentation narratives in isolated directories."""
    failures: list[str] = []
    original_directory = Path.cwd()
    sources = [(relative, None) for relative in EXECUTABLE_PAGES]
    sources.extend(EXECUTABLE_SECTIONS.items())
    for relative, stop_marker in sources:
        path = original_directory / relative
        text = path.read_text(encoding="utf-8")
        if stop_marker is not None:
            text = text.split(stop_marker, 1)[0]
        snippets = _PYTHON_FENCE.findall(text)
        program = "\n\n".join(snippets)
        output = io.StringIO()
        with TemporaryDirectory() as directory:
            os.chdir(directory)
            try:
                with redirect_stdout(output), redirect_stderr(output):
                    exec(compile(program, str(path), "exec"), {"__name__": "__main__"})
            except Exception as error:
                failures.append(
                    f"{relative}: offline example execution failed: "
                    f"{type(error).__name__}: {error}"
                )
            finally:
                os.chdir(original_directory)
                _close_figures()
    return failures


def _close_figures() -> None:
    """Close figures created while validating documentation examples."""
    from matplotlib import pyplot as plt

    plt.close("all")


if __name__ == "__main__":
    main()
