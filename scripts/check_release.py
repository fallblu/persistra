"""Validate the repository state associated with one release tag."""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path


def project_version(path: Path = Path("pyproject.toml")) -> str:
    """Return the declared project version."""
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    version = document["project"]["version"]
    if not isinstance(version, str):
        raise ValueError("project version must be a string")
    return version


def validate_release_tag(tag: str, version: str) -> None:
    """Require the exact release tag for a project version."""
    expected = f"v{version}"
    if tag != expected:
        raise ValueError(f"release tag must be {expected}, not {tag}")


def require_annotated_tag(tag: str) -> None:
    """Require a local Git tag object rather than a lightweight tag."""
    result = subprocess.run(
        ["git", "cat-file", "-t", f"refs/tags/{tag}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ValueError(f"release tag is unavailable: {tag}")
    if result.stdout.strip() != "tag":
        raise ValueError(f"release tag must be annotated: {tag}")


def main() -> None:
    """Validate one tag supplied by tag-triggered CI."""
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_release.py TAG")
    tag = sys.argv[1]
    try:
        validate_release_tag(tag, project_version())
        require_annotated_tag(tag)
    except ValueError as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
