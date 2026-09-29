# ISCLS Three-Index Retrieval Pilot PRD

> Historical pilot contract. For the implemented system, see
> [`../retrieval/README.md`](../retrieval/README.md).

## Status

Active pilot contract. The local vertical slice uses E5 with Qdrant, JSONL
entity projections, and a read-only MCP server. The PRD still leaves the
production vector topology, artifact retention, and custom chat application
open.

## Problem

Sanchaya already provides useful lexical search over its Indic text corpus.
Patra Darpan now provides a growing set of decoded Markdown documents containing
paper text, tables, figures, and page provenance. These sources need to be
experienced as one research corpus.

The missing layer is an inspectable retrieval path that can combine:

- exact lexical evidence;
- semantic similarity over stable chunks;
- entity and alias lookup; and
- passage, page, table, and image provenance.

The first user interface is ChatGPT or Codex using MCP. A custom chat
application is not part of this milestone.

## User outcome

A researcher asks a question in ChatGPT or Codex and receives an answer that:

1. uses the ontology guide and entity lookup when names are ambiguous;
2. searches the Sanchaya corpus lexically, semantically, or in hybrid mode;
3. fetches the relevant passage with document and page provenance;
4. preserves Markdown tables and links to relevant images; and
5. cites the evidence used to form the answer.

## Users

- **Researcher:** asks questions about Jyotisha and related Indic history of
  science material.
- **Curator:** reviews document metadata, categories, seed entities, and
  extracted mentions.
- **Maintainer:** runs exports, index builds, repairs, and validation.
- **Chat host:** ChatGPT or Codex plans calls and synthesizes the grounded
  response; it does not own corpus state.

## Pilot scope

The pilot contains:

- the existing Sanchaya Indic text corpus;
- 120 accepted Patra Darpan decoded papers, with a path to 200;
- Markdown tables and available per-paper media;
- deterministic, structure-aware retrieval chunks;
- a small, versioned starter ontology and seed entities;
- Zoekt lexical search;
- a vector index over the 120 papers plus the repeatable `Jyotisham` Sanchaya
  scope (with a measured path to all eligible Sanchaya text);
- structured entity extraction and a minimal entity lookup projection; and
- read-only MCP tools.

The first implementation and evaluation run locally. The active local release
covers all 120 accepted papers and the Jyotisham scope; the 29-paper audit set
and probe scope remain calibration options. Production Zoekt hosting, MCP
deployment, authentication, and scheduling remain follow-on work after the
local review gates pass.

The initial subject slice is Jyotisha-oriented, but the document and index
contracts must not encode Jyotisha as a special case.

## Goals

### G1. One corpus snapshot

A Sanchaya Git commit must identify the content used by all three projections.
Every result must be traceable to a stable document ID and, where applicable,
a chunk ID.

### G2. Useful hybrid retrieval

The system must support lexical, vector, and combined retrieval without
requiring a new corpus copy for each index.

### G3. Inspectable evidence

A result must lead to the source Markdown, source location, provenance, and
available media. Tables must remain readable in the fetched context.

### G4. Entity-aware questions

A small starter ontology and seed vocabulary must support canonical lookup,
alias resolution, mention browsing, and links back to evidence.

### G5. Safe read-only integration

MCP exposes read operations only. Ontology and corpus changes happen through
reviewed Git changes and offline jobs.

### G6. Repeatable builds

An unchanged document must not be re-embedded or re-extracted unnecessarily.
A build must record the corpus revision, chunker version, embedding model, and
ontology/extractor versions.

## Non-goals

- A custom chat UI.
- Ontology editing through ChatGPT, Codex, or MCP.
- Automatic discovery of a complete ontology from an empty vocabulary.
- A final choice of vector database or embedding model.
- Production multi-region availability.
- Perfect extraction of every table or figure before the pilot is useful.
- Duplicating papers under every category.

## Core user journeys

### Known term

The user asks for an exact phrase or Indic term. The host calls lexical search,
then fetches the relevant passage and cites it.

### Conceptual question

The user describes a concept without using the corpus wording. The host embeds
the question, calls vector or hybrid search, and fetches the strongest evidence.

### Entity question

The user names an entity or alias. The host calls `lookup_entity`, passes
confirmed IDs into search, then fetches linked evidence.

### Cross-document entity view

The user asks where an entity is discussed. The host calls
`list_entity_mentions`, then fetches selected passages.

### Rich evidence

The answer needs a table or figure. `fetch_passage` returns the Markdown
context, page references, and safe media references for the renderer.

## MCP contract for the pilot

