from __future__ import annotations

from pathlib import Path

import pytest

from baby_first_steps_medallion.silver.parsers import extract_records

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


@pytest.mark.parametrize(
    ("source_name", "request_kind", "fixture_name", "expected_record_id"),
    [
        ("pubmed", "fetch", "silver-parser-pubmed.xml", "98765432101"),
        ("europe_pmc", "search", "silver-parser-europepmc.json", "SYNTHETIC:silver-europe-0001"),
        ("openalex", "search", "silver-parser-openalex.json", "W999999999999999999"),
    ],
)
def test_source_parsers_extract_synthetic_fixtures_only_in_tests(
    source_name: str, request_kind: str, fixture_name: str, expected_record_id: str
) -> None:
    extracted = extract_records(
        source_name=source_name,  # type: ignore[arg-type]
        request_kind=request_kind,
        payload=(FIXTURES / fixture_name).read_bytes(),
    )

    assert len(extracted) == 1
    candidate = extracted[0].candidate
    assert candidate["source_record_id"] == expected_record_id
    assert candidate["title"].startswith("SYNTHETIC")
    assert len(candidate["abstract"]) >= 80
    assert candidate["language"] == "eng"
    assert candidate["resource_url"].startswith("https://")


def test_pubmed_search_envelope_is_not_misinterpreted_as_a_document() -> None:
    extracted = extract_records(
        source_name="pubmed",
        request_kind="search",
        payload=(FIXTURES / "silver-parser-pubmed.xml").read_bytes(),
    )

    assert extracted == []
