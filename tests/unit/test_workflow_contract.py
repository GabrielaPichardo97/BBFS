from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ci_runs_fast_checks_without_live_api_calls() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for required in (
        "pull_request:",
        "branches:",
        "- main",
        "python-version: \"3.11\"",
        "cache: pip",
        "coverage run",
        "docker compose config",
        "docker compose build",
        "pipeline doctor",
        "--network none",
        "tests/integration",
        "check_repository_hygiene.py",
    ):
        assert required in workflow
    assert "demo --fresh" not in workflow
    assert "secrets." not in workflow


def test_live_workflow_is_bounded_sanitized_and_manual_or_weekly() -> None:
    workflow = (ROOT / ".github" / "workflows" / "e2e-live.yml").read_text(
        encoding="utf-8"
    )

    for required in (
        "workflow_dispatch:",
        "schedule:",
        "timeout-minutes: 45",
        "permissions:",
        "contents: read",
        "concurrency:",
        "cancel-in-progress: false",
        "actions/cache@v4",
        "demo --fresh --yes",
        "retention-days: 14",
        "artifacts/evidence.json",
        "artifacts/evidence.csv",
        "docs/evidence.generated.md",
        "artifacts/run.log",
        "data/bronze/*/manifest.json",
        "data/bronze/*/checksums.sha256",
        "GITHUB_STEP_SUMMARY",
    ):
        assert required in workflow
    assert workflow.count("if: always()") == 2
    assert "secrets." not in workflow
    assert "response_" not in workflow
