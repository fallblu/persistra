"""Validate documentation structure, links, and Python snippets."""

from __future__ import annotations

import re
from pathlib import Path

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)

REQUIRED = (
    "index.md",
    "getting-started.md",
    "data-model.md",
    "acquisition.md",
    "analysis.md",
    "reference/api.md",
    "roadmap.md",
)


def main() -> None:
    """Validate required pages, local links, and Python snippets."""
    docs = Path("docs")
    failures: list[str] = []
    navigation = Path("mkdocs.yml").read_text(encoding="utf-8")
    for relative in REQUIRED:
        path = docs / relative
        if not path.is_file():
            failures.append(f"missing required documentation: {path}")
        if relative not in navigation:
            failures.append(f"documentation is absent from navigation: {relative}")
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
