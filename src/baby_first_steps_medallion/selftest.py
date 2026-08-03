"""Deterministic, offline container checks exposed by ``pipeline test``."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pydantic

from baby_first_steps_medallion.bronze.storage import new_batch_id, write_immutable_payload
from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.silver.persistence import SilverRepository


@dataclass(frozen=True)
class SelfTestCheck:
    """One executable offline assertion."""

    name: str
    status: str
    detail: str


def run_self_test(settings: Settings) -> list[SelfTestCheck]:
    """Exercise real storage and schema code without network or test fixtures."""
    checks: list[SelfTestCheck] = []
    checks.append(
        SelfTestCheck(
            "pydantic_v2",
            "PASS" if pydantic.VERSION.startswith("2.") else "FAIL",
            pydantic.VERSION,
        )
    )
    first_batch_id = new_batch_id()
    second_batch_id = new_batch_id()
    checks.append(
        SelfTestCheck(
            "batch_id_uniqueness",
            "PASS" if first_batch_id != second_batch_id else "FAIL",
            f"{first_batch_id} != {second_batch_id}",
        )
    )
    with TemporaryDirectory(prefix="bbfs-container-selftest-") as temporary:
        root = Path(temporary)
        marker = b"bbfs immutable-byte self-test; not a source record"
        target = root / "storage" / "marker.bin"
        stored = write_immutable_payload(target, marker)
        exact = target.read_bytes() == marker
        expected_hash = hashlib.sha256(marker).hexdigest()
        checks.append(
            SelfTestCheck(
                "immutable_byte_storage",
                "PASS" if exact and stored.sha256 == expected_hash else "FAIL",
                f"bytes={stored.byte_count}; sha256={stored.sha256}",
            )
        )
        isolated = Settings(
            root_dir=settings.root_dir,
            data_dir=root / "data",
            artifacts_dir=root / "artifacts",
            log_level=settings.log_level,
            hf_home=root / "hf",
        )
        repository = SilverRepository(isolated)
        repository.migrate()
        audit = repository.audit_duplicates()
        clean = not any(audit.as_dict().values())
        checks.append(
            SelfTestCheck(
                "silver_schema_and_guards",
                "PASS" if clean else "FAIL",
                str(audit.as_dict()),
            )
        )
    checks.append(
        SelfTestCheck(
            "required_secrets",
            "PASS" if not settings.required_secret_names else "FAIL",
            (
                "none"
                if not settings.required_secret_names
                else ",".join(settings.required_secret_names)
            ),
        )
    )
    return checks
