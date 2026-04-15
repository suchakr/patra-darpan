PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS primary_pdf_profiles;
DROP TABLE IF EXISTS pdf_profiles;
DROP TABLE IF EXISTS asset_refs;
DROP TABLE IF EXISTS document_sources;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS cahc_pdf_mirror_registry_entries;
DROP TABLE IF EXISTS cahc_authorship_registry_entries;
DROP TABLE IF EXISTS build_info;

CREATE TABLE build_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE documents (
    doc_id TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL,
    title TEXT NOT NULL,
    author_display TEXT,
    year TEXT,
    journal_label TEXT,
    cahc_authored INTEGER NOT NULL DEFAULT 0,
    source_root TEXT NOT NULL
);

CREATE TABLE document_sources (
    source_row_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    source_version TEXT NOT NULL,
    raw_metadata_json TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents (doc_id)
);

CREATE TABLE asset_refs (
    asset_id TEXT PRIMARY KEY,
    doc_id TEXT NOT NULL,
    asset_role TEXT NOT NULL,
    local_rel_path TEXT,
    remote_url TEXT,
    gcs_key TEXT,
    file_size_bytes INTEGER,
    checksum TEXT,
    mime_type TEXT,
    availability_status TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents (doc_id)
);

CREATE TABLE pdf_profiles (
    asset_id TEXT PRIMARY KEY,
    doc_type TEXT NOT NULL,
    page_count INTEGER,
    text_page_count INTEGER,
    raster_page_count INTEGER,
    image_count INTEGER,
    table_candidate_count INTEGER,
    fonts_missing_unicode_map_count INTEGER,
    estimated_tokens INTEGER,
    token_model TEXT,
    context_cache_eligible INTEGER,
    profile_version TEXT NOT NULL,
    profiled_at TEXT NOT NULL,
    FOREIGN KEY (asset_id) REFERENCES asset_refs (asset_id)
);

CREATE VIEW primary_pdf_profiles AS
SELECT
    d.doc_id,
    d.title,
    d.author_display,
    d.year,
    d.journal_label,
    d.source_root,
    ar.asset_id,
    ar.local_rel_path,
    ar.remote_url,
    ar.gcs_key,
    ar.file_size_bytes,
    ar.checksum,
    ar.mime_type,
    ar.availability_status,
    pp.doc_type,
    pp.page_count,
    pp.text_page_count,
    pp.raster_page_count,
    pp.image_count,
    pp.table_candidate_count,
    pp.fonts_missing_unicode_map_count,
    pp.estimated_tokens,
    pp.token_model,
    pp.context_cache_eligible,
    pp.profile_version,
    pp.profiled_at
FROM documents d
JOIN asset_refs ar ON ar.doc_id = d.doc_id
LEFT JOIN pdf_profiles pp ON pp.asset_id = ar.asset_id
WHERE ar.asset_role = 'primary_pdf';

CREATE TABLE cahc_authorship_registry_entries (
    registry_key TEXT PRIMARY KEY
);

CREATE TABLE cahc_pdf_mirror_registry_entries (
    source_url TEXT PRIMARY KEY,
    mirror_url TEXT NOT NULL
);
