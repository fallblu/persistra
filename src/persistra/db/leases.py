"""Linux kernel-backed shared and exclusive database leases."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import socket
import stat
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from persistra import __version__
from persistra.db.models import LeaseId
from persistra.domain import Duration
from persistra.errors import (
    DatabaseLeaseConflictError,
    DatabaseRecoveryRequiredError,
    LeaseUpgradeError,
    UnsupportedFilesystemError,
)


class LeaseMode(StrEnum):
    SHARED = "shared"
    EXCLUSIVE = "exclusive"


@dataclass(slots=True)
class _RegistryEntry:
    fd: int
    mode: LeaseMode
    references: int


_REGISTRY: dict[Path, _RegistryEntry] = {}
_REGISTRY_LOCK = threading.RLock()
_ZERO_DURATION = Duration(0)


def _after_fork() -> None:
    with _REGISTRY_LOCK:
        for entry in _REGISTRY.values():
            try:
                os.close(entry.fd)
            except OSError:
                pass
        _REGISTRY.clear()


os.register_at_fork(after_in_child=_after_fork)


class DatabaseLease:
    """Owned lease whose guard descriptor lives until explicit close."""

    __slots__ = ("_closed", "_identity", "_owner_path", "_path")

    def __init__(self, path: Path, owner_path: Path) -> None:
        self._path = path
        self._owner_path = owner_path
        self._closed = False
        self._identity = _path_identity(path)

    @property
    def mode(self) -> LeaseMode:
        """Return the acquired mode without exposing the guard descriptor."""
        with _REGISTRY_LOCK:
            entry = _REGISTRY.get(self._path)
            if entry is None:
                raise RuntimeError("lease is closed")
            return entry.mode

    def validate_path_identity(self) -> None:
        """Reject replacement of an existing database path during the lease."""
        current = _path_identity(self._path)
        if self._identity is not None and current != self._identity:
            raise DatabaseRecoveryRequiredError(
                "database path identity changed while its lease was held"
            )

    def record_database_id(self, database_id: str) -> None:
        """Complete owner evidence after managed bootstrap inspection."""
        self.validate_path_identity()
        if self._identity is None:
            self._identity = _path_identity(self._path)
        try:
            value = json.loads(self._owner_path.read_text(encoding="utf-8"))
            value["database_id"] = database_id
            _write_owner_file(self._owner_path, value)
        except (OSError, ValueError, TypeError) as error:
            raise DatabaseRecoveryRequiredError(
                "lease owner metadata could not record the database identity"
            ) from error

    def close(self) -> None:
        """Release one logical acquisition; safe to call repeatedly."""
        if self._closed:
            return
        self._closed = True
        try:
            self._owner_path.unlink(missing_ok=True)
        finally:
            with _REGISTRY_LOCK:
                entry = _REGISTRY.get(self._path)
                if entry is not None:
                    entry.references -= 1
                    if entry.references == 0:
                        fcntl.flock(entry.fd, fcntl.LOCK_UN)
                        os.close(entry.fd)
                        del _REGISTRY[self._path]

    def __enter__(self) -> DatabaseLease:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def acquire_lease(
    path: Path,
    mode: LeaseMode,
    *,
    timeout: Duration = _ZERO_DURATION,
    operation: str = "project_open",
    project_id: str | None = None,
    project_name: str | None = None,
) -> DatabaseLease:
    """Acquire a same-host lease using one permanent sidecar lock inode."""
    canonical = path.resolve()
    sidecar = canonical.with_name(canonical.name + ".persistra-lock")
    if sidecar.is_symlink():
        raise UnsupportedFilesystemError("database lease sidecar cannot be a symbolic link")
    owners = sidecar / "owners"
    owners.mkdir(parents=True, exist_ok=True)
    guard = sidecar / "guard"
    for managed_path in (sidecar, owners, guard):
        if managed_path.is_symlink() or (
            managed_path.exists() and stat.S_ISLNK(managed_path.lstat().st_mode)
        ):
            raise UnsupportedFilesystemError("database lease paths cannot be symbolic links")
    guard_fd = -1
    with _REGISTRY_LOCK:
        existing = _REGISTRY.get(canonical)
        if existing is not None:
            if existing.mode is not mode:
                raise LeaseUpgradeError("lease mode conversion requires a new project lifecycle")
            if mode is LeaseMode.EXCLUSIVE:
                raise DatabaseLeaseConflictError("exclusive lease is already owned in this process")
            existing.references += 1
            guard_fd = existing.fd
        else:
            guard_fd = os.open(guard, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o640)
            lock = fcntl.LOCK_SH if mode is LeaseMode.SHARED else fcntl.LOCK_EX
            deadline = time.monotonic_ns() + timeout.microseconds * 1_000
            delay = 0.05
            while True:
                try:
                    fcntl.flock(guard_fd, lock | fcntl.LOCK_NB)
                    break
                except BlockingIOError as error:
                    remaining = deadline - time.monotonic_ns()
                    if remaining <= 0:
                        os.close(guard_fd)
                        raise DatabaseLeaseConflictError(
                            "database lease conflicts with another lifecycle"
                        ) from error
                    time.sleep(min(delay, remaining / 1_000_000_000))
                    delay = min(delay * 2, 0.5)
            if mode is LeaseMode.EXCLUSIVE:
                for stale_owner in owners.glob("*.json"):
                    stale_owner.unlink(missing_ok=True)
            _REGISTRY[canonical] = _RegistryEntry(guard_fd, mode, 1)

    lease_id = LeaseId.new()
    owner_path = owners / f"{lease_id}.json"
    temporary = owner_path.with_suffix(".tmp")
    metadata: dict[str, Any] = {
        "acquired_at": datetime.now(UTC).isoformat(),
        "executable": Path(sys.executable).name,
        "hostname": socket.gethostname(),
        "lease_id": str(lease_id),
        "mode": mode.value,
        "operation": operation,
        "path_sha256": hashlib.sha256(os.fsencode(canonical)).hexdigest(),
        "pid": os.getpid(),
        "process_start_token": _process_start_token(os.getpid()),
        "project_id": project_id,
        "project_name": project_name,
        "python_version": sys.version.split()[0],
        "requested_timeout_us": timeout.microseconds,
        "thread_id": threading.get_ident(),
        "version": __version__,
    }
    try:
        _write_owner_file(owner_path, metadata)
    except BaseException:
        temporary.unlink(missing_ok=True)
        with _REGISTRY_LOCK:
            entry = _REGISTRY[canonical]
            entry.references -= 1
            if entry.references == 0:
                fcntl.flock(guard_fd, fcntl.LOCK_UN)
                os.close(guard_fd)
                del _REGISTRY[canonical]
        raise
    return DatabaseLease(canonical, owner_path)


def _path_identity(path: Path) -> tuple[int, int] | None:
    try:
        value = path.stat()
    except FileNotFoundError:
        return None
    return value.st_dev, value.st_ino


def _process_start_token(pid: int) -> str | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        fields = text[text.rfind(")") + 2 :].split()
        return fields[19]
    except (OSError, IndexError):
        return None


def _write_owner_file(owner_path: Path, metadata: dict[str, Any]) -> None:
    temporary = owner_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(metadata, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    os.chmod(temporary, 0o640)
    descriptor = os.open(temporary, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, owner_path)
    directory = os.open(owner_path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
