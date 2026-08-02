"""Production-boundary safety checks shared by future pipeline stages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping


class SyntheticProductionDataError(ValueError):
    """Raised when test-only synthetic data crosses a production boundary."""


def assert_real_source_type(source_type: str, *, context: str) -> None:
    """Reject synthetic data before it can reach production tables or evidence."""
    if source_type.strip().lower() == "synthetic":
        raise SyntheticProductionDataError(
            f"source_type='synthetic' is forbidden in production context: {context}"
        )


def assert_no_synthetic_rows(rows: Iterable[Mapping[str, object]], *, context: str) -> None:
    """Reject any synthetic row in a prospective production collection."""
    for row in rows:
        source_type = row.get("source_type")
        if isinstance(source_type, str):
            assert_real_source_type(source_type, context=context)
