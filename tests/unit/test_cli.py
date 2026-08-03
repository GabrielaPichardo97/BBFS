from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from baby_first_steps_medallion.cli import app


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


def test_doctor_succeeds_without_optional_libraries(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFSM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))

    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "[OK] python" in result.output
    assert "[OK] secretos_obligatorios: ninguno requerido" in result.output
    assert "[OK] duckdb" in result.output
    assert "[OK] faiss" in result.output


def test_container_self_test_exercises_offline_production_code(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFSM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))

    result = runner.invoke(app, ["test"])

    assert result.exit_code == 0, result.output
    assert "[PASS] immutable_byte_storage" in result.output
    assert "[PASS] silver_schema_and_guards" in result.output
    assert "[PASS] required_secrets" in result.output


def test_demo_requires_fresh_and_evidence_requires_a_prior_run(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFSM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    demo = runner.invoke(app, ["demo"])
    evidence = runner.invoke(app, ["evidence"])

    assert demo.exit_code == 2
    assert "requiere --fresh" in demo.output
    assert evidence.exit_code == 1
    assert "No existe evidencia JSON válida" in evidence.output


def test_ingest_rejects_an_unknown_source_without_contacting_a_source(runner: CliRunner) -> None:
    result = runner.invoke(app, ["ingest", "--sources", "unknown"])

    assert result.exit_code == 2
    assert "Fuentes no reconocidas: unknown" in result.output


def test_silver_validate_rejects_a_missing_local_batch_without_network(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))

    result = runner.invoke(app, ["silver-validate", "--batch-id", "missing-batch"])

    assert result.exit_code == 2
    assert "No se encontr" in result.output


def test_silver_persistence_commands_operate_on_an_empty_local_database(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFSM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    audit = runner.invoke(app, ["audit-duplicates"])
    runs = runner.invoke(app, ["show-runs"])

    assert audit.exit_code == 0, audit.output
    assert '"resource_duplicates": 0' in audit.output
    assert '"synthetic_rows": 0' in audit.output
    assert runs.exit_code == 0, runs.output
    assert runs.output.strip() == "[]"


def test_silver_rejects_a_missing_bronze_batch_without_network(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))

    result = runner.invoke(app, ["silver", "--batch-id", "missing-batch"])

    assert result.exit_code == 1
    assert "No se encontr" in result.output


def test_gold_and_search_fail_clearly_without_a_ready_local_index(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFSM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))

    gold = runner.invoke(app, ["gold"])
    search = runner.invoke(app, ["search", "lectura compartida para bebés"])

    assert gold.exit_code == 1
    assert "No hay recursos Silver" in gold.output
    assert search.exit_code == 1
    assert "No existe un índice Gold" in search.output
