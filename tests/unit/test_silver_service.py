from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.safety import SyntheticProductionDataError
from baby_first_steps_medallion.silver.models import QuarantineRecord
from baby_first_steps_medallion.silver.parsers import ExtractedRecord
from baby_first_steps_medallion.silver.service import SilverValidator, SourceMetrics

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "runtime-data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf",
    )


def _invalid_candidate() -> dict[str, Any]:
    document = json.loads((FIXTURES / "silver-invalid-records.json").read_text(encoding="utf-8"))
    candidate = copy.deepcopy(document["base"])
    candidate.update(
        next(item["overrides"] for item in document["cases"] if item["case"] == "multiple_errors")
    )
    return candidate


def test_multiple_validation_errors_create_one_deterministic_quarantine_event(
    tmp_path: Path,
) -> None:
    now = datetime(2020, 1, 2, tzinfo=UTC)
    validator = SilverValidator(_settings(tmp_path), now=lambda: now)
    extracted = ExtractedRecord(
        raw_record={"fixture": "SYNTHETIC — NEVER INGEST"},
        candidate=_invalid_candidate(),
        source_ordinal=1,
    )

    first = validator._validate_extracted_record(
        source_name="pubmed",
        extracted=extracted,
        source_batch_id="test-batch",
        source_file="pubmed/response_0001.xml",
        raw_payload_sha256="a" * 64,
        query_profile="motor_sensory",
    )
    second = validator._validate_extracted_record(
        source_name="pubmed",
        extracted=extracted,
        source_batch_id="test-batch",
        source_file="pubmed/response_0001.xml",
        raw_payload_sha256="a" * 64,
        query_profile="motor_sensory",
    )

    assert isinstance(first, QuarantineRecord)
    assert isinstance(second, QuarantineRecord)
    assert first.quarantine_id == second.quarantine_id
    assert first.rejection_code == "multiple_validation_errors"
    assert len(first.errors) >= 4
    metrics = SourceMetrics()
    SilverValidator._record_rejection(metrics, first)
    assert metrics.rows_invalid == 1
    assert metrics.invalid_by_reason["title_empty"] == 1
    assert metrics.invalid_by_reason["abstract_too_short"] == 1


def test_synthetic_manifest_is_rejected_before_a_payload_can_be_read(tmp_path: Path) -> None:
    fixture = json.loads((FIXTURES / "never-ingest.json").read_text(encoding="utf-8"))
    batch_dir = tmp_path / "runtime-data" / "bronze" / "synthetic-attempt"
    batch_dir.mkdir(parents=True)
    (batch_dir / "manifest.json").write_text(
        json.dumps(
            {
                "sources": ["pubmed"],
                "responses": [
                    {
                        "source_name": "pubmed",
                        "source_type": fixture["source_type"],
                        "file": "payload-must-never-be-read.xml",
                        "sha256": "a" * 64,
                        "request_kind": "fetch",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SyntheticProductionDataError, match="forbidden"):
        SilverValidator(_settings(tmp_path)).validate_batch("synthetic-attempt")
