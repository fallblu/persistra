#!/usr/bin/env python
"""Execute every fenced ```python block in docs/**/*.md against the real package.

Blocks within a single page share a namespace (so a class defined in one block
is usable in the next). Blocks tagged ```python no-run are skipped.

Each block runs in its own temp directory so files a snippet writes do not litter the repo.
The read-only data directories (``examples``, ``data``) are symlinked into that temp dir so
relative paths like ``examples/sample_data`` still resolve to the real shipped
data — without this, a snippet would find no local data and either degrade to
NaN results or fall back to the live Massive API, masking a broken example.
Run from the repo root.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

DOCS = Path("docs")
DATA_DIRS = ("examples", "data")  # read-only dirs snippets reference by relative path
FENCE = re.compile(r"```python(?P<flags>[^\n]*)\n(?P<code>.*?)```", re.DOTALL)


def main() -> int:
    repo_root = Path.cwd()
    failures: list[str] = []
    pages = sorted(p for p in DOCS.rglob("*.md") if "superpowers" not in p.parts)

    for page in pages:
        ns: dict = {}
        for i, m in enumerate(FENCE.finditer(page.read_text()), start=1):
            if "no-run" in m.group("flags"):
                continue
            code = m.group("code")
            with tempfile.TemporaryDirectory() as tmp:
                for name in DATA_DIRS:
                    src = repo_root / name
                    if src.exists():
                        os.symlink(src, Path(tmp) / name)
                os.chdir(tmp)
                try:
                    exec(compile(code, f"{page}#block{i}", "exec"), ns)  # noqa: S102
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{page} block {i}: {type(exc).__name__}: {exc}")
                finally:
                    os.chdir(repo_root)

    if failures:
        print(f"Snippet failures ({len(failures)}):")
        for f in failures:
            print("  ", f)
        return 1
    print(f"All runnable snippets across {len(pages)} page(s) executed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
