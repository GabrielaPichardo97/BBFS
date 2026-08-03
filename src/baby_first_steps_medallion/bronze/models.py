"""Types shared by the immutable Bronze acquisition layer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import httpx


@dataclass(frozen=True)
class QueryProfile:
    """A fixed group of internal acquisition terms."""

    profile_id: str
    terms: tuple[str, ...]


@dataclass(frozen=True)
class RequestSpec:
    """A source-native HTTP request whose response will be stored verbatim."""

    source_name: str
    profile_id: str
    request_kind: str
    endpoint: str
    params: dict[str, str]
    source_query: str
    response_extension: str

    @property
    def request_key(self) -> str:
        """Return the deterministic key used to resume this logical request."""
        return f"{self.source_name}:{self.profile_id}:{self.request_kind}"


@dataclass(frozen=True)
class ResponseDescription:
    """Storage-relevant information obtained without decoding a payload."""

    content_type: str
    response_extension: str


@dataclass(frozen=True)
class FetchedResponse:
    """A successful HTTP response and its transport metadata."""

    request: RequestSpec
    response: httpx.Response
    elapsed_ms: int
    retry_count: int
    fetched_at: str


@runtime_checkable
class SourceAdapter(Protocol):
    """Common Bronze contract while preserving source-native request formats."""

    source_name: str

    def build_requests(self, profile: QueryProfile, max_records: int) -> Sequence[RequestSpec]:
        """Build the initial source-native requests for one profile."""

    def fetch(self, request: RequestSpec) -> FetchedResponse:
        """Fetch a request with source-specific rate limiting and retries."""

    def describe_response(self, response: FetchedResponse) -> ResponseDescription:
        """Describe an opaque response for byte-preserving storage."""

    def source_record_hint(self) -> str:
        """Return a human-readable native identifier hint, never parsed records."""

    def build_follow_up_requests(
        self, request: RequestSpec, payload: bytes, max_records: int
    ) -> Sequence[RequestSpec]:
        """Build optional follow-ups from a stored transport envelope."""
