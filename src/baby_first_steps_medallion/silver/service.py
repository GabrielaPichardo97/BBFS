"""Read-only Bronze-to-Silver extraction, validation, metrics, and quarantine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from baby_first_steps_medallion.bronze.storage import sha256_bytes
from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.safety import assert_real_source_type
from baby_first_steps_medallion.silver.models import (
    QuarantineRecord,
    ResourceRecord,
    SourceName,
    ValidationIssue,
)
from baby_first_steps_medallion.silver.normalization import (
    canonical_id_for,
    content_hash_for,
    raw_record_hash,
)
from baby_first_steps_medallion.silver.parsers import (
    ExtractedRecord,
    SourceParseError,
    extract_records,
)

SUPPORTED_SOURCES = frozenset({"pubmed", "europe_pmc", "openalex"})


class SilverValidationError(ValueError):
    """A requested Bronze batch cannot safely be evaluated by Silver."""


@dataclass
class SourceMetrics:
    """Counts for one source in a read-only Silver validation run."""

    rows_extracted: int = 0
    rows_valid: int = 0
    rows_invalid: int = 0
    invalid_by_reason: dict[str, int] = field(default_factory=dict)
    parse_failures: int = 0
    abstracts_missing: int = 0

    def as_dict(self) -> dict[str, int | float | dict[str, int] | None]:
        missing_percentage = (
            None
            if self.rows_extracted == 0
            else round((self.abstracts_missing / self.rows_extracted) * 100, 2)
        )
        return {
            "rows_extracted": self.rows_extracted,
            "rows_valid": self.rows_valid,
            "rows_invalid": self.rows_invalid,
            "invalid_by_reason": dict(sorted(self.invalid_by_reason.items())),
            "parse_failures": self.parse_failures,
            "abstracts_missing": self.abstracts_missing,
            "abstracts_missing_percentage": missing_percentage,
        }


@dataclass(frozen=True)
class SilverValidationResult:
    """Ephemeral validated records and quarantine events; nothing is persisted as Silver."""

    batch_id: str
    records: tuple[ResourceRecord, ...]
    quarantines: tuple[QuarantineRecord, ...]
    metrics_by_source: dict[SourceName, SourceMetrics]

    def metrics(self) -> dict[str, Any]:
        sources = {
            source_name: source_metrics.as_dict()
            for source_name, source_metrics in sorted(self.metrics_by_source.items())
        }
        totals = SourceMetrics()
        for source_metrics in self.metrics_by_source.values():
            totals.rows_extracted += source_metrics.rows_extracted
            totals.rows_valid += source_metrics.rows_valid
            totals.rows_invalid += source_metrics.rows_invalid
            totals.parse_failures += source_metrics.parse_failures
            totals.abstracts_missing += source_metrics.abstracts_missing
            for code, count in source_metrics.invalid_by_reason.items():
                totals.invalid_by_reason[code] = totals.invalid_by_reason.get(code, 0) + count
        return {
            "batch_id": self.batch_id,
            "rows_extracted": totals.rows_extracted,
            "rows_valid": totals.rows_valid,
            "rows_invalid": totals.rows_invalid,
            "invalid_by_reason": dict(sorted(totals.invalid_by_reason.items())),
            "parse_failures": totals.parse_failures,
            "sources": sources,
        }


class SilverValidator:
    """Validate one immutable local Bronze batch without making network calls or writes."""

    def __init__(
        self,
        settings: Settings,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._now = now

    def validate_batch(self, batch_id: str) -> SilverValidationResult:
        """Extract real source records from one Bronze manifest into memory only."""
        batch_dir = self._batch_dir(batch_id)
        manifest = self._load_manifest(batch_dir)
        metrics = self._initialize_metrics(manifest)
        records: list[ResourceRecord] = []
        quarantines: list[QuarantineRecord] = []

        responses = manifest.get("responses")
        if not isinstance(responses, list):
            raise SilverValidationError("El manifest Bronze no contiene una lista de respuestas.")
        for response in responses:
            if not isinstance(response, dict):
                raise SilverValidationError("El manifest Bronze contiene una respuesta invÃ¡lida.")
            source_name = self._source_name(response)
            assert_real_source_type(str(response.get("source_type", "")), context="silver-input")
            payload, source_file, payload_sha256 = self._read_verified_payload(batch_dir, response)
            try:
                extracted_records = extract_records(
                    source_name=source_name,
                    request_kind=str(response.get("request_kind", "")),
                    payload=payload,
                )
            except SourceParseError:
                metrics[source_name].parse_failures += 1
                continue
            for extracted in extracted_records:
                metrics[source_name].rows_extracted += 1
                record_or_quarantine = self._validate_extracted_record(
                    source_name=source_name,
                    extracted=extracted,
                    source_batch_id=batch_id,
                    source_file=source_file,
                    raw_payload_sha256=payload_sha256,
                    query_profile=response.get("query_profile"),
                )
                if isinstance(record_or_quarantine, ResourceRecord):
                    records.append(record_or_quarantine)
                    metrics[source_name].rows_valid += 1
                else:
                    quarantines.append(record_or_quarantine)
                    self._record_rejection(metrics[source_name], record_or_quarantine)

        return SilverValidationResult(
            batch_id=batch_id,
            records=tuple(records),
            quarantines=tuple(quarantines),
            metrics_by_source=metrics,
        )

    def _batch_dir(self, batch_id: str) -> Path:
        if not batch_id or Path(batch_id).name != batch_id:
            raise SilverValidationError("batch_id invÃ¡lido.")
        bronze_root = (self._settings.data_dir / "bronze").resolve()
        batch_dir = (bronze_root / batch_id).resolve()
        if not batch_dir.is_relative_to(bronze_root) or not batch_dir.is_dir():
            raise SilverValidationError(f"No se encontrÃ³ el batch Bronze: {batch_id}")
        return batch_dir

    @staticmethod
    def _load_manifest(batch_dir: Path) -> dict[str, Any]:
        manifest_path = batch_dir / "manifest.json"
        try:
            document = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SilverValidationError(f"Manifest Bronze invÃ¡lido: {manifest_path}") from error
        if not isinstance(document, dict):
            raise SilverValidationError(f"Manifest Bronze invÃ¡lido: {manifest_path}")
        return cast(dict[str, Any], document)

    @staticmethod
    def _source_name(response: dict[str, Any]) -> SourceName:
        value = response.get("source_name")
        if not isinstance(value, str) or value not in SUPPORTED_SOURCES:
            raise SilverValidationError(f"Fuente Bronze no soportada: {value!r}")
        return cast(SourceName, value)

    @staticmethod
    def _initialize_metrics(manifest: dict[str, Any]) -> dict[SourceName, SourceMetrics]:
        metrics: dict[SourceName, SourceMetrics] = {}
        declared_sources = manifest.get("sources", [])
        if not isinstance(declared_sources, list):
            raise SilverValidationError("El manifest Bronze contiene fuentes invÃ¡lidas.")
        for source_name in declared_sources:
            if isinstance(source_name, str) and source_name in SUPPORTED_SOURCES:
                metrics[cast(SourceName, source_name)] = SourceMetrics()
        for source_name in SUPPORTED_SOURCES:
            metrics.setdefault(cast(SourceName, source_name), SourceMetrics())
        return metrics

    @staticmethod
    def _read_verified_payload(
        batch_dir: Path, response: dict[str, Any]
    ) -> tuple[bytes, str, str]:
        source_file = response.get("file")
        documented_hash = response.get("sha256")
        if not isinstance(source_file, str) or not isinstance(documented_hash, str):
            raise SilverValidationError("La respuesta Bronze no incluye archivo o SHA-256.")
        payload_path = (batch_dir / source_file).resolve()
        if not payload_path.is_relative_to(batch_dir) or not payload_path.is_file():
            raise SilverValidationError(f"Payload Bronze invÃ¡lido: {source_file}")
        try:
            payload = payload_path.read_bytes()
        except OSError as error:
            raise SilverValidationError(f"No se pudo leer payload Bronze: {source_file}") from error
        actual_hash = sha256_bytes(payload)
        if actual_hash != documented_hash:
            raise SilverValidationError(f"SHA-256 Bronze no coincide: {source_file}")
        return payload, source_file, actual_hash

    def _validate_extracted_record(
        self,
        *,
        source_name: SourceName,
        extracted: ExtractedRecord,
        source_batch_id: str,
        source_file: str,
        raw_payload_sha256: str,
        query_profile: Any,
    ) -> ResourceRecord | QuarantineRecord:
        candidate = dict(extracted.candidate)
        source_record_id = candidate.get("source_record_id")
        source_record_id_text = source_record_id if isinstance(source_record_id, str) else ""
        query_profiles = [query_profile] if isinstance(query_profile, str) else ["unknown"]
        candidate.update(
            {
                "canonical_id": canonical_id_for(
                    source_name=source_name,
                    source_record_id=source_record_id_text,
                    doi=cast(str | None, candidate.get("doi")),
                    pmid=cast(str | None, candidate.get("pmid")),
                    openalex_id=cast(str | None, candidate.get("openalex_id")),
                ),
                "source_name": source_name,
                "observed_sources": [source_name],
                "query_profiles": query_profiles,
                "source_batch_id": source_batch_id,
                "source_file": source_file,
                "source_ordinal": extracted.source_ordinal,
                "raw_payload_sha256": raw_payload_sha256,
                "content_hash": "pending",
                "parsed_at": self._now(),
            }
        )
        try:
            validated = ResourceRecord.model_validate(candidate)
        except ValidationError as error:
            return self._quarantine(
                source_name=source_name,
                source_record_id=source_record_id_text,
                canonical_id_candidate=str(candidate["canonical_id"]),
                raw_record=extracted.raw_record,
                source_batch_id=source_batch_id,
                source_file=source_file,
                source_ordinal=extracted.source_ordinal,
                validation_error=error,
            )
        content_hash = content_hash_for(validated.model_dump())
        return validated.model_copy(update={"content_hash": content_hash})

    def _quarantine(
        self,
        *,
        source_name: SourceName,
        source_record_id: str,
        canonical_id_candidate: str,
        raw_record: dict[str, Any] | str,
        source_batch_id: str,
        source_file: str,
        source_ordinal: int,
        validation_error: ValidationError,
    ) -> QuarantineRecord:
        issues = self._validation_issues(validation_error)
        raw_sha256 = raw_record_hash(raw_record)
        id_material = "|".join(
            [
                source_name,
                source_record_id,
                raw_sha256,
                *[f"{issue.field_path}:{issue.rejection_code}" for issue in issues],
            ]
        )
        quarantine_id = hashlib.sha256(id_material.encode("utf-8")).hexdigest()
        first_issue = issues[0]
        rejection_code = (
            first_issue.rejection_code if len(issues) == 1 else "multiple_validation_errors"
        )
        return QuarantineRecord(
            quarantine_id=quarantine_id,
            canonical_id_candidate=canonical_id_candidate,
            source_name=source_name,
            source_record_id=source_record_id,
            rejection_code=rejection_code,
            error_type=first_issue.error_type,
            field_path=first_issue.field_path,
            rejection_reason="; ".join(issue.rejection_reason for issue in issues),
            raw_record=raw_record,
            raw_record_sha256=raw_sha256,
            source_batch_id=source_batch_id,
            source_file=source_file,
            source_ordinal=source_ordinal,
            rejected_at=self._now(),
            errors=issues,
        )

    @staticmethod
    def _validation_issues(error: ValidationError) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for item in error.errors():
            location = item.get("loc", ())
            field_path = ".".join(str(part) for part in location) or "record"
            message = str(item.get("msg", "validation_error"))
            rejection_code = message.removeprefix("Value error, ")
            issues.append(
                ValidationIssue(
                    field_path=field_path,
                    rejection_code=rejection_code,
                    error_type=str(item.get("type", "validation_error")),
                    rejection_reason=message,
                )
            )
        return issues or [
            ValidationIssue(
                field_path="record",
                rejection_code="validation_error",
                error_type="validation_error",
                rejection_reason="Validation error without details",
            )
        ]

    @staticmethod
    def _record_rejection(metrics: SourceMetrics, quarantine: QuarantineRecord) -> None:
        metrics.rows_invalid += 1
        seen_codes: set[str] = set()
        for issue in quarantine.errors:
            if issue.rejection_code in seen_codes:
                continue
            metrics.invalid_by_reason[issue.rejection_code] = (
                metrics.invalid_by_reason.get(issue.rejection_code, 0) + 1
            )
            seen_codes.add(issue.rejection_code)
        if any(issue.rejection_code == "abstract_missing" for issue in quarantine.errors):
            metrics.abstracts_missing += 1
