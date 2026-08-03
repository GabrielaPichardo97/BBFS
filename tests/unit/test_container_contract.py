from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_container_uses_a_non_root_user_and_owned_runtime_paths() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "useradd --uid 10001" in dockerfile
    assert "chown -R app:app /app /home/app" in dockerfile
    assert "USER app" in dockerfile
    assert 'ENTRYPOINT ["python", "-m", "baby_first_steps_medallion.cli"]' in dockerfile
    assert 'CMD ["doctor"]' in dockerfile


def test_compose_has_one_pipeline_service_with_data_and_hf_cache() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "  pipeline:" in compose
    assert "image: bbfs-pipeline:local" in compose
    assert "./data:/app/data" in compose
    assert "./docs:/app/docs" in compose
    assert "hf-cache:/home/app/.cache/huggingface" in compose
    assert "HF_HOME: /home/app/.cache/huggingface" in compose


def test_docker_context_excludes_runtime_data_and_caches() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for pattern in ("data", "artifacts", "tmp", ".env", "*.duckdb", "*.faiss"):
        assert pattern in dockerignore
