from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from baby_first_steps_medallion.silver.models import ResourceRecord
from baby_first_steps_medallion.silver.normalization import canonical_id_for, content_hash_for

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic" / "silver-invalid-records.json"


def _fixture_document() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _candidate(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    document = _fixture_document()
    candidate = copy.deepcopy(document["base"])
    candidate["publication_date"] = date.fromisoformat(candidate["publication_date"])
    candidate["parsed_at"] = datetime(2020, 1, 2, tzinfo=UTC)
    if overrides:
        candidate.update(overrides)
        if isinstance(candidate.get("publication_date"), str):
            candidate["publication_date"] = date.fromisoformat(candidate["publication_date"])
    return candidate


def test_resource_record_normalizes_unicode_spaces_and_identifier_wrappers() -> None:
    record = ResourceRecord.model_validate(
        _candidate(
            {
                "doi": " DOI: 10.9999/SYNTHETIC-RECORD-0001 ",
                "title": " SYNTHETIC\u00a0VALIDATION   RECORD ",
                "authors": [" Synthetic   Author ", "Synthetic Author"],
            }
        )
    )

    assert record.doi == "10.9999/synthetic-record-0001"
    assert record.title == "SYNTHETIC VALIDATION RECORD"
    assert record.authors == ["Synthetic Author"]


@pytest.mark.parametrize(
    ("case_name", "expected_code"),
    [
        ("missing_source_identifier", "source_record_id_empty"),
        ("empty_title", "title_empty"),
        ("missing_abstract", "abstract_missing"),
        ("short_abstract", "abstract_too_short"),
        ("invalid_doi", "doi_invalid"),
        ("invalid_url", "resource_url_invalid"),
        ("future_date", "publication_date_future"),
        ("invalid_authors", "authors_invalid"),
        ("unexpected_field", "extra_forbidden"),
    ],
)
def test_resource_record_rejects_synthetic_invalid_cases(
    case_name: str, expected_code: str
) -> None:
    cases = {item["case"]: item["overrides"] for item in _fixture_document()["cases"]}

    with pytest.raises(ValidationError) as captured:
        ResourceRecord.model_validate(_candidate(cases[case_name]))

    error_messages = {item["msg"].removeprefix("Value error, ") for item in captured.value.errors()}
    error_types = {item["type"] for item in captured.value.errors()}
    assert expected_code in error_messages or expected_code in error_types


def test_resource_record_reports_multiple_errors_for_one_synthetic_record() -> None:
    cases = {item["case"]: item["overrides"] for item in _fixture_document()["cases"]}

    with pytest.raises(ValidationError) as captured:
        ResourceRecord.model_validate(_candidate(cases["multiple_errors"]))

    assert len(captured.value.errors()) >= 4


def test_canonical_identifier_uses_documented_precedence() -> None:
    assert canonical_id_for(
        source_name="pubmed",
        source_record_id="98765432101",
        doi="10.9999/synthetic-record-0001",
        pmid="98765432101",
        openalex_id=None,
    ) == "doi:10.9999/synthetic-record-0001"
    assert canonical_id_for(
        source_name="pubmed",
        source_record_id="98765432101",
        doi=None,
        pmid="98765432101",
        openalex_id=None,
    ) == "pmid:98765432101"
    assert canonical_id_for(
        source_name="openalex",
        source_record_id="W999999999999999999",
        doi=None,
        pmid=None,
        openalex_id="https://openalex.org/W999999999999999999",
    ) == "openalex:W999999999999999999"


def test_content_hash_excludes_batch_paths_and_timestamps() -> None:
    first = ResourceRecord.model_validate(_candidate())
    second = ResourceRecord.model_validate(
        _candidate(
            {
                "source_batch_id": "another-synthetic-batch",
                "source_file": "another/source/file.json",
                "parsed_at": datetime(2021, 1, 2, tzinfo=UTC),
            }
        )
    )

    assert content_hash_for(first.model_dump()) == content_hash_for(second.model_dump())
