# Patra Darpan: Indexing & Graph Strategy Notes

**Date:** 2026-04-21  
**Context:** Design conversation on embedding strategy, graph visualization, and Obsidian as a knowledge layer for the patra-darpan pipeline.

---

## Corpus Scale (Clarified)

- **Total IJHS corpus:** ~2,000 papers
- **Math/Astro/Indic subset:** ~430 papers — this is the **validation target**
- **Active working set:** 11 documents — used to fix pipeline issues and UX before scaling up
- All pipeline and UX decisions should be validated against the 11-doc set first, then the 430-paper subset, before full corpus indexing.

---

## Obsidian as a Knowledge Layer

Obsidian is a local-first, Markdown-based PKM app. Its graph links notes via `[[wikilinks]]`. Relevant to patra-darpan because:

- Assembled `.md` files from the pipeline are a natural vault — each paper is a note
- Citation links → `[[wikilinks]]`, concept tags → Obsidian tags
- Entity aliasing handles the IAST / Devanāgarī / anglicised form problem (e.g. `[[nakṣatra]]` with aliases)
- A shared vault = shareable structured mental model, useful for CAHC collaborators

### Graph is Document-Level (Coarse)

Obsidian's graph links are at **file/document level** — too coarse for a research corpus where the meaningful unit is often a section or passage.

Sub-document mechanisms exist but have tradeoffs:
- **Block references** (`[[note^blockid]]`) — precise but requires stable IDs embedded in markdown; adds pipeline complexity
- **Heading links** (`[[note#Heading]]`) — low friction, sections already exist in assembled `.md` files
- **Dataview plugin queries** — concept-tag notes can embed live queries pulling paragraphs corpus-wide; closer to what's needed for fine-grained retrieval

**Conclusion:** Graph = navigation/orientation (the map). Semantic search = precision retrieval (the microscope). Both are needed; neither replaces the other.

---

## Embedding Strategy: Reject Naive Chunking

### The Problem with Arbitrary Token-Window Chunks

- A 512-token mid-paragraph chunk has no identity — not human-navigable, not citable
- Retrieval returns a fragment with no sense of its position in the paper
- Adjacent chunks may score independently but their meaning is relational
- No provenance: *embeddings without structure are retrieval without provenance*

### Section-Level Indexing (Preferred)

Index at **Markdown section granularity**, not token-window granularity.

Each embedding unit is a triple:
```
(paper_id, heading_path, section_text)
```

**Why this is better:**
- The heading is the human-readable handle — citable and displayable
- Sections have **authorial coherence** — the author decided this was a unit of thought
- **Text flow adjacency is preserved** — §3 is known to follow §2; context is reconstructable
- Retrieval returns a section, not a fragment — displayable with neighbors in the UI

### Adjacency Matters for This Corpus

IJHS papers on Sanskrit astronomical texts often build arguments across consecutive sections — a result in §3 depends on a definition in §2. Section-level chunking preserves sibling relationships under the same heading hierarchy. The pipeline must store and surface this adjacency, not just the matched section.

---

## Frontend (Netlify SPA)

- Graph *can* be embedded — export link structure as JSON, render with Cytoscape.js or Sigma.js
- **Prerequisite:** Quality audit on assembled `.md` files must come first — a graph of noisy data is worse than no graph
- **Sequencing:**
  1. Audit `.md` quality on 11-doc working set
  2. Emit citation + concept-tag adjacency as static JSON at build time
  3. Add graph view to Netlify SPA as navigation layer over existing search

---

## Action Items

- [ ] Section splitter: parse assembled `.md` files into `(paper_id, heading_path, section_text)` triples
- [ ] Validate section boundaries on 11-doc working set — check heading coverage and coherence
- [ ] Embed at section level; store `heading_path` and `(prev_section, next_section)` as metadata alongside vector
- [ ] Retrieval response must include: paper title, section heading, section text, adjacent section titles
- [ ] UX: display retrieved section in context — show prev/next section headings as navigation affordance
- [ ] Graph JSON: nodes = papers, edges = citation links + shared concept tags
- [ ] Defer graph view on Netlify until `.md` audit is complete on working set
