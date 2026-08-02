from __future__ import annotations

from pathlib import Path

import pytest

from baby_first_steps_medallion.config import Settings


def test_settings_use_expected_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BFSM_DATA_DIR", raising=False)
    monkeypatch.delenv("BFSM_ARTIFACTS_DIR", raising=False)
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setenv("BFSM_LOG_LEVEL", "debug")

    settings = Settings.from_env()

    assert settings.log_level == "DEBUG"
    assert settings.data_dir == settings.root_dir / "data"
    assert settings.artifacts_dir == settings.root_dir / "artifacts"
    assert settings.required_secret_names == ()


def test_settings_honor_directory_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BFSM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("BFSM_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))

    settings = Settings.from_env()

    assert settings.data_dir == (tmp_path / "data").resolve()
    assert settings.artifacts_dir == (tmp_path / "artifacts").resolve()
    assert settings.hf_home == (tmp_path / "hf").resolve()


def test_invalid_log_level_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BFSM_LOG_LEVEL", "verbose")

    with pytest.raises(ValueError, match="BFSM_LOG_LEVEL"):
        Settings.from_env()
