# Grant Semantic Demo PRD

## Purpose

Surface a small, credible Patra Darpan decoded-corpus search demo for the Google
Cloud Research Credits proposal.

The demo should prove that Patra Darpan already has:

- a roughly 2,000-record source corpus;
- a working decoded-corpus pilot;
- searchable decoded text with cited, inspectable chunks and source provenance.

The first implementation is lexical-first and static. Here, lexical means
keyword and phrase retrieval over decoded text chunks, with transparent scoring
and citations. This is not the final semantic-search experience.

The v1 demo is better described as lexical retrieval over semantic-ready decoded
chunks. It validates the corpus, citation, artifact, and UX contract that
semantic/vector search will reuse.

Embeddings and managed semantic search are the next layer. Whether that layer
ships before the grant proposal or after it remains an explicit planning
decision.

## Starting Scope

Use the audited decoded pilot, not the full corpus.

Inputs:

```text
decode-lab/sets/audit-set.txt
decoded-corpus/manifest.jsonl
decoded-corpus/by-doc/<doc-id>/manifest.json
decoded-corpus/by-doc/<doc-id>/quality.json
decoded-corpus/by-doc/<doc-id>/document.md
```

Current evidence at PRD time:

- `decoded-corpus/manifest.jsonl` contains 43 decoded documents.
- `decode-lab/sets/audit-set.txt` contains 18 manually audited documents.
- `decoded-corpus/audit.md` reports 43 ok docs and 0 errors after recent
  repairs.

Grant/demo wording should avoid overclaiming. Prefer:

> 43-document processing pilot, with 18 manually audited documents.

## User Goals

A scholar or reviewer should be able to:

- search across decoded document text;
- see ranked chunks, not only whole-document cards;
- inspect enough surrounding text to trust the hit;
- see title, author, year, document ID, heading path, and source provenance;
- open the source PDF where available;
- understand that this is a pilot Search Lab, not the final production semantic
  search system.

## Safety Gate: JS CLI/TUI First

Before adding the browser UX, validate retrieval behavior through a local JS
CLI/TUI application.

This gate exists to test the corpus projection, chunking, scoring, snippets, and
metadata contract without changing the Netlify-facing app first.

Target commands:

```bash
node tools/search-lab/search-cli.mjs --help
node tools/search-lab/search-cli.mjs "Yājñavalkya cycle"
node tools/search-lab/search-cli.mjs --interactive
node tools/search-lab/search-cli.mjs --json "Saptarṣi era"
```

The CLI/TUI should use the same search-core module that the browser will later
use, so CLI validation is directly relevant to the web experience.

## Artifact Design

Keep corpus metadata, lexical search behavior, and future vector data decoupled.

Initial stable artifact:

```text
web/assets/data/search-corpus.json
```

This file contains document metadata plus cited chunks. It is the durable
contract for lexical search and the browser UI.

Future optional artifacts:

```text
web/assets/data/lexical-index.json
web/assets/data/vector-manifest.json
web/assets/data/vectors/*.jsonl
```

Future embedding/vector artifacts should reference `chunk_id`. They should not
duplicate full document metadata or become the source of truth for titles,
authors, provenance, or quality flags.

This allows:

- rebuilding lexical indexes without changing the corpus projection;
- rebuilding embeddings without changing UI metadata;
- testing alternate search backends against the same chunk contract;
- moving vectors to Vertex AI Search or another hosted service later.

## Chunk Contract

Each chunk should have a stable, deterministic shape:

```json
{
  "chunk_id": "Vol28_1_2_SCKak:c0007",
  "doc_id": "Vol28_1_2_SCKak",
  "title": "Astronomy of the Satapatha Brahmana",
  "author_display": "Subhash C Kak",
  "year": "1993",
  "journal_label": "IJHS-28-1993-Issue-1",
  "source_url": "https://...",
  "gcs_key": "ijhs/Vol28_1_2_SCKak.pdf",
  "quality_status": "ok",
  "quality_warnings": ["continue_marker", "figure_resolved_page_render"],
  "heading_path": ["7. THE SEVEN ṚṢIS AND THE SAPTARṢI ERA"],
  "chunk_ordinal": 7,
  "prev_chunk_id": "Vol28_1_2_SCKak:c0006",
  "next_chunk_id": "Vol28_1_2_SCKak:c0008",
  "text": "...",
  "text_preview": "..."
}
```

`chunk_id` is the join key for all future search, vector, and evaluation
artifacts.

## Section And Context Strategy

Prefer Markdown section granularity when the section is coherent and not too
large. The meaningful retrieval unit should be a citable passage with a
human-readable heading, not an arbitrary token-window fragment.

Rationale:

- the heading path is the human-readable address of the hit;
- sections often preserve the author's unit of thought;
- adjacent sections frequently carry definitions, setup, or consequences needed
  to understand a result;
- the same structure supports lexical search now and embeddings later.

Each chunk should preserve local context:

