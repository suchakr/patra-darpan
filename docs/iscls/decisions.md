# ISCLS Decision Log

## How to read this file

This ledger distinguishes decisions that are safe to implement now from choices
that should remain configurable until the first vertical slice provides
evidence. A provisional physical choice must not leak into the MCP contract.

Statuses:

- **Accepted:** use this direction for the pilot.
- **Provisional:** use a simple implementation, but keep the interface open.
- **Deferred:** do not spend implementation effort yet.

## Accepted decisions

### D1 — One content snapshot, three projections, one release catalog

**Decision:** Sanchaya is the reviewed content snapshot. Zoekt, vector, and
entity/registry indexes are independent rebuildable projections of the same
Sanchaya commit. A retrieval release also contains a composite metadata
catalog: Patra Darpan SQLite supplies `pd:*` paper rows and Sanchaya supplies
`sanchaya:*` text rows.

**Reason:** This preserves the existing Sanchaya lexical path while giving the
other indexes a common identity and provenance join.

### D2 — Patra Darpan exports into Sanchaya

**Decision:** The Patra Darpan semantic repository owns decoding and review. A
deterministic exporter projects accepted Markdown and relative media into the
Sanchaya checkout.

**Reason:** The semantic branch can repair and validate papers; Sanchaya remains
the single corpus that all three indexes consume.

### D3 — Flat paper directories, manifest-based categories

**Decision:** Keep one paper directory per stable document ID under
`patra-darpan/papers/`. Store `primary_category` and `categories` in the
manifest. Do not duplicate a paper under every category.

**Reason:** A paper may belong to multiple categories, and category changes
should not change document identity or copy content.

### D4 — Markdown stays clean

**Decision:** Do not add front matter to exported Markdown. Keep metadata in
`catalog/corpus-manifest.jsonl` and derived catalogs.

**Reason:** Front matter is useful to some tools but would add metadata noise to
the existing Zoekt lexical experience. Structured metadata remains available
for filters and vector/entity joins.

### D5 — Catalog paths are not user-facing lexical content

**Decision:** Zoekt build/search configuration excludes `catalog/`, ontology,
and derived entity artifacts from the ordinary lexical corpus. The MCP wrapper
enforces the same content allowlist.

**Reason:** A manifest is valuable to builders and fetch logic, but users should
not receive JSON metadata as if it were a paper passage.

### D6 — Preserve media and tables

**Decision:** Export relative per-paper media with Markdown. Preserve Markdown
tables as text. Image-only tables require OCR/vision extraction before they are
expected to be searchable.

**Reason:** The demo needs rich evidence. Media paths are part of provenance,
not a reason to discard the source document.

### D7 — Stable namespaced identities

**Decision:** Use stable namespaced document IDs (`sanchaya:` and `pd:`), stable
chunk IDs, content hashes, and a recorded Sanchaya commit. A directory or
category move does not silently create a new document.

**Reason:** Lexical, vector, entity, and citation results need a durable join.

### D8 — Deterministic chunking first

**Decision:** Start with structure-aware deterministic chunking and a token
limit/overlap fallback. Keep entity extraction windows independent when larger
context is useful.

**Reason:** Reproducibility and cost matter for a 120-paper pilot. LLM-assisted
chunking can be evaluated later for documents where structure is unusable.

### D9 — Small starter ontology, human maintained

**Decision:** Begin with a versioned Jyotisha starter ontology and seed aliases.
Extraction can emit unresolved mentions. Ontology edits happen through reviewed
Git changes, never through MCP.

**Reason:** Lookup needs prior structure to be useful, but the pilot should not
pretend the vocabulary is complete or freeze a final taxonomy. The active
repository-owned snapshot is `ontology/jyotisha-v0.3.json`; earlier snapshots
remain reference material. An empty registry is still expected before the first
extraction run.

### D10 — Read-only MCP tools with metadata-first shortcuts

**Decision:** The MCP surface includes entity and passage retrieval
(`lookup_entity`, `list_entity_mentions`, `search_corpus`, `fetch_passage`,
and `fetch_passages`) plus bounded catalog operations
(`get_document_metadata`, `get_documents_metadata`, `search_documents`,
`get_author_works`, and `get_corpus_info`).

**Reason:** Metadata questions such as author bibliographies should be answered
from the catalog in one call. Search follow-ups should use stable chunk or
document references, and several evidence passages should be fetched in one
batch. All tools remain stateless; conversation state belongs to ChatGPT/Codex.

### D11 — MCP is the online policy boundary

**Decision:** Do not expose raw Zoekt RPC, vector stores, registry files, or
build directories directly to the chat host. MCP applies path, result, context,
timeout, revision, and read-only policies.

**Reason:** This keeps the first online API small and prevents accidental data
or filesystem exposure.

