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
    assert "[SKIP] duckdb" in result.output
    assert "[SKIP] faiss" in result.output


@pytest.mark.parametrize("command", ["silver", "gold", "search", "evidence", "demo"])
def test_placeholder_commands_fail_without_simulating_success(
    runner: CliRunner, command: str
) -> None:
    result = runner.invoke(app, [command])

    assert result.exit_code == 2
    assert f"{command}: no implementado" in result.output
    assert "no se realizó ninguna acción" in result.output


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
