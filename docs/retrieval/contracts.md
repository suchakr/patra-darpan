# Retrieval contracts

## Stable identity

Every projection joins through stable namespaced identifiers:

- `document_id` identifies a source document independently of an index build;
- `chunk_id` identifies a deterministic passage within a document;
- `entity_id` identifies a canonical ontology entity; and
- `release_id` identifies one compatible set of catalog, chunk, vector, and
  entity artifacts.

Paths are provenance, fetch, and display references. They are not substitutes
for stable IDs.

## Canonical catalog

The canonical SQLite catalog is authoritative for document identity, metadata,
provenance, and document-level relationships. It contains complete Patra
Darpan metadata plus rows for Sanchaya documents selected into the release.

A document row includes, as applicable:

- canonical document ID and source kind;
- title, authors, journal, year, volume, issue, and pages;
- source, PDF, and mirror URLs;
- repository path and provenance references;
- `indexed_in_release`, which distinguishes full catalog coverage from current
  content-index coverage; and
- catalog schema and revision information.

PDFs, Markdown, chunks, embeddings, and lexical shards remain separate. Their
records must refer to valid catalog document IDs.

The checked-in TSV files and registries are catalog inputs or compatibility
projections. MCP metadata tools read SQLite rather than treating those files as
independent authorities.

## Release record

The release record binds:

- Patra Darpan and Sanchaya revisions;
- source manifest and chunk hashes;
- catalog revision;
- ontology version;
- entity registry and mention artifacts;
- vector model, dimensions, collection, and point count; and
- coverage metrics for documents, chunks, vectors, and entities.

[`release.schema.json`](release.schema.json) is authoritative for its shape.
Activation is atomic: clients either read the previous complete release or the
new complete release.

## Entity artifacts

`entity-registry.jsonl` has one canonical entity per row. It contains IDs,
types, preferred labels, aliases, ontology status, and relation data needed by
the resolver.

`entity-mentions.jsonl` has one resolved occurrence per row. It links an entity
ID to a document, chunk, matched surface form, character span, and evidence
context. Mention rows are evidence links; ontology relations are stored with
the ontology/registry and are not inferred merely from co-occurrence.

The versioned ontology is the reviewed seed vocabulary and relationship graph.
MCP exposes it as read-only context. Ontology changes happen in Git and take
effect through a rebuilt entity projection and release.

## MCP tools

All tools are read-only and bounded.

| Tool | Purpose |
| --- | --- |
| `lookup_entity` | Resolve a name or alias to canonical entity IDs |
| `list_entity_mentions` | Browse evidence occurrences for one entity |
| `search_corpus` | Search lexical, vector, or hybrid projections |
| `fetch_passage` | Fetch one bounded passage using a stable reference |
| `fetch_passages` | Batch-fetch several bounded passages |
| `get_document_metadata` | Read metadata for one document ID |
| `get_documents_metadata` | Batch-read metadata for document IDs |
| `search_documents` | Search the complete metadata catalog with filters |
| `get_author_works` | List cataloged works for an author |
| `get_corpus_info` | Report release identity and coverage |

Metadata-first tools avoid repeated search/fetch orchestration for catalog
questions. Search results return stable references that can be reused by the
batch fetch tools.

## MCP resources

| Resource | Purpose |
| --- | --- |
| `retrieval://ontology-context` | Compact ontology guidance for query planning |
| `retrieval://release` | Active release identity and lineage |

## Result behavior

Results include schema versions and the active corpus/release revision where
appropriate. Search limits, passage sizes, and batch sizes are bounded by the
tool implementation. Backend failures are returned explicitly so a client can
distinguish a partial result from a complete one.

## Sources of truth

| Contract | Source |
| --- | --- |
| Catalog schema and build | catalog builder and SQLite schema |
| Release shape | `release.schema.json` |
| Tool input/output schemas | MCP server implementation |
| Ontology entities and relations | `ontology/jyotisha-v0.3.json` |
| Current coverage | active release and `get_corpus_info` |
