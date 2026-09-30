# PRD: Local RAG via Open WebUI, Ollama, and Patra Darpan Markdown

## Status
Draft

## Owner
Patra Darpan local retrieval exploration

## Summary
Establish a local, low-operations retrieval workflow for the Patra Darpan corpus
using:

- local Markdown documents as the retrieval source artifact;
- Open WebUI Knowledge as the first retrieval surface;
- Ollama-hosted local models for generation and embeddings;
- Gemma 4 as the answer model;
- `bge-m3` as the initial embedding model.

This is a practical local milestone, not the final long-term retrieval
architecture. The immediate goal is to prove that a scholar can ask grounded
questions against a small Patra Darpan Markdown corpus on local hardware with
acceptable retrieval quality, preserved provenance, and manageable operator
burden.

## Problem
Patra Darpan now has enough decoded and Markdown-oriented corpus material that
semantic retrieval is worth testing, but the project does not yet have a simple,
trustworthy local RAG path.

The current gaps are:

- there is no agreed first retrieval surface for local use;
- retrieval quality for Sanskrit, IAST, and English mixes is unvalidated;
- chunk quality is not yet defined as an explicit product requirement;
- metadata and provenance expectations for RAG ingestion are underspecified;
- there is no repeatable evaluation harness for comparing chunking and embedding
  choices.

Without a narrow first milestone, semantic retrieval risks becoming another
broad architecture discussion detached from corpus quality.

## Why This Shape
Open WebUI plus Ollama is the right first milestone because it is already
running locally, keeps operations light, and gives a usable end-to-end loop
without first building a custom retrieval application.

This milestone should not be mistaken for the final authoritative search stack.
Open WebUI is the first integration target, not the long-term source of truth
for corpus structure, chunk contracts, or evaluation logic.

## Users
- local maintainer validating corpus-aware retrieval on a laptop
- scholar/test user asking exploratory questions against a pilot corpus
- agent or maintainer comparing chunking and embedding choices before larger
  indexing work

## Goals
- Stand up a local RAG workflow over a pilot Patra Darpan Markdown corpus.
- Use Open WebUI Knowledge with Ollama-hosted `bge-m3` embeddings and Gemma 4
  generation as the first usable stack.
- Define a pilot corpus package that is safe to ingest and easy to refresh.
- Validate multilingual retrieval quality for Sanskrit, IAST transliteration,
  and English gloss/query mixes.
- Define a small evaluation harness with fixed queries and expected source
  documents.
- Make chunking quality an explicit requirement before scaling from dozens of
  documents toward the broader corpus.

## Non-Goals
- Building the final production semantic search system in this milestone.
- Making Open WebUI's internal Chroma store the canonical corpus authority.
- Ingesting the full corpus immediately.
- Solving every PDF-to-Markdown quality issue before the pilot begins.
- Building a custom Patra Darpan RAG UI before local retrieval quality is
  understood.

## Starting Assumptions
- Local hardware: Apple Silicon laptop class machine with enough RAM to run
  Ollama and Docker together.
- Available local services:
  - Ollama with Gemma 4 already installed
  - Ollama with `bge-m3` available for embeddings
- Open WebUI running in Docker at `http://localhost:3000`
- The first corpus input is Markdown, not raw PDF.
- Corpus growth should follow a staged path: pilot set first, then broader
  ingest only after retrieval quality is believable.

## Initial Pilot Corpus
The initial pilot corpus should use the full audited Markdown-oriented set
already defined in:

```text
decode-lab/sets/audit-set.txt
```

Current working count:

- 29 documents

Reasoning:

- the set is already audit-informed rather than arbitrarily sampled;
- it is still small enough for local re-ingest and repeated evaluation;
- it gives more realistic coverage of corpus and chunking edge cases than a
  smaller handpicked subset.

If debugging becomes noisy, a smaller temporary debug subset may be derived from
the audit set, but the audit set remains the default pilot target.

## Product Shape

### First Retrieval Stack
The initial local stack is:

```text
User query
  -> Open WebUI
  -> Knowledge retrieval over Patra Darpan Markdown chunks
  -> Ollama embeddings via bge-m3
  -> retrieved context attached to prompt
  -> Gemma 4 answer generation
```

### Authority Boundary
The Patra Darpan corpus artifacts remain authoritative. Open WebUI is a
consumer of exported Markdown inputs plus optional metadata, not the canonical
owner of corpus structure.

Working rule:

- corpus text structure belongs to Patra Darpan artifacts
- evaluation belongs to repo-managed scripts and reports
- Open WebUI indexes a derived input set

