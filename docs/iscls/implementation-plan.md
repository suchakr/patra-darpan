# ISCLS Implementation Plan

> Historical staged plan. For current architecture and operations, see
> [`../retrieval/README.md`](../retrieval/README.md).

## Status

Active implementation sequence for the contract in [prd.md](prd.md) and
[`../retrieval/architecture.md`](../retrieval/architecture.md). Stages 0–5 have runnable local slices;
the composite release catalog is the current implementation step. Stage 6 is
the review gate, and Stage 7 covers expansion and production hardening.

## Local-first rule

The active validation path remains local. Do not configure the production
Zoekt endpoint, production MCP host, or production artifact scheduler until the
local review gates pass. Every stage below has a unit-test gate and a small
integration smoke test before a projection is promoted.

## Ownership boundaries

| Area | Owns | Does not own |
| --- | --- | --- |
| Patra Darpan semantic repository | PDF decoding, review state, repair, export, export validation | The live Zoekt/vector/entity services |
| Sanchaya repository | The reviewed corpus snapshot: existing text, exported Markdown, media, and manifest | Ontology source, decoder run directories, and local absolute paths |
| Offline index builders | Zoekt, vector, mention, and registry projections from one Sanchaya commit | Conversational state or ontology edits |
| Release catalog builder | Read-only composite catalog with complete Patra Darpan metadata, Sanchaya release rows, and `indexed_in_release` coverage flag | Upstream metadata authority or full-text/index storage |
| MCP server | Bounded read-only retrieval tools and policy checks | Corpus/index writes and answer synthesis |
| ChatGPT or Codex | Conversation, query planning, tool sequencing, and grounded synthesis | Canonical corpus state |

The semantic repository and Sanchaya repository may have separate release
cadences. A build records the Sanchaya commit so that the split is observable.

## Delivery stages

### Stage 0 — Contract and baseline

**Purpose:** freeze the vocabulary and the review boundary before coding.

**Inputs and outputs:**

- review this directory as the ISCLS contract;
- retain the checkpoint and `main` merge already made on
  `feat/pdf-semantic-index`;
- choose a fixed set of representative questions and expected evidence; and
- record unresolved choices in [`../retrieval/decisions.md`](../retrieval/decisions.md), rather than
  hiding them in implementation defaults.

**Gate:** the team can explain the same document, chunk, corpus revision, and
evidence reference across all three index paths.

**Commit boundary:** `docs(iscls): define retrieval pilot contract`.

### Stage 1 — Export the 120-paper corpus slice

**Purpose:** make the canonical source snapshot reproducible.

**Status:** The exporter, manifest contract, media checks, idempotence checks,
and fixture tests are implemented. The reviewed 120-paper Sanchaya commit is a
data/review step that remains ahead of the current 29-paper audit slice.

Implement an exporter in the Patra Darpan semantic repository. It should:

1. select accepted documents, not arbitrary decode runs;
2. copy one `document.md` and its relative `media/` tree per document into the
   Sanchaya projection;
3. keep the paper directories flat by document ID;
4. write one normalized `corpus-manifest.jsonl` row per document;
5. preserve source PDF URI/hash, extraction run, quality state, categories, and
   content hashes, including typed INSA/IJHS, CAHC, and GCS source references;
   and
6. emit an audit listing copied files, skipped files, broken media links, and
   collisions.

The exporter must be rerunnable. A second run with the same accepted inputs
must produce no content changes. It must never write local absolute paths into
the Sanchaya projection.

**Validation gate:**

- all 120 selected documents have stable IDs and manifest rows;
- Markdown tables are preserved;
- relative image links resolve within the exported paper directory;
- no duplicate document ID or destination collision exists; and
- categories are represented in manifest fields, not by duplicating files.

**Commit boundary:** exporter and validation code in the semantic repository;
reviewed corpus projection in the Sanchaya repository.

### Exporter behavior in concrete terms

The exporter is a one-way, deterministic projection from accepted semantic
documents into a Sanchaya staging worktree. It:

1. reads accepted-document state and assembled Markdown from the semantic repo;
2. assigns or verifies the stable `pd:` document ID;
3. copies `document.md` and rewrites/validates only relative media references;
4. writes one manifest row with categories, hashes, quality, extraction data,
   and typed INSA/IJHS, CAHC, and GCS source references;
