# Semantic Search Audit-Set PRD

## Purpose

Build a controlled semantic-search lab over the audited decoded corpus sample.

This is the next retrieval step after lexical Search Lab. The first target is
the current `audit-set`, which contains 29 reviewed documents under
`decode-lab/sets/audit-set.txt`.

The goal is not a production RAG system. The goal is an inspectable semantic
retrieval surface that can answer:

- does semantic retrieval add useful recall over lexical search?
- do retrieved results still preserve citation and provenance discipline?
- is the decoded Markdown quality good enough for retrieval work on this set?

## Reconciled Current State

As of 2026-04-27:

- `audit-set.txt` contains 29 effective `doc_id` entries.
- Lexical Search Lab already exists at `web/search-lab.html`.
- Lexical build input is `decoded-corpus/`.
- Lexical build output is `web/assets/data/search-corpus.json`.
- Shared lexical ranking logic lives in `web/assets/js/search-core.js`.
- Search Lab already carries provenance-friendly fields such as:
  - `doc_id`
  - heading path
  - neighboring chunk IDs
  - source/original URL
  - CAHC mirror URL when present
  - GCS archive key

This means the semantic milestone should not re-solve chunking, provenance, or
source-link modeling. It should reuse them.

## Decision: Isolation From Lexical

### UX isolation: yes

Semantic search should have its own page and its own user framing.

Reason:

- lexical and semantic are different retrieval modes with different failure
  profiles
- we need clean evaluation and honest comparisons
- a mixed UI too early makes it hard to know which layer actually helped

Recommended first surface:

- `web/semantic-lab.html`

Lexical Search Lab remains:

- `web/search-lab.html`

### Source isolation: no, not fully

Semantic search should **not** fork the underlying decoded chunk source.

Reason:

- separate chunk sources would drift immediately
- provenance, chunk IDs, headings, document links, and quality notes should
  remain shared
- lexical and semantic should be comparable over the same chunk universe

What should be isolated instead:

- build script
- build artifact
- ranking logic
- page/UI

Recommended source split:

- shared corpus source: `decoded-corpus/`
- shared set definition: `decode-lab/sets/audit-set.txt`
- lexical artifact: `web/assets/data/search-corpus.json`
- semantic artifact: `web/assets/data/semantic-corpus.json`

## Product Goal

Given a natural-language query that may not share exact wording with the source
text, return a ranked list of cited chunks from the 29-document audit set,
including enough context and source links for a scholar to inspect the evidence.

## Non-Goals

- no answer synthesis in milestone 1
- no agentic RAG orchestration
- no graph database
- no live corpus-wide indexing yet
- no attempt to merge lexical and semantic ranking into one blended score yet
- no opaque third-party UI shell such as Open WebUI as the primary evaluation
  surface

## Milestone 1 Scope

Milestone 1 is a semantic retrieval lab for `audit-set` only.

It should provide:

- query box
- top-k semantically similar chunks
- document title, doc_id, heading path, chunk excerpt
- source access links:
  - original/source
  - CAHC mirror when present
  - GCS archive when present
- retrieval metadata:
  - semantic score
  - embedding model/version
  - corpus build timestamp
- optional compare action to open the same query in lexical Search Lab

It should not provide:

- generated prose answers
- citations stitched into a final narrative
- hidden reranking that cannot be inspected

## Retrieval Design

### Core choice

Use precomputed chunk embeddings plus query-time embedding, over the same chunk
boundaries already used by lexical Search Lab.

This is the cleanest test of semantic retrieval value.

### Why this instead of LLM-only semantic tricks

- easier to reason about
- deterministic corpus-side build artifact
- cheaper to evaluate repeatedly
- easier to compare against lexical baseline
- easier to inspect failure cases

### Retrieval unit

Use the existing Search Lab chunk as the semantic retrieval unit.

Do not invent a new semantic-only chunker for milestone 1.

Reason:

- keeps lexical vs semantic comparison honest
- preserves current provenance wiring
- avoids re-opening chunking design before retrieval value is established

## Data Contract

### Input

Shared decoded corpus input:

- `decoded-corpus/by-doc/<doc-id>/document.md`
- `decoded-corpus/by-doc/<doc-id>/manifest.json`
- `decoded-corpus/by-doc/<doc-id>/quality.json`
- `decoded-corpus/manifest.jsonl`

Shared campaign-set input:

- `decode-lab/sets/audit-set.txt`

Shared metadata enrichment:

- `exports/index.tsv` for source URLs / CAHC mirror / GCS key projection

### Semantic build artifact

