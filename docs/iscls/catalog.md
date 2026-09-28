# Retrieval Catalog Contract

## Purpose

The retrieval release contains one read-only catalog for MCP metadata queries.
It is a materialized view over two source authorities:

| Document family | Source authority |
| --- | --- |
| `pd:*` papers | Patra Darpan canonical SQLite |
| `sanchaya:*` texts | Sanchaya checkout and release source manifest |

The release catalog is not a replacement for either source. It makes the
metadata needed by the online process portable and keeps the MCP container
independent of source checkouts.

The Patra Darpan side of the catalog is bibliographically complete for the
canonical SQLite input. The release source manifest marks which rows have
content projections in this release. Sanchaya rows remain release-scoped: a
text file is present only when the manifest exports it. Zoekt may still have
broader lexical coverage than the catalog or entity projection.

## Artifact

Each new release contains:

```text
retrieval-catalog.sqlite
```

The release record names the artifact, its SHA-256, and
`retrieval.catalog.v2`. The online process opens it read-only and verifies the
hash before serving requests.

The catalog contains metadata and provenance, not Markdown bodies, embeddings,
Zoekt shards, or entity-window text.

Local absolute paths are removed or reduced to stable metadata locators while
the release is materialized; they are never exposed through MCP.

## Minimum document row

The physical SQLite table is `documents`:

```text
doc_id
source_kind              patra-darpan | sanchaya
source_doc_id
title
authors_json
year
journal
categories_json
repo_path
source_refs_json
content_sha256
indexed_in_release       true when this release has a content projection
metadata_status           available | partial
authority                 patra-darpan.sqlite | sanchaya.manifest | ...
```

All rows are keyed by the stable `doc_id` already used by chunks, vectors, and
entity mentions. Missing bibliographic fields for Sanchaya text are valid and
remain null rather than being guessed.

## MCP operations

The catalog adapter exposes bounded operations only:

- `get_document_metadata(doc_id)`
- `get_documents_metadata(doc_ids)`
- `search_documents(query, source_kind, year, category, indexed_in_release, limit)`
- `get_author_works(author, indexed_in_release, limit)`
- `get_corpus_info()`

Metadata queries include all Patra Darpan rows by default. Set
`indexed_in_release=true` when the caller needs only documents that can be
followed into the current content projections. `false` selects metadata-only
rows. This flag describes release content coverage; it does not claim that
every projection (lexical, vector, and entity) has identical coverage.

No arbitrary SQL or filesystem path is exposed through MCP. Metadata operations
are intended to answer bibliographic questions directly, before a model starts
lexical, vector, or passage retrieval.

## Entity coverage

The entity registry and mention JSONL are still derived projections. Their
coverage may be smaller than the catalog or Zoekt corpus. Every release must
report entity document coverage separately; an absent mention is not evidence
that an entity is absent from an unprocessed document.

## Revisions

The release binds, but does not conflate:

- the Sanchaya content commit;
- the Patra Darpan catalog/build commit;
- the ontology revision;
- the chunk, vector, and entity projection revisions.

An index may be rebuilt independently, but it must declare the source revision
with which it was built before it can be activated.
