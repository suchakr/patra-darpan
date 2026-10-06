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

When a Sanchaya Git revision changes without changing any selected source
bytes, a release may mark its existing vector collection with
`reused_from_release`, `reuse_verified`, and `reuse_basis`.  Reuse is valid
only after the selected source hashes, deterministic chunk-key inventory, and
Qdrant point IDs/payload keys have been checked.  The refresh still creates a
new catalog, release, and entity-artifact revision so catalog and provenance
adapters do not depend on the retired release directory.  It must not be used
for a content, chunker, model, dimension, or embedding-input change.

`corpus_revision` identifies the Sanchaya revision used for the release's
catalog, chunks, entities, and vector projection. The independently operated
Zoekt lexical index has its own revision in
`artifacts.lexical_index.corpus_commit`; `get_corpus_info()` exposes this as
`indexes.lexical.revision`. Its `revision_source` is `release_metadata` and
`revision_verified` is false unless a live backend check has been performed.
This prevents a release declaration from being mistaken for proof of the
currently deployed Zoekt shard revision.

[`release.schema.json`](release.schema.json) is authoritative for its shape.
Activation is atomic: clients either read the previous complete release or the
new complete release.

## Entity artifacts

`entity-registry.jsonl` has one canonical entity per row. It contains IDs,
types, preferred labels, aliases, ontology status, and occurrence statistics
and document/chunk links needed by the resolver. The current registry builder
does not copy ontology attributes or relations into this artifact.

`entity-mentions.jsonl` has one resolved occurrence per row. It links an entity
ID to a document, chunk, matched surface form, character span, and evidence
context. Mention rows are evidence links; ontology relations are stored in the
versioned ontology and are not inferred merely from co-occurrence.

The versioned ontology is the reviewed seed vocabulary and relationship graph.
MCP reads its knowledge by entity ID alongside the release's occurrence
statistics. Top-level `relations` is canonical; node-local relations are a
cached projection. Ontology changes happen in Git and take effect through a
rebuilt entity projection and release. Exposing already-present knowledge
from an unchanged ontology requires only a runtime update, not reindexing.

## MCP tools

All tools are read-only and bounded.

| Tool | Purpose |
| --- | --- |
| `lookup_entity` | Resolve a name/alias; return occurrence counts and bounded ontology knowledge |
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
| `retrieval://search-guide` | Index coverage, query syntax, script expansion, continuation and linked evidence |

## Result behavior

Results include schema versions and the active corpus/release revision where
appropriate. Search responses also include `lexical_revision`, the observed
Zoekt `Version` when lexical results are present, plus
`lexical_revision_declared`, `lexical_revision_source`, and
`lexical_revisions_observed`. Lexical result rows expose the same observed
revision as `lexical_revision`; source links remain pinned to that row's
revision. A mismatch between observed and declared revisions is reported in
`warnings`, rather than being silently presented as one coherent release.
Search limits, passage sizes, and batch sizes are bounded by the tool
implementation. Backend failures are returned explicitly so a client can
distinguish a partial result from a complete one.

`lookup_entity` retains its arguments and `retrieval.entity-lookup.v1` schema.
Each result adds `attributes`, `relations`, `ontology` (ID/version),
`source_ref`, and `curation_status`. Relation records include type, direction,
the canonical `from_entity_id`/`to_entity_id`, and the related entity's
`target_entity_id`/`target_preferred_label`. For an incoming relation the related
entity is the edge's source. Follow its preferred label with `lookup_entity`;
authorship and composition-location relations remain attached to the work.

Knowledge is limited to 20 relations and 8 KiB per entity, including its
knowledge metadata. Complete attribute values are retained or omitted;
strings are not cut into partial values. Counts and `attributes_truncated`,
`relations_truncated`, and `knowledge_truncated` report omissions.
`relation_projection_consistent=false` identifies a stale node-local edge
projection; the canonical table still supplies returned relations. The whole
lookup JSON is limited to 64,000 UTF-8 bytes. `total_results` counts resolved
matching entities before limits, `results_truncated` reports fewer results,
and `byte_limit_reached` distinguishes the byte cap from the requested limit.

`retrieval://ontology-context` remains a compact discovery vocabulary with
`knowledge_lookup` guidance instead of repeated attributes and graph edges.
It retains `retrieval.ontology-context.v1`; `entity_count` and
`entities_truncated` describe its 64,000-byte vocabulary limit. Ontology
assertions and coarse entity source references are not passage evidence or
edge-level citations. Use mention browsing and fetched passages for evidence.

`search_corpus` preserves raw Zoekt queries, including `type:filename`, and
adds optional `result_type`, `file_filter`, `script_expansion`, `context_lines`,
`snippet_chars`, `match_limit` and `cursor`. Filename-only results use lexical
mode. Script expansion is explicit and restricted to plain terms; complex
expressions retain raw Zoekt semantics. Vector queries keep the original text.

Lexical pages expose `lexical_stats`, `next_cursor`, `has_more` and match
windows with original UTF-8 offsets. Backend-reported totals carry an exactness
flag; the bounded snapshot is not a guarantee of full-corpus enumeration.
`backend_counts` retains its original meaning: adapter candidate rows before
fusion, not occurrence totals. Cursors expire after five minutes or eviction.

`fetch_passage` adds `offset`, `text_offset` and `max_chars`; results expose
document continuation and chunk-text continuation separately. Batch requests
accept the same fields and report unprocessed requests if the shared budget
is reached. Search and passage results include `citation_url`/`source_url`
where resolvable. Existing required arguments, tool names and response fields
are retained. The [search guide](search-guide.md) contains defaults and usage.

## Sources of truth

| Contract | Source |
| --- | --- |
| Catalog schema and build | catalog builder and SQLite schema |
| Release shape | `release.schema.json` |
| Tool input/output schemas | MCP server implementation |
| Ontology entities and relations | `ontology/jyotisha-v0.3.json` |
| Current coverage | active release and `get_corpus_info` |