5. emits a dry-run/audit report for missing media, collisions, and omissions; and
6. leaves the Sanchaya commit to explicit review and Git commit.

It does not build an index, edit the source Markdown, copy decoder run caches,
or publish anything. Start its tests with a three-to-five-document fixture,
then run the same exporter against the 120-paper selection.

**Exporter unit/integration gate:** stable IDs, manifest schema, source refs,
category handling, media-link safety, idempotence, duplicate detection, and no
absolute paths all pass before any index build begins.

### Stage 2 — Build and verify the lexical projection

**Purpose:** preserve the existing Sanchaya-Zoekt path while adding exported
paper Markdown.

**Status:** The existing Zoekt service remains the lexical owner, and the local
MCP adapter can call its bounded RPC surface. Production host-private RPC and
the final Caddy deployment change remain operational work.

Configure the Zoekt build/search surface to include the existing text and
`patra-darpan/papers/**` content. Exclude `patra-darpan/catalog/**`, ontology
files, and derived entity artifacts from the user-facing lexical corpus. Keep
the exclusion in the builder/search configuration and enforce it again in the
MCP adapter.

For this milestone, the MCP adapter calls only the local Sanchaya-Zoekt Docker
service. A later production adapter can call the configured private Sanchaya
Zoekt endpoint (for example, `sanchaya.rasowshi.us`); that is not part of the
local gate. The MCP server does not read Zoekt index files directly.

The manifest is still available for filters and display metadata; it is not
required to be lexical content. This gives the user clean search results while
retaining structured metadata for later retrieval.

**Validation gate:**

- an existing Sanchaya lexical query still returns its prior result;
- a phrase present only in an exported paper is found;
- a result returns `document_id`, repository path, and corpus revision;
- a catalog or ontology term cannot be retrieved as ordinary paper content; and
- paper image links remain usable after a lexical hit is fetched.

**Commit boundary:** Zoekt configuration and smoke checks.

**Lexical unit/integration gate:** path allowlisting, catalog/ontology
exclusion, query-result identity, existing Sanchaya phrase search, and a
paper-only phrase search pass against the local Docker service.

### Stage 3 — Establish the chunk and vector projection

**Purpose:** prove semantic retrieval against the same snapshot and identity
contract.

The first Stage 3 activity was the offline model and chunking bakeoff described
in [the bakeoff report](../../reports/iscls/semantic-embedding-bakeoff.md). It reads a
clean, revision-pinned Sanchaya checkout directly, uses a standalone local
Qdrant profile, and leaves Zoekt, MCP, and the production services unchanged.
The bakeoff selected E5 with Qdrant for the pilot; its measured limits and
inconclusive challenger runs remain in the report.

**Status:** Deterministic chunks, explicit source scopes, and the E5/Qdrant
builder are implemented. The active release covers all exported papers plus
all `Jyotisham` text and the six demo anchors (6,593 vectors). The earlier
64-point collection remains as a calibration artifact.

Implement a deterministic chunker with structure-aware boundaries (heading,
paragraph, verse, table, or page marker) and a token limit/overlap fallback.
Keep the exact chunk-size and embedding model as configuration recorded in the
build metadata, not as a corpus identity rule.

Treat vector coverage as a measured policy. The repeatable default is all
exported Patra Darpan papers plus all `Jyotisham` text and the six demo
anchors, while the builder remains capable of reading all eligible Sanchaya
text. Measure token volume, chunk count, build time, embedding cost, vector
size, lookup latency, and quality on Devanagari, IAST, and mixed-script
queries before widening coverage. Zoekt can cover all Sanchaya text
independently; vector coverage does not need to match lexical coverage on day
one.

For each chunk, persist:

- `document_id` and `chunk_id`;
- text and logical location;
- source page/section when known;
- content hash and chunker version;
- Sanchaya commit; and
- embedding model/version and vector index key.

The chunk store may start as files or a lightweight local database. The vector
adapter must depend on the logical contract, so changing the store does not
change MCP semantics.

**Validation gate:**

