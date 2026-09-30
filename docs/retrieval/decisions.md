# Retrieval decisions

This file records durable current decisions. ISCLS-specific exploration and
the original staged plan remain under [`../iscls/`](../iscls/).

| ID | Decision | Status |
| --- | --- | --- |
| R1 | Build catalog, lexical, vector, and entity projections from one reviewed corpus snapshot | Accepted |
| R2 | Use stable namespaced document, chunk, entity, and release IDs across projections | Accepted |
| R3 | Keep paper Markdown clean; keep categories and other metadata in manifests/catalogs | Accepted |
| R4 | Preserve tables and relative media references in chunks and passage results | Accepted |
| R5 | Use Zoekt for lexical search and access it through private RPC rather than shard files | Accepted |
| R6 | Use multilingual E5 with Qdrant as the measured semantic baseline | Accepted |
| R7 | Use a reviewed versioned starter ontology and deterministic alias-based entity extraction | Accepted |
| R8 | Keep catalog, content-index, and entity coverage separate and observable | Accepted |
| R9 | Expose bounded read-only MCP tools and metadata-first shortcuts | Accepted |
| R10 | Treat MCP adapters as the stable interface to SQLite, Qdrant, entity artifacts, chunks, and Zoekt | Accepted |
| R11 | Build and validate locally before production; use the same Make target shape in both environments | Accepted |
| R12 | Keep Qdrant, MCP, and OAuth in the Patra Darpan companion project; do not fold them into Sanchaya-Zoekt Compose | Accepted |
| R13 | Let the production Sanchaya-Zoekt Caddy own public TLS and route dispatch | Accepted |
| R14 | Make OAuth `/mcp` the preferred public endpoint and authorize Google identities through a reloadable email allowlist | Accepted |
| R15 | Keep corpus and ontology writes outside online MCP calls | Accepted |
| R16 | Preserve raw Zoekt syntax and advertise filename-only results; offer explicit script expansion for plain Sanskrit terms | Implemented |
| R17 | Bound result bytes and expose continuation and completeness; link user-facing evidence to readable source hyperlinks | Implemented |
| R18 | Deploy runtime-only changes with Git and `make up`, reusing persistent releases, indexes and OAuth state | Implemented |

## Search iterations agreed on 2026-10-01

Iterations 1–2 cover bounded search, honest counts, passage continuation,
query/script guidance, and reusable Advanced Search transliteration behavior.
Expansion is deterministic; LLM-proposed declensions, sandhi and samāsa forms
remain hypotheses that require passage evidence. Raw queries remain available.

Iteration 3 is the reviewed v0.4 ontology extension and contextual-synonym
projection. It is not activated by runtime updates. Iteration 4 broadens
fetchable passage scope and genre coverage, with measured artifact rebuilds.
Quotas remain deferred. No deployment or ontology/index rebuild is included in
iterations 1–2.

## Consequences

- Indexes are rebuildable projections rather than Git artifacts.
- A release must record exact source, catalog, ontology, chunk, and vector
  lineage.
- Metadata questions can avoid full-text retrieval.
- Expanding corpus scope requires a measured rebuild but not new interfaces.
- Production deployment spans two repositories with explicit ownership and a
  shared Docker-network contract.

## Deferred

- Full-domain ontology design and learned entity extraction.
- Broader Sanchaya vector coverage beyond the configured scope.
- Web administration for the OAuth allowlist.
- Per-user roles, quotas, and audit UI.
- Shipping prebuilt multi-architecture vector releases instead of building on
  the production host.

Deferred items should become separate decisions only when implementation work
is approved.
