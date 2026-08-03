"""Strict Pydantic contracts for in-memory Silver validation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

from baby_first_steps_medallion.silver.normalization import (
    DOI_PATTERN,
    OPENALEX_ID_PATTERN,
    PMID_PATTERN,
    normalize_doi,
    normalize_openalex_id,
    normalize_pmid,
    normalize_text,
)

SourceName = Literal["pubmed", "europe_pmc", "openalex"]
MIN_ABSTRACT_CHARACTERS = 80


def _normalized_list(value: Any, *, field_name: str, allow_empty: bool) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name}_invalid")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field_name}_invalid")
        cleaned = normalize_text(item)
        if not cleaned:
            if allow_empty:
                continue
            raise ValueError(f"{field_name}_invalid")
        if cleaned not in normalized:
            normalized.append(cleaned)
    return normalized


class ResourceRecord(BaseModel):
    """One validated source record; it has no persistence or UPSERT behavior."""

    model_config = ConfigDict(extra="forbid", strict=True)

    canonical_id: str
    source_name: SourceName
    source_record_id: str
    observed_sources: list[str]
    doi: str | None
    pmid: str | None
    openalex_id: str | None
    title: str
    abstract: str
    language: str
    publication_date: date | None
    authors: list[str]
    journal_or_publisher: str | None
    keywords: list[str]
    subject_terms: list[str]
    resource_url: str
    query_profiles: list[str]
    source_batch_id: str
    source_file: str
    source_ordinal: int
    raw_payload_sha256: str
    content_hash: str
    parsed_at: datetime

    @field_validator(
        "canonical_id",
        "source_record_id",
        "title",
        "language",
        "resource_url",
        "source_batch_id",
        "source_file",
        "raw_payload_sha256",
        "content_hash",
        mode="before",
    )
    @classmethod
    def normalize_required_text(cls, value: Any, info: Any) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{info.field_name}_invalid")
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError(f"{info.field_name}_empty")
        return normalized

    @field_validator("abstract", mode="before")
    @classmethod
    def validate_abstract(cls, value: Any) -> str:
        if not isinstance(value, str):
            raise ValueError("abstract_missing")
        normalized = normalize_text(value)
        if not normalized:
            raise ValueError("abstract_missing")
        if len(normalized) < MIN_ABSTRACT_CHARACTERS:
            raise ValueError("abstract_too_short")
        return normalized

    @field_validator("journal_or_publisher", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("journal_or_publisher_invalid")
        return normalize_text(value) or None

    @field_validator("doi", mode="before")
    @classmethod
    def validate_doi(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("doi_invalid")
        normalized = normalize_doi(value)
        if normalized is None or DOI_PATTERN.fullmatch(normalized) is None:
            raise ValueError("doi_invalid")
        return normalized

    @field_validator("pmid", mode="before")
    @classmethod
    def validate_pmid(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("pmid_invalid")
        normalized = normalize_pmid(value)
        if normalized is None or PMID_PATTERN.fullmatch(normalized) is None:
            raise ValueError("pmid_invalid")
        return normalized

    @field_validator("openalex_id", mode="before")
    @classmethod
    def validate_openalex_id(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("openalex_id_invalid")
        normalized = normalize_openalex_id(value)
        if normalized is None or OPENALEX_ID_PATTERN.fullmatch(normalized) is None:
            raise ValueError("openalex_id_invalid")
        return normalized

    @field_validator("authors", mode="before")
    @classmethod
    def validate_authors(cls, value: Any) -> list[str]:
        return _normalized_list(value, field_name="authors", allow_empty=True)

    @field_validator("keywords", "subject_terms", mode="before")
    @classmethod
    def validate_optional_terms(cls, value: Any, info: Any) -> list[str]:
        return _normalized_list(value, field_name=info.field_name, allow_empty=True)

    @field_validator("observed_sources", "query_profiles", mode="before")
    @classmethod
    def validate_required_terms(cls, value: Any, info: Any) -> list[str]:
        normalized = _normalized_list(value, field_name=info.field_name, allow_empty=False)
        if not normalized:
            raise ValueError(f"{info.field_name}_empty")
        return normalized

    @field_validator("resource_url")
    @classmethod
    def validate_resource_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("resource_url_invalid")
        return value

    @field_validator("publication_date")
    @classmethod
    def reject_future_publication_date(cls, value: date | None) -> date | None:
        if value is not None and value > datetime.now(UTC).date():
            raise ValueError("publication_date_future")
        return value

    @field_validator("source_ordinal")
    @classmethod
    def validate_source_ordinal(cls, value: int) -> int:
        if value < 1:
            raise ValueError("source_ordinal_invalid")
        return value

    @field_validator("parsed_at")
    @classmethod
    def validate_parsed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("parsed_at_timezone_missing")
        return value.astimezone(UTC)


class ValidationIssue(BaseModel):
    """A single validation error retained inside one quarantine event."""

    model_config = ConfigDict(extra="forbid", strict=True)

    field_path: str
    rejection_code: str
    error_type: str
    rejection_reason: str


class QuarantineRecord(BaseModel):
    """One auditable rejection per raw source record, with all its errors."""

    model_config = ConfigDict(extra="forbid", strict=True)

    quarantine_id: str
    canonical_id_candidate: str
    source_name: SourceName
    source_record_id: str
    rejection_code: str
    error_type: str
    field_path: str
    rejection_reason: str
    raw_record: dict[str, Any] | str
    raw_record_sha256: str
    source_batch_id: str
    source_file: str
    source_ordinal: int
    rejected_at: datetime
    errors: list[ValidationIssue]