- unchanged content produces stable chunk IDs;
- a changed document rebuilds only affected chunks;
- vector results can be fetched by chunk ID;
- the query embedding is generated by the configured model at search time; and
- lexical and vector results can be fused without mixing corpus revisions.

The vector build report must include the eligibility policy and the measured
coverage, cost, latency, and quality metrics. The logical adapter must support
source filters so a later full-Sanchaya build does not require a new MCP
contract.

**Commit boundary:** chunker, vector builder/adapter, and a small local index
fixture. E5/Qdrant are the pilot choices; production retention and operating
topology remain replaceable.

**Vector unit/integration gate:** deterministic chunk IDs, Unicode/script
preservation, revision/hash invalidation, model-adapter behavior, vector lookup,
and a small Devanagari/IAST/mixed-script quality set pass locally. The build
report records token count, chunk count, duration, cost/accounting, vector size,
latency, and coverage policy.

### Stage 4 — Add the starter ontology and entity projection

**Purpose:** make entity lookup useful for the demo without pretending that the
ontology is complete.

**Status:** The repository-owned v0.3 snapshot, deterministic alias extractor,
mention JSONL, and 143-row registry projection are implemented. The active
Jyotisham release has 22,114 mentions across 152 documents and observes 133 of
143 ontology entities. Morphology, unknown-entity discovery, and inferred
relations remain iteration-0 limits.

Create a small versioned Jyotisha starter ontology with categories, relations,
and seed aliases. Keep it human-edited in the Patra Darpan repository under
`ontology/`. The entity
extractor reads the ontology and manifest, emits spans and candidate types, and
may leave `canonical_entity_id` empty. A separate registry builder resolves
accepted links and produces the logical lookup projection.

Use the same pilot eligibility policy as vector search: the 120 papers and the
repeatable `Jyotisham` scope. The mention and registry builders should still
accept a broader manifest later, but a build record must state which documents
and source files were processed.

An empty ontology schema is useful for validating file handling, but an empty
ontology is not useful for the demo. Use the repository-owned snapshots in
[`ontology/`](../../ontology/). The active pilot input is
[`jyotisha-v0.3.json`](../../ontology/jyotisha-v0.3.json); the historical v0
example remains reference-only. An empty registry before
the first extraction run is expected.

Extraction windows may be paragraphs, verses, tables, or sections rather than
the exact vector chunk. Each mention should still point to a document and,
where possible, nearby chunks.

**Validation gate:**

- a seeded name and alias resolve to the same candidate ID;
- an unknown mention remains visible without a fabricated canonical ID;
- each mention row follows the versioned one-row-per-mention contract, with
  Unicode offsets and a fetchable window locator;
- `list_entity_mentions` returns source spans and fetchable evidence;
- registry links can be rebuilt from mentions and ontology versions; and
- no online tool can modify ontology, seed, mention, or registry data.

**Commit boundary:** ontology snapshots and extraction/registry projection code;
derived mention/registry artifacts may be versioned or retained in a build
artifact store, but must always carry the Sanchaya revision.

**Implementation checkpoint:** The first deterministic graph-extraction slice is
implemented in [`lib/retrieval_entities.py`](../../lib/retrieval_entities.py) and
[`scripts/build_retrieval_entities.py`](../../scripts/build_retrieval_entities.py).
It treats the shared chunk inventory as the initial extraction-window source,
emits one mention edge per explicit ontology alias, and writes a rebuildable
registry node projection. Run it with the active repository-owned ontology using:

```bash
uv run python scripts/build_retrieval_entities.py
```

The original v0.1 smoke build over the frozen pilot snapshot produced 2,515
resolved mentions across 51 documents and observed all 16 seed entities. The
intermediate v0.3 calibration build produced 10,231 mentions across 57
documents; the active full-scope build produces 22,114 across 152 documents
and observes 133 of 143 ontology entities. These figures validate plumbing and
span/chunk links, not ontology completeness. The extractor still does not
discover unknown entities, perform Sanskrit morphology, or infer new relations;
those remain explicit iteration-0 gaps.

**Entity unit/integration gate:** ontology schema validation, alias lookup,
Unicode span offsets, unresolved mentions, registry rebuilds, pagination, and
document/chunk evidence links pass locally. The pilot can load JSONL into memory
or SQLite; it does not need a production entity service yet.