All tools are read-only and stateless. Each call carries the inputs required to
reproduce its result; long-lived conversation state remains with ChatGPT or
Codex.

| Tool | Purpose | Writes state? |
| --- | --- | --- |
| `lookup_entity` | Resolve a name, alias, or type hint to candidate canonical IDs | No |
| `search_corpus` | Run lexical, vector, or hybrid retrieval with metadata filters | No |
| `fetch_passage` | Return passage text, location, provenance, and media references | No |
| `list_entity_mentions` | Browse mentions and links for a canonical entity | No |
| `get_document_metadata` | Resolve one stable document ID through the release catalog | No |
| `get_documents_metadata` | Batch-resolve stable document IDs | No |
| `search_documents` | Search bounded metadata filters without full-text retrieval | No |
| `get_author_works` | Resolve an author's cataloged works | No |
| `get_corpus_info` | Report source counts, revisions, and entity coverage | No |

The exact JSON schemas belong in the architecture document and are versioned
with the MCP implementation. The server also exposes a compact read-only
`ontology_context` resource (or compatibility tool) so the host can plan calls
using the starter types and normalization rules.

The release catalog carries typed source references for each document. Patra
Darpan SQLite remains authoritative for `pd:*` paper metadata; Sanchaya source
rows remain authoritative for `sanchaya:*` text metadata. A document can have
multiple references; they are provenance, not duplicate corpus documents.

## Acceptance criteria

The pilot is ready for review when:

- 120 accepted papers export deterministically into Sanchaya-compatible paths.
- Each exported paper can retain typed INSA/IJHS, CAHC, and GCS provenance
  references without committing signed URLs or local paths.
- Relative image links resolve after export; no local absolute paths escape the
  semantic repository.
- Markdown tables survive export and render in fetched evidence.
- The Zoekt surface searches content files without exposing catalog metadata.
- The active release contains a composite catalog covering every document
  represented by its source rows, with Patra Darpan and Sanchaya authority
  recorded separately.
- Vector results return `document_id`, `chunk_id`, score, and provenance.
- The vector build report states its source eligibility policy, token/chunk
  count, build time, model, and measured Devanagari/IAST quality.
- Entity extraction writes one `entity-mentions.jsonl` row per mention with a
  source window, Unicode span, type, confidence, extractor/ontology versions,
  and nullable `canonical_entity_id`.
- Entity lookup returns seed or resolved candidates with aliases and evidence
  links.
- Entity-index document coverage is reported separately from catalog coverage.
- The host can read compact ontology context before issuing entity/search calls.
- All indexes identify the same Sanchaya commit.
- MCP rejects metadata paths and arbitrary write operations.
- A fixed evaluation set covers lexical, vector, entity, citation, table,
  image, and metadata-leak cases.

## Scale target

The full target is approximately 2,000 Patra Darpan papers plus the existing
Sanchaya text corpus. The architecture is considered scale-ready when the same
contracts support:

- incremental export by document/content hash;
- batched vector and entity builds;
- resumable extraction and indexing;
- versioned derived artifacts;
- media storage that can move outside Git without changing document identity;
- filtered retrieval by source and category; and
- a measured decision to vectorize all eligible Sanchaya text rather than only
  the pilot Jyotisha slice; and
- rebuilds from a recorded Sanchaya commit.

The main expected scaling costs are media storage, embedding volume, entity
extraction time, index disk, and operational scheduling. They do not require a
new logical architecture.

## Risks and responses

| Risk | Response |
| --- | --- |
| Metadata becomes lexical noise or leaks through Zoekt | Keep metadata in catalog paths, exclude those paths at index/search boundaries, and enforce MCP allowlists |
| Entity extraction creates false canonical links | Preserve spans and confidence; allow unresolved mentions; require ontology/version fields |
| Vector and entity boundaries differ | Share document/chunk IDs but permit larger entity context windows |
| Indic embedding quality is weak or uneven across scripts | Evaluate Devanagari, IAST, and mixed-script queries on the pilot slice before widening vector coverage |
| Git grows too large because of page images | Preserve media paths for the pilot; move large assets to object storage later |
| One-off repairs invalidate indexes | Use content hashes and corpus revision checks before rebuilding projections |
| Ontology schema freezes too early | Treat ontology shape as a versioned pilot input and keep registry storage provisional |

## Success signal

A researcher and maintainer can inspect the same answer from two directions:
from the conversational response down to a cited passage, and from a passage back
to its document, extraction provenance, entity links, and media. The pilot is
successful when that chain is understandable without verbal explanation.
