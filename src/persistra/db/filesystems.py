"""This module contains Linux mount classifications for managed database durability."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from persistra.errors import UnsupportedFilesystemError

_LOCAL = frozenset({"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs", "tmpfs", "overlay"})
_DURABILITY_WARNINGS = frozenset({"tmpfs", "overlay"})


@dataclass(frozen=True, slots=True)
class FilesystemInspection:
    filesystem_type: str
    mount_point: Path
    warning: str | None


def inspect_filesystem(
    path: Path, *, allow_unsupported_read: bool = False
) -> FilesystemInspection:
    """Resolve one path to its longest matching Linux mount-info entry."""
    candidate = path.resolve() if path.exists() else path.parent.resolve()
    matches: list[tuple[Path, str]] = []
    try:
        lines = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise UnsupportedFilesystemError("Linux mount information is unavailable") from error
    for line in lines:
        left, separator, right = line.partition(" - ")
        fields = left.split()
        right_fields = right.split()
        if not separator or len(fields) < 5 or not right_fields:
            continue
        mount_text = (
            fields[4]
            .replace("\\040", " ")
            .replace("\\011", "\t")
            .replace("\\012", "\n")
            .replace("\\134", "\\")
        )
        mount = Path(mount_text)
        try:
            if os.path.commonpath((candidate, mount)) == str(mount):
                matches.append((mount, right_fields[0]))
        except ValueError:
            continue
    if not matches:
        raise UnsupportedFilesystemError("database path has no matching Linux mount")
    mount, filesystem_type = max(matches, key=lambda item: len(os.fsencode(item[0])))
    if filesystem_type not in _LOCAL:
        if allow_unsupported_read:
            return FilesystemInspection(
                filesystem_type, mount, "db.storage.remote_read_only"
            )
        raise UnsupportedFilesystemError(
            f"managed database storage type is unsupported: {filesystem_type}"
        )
    warning = (
        f"db.storage.{filesystem_type}.durability_limited"
        if filesystem_type in _DURABILITY_WARNINGS
        else None
    )
    return FilesystemInspection(filesystem_type, mount, warning)
