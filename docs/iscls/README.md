# ISCLS Three-Index Retrieval Pilot

## Status

The local retrieval vertical slice is implemented on `feat/pdf-semantic-index`:

- Sanchaya remains the one corpus snapshot for lexical, vector, and entity
  projections.
- E5 with Qdrant is the selected local semantic baseline.
- Deterministic chunking, the v0.3 Jyotisha ontology, entity JSONL projections,
  release assembly, four read-only MCP tools, and local smoke checks are in
  place.
- The current active release is a 64-vector smoke collection over a 3,625-
  chunk build input. Full 120-paper vector coverage, manual answer review, and
  production hardening remain.

ISCLS is the event/pilot name. Durable runtime names use `retrieval`; the
pilot history can later be retained as a Git tag without renaming the runtime.

## Read in this order

1. [prd.md](prd.md) — user outcome, pilot scope, scale target, and acceptance.
2. [architecture.md](architecture.md) — data lifecycle, stores, projections,
   APIs, and focused diagrams.
3. [implementation-plan.md](implementation-plan.md) — stage status, gates, and
   remaining work.
4. [decisions.md](decisions.md) — accepted, provisional, and deferred choices.
5. [ontology/README.md](../../ontology/README.md) — versioned ontology
   snapshots; `jyotisha-v0.3.json` is the active pilot input.
6. [release.schema.json](release.schema.json) and
   [release.example.json](release.example.json) — release lineage contract.

The one-off experiment and generation records are kept separately:

- [Embedding bakeoff report](../../reports/iscls/semantic-embedding-bakeoff.md)
- [Ontology generation report](../../reports/iscls/ontology-creation-v0.3.md)
- [Fixed bakeoff queries](../../tests/fixtures/iscls/semantic-embedding-bakeoff-queries.jsonl)

## Central contract

```text
One reviewed Sanchaya commit
  ├── Zoekt lexical projection
  ├── E5/Qdrant vector projection
  └── ontology-driven entity mentions and registry projection
```

The projections are rebuildable. Stable document IDs, chunk IDs, provenance,
and the Sanchaya commit are the joins between them. Online MCP calls are
read-only; corpus, ontology, and index writes happen in reviewed Git changes or
offline build jobs.

## Current local slice

The current manifest contains 29 audit-set papers and 30 Sanchaya probe files
(59 sources total, 3,625 chunks). The pilot target remains 120 accepted papers,
then 200 and eventually the broader corpus.

| Projection | Implementation | Current local result | MCP use |
| --- | --- | --- | --- |
| **Lexical text index** | Zoekt in `sanchaya-zoekt` | Full Sanchaya text plus exported paper Markdown | `search_corpus(mode="lexical")` returns files and snippets |
| **Semantic vector index** | `intfloat/multilingual-e5-base` + Qdrant | 3,625 chunk build input; active smoke release has 64 points | `search_corpus(mode="vector"/"hybrid")` returns chunk references |
| **Entity graph projection** | `ontology/jyotisha-v0.3.json` + JSONL | 143 registry rows, 632 normalized aliases, 147 ontology relations, 10,231 mentions | `lookup_entity` and `list_entity_mentions` return IDs, spans, and evidence links |

`fetch_passage` reads the release chunk/provenance projection and returns the
bounded Markdown context, tables, page locations, and safe relative media links.

## Local build and smoke path

The working tree uses the existing Sanchaya checkout read-only. Generated
artifacts belong under the ignored `.local/retrieval/` directory.

```bash
uv run python scripts/prepare_retrieval_manifest.py
uv run python scripts/build_retrieval_chunks.py
uv run python scripts/build_retrieval_entities.py
```

Run the E5 vector builder against local Qdrant, then materialize an immutable
release from its `run.json`:

```bash
uv run --with sentence-transformers --with qdrant-client==1.14.1 \
  python scripts/run_retrieval_vector_build.py \
  --model intfloat/multilingual-e5-base \
  --collection sanchaya-vector-smoke --max-chunks 64 --recreate

uv run python scripts/create_retrieval_release.py \
  --vector-run .local/retrieval/runs/sanchaya-vector-smoke/run.json

uv run --with qdrant-client==1.14.1 --with sentence-transformers \
  python scripts/smoke_retrieval.py --require-backends
```

The MCP server reads the active release for projections and the versioned
ontology mount for context, then exposes:

`lookup_entity`, `search_corpus`, `fetch_passage`, and
`list_entity_mentions`, plus the read-only resources
`retrieval://ontology-context` and `retrieval://release`.

## Deployment boundary

`docker-compose.retrieval.yml` is a companion project to Sanchaya-Zoekt. It
defines Qdrant, the one-shot retrieval builder, and the MCP runtime without
assuming a shared Docker network. Copy [retrieval.env.example](../../retrieval.env.example)
to an untracked `.env` beside the Compose file, or pass an explicit production
env file. The host paths mount the existing Sanchaya checkout; no second corpus
clone is required. The Compose file records the deployment shape; the current
local gate runs the builders and MCP server from the checkout because pinned
retrieval images are a later packaging step.

Zoekt owns lexical repository sync, shards, HTML, and private RPC. MCP calls
Zoekt through its configured adapter; it never reads Zoekt shard files. In
production the raw Zoekt RPC remains host-private while the public HTML route
continues through Caddy. See [architecture.md](architecture.md) for the
development/production sequence and network boundary.

## Scope and scale

The pilot is smaller data, not a different architecture. Zoekt can index the
full lexical corpus early. Vector and entity coverage widen from the measured
Jyotisha/paper slice after script quality, cost, storage, and latency checks.
The same IDs, release lineage, and MCP contracts are intended to support 2,000
papers and broader Sanchaya coverage.
