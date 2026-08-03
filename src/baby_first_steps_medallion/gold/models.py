"""Public Gold-layer results and the narrow embedding interface used by the pipeline."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class Embedder(Protocol):
    """Encode already-prefixed E5 texts on CPU in bounded batches."""

    model_name: str
    model_revision: str

    def encode(self, texts: Sequence[str], *, batch_size: int) -> NDArray[np.float32]:
        """Return one embedding row per input text."""


@dataclass(frozen=True)
class SearchResult:
    """A display-safe semantic-search match; it does not expose raw Bronze payloads."""

    rank: int
    canonical_id: str
    title: str
    score: float
    abstract_snippet: str
    language: str
    publication_date: str | None
    resource_url: str
    observed_sources: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Produce JSON-safe output for the CLI and acceptance evidence."""
        document = asdict(self)
        document["observed_sources"] = list(self.observed_sources)
        return document


@dataclass(frozen=True)
class GoldBuildResult:
    """Counts and identity information from one incremental Gold build."""

    model_name: str
    model_revision: str
    embedding_dimension: int
    vector_count: int
    embeddings_inserted: int
    embeddings_updated: int
    embeddings_noop: int
    embeddings_deleted: int
    index_path: str
    index_sha256: str | None

    def as_dict(self) -> dict[str, int | str | None]:
        """Produce a JSON-safe build summary."""
        return asdict(self)
