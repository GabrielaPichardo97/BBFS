"""Offline integration for an empty valid batch through Silver and Gold."""

from __future__ import annotations

import socket
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.gold.service import GoldError, GoldRepository
from baby_first_steps_medallion.silver.models import SourceName
from baby_first_steps_medallion.silver.persistence import SilverRepository
from baby_first_steps_medallion.silver.service import SilverValidationResult, SourceMetrics

ROOT = Path(__file__).resolve().parents[2]
FIXED_TIME = datetime(2020, 1, 2, tzinfo=UTC)


@dataclass
class OfflineEmbedder:
    model_name: str = "test/offline-e5"
    model_revision: str = "test-only"

    def encode(self, texts: Sequence[str], *, batch_size: int) -> np.ndarray[Any, Any]:
        del texts, batch_size
        raise AssertionError("an empty batch must not request embeddings")


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        root_dir=ROOT,
        data_dir=tmp_path / "test-runtime",
        artifacts_dir=tmp_path / "test-artifacts",
        log_level="INFO",
        hf_home=tmp_path / "test-hf-cache",
    )


def _empty_validation() -> SilverValidationResult:
    metrics: dict[SourceName, SourceMetrics] = {
        "pubmed": SourceMetrics(),
        "europe_pmc": SourceMetrics(),
        "openalex": SourceMetrics(),
    }
    return SilverValidationResult(
        batch_id="test-empty-offline-batch",
        records=(),
        quarantines=(),
        metrics_by_source=metrics,
    )


@pytest.mark.integration
def test_empty_silver_is_idempotent_and_gold_fails_clearly_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_network(*_: object, **__: object) -> None:
        raise AssertionError("network access is forbidden in integration tests")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    settings = _settings(tmp_path)
    validation = _empty_validation()
    silver = SilverRepository(settings, now=lambda: FIXED_TIME)

    first_silver = silver.persist(validation)
    second_silver = silver.persist(validation)
    gold = GoldRepository(settings, embedder=OfflineEmbedder(), now=lambda: FIXED_TIME)
    with pytest.raises(GoldError, match="No hay recursos Silver"):
        gold.build()
    audit = silver.audit_duplicates()

    assert first_silver.rows_inserted == 0
    assert second_silver.rows_inserted == 0
    assert second_silver.rows_updated == 0
    assert second_silver.rows_noop == 0
    assert audit.resource_duplicates == 0
    assert audit.quarantine_duplicates == 0
    assert audit.synthetic_rows == 0