### D12 — Focused operational diagrams

**Decision:** Document separate sequence diagrams for export, independent index
builds, and online query, plus a small dev/prod topology diagram.

**Reason:** These diagrams explain real process boundaries and data flow without
turning the review into a graph-reading exercise.

### D13 — Typed multi-source provenance

**Decision:** `corpus-manifest.jsonl` uses a `source_refs` array. A document may
carry typed INSA/IJHS, CAHC, and GCS references, with hashes and observation
metadata where available.

**Reason:** A primary source, mirror, and managed asset are related but do not
have the same authority or lifecycle. One URL field cannot express that safely.

### D14 — One mention per entity-mentions row

**Decision:** `entity-mentions.jsonl` has one row per observed mention. Each row
contains a document/window locator, Unicode code-point span, surface and
normalized forms, entity type, confidence, extractor/ontology versions, and a
nullable canonical ID.

**Reason:** This is a stable interchange contract for extraction, review, and
registry rebuilds. An extraction window can contain many mention rows.

### D15 — Staged vector coverage

**Decision:** Zoekt may index all eligible Sanchaya content from the start. The
initial vector projection covered the 120 Patra Darpan papers plus a selected
Jyotisha Sanchaya slice. D23 now defines the repeatable default as all
`Jyotisham` text plus fixed anchors; full Sanchaya vector coverage still
requires a measured Devanagari/IAST quality, cost, size, and latency review.

**Reason:** Vector build cost and semantic quality depend on token volume and
model support, not file count. Staged coverage gives the demo enough breadth
without hiding an Indic model risk.

### D16 — Backend adapters, not shared index files

**Decision:** MCP calls backend adapters. Local Zoekt is a Docker service;
production Zoekt is the configured private Sanchaya endpoint. Vector and entity
backends may be local libraries/databases or remote services. JSONL remains a
portable build artifact, not a required hot query path.

**Reason:** Deployment can change without changing tool semantics, and lexical,
vector, and entity systems do not need to share a process.

### D17 — Ontology context is read-only MCP context

**Decision:** Expose a compact `ontology_context` MCP resource (or compatibility
read tool) containing types, relations, topic labels, normalization rules, and
seed examples. Keep canonical resolution in `lookup_entity`; do not dump the
full registry into model context.

**Reason:** The host needs a vocabulary to plan useful calls, while the full
registry would be noisy, expensive, and a poor substitute for lookup.

### D18 — Local validation before production

**Decision:** The first implementation milestone uses a local Sanchaya
worktree, local Docker Zoekt, local vector/entity projections, and a local MCP
server. Production endpoint and deployment work waits for the local gates.

**Reason:** It isolates contract and data-quality failures from network,
authentication, and deployment failures. The same adapters can be pointed at a
production service later.

### D19 — Production Zoekt RPC is host-private

**Decision:** Enable Zoekt JSON RPC for the local MCP test first. In
production, MCP and Zoekt run on the same host, preferably on the same private
Docker network. Zoekt's RPC is not published as a host or public port. Caddy
continues to serve the public HTML search routes and rejects `/api` and
`/api/*` before the public catch-all proxy. A host-process MCP may use a
loopback-only port instead.

**Reason:** The public site should remain reachable while raw search RPC stays
inside the production trust boundary. MCP is the policy boundary for queries,
limits, and evidence; Zoekt's `-rpc` flag does not provide authentication or
rate limiting.

### D20 — Pilot codename, neutral runtime namespace

**Decision:** Keep `ISCLS` for the event-scoped documentation, bakeoff history,
and eventual Git tag. Use neutral `retrieval` names for durable runtime
contracts, Compose services, environment variables, and new artifact schemas.

**Reason:** The pilot should retain its provenance without making an event name
part of the long-lived retrieval platform. Existing `iscls.*` bakeoff records
remain readable as historical artifacts; new releases use `retrieval.*`.

### D21 — TLS terminates at the gateway

**Decision:** Keep the MCP application on private HTTP inside Docker. Terminate
HTTPS at Caddy: the local profile uses Caddy's internal CA, while production
uses the existing Sanchaya-Zoekt Caddy certificate and private Docker network.
Do not publish the MCP or Qdrant ports in production.

**Reason:** Certificate renewal, authentication, and rate limiting belong at
the gateway. The MCP image stays identical between local and production, and
the external contract is a normal HTTPS Streamable HTTP endpoint.

### D22 — Complete metadata with release coverage flag

**Decision:** Materialize every canonical Patra Darpan metadata row in the
release catalog. Add `indexed_in_release` to each document row; it is true
when the current release has a content projection for that document and false
when the row is metadata-only. Metadata tools return the complete catalog by
default and accept the flag as an optional filter.

