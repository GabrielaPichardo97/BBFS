"""Runtime paths and conservative writability checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from baby_first_steps_medallion.config import Settings


@dataclass(frozen=True)
class RuntimePaths:
    data_dir: Path
    artifacts_dir: Path
    bronze_dir: Path
    gold_dir: Path
    models_dir: Path
    hf_cache_dir: Path


def build_runtime_paths(settings: Settings) -> RuntimePaths:
    """Build paths without interpreting or transforming any data."""
    return RuntimePaths(
        data_dir=settings.data_dir,
        artifacts_dir=settings.artifacts_dir,
        bronze_dir=settings.data_dir / "bronze",
        gold_dir=settings.data_dir / "gold",
        models_dir=settings.data_dir / "models",
        hf_cache_dir=settings.hf_home,
    )


def ensure_writable(paths: RuntimePaths) -> None:
    """Create runtime directories and prove that each can be written."""
    for directory in (
        paths.data_dir,
        paths.artifacts_dir,
        paths.bronze_dir,
        paths.gold_dir,
        paths.models_dir,
        paths.hf_cache_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / f".bbfs-write-probe-{uuid4().hex}"
        probe.write_bytes(b"")
        probe.unlink()