Recommended artifact:

`web/assets/data/semantic-corpus.json`

Recommended top-level shape:

```json
{
  "metadata": {
    "build_time": "2026-04-27T12:34:56Z",
    "set_name": "audit-set",
    "doc_count": 29,
    "chunk_count": 1234,
    "embedding_model": "TBD",
    "embedding_dimensions": 768,
    "similarity_metric": "cosine"
  },
  "documents": [...],
  "chunks": [...],
  "embeddings": {
    "format": "base64-f32 | base64-f16 | quantized",
    "by_chunk_id": {
      "doc:page:chunk": "..."
    }
  }
}
```

### Important constraint

Semantic artifact should reuse the same `chunk_id` values as lexical Search Lab.

That is the join key for:

- provenance
- inspection
- comparison
- future hybrid ranking

## Build Workflow

Recommended new builder:

```bash
uv run python scripts/build_semantic_index.py --set audit-set
```

Recommended options:

```bash
uv run python scripts/build_semantic_index.py --help
uv run python scripts/build_semantic_index.py --set audit-set
uv run python scripts/build_semantic_index.py --doc-id Vol28_1_2_SCKak
uv run python scripts/build_semantic_index.py --all-decoded
```

Builder responsibilities:

1. read the same decoded chunk universe used by lexical Search Lab
2. select docs via set or explicit doc IDs
3. generate chunk embeddings
4. write a semantic artifact with shared chunk metadata
5. write a smoke/eval report

Recommended report:

- `reports/semantic-search-smoke.md`

## Runtime Design

### Preferred first implementation

Separate semantic lab page with query-time embedding through a small controlled
backend surface.

Reason:

- corpus embeddings can stay static
- query embeddings are cheap
- browser does not need to ship a local embedding model
- ranking logic stays under repo control

### Practical shape

Two reasonable options:

1. Netlify/server function for query embedding + browser-side ranking
2. Local-only CLI and desktop/browser validator before web wiring

Given the current repo direction, the safest sequence is:

1. local CLI evaluation first
2. then browser lab wiring

This keeps the evaluation path stable even if web/backend wiring changes.

## UX Contract

Semantic Lab should look separate from Lexical Search Lab.

Recommended framing:

- page title: `Semantic Search Lab`
- badge: `Embedding pilot`
- explicit scope note: semantic retrieval over audited decoded chunks

Recommended result actions:

- open source PDF
- open CAHC mirror
- open archive copy
- open decoded document
- compare in lexical lab

Important:

Use the same compact icon scheme already used in Patra Darpan and Search Lab.
Do not reintroduce verbose textual link overload.

## Evaluation Plan

Milestone 1 should be judged on retrieval, not answer generation.

Create a small fixed query set with expected relevant documents/chunks.

Suggested query classes:

- spelling variation / transliteration variation
- concept query without exact phrase overlap
- person/work/topic linkage
- astronomy/mathematics technical vocabulary
- Sanskrit or IAST-bearing terms

Minimum evaluation outputs:

- query
- top 5 results
- whether at least one clearly relevant result appears in top 5
- notes on false positives
- lexical comparison notes

Recommended benchmark framing:

- semantic better than lexical
- lexical better than semantic
- both good
- both weak

## Risks

### 1. Chunk quality ceiling

Semantic retrieval cannot repair bad chunk boundaries or decode corruption.

Mitigation:

- keep quality notes visible
- constrain milestone 1 to audited set

### 2. Embedding model drift / opacity

If the embedding path is not inspectable, trust erodes quickly.

Mitigation:

- record exact embedding model/version in artifact metadata
- keep build deterministic
- avoid UI-only black-box tools

### 3. Over-isolation from lexical

If semantic search uses a different chunk universe, comparisons become
meaningless.

Mitigation:

- separate page and artifact, shared chunk IDs and provenance contract

## Recommended Next Sequence

1. inspect current lexical corpus schema and factor out reusable chunk export if
   needed
2. choose the first embedding path and write it down explicitly
3. build a local semantic CLI evaluator for `audit-set`
4. define a fixed smoke query set and expected-good examples
5. wire `web/semantic-lab.html`
6. compare lexical vs semantic on the same audited queries

## Recommendation On Isolation

Your instinct is partly right.

What is wise:

- isolate semantic from lexical in UX
- isolate semantic from lexical in build artifact
- isolate semantic from lexical in ranking logic

What is not wise:

- isolate semantic from lexical in decoded source chunks
- isolate semantic from lexical in provenance/link metadata

The correct split is:

- separate labs
- shared corpus facts

