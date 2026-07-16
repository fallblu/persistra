"""Verified immutable physical database-copy publication."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from typing import TYPE_CHECKING, Any, cast

import duckdb

from persistra import __version__
from persistra.db.connection import ManagedConnection, inspect_database, publish_noreplace
from persistra.db.leases import LeaseMode, acquire_lease
from persistra.db.models import CopyId, CopyResult, CopyVerification, DatabaseRole
from persistra.domain import Clock, ContentId, Duration
from persistra.domain.serialization import canonical_bytes
from persistra.errors import CopyVerificationError, DatabaseAlreadyExistsError

if TYPE_CHECKING:
    from pathlib import Path

_CHUNK_BYTES = 8 * 1024 * 1024


def _copy_paths(path: Path) -> tuple[Path, Path]:
    return (
        path.with_name(path.name + ".persistra-copy.json"),
        path.with_name(path.name + ".persistra-copy.sha256"),
    )


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_BYTES):
            digest.update(chunk)
            size += len(chunk)
    return f"sha256:{digest.hexdigest()}", size


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_backup(
    source: Path,
    destination: Path,
    *,
    expected_role: DatabaseRole,
    logical_name: str,
    clock: Clock,
    project_id: str | None,
    project_name: str | None,
    kind: str = "backup",
    market_snapshot_id: str | None = None,
    market_snapshot_manifest_content_id: str | None = None,
) -> CopyResult:
    """Checkpoint and publish a byte-verified, read-only physical backup."""
    destination = destination.resolve()
    if not destination.parent.is_dir():
        raise FileNotFoundError("copy destination parent must already exist")
    manifest_path, checksum_path = _copy_paths(destination)
    if any(path.exists() for path in (destination, manifest_path, checksum_path)):
        raise DatabaseAlreadyExistsError("copy destination or metadata already exists")
    copy_id = CopyId.new()
    partial = destination.with_name(f"{destination.name}.partial-{copy_id.value}")
    partial_manifest = manifest_path.with_name(f"{manifest_path.name}.partial-{copy_id.value}")
    partial_checksum = checksum_path.with_name(f"{checksum_path.name}.partial-{copy_id.value}")
    lease = acquire_lease(
        destination,
        LeaseMode.EXCLUSIVE,
        timeout=Duration(0),
        operation="database_backup_destination",
        project_id=project_id,
        project_name=project_name,
    )
    try:
        source_connection = ManagedConnection(source, read_only=False)
        try:
            metadata = inspect_database(source_connection, expected_role=expected_role)
            source_connection.execute("CHECKPOINT")
        finally:
            source_connection.close()
        before = source.stat()
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as input_file, partial.open("xb") as output_file:
            while chunk := input_file.read(_CHUNK_BYTES):
                output_file.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            output_file.flush()
            os.fsync(output_file.fileno())
        after = source.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            raise CopyVerificationError("source database changed during copy")
        content_id = f"sha256:{digest.hexdigest()}"
        verified_content_id, verified_size = _hash_file(partial)
        if verified_content_id != content_id or verified_size != size:
            raise CopyVerificationError("independent destination hash does not match")
        verify_connection = ManagedConnection(partial, read_only=True)
        try:
            verified_metadata = inspect_database(
                verify_connection,
                expected_role=expected_role,
                expected_project_id=metadata.owner_project_id,
            )
        finally:
            verify_connection.close()
        if verified_metadata.database_id != metadata.database_id:
            raise CopyVerificationError("copy changed the database identity")
        manifest: dict[str, Any] = {
            "copy_id": str(copy_id),
            "created_at": clock.now(),
            "database_content_id": content_id,
            "database_id": str(metadata.database_id),
            "duckdb_version": duckdb.__version__,
            "kind": kind,
            "logical_name": logical_name,
            "manifest_schema": "persistra.database.copy_manifest@1",
            "market_snapshot_id": market_snapshot_id,
            "market_snapshot_manifest_content_id": market_snapshot_manifest_content_id,
            "owner_project_id": (
                None if metadata.owner_project_id is None else str(metadata.owner_project_id)
            ),
            "persistra_version": __version__,
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "required_extensions": [],
            "role": metadata.role.value,
            "schema_version": metadata.schema_version,
            "size_bytes": size,
            "source_path_sha256": hashlib.sha256(os.fsencode(source.resolve())).hexdigest(),
            "supported_reader": ">=3,<4",
            "verification": {
                "bootstrap": True,
                "independent_hash": True,
                "migration_checksums": True,
                "source_metadata_stable": True,
            },
        }
        manifest_bytes = canonical_bytes(manifest)
        manifest_content_id = str(ContentId.from_bytes(manifest_bytes))
        partial_manifest.write_bytes(manifest_bytes)
        _fsync_file(partial_manifest)
        partial_checksum.write_text(manifest_content_id + "\n", encoding="ascii")
        _fsync_file(partial_checksum)
        publish_noreplace(partial, destination)
        publish_noreplace(partial_manifest, manifest_path)
        publish_noreplace(partial_checksum, checksum_path)
        _fsync_directory(destination.parent)
        destination.chmod(0o444)
        verification = verify_published_copy(destination, expected_role=expected_role)
        return CopyResult(
            verification.copy_id,
            verification.database_id,
            verification.role,
            destination,
            manifest_path,
            checksum_path,
            verification.database_content_id,
            verification.manifest_content_id,
            verification.size_bytes,
        )
    except BaseException:
        for path in (partial, partial_manifest, partial_checksum):
            path.unlink(missing_ok=True)
        raise
    finally:
        lease.close()


def verify_published_copy(
    path: Path, *, expected_role: DatabaseRole | None = None
) -> CopyVerification:
    """Rehash and validate a committed copy and its manifest marker."""
    path = path.resolve()
    manifest_path, checksum_path = _copy_paths(path)
    try:
        manifest_bytes = manifest_path.read_bytes()
        checksum_text = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise CopyVerificationError("copy metadata is missing or unreadable") from error
    manifest_content_id = str(ContentId.from_bytes(manifest_bytes))
    if checksum_text != manifest_content_id + "\n":
        raise CopyVerificationError("copy manifest checksum marker does not match")
    try:
        decoded = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CopyVerificationError("copy manifest is not valid JSON") from error
    if not isinstance(decoded, dict) or canonical_bytes(decoded) != manifest_bytes:
        raise CopyVerificationError("copy manifest is not canonical JSON")
    manifest = cast("dict[str, Any]", decoded)
    if manifest.get("manifest_schema") != "persistra.database.copy_manifest@1":
        raise CopyVerificationError("copy manifest schema is unsupported")
    content_id, size = _hash_file(path)
    if manifest.get("database_content_id") != content_id or manifest.get("size_bytes") != size:
        raise CopyVerificationError("copy bytes do not match the manifest")
    connection = ManagedConnection(path, read_only=True)
    try:
        metadata = inspect_database(connection, expected_role=expected_role)
    finally:
        connection.close()
    if manifest.get("database_id") != str(metadata.database_id):
        raise CopyVerificationError("copy database identity does not match the manifest")
    if manifest.get("role") != metadata.role.value:
        raise CopyVerificationError("copy database role does not match the manifest")
    try:
        copy_id = CopyId.parse(manifest["copy_id"])
    except (KeyError, TypeError, ValueError) as error:
        raise CopyVerificationError("copy identifier is invalid") from error
    return CopyVerification(
        copy_id,
        metadata.database_id,
        metadata.role,
        path,
        content_id,
        manifest_content_id,
        size,
    )
