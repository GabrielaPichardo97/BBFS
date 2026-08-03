"""Immutable payload storage and atomically replaceable Bronze metadata."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4


class PayloadCollisionError(RuntimeError):
    """An existing response path contains different bytes and cannot be overwritten."""


class BatchNotFoundError(FileNotFoundError):
    """A requested batch cannot be resumed because its manifest is missing."""


@dataclass(frozen=True)
class PayloadWriteResult:
    """The persisted raw payload identity."""

    path: Path
    sha256: str
    byte_count: int
    reused: bool


def utc_timestamp(value: datetime | None = None) -> str:
    """Return an ISO-8601 UTC timestamp with microsecond precision."""
    current = value or datetime.now(UTC)
    return current.astimezone(UTC).isoformat().replace("+00:00", "Z")


def new_batch_id(
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    token_hex: Callable[[int], str] = secrets.token_hex,
) -> str:
    """Build a sortable timestamp ID with a random suffix for collisions."""
    timestamp = now().astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{token_hex(3)}"


def sha256_bytes(payload: bytes) -> str:
    """Hash precisely the bytes received from the HTTP response."""
    return hashlib.sha256(payload).hexdigest()


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def write_immutable_payload(path: Path, payload: bytes) -> PayloadWriteResult:
    """Atomically create a raw response, or verify an identical prior response."""
    expected_hash = sha256_bytes(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        lock_handle = lock_path.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise PayloadCollisionError(f"payload write already in progress: {path}") from error
    else:
        lock_handle.close()
    try:
        if path.exists():
            existing_hash = sha256_bytes(path.read_bytes())
            if existing_hash != expected_hash:
                raise PayloadCollisionError(
                    f"refusing to overwrite {path}: {existing_hash} differs from {expected_hash}"
                )
            return PayloadWriteResult(path, expected_hash, len(payload), reused=True)
        _atomic_replace(path, payload)
        return PayloadWriteResult(path, expected_hash, len(payload), reused=False)
    finally:
        if lock_path.exists():
            lock_path.unlink()


def write_json_metadata(path: Path, document: Any) -> None:
    """Atomically replace metadata; never use this function for raw response bytes."""
    serialized = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = serialized.encode("utf-8")
    _atomic_replace(path, encoded)


def write_json_lines_metadata(path: Path, rows: list[dict[str, Any]]) -> None:
    """Atomically replace the derived failure log from manifest state."""
    content = b"".join(
        (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows
    )
    _atomic_replace(path, content)


class BronzeBatchStore:
    """File layout for one batch; only payload files are immutable."""

    def __init__(self, bronze_dir: Path, batch_id: str) -> None:
        self.batch_id = batch_id
        self.batch_dir = bronze_dir / batch_id
        self.manifest_path = self.batch_dir / "manifest.json"
        self.checksums_path = self.batch_dir / "checksums.sha256"
        self.failures_path = self.batch_dir / "failures.jsonl"

    @classmethod
    def create(cls, bronze_dir: Path, batch_id: str) -> BronzeBatchStore:
        store = cls(bronze_dir, batch_id)
        store.batch_dir.mkdir(parents=True, exist_ok=False)
        return store

    @classmethod
    def resume(cls, bronze_dir: Path, batch_id: str) -> BronzeBatchStore:
        store = cls(bronze_dir, batch_id)
        if not store.manifest_path.is_file():
            raise BatchNotFoundError(f"No se encontró manifest para reanudar: {batch_id}")
        return store

    def load_manifest(self) -> dict[str, Any]:
        document = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise BatchNotFoundError(f"Manifest inválido: {self.manifest_path}")
        return cast(dict[str, Any], document)

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        write_json_metadata(self.manifest_path, manifest)

    def write_request_metadata(
        self, source_name: str, sequence: int, document: dict[str, Any]
    ) -> Path:
        path = self.batch_dir / source_name / f"request_{sequence:04d}.meta.json"
        serialized = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        write_immutable_payload(path, serialized.encode("utf-8"))
        return path

    def write_response(
        self, source_name: str, sequence: int, extension: str, payload: bytes
    ) -> PayloadWriteResult:
        path = self.batch_dir / source_name / f"response_{sequence:04d}.{extension}"
        return write_immutable_payload(path, payload)

    def write_checksums(self, responses: list[dict[str, Any]]) -> None:
        lines = []
        for response in sorted(responses, key=lambda item: str(item["file"])):
            lines.append(f"{response['sha256']}  {response['file']}\n")
        _atomic_replace(self.checksums_path, "".join(lines).encode("ascii"))

    def write_failures(self, failures: list[dict[str, Any]]) -> None:
        write_json_lines_metadata(self.failures_path, failures)

    def relative_to_batch(self, path: Path) -> str:
        return path.relative_to(self.batch_dir).as_posix()
