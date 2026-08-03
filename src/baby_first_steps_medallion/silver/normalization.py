"""Silver-only normalization and stable identifiers for source records."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Any

DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)
PMID_PATTERN = re.compile(r"^\d+$")
OPENALEX_ID_PATTERN = re.compile(r"^W\d+$", re.IGNORECASE)


def normalize_text(value: str) -> str:
    """Apply the allowed Unicode and whitespace normalization in Silver."""
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalize_doi(value: str | None) -> str | None:
    """Remove standard DOI wrappers without changing the DOI content itself."""
    if value is None:
        return None
    normalized = normalize_text(value)
    lowered = normalized.lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "http://dx.doi.org/", "doi:"):
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    normalized = normalize_text(normalized).lower()
    return normalized or None


def normalize_pmid(value: str | None) -> str | None:
    """Normalize a PMID wrapper while retaining the source-provided digits."""
    if value is None:
        return None
    normalized = normalize_text(value)
    if normalized.lower().startswith("pmid:"):
        normalized = normalize_text(normalized[5:])
    return normalized or None


def normalize_openalex_id(value: str | None) -> str | None:
    """Use the compact W identifier from a native OpenAlex URL or ID."""
    if value is None:
        return None
    normalized = normalize_text(value).rstrip("/")
    marker = "/"
    if marker in normalized:
        normalized = normalized.rsplit(marker, maxsplit=1)[-1]
    return normalized.upper() or None


def is_valid_doi(value: str | None) -> bool:
    """Return whether an already-normalized DOI has a usable DOI shape."""
    return value is not None and DOI_PATTERN.fullmatch(value) is not None


def canonical_id_for(
    *,
    source_name: str,
    source_record_id: str,
    doi: str | None,
    pmid: str | None,
    openalex_id: str | None,
) -> str:
    """Apply the documented DOI, PMID, OpenAlex, then source-native precedence."""
    normalized_doi = normalize_doi(doi)
    normalized_pmid = normalize_pmid(pmid)
    normalized_openalex_id = normalize_openalex_id(openalex_id)
    if is_valid_doi(normalized_doi):
        return f"doi:{normalized_doi}"
    if normalized_pmid is not None and PMID_PATTERN.fullmatch(normalized_pmid):
        return f"pmid:{normalized_pmid}"
    if source_name == "openalex" and normalized_openalex_id is not None:
        return f"openalex:{normalized_openalex_id}"
    return f"source:{source_name}:{normalize_text(source_record_id)}"


def content_hash_for(record: dict[str, Any]) -> str:
    """Hash normalized document content, deliberately excluding batch paths and timestamps."""
    publication_date = record.get("publication_date")
    if isinstance(publication_date, date):
        publication_date_value: str | None = publication_date.isoformat()
    else:
        publication_date_value = None
    stable_content = {
        "abstract": record.get("abstract"),
        "authors": record.get("authors"),
        "doi": record.get("doi"),
        "journal_or_publisher": record.get("journal_or_publisher"),
        "keywords": record.get("keywords"),
        "language": record.get("language"),
        "openalex_id": record.get("openalex_id"),
        "pmid": record.get("pmid"),
        "publication_date": publication_date_value,
        "subject_terms": record.get("subject_terms"),
        "title": record.get("title"),
    }
    serialized = json.dumps(
        stable_content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def raw_record_hash(raw_record: dict[str, Any] | str) -> str:
    """Hash a parsed source record for quarantine traceability, not domain identity."""
    if isinstance(raw_record, str):
        encoded = raw_record.encode("utf-8")
    else:
        encoded = json.dumps(
            raw_record,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
