from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_outputs_and_credentials_are_ignored() -> None:
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for pattern in (
        "data/bronze/**",
        "data/*.duckdb",
        "data/gold/**",
        "artifacts/*",
        "data/models/**",
        "*.faiss",
        ".env",
        "credentials*.json",
        ".cache/",
        "notebooks/**/*.executed.ipynb",
    ):
        assert pattern in ignored


def test_runtime_directory_markers_are_versionable() -> None:
    assert (ROOT / "data" / ".gitkeep").is_file()
    assert (ROOT / "artifacts" / ".gitkeep").is_file()
