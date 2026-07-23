from scripts.check_docs import (
    _markdown_paragraphs,  # pyright: ignore[reportPrivateUsage]
    _validate_style,  # pyright: ignore[reportPrivateUsage]
)


def test_markdown_paragraphs_exclude_literal_technical_content() -> None:
    text = """A short descriptive sentence.

```python
statement = "SELECT 1; SELECT 2"
```

Use `value;other` as the identifier.
"""
    failures: list[str] = []

    _validate_style(
        label="sample.md",
        paragraphs=_markdown_paragraphs(text),
        sentence_limit=25,
        failures=failures,
    )

    assert failures == []


def test_style_check_reports_mechanical_ste_failures() -> None:
    failures: list[str] = []
    paragraphs = (
        "This sentence has a semicolon; it also has a contraction that isn't permitted.",
        "One. Two. Three. Four. Five. Six. Seven.",
        "This procedural sentence contains more than twenty words because it has too much "
        "unnecessary information for one clear instruction to the reader.",
    )

    _validate_style(
        label="sample",
        paragraphs=paragraphs,
        sentence_limit=20,
        failures=failures,
    )

    assert any("semicolon" in failure for failure in failures)
    assert any("contraction" in failure for failure in failures)
    assert any("7 sentences" in failure for failure in failures)
    assert any("maximum 20" in failure for failure in failures)
