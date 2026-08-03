"""Isolated persistence tests; fixture records never target a production data directory."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import duckdb
import pytest

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.silver.models import (
    QuarantineRecord,
    ResourceRecord,
    SourceName,
    ValidationIssue,
)
from baby_first_steps_medallion.silver.normalization import canonical_id_for, content_hash_for
from baby_first_steps_medallion.silver.persistence import (
    SilverPersistenceError,
    SilverRepository,
)
from baby_first_steps_medallion.silver.service import SilverValidationResult, SourceMetrics

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"
FIXED_TIME = datetime(2020, 1, 2, tzinfo=UTC)


def _settings(tmp_path: Path) -> Settings:
    """Use the versioned schema but a disposable test-only DuckDB file."""
    return Settings(
        root_dir=ROOT,
        data_dir=tmp_path / "runtime-data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf",
    )


def _fixture_base() -> dict[str, Any]:
    document = json.loads((FIXTURES / "silver-invalid-records.json").read_text(encoding="utf-8"))
    candidate = copy.deepcopy(document["base"])
    candidate["publication_date"] = date(2020, 1, 2)
    candidate["parsed_at"] = FIXED_TIME
    return candidate


def _record(
    *,
    source_name: SourceName = "pubmed",
    source_record_id: str = "98765432101",
    doi: str | None = "10.9999/synthetic-record-0001",
    pmid: str | None = "98765432101",
    openalex_id: str | None = None,
    title: str = "SYNTHETIC VALIDATION RECORD — NEVER INGEST",
    abstract: str | None = None,
    batch_id: str = "test-batch-001",
    source_ordinal: int = 1,
    query_profile: str = "motor_sensory",
) -> ResourceRecord:
    """Build a valid record from a fixture for a test database only."""
    candidate = _fixture_base()
    record_abstract = abstract or str(candidate["abstract"])
    candidate.update(
        {
            "canonical_id": canonical_id_for(
                source_name=source_name,
                source_record_id=source_record_id,
                doi=doi,
                pmid=pmid,
                openalex_id=openalex_id,
            ),
            "source_name": source_name,
            "source_record_id": source_record_id,
            "observed_sources": [source_name],
            "doi": doi,
            "pmid": pmid,
            "openalex_id": openalex_id,
            "title": title,
            "abstract": record_abstract,
            "query_profiles": [query_profile],
            "source_batch_id": batch_id,
            "source_file": "synthetic/test-only-record.json",
            "source_ordinal": source_ordinal,
            "raw_payload_sha256": hashlib.sha256(
                f"{source_name}|{source_record_id}|{source_ordinal}".encode()
            ).hexdigest(),
        }
    )
    validated = ResourceRecord.model_validate(candidate)
    return validated.model_copy(update={"content_hash": content_hash_for(validated.model_dump())})


def _quarantine(*, batch_id: str = "test-batch-001") -> QuarantineRecord:
    raw_record = json.loads((FIXTURES / "never-ingest.json").read_text(encoding="utf-8"))
    raw_hash = hashlib.sha256(
        json.dumps(raw_record, sort_keys=True).encode("utf-8")
    ).hexdigest()
    issue = ValidationIssue(
        field_path="title",
        rejection_code="title_empty",
        error_type="value_error",
        rejection_reason="Test-only controlled rejection.",
    )
    return QuarantineRecord(
        quarantine_id=hashlib.sha256(f"test-quarantine|{raw_hash}".encode()).hexdigest(),
        canonical_id_candidate="source:pubmed:test-only-invalid",
        source_name="pubmed",
        source_record_id="test-only-invalid",
        rejection_code=issue.rejection_code,
        error_type=issue.error_type,
        field_path=issue.field_path,
        rejection_reason=issue.rejection_reason,
        raw_record=raw_record,
        raw_record_sha256=raw_hash,
        source_batch_id=batch_id,
        source_file="synthetic/never-ingest.json",
        source_ordinal=1,
        rejected_at=FIXED_TIME,
        errors=[issue],
    )


def _validation(
    records: tuple[ResourceRecord, ...],
    *,
    batch_id: str = "test-batch-001",
    quarantines: tuple[QuarantineRecord, ...] = (),
) -> SilverValidationResult:
    metrics: dict[SourceName, SourceMetrics] = {
        "pubmed": SourceMetrics(),
        "europe_pmc": SourceMetrics(),
        "openalex": SourceMetrics(),
    }
    for record in records:
        source_metrics = metrics[record.source_name]
        source_metrics.rows_extracted += 1
        source_metrics.rows_valid += 1
    for quarantine in quarantines:
        source_metrics = metrics[quarantine.source_name]
        source_metrics.rows_extracted += 1
        source_metrics.rows_invalid += 1
        source_metrics.invalid_by_reason[quarantine.rejection_code] = 1
    return SilverValidationResult(
        batch_id=batch_id,
        records=records,
        quarantines=quarantines,
        metrics_by_source=metrics,
    )


def _rows(settings: Settings, query: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"), read_only=True)
    try:
        return connection.execute(query, params or []).fetchall()
    finally:
        connection.close()


def test_first_load_and_three_exact_reprocesses_are_idempotent(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = SilverRepository(settings, now=lambda: FIXED_TIME)
    validation = _validation((_record(),))

    first = repository.persist(validation)
    repeats = [repository.persist(validation) for _ in range(3)]

    assert (first.rows_inserted, first.rows_updated, first.rows_noop) == (1, 0, 0)
    assert [(item.rows_inserted, item.rows_updated, item.rows_noop) for item in repeats] == [
        (0, 0, 1),
        (0, 0, 1),
        (0, 0, 1),
    ]
    assert _rows(settings, "SELECT COUNT(*) FROM silver_resources") == [(1,)]
    assert _rows(settings, "SELECT COUNT(*) FROM silver_resource_sources") == [(1,)]
    assert _rows(settings, "SELECT COUNT(*) FROM meta_schema_version") == [(1,)]
    assert _rows(settings, "SELECT status, COUNT(*) FROM pipeline_runs GROUP BY status") == [
        ("completed", 4)
    ]
    assert repository.audit_duplicates().as_dict() == {
        "resource_duplicates": 0,
        "quarantine_duplicates": 0,
        "synthetic_rows": 0,
    }


def test_changed_content_updates_but_exact_noop_preserves_updated_at(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    current_time = [FIXED_TIME]
    repository = SilverRepository(settings, now=lambda: current_time[0])
    original = _record()
    repository.persist(_validation((original,)))
    first_updated_at = _rows(settings, "SELECT updated_at FROM silver_resources")[0][0]

    current_time[0] += timedelta(days=1)
    noop = repository.persist(_validation((original,), batch_id="test-batch-002"))
    noop_updated_at = _rows(settings, "SELECT updated_at FROM silver_resources")[0][0]

    current_time[0] += timedelta(days=1)
    changed = _record(
        batch_id="test-batch-003",
        title="SYNTHETIC VALIDATION RECORD WITH A CONTROLLED CONTENT CHANGE",
    )
    updated = repository.persist(_validation((changed,), batch_id="test-batch-003"))
    changed_updated_at = _rows(settings, "SELECT updated_at FROM silver_resources")[0][0]

    assert (noop.rows_inserted, noop.rows_updated, noop.rows_noop) == (0, 0, 1)
    assert noop_updated_at == first_updated_at
    assert (updated.rows_inserted, updated.rows_updated, updated.rows_noop) == (0, 1, 0)
    assert changed_updated_at > noop_updated_at


def test_duplicate_source_and_cross_source_doi_keep_one_entity_and_all_provenance(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    repository = SilverRepository(settings)
    doi = "10.9999/shared-doi-0001"
    same_source_first = _record(source_record_id="source-duplicate-a", doi=doi, pmid=None)
    same_source_second = _record(
        source_record_id="source-duplicate-b",
        doi=doi,
        pmid=None,
        source_ordinal=2,
        abstract="SYNTHETIC TEST ABSTRACT — NEVER INGEST. " + "More detail. " * 12,
    )
    other_source = _record(
        source_name="europe_pmc",
        source_record_id="europe-duplicate-a",
        doi=doi,
        pmid=None,
        source_ordinal=3,
        abstract=same_source_second.abstract,
    )

    result = repository.persist(_validation((same_source_first, same_source_second, other_source)))
    resource = _rows(
        settings,
        """
        SELECT canonical_id, primary_source_name, primary_source_record_id,
               observed_sources_json, source_count
        FROM silver_resources
        """,
    )

    assert (result.rows_inserted, result.rows_updated, result.rows_noop) == (1, 0, 0)
    assert resource[0][0:3] == (f"doi:{doi}", "pubmed", "source-duplicate-b")
    assert json.loads(cast(str, resource[0][3])) == ["europe_pmc", "pubmed"]
    assert resource[0][4] == 2
    assert _rows(settings, "SELECT COUNT(*) FROM silver_resource_sources") == [(3,)]


def test_later_source_observation_is_accumulated_without_changing_content(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = SilverRepository(settings)
    doi = "10.9999/cross-batch-observation"
    first = _record(source_record_id="pubmed-first", doi=doi, pmid=None)
    later = _record(
        source_name="europe_pmc",
        source_record_id="europe-later",
        doi=doi,
        pmid=None,
        batch_id="test-batch-002",
    )

    repository.persist(_validation((first,)))
    result = repository.persist(_validation((later,), batch_id="test-batch-002"))
    observed_sources, source_count = _rows(
        settings,
        """
        SELECT observed_sources_json, source_count
        FROM silver_resources
        WHERE canonical_id = ?
        """,
        [f"doi:{doi}"],
    )[0]

    assert (result.rows_inserted, result.rows_updated, result.rows_noop) == (0, 0, 1)
    assert json.loads(cast(str, observed_sources)) == ["europe_pmc", "pubmed"]
    assert source_count == 2
    assert _rows(settings, "SELECT COUNT(*) FROM silver_resource_sources") == [(2,)]


def test_same_pmid_across_sources_and_deterministic_priority(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = SilverRepository(settings)
    pmid = "98765432109"
    by_pmid = (
        _record(source_record_id="pmid-pubmed", doi=None, pmid=pmid),
        _record(
            source_name="europe_pmc",
            source_record_id="pmid-europe",
            doi=None,
            pmid=pmid,
            source_ordinal=2,
        ),
    )
    longer_openalex = _record(
        source_name="openalex",
        source_record_id="openalex-longer",
        doi="10.9999/priority-longer",
        pmid=None,
        openalex_id="W1234567890",
        source_ordinal=3,
        abstract="SYNTHETIC TEST ABSTRACT — NEVER INGEST. " + "More detail. " * 15,
    )
    shorter_pubmed = _record(
        source_record_id="pubmed-shorter",
        doi="10.9999/priority-longer",
        pmid=None,
        source_ordinal=4,
    )
    equal_pubmed = _record(
        source_record_id="pubmed-equal",
        doi="10.9999/priority-equal",
        pmid=None,
        source_ordinal=5,
    )
    equal_openalex = _record(
        source_name="openalex",
        source_record_id="openalex-equal",
        doi="10.9999/priority-equal",
        pmid=None,
        openalex_id="W1234567891",
        source_ordinal=6,
    )

    repository.persist(
        _validation((*by_pmid, longer_openalex, shorter_pubmed, equal_pubmed, equal_openalex))
    )
    primary_by_id = dict(
        _rows(
            settings,
            "SELECT canonical_id, primary_source_name FROM silver_resources ORDER BY canonical_id",
        )
    )

    assert primary_by_id[f"pmid:{pmid}"] == "pubmed"
    assert primary_by_id["doi:10.9999/priority-longer"] == "openalex"
    assert primary_by_id["doi:10.9999/priority-equal"] == "pubmed"


def test_quarantine_is_idempotent_and_dq_metrics_match_persistence_result(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = SilverRepository(settings)
    quarantine = _quarantine()
    validation = _validation((), quarantines=(quarantine,))

    first = repository.persist(validation)
    second = repository.persist(validation)
    metrics = dict(
        _rows(
            settings,
            """
            SELECT metric_name, metric_value
            FROM dq_metrics
            WHERE run_id = ? AND source_name = '__all__'
            """,
            [first.run_id],
        )
    )

    assert (first.quarantine_inserted, first.quarantine_noop) == (1, 0)
    assert (second.quarantine_inserted, second.quarantine_noop) == (0, 1)
    assert _rows(settings, "SELECT COUNT(*) FROM silver_rejects") == [(1,)]
    assert metrics["quarantine_inserted"] == first.quarantine_inserted
    assert metrics["rows_inserted"] == first.rows_inserted
    assert metrics["rows_invalid"] == 1


def test_rollback_marks_run_failed_without_partial_silver_rows(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def fail_after_staging() -> None:
        raise RuntimeError("test-only transactional failure")

    repository = SilverRepository(settings, failure_injector=fail_after_staging)
    with pytest.raises(SilverPersistenceError, match="transacci"):
        repository.persist(_validation((_record(),)))

    assert _rows(settings, "SELECT COUNT(*) FROM silver_resources") == [(0,)]
    assert _rows(settings, "SELECT COUNT(*) FROM silver_resource_sources") == [(0,)]
    assert _rows(settings, "SELECT COUNT(*) FROM bronze_batches") == [(0,)]
    assert _rows(settings, "SELECT status, COUNT(*) FROM pipeline_runs GROUP BY status") == [
        ("failed", 1)
    ]


def test_schema_and_audit_reject_synthetic_source_type_in_test_database(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    repository = SilverRepository(settings)
    record = _record()
    repository.persist(_validation((record,)))
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"))
    try:
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                """
                INSERT INTO stg_resources (
                    run_id, stage_ordinal, canonical_id, source_name, source_record_id, doi, pmid,
                    openalex_id, title, abstract, language, publication_date, authors_json,
                    journal_or_publisher, keywords_json, subject_terms_json, resource_url,
                    query_profiles_json, observed_sources_json, source_count, source_batch_id,
                    source_file, source_ordinal, raw_payload_sha256, content_hash, parsed_at,
                    source_type
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    "test-run",
                    999,
                    record.canonical_id,
                    record.source_name,
                    record.source_record_id,
                    record.doi,
                    record.pmid,
                    record.openalex_id,
                    record.title,
                    record.abstract,
                    record.language,
                    record.publication_date,
                    "[]",
                    record.journal_or_publisher,
                    "[]",
                    "[]",
                    record.resource_url,
                    "[\"motor_sensory\"]",
                    "[\"pubmed\"]",
                    1,
                    record.source_batch_id,
                    record.source_file,
                    999,
                    record.raw_payload_sha256,
                    record.content_hash,
                    record.parsed_at,
                    "synthetic",
                ],
            )
    finally:
        connection.close()

    assert repository.audit_duplicates().synthetic_rows == 0
    assert _rows(
        settings,
        """
        SELECT COUNT(*)
        FROM (
            SELECT source_type FROM stg_resources
            UNION ALL SELECT source_type FROM silver_resources
            UNION ALL SELECT source_type FROM silver_resource_sources
            UNION ALL SELECT source_type FROM silver_rejects
        )
        WHERE source_type = 'synthetic'
        """,
    ) == [(0,)]