- `heading_path`: the current section address;
- `prev_chunk_id`: previous searchable unit in the same document, when present;
- `next_chunk_id`: next searchable unit in the same document, when present;
- `chunk_ordinal`: deterministic document-local order.

The CLI/TUI validation gate should inspect section boundaries, heading coverage,
and neighboring headings. This keeps the first web demo citable and
human-navigable before embeddings are introduced.

Graph and Obsidian-style navigation are useful later, but they are not v1
requirements. The pre-embedding takeaway is to preserve heading structure,
adjacency, and provenance in static JSON. A future graph projection can derive
nodes and edges from citations, headings, concept tags, and document metadata
after the Markdown quality audit is strong enough.

## Chunking Rules

Start simple and deterministic:

- parse Markdown linearly;
- preserve nearest heading path;
- remove internal HTML provenance comments from searchable text;
- split on Markdown headings and paragraph blocks;
- merge paragraph blocks into roughly 500-1200 word chunks when possible;
- keep section boundaries when they are clear;
- preserve tables as searchable text;
- do not require page-perfect citation for v1.

Acceptable v1 citation:

- document ID;
- title, author, year;
- heading path;
- source PDF URL or GCS-backed source link;
- chunk ordinal.

Page hints are useful if recoverable from figure/page markers, but they are not
required for the lexical demo.

## Search Behavior

The first search implementation is lexical: keyword and phrase search over the
decoded chunk text and selected metadata fields.

Lexical search demonstrates value because it proves that the decoded pilot has
usable text, deterministic chunks, source provenance, and a scholar-facing
retrieval workflow. Semantic search depends on these foundations; embeddings
without trustworthy chunk boundaries and citations would not be credible.

Expected scoring:

- case-insensitive token matching;
- exact phrase boost;
- title, author, and heading boosts;
- higher score for multiple query terms in the same chunk;
- snippets with highlighted matched terms;
- deterministic ordering for equal scores.

No API calls, embeddings, backend service, or credentials are required for v1.

Semantic search is deferred for v1 because it adds inference and operations
complexity:

- embedding generation requires model calls and batch rebuilds;
- vector artifacts need model/version/dimension/chunk-hash provenance;
- vector data should be decoupled from metadata and joined by `chunk_id`;
- browser-only vector search may work for a tiny pilot but does not represent
  the likely production architecture;
- hosted semantic search introduces indexing, auth, refresh, cost, and
  evaluation concerns.

The intended sequence is:

1. lexical pilot now: decoded corpus, cited chunks, static demo, provenance;
2. semantic layer next: attach embeddings or vector IDs to the same `chunk_id`
   contract and compare ranking against lexical smoke queries;
3. cloud scale later: use Google Cloud credits for full decoding, embedding
   generation, managed semantic retrieval, and evaluation.

## Web UX

The web surface should be additive.

Add a new static Search Lab page:

```text
web/search-lab.html
```

The existing `web/index.html` paper browser should remain unchanged in behavior.
After CLI/TUI validation, the main app may add a small link to the Search Lab,
but the search lab should not replace the current title/author browser.

The Search Lab should show:

- a query input;
- pilot corpus stats;
- ranked cited chunks;
- title, author, year;
- matched excerpt;
- `doc_id` and heading path;
- quality warning badge when present;
- source PDF action when available.

For v1, cited chunk text in the result payload plus a source PDF link is enough.
A full decoded Markdown viewer can be added later if the demo needs deeper
inspection.

## Static Deployment Fit

The v1 demo must work as static Netlify content:

- no server-side search endpoint;
- no client-side secrets;
- no CORS-sensitive fetches;
- no embedding generation at runtime;
- artifacts generated offline and committed or deployed with `web/`.

The existing Netlify PDF access strategy can continue to handle source PDFs.

## Proposed Build Command

Add a corpus projection builder:

```bash
uv run python scripts/build_search_index.py --help
uv run python scripts/build_search_index.py --set audit-set
```

`audit-set` is the initial validation target, not an implementation boundary.
The builder and UI should be corpus-size agnostic.

Expected corpus selection modes:

```bash
uv run python scripts/build_search_index.py --set audit-set
uv run python scripts/build_search_index.py --set astro-math-indic-10
uv run python scripts/build_search_index.py --doc-id Vol28_1_2_SCKak
uv run python scripts/build_search_index.py --all-decoded
```

Expected outputs:

```text
web/assets/data/search-corpus.json
reports/search-smoke.md
```

The script should fail clearly if an audit-set document is missing from
`decoded-corpus/manifest.jsonl` or lacks `document.md`.

The generated corpus artifact should include build metadata such as selected
sets, selected document IDs, decoded-corpus root, generated timestamp, document
count, and chunk count. The web UI must read these fields rather than assuming
an 18-document corpus.

## Discovery And Inventory

Every new command-line entry point must support `--help` with examples and
plain descriptions of inputs, outputs, and selection modes.

Required discovery commands:

```bash
uv run python scripts/build_search_index.py --help
node tools/search-lab/search-cli.mjs --help
```

Keep the v1 source surface small:

