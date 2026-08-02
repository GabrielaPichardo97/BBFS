from __future__ import annotations

from pathlib import Path

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.paths import build_runtime_paths, ensure_writable


def test_runtime_paths_are_built_under_configured_directories(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf-cache",
    )

    paths = build_runtime_paths(settings)

    assert paths.bronze_dir == tmp_path / "data" / "bronze"
    assert paths.gold_dir == tmp_path / "data" / "gold"
    assert paths.models_dir == tmp_path / "data" / "models"


def test_runtime_paths_are_writable(tmp_path: Path) -> None:
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf-cache",
    )

    ensure_writable(build_runtime_paths(settings))

    assert (tmp_path / "data" / "bronze").is_dir()
    assert (tmp_path / "artifacts").is_dir()
    assert (tmp_path / "hf-cache").is_dir()
