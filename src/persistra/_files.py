"""Private atomic file-publication helpers."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

type FileIdentity = tuple[int, int]


def file_identity(path: Path) -> FileIdentity:
    """Return the device and inode identity of one path without following symlinks."""
    status = path.stat(follow_symlinks=False)
    return status.st_dev, status.st_ino


def unlink_if_identity(path: Path, identity: FileIdentity) -> bool:
    """Unlink a path only while it still names the expected file."""
    try:
        current = file_identity(path)
    except FileNotFoundError:
        return False
    if current != identity:
        return False
    path.unlink()
    return True


def atomic_write_bytes(path: Path, document: bytes, *, overwrite: bool = False) -> None:
    """Publish complete bytes from a private same-directory file."""
    descriptor, staging_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    staging_path = Path(staging_name)
    staging_identity = file_identity(staging_path)
    linked = False
    published = False
    try:
        stream = os.fdopen(descriptor, "wb")
        descriptor = -1
        with stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        if file_identity(staging_path) != staging_identity:
            raise OSError(f"private staging path changed before publication: {staging_path}")
        if overwrite:
            os.replace(staging_path, path)
        else:
            os.link(staging_path, path)
            linked = True
            if file_identity(path) != staging_identity:
                raise OSError(f"published path changed during publication: {path}")
        published = True
    except Exception:
        if linked and not published:
            unlink_if_identity(path, staging_identity)
        raise
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        unlink_if_identity(staging_path, staging_identity)
