# ISCLS Implementation Plan

## Status

Proposed implementation sequence for the contract in [prd.md](prd.md) and
[architecture.md](architecture.md). This plan is intentionally staged: the
first vertical slice proves the joins and evidence path before the corpus or
the physical index stores are enlarged.

## Ownership boundaries

| Area | Owns | Does not own |
| --- | --- | --- |
| Patra Darpan semantic repository | PDF decoding, review state, repair, export, export validation | The live Zoekt/vector/entity services |
| Sanchaya repository | The reviewed corpus snapshot: existing text, exported Markdown, media, manifest, and ontology inputs | Decoder run directories and local absolute paths |
| Offline index builders | Zoekt, vector, mention, and registry projections from one Sanchaya commit | Conversational state or ontology edits |
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
- record unresolved choices in [decisions.md](decisions.md), rather than
  hiding them in implementation defaults.

**Gate:** the team can explain the same document, chunk, corpus revision, and
evidence reference across all three index paths.

**Commit boundary:** `docs(iscls): define retrieval pilot contract`.

### Stage 1 — Export the 120-paper corpus slice

**Purpose:** make the canonical source snapshot reproducible.

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

### Stage 2 — Build and verify the lexical projection

**Purpose:** preserve the existing Sanchaya-Zoekt path while adding exported
paper Markdown.

Configure the Zoekt build/search surface to include the existing text and
`patra-darpan/papers/**` content. Exclude `patra-darpan/catalog/**`, ontology
files, and derived entity artifacts from the user-facing lexical corpus. Keep
the exclusion in the builder/search configuration and enforce it again in the
MCP adapter.

In local development, the MCP adapter calls the local Sanchaya-Zoekt Docker
service. In production, it calls the configured private Sanchaya Zoekt endpoint
(for example, `sanchaya.rasowwhi.us`). The adapter interface is the same in
both environments; the MCP server does not read Zoekt index files directly.

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

### Stage 3 — Establish the chunk and vector projection

**Purpose:** prove semantic retrieval against the same snapshot and identity
contract.

Implement a deterministic chunker with structure-aware boundaries (heading,
paragraph, verse, table, or page marker) and a token limit/overlap fallback.
Keep the exact chunk-size and embedding model as configuration recorded in the
build metadata, not as a corpus identity rule.

Treat vector coverage as a measured policy. Start with the 120 Patra Darpan
papers and a selected Jyotisha slice of Sanchaya, while keeping the builder
capable of reading all eligible Sanchaya text. Measure token volume, chunk
count, build time, embedding cost, vector size, lookup latency, and quality on
Devanagari, IAST, and mixed-script queries before widening coverage. Zoekt can
cover all Sanchaya text independently; vector coverage does not need to match
lexical coverage on day one.

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
fixture. Do not commit a vendor-specific production decision yet.

### Stage 4 — Add the starter ontology and entity projection

**Purpose:** make entity lookup useful for the demo without pretending that the
ontology is complete.

Create a small versioned Jyotisha starter ontology with categories, relations,
and seed aliases. Keep it human-edited in the Sanchaya repository. The entity
extractor reads the ontology and manifest, emits spans and candidate types, and
may leave `canonical_entity_id` empty. A separate registry builder resolves
accepted links and produces the logical lookup projection.

Use the same pilot eligibility policy as vector search: the 120 papers and the
selected Jyotisha slice first. The mention and registry builders should still
accept a broader manifest later, but a build record must state which documents
and source files were processed.

An empty ontology schema is useful for validating file handling, but an empty
ontology is not useful for the demo. Begin from
[`starter-ontology-v0.example.json`](starter-ontology-v0.example.json), trim
or extend the seeds against the evaluation questions, and then copy the
reviewed version into the Sanchaya ontology directory. An empty registry before
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

**Commit boundary:** ontology seed and extraction/registry projection code;
derived mention/registry artifacts may be versioned or retained in a build
artifact store, but must always carry the Sanchaya revision.

### Stage 5 — Expose the read-only MCP boundary

**Purpose:** give ChatGPT/Codex a small, inspectable online interface.

Implement these tools first:

| Tool | Backend path | Required safeguards |
| --- | --- | --- |
| `lookup_entity` | ontology + registry | bounded candidates, no writes |
| `search_corpus` | Zoekt/vector/hybrid adapters | allowlisted paths, filters, result/context limits, revision in response |
| `fetch_passage` | chunk store + Sanchaya content/media | document/chunk references only, no arbitrary filesystem paths |
| `list_entity_mentions` | mention/registry projection | pagination, bounded spans, no writes |

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

### Stage 6 — Demo evaluation and review

**Purpose:** test the experience rather than only the components.

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
document_count        accepted documents included
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

1. this documentation contract;
2. exporter and manifest validation;
3. 120-paper Sanchaya projection and lexical configuration;
4. deterministic chunker and local vector projection;
5. starter ontology, mention extraction, and registry projection;
6. MCP read-only tools and policy tests; and
7. demo evaluation plus expansion hardening.

Each boundary should leave the previous path usable. A failed later stage must
not require reverting the corpus export or lexical index.

## Open implementation questions

These are intentionally left for the vertical slice:

- exact exporter command name and configuration file;
- exact manifest field list and category vocabulary;
- chunk token limit and overlap;
- embedding model and vector store;
- threshold and evidence for widening vector coverage from the Jyotisha slice to
  all eligible Sanchaya text;
- extraction model/rules and confidence thresholds;
- physical registry form; and
- deployment/authentication details for the private MCP service and Zoekt
  endpoint.

They are implementation choices unless they change the stable IDs, evidence
contract, or read-only boundary.
