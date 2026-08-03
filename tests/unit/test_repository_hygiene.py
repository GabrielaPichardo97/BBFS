from __future__ import annotations

from pathlib import Path

from scripts.check_repository_hygiene import scan_repository


def test_hygiene_allows_synthetic_fixture_only_under_tests(tmp_path: Path) -> None:
    fixture = tmp_path / "tests" / "fixtures" / "synthetic" / "record.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"source_type":"synthetic"}', encoding="utf-8")

    assert scan_repository(tmp_path, [fixture.relative_to(tmp_path)]) == []


def test_hygiene_rejects_generated_data_secret_and_model(tmp_path: Path) -> None:
    generated = tmp_path / "data" / "bronze" / "batch" / "response.json"
    secret = tmp_path / "credentials-prod.json"
    model = tmp_path / "models" / "weights.safetensors"
    for path in (generated, secret, model):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"source_type":"synthetic"}', encoding="utf-8")

    violations = scan_repository(
        tmp_path,
        [
            generated.relative_to(tmp_path),
            secret.relative_to(tmp_path),
            model.relative_to(tmp_path),
        ],
    )

    assert any("generated runtime file: data/bronze" in item for item in violations)
    assert any("synthetic production record" in item for item in violations)
    assert any("credential-like filename" in item for item in violations)
    assert any("database/model/index file" in item for item in violations)
