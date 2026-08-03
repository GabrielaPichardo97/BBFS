"""Orchestrate immutable Bronze batches without parsing source records."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, cast
from urllib.parse import urlencode

import httpx

from baby_first_steps_medallion import __version__
from baby_first_steps_medallion.bronze.adapters import (
    AdapterResponseError,
    EuropePmcAdapter,
    OpenAlexAdapter,
    PubMedAdapter,
)
from baby_first_steps_medallion.bronze.http import (
    FetchError,
    ResilientHttpFetcher,
    SourceRateLimiter,
    default_http_client,
)
from baby_first_steps_medallion.bronze.models import QueryProfile, RequestSpec, SourceAdapter
from baby_first_steps_medallion.bronze.profiles import select_profiles
from baby_first_steps_medallion.bronze.storage import (
    BronzeBatchStore,
    new_batch_id,
    sha256_bytes,
    utc_timestamp,
)
from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.safety import assert_real_source_type

DEFAULT_SOURCE_NAMES = ("pubmed", "europe_pmc", "openalex")


class BronzeUsageError(ValueError):
    """CLI-provided acquisition inputs cannot produce a reproducible batch."""


class BatchIntegrityError(RuntimeError):
    """A resumed manifest refers to missing or modified immutable bytes."""


def build_default_adapters() -> tuple[dict[str, SourceAdapter], httpx.Client]:
    """Build the three anonymous-source adapters with independent rate limiters."""
    client = default_http_client()
    adapters: dict[str, SourceAdapter] = {
        "pubmed": PubMedAdapter(
            ResilientHttpFetcher(client=client, limiter=SourceRateLimiter(requests_per_second=3.0))
        ),
        "europe_pmc": EuropePmcAdapter(
            ResilientHttpFetcher(client=client, limiter=SourceRateLimiter(requests_per_second=2.0))
        ),
        "openalex": OpenAlexAdapter(
            ResilientHttpFetcher(client=client, limiter=SourceRateLimiter(requests_per_second=2.0))
        ),
    }
    return adapters, client


def _select_sources(value: str | None, adapters: Mapping[str, SourceAdapter]) -> list[str]:
    names = (
        list(DEFAULT_SOURCE_NAMES)
        if value is None
        else [item.strip() for item in value.split(",")]
    )
    names = [name for name in names if name]
    unknown = sorted(set(names) - set(adapters))
    if unknown:
        raise BronzeUsageError(f"Fuentes no reconocidas: {', '.join(unknown)}")
    if not names:
        raise BronzeUsageError("Debe seleccionarse al menos una fuente.")
    return names


def _profile_limits(profiles: Sequence[QueryProfile], total: int) -> list[tuple[QueryProfile, int]]:
    if total < 1:
        raise BronzeUsageError("max_records_per_source debe ser mayor que cero.")
    base, remainder = divmod(total, len(profiles))
    return [
        (profile, base + (1 if index < remainder else 0))
        for index, profile in enumerate(profiles)
        if base + (1 if index < remainder else 0) > 0
    ]


class BronzeIngestor:
    """Persist real HTTP response bytes in a resumable, source-separated batch."""

    def __init__(
        self,
        settings: Settings,
        adapters: Mapping[str, SourceAdapter],
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        batch_id_factory: Callable[[], str] = new_batch_id,
    ) -> None:
        self._settings = settings
        self._adapters = dict(adapters)
        self._now = now
        self._batch_id_factory = batch_id_factory

    def ingest(
        self,
        *,
        sources: str | None = None,
        profiles: str | None = None,
        max_records_per_source: int | None = None,
        resume: str | None = None,
    ) -> dict[str, Any]:
        """Run one small Bronze batch or retry unfinished requests in a prior batch."""
        if resume:
            store = BronzeBatchStore.resume(self._settings.data_dir / "bronze", resume)
            manifest = store.load_manifest()
            source_names = self._resume_sources(sources, manifest)
            profile_objects = self._resume_profiles(profiles, manifest)
            max_records = self._resume_max_records(max_records_per_source, manifest)
            manifest["resumed_at"] = utc_timestamp(self._now())
        else:
            source_names = _select_sources(sources, self._adapters)
            try:
                profile_objects = select_profiles(profiles)
            except ValueError as error:
                raise BronzeUsageError(str(error)) from error
            max_records = max_records_per_source or 20
            if max_records < 1:
                raise BronzeUsageError("max_records_per_source debe ser mayor que cero.")
            batch_id = self._batch_id_factory()
            store = BronzeBatchStore.create(self._settings.data_dir / "bronze", batch_id)
            manifest = {
                "batch_id": batch_id,
                "started_at": utc_timestamp(self._now()),
                "completed_at": None,
                "pipeline_version": __version__,
                "query_profiles": [profile.profile_id for profile in profile_objects],
                "sources": source_names,
                "max_records_per_source": max_records,
                "request_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_bytes": 0,
                "responses": [],
                "failures": [],
            }
            self._persist_state(store, manifest)

        for source_name in source_names:
            adapter = self._adapters[source_name]
            for profile, allocation in _profile_limits(profile_objects, max_records):
                for request in adapter.build_requests(profile, allocation):
                    payload = self._process_request(store, manifest, adapter, request)
                    if payload is None:
                        continue
                    try:
                        follow_ups = adapter.build_follow_up_requests(request, payload, allocation)
                    except AdapterResponseError as error:
                        self._record_follow_up_failure(manifest, adapter, request, error)
                        self._persist_state(store, manifest)
                        continue
                    for follow_up in follow_ups:
                        self._process_request(store, manifest, adapter, follow_up)

        manifest["completed_at"] = utc_timestamp(self._now())
        manifest["status"] = "completed" if not manifest["failures"] else "completed_with_failures"
        self._persist_state(store, manifest)
        return manifest

    def _resume_sources(self, provided: str | None, manifest: dict[str, Any]) -> list[str]:
        documented = ",".join(str(item) for item in manifest["sources"])
        if provided is not None and provided != documented:
            raise BronzeUsageError("--resume debe conservar las fuentes originales del batch.")
        return _select_sources(documented, self._adapters)

    def _resume_profiles(
        self, provided: str | None, manifest: dict[str, Any]
    ) -> list[QueryProfile]:
        documented = ",".join(str(item) for item in manifest["query_profiles"])
        if provided is not None and provided != documented:
            raise BronzeUsageError("--resume debe conservar los perfiles originales del batch.")
        try:
            return select_profiles(documented)
        except ValueError as error:
            raise BronzeUsageError(str(error)) from error

    def _resume_max_records(self, provided: int | None, manifest: dict[str, Any]) -> int:
        documented = int(manifest["max_records_per_source"])
        if provided is not None and provided != documented:
            raise BronzeUsageError("--resume debe conservar max_records_per_source del batch.")
        return documented

    def _process_request(
        self,
        store: BronzeBatchStore,
        manifest: dict[str, Any],
        adapter: SourceAdapter,
        request: RequestSpec,
    ) -> bytes | None:
        existing = self._find_response(manifest, request.request_key)
        if existing is not None:
            path = store.batch_dir / str(existing["file"])
            if not path.is_file():
                raise BatchIntegrityError(f"Payload faltante durante reanudación: {path}")
            payload = path.read_bytes()
            if sha256_bytes(payload) != existing["sha256"]:
                raise BatchIntegrityError(
                    f"Hash de payload incompatible durante reanudación: {path}"
                )
            return payload

        try:
            fetched = adapter.fetch(request)
        except FetchError as error:
            self._record_failure(manifest, request, error)
            self._persist_state(store, manifest)
            return None

        description = adapter.describe_response(fetched)
        sequence = self._next_sequence(manifest, request.source_name)
        payload = fetched.response.content
        write_result = store.write_response(
            request.source_name, sequence, description.response_extension, payload
        )
        response_record = {
            "request_key": request.request_key,
            "source_name": request.source_name,
            "source_type": "real",
            "query_profile": request.profile_id,
            "source_query": request.source_query,
            "request_kind": request.request_kind,
            "source_record_hint": adapter.source_record_hint(),
            "file": store.relative_to_batch(write_result.path),
            "archivo": store.relative_to_batch(write_result.path),
            "endpoint": request.endpoint,
            "parameters": request.params,
            "request_url": f"{request.endpoint}?{urlencode(request.params)}",
            "status_code": fetched.response.status_code,
            "content_type": description.content_type,
            "fetched_at": fetched.fetched_at,
            "elapsed_ms": fetched.elapsed_ms,
            "retry_count": fetched.retry_count,
            "sha256": write_result.sha256,
            "byte_count": write_result.byte_count,
            "sequence": sequence,
        }
        assert_real_source_type("real", context="bronze-manifest")
        metadata_path = store.write_request_metadata(request.source_name, sequence, response_record)
        response_record["metadata_file"] = store.relative_to_batch(metadata_path)
        self._upsert_response(manifest, response_record)
        self._persist_state(store, manifest)
        return payload

    def _record_failure(
        self, manifest: dict[str, Any], request: RequestSpec, error: FetchError
    ) -> None:
        failure = {
            "request_key": request.request_key,
            "source_name": request.source_name,
            "source_type": "real",
            "query_profile": request.profile_id,
            "source_query": request.source_query,
            "request_kind": request.request_kind,
            "endpoint": request.endpoint,
            "parameters": request.params,
            "status_code": error.status_code,
            "retry_count": error.retry_count,
            "error": str(error),
            "failed_at": utc_timestamp(self._now()),
        }
        assert_real_source_type("real", context="bronze-failures")
        self._upsert_failure(manifest, failure)

    def _record_follow_up_failure(
        self,
        manifest: dict[str, Any],
        adapter: SourceAdapter,
        request: RequestSpec,
        error: AdapterResponseError,
    ) -> None:
        failure = {
            "request_key": f"{request.source_name}:{request.profile_id}:follow_up",
            "source_name": request.source_name,
            "source_type": "real",
            "query_profile": request.profile_id,
            "source_query": request.source_query,
            "request_kind": "follow_up",
            "endpoint": request.endpoint,
            "parameters": request.params,
            "source_record_hint": adapter.source_record_hint(),
            "status_code": None,
            "retry_count": 0,
            "error": str(error),
            "failed_at": utc_timestamp(self._now()),
        }
        assert_real_source_type("real", context="bronze-failures")
        self._upsert_failure(manifest, failure)

    @staticmethod
    def _find_response(manifest: dict[str, Any], request_key: str) -> dict[str, Any] | None:
        for response in manifest["responses"]:
            if response["request_key"] == request_key:
                return cast(dict[str, Any], response)
        return None

    @staticmethod
    def _next_sequence(manifest: dict[str, Any], source_name: str) -> int:
        sequences = [
            int(response["sequence"])
            for response in manifest["responses"]
            if response["source_name"] == source_name
        ]
        return max(sequences, default=0) + 1

    @staticmethod
    def _upsert_response(manifest: dict[str, Any], response: dict[str, Any]) -> None:
        manifest["responses"] = [
            item for item in manifest["responses"] if item["request_key"] != response["request_key"]
        ]
        manifest["failures"] = [
            item for item in manifest["failures"] if item["request_key"] != response["request_key"]
        ]
        manifest["responses"].append(response)

    @staticmethod
    def _upsert_failure(manifest: dict[str, Any], failure: dict[str, Any]) -> None:
        manifest["failures"] = [
            item for item in manifest["failures"] if item["request_key"] != failure["request_key"]
        ]
        manifest["failures"].append(failure)

    @staticmethod
    def _persist_state(store: BronzeBatchStore, manifest: dict[str, Any]) -> None:
        manifest["request_count"] = len(manifest["responses"]) + len(manifest["failures"])
        manifest["success_count"] = len(manifest["responses"])
        manifest["failure_count"] = len(manifest["failures"])
        manifest["total_bytes"] = sum(
            int(response["byte_count"]) for response in manifest["responses"]
        )
        store.write_manifest(manifest)
        store.write_checksums(manifest["responses"])
        store.write_failures(manifest["failures"])
