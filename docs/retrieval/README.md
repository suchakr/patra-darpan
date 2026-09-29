# Retrieval and MCP

This directory documents the current retrieval system. ISCLS was the pilot
that established the design; its PRD, implementation plan, and experiment
reports remain under [`../iscls/`](../iscls/) and [`../../reports/iscls/`](../../reports/iscls/).

## System boundary

One reviewed Sanchaya corpus snapshot is projected into:

- a Zoekt lexical index managed by the `sanchaya-zoekt` repository;
- an E5 vector index stored in Qdrant;
- an ontology-driven entity registry and mention projection; and
- a read-only SQLite catalog for document identity, metadata, and provenance.

The Patra Darpan retrieval services own the catalog, chunks, vectors, entity
artifacts, ontology context, and MCP tools. Sanchaya-Zoekt owns corpus sync,
lexical shards, the public search UI, and the production Caddy edge.

## Read in this order

1. [`architecture.md`](architecture.md) — ownership and offline/online flows.
2. [`contracts.md`](contracts.md) — IDs, release artifacts, catalog, MCP tools,
   and resources.
3. [`operations.md`](operations.md) — repeatable development and production
   commands.
4. [`auth.md`](auth.md) — OAuth, allowlist, and public route behavior.
5. [`decisions.md`](decisions.md) — durable design decisions and deferred work.

The machine-readable release contract is
[`release.schema.json`](release.schema.json); [`release.example.json`](release.example.json)
is an illustrative record.

## Current status

The vertical slice is implemented and deployed. The repeatable build covers
all exported Patra Darpan paper Markdown plus the configured Sanchaya scope.
Exact document, chunk, vector, and entity counts belong to the active release,
not to this document. Inspect them with:

```bash
make inspect
```

At runtime, MCP clients can call `get_corpus_info` for the same release-scoped
facts.

## Normal entry points

```bash
make help
make check
make build
make index
make inspect
make smoke
```

`make pilot` runs the complete build and verification sequence. It includes an
embedding build and should be used intentionally. See [`operations.md`](operations.md)
for update-specific paths that avoid unnecessary indexing.
