"""Bounded, source-local HTTP retries for Bronze acquisition."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from baby_first_steps_medallion.bronze.models import FetchedResponse, RequestSpec

RETRIABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
DEFAULT_USER_AGENT = "baby-first-steps-medallion/0.1.0 (Bronze acquisition; no API key)"


class FetchError(RuntimeError):
    """A request that exhausted retriable attempts or received a final HTTP error."""

    def __init__(self, message: str, *, status_code: int | None, retry_count: int) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_count = retry_count


class SourceRateLimiter:
    """Independent minimum-interval limiter for one source only."""

    def __init__(
        self,
        requests_per_second: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be positive")
        self._interval = 1.0 / requests_per_second
        self._clock = clock
        self._sleep = sleep
        self._next_allowed_at = 0.0

    def wait(self) -> None:
        """Wait only long enough to meet this source's last-request interval."""
        now = self._clock()
        delay = max(0.0, self._next_allowed_at - now)
        if delay:
            self._sleep(delay)
        self._next_allowed_at = max(self._next_allowed_at, self._clock()) + self._interval


def _retry_after_seconds(value: str | None, now: datetime) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return float(max(0.0, (retry_at - now).total_seconds()))


@dataclass
class ResilientHttpFetcher:
    """HTTP client with bounded retries; it never decodes response content."""

    client: httpx.Client
    limiter: SourceRateLimiter
    max_attempts: int = 3
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.monotonic
    utcnow: Callable[[], datetime] = lambda: datetime.now(UTC)
    jitter: Callable[[], float] = lambda: random.uniform(0.0, 0.25)

    def fetch(self, request: RequestSpec) -> FetchedResponse:
        """Fetch one request and retry only explicitly transient failures."""
        for attempt in range(1, self.max_attempts + 1):
            self.limiter.wait()
            started = self.clock()
            try:
                response = self.client.get(
                    request.endpoint,
                    params=request.params,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                )
            except httpx.TimeoutException as error:
                elapsed_ms = int((self.clock() - started) * 1000)
                if attempt == self.max_attempts:
                    raise FetchError(
                        f"timeout after {attempt} attempts ({elapsed_ms} ms): {error}",
                        status_code=None,
                        retry_count=attempt - 1,
                    ) from error
                self.sleep(self._backoff_seconds(attempt, retry_after=None))
                continue
            except httpx.RequestError as error:
                if attempt == self.max_attempts:
                    raise FetchError(
                        f"request error after {attempt} attempts: {error}",
                        status_code=None,
                        retry_count=attempt - 1,
                    ) from error
                self.sleep(self._backoff_seconds(attempt, retry_after=None))
                continue

            elapsed_ms = int((self.clock() - started) * 1000)
            if 200 <= response.status_code < 300:
                return FetchedResponse(
                    request=request,
                    response=response,
                    elapsed_ms=elapsed_ms,
                    retry_count=attempt - 1,
                    fetched_at=(
                        self.utcnow().astimezone(UTC).isoformat().replace("+00:00", "Z")
                    ),
                )
            if response.status_code not in RETRIABLE_STATUS_CODES:
                raise FetchError(
                    f"non-retriable HTTP status {response.status_code}",
                    status_code=response.status_code,
                    retry_count=attempt - 1,
                )
            if attempt == self.max_attempts:
                raise FetchError(
                    f"retriable HTTP status {response.status_code} exhausted {attempt} attempts",
                    status_code=response.status_code,
                    retry_count=attempt - 1,
                )
            retry_after = _retry_after_seconds(response.headers.get("Retry-After"), self.utcnow())
            self.sleep(self._backoff_seconds(attempt, retry_after=retry_after))

        raise AssertionError("fetch loop must return or raise")  # pragma: no cover

    def _backoff_seconds(self, attempt: int, *, retry_after: float | None) -> float:
        backoff = 0.5 * (2 ** (attempt - 1)) + self.jitter()
        return float(max(backoff, retry_after or 0.0))


def default_http_client() -> httpx.Client:
    """Create the bounded synchronous client used by real Bronze acquisition."""
    timeout = httpx.Timeout(timeout=15.0, connect=5.0, read=15.0, write=15.0, pool=5.0)
    return httpx.Client(timeout=timeout, follow_redirects=True)
