"""Incremental CPU embeddings, FAISS persistence, Spanish search, and acceptance evidence."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import numpy as np
from numpy.typing import NDArray

from baby_first_steps_medallion.config import Settings
from baby_first_steps_medallion.evidence.safety import assert_real_source_type
from baby_first_steps_medallion.gold.embeddings import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_REVISION,
    MultilingualE5Embedder,
)
from baby_first_steps_medallion.gold.models import Embedder, GoldBuildResult, SearchResult
from baby_first_steps_medallion.silver.persistence import SilverRepository

INDEX_STATE_PATH = "data/gold/resources.faiss"
ACCEPTANCE_QUERIES = (
    "actividades sensoriales con diferentes texturas para un bebé",
    "materiales cotidianos para desarrollar la motricidad fina",
    "juegos entre cuidadores y bebés para estimular el lenguaje",
    "lectura compartida durante los primeros años de vida",
    "música y movimiento para mejorar la coordinación infantil",
    "actividades para fortalecer la interacción entre padres e hijos",
)


class GoldError(RuntimeError):
    """Gold cannot safely create or query the local semantic index."""


@dataclass(frozen=True)
class _SilverDocument:
    canonical_id: str
    content_hash: str
    title: str
    abstract: str
    keywords: tuple[str, ...]
    subject_terms: tuple[str, ...]
    language: str
    publication_date: str | None
    resource_url: str
    observed_sources: tuple[str, ...]

    @property
    def passage(self) -> str:
        """Build the documented E5 passage text without translating or enriching it."""
        return (
            f"passage: {self.title}. {self.abstract}. "
            f"Keywords: {', '.join(self.keywords)}. "
            f"Subjects: {', '.join(self.subject_terms)}."
        )


@dataclass(frozen=True)
class _StoredEmbedding:
    canonical_id: str
    vector_id: int
    model_name: str
    model_revision: str
    embedding_dimension: int
    content_hash: str
    vector_blob: bytes


@dataclass(frozen=True)
class _IndexState:
    index_path: str
    vector_count: int
    model_name: str
    model_revision: str
    index_sha256: str


class GoldRepository:
    """Build and search a local FAISS index from real, valid Silver resources only."""

    def __init__(
        self,
        settings: Settings,
        *,
        embedder: Embedder | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        index_writer: Callable[[Any, str], None] | None = None,
    ) -> None:
        self._settings = settings
        self._embedder_instance = embedder
        self._now = now
        self._index_writer = index_writer

    @property
    def db_path(self) -> Path:
        """Return the shared local DuckDB database path."""
        return self._settings.data_dir / "baby_first_steps.duckdb"

    @property
    def index_path(self) -> Path:
        """Return the ignored, persistent FAISS index location."""
        return self._settings.data_dir / "gold" / "resources.faiss"

    @property
    def acceptance_artifact_path(self) -> Path:
        """Return the ignored generated evidence location."""
        return self._settings.artifacts_dir / "gold" / "acceptance-search.json"

    def build(self, *, batch_size: int = 32) -> GoldBuildResult:
        """Incrementally embed real Silver documents and atomically persist FAISS."""
        if batch_size < 1:
            raise GoldError("batch_size debe ser mayor que cero.")
        SilverRepository(self._settings).migrate()
        connection = self._connect()
        try:
            self._assert_real_silver(connection)
            documents = self._load_documents(connection)
            if not documents:
                raise GoldError("No hay recursos Silver válidos para indexar.")
            embedder = self._embedder()
            existing = self._load_embeddings(connection)
            state = self._load_index_state(connection)
            current_ids = {document.canonical_id for document in documents}
            stale_ids = sorted(set(existing) - current_ids)
            index_ready = self._index_ready(state, existing, embedder)
            unchanged_ids = {
                document.canonical_id
                for document in documents
                if self._embedding_matches(existing.get(document.canonical_id), document, embedder)
            }
            pending_documents = [
                document for document in documents if document.canonical_id not in unchanged_ids
            ]
            if index_ready and not pending_documents and not stale_ids:
                return GoldBuildResult(
                    model_name=embedder.model_name,
                    model_revision=embedder.model_revision,
                    embedding_dimension=self._existing_dimension(existing),
                    vector_count=len(existing),
                    embeddings_inserted=0,
                    embeddings_updated=0,
                    embeddings_noop=len(documents),
                    embeddings_deleted=0,
                    index_path=str(self.index_path),
                    index_sha256=state.index_sha256 if state is not None else None,
                )

            vectors_by_id: dict[str, NDArray[np.float32]] = {}
            if not index_ready:
                reusable = [
                    document for document in documents if document.canonical_id in unchanged_ids
                ]
                for document in reusable:
                    stored = existing[document.canonical_id]
                    vectors_by_id[document.canonical_id] = self._vector_from_blob(stored)
                index: Any | None = None
            else:
                index = self._read_index()

            if pending_documents:
                vectors_by_id.update(
                    self._encode_documents(embedder, pending_documents, batch_size)
                )
            dimension = self._embedding_dimension(vectors_by_id, index)
            if not index_ready:
                index = self._new_index(dimension)
                all_vectors = np.ascontiguousarray(
                    np.vstack(
                        [vectors_by_id[document.canonical_id] for document in documents]
                    ),
                    dtype=np.float32,
                )
                all_ids = np.asarray(
                    [
                        self._vector_id_for(document.canonical_id, existing)
                        for document in documents
                    ],
                    dtype=np.int64,
                )
                index.add_with_ids(all_vectors, all_ids)
            else:
                if index is None:
                    raise GoldError("El índice Gold no se pudo cargar.")
                removed_vector_ids = [
                    existing[canonical_id].vector_id for canonical_id in stale_ids
                ]
                removed_vector_ids.extend(
                    existing[document.canonical_id].vector_id
                    for document in pending_documents
                    if document.canonical_id in existing
                )
                if removed_vector_ids:
                    index.remove_ids(np.asarray(removed_vector_ids, dtype=np.int64))
                if pending_documents:
                    pending_vectors = np.ascontiguousarray(
                        np.vstack(
                            [vectors_by_id[document.canonical_id] for document in pending_documents]
                        ),
                        dtype=np.float32,
                    )
                    pending_ids = np.asarray(
                        [
                            self._vector_id_for(document.canonical_id, existing)
                            for document in pending_documents
                        ],
                        dtype=np.int64,
                    )
                    index.add_with_ids(pending_vectors, pending_ids)

            inserted = sum(document.canonical_id not in existing for document in pending_documents)
            updated = len(pending_documents) - inserted
            noops = len(documents) - len(pending_documents)
            index_sha256 = self._write_index_atomic(index)
            now = self._now()
            try:
                connection.execute("BEGIN TRANSACTION")
                if stale_ids:
                    placeholders = ", ".join("?" for _ in stale_ids)
                    connection.execute(
                        f"DELETE FROM gold_embeddings WHERE canonical_id IN ({placeholders})",
                        stale_ids,
                    )
                for document in pending_documents:
                    vector_id = self._vector_id_for(document.canonical_id, existing)
                    vector = vectors_by_id[document.canonical_id]
                    if document.canonical_id in existing:
                        connection.execute(
                            """
                            UPDATE gold_embeddings
                            SET vector_id = ?, model_name = ?, model_revision = ?,
                                embedding_dimension = ?, content_hash = ?, vector_blob = ?,
                                embedded_at = ?, source_type = 'real'
                            WHERE canonical_id = ?
                            """,
                            [
                                vector_id,
                                embedder.model_name,
                                embedder.model_revision,
                                dimension,
                                document.content_hash,
                                vector.tobytes(),
                                now,
                                document.canonical_id,
                            ],
                        )
                    else:
                        connection.execute(
                            """
                            INSERT INTO gold_embeddings (
                                canonical_id, vector_id, model_name, model_revision,
                                embedding_dimension, content_hash, vector_blob, embedded_at,
                                source_type
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'real')
                            """,
                            [
                                document.canonical_id,
                                vector_id,
                                embedder.model_name,
                                embedder.model_revision,
                                dimension,
                                document.content_hash,
                                vector.tobytes(),
                                now,
                            ],
                        )
                connection.execute(
                    """
                    INSERT INTO gold_index_state (
                        index_path, vector_count, model_name, model_revision, updated_at,
                        index_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT (index_path) DO UPDATE SET
                        vector_count = excluded.vector_count,
                        model_name = excluded.model_name,
                        model_revision = excluded.model_revision,
                        updated_at = excluded.updated_at,
                        index_sha256 = excluded.index_sha256
                    """,
                    [
                        INDEX_STATE_PATH,
                        len(documents),
                        embedder.model_name,
                        embedder.model_revision,
                        now,
                        index_sha256,
                    ],
                )
                connection.execute("COMMIT")
            except Exception as error:
                connection.execute("ROLLBACK")
                raise GoldError("No se pudo registrar el estado Gold en DuckDB.") from error
            return GoldBuildResult(
                model_name=embedder.model_name,
                model_revision=embedder.model_revision,
                embedding_dimension=dimension,
                vector_count=len(documents),
                embeddings_inserted=inserted,
                embeddings_updated=updated,
                embeddings_noop=noops,
                embeddings_deleted=len(stale_ids),
                index_path=str(self.index_path),
                index_sha256=index_sha256,
            )
        finally:
            connection.close()

    def semantic_search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Return ranked Spanish-query matches without translating any document text."""
        cleaned_query = " ".join(query.split())
        if not cleaned_query:
            raise GoldError("La consulta no puede estar vacía.")
        if top_k < 1:
            raise GoldError("top_k debe ser mayor que cero.")
        SilverRepository(self._settings).migrate()
        connection = self._connect()
        try:
            self._assert_real_silver(connection)
            self._assert_real_gold(connection)
            state = self._load_index_state(connection)
            if state is None or not self.index_path.is_file():
                raise GoldError(
                    "No existe un índice Gold; ejecute `baby-first-steps gold` primero."
                )
            embedder = self._embedder()
            if (
                state.model_name != embedder.model_name
                or state.model_revision != embedder.model_revision
            ):
                raise GoldError(
                    "El índice Gold usa otro modelo o revisión; ejecútelo de nuevo."
                )
            if state.index_sha256 != self._sha256_file(self.index_path):
                raise GoldError(
                    "El checksum del índice Gold no coincide; ejecútelo de nuevo."
                )
            query_vector = self._normalize_vectors(
                embedder.encode([f"query: {cleaned_query}"], batch_size=1)
            )
            index = self._read_index()
            if int(index.ntotal) != state.vector_count:
                raise GoldError(
                    "El índice y la metadata Gold no son consistentes; ejecútelo de nuevo."
                )
            scores, vector_ids = index.search(query_vector, min(top_k, int(index.ntotal)))
            results: list[SearchResult] = []
            for score, vector_id in zip(scores[0], vector_ids[0], strict=True):
                if int(vector_id) < 0:
                    continue
                row = connection.execute(
                    """
                    SELECT resource.canonical_id, resource.title, resource.abstract,
                           resource.language,
                           resource.publication_date, resource.resource_url,
                           resource.observed_sources_json
                    FROM gold_embeddings AS embedding
                    JOIN silver_resources AS resource
                      ON resource.canonical_id = embedding.canonical_id
                    WHERE embedding.vector_id = ?
                      AND embedding.source_type = 'real'
                      AND resource.source_type = 'real'
                    """,
                    [int(vector_id)],
                ).fetchone()
                if row is None:
                    raise GoldError(
                        "El índice y la metadata Gold no son consistentes; ejecútelo de nuevo."
                    )
                results.append(
                    SearchResult(
                        rank=len(results) + 1,
                        canonical_id=str(row[0]),
                        title=str(row[1]),
                        score=float(score),
                        abstract_snippet=self._snippet(str(row[2])),
                        language=str(row[3]),
                        publication_date=row[4].isoformat() if row[4] is not None else None,
                        resource_url=str(row[5]),
                        observed_sources=tuple(_json_string_list(row[6])),
                    )
                )
            return results
        finally:
            connection.close()

    def write_acceptance_evidence(self, *, top_k: int = 5) -> Path:
        """Generate review-ready Spanish-query evidence without auto-scoring relevance."""
        payload = {
            "generated_at": self._now().isoformat(),
            "query_language": "es",
            "top_k": top_k,
            "queries": [
                {
                    "query": query,
                    "results": [result.as_dict() for result in self.semantic_search(query, top_k)],
                    "manual_coherence_review": {
                        "status": "pending_human_review",
                        "check": "Revisar título, fragmento, idioma y fuente frente a la consulta.",
                        "automated_relevance_metric": None,
                    },
                }
                for query in ACCEPTANCE_QUERIES
            ],
        }
        _write_json_atomic(self.acceptance_artifact_path, payload)
        return self.acceptance_artifact_path

    def _embedder(self) -> Embedder:
        if self._embedder_instance is None:
            self._embedder_instance = MultilingualE5Embedder(
                model_name=DEFAULT_MODEL_NAME,
                model_revision=DEFAULT_MODEL_REVISION,
                cache_folder=self._settings.hf_home,
            )
        return self._embedder_instance

    def _connect(self) -> duckdb.DuckDBPyConnection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.db_path))

    @staticmethod
    def _assert_real_silver(connection: duckdb.DuckDBPyConnection) -> None:
        row = connection.execute(
            "SELECT COUNT(*) FROM silver_resources WHERE source_type <> 'real'"
        ).fetchone()
        if row is not None and int(row[0]):
            assert_real_source_type("synthetic", context="gold-input")

    @staticmethod
    def _assert_real_gold(connection: duckdb.DuckDBPyConnection) -> None:
        row = connection.execute(
            "SELECT COUNT(*) FROM gold_embeddings WHERE source_type <> 'real'"
        ).fetchone()
        if row is not None and int(row[0]):
            assert_real_source_type("synthetic", context="gold-storage")

    @staticmethod
    def _load_documents(connection: duckdb.DuckDBPyConnection) -> list[_SilverDocument]:
        rows = connection.execute(
            """
            SELECT canonical_id, content_hash, title, abstract, keywords_json, subject_terms_json,
                   language, publication_date, resource_url, observed_sources_json
            FROM silver_resources
            WHERE source_type = 'real'
            ORDER BY canonical_id
            """
        ).fetchall()
        documents: list[_SilverDocument] = []
        for row in rows:
            documents.append(
                _SilverDocument(
                    canonical_id=str(row[0]),
                    content_hash=str(row[1]),
                    title=str(row[2]),
                    abstract=str(row[3]),
                    keywords=tuple(_json_string_list(row[4])),
                    subject_terms=tuple(_json_string_list(row[5])),
                    language=str(row[6]),
                    publication_date=row[7].isoformat() if row[7] is not None else None,
                    resource_url=str(row[8]),
                    observed_sources=tuple(_json_string_list(row[9])),
                )
            )
        return documents

    @staticmethod
    def _load_embeddings(connection: duckdb.DuckDBPyConnection) -> dict[str, _StoredEmbedding]:
        rows = connection.execute(
            """
            SELECT canonical_id, vector_id, model_name, model_revision, embedding_dimension,
                   content_hash, vector_blob
            FROM gold_embeddings
            WHERE source_type = 'real'
            """
        ).fetchall()
        return {
            str(row[0]): _StoredEmbedding(
                canonical_id=str(row[0]),
                vector_id=int(row[1]),
                model_name=str(row[2]),
                model_revision=str(row[3]),
                embedding_dimension=int(row[4]),
                content_hash=str(row[5]),
                vector_blob=bytes(row[6]),
            )
            for row in rows
        }

    @staticmethod
    def _load_index_state(connection: duckdb.DuckDBPyConnection) -> _IndexState | None:
        row = connection.execute(
            """
            SELECT index_path, vector_count, model_name, model_revision, index_sha256
            FROM gold_index_state
            WHERE index_path = ?
            """,
            [INDEX_STATE_PATH],
        ).fetchone()
        if row is None:
            return None
        return _IndexState(
            index_path=str(row[0]),
            vector_count=int(row[1]),
            model_name=str(row[2]),
            model_revision=str(row[3]),
            index_sha256=str(row[4]),
        )

    def _index_ready(
        self,
        state: _IndexState | None,
        embeddings: dict[str, _StoredEmbedding],
        embedder: Embedder,
    ) -> bool:
        return (
            state is not None
            and self.index_path.is_file()
            and state.index_path == INDEX_STATE_PATH
            and state.vector_count == len(embeddings)
            and state.model_name == embedder.model_name
            and state.model_revision == embedder.model_revision
            and state.index_sha256 == self._sha256_file(self.index_path)
        )

    @staticmethod
    def _embedding_matches(
        stored: _StoredEmbedding | None, document: _SilverDocument, embedder: Embedder
    ) -> bool:
        return (
            stored is not None
            and stored.content_hash == document.content_hash
            and stored.model_name == embedder.model_name
            and stored.model_revision == embedder.model_revision
        )

    def _encode_documents(
        self,
        embedder: Embedder,
        documents: Sequence[_SilverDocument],
        batch_size: int,
    ) -> dict[str, NDArray[np.float32]]:
        vectors = self._normalize_vectors(
            embedder.encode([item.passage for item in documents], batch_size=batch_size)
        )
        if vectors.shape[0] != len(documents):
            raise GoldError("El embedder no devolvió un vector por documento.")
        return {
            document.canonical_id: vectors[index]
            for index, document in enumerate(documents)
        }

    @staticmethod
    def _normalize_vectors(vectors: NDArray[np.float32]) -> NDArray[np.float32]:
        array = np.asarray(vectors, dtype=np.float32)
        if array.ndim == 1:
            array = array.reshape(1, -1)
        if array.ndim != 2 or array.shape[1] == 0:
            raise GoldError("El embedder devolvió una matriz de vectores inválida.")
        norms = np.linalg.norm(array, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise GoldError("El embedder devolvió un vector de norma cero.")
        return np.ascontiguousarray(array / norms, dtype=np.float32)

    @staticmethod
    def _vector_from_blob(stored: _StoredEmbedding) -> NDArray[np.float32]:
        vector = np.frombuffer(stored.vector_blob, dtype=np.float32)
        if vector.size != stored.embedding_dimension:
            raise GoldError("El vector Gold almacenado no coincide con su metadata.")
        return np.ascontiguousarray(vector, dtype=np.float32)

    @staticmethod
    def _existing_dimension(embeddings: dict[str, _StoredEmbedding]) -> int:
        if not embeddings:
            return 0
        return next(iter(embeddings.values())).embedding_dimension

    @staticmethod
    def _embedding_dimension(
        vectors_by_id: dict[str, NDArray[np.float32]], index: Any | None
    ) -> int:
        if vectors_by_id:
            dimensions = {int(vector.shape[0]) for vector in vectors_by_id.values()}
            if len(dimensions) != 1:
                raise GoldError("El embedder devolvió dimensiones inconsistentes.")
            return dimensions.pop()
        if index is None:
            raise GoldError("No se pudo detectar la dimensión de embedding.")
        dimension = int(index.d)
        if dimension < 1:
            raise GoldError("No se pudo detectar la dimensión de embedding.")
        return dimension

    @staticmethod
    def _vector_id_for(canonical_id: str, existing: dict[str, _StoredEmbedding]) -> int:
        stored = existing.get(canonical_id)
        if stored is not None:
            return stored.vector_id
        used_ids = {item.vector_id for item in existing.values()}
        nonce = 0
        while True:
            material = canonical_id if nonce == 0 else f"{canonical_id}:{nonce}"
            candidate = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
            candidate &= (1 << 63) - 1
            if candidate and candidate not in used_ids:
                return candidate
            nonce += 1

    @staticmethod
    def _new_index(dimension: int) -> Any:
        if dimension < 1:
            raise GoldError("No se puede crear un índice sin dimensión de embedding.")
        try:
            import faiss  # type: ignore[import-untyped]
        except ImportError as error:  # pragma: no cover - exercised in the runtime image
            raise GoldError("faiss-cpu no está instalado.") from error
        return faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))

    def _read_index(self) -> Any:
        try:
            import faiss
        except ImportError as error:  # pragma: no cover - exercised in the runtime image
            raise GoldError("faiss-cpu no está instalado.") from error
        try:
            return faiss.read_index(str(self.index_path))
        except RuntimeError as error:
            raise GoldError("No se pudo leer el índice FAISS Gold.") from error

    def _write_index_atomic(self, index: Any) -> str:
        """Write the FAISS file through a sibling temporary path and atomically replace it."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.index_path.with_name(f".{self.index_path.name}.{uuid4().hex}.tmp")
        try:
            if self._index_writer is None:
                try:
                    import faiss
                except ImportError as error:  # pragma: no cover - exercised in runtime image
                    raise GoldError("faiss-cpu no está instalado.") from error
                faiss.write_index(index, str(temporary_path))
            else:
                self._index_writer(index, str(temporary_path))
            os.replace(temporary_path, self.index_path)
        except (OSError, RuntimeError) as error:
            raise GoldError("No se pudo escribir el índice FAISS de forma atómica.") from error
        finally:
            if temporary_path.exists():
                temporary_path.unlink()
        return self._sha256_file(self.index_path)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _snippet(abstract: str, limit: int = 240) -> str:
        normalized = " ".join(abstract.split())
        return normalized if len(normalized) <= limit else f"{normalized[: limit - 1]}…"


def semantic_search(query: str, top_k: int = 5) -> list[SearchResult]:
    """Public local search entry point for Spanish user queries."""
    return GoldRepository(Settings.from_env()).semantic_search(query, top_k)


def _json_string_list(value: Any) -> list[str]:
    if not isinstance(value, str):
        raise GoldError("Los metadatos JSON Silver no son texto válido.")
    decoded = json.loads(value)
    if not isinstance(decoded, list) or not all(isinstance(item, str) for item in decoded):
        raise GoldError("Los metadatos JSON Silver no contienen una lista de texto válida.")
    return decoded


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    except OSError as error:
        raise GoldError("No se pudo escribir la evidencia Gold de forma atómica.") from error
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
