# Work Plan: Local RAG via Open WebUI and Ollama

## Status
Proposed

## Objective
Turn the local Open WebUI + Ollama setup into a repeatable Patra Darpan pilot
RAG workflow without creating a new branch or worktree structure.

The work should stay on the current branch unless a later implementation phase
becomes risky enough to justify isolation.

Exploratory artifacts should be isolated in a dedicated disposable subfolder so
the experiment is easy to discard or promote selectively.

## Phase 1: Define The Pilot Corpus
Deliverable:
- a named pilot Markdown set for local RAG ingestion

Tasks:
- use `decode-lab/sets/audit-set.txt` as the default pilot corpus
- confirm the 29-document audited set is coherent enough for manual retrieval
  review
- document the source path and refresh path for that set
- decide whether the pilot input is existing Markdown directly or a derived
  export bundle for RAG

Exit criteria:
- the pilot corpus is explicitly the audited set unless a documented debug
  subset is temporarily required

## Phase 2: Define The Evaluation Set
Deliverable:
- a small query set with expected relevant documents

Tasks:
- create 10 to 20 benchmark questions
- mix English, IAST, and hybrid queries
- record expected relevant `doc_id` values
- include a few failure-sensitive cases where superficial lexical similarity is
  not enough

Exit criteria:
- retrieval quality can be discussed against a stable benchmark

## Phase 3: Validate Open WebUI Ingestion
Deliverable:
- a documented ingestion path into Open WebUI Knowledge

Tasks:
- confirm `bge-m3` works through Ollama for embeddings
- create or document the Open WebUI Knowledge collection for the pilot corpus
- verify documents are indexed successfully
- document chunk-size and overlap settings used for the pilot
- document persistence expectations for the Docker setup

Exit criteria:
- the same pilot set can be ingested again without guesswork

## Phase 4: Run Retrieval Review
Deliverable:
- a short report against the benchmark queries

Tasks:
- run the benchmark queries in Open WebUI
- record which documents/chunks appear relevant
- note obvious chunking failures, language-alignment failures, and false hits
- compare whether mixed-register queries perform better than plain English where
  expected

Exit criteria:
- there is written evidence that the stack is either usable, weak, or blocked

## Phase 5: Tighten Corpus Packaging
Deliverable:
- a clearer RAG-facing corpus package if the raw Markdown is not good enough

Tasks:
- decide whether filenames, frontmatter, or body structure need normalization
- preserve `doc_id` and provenance more explicitly if Open WebUI obscures them
- adjust the Markdown export strategy if verse/commentary chunking is poor

Exit criteria:
- the ingestion artifact is shaped intentionally for retrieval, not accidentally

## Phase 6: Decide The Next Architecture Step
Deliverable:
- a go/no-go decision for scaling beyond the pilot

Decision options:
- continue with Open WebUI as the practical local retrieval surface
- keep Open WebUI for ad hoc use but build a repo-owned indexing/evaluation
  path
- change embedding model and rerun the benchmark before scaling
- stop and improve Markdown quality before further RAG work

## Implementation Notes
- Do not treat Open WebUI storage as canonical corpus state.
- Keep benchmark definitions and findings in the repo.
- Avoid full-corpus ingest until the pilot benchmark is credible.
- Prefer one clear current-branch effort over new branch/worktree churn for this
  phase.
- Keep disposable experiment artifacts under `scratch~/local-rag-openwebui/`.
- Promote only durable outputs later, such as refined docs, reports, scripts, or
  set definitions.

## Immediate Next Step
The next concrete task should be Phase 1 plus Phase 2 together:

- use the audited 29-document set as the pilot Markdown set
- define the benchmark query set

That creates the minimum substrate needed before spending time on ingestion
tuning.
