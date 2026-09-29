# ISCLS Three-Index Retrieval Pilot

## Status

The local retrieval vertical slice is implemented on `feat/pdf-semantic-index`:

- Sanchaya remains the one corpus snapshot for lexical, vector, and entity
  projections.
- E5 with Qdrant is the selected local semantic baseline.
- Deterministic chunking, the v0.3 Jyotisha ontology, entity JSONL projections,
  release assembly, metadata-first and retrieval MCP tools, and local smoke checks are in
  place.
- The current active release covers 120 exported papers plus 34 Jyotisha
  Sanchaya sources: 6,593 chunks/vectors and 22,114 entity mentions. The
  earlier 64-vector collection remains as a calibration artifact.

ISCLS is the event/pilot name. Durable runtime names use `retrieval`; the
pilot history can later be retained as a Git tag without renaming the runtime.

## Read in this order

1. [prd.md](prd.md) — user outcome, pilot scope, scale target, and acceptance.
2. [architecture.md](architecture.md) — data lifecycle, stores, projections,
   APIs, and focused diagrams.
3. [catalog.md](catalog.md) — composite SQLite release catalog and metadata
   operations.
4. [implementation-plan.md](implementation-plan.md) — stage status, gates, and
   remaining work.
5. [decisions.md](decisions.md) — accepted, provisional, and deferred choices.
6. [ontology/README.md](../../ontology/README.md) — versioned ontology
   snapshots; `jyotisha-v0.3.json` is the active pilot input.
7. [release.schema.json](release.schema.json) and
   [release.example.json](release.example.json) — release lineage contract.
8. [https.md](https.md) — local HTTPS test gateway and production Caddy boundary.
9. [oauth.md](oauth.md) — Google OAuth, allowlist, and route lifecycle.
10. [index-build.md](index-build.md) — repeatable Jyotisham/vector release build.
11. [production-deploy.md](production-deploy.md) — production preconditions and
    deploy/build/activate sequence.

The one-off experiment and generation records are kept separately:

- [Embedding bakeoff report](../../reports/iscls/semantic-embedding-bakeoff.md)
- [Ontology generation report](../../reports/iscls/ontology-creation-v0.3.md)
- [Fixed bakeoff queries](../../tests/fixtures/iscls/semantic-embedding-bakeoff-queries.jsonl)

## Central contract

```text
One reviewed release source set
  ├── composite SQLite metadata catalog
  ├── Zoekt lexical projection
  ├── E5/Qdrant vector projection
  └── ontology-driven entity mentions and registry projection
```

The projections are rebuildable. Stable document IDs, chunk IDs, provenance,
and the source revisions are the joins between them. The catalog covers both
Patra Darpan papers and Sanchaya text files; entity coverage may be smaller and
is reported separately. Online MCP calls are read-only; corpus, ontology, and
index writes happen in reviewed Git changes or offline build jobs.

## Current local slice

The current active manifest contains 120 exported papers and 34 Jyotisha
Sanchaya sources (154 sources total, 6,593 chunks). The same builder can use the
29-paper audit scope for calibration, and can later widen the Sanchaya scope.

| Projection | Implementation | Current local result | MCP use |
| --- | --- | --- | --- |
| **Release catalog** | Composite read-only SQLite: complete Patra Darpan metadata plus Sanchaya release rows | All Patra Darpan metadata rows; `indexed_in_release` identifies rows with current content projections | Metadata-first tools answer catalog questions; optional flag filters to indexed content |
| **Lexical text index** | Zoekt in `sanchaya-zoekt` | Full Sanchaya text plus exported paper Markdown | `search_corpus(mode="lexical")` returns files and snippets |
| **Semantic vector index** | `intfloat/multilingual-e5-base` + Qdrant | 6,593 normalized 768-dimensional points in the active release | `search_corpus(mode="vector"/"hybrid")` returns chunk references |
| **Entity graph projection** | `ontology/jyotisha-v0.3.json` + JSONL | 143 registry rows, 632 normalized aliases, 147 ontology relations, 22,114 mentions | `lookup_entity` and `list_entity_mentions` return IDs, spans, and evidence links |

