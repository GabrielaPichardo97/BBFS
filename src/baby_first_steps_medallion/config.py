"""Configuration for the local scaffold; no credentials are required."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VALID_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


def project_root() -> Path:
    """Return the repository root from the installed source layout."""
    return Path(__file__).resolve().parents[2]


def _path_from_env(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


@dataclass(frozen=True)
class Settings:
    """Paths and non-secret process settings."""

    root_dir: Path
    data_dir: Path
    artifacts_dir: Path
    log_level: str
    hf_home: Path
    required_secret_names: tuple[str, ...] = ()

    @classmethod
    def from_env(cls) -> Settings:
        root = project_root()
        log_level = os.environ.get("BFSM_LOG_LEVEL", "INFO").upper()
        if log_level not in VALID_LOG_LEVELS:
            raise ValueError(f"BFSM_LOG_LEVEL must be one of {sorted(VALID_LOG_LEVELS)}")
        data_dir = _path_from_env("BFSM_DATA_DIR", root / "data")
        artifacts_dir = _path_from_env("BFSM_ARTIFACTS_DIR", root / "artifacts")
        hf_home = _path_from_env("HF_HOME", data_dir / "cache" / "huggingface")
        return cls(
            root_dir=root,
            data_dir=data_dir,
            artifacts_dir=artifacts_dir,
            log_level=log_level,
            hf_home=hf_home,
        )
