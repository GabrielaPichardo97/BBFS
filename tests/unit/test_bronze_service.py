from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx

from baby_first_steps_medallion.bronze.adapters import (
    EuropePmcAdapter,
    OpenAlexAdapter,
    PubMedAdapter,
)
from baby_first_steps_medallion.bronze.http import ResilientHttpFetcher, SourceRateLimiter
from baby_first_steps_medallion.bronze.profiles import QUERY_PROFILES
from baby_first_steps_medallion.bronze.service import BronzeIngestor
from baby_first_steps_medallion.config import Settings

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "runtime-data",
        artifacts_dir=tmp_path / "artifacts",
        log_level="INFO",
        hf_home=tmp_path / "hf",
    )


def _adapter(
    adapter_type: type[EuropePmcAdapter] | type[OpenAlexAdapter] | type[PubMedAdapter],
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[EuropePmcAdapter | OpenAlexAdapter | PubMedAdapter, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = ResilientHttpFetcher(
        client=client,
        limiter=SourceRateLimiter(requests_per_second=1_000_000_000),
        sleep=lambda _: None,
        jitter=lambda: 0.0,
    )
    return adapter_type(fetcher), client


def test_acquisition_queries_are_bounded_and_openalex_is_bilingual() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - not fetched
        return httpx.Response(200, request=request)

    profile = QUERY_PROFILES["motor_sensory"]
    europe, europe_client = _adapter(EuropePmcAdapter, handler)
    openalex, openalex_client = _adapter(OpenAlexAdapter, handler)
    try:
        europe_requests = europe.build_requests(profile, 5)
        openalex_requests = openalex.build_requests(profile, 5)
    finally:
        europe_client.close()
        openalex_client.close()

    assert len(europe_requests) == 1
    assert europe_requests[0].source_query == profile.terms[2]
    assert [request.request_kind for request in openalex_requests] == ["search_es", "search_en"]
    assert [request.params["filter"] for request in openalex_requests] == [
        "language:es",
        "language:en",
    ]
    assert sum(int(request.params["per-page"]) for request in openalex_requests) == 5


def test_resume_retries_failed_request_and_keeps_manifest_consistent(tmp_path: Path) -> None:
    batch_id = "20260802T120000000000Z-aaaaaa"

    def failure_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, request=request)

    first_adapter, first_client = _adapter(EuropePmcAdapter, failure_handler)
    try:
        failed = BronzeIngestor(
            _settings(tmp_path),
            {"europe_pmc": first_adapter},
            batch_id_factory=lambda: batch_id,
        ).ingest(sources="europe_pmc", profiles="motor_sensory", max_records_per_source=1)
    finally:
        first_client.close()

    assert failed["success_count"] == 0
    assert failed["failure_count"] == 1
    assert (tmp_path / "runtime-data" / "bronze" / batch_id / "failures.jsonl").is_file()

    payload = (FIXTURES / "bronze-pretty-response.json").read_bytes()

    def success_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"Content-Type": "application/json"},
            request=request,
        )

    second_adapter, second_client = _adapter(EuropePmcAdapter, success_handler)
    try:
        resumed = BronzeIngestor(
            _settings(tmp_path), {"europe_pmc": second_adapter}
        ).ingest(resume=batch_id)
    finally:
        second_client.close()

    batch_dir = tmp_path / "runtime-data" / "bronze" / batch_id
    manifest = json.loads((batch_dir / "manifest.json").read_text(encoding="utf-8"))
    response = manifest["responses"][0]
    assert resumed["success_count"] == 1
    assert resumed["failure_count"] == 0
    assert response["source_type"] == "real"
    assert (batch_dir / response["file"]).read_bytes() == payload
    assert response["byte_count"] == len(payload)
    assert response["sha256"] in (batch_dir / "checksums.sha256").read_text(encoding="ascii")
    assert (batch_dir / "failures.jsonl").read_bytes() == b""


def test_pubmed_stores_search_json_and_fetch_xml_without_parsing_documents(tmp_path: Path) -> None:
    search_payload = (FIXTURES / "pubmed-esearch-history.json").read_bytes()
    xml_payload = (FIXTURES / "bronze-response.xml").read_bytes()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if "esearch.fcgi" in str(request.url):
            return httpx.Response(200, content=search_payload, request=request)
        return httpx.Response(200, content=xml_payload, request=request)

    adapter, client = _adapter(PubMedAdapter, handler)
    try:
        manifest = BronzeIngestor(
            _settings(tmp_path),
            {"pubmed": adapter},
            batch_id_factory=lambda: "20260802T120000000001Z-bbbbbb",
        ).ingest(sources="pubmed", profiles="motor_sensory", max_records_per_source=1)
    finally:
        client.close()

    files = {entry["file"]: entry for entry in manifest["responses"]}
    batch_dir = tmp_path / "runtime-data" / "bronze" / manifest["batch_id"]
    assert calls == 2
    assert (batch_dir / "pubmed" / "response_0001.json").read_bytes() == search_payload
    assert (batch_dir / "pubmed" / "response_0002.xml").read_bytes() == xml_payload
    assert len(files) == 2
