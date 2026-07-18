"""Documentation topology, link, and Python-snippet validation."""

import re
from pathlib import Path

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def main() -> None:
    """Validate required public documentation and release-boundary statements."""
    docs = Path("docs")
    required = (
        docs / "index.md",
        docs / "guide.md",
        docs / "api-reference.md",
        docs / "implementation-status.md",
        docs / "assumptions-and-limitations.md",
        docs / "migration-guide.md",
        docs / "release-readiness.md",
        docs / "adr" / "0001-adopt-streamlit-dashboard.md",
        docs / "v3" / "v3-spec.md",
        docs / "v3" / "phase-plan.md",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing required documentation: {', '.join(missing)}")
    _validate_navigation(required)
    _validate_markdown(docs)
    index = (docs / "index.md").read_text(encoding="utf-8")
    stale = ("phase-4 simulator", "assigned to later phases")
    if any(value in index for value in stale):
        raise SystemExit("documentation index contains stale implementation status")
    readiness = (docs / "release-readiness.md").read_text(encoding="utf-8")
    if (
        "human-controlled" not in readiness
        or "static" not in readiness
        or "pre-release" not in readiness
    ):
        raise SystemExit("release boundary documentation is incomplete")


def _validate_navigation(required: tuple[Path, ...]) -> None:
    navigation = Path("mkdocs.yml").read_text(encoding="utf-8")
    absent = [
        str(path)
        for path in required
        if path.name not in {"v3-spec.md", "phase-plan.md"}
        and str(path.relative_to("docs")) not in navigation
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