`fetch_passage` reads the release chunk/provenance projection and returns the
bounded Markdown context, tables, page locations, and safe relative media links.

## Repeatable Compose flow

Run these from the semantic checkout. Development uses the untracked `.env`
beside the Makefile. Production uses the host-only retrieval env file and the
production Compose overlay; the target names remain unchanged.

```bash
make check
make build
make index
make inspect
make smoke
```

`make pilot` runs that sequence as one ordered flow. For first-time production
setup, create the private env file from the checked-in
[production example](../../retrieval.env.prod.example), edit its host paths and
tokens, then run:

```bash
make PROD=1 prod-env
make check
make pilot
```

`make help` lists the targets and default env paths. Set `ENV_FILE=...` only
when using a different env-file location.

The Makefile derives its repository path from the Makefile itself. No `PD_DIR`
or shell-profile setting is required. `SANCHAYA_REPO_ROOT` remains an explicit
env-file setting because it points to the separately managed corpus checkout.
`make catalog` builds or atomically refreshes the canonical Patra Darpan SQLite
catalog in a one-shot container. `make index` runs it automatically before
building retrieval projections. Run `make catalog` by itself when only the
metadata catalog needs refreshing; it does not start Qdrant or build vectors.

## Local build and smoke path

The working tree uses the existing Sanchaya checkout read-only. Generated
artifacts belong under the ignored `.local/retrieval/` directory.

```bash
uv run python scripts/prepare_retrieval_manifest.py
uv run python scripts/build_retrieval_chunks.py
uv run python scripts/build_retrieval_entities.py

# Build/update only the canonical metadata catalog when needed.
make catalog
```

For the repeatable path, build and activate one release with Docker Compose:

```bash
make check
make build
make index
make inspect
make smoke
```

When `/etc/patra-darpan/retrieval.env` exists, the same targets automatically
select the production overlay. `make pilot` runs the one-command production
flow; `PROD=1` is needed only for the guarded `prod-env` setup target.

The low-level `run_retrieval_vector_build.py` and
`create_retrieval_release.py` commands remain useful for calibration and
debugging; the Compose builder is the normal dev/prod path.

The MCP server reads the active release for projections and the versioned
ontology mount for context, then exposes:

`lookup_entity`, `list_entity_mentions`, `search_corpus`, `fetch_passage`,
`fetch_passages`, and the metadata-first catalog operations
`get_document_metadata`, `get_documents_metadata`, `search_documents`,
`get_author_works`, and `get_corpus_info`, plus the read-only resources
`retrieval://ontology-context` and `retrieval://release`.

## Deployment boundary

`docker-compose.retrieval.yml` is a companion project to Sanchaya-Zoekt. It
defines Qdrant and the containerized MCP runtime without assuming a shared
Docker network. The runtime image is built from `Dockerfile.retrieval`; model
weights remain in the host cache mounted at runtime, read-write so
Transformers can record cache metadata. Copy
[retrieval.env.example](../../retrieval.env.example) to an untracked `.env`
beside the Compose file, or pass an explicit production env file. The host
paths mount the existing Sanchaya checkout; no second corpus clone is
required.

For a local Docker smell test, use the same Make targets. The Compose project
owns Qdrant and waits for it before the one-shot builder runs:

```bash
make check
make pilot
```

The Makefile also provides `make backend-smoke` for adapter checks and
`make mcp-smoke` for protocol-level MCP initialization, entity lookup, and
hybrid search.

The MCP endpoint is then `http://127.0.0.1:8787/mcp`. The protocol smoke runs
inside the retrieval image, so it uses the same client dependencies in
development and production.

```bash
make mcp-smoke
```

For a harness that requires HTTPS, use the optional local Caddy profile or the
production Caddy route described in [https.md](https.md).

A browser `GET` is expected to return a content-negotiation error because
Streamable HTTP requires an MCP client request. Stop the stack with:

```bash
make down
```

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
