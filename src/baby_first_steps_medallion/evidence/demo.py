"""Reproducible real-data demonstration and rubric evidence generation."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from baby_first_steps_medallion.bronze.service import BronzeIngestor, build_default_adapters
from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.safety import assert_real_source_type
from baby_first_steps_medallion.gold.models import GoldBuildResult, SearchResult
from baby_first_steps_medallion.gold.service import ACCEPTANCE_QUERIES, GoldRepository
from baby_first_steps_medallion.paths import build_runtime_paths, ensure_writable
from baby_first_steps_medallion.silver.persistence import (
    DuplicateAudit,
    SilverPersistenceResult,
    SilverRepository,
)
from baby_first_steps_medallion.silver.service import SilverValidationResult, SilverValidator

DEMO_SOURCES = ("pubmed", "europe_pmc", "openalex")
DEMO_PROFILE = "motor_sensory"
DEFAULT_MAX_RECORDS_PER_SOURCE = 5
GENERATED_PROJECT_PATHS = (
    Path("data/bronze"),
    Path("data/gold"),
    Path("data/models"),
    Path("data/cache"),
    Path("data/baby_first_steps.duckdb"),
    Path("data/baby_first_steps.duckdb.wal"),
    Path("data/baby_first_steps.duckdb.tmp"),
    Path("artifacts/evidence.json"),
    Path("artifacts/evidence.csv"),
    Path("artifacts/run.log"),
    Path("artifacts/gold"),
    Path("docs/evidence.generated.md"),
)
DUPLICATE_QUERIES = (
    (
        "silver_canonical_id",
        """
        SELECT canonical_id, COUNT(*) AS duplicate_count
        FROM silver_resources
        GROUP BY canonical_id
        HAVING COUNT(*) > 1
        """,
    ),
    (
        "silver_quarantine_id",
        """
        SELECT quarantine_id, COUNT(*) AS duplicate_count
        FROM silver_rejects
        GROUP BY quarantine_id
        HAVING COUNT(*) > 1
        """,
    ),
    (
        "gold_vector_id",
        """
        SELECT vector_id, COUNT(*) AS duplicate_count
        FROM gold_embeddings
        GROUP BY vector_id
        HAVING COUNT(*) > 1
        """,
    ),
)


class DemoError(RuntimeError):
    """The reproducible demonstration did not meet an explicit acceptance criterion."""


class EvidenceError(RuntimeError):
    """Persisted evidence is missing, malformed, or unsafe to publish."""


@dataclass(frozen=True)
class DemoResult:
    """Paths and IDs emitted by one complete real-data demonstration."""

    first_batch_id: str
    second_batch_id: str
    evidence_path: Path
    csv_path: Path
    log_path: Path
    markdown_path: Path

    def as_dict(self) -> dict[str, str]:
        return {
            "first_batch_id": self.first_batch_id,
            "second_batch_id": self.second_batch_id,
            "evidence_path": str(self.evidence_path),
            "csv_path": str(self.csv_path),
            "log_path": str(self.log_path),
            "markdown_path": str(self.markdown_path),
        }


class GeneratedPathCleaner:
    """Remove only the explicitly documented generated paths inside this project."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def clean(self) -> list[Path]:
        """Delete known generated outputs, never a broad directory or arbitrary user file."""
        removed: list[Path] = []
        root = self._settings.root_dir.resolve()
        for relative_path in GENERATED_PROJECT_PATHS:
            target = (root / relative_path).resolve()
            # The static list above is intentionally resolved before deletion.
            if not target.is_relative_to(root):  # pragma: no cover
                raise DemoError(f"Ruta de limpieza fuera del proyecto: {relative_path}")
            if target.is_dir():
                shutil.rmtree(target)
                removed.append(target)
            elif target.is_file() or target.is_symlink():
                target.unlink()
                removed.append(target)
        return removed