```text
scripts/build_search_index.py       # offline corpus projection
web/assets/js/search-core.js        # shared lexical scoring/snippets
tools/search-lab/search-cli.mjs     # local validation CLI/TUI
web/search-lab.html                 # additive browser surface
web/assets/js/search-lab.js         # optional page glue if needed
web/assets/css/search-lab.css       # optional page styles if needed
```

Add a short implementation note only if the source surface grows beyond this
inventory or if responsibilities become unclear. Preferred location:

```text
docs/search-lab-implementation-note.md
```

That note, if needed, should be an inventory and comprehension aid, not a second
PRD.

## Implementation Plan

Phase 1: projection builder.

- Add `scripts/build_search_index.py`.
- Provide `--help` with examples.
- Support `--set`, repeated `--set`, repeated `--doc-id`, and `--all-decoded`.
- Default initial run uses `--set audit-set`.
- Join each `doc_id` against `decoded-corpus/manifest.jsonl` and per-doc
  `manifest.json` / `quality.json`.
- Parse `document.md` into section-first cited chunks.
- Record `heading_path`, `chunk_ordinal`, `prev_chunk_id`, and `next_chunk_id`.
- Record build metadata so the web UI does not assume a fixed document count.
- Write `web/assets/data/search-corpus.json`.
- Write `reports/search-smoke.md` after running the smoke query set.

Phase 2: shared JS search core.

- Add `web/assets/js/search-core.js`.
- Implement query normalization, tokenization, lexical scoring, phrase boost,
  metadata boosts, result sorting, and snippet highlighting.
- Keep the module browser-safe and Node-compatible so the CLI and web page use
  the same ranking behavior.

Phase 3: JS CLI/TUI validation.

- Add `tools/search-lab/search-cli.mjs`.
- Provide `--help` with examples.
- Support one-shot query mode.
- Support `--json` output for reproducible checks.
- Support `--interactive` for local review before changing the web UX.
- Show heading path and neighboring headings so section coherence can be
  reviewed.
- Use `web/assets/data/search-corpus.json` and `web/assets/js/search-core.js`.

Phase 4: static web Search Lab.

- Add `web/search-lab.html`.
- Add a small page-specific script and styles only if needed.
- Load `web/assets/data/search-corpus.json`.
- Render pilot stats, query input, ranked cited chunks, snippets, quality
  badges, neighboring context links, and source PDF actions.
- Read artifact metadata for document and chunk counts; do not assume the
  audit-set size.
- Keep `web/index.html` behavior unchanged.

Phase 5: additive link from existing app.

- After CLI/TUI and Search Lab validation, add a small Search Lab link from the
  existing web surface.
- Do not merge chunk search into the current title/author paper browser in v1.

Phase 6: semantic-next design.

- Define `web/assets/data/vector-manifest.json` with `chunk_id` joins.
- Record embedding model, vector dimensions, chunk text hash, generation time,
  and backend reference.
- Run semantic ranking against the same smoke query set before exposing it in
  the UI.

Phase 7: graph/navigation-next design.

- Defer graph rendering until decoded Markdown quality is validated.
- Consider a static graph projection where nodes are documents, headings,
  citations, or concept tags.
- Treat graph as navigation and orientation, not as the precision retrieval
  mechanism.

## Smoke Queries

Use domain queries likely to hit the audited pilot:

- `Yājñavalkya cycle`
- `Saptarṣi era`
- `pandiagonal magic square`
- `Nārāyaṇa Paṇḍita magic square`
- `Vedāṅga Jyotiṣa solstice`
- `intercalary month Vedic texts`
- `Sūrya Siddhānta planetary nodes`
- `Jñānarāja sine table`
- `Yuktibhāṣā Jyesthadeva`
- `circle square conversion Sundararaja`

`reports/search-smoke.md` should record:

- query;
- top result title and `doc_id`;
- chunk heading;
- score;
- short snippet;
- whether the result is credible enough for demo use.

## Non-Goals For V1

- full 2,000-document decoded search;
- embedding generation;
- Vertex AI Search integration;
- relevance tuning beyond simple lexical scoring;
- page-perfect citations;
- in-browser Markdown rendering of every decoded document;
- replacing the existing Patra Darpan paper browser.

## Acceptance Criteria

- A JS CLI/TUI can search the generated artifact and return cited chunks.
- Corpus metadata and future vector artifacts are decoupled by `chunk_id`.
- The browser Search Lab is additive and does not alter existing app behavior.
- The static web page can run from `web/` with a simple local HTTP server.
- Smoke queries produce plausible top results and are recorded in a report.
- The demo copy clearly says pilot/Search Lab and does not imply production
  semantic search is complete.

## Open Questions

- Should v1 publish sanitized full decoded Markdown files under `web/assets/`,
  or are cited chunks plus source PDF links sufficient for the grant demo?
- Should `search-corpus.json` include all 43 decoded docs or only the 18 audited
  docs? Current default should be the 18-doc audit set.
- Should the CLI/TUI be plain Node.js only, or can it use a small dependency for
  interactive selection if already available locally?
