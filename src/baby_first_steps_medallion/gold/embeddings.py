"""CPU-only wrapper for the selected multilingual E5 embedding model."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

DEFAULT_MODEL_NAME = "intfloat/multilingual-e5-small"
DEFAULT_MODEL_REVISION = "main"


class MultilingualE5Embedder:
    """Load E5 on CPU only, keeping the Hugging Face cache outside version control."""

    def __init__(
        self,
        *,
        model_name: str = DEFAULT_MODEL_NAME,
        model_revision: str = DEFAULT_MODEL_REVISION,
        cache_folder: Path,
    ) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:  # pragma: no cover - exercised in the runtime image
            raise RuntimeError(
                "sentence-transformers no está instalado; ejecute la imagen Gold documentada."
            ) from error
        requested_revision = None if model_revision == DEFAULT_MODEL_REVISION else model_revision
        self._model = SentenceTransformer(
            model_name,
            revision=requested_revision,
            cache_folder=str(cache_folder),
            device="cpu",
            trust_remote_code=False,
        )
        self.model_name = model_name
        self.model_revision = self._resolved_revision(model_revision)

    def encode(self, texts: Sequence[str], *, batch_size: int) -> NDArray[np.float32]:
        """Encode text with no GPU selection and return float32 NumPy vectors."""
        vectors = self._model.encode(
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

    def _resolved_revision(self, fallback: str) -> str:
        """Prefer the exact commit exposed by Transformers, otherwise retain the request."""
        try:
            first_module = self._model[0]
            config = first_module.auto_model.config
            revision = getattr(config, "_commit_hash", None)
        except (AttributeError, IndexError, TypeError):
            revision = None
        return revision if isinstance(revision, str) and revision else fallback