**Reason:** Bibliographic questions should not be limited to the current
120-paper content slice, while passage/vector/entity retrieval must still be
honest about what has been built. The flag is release coverage, not a claim
that lexical, vector, and entity indexes have identical coverage.

### D23 — Jyotisham is a reproducible vector scope

**Decision:** The default retrieval builder includes all UTF-8 text under
`Sanchaya/Jyotisham` plus the six fixed Jyotisha anchor texts. It builds that
scope through the same manifest, chunk, E5/Qdrant, entity, and release steps
in development and production. The MCP service never embeds during a restart.

**Reason:** Jyotisham coverage should not depend on a manually selected
one-off sample, while a separate one-shot indexer preserves fast, predictable
MCP startup and persistent Qdrant reuse.

## Provisional decisions

### P1 — Composite release catalog

**Decision:** Patra Darpan's canonical SQLite database remains authoritative for
`pd:*` paper metadata. Sanchaya remains authoritative for `sanchaya:*` text
metadata. Each retrieval release materializes both into a read-only
`retrieval-catalog.sqlite` artifact.

`corpus-manifest.jsonl` remains a portable export and audit projection;
`entity-mentions.jsonl` remains derived extraction output; and
`entity-registry.jsonl` remains the ontology lookup projection. None of these
files is treated as a universal catalog by the online MCP process.

Entity coverage is recorded separately from catalog coverage. An entity lookup
with no mention in the active projection must not be interpreted as proof that
the entity is absent from documents that were not extracted.

### P2 — Paper path and media layout

**Decision:** Use `patra-darpan/papers/<document-id>/document.md` and a sibling
`media/` directory for the pilot. The logical source locator must survive a
later move of media to object storage.

### P3 — Vector model and store

**Decision:** Choose a model and local vector store during Stage 3. Record both
in build metadata and never encode either into document identity or MCP tool
names.

### P4 — Entity extractor and resolver

**Decision:** Start with the simplest reproducible rules/dictionary/model mix
that handles the seed ontology. Evaluate an LLM only where ambiguity or context
requires it. Keep mention spans and confidence regardless of extractor type.

### P5 — Chunk size and entity window size

**Decision:** Tune against the fixed evaluation set. Vector chunks and entity
windows may differ while sharing document and evidence joins.

### P6 — Derived artifact retention

**Decision:** During the pilot, derived JSONL and index artifacts may be kept
near the build output or committed where inspectability helps. At scale, retain
versioned artifacts keyed by Sanchaya commit rather than making Git carry every
large derived object.

### P7 — Zoekt endpoint address and transport

**Decision:** Treat the local Docker endpoint and the production Sanchaya Zoekt
hostname as deployment configuration. The MCP adapter must not hard-code either
address or assume that the chat host can reach Zoekt directly.

### D23 — MCP authentication routes

**Decision:** Keep the existing shared bearer process for compatibility at the
`/mcp-bearer` route. Add a second process using the same retrieval image and
tools, with Google OAuth and a server-side email allowlist, at `/mcp`; expose
`/mcp-oauth` as an explicit path alias. Caddy terminates TLS and keeps Qdrant
and Zoekt RPC private.

**Reason:** This preserves the trusted-demo bearer client while making the
default route usable by OAuth-capable ChatGPT and other MCP clients. The
allowlist is deliberately a simple operator-edited file; its cache is refreshed
by a cheap stat check and does not affect releases or indexing.

## Deferred decisions

### F1 — Full ontology design

Do not design a complete Jyotisha or cross-domain ontology before the pilot
questions reveal which types and relations earn their maintenance cost.

### F2 — Category taxonomy and automatic classification

Categories are metadata filters for now. Do not infer a final taxonomy or
duplicate documents based on categories until retrieval questions justify it.

### F3 — OAuth administration and long-term identity

Google OAuth and per-user access are implemented for the pilot. A web UI for
editing the allowlist, group-based policy, account lifecycle, audit history,
and broader identity providers remain future work. The shared bearer token is
compatibility-only and is not a long-term identity model. The host-private
Zoekt RPC boundary in D19 remains accepted; a public raw RPC route is not part
of the pilot.

### F4 — Custom chat application

ChatGPT/Codex plus MCP is the first client. Build a custom application only if
the tool contract proves insufficient for the intended user experience.

### F5 — Public Zoekt or index APIs

No public raw-index endpoint is part of this pilot. The MCP adapter is the
reviewed interface.

## Review questions before implementation

1. Do the 120-paper questions require all four MCP tools, or is one tool unused?
2. Which media references must be served as URLs versus repository paths?
3. Is the initial entity registry more useful as inspectable JSONL or as a local
   query database?
4. Which metadata filters are essential for the first demo?
5. What corpus revision/build metadata must be visible in the answer trace?

Answers may promote provisional items to accepted decisions; they should not
silently broaden the pilot.