### Stage 5 — Expose the read-only MCP boundary

**Purpose:** give ChatGPT/Codex a small, inspectable online interface.

**Status:** The retrieval tools, metadata-first catalog tools, two read-only
resources, release lineage, local Streamable HTTP smoke client, and Docker
runtime are implemented on this branch. Batch passage retrieval and the
optional HTTPS gateway are included; native client setup, production
authentication, and public deployment remain outside the local gate.

Implement these tools first:

| Tool | Backend path | Required safeguards |
| --- | --- | --- |
| `lookup_entity` | ontology + registry | bounded candidates, no writes |
| `search_corpus` | Zoekt/vector/hybrid adapters | allowlisted paths, filters, result/context limits, revision in response |
| `fetch_passage` | chunk store + Sanchaya content/media | document/chunk references only, no arbitrary filesystem paths |
| `fetch_passages` | chunk store + Sanchaya content/media | maximum batch size, per-item limits, isolated stale-reference errors |
| `list_entity_mentions` | mention/registry projection | pagination, bounded spans, no writes |

The catalog operations are deliberately separate from full-text retrieval:

| Tool | Backend path | Required safeguards |
| --- | --- | --- |
| `get_document_metadata` | composite SQLite catalog | one stable ID, bounded response |
| `get_documents_metadata` | composite SQLite catalog | maximum batch size, stable ordering |
| `search_documents` | composite SQLite catalog | allowlisted filters, optional indexed-only filter, and result limit |
| `get_author_works` | composite SQLite catalog | bounded author query, optional indexed-only filter, no arbitrary SQL |
| `get_corpus_info` | catalog plus entity coverage | counts and revisions only |

The MCP server is the only online API in the pilot. The underlying Zoekt RPC,
vector store, registry files, and build directories remain private adapters.
Every response includes enough identity and revision metadata for the host to
avoid fusing incompatible results.

Also expose the compact ontology as an MCP read-only resource named
`ontology_context` (or a compatibility read tool). It contains types, relation
names, topic labels, normalization rules, and examples, not the full registry.

**Validation gate:**

- each tool has a schema fixture and a negative-path fixture;
- the host can load `ontology_context` and then resolve a seed alias through
  `lookup_entity`;
- catalog paths, ontology writes, and arbitrary filesystem reads are rejected;
- result limits and timeouts are enforced;
- a ChatGPT/Codex conversation can complete lookup → search → fetch; and
- the answer can cite a table and a media reference without exposing metadata
  as ordinary search text.

**Commit boundary:** MCP schemas, adapters, local server, and integration
smoke tests.

**Implementation checkpoint:** The first host-level vertical slice is now
implemented in [`lib/retrieval_adapters.py`](../../lib/retrieval_adapters.py),
[`scripts/create_retrieval_release.py`](../../scripts/create_retrieval_release.py),
and [`scripts/retrieval_mcp_server.py`](../../scripts/retrieval_mcp_server.py).
The release script materializes `retrieval-catalog.sqlite` from the canonical
Patra Darpan SQLite database plus release-scoped Sanchaya source rows. It also
copies the corpus manifest, chunks, mentions, and registry into a release
directory, records the E5/Qdrant collection and source commits, and atomically
selects `active-release.json`. The adapters cover:

- Zoekt JSON RPC (`POST /api/search`) with catalog-path exclusion and decoded
  line snippets;
- Qdrant query plus the configured E5 query prefix, loaded lazily only for a
  vector call;
- composite SQLite metadata queries with explicit Patra Darpan/Sanchaya source
  authority;
- bounded JSONL entity lookup and mention pagination; and
- chunk/provenance/media fetches without arbitrary filesystem access.
- batched passage fetches and stable `document_id`/`chunk_id` references on
  lexical results.

The MCP server exposes the retrieval and metadata tools in this section plus
the `retrieval://ontology-context` and `retrieval://release` resources. Run it
locally with `uv run --with 'mcp<2' ...`; the v1 SDK pin is intentional because
the installed MCP v2 package renamed the FastMCP API. The 64-vector
calibration collection remains available for quick checks; the active local
release is the full 6,593-vector Jyotisham scope.

