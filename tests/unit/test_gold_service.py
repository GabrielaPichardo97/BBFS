"""Gold tests use deterministic vectors and disposable test databases only."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pytest

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.gold.service import (
    ACCEPTANCE_QUERIES,
    GoldError,
    GoldRepository,
)
from baby_first_steps_medallion.silver.models import ResourceRecord, SourceName
from baby_first_steps_medallion.silver.normalization import canonical_id_for, content_hash_for
from baby_first_steps_medallion.silver.persistence import SilverRepository
from baby_first_steps_medallion.silver.service import SilverValidationResult, SourceMetrics

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"
FIXED_TIME = datetime(2020, 1, 2, tzinfo=UTC)


@dataclass
class DeterministicEmbedder:
    """A test-only deterministic embedder; it never contacts Hugging Face."""

    model_name: str = "test/multilingual-e5"
    model_revision: str = "test-revision"
    calls: list[tuple[str, ...]] = field(default_factory=list)

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray[Any, Any]:
        self.calls.append(tuple(texts))
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "texturas" in lowered or "sensorial" in lowered:
                vectors.append([3.0, 0.0, 0.0])
            elif "motricidad" in lowered:
                vectors.append([0.0, 3.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 3.0])
        return np.asarray(vectors, dtype=np.float32)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=ROOT,
        data_dir=tmp_path / "runtime-data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf",
    )


def _record(
    *,
    source_record_id: str,
    title: str,
    abstract: str,
    doi: str,
    source_name: SourceName = "pubmed",
    batch_id: str = "gold-test-batch",
) -> ResourceRecord:
    fixture = json.loads((FIXTURES / "silver-invalid-records.json").read_text(encoding="utf-8"))
    candidate: dict[str, Any] = copy.deepcopy(fixture["base"])
    candidate.update(
        {
            "canonical_id": canonical_id_for(
                source_name=source_name,
                source_record_id=source_record_id,
                doi=doi,
                pmid=None,
                openalex_id=None,
            ),
            "source_name": source_name,
            "source_record_id": source_record_id,
            "observed_sources": [source_name],
            "doi": doi,
            "pmid": None,
            "openalex_id": None,
            "title": title,
            "abstract": abstract,
            "publication_date": date(2020, 1, 2),
            "query_profiles": ["motor_sensory"],
            "source_batch_id": batch_id,
            "source_file": "synthetic/test-only-gold-record.json",
            "source_ordinal": int(source_record_id.rsplit("-", maxsplit=1)[-1]),
            "raw_payload_sha256": hashlib.sha256(source_record_id.encode()).hexdigest(),
            "parsed_at": FIXED_TIME,
        }
    )
    validated = ResourceRecord.model_validate(candidate)
    return validated.model_copy(update={"content_hash": content_hash_for(validated.model_dump())})


def _validation(records: tuple[ResourceRecord, ...], *, batch_id: str) -> SilverValidationResult:
    metrics: dict[SourceName, SourceMetrics] = {
        "pubmed": SourceMetrics(),
        "europe_pmc": SourceMetrics(),
        "openalex": SourceMetrics(),
    }
    for record in records:
        metrics[record.source_name].rows_extracted += 1
        metrics[record.source_name].rows_valid += 1
    return SilverValidationResult(
        batch_id=batch_id,
        records=records,
        quarantines=(),
        metrics_by_source=metrics,
    )


def _seed_silver(settings: Settings) -> tuple[ResourceRecord, ResourceRecord]:
    sensory = _record(
        source_record_id="gold-record-1",
        doi="10.9999/gold-sensory",
        title="Juego sensorial con texturas",
        abstract=(
            "Actividad de juego sensorial con diferentes texturas para bebés y cuidadores "
            "durante el desarrollo temprano."
        ),
    )
    motor = _record(
        source_record_id="gold-record-2",
        doi="10.9999/gold-motor",
        title="Materiales cotidianos y motricidad fina",
        abstract=(
            "Materiales cotidianos para actividades de motricidad fina con bebés y niños "
            "pequeños en el hogar."
        ),
    )
    SilverRepository(settings, now=lambda: FIXED_TIME).persist(
        _validation((sensory, motor), batch_id="gold-test-batch")
    )
    return sensory, motor


def _database_rows(
    settings: Settings, query: str, params: list[Any] | None = None
) -> list[tuple[Any, ...]]:
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"), read_only=True)
    try:
        return connection.execute(query, params or []).fetchall()
    finally:
        connection.close()


def test_gold_build_search_order_top_k_and_metadata(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_silver(settings)
    embedder = DeterministicEmbedder()
    repository = GoldRepository(settings, embedder=embedder, now=lambda: FIXED_TIME)

    build = repository.build(batch_size=2)
    results = repository.semantic_search("actividades con texturas", top_k=1)

    assert (build.embeddings_inserted, build.embeddings_updated, build.embeddings_noop) == (2, 0, 0)
    assert build.embedding_dimension == 3
    assert results[0].rank == 1
    assert results[0].title == "Juego sensorial con texturas"
    assert results[0].score >= 0.99
    assert results[0].language == "eng"
    assert results[0].observed_sources == ("pubmed",)
    passages = [text for call in embedder.calls for text in call if text.startswith("passage:")]
    assert passages and all(text.startswith("passage: ") for text in passages)
    assert _database_rows(settings, "SELECT COUNT(*) FROM gold_embeddings") == [(2,)]
    assert repository.index_path.is_file()


def test_noop_keeps_vector_ids_and_index_bytes_unchanged(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_silver(settings)
    repository = GoldRepository(settings, embedder=DeterministicEmbedder(), now=lambda: FIXED_TIME)
    repository.build()
    before_ids = _database_rows(
        settings, "SELECT canonical_id, vector_id FROM gold_embeddings ORDER BY canonical_id"
    )
    before_index = repository.index_path.read_bytes()

    noop = repository.build()

    assert (noop.embeddings_inserted, noop.embeddings_updated, noop.embeddings_noop) == (0, 0, 2)
    assert (
        _database_rows(
            settings, "SELECT canonical_id, vector_id FROM gold_embeddings ORDER BY canonical_id"
        )
        == before_ids
    )
    assert repository.index_path.read_bytes() == before_index


def test_modified_silver_content_reuses_stable_vector_id_and_updates_embedding(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    sensory, _ = _seed_silver(settings)
    repository = GoldRepository(settings, embedder=DeterministicEmbedder(), now=lambda: FIXED_TIME)
    repository.build()
    before_id = _database_rows(
        settings,
        "SELECT vector_id FROM gold_embeddings WHERE canonical_id = ?",
        [sensory.canonical_id],
    )
    assert before_id

    changed = _record(
        source_record_id="gold-record-1",
        doi="10.9999/gold-sensory",
        title="Juego sensorial con texturas actualizado",
        abstract=(
            "Actividad actualizada de juego sensorial con diferentes texturas para bebés y "
            "cuidadores durante el desarrollo temprano."
        ),
        batch_id="gold-test-batch-2",
    )
    SilverRepository(settings, now=lambda: FIXED_TIME).persist(
        _validation((changed,), batch_id="gold-test-batch-2")
    )

    updated = repository.build()
    after_id = _database_rows(
        settings,
        "SELECT vector_id FROM gold_embeddings WHERE canonical_id = ?",
        [changed.canonical_id],
    )

    assert changed.canonical_id == sensory.canonical_id
    assert updated.embeddings_updated == 1
    assert before_id == after_id


def test_persisted_index_can_be_searched_by_a_new_repository_instance(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_silver(settings)
    GoldRepository(settings, embedder=DeterministicEmbedder(), now=lambda: FIXED_TIME).build()

    results = GoldRepository(settings, embedder=DeterministicEmbedder()).semantic_search(
        "materiales para motricidad", top_k=5
    )

    assert len(results) == 2
    assert [item.score for item in results] == sorted(
        [item.score for item in results], reverse=True
    )
    assert results[0].title == "Materiales cotidianos y motricidad fina"


def test_empty_query_is_rejected(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_silver(settings)
    repository = GoldRepository(settings, embedder=DeterministicEmbedder())
    repository.build()

    with pytest.raises(GoldError, match="vacía"):
        repository.semantic_search("   ")


def test_atomic_index_write_preserves_previous_file_on_writer_failure(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def failing_writer(_: Any, destination: str) -> None:
        Path(destination).write_bytes(b"partial-test-index")
        raise OSError("test-only writer failure")

    repository = GoldRepository(
        settings, embedder=DeterministicEmbedder(), index_writer=failing_writer
    )
    repository.index_path.parent.mkdir(parents=True)
    repository.index_path.write_bytes(b"previous-index")

    with pytest.raises(GoldError, match="atómica"):
        repository._write_index_atomic(object())

    assert repository.index_path.read_bytes() == b"previous-index"
    assert list(repository.index_path.parent.glob("*.tmp")) == []


def test_gold_rejects_synthetic_rows_and_metadata_matches_index(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_silver(settings)
    repository = GoldRepository(settings, embedder=DeterministicEmbedder(), now=lambda: FIXED_TIME)
    build = repository.build()
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"))
    try:
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                """
                INSERT INTO gold_embeddings (
                    canonical_id, vector_id, model_name, model_revision, embedding_dimension,
                    content_hash, vector_blob, embedded_at, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'synthetic')
                """,
                [
                    "source:synthetic:blocked",
                    922337203685477000,
                    "test/multilingual-e5",
                    "test-revision",
                    3,
                    "synthetic",
                    b"\x00" * 12,
                    FIXED_TIME,
                ],
            )
    finally:
        connection.close()

    state = _database_rows(settings, "SELECT vector_count, index_sha256 FROM gold_index_state")
    assert state == [(2, build.index_sha256)]
    assert _database_rows(
        settings, "SELECT COUNT(*) FROM gold_embeddings WHERE source_type = 'synthetic'"
    ) == [(0,)]

    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"))
    try:
        connection.execute("UPDATE gold_index_state SET vector_count = 1")
    finally:
        connection.close()
    with pytest.raises(GoldError, match="metadata Gold no son consistentes"):
        repository.semantic_search("texturas")


def test_acceptance_evidence_has_all_spanish_queries_and_manual_review(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    _seed_silver(settings)
    repository = GoldRepository(settings, embedder=DeterministicEmbedder(), now=lambda: FIXED_TIME)
    repository.build()

    path = repository.write_acceptance_evidence()
    evidence = json.loads(path.read_text(encoding="utf-8"))

    assert [item["query"] for item in evidence["queries"]] == list(ACCEPTANCE_QUERIES)
    assert all(
        item["manual_coherence_review"]["status"] == "pending_human_review"
        for item in evidence["queries"]
    )