class EvidenceRenderer:
    """Render JSON-derived CSV, log, and Markdown evidence without contacting sources."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def evidence_path(self) -> Path:
        return self._settings.artifacts_dir / "evidence.json"

    @property
    def csv_path(self) -> Path:
        return self._settings.artifacts_dir / "evidence.csv"

    @property
    def log_path(self) -> Path:
        return self._settings.artifacts_dir / "run.log"

    @property
    def markdown_path(self) -> Path:
        return self._settings.root_dir / "docs" / "evidence.generated.md"

    def write(self, document: dict[str, Any]) -> None:
        """Persist the primary JSON and its human-readable derived views atomically."""
        synthetic_count = count_synthetic_markers(document)
        if synthetic_count:
            raise EvidenceError("La evidencia contiene source_type='synthetic'.")
        safety = document.get("synthetic_safety")
        if not isinstance(safety, dict) or any(int(value) != 0 for value in safety.values()):
            raise EvidenceError("La evidencia no demuestra ausencia total de datos sintéticos.")
        _write_json_atomic(self.evidence_path, document)
        self.render_existing()

    def render_existing(self) -> None:
        """Regenerate CSV, run log, and Markdown strictly from the saved JSON evidence."""
        document = self.load()
        synthetic_count = count_synthetic_markers(document)
        if synthetic_count:
            raise EvidenceError("La evidencia almacenada contiene source_type='synthetic'.")
        safety = document.get("synthetic_safety")
        if not isinstance(safety, dict) or any(int(value) != 0 for value in safety.values()):
            raise EvidenceError("La evidencia almacenada no pasa la salvaguarda sintética.")
        _write_csv_atomic(self.csv_path, _csv_rows(document))
        _write_text_atomic(self.log_path, _render_log(document))
        _write_text_atomic(self.markdown_path, _render_markdown(document))

    def load(self) -> dict[str, Any]:
        """Load the generated JSON evidence without transforming source payloads."""
        try:
            decoded = json.loads(self.evidence_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise EvidenceError(
                "No existe evidencia JSON válida; ejecute `baby-first-steps demo --fresh --yes`."
            ) from error
        if not isinstance(decoded, dict):
            raise EvidenceError("La evidencia JSON debe ser un objeto.")
        return decoded


class DemoService:
    """Execute the full real-data two-batch demonstration without a notebook."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._renderer = EvidenceRenderer(settings)

    def run(self, *, fresh: bool, max_records_per_source: int) -> DemoResult:
        """Run the required acquisition, idempotency, search, safety, and evidence checks."""
        if not fresh:
            raise DemoError("La demostración reproducible requiere --fresh.")
        if max_records_per_source < 1:
            raise DemoError("max_records_per_source debe ser mayor que cero.")
        environment = verify_environment(self._settings)
        failures = [item for item in environment if item["status"] != "PASS"]
        if failures:
            details = ", ".join(str(item["name"]) for item in failures)
            raise DemoError(f"El entorno no cumple la demostración: {details}")

        removed_paths = GeneratedPathCleaner(self._settings).clean()
        cleaned_text = ", ".join(str(path) for path in removed_paths) or "nothing_to_remove"
        log_events = [
            "environment: PASS",
            f"fresh_cleanup: {cleaned_text}",
        ]
        first_manifest, second_manifest = self._ingest_two_real_batches(
            log_events, max_records_per_source
        )
        first_batch_id = _required_text(first_manifest, "batch_id")
        second_batch_id = _required_text(second_manifest, "batch_id")
        if first_batch_id == second_batch_id:
            raise DemoError("Los dos batch_id Bronze deben ser diferentes.")
        bronze_rows = bronze_evidence_rows((first_manifest, second_manifest))
        _require_bronze_coverage(bronze_rows)
        payload_integrity = payload_integrity_rows(
            self._settings, (first_manifest, second_manifest)
        )
        _require_payload_integrity(payload_integrity)
        log_events.append(f"bronze_batch_1: {first_batch_id}")
        log_events.append(f"bronze_batch_2: {second_batch_id}")

        validator = SilverValidator(self._settings)
        repository = SilverRepository(self._settings)
        validation_1 = validator.validate_batch(first_batch_id)
        persistence_1 = repository.persist(validation_1)
        gold_repository = GoldRepository(self._settings)
        gold_1 = gold_repository.build()
        log_events.append(
            f"run_1: silver={persistence_1.run_id}, gold_vectors={gold_1.vector_count}"
        )

        validation_2 = validator.validate_batch(first_batch_id)
        persistence_2 = repository.persist(validation_2)
        gold_2 = gold_repository.build()
        log_events.append(
            f"run_2: silver={persistence_2.run_id}, gold_vectors={gold_2.vector_count}"
        )

        contract_rows = contract_evidence_rows(validation_1)
        _require_contract_coverage(contract_rows)
        language_rows = language_evidence_rows(self._settings)
        _require_bilingual_corpus(language_rows)
        idempotency_rows = idempotency_evidence_rows(
            persistence_1, persistence_2, gold_1, gold_2
        )
        _require_idempotency(idempotency_rows)
        duplicates = duplicate_evidence_rows(self._settings)
        _require_duplicate_clean(duplicates)
        search_rows = semantic_search_rows(gold_repository)
        _require_searches(search_rows)
        synthetic_safety = synthetic_safety_snapshot(
            self._settings,
            manifests=(first_manifest, second_manifest),
            evidence_without_safety={
                "bronze": bronze_rows,
                "payload_integrity": payload_integrity,
                "contract": contract_rows,
                "languages": language_rows,
                "idempotency": idempotency_rows,
                "duplicates": duplicates,
                "semantic_search": search_rows,
            },
        )
        _require_synthetic_safety(synthetic_safety)
        log_events.extend(
            [
                "duplicates: PASS",
                "semantic_search: PASS",
                "synthetic_safety: PASS",
            ]
        )

        document = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "selected_batch_id": first_batch_id,
            "second_bronze_batch_id": second_batch_id,
            "environment": environment,
            "bronze": bronze_rows,
            "payload_integrity": payload_integrity,
            "contract": contract_rows,
            "languages": language_rows,
            "runs": {
                "run_1": _run_document(first_batch_id, persistence_1, gold_1),
                "run_2": _run_document(first_batch_id, persistence_2, gold_2),
            },
            "idempotency": idempotency_rows,
            "duplicates": duplicates,
            "semantic_search": search_rows,
            "synthetic_safety": synthetic_safety,
            "criteria": criteria_rows(
                environment,
                bronze_rows,
                payload_integrity,
                contract_rows,
                language_rows,
                idempotency_rows,
                duplicates,
                search_rows,
                synthetic_safety,
            ),
            "execution_log": log_events,
        }
        self._renderer.write(document)
        return DemoResult(
            first_batch_id=first_batch_id,
            second_batch_id=second_batch_id,
            evidence_path=self._renderer.evidence_path,
            csv_path=self._renderer.csv_path,
            log_path=self._renderer.log_path,
            markdown_path=self._renderer.markdown_path,
        )

    def render_existing_evidence(self) -> tuple[Path, Path, Path]:
        """Render all evidence views from a prior successful demonstration."""
        self._renderer.render_existing()
        return self._renderer.csv_path, self._renderer.log_path, self._renderer.markdown_path

    def _ingest_two_real_batches(
        self, log_events: list[str], max_records_per_source: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        adapters, client = build_default_adapters()
        try:
            ingestor = BronzeIngestor(self._settings, adapters)
            first = ingestor.ingest(
                sources=",".join(DEMO_SOURCES),
                profiles=DEMO_PROFILE,
                max_records_per_source=max_records_per_source,
            )
            log_events.append("bronze_ingest_1: completed")
            second = ingestor.ingest(
                sources=",".join(DEMO_SOURCES),
                profiles=DEMO_PROFILE,
                max_records_per_source=max_records_per_source,
            )
            log_events.append("bronze_ingest_2: completed")
            return first, second
        finally:
            client.close()


def verify_environment(settings: Settings) -> list[dict[str, str]]:
    """Verify only local runtime prerequisites; never contacts a public source."""
    checks: list[dict[str, str]] = []
    checks.append(
        {
            "name": "python",
            "status": "PASS" if sys.version_info >= (3, 11) else "FAIL",
            "detail": (
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            ),
        }
    )
    try:
        ensure_writable(build_runtime_paths(settings))
    except OSError as error:
        checks.append({"name": "runtime_paths", "status": "FAIL", "detail": str(error)})
    else:
        checks.append({"name": "runtime_paths", "status": "PASS", "detail": str(settings.data_dir)})
    checks.append(
        {
            "name": "required_secrets",
            "status": "PASS" if not settings.required_secret_names else "FAIL",
            "detail": "none"
            if not settings.required_secret_names
            else ", ".join(settings.required_secret_names),
        }
    )
    for module_name in ("duckdb", "faiss", "sentence_transformers"):
        available = importlib.util.find_spec(module_name) is not None
        checks.append(
            {
                "name": module_name,
                "status": "PASS" if available else "FAIL",
                "detail": "available" if available else "missing",
            }
        )
    return checks


def bronze_evidence_rows(manifests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate immutable response manifests by required batch and source fields."""
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        batch_id = _required_text(manifest, "batch_id")
        responses = manifest.get("responses")
        failures = manifest.get("failures")
        if not isinstance(responses, list) or not isinstance(failures, list):
            raise DemoError(f"Manifest Bronze inválido: {batch_id}")
        for source_name in DEMO_SOURCES:
            source_responses = [
                row
                for row in responses
                if isinstance(row, dict) and row.get("source_name") == source_name
            ]
            source_failures = [
                row
                for row in failures
                if isinstance(row, dict) and row.get("source_name") == source_name
            ]
            for row in [*source_responses, *source_failures]:
                assert_real_source_type(str(row.get("source_type", "")), context="demo-bronze")
            files = [
                str(row["file"])
                for row in source_responses
                if isinstance(row.get("file"), str)
            ]
            fetched_at = [
                str(row["fetched_at"])
                for row in source_responses
                if isinstance(row.get("fetched_at"), str)
            ]
            sha256_count = sum(
                1
                for row in source_responses
                if isinstance(row.get("sha256"), str) and len(str(row["sha256"])) == 64
            )
            status = "PASS" if source_responses and not source_failures else "FAIL"
            rows.append(
                {
                    "batch_id": batch_id,
                    "source": source_name,
                    "fetched_at": fetched_at,
                    "files": files,
                    "bytes": sum(int(row.get("byte_count", 0)) for row in source_responses),
                    "sha256_count": sha256_count,
                    "status": status,
                }
            )
    return rows


def payload_integrity_rows(
    settings: Settings, manifests: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Re-read every persisted Bronze response and verify its original byte hash."""
    rows: list[dict[str, Any]] = []
    for manifest in manifests:
        batch_id = _required_text(manifest, "batch_id")
        responses = manifest.get("responses")
        if not isinstance(responses, list):
            raise DemoError(f"Manifest Bronze invÃ¡lido: {batch_id}")
        for response in responses:
            if not isinstance(response, Mapping):
                raise DemoError(f"Respuesta Bronze invÃ¡lida: {batch_id}")
            relative_path = _required_text(response, "file")
            payload_path = settings.data_dir / "bronze" / batch_id / relative_path
            try:
                payload = payload_path.read_bytes()
            except OSError as error:
                raise DemoError(f"No se pudo releer Bronze: {payload_path}") from error
            expected_hash = _required_text(response, "sha256")
            expected_bytes = int(response.get("byte_count", -1))
            actual_hash = hashlib.sha256(payload).hexdigest()
            passed = actual_hash == expected_hash and len(payload) == expected_bytes
            rows.append(
                {
                    "batch_id": batch_id,
                    "source": str(response.get("source_name", "")),
                    "file": relative_path,
                    "expected_bytes": expected_bytes,
                    "actual_bytes": len(payload),
                    "sha256_matches": actual_hash == expected_hash,
                    "status": _status(passed),
                }
            )
    return rows


def contract_evidence_rows(validation: SilverValidationResult) -> list[dict[str, Any]]:
    """Expose Silver extraction and real validation reasons by source."""
    rows: list[dict[str, Any]] = []
    for source_name, metrics in sorted(validation.metrics_by_source.items()):
        reasons = [
            {"reason": reason, "count": count}
            for reason, count in sorted(
                metrics.invalid_by_reason.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        rows.append(
            {
                "source": source_name,
                "rows_extracted": metrics.rows_extracted,
                "rows_valid": metrics.rows_valid,
                "rows_invalid": metrics.rows_invalid,
                "principales_motivos_reales": reasons,
            }
        )
    return rows


def language_evidence_rows(settings: Settings) -> list[dict[str, Any]]:
    """Calculate observed bilingual Silver coverage from persisted real records."""
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"), read_only=True)
    try:
        observed = connection.execute(
            "SELECT LOWER(language), COUNT(*) FROM silver_resources GROUP BY LOWER(language)"
        ).fetchall()
    finally:
        connection.close()
    groups = {"spanish": 0, "english": 0, "other_or_unknown": 0}
    for language, count in observed:
        normalized = str(language).strip().lower()
        if normalized in {"es", "spa", "spanish", "espaÃ±ol"}:
            groups["spanish"] += int(count)
        elif normalized in {"en", "eng", "english"}:
            groups["english"] += int(count)
        else:
            groups["other_or_unknown"] += int(count)
    return [
        {"language_group": name, "rows": count}
        for name, count in groups.items()
    ]


def idempotency_evidence_rows(
    first: SilverPersistenceResult,
    second: SilverPersistenceResult,
    first_gold: GoldBuildResult,
    second_gold: GoldBuildResult,
) -> list[dict[str, Any]]:
    """Build and evaluate required first-run versus exact-reprocess metrics."""
    expected_noops = first.rows_inserted + first.rows_updated + first.rows_noop
    expected_quarantine_noops = first.quarantine_inserted + first.quarantine_noop
    rows = [
        ("rows_inserted", first.rows_inserted, second.rows_inserted, 0),
        ("rows_updated", first.rows_updated, second.rows_updated, 0),
        ("rows_noop", first.rows_noop, second.rows_noop, expected_noops),
        ("quarantine_inserted", first.quarantine_inserted, second.quarantine_inserted, 0),
        (
            "quarantine_noop",
            first.quarantine_noop,
            second.quarantine_noop,
            expected_quarantine_noops,
        ),
        (
            "embeddings_inserted",
            first_gold.embeddings_inserted,
            second_gold.embeddings_inserted,
            0,
        ),
        (
            "embeddings_updated",
            first_gold.embeddings_updated,
            second_gold.embeddings_updated,
            0,
        ),
        (
            "embeddings_noop",
            first_gold.embeddings_noop,
            second_gold.embeddings_noop,
            first_gold.vector_count,
        ),
    ]
    return [
        {
            "metric": metric,
            "run_1": run_1,
            "run_2": run_2,
            "expected": expected,
            "status": "PASS" if run_2 == expected else "FAIL",
        }
        for metric, run_1, run_2, expected in rows
    ]


def duplicate_evidence_rows(settings: Settings) -> list[dict[str, Any]]:
    """Execute and capture each exact duplicate-detection SQL statement."""
    repository = SilverRepository(settings)
    audit: DuplicateAudit = repository.audit_duplicates()
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"), read_only=True)
    try:
        rows: list[dict[str, Any]] = []
        for name, sql in DUPLICATE_QUERIES:
            returned_rows = connection.execute(sql).fetchall()
            rows.append(
                {
                    "name": name,
                    "sql": _clean_sql(sql),
                    "returned_rows": len(returned_rows),
                    "status": "PASS" if not returned_rows else "FAIL",
                }
            )
        rows.append(
            {
                "name": "synthetic_rows_audit",
                "sql": "SilverRepository.audit_duplicates().synthetic_rows",
                "returned_rows": audit.synthetic_rows,
                "status": "PASS" if audit.synthetic_rows == 0 else "FAIL",
            }
        )
        return rows
    finally:
        connection.close()


def semantic_search_rows(repository: GoldRepository) -> list[dict[str, Any]]:
    """Run all required Spanish queries and preserve their result metadata for review."""
    rows: list[dict[str, Any]] = []
    for query in ACCEPTANCE_QUERIES:
        results = repository.semantic_search(query, top_k=5)
        rows.append(
            {
                "query": query,
                "status": "PASS" if results else "FAIL",
                "results": [_search_row(item) for item in results],
            }
        )
    return rows


def synthetic_safety_snapshot(
    settings: Settings,
    *,
    manifests: Sequence[Mapping[str, Any]],
    evidence_without_safety: Mapping[str, Any],
) -> dict[str, int]:
    """Calculate every required synthetic-data count from persisted state and evidence content."""
    bronze = 0
    for manifest in manifests:
        for key in ("responses", "failures"):
            records = manifest.get(key, [])
            if not isinstance(records, list):
                raise DemoError("Manifest Bronze inválido al auditar datos sintéticos.")
            bronze += sum(
                1
                for record in records
                if isinstance(record, dict)
                and str(record.get("source_type", "")).strip().lower() == "synthetic"
            )
    connection = duckdb.connect(str(settings.data_dir / "baby_first_steps.duckdb"), read_only=True)
    try:
        silver = 0
        for table_name in (
            "stg_resources",
            "silver_resources",
            "silver_resource_sources",
            "silver_rejects",
        ):
            silver += _query_count(
                connection,
                f"SELECT COUNT(*) FROM {table_name} WHERE source_type = 'synthetic'",
            )
        gold = _query_count(
            connection,
            "SELECT COUNT(*) FROM gold_embeddings WHERE source_type = 'synthetic'",
        )
    finally:
        connection.close()
    return {
        "synthetic_records_in_bronze": bronze,
        "synthetic_records_in_silver": silver,
        "synthetic_records_in_gold": gold,
        "synthetic_records_in_evidence": count_synthetic_markers(evidence_without_safety),
    }


def count_synthetic_markers(value: Any) -> int:
    """Count actual source-type markers recursively instead of hardcoding an evidence value."""
    if isinstance(value, Mapping):
        own = int(str(value.get("source_type", "")).strip().lower() == "synthetic")
        return own + sum(count_synthetic_markers(item) for item in value.values())
    if isinstance(value, list | tuple):
        return sum(count_synthetic_markers(item) for item in value)
    return 0


def _query_count(connection: duckdb.DuckDBPyConnection, sql: str) -> int:
    row = connection.execute(sql).fetchone()
    if row is None:
        raise DemoError("La consulta de seguridad no devolvió un conteo.")
    return int(row[0])


def criteria_rows(
    environment: Sequence[Mapping[str, str]],
    bronze: Sequence[Mapping[str, Any]],
    payload_integrity: Sequence[Mapping[str, Any]],
    contract: Sequence[Mapping[str, Any]],
    languages: Sequence[Mapping[str, Any]],
    idempotency: Sequence[Mapping[str, Any]],
    duplicates: Sequence[Mapping[str, Any]],
    searches: Sequence[Mapping[str, Any]],
    synthetic_safety: Mapping[str, int],
) -> list[dict[str, str]]:
    """Produce a reviewable PASS/FAIL matrix from calculated checks."""
    environment_passed = all(item["status"] == "PASS" for item in environment)
    idempotency_passed = all(item["status"] == "PASS" for item in idempotency)
    duplicates_passed = all(item["status"] == "PASS" for item in duplicates)
    searches_passed = len(searches) == len(ACCEPTANCE_QUERIES) and all(
        item["status"] == "PASS" for item in searches
    )
    language_counts = {
        str(item.get("language_group")): int(item.get("rows", 0)) for item in languages
    }
    return [
        {
            "criterion": "environment",
            "status": _status(environment_passed),
        },
        {
            "criterion": "two_real_bronze_batches",
            "status": _status(
                len({str(item["batch_id"]) for item in bronze}) == 2
                and all(item["status"] == "PASS" for item in bronze)
            ),
        },
        {
            "criterion": "payload_integrity",
            "status": _status(
                bool(payload_integrity)
                and all(item.get("status") == "PASS" for item in payload_integrity)
            ),
        },
        {
            "criterion": "three_sources_with_records",
            "status": _status(
                {str(item.get("source")) for item in contract} == set(DEMO_SOURCES)
                and all(int(item.get("rows_extracted", 0)) > 0 for item in contract)
            ),
        },
        {
            "criterion": "real_quarantine_with_reason",
            "status": _status(
                any(
                    int(item.get("rows_invalid", 0)) > 0
                    and bool(item.get("principales_motivos_reales"))
                    for item in contract
                )
            ),
        },
        {
            "criterion": "bilingual_corpus",
            "status": _status(
                language_counts.get("spanish", 0) > 0
                and language_counts.get("english", 0) > 0
            ),
        },
        {
            "criterion": "idempotency",
            "status": _status(idempotency_passed),
        },
        {
            "criterion": "duplicates",
            "status": _status(duplicates_passed),
        },
        {
            "criterion": "six_spanish_searches",
            "status": _status(searches_passed),
        },
        {
            "criterion": "synthetic_safety",
            "status": _status(all(value == 0 for value in synthetic_safety.values())),
        },
    ]


def _require_bronze_coverage(rows: Sequence[Mapping[str, Any]]) -> None:
    expected_rows = len(DEMO_SOURCES) * 2
    if len(rows) != expected_rows or any(row.get("status") != "PASS" for row in rows):
        raise DemoError(
            "La demostración requiere respuestas reales exitosas de las tres fuentes "
            "en dos batches."
        )


def _require_payload_integrity(rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows or any(row.get("status") != "PASS" for row in rows):
        raise DemoError("Uno o mÃ¡s payloads Bronze no conservan bytes y SHA-256 originales.")


def _require_contract_coverage(rows: Sequence[Mapping[str, Any]]) -> None:
    sources = {str(row.get("source")) for row in rows}
    if sources != set(DEMO_SOURCES) or any(
        int(row.get("rows_extracted", 0)) <= 0 for row in rows
    ):
        raise DemoError("Las tres fuentes deben aportar registros extraÃ­dos reales.")
    if not any(
        int(row.get("rows_invalid", 0)) > 0 and row.get("principales_motivos_reales")
        for row in rows
    ):
        raise DemoError("La demostraciÃ³n requiere cuarentena real con un motivo calculado.")


def _require_bilingual_corpus(rows: Sequence[Mapping[str, Any]]) -> None:
    counts = {str(row.get("language_group")): int(row.get("rows", 0)) for row in rows}
    if counts.get("spanish", 0) <= 0 or counts.get("english", 0) <= 0:
        raise DemoError("Silver debe contener registros reales tanto en espaÃ±ol como en inglÃ©s.")


def _require_idempotency(rows: Sequence[Mapping[str, Any]]) -> None:
    if any(row.get("status") != "PASS" for row in rows):
        raise DemoError("La segunda corrida no fue idempotente.")


def _require_duplicate_clean(rows: Sequence[Mapping[str, Any]]) -> None:
    if any(row.get("status") != "PASS" for row in rows):
        raise DemoError("Las consultas de duplicados devolvieron filas.")


def _require_searches(rows: Sequence[Mapping[str, Any]]) -> None:
    if len(rows) != len(ACCEPTANCE_QUERIES) or any(row.get("status") != "PASS" for row in rows):
        raise DemoError("Una consulta semántica de aceptación no devolvió resultados.")


def _require_synthetic_safety(safety: Mapping[str, int]) -> None:
    if any(value != 0 for value in safety.values()):
        raise DemoError("La salvaguarda detectó datos sintéticos fuera de pruebas.")


def _run_document(
    batch_id: str, persistence: SilverPersistenceResult, gold: GoldBuildResult
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "silver": persistence.as_dict(),
        "gold": gold.as_dict(),
    }


def _search_row(result: SearchResult) -> dict[str, Any]:
    return {
        "rank": result.rank,
        "canonical_id": result.canonical_id,
        "title": result.title,
        "language": result.language,
        "source": ",".join(result.observed_sources),
        "observed_sources": list(result.observed_sources),
        "score": result.score,
    }


def _required_text(document: Mapping[str, Any], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise DemoError(f"El documento de demostración no contiene {field}.")
    return value


def _status(value: bool) -> str:
    return "PASS" if value else "FAIL"


def _clean_sql(sql: str) -> str:
    return "\n".join(line.strip() for line in sql.strip().splitlines())


def _write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    _write_text_atomic(
        path, json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _write_csv_atomic(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    fieldnames = ["section", "field", "value"]
    try:
        with temporary_path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _csv_rows(document: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in (
        "bronze",
        "payload_integrity",
        "contract",
        "languages",
        "idempotency",
        "duplicates",
        "synthetic_safety",
    ):
        value = document.get(section, [] if section != "synthetic_safety" else {})
        if isinstance(value, Mapping):
            for key, item in value.items():
                rows.append({"section": section, "field": str(key), "value": _json_cell(item)})
        elif isinstance(value, list):
            for index, item in enumerate(value, start=1):
                rows.append({"section": section, "field": str(index), "value": _json_cell(item)})
    searches = document.get("semantic_search", [])
    if isinstance(searches, list):
        for search in searches:
            if isinstance(search, Mapping):
                rows.append(
                    {
                        "section": "semantic_search",
                        "field": str(search.get("query", "")),
                        "value": _json_cell(search.get("results", [])),
                    }
                )
    return rows


def _render_log(document: Mapping[str, Any]) -> str:
    events = document.get("execution_log", [])
    if not isinstance(events, list) or not all(isinstance(item, str) for item in events):
        raise EvidenceError("execution_log inválido en la evidencia.")
    return "\n".join(events) + "\n"


def _render_markdown(document: Mapping[str, Any]) -> str:
    generated_at = _required_text(document, "generated_at")
    lines = ["# Evidencia generada", "", f"Generada: `{generated_at}`.", ""]
    lines.extend(["## Matriz de criterios", "", "| Criterio | Estado |", "| --- | --- |"])
    for item in _required_list(document, "criteria"):
        lines.append(f"| {item['criterion']} | {item['status']} |")
    lines.extend(
        [
            "",
            "## Bronze",
            "",
            "| Batch | Fuente | Obtenido en | Archivos | Bytes | SHA-256 | Estado |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in _required_list(document, "bronze"):
        bronze_line = (
            "| {batch_id} | {source} | {fetched_at} | {files} | {bytes} | "
            "{sha256_count} | {status} |"
        )
        lines.append(
            bronze_line.format(
                batch_id=item["batch_id"],
                source=item["source"],
                fetched_at="<br>".join(item["fetched_at"]),
                files=len(item["files"]),
                bytes=item["bytes"],
                sha256_count=item["sha256_count"],
                status=item["status"],
            )
        )
    integrity = document.get("payload_integrity", [])
    if isinstance(integrity, list):
        passed = sum(
            1 for item in integrity if isinstance(item, Mapping) and item.get("status") == "PASS"
        )
        lines.extend(
            [
                "",
                "## Integridad de payloads",
                "",
                (
                    "Payloads re-leÃ­dos con bytes y SHA-256 coincidentes: "
                    f"`{passed}/{len(integrity)}`."
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Contrato",
            "",
            "| Fuente | Extraídas | Válidas | Inválidas | Motivos reales |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in _required_list(document, "contract"):
        contract_line = "| {source} | {extracted} | {valid} | {invalid} | {reasons} |"
        lines.append(
            contract_line.format(
                source=item["source"],
                extracted=item["rows_extracted"],
                valid=item["rows_valid"],
                invalid=item["rows_invalid"],
                reasons=_json_cell(item["principales_motivos_reales"]),
            )
        )
    languages = document.get("languages", [])
    if isinstance(languages, list):
        lines.extend(
            [
                "",
                "## Cobertura de idiomas observada",
                "",
                "| Grupo | Registros Silver |",
                "| --- | ---: |",
            ]
        )
        for item in languages:
            if isinstance(item, Mapping):
                lines.append(f"| {item.get('language_group', '')} | {item.get('rows', 0)} |")
    lines.extend(
        [
            "",
            "## Idempotencia",
            "",
            "| Métrica | Corrida 1 | Corrida 2 | Esperado | Estado |",
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in _required_list(document, "idempotency"):
        idempotency_line = "| {metric} | {run_1} | {run_2} | {expected} | {status} |"
        lines.append(
            idempotency_line.format(
                metric=item["metric"],
                run_1=item["run_1"],
                run_2=item["run_2"],
                expected=item["expected"],
                status=item["status"],
            )
        )
    lines.extend(["", "## Duplicados", ""])
    for item in _required_list(document, "duplicates"):
        lines.extend(
            [
                f"### {item['name']} — {item['status']}",
                "",
                "```sql",
                str(item["sql"]),
                "```",
                "",
                f"Filas devueltas: `{item['returned_rows']}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Búsqueda semántica",
            "",
            "| Consulta | Rank | Canonical ID | Título | Idioma | Fuente | Score |",
            "| --- | ---: | --- | --- | --- | --- | ---: |",
        ]
    )
    for search in _required_list(document, "semantic_search"):
        for result in search["results"]:
            search_line = (
                "| {query} | {rank} | {canonical_id} | {title} | {language} | "
                "{source} | {score:.6f} |"
            )
            lines.append(
                search_line.format(
                    query=search["query"],
                    rank=result["rank"],
                    canonical_id=result["canonical_id"],
                    title=result["title"],
                    language=result["language"],
                    source=result["source"],
                    score=float(result["score"]),
                )
            )
    lines.extend(["", "## Seguridad sintética", ""])
    safety = document.get("synthetic_safety")
    if not isinstance(safety, Mapping):
        raise EvidenceError("synthetic_safety inválido en la evidencia.")
    for key, value in safety.items():
        lines.append(f"- `{key} = {value}`")
    lines.append("")
    return "\n".join(lines)


def _required_list(document: Mapping[str, Any], name: str) -> list[Mapping[str, Any]]:
    value = document.get(name)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise EvidenceError(f"{name} inválido en la evidencia.")
    return list(value)


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
