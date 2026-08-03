"""Source-specific parsing performed only after immutable Bronze storage."""

from __future__ import annotations

import json
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, cast

from baby_first_steps_medallion.silver.normalization import normalize_openalex_id

SourceName = Literal["pubmed", "europe_pmc", "openalex"]


class SourceParseError(ValueError):
    """A stored source response cannot be decoded into its documented envelope."""


@dataclass(frozen=True)
class ExtractedRecord:
    """A raw record plus source-mapped candidate fields before Pydantic validation."""

    raw_record: dict[str, Any] | str
    candidate: dict[str, Any]
    source_ordinal: int


def extract_records(
    *, source_name: SourceName, request_kind: str, payload: bytes
) -> list[ExtractedRecord]:
    """Decode one stored payload without changing its Bronze bytes on disk."""
    if source_name == "pubmed":
        if request_kind != "fetch":
            return []
        return _extract_pubmed(payload)
    if source_name == "europe_pmc":
        return _extract_europe_pmc(payload)
    if source_name == "openalex":
        return _extract_openalex(payload)
    raise SourceParseError(f"Fuente Silver no soportada: {source_name}")


def _load_json(payload: bytes, *, source_name: str) -> dict[str, Any]:
    try:
        decoded = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceParseError(f"JSON invÃ¡lido para {source_name}") from error
    if not isinstance(decoded, dict):
        raise SourceParseError(f"La respuesta JSON de {source_name} no es un objeto")
    return cast(dict[str, Any], decoded)


def _as_mapping(value: Any) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _string_list(value: Any) -> list[str]:
    return [item for item in _as_list(value) if isinstance(item, str)]


def _full_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _date_from_elements(parent: element_tree.Element | None) -> date | None:
    if parent is None:
        return None
    year = _as_text(parent.findtext("Year"))
    month = _as_text(parent.findtext("Month"))
    day = _as_text(parent.findtext("Day"))
    if year is None or month is None or day is None:
        return None
    month_lookup = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    try:
        month_number = int(month) if month.isdigit() else month_lookup[month[:3].lower()]
        return date(int(year), month_number, int(day))
    except (KeyError, ValueError):
        return None


def _xml_text(element: element_tree.Element | None) -> str:
    if element is None:
        return ""
    return "".join(element.itertext())


def _pubmed_abstract(article: element_tree.Element) -> str:
    parts: list[str] = []
    for abstract_node in article.findall("./MedlineCitation/Article/Abstract/AbstractText"):
        text = _xml_text(abstract_node)
        label = abstract_node.attrib.get("Label")
        if label and text:
            parts.append(f"{label} {text}")
        elif text:
            parts.append(text)
    return " ".join(parts)


def _pubmed_authors(article: element_tree.Element) -> list[str]:
    authors: list[str] = []
    for author in article.findall("./MedlineCitation/Article/AuthorList/Author"):
        collective = _as_text(author.findtext("CollectiveName"))
        if collective:
            authors.append(collective)
            continue
        given = _as_text(author.findtext("ForeName")) or _as_text(author.findtext("Initials"))
        family = _as_text(author.findtext("LastName"))
        name = " ".join(part for part in (given, family) if part)
        if name:
            authors.append(name)
    return authors


def _pubmed_doi(article: element_tree.Element) -> str | None:
    for node in article.findall("./PubmedData/ArticleIdList/ArticleId"):
        if node.attrib.get("IdType", "").lower() == "doi":
            value = _xml_text(node)
            if value:
                return value
    for node in article.findall("./MedlineCitation/Article/ELocationID"):
        if node.attrib.get("EIdType", "").lower() == "doi":
            value = _xml_text(node)
            if value:
                return value
    return None


