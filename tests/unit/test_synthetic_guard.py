from __future__ import annotations

import json
from pathlib import Path

import pytest

from baby_first_steps_medallion.evidence.safety import (
    SyntheticProductionDataError,
    assert_no_synthetic_rows,
    assert_real_source_type,
)

ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_FIXTURE = ROOT / "tests" / "fixtures" / "synthetic" / "never-ingest.json"


def test_synthetic_fixture_is_rejected_at_production_boundary() -> None:
    fixture = json.loads(SYNTHETIC_FIXTURE.read_text(encoding="utf-8"))

    with pytest.raises(SyntheticProductionDataError, match="forbidden"):
        assert_no_synthetic_rows([fixture], context="silver-table")


def test_real_source_type_is_allowed() -> None:
    assert_real_source_type("real", context="evidence")
