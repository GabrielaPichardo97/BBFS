"""Source-native Bronze adapters for PubMed, Europe PMC and OpenAlex."""

from __future__ import annotations

import json
from collections.abc import Sequence

from baby_first_steps_medallion.bronze.http import ResilientHttpFetcher
from baby_first_steps_medallion.bronze.models import (
    FetchedResponse,
    QueryProfile,
    RequestSpec,
    ResponseDescription,
)


class AdapterResponseError(ValueError):
    """A transport envelope cannot supply the required follow-up request."""


class BaseAdapter:
    """Shared transport delegation, not a shared source payload model."""

    source_name: str

    def __init__(self, fetcher: ResilientHttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, request: RequestSpec) -> FetchedResponse:
        return self._fetcher.fetch(request)

    def describe_response(self, response: FetchedResponse) -> ResponseDescription:
        content_type = response.response.headers.get("Content-Type", "").split(";", maxsplit=1)[0]
        return ResponseDescription(
            content_type=content_type or "application/octet-stream",
            response_extension=response.request.response_extension,
        )

    def build_follow_up_requests(
        self, request: RequestSpec, payload: bytes, max_records: int
    ) -> Sequence[RequestSpec]:
        del request, payload, max_records
        return ()


class PubMedAdapter(BaseAdapter):
    """PubMed E-utilities history search followed by one XML fetch response."""

    source_name = "pubmed"
    _search_endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    _fetch_endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def build_requests(self, profile: QueryProfile, max_records: int) -> Sequence[RequestSpec]:
        source_query = "(" + " OR ".join(f'"{term}"' for term in profile.terms) + ")"
        return (
            RequestSpec(
                source_name=self.source_name,
                profile_id=profile.profile_id,
                request_kind="search",
                endpoint=self._search_endpoint,
                params={
                    "db": "pubmed",
                    "term": source_query,
                    "retmax": str(max_records),
                    "retmode": "json",
                    "usehistory": "y",
                    "sort": "relevance",
                },
                source_query=source_query,
                response_extension="json",
            ),
        )

    def build_follow_up_requests(
        self, request: RequestSpec, payload: bytes, max_records: int
    ) -> Sequence[RequestSpec]:
        if request.request_kind != "search":
            return ()
        try:
            envelope = json.loads(payload)
            search_result = envelope["esearchresult"]
            webenv = str(search_result["webenv"])
            query_key = str(search_result["querykey"])
            hit_count = int(search_result.get("count", 0))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AdapterResponseError("PubMed ESearch response lacks history metadata") from error
        if hit_count <= 0:
            return ()
        return (
            RequestSpec(
                source_name=self.source_name,
                profile_id=request.profile_id,
                request_kind="fetch",
                endpoint=self._fetch_endpoint,
                params={
                    "db": "pubmed",
                    "WebEnv": webenv,
                    "query_key": query_key,
                    "retstart": "0",
                    "retmax": str(min(max_records, hit_count)),
                    "retmode": "xml",
                },
                source_query=request.source_query,
                response_extension="xml",
            ),
        )

    def source_record_hint(self) -> str:
        return "PMID"


class EuropePmcAdapter(BaseAdapter):
    """Europe PMC JSON core search; no result extraction occurs in Bronze."""

    source_name = "europe_pmc"
    _endpoint = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def build_requests(self, profile: QueryProfile, max_records: int) -> Sequence[RequestSpec]:
        # Europe PMC ranks this concise English expansion reliably.  Joining every
        # bilingual phrase with exact-match OR produced empty result sets in the
        # independent audit, so use one documented acquisition expansion here.
        source_query = profile.terms[2]
        return (
            RequestSpec(
                source_name=self.source_name,
                profile_id=profile.profile_id,
                request_kind="search",
                endpoint=self._endpoint,
                params={
                    "query": source_query,
                    "format": "json",
                    "resultType": "core",
                    "pageSize": str(max_records),
                    "cursorMark": "*",
                },
                source_query=source_query,
                response_extension="json",
            ),
        )

    def source_record_hint(self) -> str:
        return "Europe PMC source:id"


class OpenAlexAdapter(BaseAdapter):
    """OpenAlex works search with its native full-text query syntax."""

    source_name = "openalex"
    _endpoint = "https://api.openalex.org/works"

    def build_requests(self, profile: QueryProfile, max_records: int) -> Sequence[RequestSpec]:
        # OpenAlex treats unqualified search words as AND.  Separate bounded
        # Spanish and English requests so the corpus is predictably bilingual
        # without exceeding max_records for the source.
        spanish_count = (max_records + 1) // 2
        english_count = max_records - spanish_count
        requests = [
            RequestSpec(
                source_name=self.source_name,
                profile_id=profile.profile_id,
                request_kind="search_es",
                endpoint=self._endpoint,
                params={
                    "search": profile.terms[0],
                    "filter": "language:es",
                    "per-page": str(spanish_count),
                },
                source_query=profile.terms[0],
                response_extension="json",
            )
        ]
        if english_count:
            requests.append(
                RequestSpec(
                    source_name=self.source_name,
                    profile_id=profile.profile_id,
                    request_kind="search_en",
                    endpoint=self._endpoint,
                    params={
                        "search": profile.terms[2],
                        "filter": "language:en",
                        "per-page": str(english_count),
                    },
                    source_query=profile.terms[2],
                    response_extension="json",
                )
            )
        return tuple(requests)

    def source_record_hint(self) -> str:
        return "OpenAlex work id"
