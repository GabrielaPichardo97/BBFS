CREATE TABLE IF NOT EXISTS gold_embeddings (
    canonical_id VARCHAR PRIMARY KEY,
    vector_id BIGINT NOT NULL UNIQUE,
    model_name VARCHAR NOT NULL,
    model_revision VARCHAR NOT NULL,
    embedding_dimension INTEGER NOT NULL,
    content_hash VARCHAR NOT NULL,
    vector_blob BLOB NOT NULL,
    embedded_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR NOT NULL CHECK (source_type = 'real')
);

CREATE TABLE IF NOT EXISTS gold_index_state (
    index_path VARCHAR PRIMARY KEY,
    vector_count BIGINT NOT NULL,
    model_name VARCHAR NOT NULL,
    model_revision VARCHAR NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    index_sha256 VARCHAR NOT NULL
);
