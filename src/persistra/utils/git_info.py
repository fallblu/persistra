from __future__ import annotations

import subprocess


def git_info() -> dict[str, str | bool]:
    """Return git repo metadata. Falls back to safe defaults on any error."""
    try:
        sha: str = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )
    except Exception:
        sha = "unknown"

    try:
        dirty: bool = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
            ).strip()
        )
    except Exception:
        dirty = False

    try:
        branch: str = (
            subprocess.check_output(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        branch = "unknown"

    try:
        remote: str = (
            subprocess.check_output(
                ["git", "remote", "get-url", "origin"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        remote = "unknown"

    return {"git_sha": sha, "git_dirty": dirty, "git_branch": branch, "git_remote": remote}
