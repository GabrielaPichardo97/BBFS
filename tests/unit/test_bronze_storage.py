from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from baby_first_steps_medallion.bronze import storage
from baby_first_steps_medallion.bronze.storage import (
    PayloadCollisionError,
    new_batch_id,
    write_immutable_payload,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures" / "synthetic"


def test_json_payload_is_byte_for_byte_and_keeps_spaces(tmp_path: Path) -> None:
    payload = (FIXTURES / "bronze-pretty-response.json").read_bytes()
    target = tmp_path / "response_0001.json"

    result = write_immutable_payload(target, payload)

    assert target.read_bytes() == payload
    assert b"{  \"fixture\"" in target.read_bytes()
    assert result.byte_count == len(payload)
    assert result.reused is False


def test_xml_payload_is_byte_for_byte(tmp_path: Path) -> None:
    payload = (FIXTURES / "bronze-response.xml").read_bytes()
    target = tmp_path / "response_0001.xml"

    write_immutable_payload(target, payload)

    assert target.read_bytes() == payload


def test_existing_identical_payload_is_reused_without_overwrite(tmp_path: Path) -> None:
    payload = (FIXTURES / "bronze-pretty-response.json").read_bytes()
    target = tmp_path / "response_0001.json"
    write_immutable_payload(target, payload)

    result = write_immutable_payload(target, payload)

    assert result.reused is True
    assert target.read_bytes() == payload


def test_existing_different_payload_stops_on_hash_collision(tmp_path: Path) -> None:
    target = tmp_path / "response_0001.json"
    first = (FIXTURES / "bronze-pretty-response.json").read_bytes()
    second = (FIXTURES / "bronze-response.xml").read_bytes()
    write_immutable_payload(target, first)

    with pytest.raises(PayloadCollisionError, match="refusing to overwrite"):
        write_immutable_payload(target, second)


def test_payload_write_renames_a_complete_temporary_file_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "response_0001.json"
    observed: list[tuple[Path, Path]] = []
    original_replace = storage.os.replace

    def checked_replace(temporary: Path, destination: Path) -> None:
        assert temporary.exists()
        assert not destination.exists()
        observed.append((temporary, destination))
        original_replace(temporary, destination)

    monkeypatch.setattr(storage.os, "replace", checked_replace)

    payload = (FIXTURES / "bronze-pretty-response.json").read_bytes()
    write_immutable_payload(target, payload)

    assert observed and observed[0][1] == target
    assert target.read_bytes() == payload


def test_batch_ids_do_not_collide_inside_one_microsecond() -> None:
    moment = datetime(2026, 8, 2, 12, 0, 0, 123456, tzinfo=UTC)
    suffixes = iter(["aaaaaa", "bbbbbb"])

    first = new_batch_id(now=lambda: moment, token_hex=lambda _: next(suffixes))
    second = new_batch_id(now=lambda: moment, token_hex=lambda _: next(suffixes))

    assert first != second
    assert first.startswith("20260802T120000123456Z-")
    assert second.startswith("20260802T120000123456Z-")
