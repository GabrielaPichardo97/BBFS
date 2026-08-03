"""Tests for demo evidence use only disposable paths and synthetic test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.demo import (
    EvidenceError,
    EvidenceRenderer,
    GeneratedPathCleaner,
    count_synthetic_markers,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf",
    )


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_cleaner_removes_only_documented_generated_paths(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    generated_paths = (
        settings.data_dir / "bronze" / "batch" / "response.json",
        settings.data_dir / "gold" / "resources.faiss",
        settings.data_dir / "baby_first_steps.duckdb",
        settings.artifacts_dir / "evidence.json",
        settings.artifacts_dir / "gold" / "acceptance-search.json",
        settings.root_dir / "docs" / "evidence.generated.md",
    )
    for path in generated_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated", encoding="utf-8")
    retained = (
        settings.data_dir / "retain.txt",
        settings.artifacts_dir / "retain.txt",
        settings.root_dir / "docs" / "retain.md",
    )
    for path in retained:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("user-content", encoding="utf-8")

    removed = GeneratedPathCleaner(settings).clean()

    assert removed
    assert all(not path.exists() for path in generated_paths)
    assert all(path.read_text(encoding="utf-8") == "user-content" for path in retained)


def test_renderer_writes_all_required_evidence_views(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    renderer = EvidenceRenderer(settings)

    renderer.write(_fixture("evidence-valid.json"))

    assert renderer.evidence_path.is_file()
    assert renderer.csv_path.is_file()
    assert renderer.log_path.is_file()
    assert renderer.markdown_path.is_file()
    assert "## Idempotencia" in renderer.markdown_path.read_text(encoding="utf-8")
    assert "section,field,value" in renderer.csv_path.read_text(encoding="utf-8")


def test_renderer_rejects_a_synthetic_marker_before_production_evidence(tmp_path: Path) -> None:
    renderer = EvidenceRenderer(_settings(tmp_path))
    synthetic = _fixture("evidence-with-synthetic.json")

    with pytest.raises(EvidenceError, match="source_type='synthetic'"):
        renderer.write(synthetic)

    assert not renderer.evidence_path.exists()
    assert count_synthetic_markers(synthetic) == 1
