"""Documentation topology, link, and Python-snippet validation."""

import re
from pathlib import Path

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)

REQUIRED = (
    "index.md",
    "getting-started/installation.md",
    "getting-started/first-project.md",
    "how-to/ingest-market-data.md",
    "how-to/build-research-datasets.md",
    "how-to/run-simulations.md",
    "how-to/run-studies.md",
    "how-to/analyze-and-report.md",
    "how-to/dashboard.md",
    "how-to/operate-projects.md",
    "reference/api/index.md",
    "reference/cli.md",
    "reference/metric-catalog.md",
    "reference/export-formats.md",
    "reference/benchmark.md",
    "explanation/architecture.md",
    "explanation/assumptions-and-limitations.md",
    "explanation/migration-from-v2.md",
    "explanation/adr-0001-streamlit-dashboard.md",
    "explanation/release-governance.md",
)


def main() -> None:
    """Validate required public documentation, navigation, links, and snippets."""
    docs = Path("docs")
    required = tuple(docs / name for name in REQUIRED)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing required documentation: {', '.join(missing)}")
    _validate_navigation(required)
    _validate_markdown(docs)
    governance = (docs / "explanation" / "release-governance.md").read_text(
        encoding="utf-8"
    )
    if (
        "human-controlled" not in governance
        or "static" not in governance
        or "pre-release" not in governance
    ):
        raise SystemExit("release boundary documentation is incomplete")


def _validate_navigation(required: tuple[Path, ...]) -> None:
    navigation = Path("mkdocs.yml").read_text(encoding="utf-8")
    absent = [
        str(path)
        for path in required
        if str(path.relative_to("docs")) not in navigation
    ]
    if absent:
        raise SystemExit(f"public documentation is absent from navigation: {', '.join(absent)}")


def _validate_markdown(docs: Path) -> None:
    failures: list[str] = []
    for path in sorted(docs.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        for target in _LINK.findall(text):
            clean = target.split("#", 1)[0]
            if not clean or "://" in clean or clean.startswith("mailto:"):
                continue
            resolved = (path.parent / clean).resolve()
            if not resolved.is_file():
                failures.append(f"{path}: missing link target {target}")
        for ordinal, snippet in enumerate(_PYTHON_FENCE.findall(text), 1):
            try:
                compile(snippet, f"{path}:python-fence-{ordinal}", "exec")
            except SyntaxError as error:
                failures.append(f"{path}: invalid Python fence {ordinal}: {error.msg}")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
