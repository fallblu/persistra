"""
src/persistra/core/recent.py

Manages the list of recently opened project files.

- Stored in ``~/.persistra/recent.json`` as a JSON array of file paths.
- Maximum 10 entries, most-recent first.
- Pruned on load: entries whose files no longer exist are removed.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

MAX_RECENT = 10
_CONFIG_DIR = Path.home() / ".persistra"
_RECENT_FILE = _CONFIG_DIR / "recent.json"


def _ensure_config_dir() -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_recent_projects() -> List[str]:
    """Load and prune the list of recent project paths."""
    if not _RECENT_FILE.exists():
        return []
    try:
        raw = json.loads(_RECENT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(raw, list):
        return []

    # Prune entries whose files no longer exist
    valid = [p for p in raw if isinstance(p, str) and Path(p).exists()]
    # Persist the pruned list back
    if len(valid) != len(raw):
        _save(valid)
    return valid[:MAX_RECENT]


def add_recent_project(filepath: str) -> None:
    """Add *filepath* to the top of the recent list (deduplicating)."""
    recent = load_recent_projects()
    filepath = str(Path(filepath).resolve())
    if filepath in recent:
        recent.remove(filepath)
    recent.insert(0, filepath)
    _save(recent[:MAX_RECENT])


def _save(entries: List[str]) -> None:
    _ensure_config_dir()
    _RECENT_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")
