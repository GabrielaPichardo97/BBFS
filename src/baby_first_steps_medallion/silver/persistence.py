"""Transactional DuckDB persistence for validated Silver records."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.safety import assert_real_source_type
from baby_first_steps_medallion.silver.models import QuarantineRecord, ResourceRecord
from baby_first_steps_medallion.silver.service import SilverValidationResult

MIGRATION_NAME_PATTERN = re.compile(r"^(\d+)_([a-z0-9_]+)\.sql$")
SOURCE_PRIORITY = {"pubmed": 0, "europe_pmc": 1, "openalex": 2}


class SilverPersistenceError(RuntimeError):
    """A Silver transaction or its post-transaction audit could not complete safely."""


@dataclass(frozen=True)
class SilverPersistenceResult:
    """Counts calculated before the resource MERGE and returned after a commit."""

    run_id: str
    batch_id: str
    rows_inserted: int
    rows_updated: int
    rows_noop: int
    quarantine_inserted: int
    quarantine_noop: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "run_id": self.run_id,
            "batch_id": self.batch_id,
            "rows_inserted": self.rows_inserted,
            "rows_updated": self.rows_updated,
            "rows_noop": self.rows_noop,
            "quarantine_inserted": self.quarantine_inserted,
            "quarantine_noop": self.quarantine_noop,
        }


@dataclass(frozen=True)
class DuplicateAudit:
    """The exact duplicate counts used by the acceptance queries."""

    resource_duplicates: int
    quarantine_duplicates: int
    synthetic_rows: int

    def as_dict(self) -> dict[str, int]:
        return {
            "resource_duplicates": self.resource_duplicates,
            "quarantine_duplicates": self.quarantine_duplicates,
            "synthetic_rows": self.synthetic_rows,
        }


@dataclass(frozen=True)
class _StagedEntry:
    stage_ordinal: int
    canonical_id: str
    record: ResourceRecord


@dataclass(frozen=True)
class _CanonicalGroup:
    canonical_id: str
    entries: tuple[_StagedEntry, ...]
    primary: _StagedEntry
    observed_sources: tuple[str, ...]
    query_profiles: tuple[str, ...]


class SilverRepository:
    """Own Silver schema migration, load, audit, and run-history operations."""

    def __init__(
        self,
        settings: Settings,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        failure_injector: Callable[[], None] | None = None,
    ) -> None:
        self._settings = settings
        self._now = now
        self._failure_injector = failure_injector

    @property
    def db_path(self) -> Path:
        """Return the documented local DuckDB file path."""
        return self._settings.data_dir / "baby_first_steps.duckdb"

    def persist(self, validation: SilverValidationResult) -> SilverPersistenceResult:
        """Stage, merge, audit, and commit one validated real Bronze batch."""
        connection = self._connect()
        run_id = uuid4().hex
        started_at = self._now()
        try:
            self._apply_migrations(connection)
            self._create_run(connection, run_id, validation.batch_id, started_at)
            try:
                connection.execute("BEGIN TRANSACTION")
                self._upsert_bronze_batch(connection, validation.batch_id, started_at)
                connection.execute("DELETE FROM stg_resources")
                entries = self._staged_entries(validation.records)
                groups = self._canonical_groups(entries)
                groups = self._with_persisted_observations(connection, groups)
                self._insert_staging(connection, run_id, entries)
                self._apply_group_aggregates(connection, run_id, groups)
                if self._failure_injector is not None:
                    self._failure_injector()
                rows_inserted, rows_updated, rows_noop = self._resource_change_counts(
                    connection, run_id
                )
                self._upsert_resources(connection, run_id, started_at)
                self._upsert_resource_sources(connection, groups, validation.batch_id, started_at)
                quarantine_inserted, quarantine_noop = self._upsert_quarantines(
                    connection, validation.quarantines, started_at
                )
                result = SilverPersistenceResult(
                    run_id=run_id,
                    batch_id=validation.batch_id,
                    rows_inserted=rows_inserted,
                    rows_updated=rows_updated,
                    rows_noop=rows_noop,
                    quarantine_inserted=quarantine_inserted,
                    quarantine_noop=quarantine_noop,
                )
                audit = self._audit_connection(connection)
                self._require_clean_audit(audit)
                metrics = self._metrics_document(validation, result, audit)
                self._insert_dq_metrics(connection, validation, result, started_at)
                self._complete_run(connection, run_id, started_at, metrics)
                connection.execute("COMMIT")
                return result
            except Exception as error:
                connection.execute("ROLLBACK")
                self._fail_run(connection, run_id, self._now(), str(error))
                if isinstance(error, SilverPersistenceError):
                    raise
                raise SilverPersistenceError("La transacciÃ³n Silver se revirtiÃ³.") from error
        finally:
            connection.close()

    def audit_duplicates(self) -> DuplicateAudit:
        """Run acceptance queries and fail if duplicate or synthetic production rows exist."""
        connection = self._connect()
        try:
            self._apply_migrations(connection)
            audit = self._audit_connection(connection)
            self._require_clean_audit(audit)
            return audit
        finally:
            connection.close()

    def migrate(self) -> None:
        """Apply all versioned local schema migrations without loading a Bronze batch."""
        connection = self._connect()
        try:
            self._apply_migrations(connection)
        finally:
            connection.close()

    def show_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent persisted pipeline runs without exposing source payloads."""
        connection = self._connect()
        try:
            self._apply_migrations(connection)
            cursor = connection.execute(
                """
                SELECT run_id, command_name, batch_id, status, started_at, completed_at,
                       error_message,
                       metrics_json
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                [limit],
            )
            columns = [str(column[0]) for column in (cursor.description or [])]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _connect(self) -> duckdb.DuckDBPyConnection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path))

    def _apply_migrations(self, connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS meta_schema_version (
                version INTEGER PRIMARY KEY,
                migration_name VARCHAR NOT NULL UNIQUE,
                applied_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        migrations_dir = self._settings.root_dir / "sql"
        migration_paths = sorted(migrations_dir.glob("*.sql"))
        for path in migration_paths:
            match = MIGRATION_NAME_PATTERN.fullmatch(path.name)
            if match is None:
                continue
            version = int(match.group(1))
            applied = connection.execute(
                "SELECT 1 FROM meta_schema_version WHERE version = ?", [version]
            ).fetchone()
            if applied is not None:
                continue
            try:
                connection.execute("BEGIN TRANSACTION")
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute(
                    """
                    INSERT INTO meta_schema_version (version, migration_name, applied_at)
                    VALUES (?, ?, ?)
                    """,
                    [version, path.name, self._now()],
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                raise SilverPersistenceError(
                    f"No se pudo aplicar migraciÃ³n {path.name}."
                ) from error

    @staticmethod
    def _create_run(
        connection: duckdb.DuckDBPyConnection, run_id: str, batch_id: str, started_at: datetime
    ) -> None:
        connection.execute(
            """
            INSERT INTO pipeline_runs (run_id, command_name, batch_id, status, started_at)
            VALUES (?, 'silver', ?, 'running', ?)
            """,
            [run_id, batch_id, started_at],
        )

    @staticmethod
    def _upsert_bronze_batch(
        connection: duckdb.DuckDBPyConnection, batch_id: str, now: datetime
    ) -> None:
        connection.execute(
            """
            INSERT INTO bronze_batches (batch_id, status, first_loaded_at, last_loaded_at)
            VALUES (?, 'silver_loaded', ?, ?)
            ON CONFLICT (batch_id) DO UPDATE SET
                status = excluded.status,
                last_loaded_at = excluded.last_loaded_at
            """,
            [batch_id, now, now],
        )

    @staticmethod
    def _staged_entries(records: Iterable[ResourceRecord]) -> tuple[_StagedEntry, ...]:
        records_list = list(records)
        parent = list(range(len(records_list)))

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root = find(left)
            right_root = find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        identity_owner: dict[str, int] = {}
        for index, record in enumerate(records_list):
            for identifier_kind, identifier in (("doi", record.doi), ("pmid", record.pmid)):
                if identifier is None:
                    continue
                identity_key = f"{identifier_kind}:{identifier}"
                existing = identity_owner.get(identity_key)
                if existing is None:
                    identity_owner[identity_key] = index
                else:
                    union(index, existing)

        grouped_indices: dict[int, list[int]] = defaultdict(list)
        for index in range(len(records_list)):
            grouped_indices[find(index)].append(index)

        canonical_by_index: dict[int, str] = {}
        for indices in grouped_indices.values():
            group_records = [records_list[index] for index in indices]
            canonical_id = SilverRepository._canonical_id_for_group(group_records)
            for index in indices:
                canonical_by_index[index] = canonical_id
        return tuple(
            _StagedEntry(
                stage_ordinal=index + 1,
                canonical_id=canonical_by_index[index],
                record=record,
            )
            for index, record in enumerate(records_list)
        )

    @staticmethod
    def _canonical_id_for_group(records: list[ResourceRecord]) -> str:
        dois = sorted({record.doi for record in records if record.doi is not None})
        if dois:
            return f"doi:{dois[0]}"
        pmids = sorted({record.pmid for record in records if record.pmid is not None})
        if pmids:
            return f"pmid:{pmids[0]}"
        openalex_ids = sorted(
            {
                record.openalex_id
                for record in records
                if record.source_name == "openalex" and record.openalex_id is not None
            }
        )
        if openalex_ids:
            return f"openalex:{openalex_ids[0]}"
        return min(record.canonical_id for record in records)

    @staticmethod
    def _canonical_groups(entries: tuple[_StagedEntry, ...]) -> tuple[_CanonicalGroup, ...]:
        grouped: dict[str, list[_StagedEntry]] = defaultdict(list)
        for entry in entries:
            grouped[entry.canonical_id].append(entry)
        groups: list[_CanonicalGroup] = []
        for canonical_id, group_entries in grouped.items():
            primary = min(group_entries, key=SilverRepository._primary_sort_key)
            observed_sources = tuple(sorted({entry.record.source_name for entry in group_entries}))
            query_profiles = tuple(
                sorted(
                    {
                        profile
                        for entry in group_entries
                        for profile in entry.record.query_profiles
                    }
                )
            )
            groups.append(
                _CanonicalGroup(
                    canonical_id=canonical_id,
                    entries=tuple(group_entries),
                    primary=primary,
                    observed_sources=observed_sources,
                    query_profiles=query_profiles,
                )
            )
        return tuple(sorted(groups, key=lambda group: group.canonical_id))

    @staticmethod
    def _with_persisted_observations(
        connection: duckdb.DuckDBPyConnection, groups: tuple[_CanonicalGroup, ...]
    ) -> tuple[_CanonicalGroup, ...]:
        """Accumulate source and query-profile observations across idempotent loads."""
        enriched_groups: list[_CanonicalGroup] = []
        for group in groups:
            row = connection.execute(
                """
                SELECT observed_sources_json, query_profiles_json
                FROM silver_resources
                WHERE canonical_id = ?
                """,
                [group.canonical_id],
            ).fetchone()
            if row is None:
                enriched_groups.append(group)
                continue
            try:
                persisted_sources = _json_string_list(row[0])
                persisted_profiles = _json_string_list(row[1])
            except (TypeError, ValueError) as error:
                raise SilverPersistenceError(
                    "El agregado de procedencia Silver almacenado no es vÃ¡lido."
                ) from error
            enriched_groups.append(
                _CanonicalGroup(
                    canonical_id=group.canonical_id,
                    entries=group.entries,
                    primary=group.primary,
                    observed_sources=tuple(
                        sorted(set(group.observed_sources) | set(persisted_sources))
                    ),
                    query_profiles=tuple(
                        sorted(set(group.query_profiles) | set(persisted_profiles))
                    ),
                )
            )
        return tuple(enriched_groups)

    @staticmethod
    def _primary_sort_key(entry: _StagedEntry) -> tuple[int, int, int, str]:
        abstract = entry.record.abstract.strip()
        return (
            0 if abstract else 1,
            -len(abstract),
            SOURCE_PRIORITY[entry.record.source_name],
            entry.record.source_record_id,
        )

    @staticmethod
    def _insert_staging(
        connection: duckdb.DuckDBPyConnection, run_id: str, entries: tuple[_StagedEntry, ...]
    ) -> None:
        if not entries:
            return
        connection.executemany(
            """
            INSERT INTO stg_resources (
                run_id, stage_ordinal, canonical_id, source_name, source_record_id, doi, pmid,
                openalex_id, title, abstract, language, publication_date, authors_json,
                journal_or_publisher, keywords_json, subject_terms_json, resource_url,
                query_profiles_json, observed_sources_json, source_count, source_batch_id,
                source_file,
                source_ordinal, raw_payload_sha256, content_hash, parsed_at, source_type
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'real'
            )
            """,
            [
                (
                    run_id,
                    entry.stage_ordinal,
                    entry.canonical_id,
                    entry.record.source_name,
                    entry.record.source_record_id,
                    entry.record.doi,
                    entry.record.pmid,
                    entry.record.openalex_id,
                    entry.record.title,
                    entry.record.abstract,
                    entry.record.language,
                    entry.record.publication_date,
                    _json(entry.record.authors),
                    entry.record.journal_or_publisher,
                    _json(entry.record.keywords),
                    _json(entry.record.subject_terms),
                    entry.record.resource_url,
                    _json(entry.record.query_profiles),
                    _json(entry.record.observed_sources),
                    len(entry.record.observed_sources),
                    entry.record.source_batch_id,
                    entry.record.source_file,
                    entry.record.source_ordinal,
                    entry.record.raw_payload_sha256,
                    entry.record.content_hash,
                    entry.record.parsed_at,
                )
                for entry in entries
            ],
        )

    @staticmethod
    def _apply_group_aggregates(
        connection: duckdb.DuckDBPyConnection, run_id: str, groups: tuple[_CanonicalGroup, ...]
    ) -> None:
        for group in groups:
            connection.execute(
                """
                UPDATE stg_resources
                SET observed_sources_json = ?, query_profiles_json = ?, source_count = ?
                WHERE run_id = ? AND stage_ordinal = ?
                """,
                [
                    _json(group.observed_sources),
                    _json(group.query_profiles),
                    len(group.observed_sources),
                    run_id,
                    group.primary.stage_ordinal,
                ],
            )

    @staticmethod
    def _ranked_staging_sql() -> str:
        return """
            SELECT * FROM (
                SELECT
                    stg.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY canonical_id
                        ORDER BY
                            CASE WHEN length(abstract) > 0 THEN 0 ELSE 1 END,
                            length(abstract) DESC,
                            CASE source_name
                                WHEN 'pubmed' THEN 0
                                WHEN 'europe_pmc' THEN 1
                                WHEN 'openalex' THEN 2
                                ELSE 3
                            END,
                            source_record_id ASC
                    ) AS source_rank
                FROM stg_resources AS stg
                WHERE run_id = ?
            )
            WHERE source_rank = 1
        """

    def _resource_change_counts(
        self, connection: duckdb.DuckDBPyConnection, run_id: str
    ) -> tuple[int, int, int]:
        cursor = connection.execute(
            f"""
            WITH ranked AS ({self._ranked_staging_sql()})
            SELECT ranked.content_hash AS incoming_hash, silver.content_hash AS existing_hash
            FROM ranked
            LEFT JOIN silver_resources AS silver ON silver.canonical_id = ranked.canonical_id
            """,
            [run_id],
        )
        inserted = 0
        updated = 0
        noop = 0
        for incoming_hash, existing_hash in cursor.fetchall():
            if existing_hash is None:
                inserted += 1
            elif existing_hash == incoming_hash:
                noop += 1
            else:
                updated += 1
        return inserted, updated, noop

    def _upsert_resources(
        self, connection: duckdb.DuckDBPyConnection, run_id: str, now: datetime
    ) -> None:
        """Apply an insert/update UPSERT supported by the pinned DuckDB version.

        DuckDB 1.2 has transactions and unique constraints but no SQL ``MERGE``.
        The staging query already returns one deterministic row per canonical ID, so
        selecting it and inserting or updating within this transaction preserves
        the required UPSERT behavior without a database-version escalation.
        """
        cursor = connection.execute(f"SELECT * FROM ({self._ranked_staging_sql()})", [run_id])
        columns = [str(column[0]) for column in (cursor.description or [])]
        for row in cursor.fetchall():
            source = dict(zip(columns, row, strict=True))
            existing = connection.execute(
                "SELECT content_hash FROM silver_resources WHERE canonical_id = ?",
                [source["canonical_id"]],
            ).fetchone()
            if existing is None:
                self._insert_resource(connection, source, now)
            elif existing[0] == source["content_hash"]:
                self._update_resource_observation(connection, source)
            else:
                self._update_resource_content(connection, source, now)

    @staticmethod
    def _insert_resource(
        connection: duckdb.DuckDBPyConnection, source: dict[str, Any], now: datetime
    ) -> None:
        connection.execute(
            """
            INSERT INTO silver_resources (
                canonical_id, doi, pmid, openalex_id, primary_source_name, primary_source_record_id,
                title, abstract, language, publication_date, authors_json, journal_or_publisher,
                keywords_json, subject_terms_json, resource_url, query_profiles_json,
                observed_sources_json, source_count, content_hash, first_seen_batch_id,
                last_seen_batch_id, inserted_at, updated_at, source_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'real')
            """,
            [
                source["canonical_id"],
                source["doi"],
                source["pmid"],
                source["openalex_id"],
                source["source_name"],
                source["source_record_id"],
                source["title"],
                source["abstract"],
                source["language"],
                source["publication_date"],
                source["authors_json"],
                source["journal_or_publisher"],
                source["keywords_json"],
                source["subject_terms_json"],
                source["resource_url"],
                source["query_profiles_json"],
                source["observed_sources_json"],
                source["source_count"],
                source["content_hash"],
                source["source_batch_id"],
                source["source_batch_id"],
                now,
                now,
            ],
        )

    @staticmethod
    def _update_resource_observation(
        connection: duckdb.DuckDBPyConnection, source: dict[str, Any]
    ) -> None:
        """Refresh batch provenance without modifying ``updated_at`` for an exact no-op."""
        connection.execute(
            """
            UPDATE silver_resources
            SET query_profiles_json = ?, observed_sources_json = ?, source_count = ?,
                last_seen_batch_id = ?
            WHERE canonical_id = ?
            """,
            [
                source["query_profiles_json"],
                source["observed_sources_json"],
                source["source_count"],
                source["source_batch_id"],
                source["canonical_id"],
            ],
        )

    @staticmethod
    def _update_resource_content(
        connection: duckdb.DuckDBPyConnection, source: dict[str, Any], now: datetime
    ) -> None:
        connection.execute(
            """
            UPDATE silver_resources
            SET doi = ?, pmid = ?, openalex_id = ?, primary_source_name = ?,
                primary_source_record_id = ?, title = ?, abstract = ?, language = ?,
                publication_date = ?, authors_json = ?, journal_or_publisher = ?,
                keywords_json = ?, subject_terms_json = ?, resource_url = ?,
                query_profiles_json = ?, observed_sources_json = ?, source_count = ?,
                content_hash = ?, last_seen_batch_id = ?, updated_at = ?
            WHERE canonical_id = ?
            """,
            [
                source["doi"],
                source["pmid"],
                source["openalex_id"],
                source["source_name"],
                source["source_record_id"],
                source["title"],
                source["abstract"],
                source["language"],
                source["publication_date"],
                source["authors_json"],
                source["journal_or_publisher"],
                source["keywords_json"],
                source["subject_terms_json"],
                source["resource_url"],
                source["query_profiles_json"],
                source["observed_sources_json"],
                source["source_count"],
                source["content_hash"],
                source["source_batch_id"],
                now,
                source["canonical_id"],
            ],
        )

    @staticmethod
    def _upsert_resource_sources(
        connection: duckdb.DuckDBPyConnection,
        groups: tuple[_CanonicalGroup, ...],
        batch_id: str,
        now: datetime,
    ) -> None:
        for group in groups:
            for entry in group.entries:
                record = entry.record
                connection.execute(
                    """
                    INSERT INTO silver_resource_sources (
                        canonical_id, source_name, source_record_id, raw_payload_sha256,
                        source_batch_id, source_file, source_ordinal, query_profiles_json,
                        first_seen_batch_id, last_seen_batch_id, first_seen_at, last_seen_at,
                        source_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'real')
                    ON CONFLICT (
                        canonical_id, source_name, source_record_id, raw_payload_sha256,
                        source_ordinal
                    ) DO UPDATE SET
                        last_seen_batch_id = excluded.last_seen_batch_id,
                        last_seen_at = excluded.last_seen_at,
                        query_profiles_json = excluded.query_profiles_json
                    """,
                    [
                        group.canonical_id,
                        record.source_name,
                        record.source_record_id,
                        record.raw_payload_sha256,
                        batch_id,
                        record.source_file,
                        record.source_ordinal,
                        _json(record.query_profiles),
                        batch_id,
                        batch_id,
                        now,
                        now,
                    ],
                )

    @staticmethod
    def _upsert_quarantines(
        connection: duckdb.DuckDBPyConnection,
        quarantines: tuple[QuarantineRecord, ...],
        now: datetime,
    ) -> tuple[int, int]:
        inserted = 0
        noop = 0
        for quarantine in quarantines:
            assert_real_source_type("real", context="silver-rejects")
            existing = connection.execute(
                "SELECT 1 FROM silver_rejects WHERE quarantine_id = ?", [quarantine.quarantine_id]
            ).fetchone()
            if existing is None:
                inserted += 1
            else:
                noop += 1
            connection.execute(
                """
                INSERT INTO silver_rejects (
                    quarantine_id, canonical_id_candidate, source_name, source_record_id,
                    rejection_code, error_type, field_path, rejection_reason, raw_record_json,
                    raw_record_sha256, errors_json, source_batch_id, source_file, source_ordinal,
                    rejected_at, inserted_at, source_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'real')
                ON CONFLICT (quarantine_id) DO NOTHING
                """,
                [
                    quarantine.quarantine_id,
                    quarantine.canonical_id_candidate,
                    quarantine.source_name,
                    quarantine.source_record_id,
                    quarantine.rejection_code,
                    quarantine.error_type,
                    quarantine.field_path,
                    quarantine.rejection_reason,
                    _json(quarantine.raw_record),
                    quarantine.raw_record_sha256,
                    _json([issue.model_dump() for issue in quarantine.errors]),
                    quarantine.source_batch_id,
                    quarantine.source_file,
                    quarantine.source_ordinal,
                    quarantine.rejected_at,
                    now,
                ],
            )
        return inserted, noop

    @staticmethod
    def _metrics_document(
        validation: SilverValidationResult,
        result: SilverPersistenceResult,
        audit: DuplicateAudit,
    ) -> dict[str, Any]:
        return {
            "validation": validation.metrics(),
            "persistence": result.as_dict(),
            "audit": audit.as_dict(),
        }

    @staticmethod
    def _insert_dq_metrics(
        connection: duckdb.DuckDBPyConnection,
        validation: SilverValidationResult,
        result: SilverPersistenceResult,
        now: datetime,
    ) -> None:
        totals = validation.metrics()
        rows: list[tuple[str, str, int]] = []
        for metric_name in ("rows_extracted", "rows_valid", "rows_invalid", "parse_failures"):
            rows.append(("__all__", metric_name, int(totals[metric_name])))
        for metric_name, metric_value in result.as_dict().items():
            if isinstance(metric_value, int):
                rows.append(("__all__", metric_name, metric_value))
        for source_name, source_metrics in validation.metrics_by_source.items():
            for metric_name in ("rows_extracted", "rows_valid", "rows_invalid", "parse_failures"):
                rows.append((source_name, metric_name, int(getattr(source_metrics, metric_name))))
            for code, count in source_metrics.invalid_by_reason.items():
                rows.append((source_name, f"invalid_by_reason:{code}", count))
        connection.executemany(
            """
            INSERT INTO dq_metrics (
                run_id, batch_id, source_name, metric_name, metric_value, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (result.run_id, result.batch_id, source_name, metric_name, metric_value, now)
                for source_name, metric_name, metric_value in rows
            ],
        )

    @staticmethod
    def _complete_run(
        connection: duckdb.DuckDBPyConnection,
        run_id: str,
        completed_at: datetime,
        metrics: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            UPDATE pipeline_runs
            SET status = 'completed', completed_at = ?, metrics_json = ?
            WHERE run_id = ?
            """,
            [completed_at, _json(metrics), run_id],
        )

    @staticmethod
    def _fail_run(
        connection: duckdb.DuckDBPyConnection,
        run_id: str,
        completed_at: datetime,
        message: str,
    ) -> None:
        connection.execute(
            """
            UPDATE pipeline_runs
            SET status = 'failed', completed_at = ?, error_message = ?
            WHERE run_id = ?
            """,
            [completed_at, message, run_id],
        )

    @staticmethod
    def _audit_connection(connection: duckdb.DuckDBPyConnection) -> DuplicateAudit:
        resource_duplicates = len(
            connection.execute(
                """
                SELECT canonical_id, COUNT(*) AS duplicate_count
                FROM silver_resources
                GROUP BY canonical_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
        )
        quarantine_duplicates = len(
            connection.execute(
                """
                SELECT quarantine_id, COUNT(*) AS duplicate_count
                FROM silver_rejects
                GROUP BY quarantine_id
                HAVING COUNT(*) > 1
                """
            ).fetchall()
        )
        synthetic_rows = 0
        for table_name in (
            "stg_resources",
            "silver_resources",
            "silver_resource_sources",
            "silver_rejects",
            "gold_embeddings",
        ):
            row = connection.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE source_type = 'synthetic'"
            ).fetchone()
            if row is not None:
                synthetic_rows += int(row[0])
        return DuplicateAudit(resource_duplicates, quarantine_duplicates, synthetic_rows)

    @staticmethod
    def _require_clean_audit(audit: DuplicateAudit) -> None:
        if audit.resource_duplicates or audit.quarantine_duplicates or audit.synthetic_rows:
            raise SilverPersistenceError(
                "AuditorÃ­a Silver fallÃ³: duplicados o source_type='synthetic' detectados."
            )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)


def _json_string_list(value: Any) -> list[str]:
    """Decode a persisted JSON list while rejecting malformed provenance state."""
    if not isinstance(value, str):
        raise ValueError("json_list_not_text")
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise ValueError("json_list_invalid")
    return decoded
