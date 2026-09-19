# ISCLS Three-Index Retrieval Pilot

## Status

Proposed contract. Implementation begins after this document set is reviewed.

## Purpose

ISCLS is the first integrated retrieval experience over the Sanchaya Indic text
corpus and the decoded Patra Darpan paper corpus. It combines lexical, vector,
and entity-oriented retrieval behind read-only MCP tools that ChatGPT or Codex
can call while composing a grounded answer.

The directory name `docs/iscls/` is intentionally provisional. It names the
current pilot and can later move to a broader retrieval name without changing
the data contracts.

## Read in this order

1. [prd.md](prd.md) — user outcome, pilot scope, scale target, and acceptance.
2. [architecture.md](architecture.md) — data lifecycle, stores, indexes, APIs,
   and focused diagrams.
3. [implementation-plan.md](implementation-plan.md) — build stages, gates, and
   commit boundaries.
4. [decisions.md](decisions.md) — accepted, provisional, and deferred choices.
5. [starter-ontology-v0.example.json](starter-ontology-v0.example.json) — a
   small non-empty Jyotisha seed to review before copying into Sanchaya.

## The central idea

```text
One canonical Sanchaya commit
  ├── Zoekt lexical projection
  ├── vector projection
  └── entity and registry projection
```

The indexes are rebuildable projections. Stable document IDs, chunk IDs,
provenance, and the Sanchaya commit connect them.

## Pilot and scale profiles

| Profile | Corpus / index coverage | Experience | Purpose |
| --- | --- | --- | --- |
| Pilot | Zoekt over existing Sanchaya text plus 120 papers; vector/entity over the papers plus a selected Jyotisha slice | Read-only MCP, lexical/vector/entity retrieval, citations, tables, and images | Prove the end-to-end contract |
| Expansion | Zoekt over 200 papers; vector/entity over 200 papers plus the selected Jyotisha slice | Same contracts, larger batch and evaluation set | Validate repeatability |
| Full corpus | Up to 2,000 Patra Darpan papers plus Sanchaya in all eligible projections | Incremental builds, durable index artifacts, operational monitoring | Scale the same architecture |

The pilot profile is smaller in data volume, not a separate architecture.

Zoekt can cover the full lexical corpus early. The pilot vector build starts
with the 120 papers and a selected Jyotisha slice of Sanchaya, then widens after
Devanagari/IAST quality and cost measurements.

Implementation is local-first: exporter, Zoekt, vector/entity projections, and
MCP are validated on the workstation before production endpoints are considered.

## Existing design references

This package integrates and extends the component work already documented in:

- `docs/build-decoded-corpus-prd.md`
- `docs/pdf-decoding-lab.md`
- `docs/decode-lab-status.md`
- `docs/spasta-corpus-prd.md`
- `docs/spasta-corpus-technical-design.md`
- `docs/semantic-search-audit-set-prd.md`
- `docs/pd-corpus-snapshot-prd.md`

Those documents remain useful component and historical references. This package
is the integration contract for the three-index retrieval experience.

## Current repository baseline

The design starts after these commits on `feat/pdf-semantic-index`:

- `f4103a9` — checkpoint current decode, audit, search, and media work.
- `fdf55f5` — merge current `main`, including corpus and guarded deployment
  updates.

## Review rule

Physical names for the entity registry, vector store, and final ontology schema
remain provisional until the first vertical slice proves the query contract.
The logical roles and lifecycle are fixed enough to implement against.
