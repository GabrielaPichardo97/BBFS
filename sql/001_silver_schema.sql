CREATE TABLE IF NOT EXISTS meta_schema_version (
    version INTEGER PRIMARY KEY,
    migration_name VARCHAR NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS bronze_batches (
    batch_id VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    first_loaded_at TIMESTAMPTZ NOT NULL,
    last_loaded_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS stg_resources (
    run_id VARCHAR NOT NULL,
    stage_ordinal INTEGER NOT NULL,
    canonical_id VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    doi VARCHAR,
    pmid VARCHAR,
    openalex_id VARCHAR,
    title VARCHAR NOT NULL,
    abstract VARCHAR NOT NULL,
    language VARCHAR NOT NULL,
    publication_date DATE,
    authors_json VARCHAR NOT NULL,
    journal_or_publisher VARCHAR,
    keywords_json VARCHAR NOT NULL,
    subject_terms_json VARCHAR NOT NULL,
    resource_url VARCHAR NOT NULL,
    query_profiles_json VARCHAR NOT NULL,
    observed_sources_json VARCHAR NOT NULL,
    source_count INTEGER NOT NULL,
    source_batch_id VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_ordinal INTEGER NOT NULL,
    raw_payload_sha256 VARCHAR NOT NULL,
    content_hash VARCHAR NOT NULL,
    parsed_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR NOT NULL CHECK (source_type = 'real')
);

CREATE TABLE IF NOT EXISTS silver_resources (
    canonical_id VARCHAR PRIMARY KEY,
    doi VARCHAR,
    pmid VARCHAR,
    openalex_id VARCHAR,
    primary_source_name VARCHAR NOT NULL,
    primary_source_record_id VARCHAR NOT NULL,
    title VARCHAR NOT NULL,
    abstract VARCHAR NOT NULL,
    language VARCHAR NOT NULL,
    publication_date DATE,
    authors_json VARCHAR NOT NULL,
    journal_or_publisher VARCHAR,
    keywords_json VARCHAR NOT NULL,
    subject_terms_json VARCHAR NOT NULL,
    resource_url VARCHAR NOT NULL,
    query_profiles_json VARCHAR NOT NULL,
    observed_sources_json VARCHAR NOT NULL,
    source_count INTEGER NOT NULL,
    content_hash VARCHAR NOT NULL,
    first_seen_batch_id VARCHAR NOT NULL,
    last_seen_batch_id VARCHAR NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR NOT NULL CHECK (source_type = 'real')
);

CREATE TABLE IF NOT EXISTS silver_resource_sources (
    canonical_id VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    raw_payload_sha256 VARCHAR NOT NULL,
    source_batch_id VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_ordinal INTEGER NOT NULL,
    query_profiles_json VARCHAR NOT NULL,
    first_seen_batch_id VARCHAR NOT NULL,
    last_seen_batch_id VARCHAR NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR NOT NULL CHECK (source_type = 'real'),
    PRIMARY KEY (
        canonical_id,
        source_name,
        source_record_id,
        raw_payload_sha256,
        source_ordinal
    )
);

CREATE TABLE IF NOT EXISTS silver_rejects (
    quarantine_id VARCHAR PRIMARY KEY,
    canonical_id_candidate VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    source_record_id VARCHAR NOT NULL,
    rejection_code VARCHAR NOT NULL,
    error_type VARCHAR NOT NULL,
    field_path VARCHAR NOT NULL,
    rejection_reason VARCHAR NOT NULL,
    raw_record_json VARCHAR NOT NULL,
    raw_record_sha256 VARCHAR NOT NULL,
    errors_json VARCHAR NOT NULL,
    source_batch_id VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    source_ordinal INTEGER NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL,
    source_type VARCHAR NOT NULL CHECK (source_type = 'real')
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id VARCHAR PRIMARY KEY,
    command_name VARCHAR NOT NULL,
    batch_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_message VARCHAR,
    metrics_json VARCHAR
);

CREATE TABLE IF NOT EXISTS dq_metrics (
    run_id VARCHAR NOT NULL,
    batch_id VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    metric_name VARCHAR NOT NULL,
    metric_value BIGINT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, source_name, metric_name)
);
