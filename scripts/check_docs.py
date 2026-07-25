"""Validate documentation structure, links, snippets, and controlled-language rules."""

import ast
import re
from pathlib import Path

_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
_PYTHON_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_CONTRACTION = re.compile(r"\b\w+(?:n't|'re|'ve|'ll|'d|'m)\b", re.IGNORECASE)
_LATIN_ABBREVIATION = re.compile(r"\b(?:e\.g\.|i\.e\.|etc\.)", re.IGNORECASE)
_SENTENCE = re.compile(r"[^.!?]+[.!?]+|[^.!?]+$")
_WORD = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")

REQUIRED = (
    "index.md",
    "reference/api/index.md",
    "reference/api/sources.md",
    "reference/cli.md",
    "reference/metric-catalog.md",
    "reference/export-formats.md",
)

ROOT_DOCUMENTATION = (
    Path("AGENTS.md"),
    Path("CHANGELOG.md"),
    Path("CONTRIBUTING.md"),
    Path("README.md"),
)


def main() -> None:
    """Validate all repository documentation and public API docstrings."""
    docs = Path("docs")
    required = tuple(docs / name for name in REQUIRED)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"missing required documentation: {', '.join(missing)}")
    _validate_navigation(required)
    _validate_markdown((*ROOT_DOCUMENTATION, *sorted(docs.rglob("*.md"))))
    _validate_docstrings(Path("src/persistra"))


def _validate_navigation(required: tuple[Path, ...]) -> None:
    """Make sure that navigation contains each necessary public document."""
    navigation = Path("mkdocs.yml").read_text(encoding="utf-8")
    absent = [str(path) for path in required if str(path.relative_to("docs")) not in navigation]
    if absent:
        raise SystemExit(f"public documentation is absent from navigation: {', '.join(absent)}")


def _validate_markdown(paths: tuple[Path, ...]) -> None:
    """Validate links, Python snippets, and controlled language in Markdown files."""
    failures: list[str] = []
    for path in paths:
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
        _validate_style(
            label=str(path),
            paragraphs=_markdown_paragraphs(text),
            sentence_limit=25,
            failures=failures,
        )
    if failures:
        raise SystemExit("\n".join(failures))


def _validate_docstrings(source: Path) -> None:
    """Validate controlled language in each public API docstring."""
    failures: list[str] = []
    for path in sorted(source.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        nodes: list[ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = [tree]
        nodes.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        )
        for node in nodes:
            docstring = ast.get_docstring(node, clean=True)
            if not docstring:
                continue
            name = "<module>" if isinstance(node, ast.Module) else node.name
            line = node.body[0].lineno
            limit = 20 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else 25
            _validate_style(
                label=f"{path}:{line}:{name}",
                paragraphs=_docstring_paragraphs(docstring),
                sentence_limit=limit,
                failures=failures,
            )
    if failures:
        raise SystemExit("\n".join(failures))


def _markdown_paragraphs(text: str) -> tuple[str, ...]:
    """Return Markdown prose paragraphs without literal technical content."""
    paragraphs: list[str] = []
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        if current:
            paragraphs.append(" ".join(current))
            current.clear()

    for source_line in text.splitlines():
        line = source_line.strip()
        if line.startswith("```"):
            flush()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line:
            flush()
            continue
        if line.startswith("#") or line.startswith(":::") or re.match(r"^\[[^\]]+\]:", line):
            flush()
            continue
        line = _MARKDOWN_LINK.sub(r"\1", line)
        line = _INLINE_CODE.sub("TOKEN", line)
        if line.startswith("|"):
            flush()
            paragraphs.extend(cell.strip() for cell in line.split("|") if cell.strip())
            continue
        if re.match(r"^(?:[-*+]|\d+\.)\s+", line):
            flush()
            item = re.sub(r"^(?:[-*+]|\d+\.)\s+", "", line)
            item = re.sub(r"^\*\*[^*]+\*\*\s*", "", item)
            current.append(item.replace("**", "").replace("__", ""))
            continue
        current.append(line.replace("**", "").replace("__", ""))
    flush()
    return tuple(paragraphs)


def _docstring_paragraphs(text: str) -> tuple[str, ...]:
    """Return docstring paragraphs without literal technical content."""
    clean = re.sub(r"``[^`]*``|:[a-z]+:`[^`]*`", "TOKEN", text)
    return tuple(
        re.sub(r"\s+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", clean)
        if paragraph.strip()
    )


def _validate_style(
    *,
    label: str,
    paragraphs: tuple[str, ...],
    sentence_limit: int,
    failures: list[str],
) -> None:
    """Add deterministic ASD-STE100 style failures to the failure list."""
    for paragraph in paragraphs:
        if ";" in paragraph:
            failures.append(f"{label}: semicolon in prose")
        if _CONTRACTION.search(paragraph):
            failures.append(f"{label}: contraction in prose")
        if _LATIN_ABBREVIATION.search(paragraph):
            failures.append(f"{label}: Latin abbreviation in prose")
        sentences = [match.group().strip() for match in _SENTENCE.finditer(paragraph)]
        if len(sentences) > 6:
            failures.append(f"{label}: paragraph has {len(sentences)} sentences (maximum 6)")
        for sentence in sentences:
            word_count = len(_WORD.findall(sentence))
            if word_count > sentence_limit:
                preview = sentence[:80].replace("\n", " ")
                failures.append(
                    f"{label}: sentence has {word_count} words "
                    f"(maximum {sentence_limit}): {preview}"
                )


if __name__ == "__main__":
    main()