## Corpus Input Contract
The first ingestable unit is one Markdown document per corpus document.

The pilot Markdown should:

- preserve document identity in filename or frontmatter;
- preserve headings and section structure;
- avoid arbitrary line-wrapped noise where possible;
- keep verse plus directly attached commentary together where feasible;
- retain enough provenance to identify the source document unambiguously.

Desired minimum per document:

- `doc_id`
- title
- author if known
- year if known
- source PDF or source URL reference
- Markdown body with meaningful headings

If Open WebUI ignores frontmatter for retrieval, the exported Markdown filename
and body should still expose the document identity clearly.

## Chunking Requirements
Chunking quality is a product requirement, not just an ingestion setting.

The pilot must avoid common failure modes:

- splitting a verse from its commentary when they need to be read together;
- splitting transliterated terms from their nearby English explanation;
- creating chunks so large that retrieval becomes vague;
- creating chunks so small that answers lose context.

Working guidance:

- prefer natural Markdown boundaries over blind fixed windows;
- treat verse-plus-commentary as one semantic unit where the source structure
  supports that;
- use overlap only when it improves continuity without flooding retrieval with
  near-duplicates.

## Embedding Model Decision
Initial choice:

- `bge-m3`

Rationale:

- multilingual support matters for the Sanskrit/IAST/English mix;
- it is lightweight enough for local operation;
- it is already available in the intended local stack.

Fallback candidate for comparison:

- `nomic-embed-text-v2-moe`

This project should not assume the initial embedding choice is correct without a
small evaluation pass.

## Evaluation Requirement
Before scaling, the project needs a small repeatable evaluation harness.

Minimum evaluation shape:

- 10 to 20 fixed test queries;
- expected relevant documents for each query;
- a mix of English, IAST, and mixed-register queries;
- at least a few term-alignment checks where Sanskrit concepts should retrieve
  the correct scholarly context.

Example test styles:

- concept in IAST plus English framing
- English gloss expected to retrieve Sanskrit-heavy passages
- named entity query such as a star, text, author, or technical term

Success should be reported in repo-managed notes, not only judged informally in
the Open WebUI chat surface.

## Metadata And Filtering
Metadata is not required to prove the first pilot, but the design should leave
room for it.

Useful later metadata includes:

- document type
- author
- year
- journal or source
- language/script hints
- domain tags such as astronomy, Ayurveda, philosophy

If Open WebUI metadata filtering is limited, the repo should still preserve a
clean metadata sidecar so that later custom retrieval paths are not blocked.

## Persistence And Operations
Open WebUI's vector store must be treated as disposable unless persistence is
configured deliberately.

Operational requirement:

- the pilot must document where Knowledge data lives;
- container restart should not silently destroy the indexed corpus if the user
  expects persistence;
- re-ingest should be easy enough that loss of index state is recoverable.

## Scale Path

### Stage 1
Pilot with the audited 29-document Markdown set that is already trustworthy
enough for manual inspection.

### Stage 2
Expand the Markdown corpus only after:

- chunking behavior is acceptable;
- retrieval quality is believable on the fixed query set;
- ingest/refresh steps are documented and reproducible.

### Stage 3
Decide whether Open WebUI remains sufficient or whether Patra Darpan should own
a custom retrieval/index pipeline with tighter control over:

- chunk identity
- metadata filters
- evaluation
- citation surfaces
- reindex automation

## Acceptance Criteria
This milestone passes when:

- a pilot Markdown corpus can be ingested into Open WebUI locally;
- Open WebUI uses Ollama-hosted `bge-m3` embeddings successfully;
- Gemma 4 can answer against retrieved Patra Darpan context locally;
- a fixed query set exists and is documented in the repo;
- pilot retrieval quality is reviewed against expected source documents;
- the ingest/re-ingest workflow is documented clearly enough to reproduce;
- persistence expectations and limitations are documented honestly.

## Risks
- Markdown quality may still be too uneven for stable chunking.
- Open WebUI chunking controls may be too coarse for verse/commentary-heavy
  material.
- Embedding quality for Sanskrit and transliterated vocabulary may be weaker
  than expected.
- Manual upload flow may not scale beyond the pilot set.
- A good Open WebUI demo may hide missing evaluation rigor unless the harness is
  written down in the repo.

## Decision Points After Pilot
- keep Open WebUI as the main local retrieval surface for a while;
- keep Open WebUI for ad hoc exploration but build a repo-owned retrieval
  pipeline for serious evaluation;
- switch embedding model if the multilingual alignment tests are weak;
- introduce a corpus export step that prepares RAG-specific Markdown or metadata
  bundles instead of uploading raw working files.
