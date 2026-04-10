PRAGMA foreign_keys = ON;

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
    availability_status TEXT NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents (doc_id)
);

CREATE TABLE cahc_authorship_registry_entries (
    registry_key TEXT PRIMARY KEY
);

CREATE TABLE cahc_pdf_mirror_registry_entries (
    source_url TEXT PRIMARY KEY,
    mirror_url TEXT NOT NULL
);
