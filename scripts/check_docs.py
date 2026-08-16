"""Validate documentation structure, links, and Python snippets."""

from __future__ import annotations

import ast
import importlib
import io
import os
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)

REQUIRED = (
    "index.md",
    "getting-started/installation.md",
    "getting-started/quickstart.md",
    "getting-started/trading-engine.md",
    "getting-started/alpha-vantage.md",
    "getting-started/fred.md",
    "guides/acquisition.md",
    "guides/cache-offline.md",
    "guides/storage.md",
    "guides/transforms.md",
    "guides/research.md",
    "guides/portfolio.md",
    "guides/strategy-development.md",
    "guides/trading-engine.md",
    "guides/analysis.md",
    "guides/visualization.md",
    "guides/errors.md",
    "concepts/architecture.md",
    "concepts/data-model.md",
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
    failures.extend(_executable_example_failures())
    if failures:
        raise SystemExit("\n".join(failures))


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