def _extract_pubmed(payload: bytes) -> list[ExtractedRecord]:
    try:
        root = element_tree.fromstring(payload)
    except element_tree.ParseError as error:
        raise SourceParseError("XML PubMed invÃ¡lido") from error
    extracted: list[ExtractedRecord] = []
    for ordinal, article in enumerate(root.findall(".//PubmedArticle"), start=1):
        pmid = _as_text(article.findtext("./MedlineCitation/PMID")) or ""
        issue_date = _date_from_elements(
            article.find("./MedlineCitation/Article/Journal/JournalIssue/PubDate")
        )
        article_date = _date_from_elements(article.find("./MedlineCitation/Article/ArticleDate"))
        raw_record = element_tree.tostring(article, encoding="unicode")
        extracted.append(
            ExtractedRecord(
                raw_record=raw_record,
                source_ordinal=ordinal,
                candidate={
                    "source_record_id": pmid,
                    "doi": _pubmed_doi(article),
                    "pmid": pmid or None,
                    "openalex_id": None,
                    "title": _xml_text(article.find("./MedlineCitation/Article/ArticleTitle")),
                    "abstract": _pubmed_abstract(article),
                    "language": _as_text(
                        article.findtext("./MedlineCitation/Article/Language")
                    )
                    or "unknown",
                    "publication_date": article_date or issue_date,
                    "authors": _pubmed_authors(article),
                    "journal_or_publisher": _xml_text(
                        article.find("./MedlineCitation/Article/Journal/Title")
                    )
                    or None,
                    "keywords": [
                        _xml_text(node)
                        for node in article.findall("./MedlineCitation/KeywordList/Keyword")
                        if _xml_text(node)
                    ],
                    "subject_terms": [
                        _xml_text(node)
                        for node in article.findall(
                            "./MedlineCitation/MeshHeadingList/MeshHeading/DescriptorName"
                        )
                        if _xml_text(node)
                    ],
                    "resource_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                },
            )
        )
    return extracted


def _europe_authors(record: dict[str, Any]) -> list[str]:
    author_list = _as_mapping(record.get("authorList"))
    authors: list[str] = []
    for author in _as_list(author_list.get("author")):
        if isinstance(author, str):
            authors.append(author)
            continue
        author_map = _as_mapping(author)
        name = _as_text(author_map.get("fullName")) or _as_text(author_map.get("lastName"))
        if name:
            authors.append(name)
    return authors


def _europe_terms(record: dict[str, Any], field_name: str) -> list[str]:
    values = record.get(field_name)
    if isinstance(values, dict):
        values = values.get(field_name.removesuffix("List"))
    return _string_list(values)


def _extract_europe_pmc(payload: bytes) -> list[ExtractedRecord]:
    envelope = _load_json(payload, source_name="europe_pmc")
    result_list = _as_mapping(envelope.get("resultList"))
    extracted: list[ExtractedRecord] = []
    for ordinal, raw in enumerate(_as_list(result_list.get("result")), start=1):
        raw_record = _as_mapping(raw)
        source = _as_text(raw_record.get("source")) or "unknown"
        native_id = _as_text(raw_record.get("id")) or ""
        source_record_id = f"{source}:{native_id}" if native_id else ""
        journal_info = _as_mapping(raw_record.get("journalInfo"))
        journal = _as_text(raw_record.get("journalTitle")) or _as_text(journal_info.get("title"))
        journal = journal or _as_text(raw_record.get("publisher"))
        extracted.append(
            ExtractedRecord(
                raw_record=raw_record,
                source_ordinal=ordinal,
                candidate={
                    "source_record_id": source_record_id,
                    "doi": _as_text(raw_record.get("doi")),
                    "pmid": _as_text(raw_record.get("pmid")),
                    "openalex_id": None,
                    "title": _as_text(raw_record.get("title")) or "",
                    "abstract": _as_text(raw_record.get("abstractText")) or "",
                    "language": _as_text(raw_record.get("language")) or "unknown",
                    "publication_date": _full_date(raw_record.get("firstPublicationDate")),
                    "authors": _europe_authors(raw_record),
                    "journal_or_publisher": journal,
                    "keywords": _europe_terms(raw_record, "keywordList"),
                    "subject_terms": _europe_terms(raw_record, "meshHeadingList"),
                    "resource_url": f"https://europepmc.org/article/{source}/{native_id}",
                },
            )
        )
    return extracted


def _openalex_abstract(value: Any) -> str:
    inverted_index = _as_mapping(value)
    positions: dict[int, str] = {}
    for token, token_positions in inverted_index.items():
        if not isinstance(token, str):
            continue
        for position in _as_list(token_positions):
            if isinstance(position, int) and position >= 0 and position not in positions:
                positions[position] = token
    return " ".join(positions[index] for index in sorted(positions))


def _openalex_authors(record: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for authorship in _as_list(record.get("authorships")):
        author = _as_mapping(_as_mapping(authorship).get("author"))
        name = _as_text(author.get("display_name"))
        if name:
            authors.append(name)
    return authors


def _openalex_display_names(value: Any) -> list[str]:
    names: list[str] = []
    for item in _as_list(value):
        name = _as_text(_as_mapping(item).get("display_name"))
        if name:
            names.append(name)
    return names


def _extract_openalex(payload: bytes) -> list[ExtractedRecord]:
    envelope = _load_json(payload, source_name="openalex")
    extracted: list[ExtractedRecord] = []
    for ordinal, raw in enumerate(_as_list(envelope.get("results")), start=1):
        raw_record = _as_mapping(raw)
        openalex_id = normalize_openalex_id(_as_text(raw_record.get("id")))
        primary_location = _as_mapping(raw_record.get("primary_location"))
        source = _as_mapping(primary_location.get("source"))
        ids = _as_mapping(raw_record.get("ids"))
        extracted.append(
            ExtractedRecord(
                raw_record=raw_record,
                source_ordinal=ordinal,
                candidate={
                    "source_record_id": openalex_id or "",
                    "doi": _as_text(raw_record.get("doi")),
                    "pmid": _as_text(ids.get("pmid")),
                    "openalex_id": openalex_id,
                    "title": _as_text(raw_record.get("title")) or "",
                    "abstract": _openalex_abstract(raw_record.get("abstract_inverted_index")),
                    "language": _as_text(raw_record.get("language")) or "unknown",
                    "publication_date": _full_date(raw_record.get("publication_date")),
                    "authors": _openalex_authors(raw_record),
                    "journal_or_publisher": _as_text(source.get("display_name"))
                    or _as_text(raw_record.get("publisher")),
                    "keywords": _openalex_display_names(raw_record.get("keywords")),
                    "subject_terms": _openalex_display_names(raw_record.get("concepts")),
                    "resource_url": _as_text(raw_record.get("id"))
                    or "https://openalex.org/unknown",
                },
            )
        )
    return extracted
