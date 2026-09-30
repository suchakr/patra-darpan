# ISCLS retrieval pilot history

ISCLS was the pilot that established the three-index retrieval design. This
directory retains the event-specific product framing and staged implementation
record. It is historical context, not the current operational manual.

For the live system, start with [`../retrieval/README.md`](../retrieval/README.md).

## Historical documents

- [`prd.md`](prd.md) — pilot problem, users, scope, and acceptance criteria.
- [`implementation-plan.md`](implementation-plan.md) — original delivery stages
  and commit plan.

Experiment evidence remains separate:

- [`../../reports/iscls/semantic-embedding-bakeoff.md`](../../reports/iscls/semantic-embedding-bakeoff.md)
- [`../../reports/iscls/ontology-creation-v0.3.md`](../../reports/iscls/ontology-creation-v0.3.md)
- [`../../tests/fixtures/iscls/semantic-embedding-bakeoff-queries.jsonl`](../../tests/fixtures/iscls/semantic-embedding-bakeoff-queries.jsonl)

## What survived the pilot

The durable architecture, contracts, operations, authentication model, and
decisions were promoted to [`../retrieval/`](../retrieval/). Runtime names use
`retrieval`; ISCLS remains only as historical provenance and can be represented
by a Git tag or release note for the event.
