from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from baby_first_steps_medallion.bronze.http import (
    FetchError,
    ResilientHttpFetcher,
    SourceRateLimiter,
)
from baby_first_steps_medallion.bronze.models import RequestSpec

ROOT = Path(__file__).resolve().parents[2]
RAW_FIXTURE = (
    ROOT / "tests" / "fixtures" / "synthetic" / "bronze-pretty-response.json"
).read_bytes()


def _request() -> RequestSpec:
    return RequestSpec(
        source_name="test_source",
        profile_id="test_profile",
        request_kind="search",
        endpoint="https://example.test/search",
        params={"query": "test"},
        source_query="test",
        response_extension="json",
    )


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response], sleeps: list[float]
) -> tuple[ResilientHttpFetcher, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetcher = ResilientHttpFetcher(
        client=client,
        limiter=SourceRateLimiter(requests_per_second=1_000_000_000),
        sleep=sleeps.append,
        jitter=lambda: 0.0,
    )
    return fetcher, client


def test_429_respects_retry_after_then_recovers() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, request=request)
        return httpx.Response(200, content=RAW_FIXTURE, request=request)

    fetcher, client = _fetcher(handler, sleeps)
    try:
        result = fetcher.fetch(_request())
    finally:
        client.close()

    assert result.response.content == RAW_FIXTURE
    assert result.retry_count == 1
    assert calls == 2
    assert sleeps == [2.0]


def test_500_is_recoverable() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        status = 500 if calls == 1 else 200
        return httpx.Response(status, content=RAW_FIXTURE, request=request)

    fetcher, client = _fetcher(handler, sleeps)
    try:
        result = fetcher.fetch(_request())
    finally:
        client.close()

    assert result.retry_count == 1
    assert calls == 2
    assert sleeps == [0.5]


def test_timeout_is_retried() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("test timeout", request=request)
        return httpx.Response(200, content=RAW_FIXTURE, request=request)

    fetcher, client = _fetcher(handler, sleeps)
    try:
        result = fetcher.fetch(_request())
    finally:
        client.close()

    assert result.retry_count == 1
    assert sleeps == [0.5]


def test_non_retriable_error_stops_immediately() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, request=request)

    fetcher, client = _fetcher(handler, sleeps)
    try:
        with pytest.raises(FetchError, match="non-retriable HTTP status 400"):
            fetcher.fetch(_request())
    finally:
        client.close()

    assert sleeps == []