The MCP vertical slice now joins the three backend adapters. Its tests and smoke
checks cover tool schemas, bounded limits, catalog/path rejection, revision
lineage, backend error mapping, and the sequence `ontology_context` →
`lookup_entity` → `search_corpus` → `fetch_passages`. A local end-to-end smoke
test must complete before any production endpoint or deployment work is
scheduled.

The local smoke test must exercise both sides of the local Zoekt boundary: the
HTML search page remains available and a `POST /api/search` request succeeds
when the local webserver is run with `-rpc`. Production work must preserve the
private-RPC boundary described in
[`../retrieval/architecture.md`](../retrieval/architecture.md): MCP and
Zoekt share the host's private network, Caddy serves the public HTML routes,
and public `/api` paths are rejected before the catch-all proxy.

### Stage 6 — Demo evaluation and review

**Purpose:** test the experience rather than only the components.

**Status:** The E5 bakeoff baseline and protocol smoke checks are recorded.
Manual answer/citation/table/media review and the fixed 120-paper expansion are
the current review work.

Create a small fixed evaluation set containing:

- an exact Indic phrase;
- a conceptual question requiring vector search;
- a known entity and alias;
- a cross-document entity query;
- a table/figure question;
- a citation/provenance check; and
- a metadata-leak negative case.

Record the Sanchaya commit, build versions, tool calls, returned evidence, and
whether the answer is supportable. Review failure cases as contract or data
quality issues before changing ranking heuristics.

**Gate:** the researcher can follow an answer to a passage, page/table/figure,
document ID, and corpus revision without verbal explanation from the author.

**Commit boundary:** evaluation set and report; no silent changes to the
contract.

### Stage 7 — Expand from 120 to 200 and then 2,000

Scale only after the pilot gates pass. Add content-hash incremental export,
resumable batches, durable versioned artifacts, build scheduling, disk/media
monitoring, pagination, and retention. The logical interfaces remain unchanged.

## Build and release records

Every offline export or index build records:

```text
corpus_revision       Sanchaya commit SHA
catalog_revision      Patra Darpan catalog/build revision
document_count        accepted documents included
catalog_document_count documents represented in the composite release catalog
catalog_indexed_document_count documents with content projections in this release
catalog_metadata_only_document_count metadata rows without release content
entity_document_count documents with extracted entity mentions
vector_scope          eligible sources/files for this vector build
token_count           source tokens included in vector build
chunk_count           chunks emitted
build_duration        elapsed time for this projection
embedding_cost        provider estimate or local compute accounting
content_hash_policy   hash/version used for change detection
chunker_version       if vector projection is built
embedding_model       if vector projection is built
ontology_version      if entity projection is built
extractor_version     if entity projection is built
builder_version       code/build identifier
created_at             UTC timestamp
status                 complete | partial | failed
```

Partial artifacts are never silently promoted to the active MCP revision.

## Commit sequence

The implementation should remain reviewable through small boundaries:

1. this documentation and catalog contract;
2. exporter and manifest validation;
3. 120-paper Sanchaya projection and lexical configuration;
4. deterministic chunker and local vector projection;
5. starter ontology, mention extraction, and registry projection;
6. composite release catalog and metadata-first MCP tools;
7. retrieval MCP policy checks and demo evaluation; and
8. expansion hardening.

Each boundary should leave the previous path usable. A failed later stage must
not require reverting the corpus export or lexical index.

## Open implementation questions

These are the remaining decisions after the local vertical slice:

- the reviewed 120-paper export and the threshold for widening Sanchaya vector
  coverage;
- manual quality review of Devanagari, IAST, mixed-script, table, image, and
  citation answers;
- incremental/resumable vector and entity builds for the 200/2,000-paper path;
- durable artifact retention and Qdrant backup/restore; and
- deployment, authentication, rate limits, and host-private Zoekt RPC in
  production.

The pilot defaults are now explicit: structure-aware chunking, E5
`intfloat/multilingual-e5-base`, Qdrant, the v0.3 ontology, JSONL entity
projections, and the read-only metadata/retrieval MCP contract. Revisit them only with measured
evidence or a changed scale requirement.

They are implementation choices unless they change the stable IDs, evidence
contract, or read-only boundary.
