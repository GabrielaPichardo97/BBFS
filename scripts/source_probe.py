#!/usr/bin/env python3
"""Small, non-production probe for documented scholarly metadata endpoints.

The script keeps raw responses outside Git for evidence during source discovery.
It is deliberately limited to a small sample and is not an ingestion client.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:  # httpx is optional; urllib keeps this script runnable in a bare Python install.
    import httpx  # type: ignore
except ImportError:  # pragma: no cover - environment dependent
    httpx = None

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


USER_AGENT = "baby-first-steps-medallion-source-probe/0.1 (source discovery; contact: github.com/GabrielaPichardo97/BBFS)"
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 3
MIN_REQUEST_INTERVAL_SECONDS = 0.5  # At most two HTTP requests per second.
RAW_ROOT = Path("tmp/source_probe")
LAST_REQUEST_AT = 0.0


def text_of(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join(part.strip() for part in element.itertext() if part.strip())
    return value or None


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value.strip(), flags=re.I).lower() or None


def get(url: str) -> tuple[int | None, str, dict[str, str], float, str | None]:
    """Fetch once with bounded retries and return a recordable outcome."""
    global LAST_REQUEST_AT
    last_error: str | None = None
    for attempt in range(MAX_ATTEMPTS):
        delay = MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - LAST_REQUEST_AT)
        if delay > 0:
            time.sleep(delay)
        started = time.perf_counter()
        try:
            if httpx is not None:
                response = httpx.get(
                    url,
                    headers={"User-Agent": USER_AGENT, "Accept": "application/xml, application/json;q=0.9"},
                    timeout=TIMEOUT_SECONDS,
                    follow_redirects=True,
                )
                status, body = response.status_code, response.text
                headers = {key.lower(): value for key, value in response.headers.items()}
            else:
                request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # nosec B310: URL is fixed by source map
                    status, body = response.status, response.read().decode("utf-8", errors="replace")
                    headers = {key.lower(): value for key, value in response.headers.items()}
            LAST_REQUEST_AT = time.monotonic()
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            if status < 500 and status != 429:
                return status, body, headers, latency_ms, None
            last_error = f"HTTP {status}"
            retry_after = headers.get("retry-after")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
        except urllib.error.HTTPError as error:
            LAST_REQUEST_AT = time.monotonic()
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            body = error.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in error.headers.items()}
            if error.code < 500 and error.code != 429:
                return error.code, body, headers, latency_ms, None
            last_error = f"HTTP {error.code}"
            retry_after = headers.get("retry-after")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
        except Exception as error:  # Network failures should not abort a multi-source comparison.
            LAST_REQUEST_AT = time.monotonic()
            latency_ms = round((time.perf_counter() - started) * 1000, 1)
            body, headers = "", {}
            last_error = f"{type(error).__name__}: {error}"
            wait = 2**attempt
        if attempt < MAX_ATTEMPTS - 1:
            time.sleep(min(wait, 15))
    return None, body, headers, latency_ms, last_error


def save_raw(source: str, label: str, body: str, extension: str) -> str:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = RAW_ROOT / f"{stamp}_{source}_{label}.{extension}"
    path.write_text(body, encoding="utf-8")
    return str(path)


def pubmed_records(body: str) -> list[dict[str, Any]]:
    root = ET.fromstring(body)
    records = []
    for article in root.findall(".//PubmedArticle"):
        ids = {node.attrib.get("IdType", ""): text_of(node) for node in article.findall(".//ArticleId")}
        languages = [text_of(node) for node in article.findall(".//Article/Language")]
        records.append(
            {
                "title": text_of(article.find(".//ArticleTitle")),
                "abstract": " ".join(filter(None, (text_of(node) for node in article.findall(".//Abstract/AbstractText")))) or None,
                "language": languages[0] if languages else None,
                "pmid": text_of(article.find(".//PMID")),
                "doi": normalize_doi(ids.get("doi")),
                "external_id": text_of(article.find(".//PMID")),
                "permalink": f"https://pubmed.ncbi.nlm.nih.gov/{text_of(article.find('.//PMID'))}/" if text_of(article.find(".//PMID")) else None,
                "publication_date": text_of(article.find(".//ArticleDate/Year")) or text_of(article.find(".//PubDate/Year")) or text_of(article.find(".//PubDate/MedlineDate")),
                "authors": [text_of(node.find("LastName")) for node in article.findall(".//Author") if text_of(node.find("LastName"))],
                "keywords": [text_of(node) for node in article.findall(".//Keyword") if text_of(node)],
                "controlled_terms": [text_of(node) for node in article.findall(".//MeshHeading/DescriptorName") if text_of(node)],
            }
        )
    return records


def europepmc_records(body: str) -> list[dict[str, Any]]:
    results = json.loads(body).get("resultList", {}).get("result", [])
    records = []
    for item in results:
        keyword_list = item.get("keywordList") or {}
        keywords = keyword_list.get("keyword", []) if isinstance(keyword_list, dict) else []
        records.append(
            {
                "title": item.get("title"),
                "abstract": item.get("abstractText"),
                "language": item.get("language"),
                "pmid": item.get("pmid"),
                "doi": normalize_doi(item.get("doi")),
                "external_id": f"{item.get('source')}:{item.get('id')}" if item.get("source") and item.get("id") else item.get("id"),
                "permalink": item.get("fullTextUrlList", {}).get("fullTextUrl", [{}])[0].get("url") if item.get("fullTextUrlList") else None,
                "publication_date": item.get("firstPublicationDate") or item.get("journalIssn"),
                "authors": (item.get("authorString") or "").split(", ") if item.get("authorString") else [],
                "keywords": keywords,
                "controlled_terms": item.get("meshHeadingList", {}).get("meshHeading", []) if isinstance(item.get("meshHeadingList"), dict) else [],
                "license": item.get("license"),
            }
        )
    return records


def doaj_records(body: str) -> list[dict[str, Any]]:
    results = json.loads(body).get("results", [])
    records = []
    for item in results:
        bib = item.get("bibjson", {})
        identifiers = {value.get("type", "").lower(): value.get("id") for value in bib.get("identifier", [])}
        links = bib.get("link", [])
        records.append(
            {
                "title": bib.get("title"),
                "abstract": bib.get("abstract"),
                "language": (bib.get("language") or [None])[0],
                "pmid": None,
                "doi": normalize_doi(identifiers.get("doi")),
                "external_id": item.get("id"),
                "permalink": next((link.get("url") for link in links if link.get("type") in {"fulltext", "abstract"}), None),
                "publication_date": bib.get("year"),
                "authors": [author.get("name") for author in bib.get("author", []) if author.get("name")],
                "keywords": bib.get("keywords", []),
                "controlled_terms": [],
                "license": next((link.get("license") for link in links if link.get("license")), None),
            }
        )
    return records


def build_urls(source: str, query: str, limit: int) -> list[tuple[str, str, str]]:
    quoted = urllib.parse.quote(query)
    if source == "pubmed":
        search = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax={limit}&sort=relevance&term={quoted}"
        return [("search", search, "json")]
    if source == "europepmc":
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={quoted}&format=json&resultType=core&pageSize={limit}"
        return [("search", url, "json")]
    if source == "doaj":
        url = f"https://doaj.org/api/search/articles/{quoted}?pageSize={limit}"
        return [("search", url, "json")]
    raise ValueError(f"Unsupported source: {source}")


def profile(records: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(records)
    def share(predicate: Any) -> float | None:
        return round(100 * sum(bool(predicate(record)) for record in records) / count, 1) if count else None
    language_values = [str(record.get("language") or "").lower() for record in records]
    labeled_languages = [value for value in language_values if value]
    def language_share(predicate: Any) -> float | None:
        return round(100 * sum(predicate(value) for value in labeled_languages) / len(labeled_languages), 1) if labeled_languages else None
    return {
        "records": count,
        "title_pct": share(lambda row: row.get("title")),
        "abstract_or_description_pct": share(lambda row: row.get("abstract")),
        "language_labeled_pct": share(lambda row: row.get("language")),
        "spanish_pct_among_labeled": language_share(lambda value: value.startswith("spa") or value in {"es", "spanish"}),
        "english_pct_among_labeled": language_share(lambda value: value.startswith("eng") or value in {"en", "english"}),
        "doi_pct": share(lambda row: row.get("doi")),
        "pmid_pct": share(lambda row: row.get("pmid")),
        "permalink_pct": share(lambda row: row.get("permalink")),
        "publication_date_pct": share(lambda row: row.get("publication_date")),
        "authors_pct": share(lambda row: row.get("authors")),
        "keywords_pct": share(lambda row: row.get("keywords")),
        "controlled_terms_pct": share(lambda row: row.get("controlled_terms")),
        "license_pct": share(lambda row: row.get("license")),
    }


def probe(source: str, query: str, limit: int) -> dict[str, Any]:
    result: dict[str, Any] = {"source": source, "query": query, "limit": limit, "results_found": None, "requests": [], "records": [], "errors": []}
    consecutive_errors = 0
    try:
        requests = build_urls(source, query, limit)
    except ValueError as error:
        result["errors"].append(str(error))
        return result
    for label, url, extension in requests:
        if consecutive_errors >= 3:
            result["errors"].append("Stopped after three consecutive errors.")
            break
        status, body, headers, latency_ms, error = get(url)
        raw_path = save_raw(source, label, body, extension) if body else None
        result["requests"].append({"endpoint": url, "status_code": status, "latency_ms": latency_ms, "retry_after": headers.get("retry-after"), "raw_path": raw_path, "error": error})
        if error or status is None or status >= 400:
            consecutive_errors += 1
            result["errors"].append(error or f"HTTP {status}")
            continue
        consecutive_errors = 0
        try:
            if source == "pubmed":
                search_result = json.loads(body).get("esearchresult", {})
                result["results_found"] = int(search_result.get("count", 0))
                ids = search_result.get("idlist", [])
                if not ids:
                    result["records"] = []
                    continue
                fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&retmode=xml&id=" + urllib.parse.quote(",".join(ids))
                fetch_status, fetch_body, fetch_headers, fetch_latency, fetch_error = get(fetch_url)
                fetch_path = save_raw(source, "fetch", fetch_body, "xml") if fetch_body else None
                result["requests"].append({"endpoint": fetch_url, "status_code": fetch_status, "latency_ms": fetch_latency, "retry_after": fetch_headers.get("retry-after"), "raw_path": fetch_path, "error": fetch_error})
                if fetch_error or fetch_status is None or fetch_status >= 400:
                    result["errors"].append(fetch_error or f"HTTP {fetch_status}")
                else:
                    result["records"] = pubmed_records(fetch_body)
            elif source == "europepmc":
                result["results_found"] = int(json.loads(body).get("hitCount", 0))
                result["records"] = europepmc_records(body)
            elif source == "doaj":
                result["results_found"] = int(json.loads(body).get("total", 0))
                result["records"] = doaj_records(body)
        except (ValueError, ET.ParseError, KeyError, TypeError) as parse_error:
            result["errors"].append(f"Parse error: {parse_error}")
    result["sample_metrics"] = profile(result["records"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded source-discovery probe; not a production ingestion client.")
    parser.add_argument("--source", required=True, help="Comma-separated: pubmed, europepmc, doaj")
    parser.add_argument("--query", required=True, help="One source-side query; it may be an internal bilingual expansion.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum records per source (1-5, default 5).")
    args = parser.parse_args()
    if not 1 <= args.limit <= 5:
        parser.error("--limit must be between 1 and 5")
    sources = list(dict.fromkeys(part.strip().lower() for part in args.source.split(",") if part.strip()))
    if not sources or len(sources) > 3:
        parser.error("--source accepts between one and three distinct sources per comparison")
    summary = {"generated_at": datetime.now(timezone.utc).isoformat(), "purpose": "small source-discovery sample; percentages are sample-only", "probes": [probe(source, args.query, args.limit) for source in sources]}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
