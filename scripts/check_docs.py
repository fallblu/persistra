"""Validate documentation structure, links, and Python snippets."""

from __future__ import annotations

import re
from pathlib import Path

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)

REQUIRED = (
    "index.md",
    "roadmap.md",
    "foundation-assurance.md",
    "getting-started/installation.md",
    "getting-started/quickstart.md",
    "getting-started/alpha-vantage.md",
    "tutorials/market-research.md",
    "tutorials/options-research.md",
    "tutorials/economic-research.md",
    "guides/acquisition.md",
    "guides/cache-offline.md",
    "guides/storage.md",
    "guides/transforms.md",
    "guides/analysis.md",
    "guides/visualization.md",
    "guides/errors.md",
    "concepts/architecture.md",
    "concepts/data-model.md",
    "concepts/time-provenance.md",
    "examples/snippets.md",
    "reference/index.md",
    "reference/model.md",
    "reference/data.md",
    "reference/alphavantage.md",
    "reference/analysis.md",
    "reference/visualization.md",
    "reference/schemas.md",
    "reference/errors.md",
)


def main() -> None:
    """Validate page coverage, local links, and Python snippets."""
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
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
