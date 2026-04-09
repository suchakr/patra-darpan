# PRD: Spasta Corpus

## Status
Draft

## Owner
Patra Darpan / CAHC corpus engineering

## Summary
`spasta-corpus` is an isolated corpus assembly feature for Patra Darpan. It exists to introduce a clean internal authority layer over a historically messy but still functional corpus pipeline, while preserving compatibility with current Patra Darpan consumers until the new system is proven.

`spasta-corpus` does not replace the live Patra Darpan flow immediately. It runs in isolation, reuses the existing local PDF asset store under the live repo's `corpus/{ijhs,other}`, and produces canonical assembled outputs plus compatibility projections.

The goal is not to pretend the old system was clean. The goal is to preserve the real history of that system as design context, then build a cleaner assembly layer that can authoritatively represent the corpus without duplicating binaries or destabilizing the live checkout.

Companion technical design:
- [docs/spasta-corpus-technical-design.md](docs/spasta-corpus-technical-design.md)

## Problem Statement
Patra Darpan's current corpus pipeline works, but its authority model is accidental.

The current corpus emerged from a sequence of practical expansions:
- PDFs and metadata scraped from a portal source, with IJHS as the first implemented example
- LLM-enriched metadata such as subject/category classification
- CAHC-authored assets that also happened to appear in IJHS
- curated CAHC PDFs from other journals or institutional portals not yet covered by portal ingest
- URL-only assets that are part of the scholarly corpus but do not exist as locally managed PDFs

Those expansions were reasonable, but they accumulated into a system where:
- `corpus/ijhs.tsv`, `corpus/ijhs-classified.tsv`, and `corpus/index.tsv` each carry part of the corpus story
- generated and operational files have partially become de facto authority
- ingestion, enrichment, curation, storage, and serving are mixed together
- Patra Darpan and GCS sync depend on overlapping but not identical views

This makes the system hard to reason about and creates concrete risks:
- it is unclear which layer has final authority when fields disagree
- identity is too easy to infer from URLs, filenames, or current TSV shape
- migration is risky because consumers are tied to projections that were never designed as explicit contracts
- extending the corpus model tends to create one more sidecar file rather than a principled schema change

The problem to solve is not "replace TSV with SQLite." The problem is to establish a canonical assembly layer with explicit source-of-truth boundaries, while preserving compatibility with the historically evolved pipeline and its shared binary asset store.

## Historical Context And Baggage
The current state is the result of several reasonable local optimizations made at different times, and this PRD intentionally preserves that history rather than erasing it.

1. Patra Darpan began as a focused IJHS access layer: scrape INSA metadata, download PDFs, and present them through a more navigable interface.
2. Classification was added later, producing enriched metadata in a separate file rather than replacing the original scrape store.
3. Scope then expanded from "IJHS access layer" to "CAHC corpus," pulling in CAHC-authored and CAHC-relevant material beyond IJHS.
4. Those new materials did not arrive in one uniform form. Some were already present as IJHS PDFs, some were local PDFs from elsewhere, and some existed only as external URLs.
5. Integration happened through pragmatic scripts and manual curation loops rather than through an explicit domain model.
6. Over time, operational outputs began to function as authority surfaces, even when they were originally only intermediate or consumer-facing artifacts.

This produced a historically layered, not cleanly designed, pipeline:
- `corpus/ijhs.tsv` is the scraped-plus-patched base metadata store for IJHS and some imported additions.
- `corpus/ijhs-classified.tsv` adds LLM enrichment but is still not the whole corpus.
- `corpus/index.tsv` is the current unified projection used by downstream consumers, but it is simultaneously acting as an operational master index.
- `web/assets/js/data.js` is a serving projection derived from that chain.
- `corpus/ijhs/` and `corpus/other/` function as the effective shared binary asset store, even though the binaries are not git-managed here.

The existence of `pipeline/02-patch.py` is especially revealing. It is not just an ugly step; it is evidence that the old pipeline lacked two explicit layers:
- deterministic normalization of source-specific quirks
- explicit curated overrides for exceptional human corrections

In other words, the "patch" phase is historically understandable, but it is architecturally underspecified. It mixes concerns that should be distinct in `spasta-corpus`.

This messiness is not an embarrassment to hide. It is the reason `spasta-corpus` exists. The new design must be understandable in direct relation to this history:
- the old pipeline remains the source of migration inputs
- the old projections remain compatibility surfaces for some time
- the old binary asset layout remains in place
- but the old layering must stop being the long-term authority model

## Why Now
The current approach is becoming structurally limiting.

It is difficult to safely add richer document information over time, including:
- text extracts
- curated notes and snippets
- chunk-level content
- embeddings or vector metadata
- processing status per document
- new asset/link types beyond PDFs

Without a canonical corpus model, each such addition will either be bolted into a TSV not designed for it, or introduced as another sidecar flow with unclear authority.

## Goals
- Define a canonical corpus assembly layer separate from the legacy write path.
- Preserve compatibility with current Patra Darpan consumers during migration.
- Reuse the existing local PDF asset store under the live repo's `corpus/{ijhs,other}` without duplicating binaries.
- Support multiple entry types including local PDFs and URL-only corpus entries.
- Make the write path explicit: source inputs -> assembly -> validation -> projections.
- Create a schema that can grow to include extracted content, derived features, chunk metadata, and vectors.
- Make the feature worktree-friendly so it can be developed without destabilizing the live checkout.
- Preserve the historical baggage explicitly so later maintainers understand why the architecture is layered this way.

## Non-Goals
- Immediate replacement of the live Patra Darpan deploy flow.
- Re-homing or duplicating the existing PDF binaries.
- Solving all historical metadata quality issues in phase 1.
- Immediate migration of every existing script to the new pipeline.
- Introducing vector search or retrieval features in the initial assembly milestone.
- Pretending the legacy pipeline can be cleanly rewritten in one pass.

## Users And Stakeholders
- Maintainer of Patra Darpan corpus and ingestion flows.
- Future tooling that may consume enriched document metadata or embeddings.
- Reviewers who need a clear explanation of corpus authority and transition risk.

## Proposed Direction
`spasta-corpus` is a new corpus assembly layer with canonical internal authority and explicit compatibility projections.

### Core Principle
Preserve legacy projections, replace legacy authority.

The new system may continue to emit TSV or JSON shapes that older consumers expect, but those are projections of a canonical assembled corpus rather than the primary editable store.

### Design Principles
- Preserve the historical pipeline as migration input and design context, not as the new authority model.
- Keep source-specific ingest logic separate from canonical assembly logic.
- Support different ingest workflows, especially portal ingest and curated ingest, with a shared downstream contract.
- Replace the vague notion of "patching" with explicit normalization and explicit curated overrides.
- Treat consumer-facing exports as projections with explicit contracts.
- Keep storage/location properties distinct from document identity.
- Make worktree isolation and shared-binary reuse first-class constraints, not implementation details.

## Authority Boundaries
The PRD should make source-of-truth boundaries explicit.

### Canonical Authority
The canonical assembled corpus is the internal authority for document identity, normalized metadata, asset references, and projection generation.

### Editable Inputs
Editable and consumable source inputs remain source-specific and may be machine-captured, pipeline-derived, or curator-authored. Examples:
- portal-ingest metadata as source capture, with IJHS as the first implemented portal
- classification or other derived input built from portal-ingest metadata
- curated PDF metadata for one-off or not-yet-automated sources
- curated URL-only entry metadata
- curated overrides needed to resolve identity or projection issues

### Non-Authority Outputs
The following are outputs, not canonical editable stores:
- web JSON for Patra Darpan
- compatibility TSV exports
- deploy artifacts such as `data.js`

### Important Rule
URL, filename, current TSV row order, and `gcs_key` are storage or projection properties, not primary identity.

## Isolation And Shared Asset Model
`spasta-corpus` should be developed and stabilized in an isolated feature branch and worktree.

Recommended setup:
- Live checkout: `/Users/sunder/projects/patra-darpan`
- Feature branch: `feat/spasta-corpus`
- Feature worktree: `/Users/sunder/projects/patra-darpan-spasta-corpus`
- Shared binary asset root used by feature code: `/Users/sunder/projects/patra-darpan/corpus`

The new pipeline must not assume that the local binary corpus sits inside the same checkout where the assembly code runs. The corpus root must be configurable.

The live repo remains the owner of the shared binary asset store. This worktree consumes that store but must not copy it into the feature checkout, regenerate it into a second location, or silently drift into a competing asset root.

## Binary Asset Reuse
`spasta-corpus` does not duplicate PDFs already present in the live repo under:
- `corpus/ijhs/*.pdf`
- `corpus/other/*.pdf`

Instead, it references them as canonical local assets using metadata such as:
- `asset_id`
- owning `doc_id`
- local relative path from configured corpus root
- storage class
- file size
- checksum when available
- mapped `gcs_key` when relevant
- availability status

This is an intentional split:
- document identity belongs to the canonical corpus model
- asset location belongs to the asset reference model

One document may have zero, one, or multiple access paths over time. The model should not assume that one filename or one URL permanently defines the document.

## Canonical Layers
The new design separates six layers. The point is to describe corpus roles, not to freeze the current IJHS-first script order into the new architecture.

### 1. Source Inputs
These are explicit upstream feeds into canonical assembly. They are not necessarily hand-authored, and they are not themselves the canonical corpus.

Examples:
- portal-ingest metadata as machine-captured source input, with IJHS as the first implemented portal source
- classification output as pipeline-derived input from portal-ingest metadata
- curated PDF metadata for non-INSA PDFs, which currently correspond to PDFs under `corpus/other`
- curated external link metadata
- curated overrides

Portal ingest and curated ingest may have different upstream workflows, but they should converge on the same downstream contract: explicit source records that can be normalized, curated, assembled, validated, and projected.

Working phase-1 assumption:
- portal-ingest metadata is captured from the source web page into the normalized source schema
- curated PDF metadata may be bootstrapped by extracting comparable metadata from the PDF itself, likely from the first page or leading pages, before review
- model-assisted extraction or review may propose metadata or override candidates, but canonical authority still comes only from accepted source inputs and explicit curated overrides

### 2. Normalization
Normalization is deterministic cleanup of known source quirks.

Examples:
- whitespace cleanup
- journal or issue identifier normalization
- author-string cleanup
- URL cleanup
- year parsing
- source-field mapping into a normalized intermediate form

Normalization replaces the mechanical part of today's `02-patch.py`. It should be rule-based, reviewable, and rerunnable. It should not depend on ad hoc in-place edits to a file that is simultaneously being treated as a source of truth.

Working phase-1 normalization minimums should include:
- trimming and null/empty normalization
- conservative author/title cleanup
- journal and issue label normalization
- URL normalization for comparison and dedupe
- boolean-field normalization
- year parsing when reliable
- normalization of machine-extracted PDF metadata into the same intermediate shape used by portal-ingest metadata

### 3. Curation
Curation is for explicit human corrections and overrides that cannot be derived mechanically.

Examples:
- resolving duplicate intellectual works across sources
- correcting bibliographic fields when the source is wrong
- recording corpus-inclusion decisions
- setting CAHC-specific flags or notes that are curator-authored rather than scraped

Curation must live in explicit override inputs, not as silent in-place mutation of a generated TSV.

Working rule:
- curation may override descriptive metadata, flags, inclusion decisions, and projection-relevant fields
- routine curation should not silently rewrite `doc_id`
- identity merges or rekeys belong to explicit assembly/identity handling, not everyday metadata correction
- model-generated review or override suggestions are advisory until accepted into explicit curated override inputs

### 4. Enrichment
Enrichment adds derived metadata that is not source-native and not part of deterministic cleanup.

Examples:
- subject/category classification
- future extracted text metadata
- chunk metadata
- embeddings and processing status

### 5. Assembly
A single assembly pipeline merges normalized sources, curated overrides, and enrichments into a canonical corpus model.

Assembly is where:
- source rows become canonical documents
- duplicate or related source records are resolved
- canonical IDs are assigned or mapped
- asset references are attached
- projection-specific quirks are intentionally excluded

### 6. Validation And Projection
The assembled corpus is checked for:
- identity conflicts
- missing required fields
- ambiguous source merges
- path inconsistencies
- duplicate asset references
- projection readiness

The system emits consumer-facing artifacts such as:
- web JSON projection for Patra Darpan
- compatibility TSV exports

Validation and projection are grouped here because both operate on assembled canonical state rather than on raw source-specific state.

## Execution Model
`spasta-corpus` should behave like a repeatable, dependency-aware build pipeline rather than a one-off sequence of scripts.

The expected stage order is:
1. ingest source feeds
2. normalize changed inputs
3. apply curated overrides
4. run dependent enrichments
5. assemble canonical corpus state
6. validate canonical corpus state
7. project consumer-facing outputs
8. rebuild affected search sidecars if enabled

The required properties are:
- repeatable: rerunning with unchanged inputs produces the same results
- idempotent: rerunning does not duplicate state or drift outputs
- incremental: a change in one source feed should only dirty dependent downstream artifacts
- dependency-aware: enrichments and projections should only rerun when their declared inputs change

Examples of intended incremental behavior:
- a new portal PDF or metadata row should only trigger dependent normalization, enrichment, assembly, and projection work for affected documents
- a new curated PDF record should not require reprocessing unrelated portal-ingest records
- a new URL-only entry should not trigger PDF extraction work
- a changed local PDF checksum should invalidate extraction-, chunk-, and embedding-derived sidecars for the affected `doc_id`

Operationally, the build system should support force semantics at sensible scopes such as:
- one `doc_id`
- one source feed or source group
- one canonical selector such as `entry_type=pdf` or another supported field/query filter
- whole-corpus rebuild

## Naming And Organization Principles
The new vocabulary should avoid making IJHS look like the universe of the system.

The naming rule is:
- source-specific logic should be named by source
- corpus-wide logic should be named by function
- no globally central component should have an IJHS-shaped name unless it is actually IJHS-only

This implies a conceptual organization like:
- `sources/` for source adapters such as portal ingest, curated ingest, and external-link imports
- `normalize/` for deterministic source cleanup
- `curate/` for explicit human override inputs
- `enrich/` for classification and future derived metadata
- `assemble/` for canonical corpus construction and validation
- `project/` for Patra Darpan and legacy compatibility exports

The current scripts map into this model approximately as follows:
- `pipeline/01-scrape.py` is the first implemented portal-ingest adapter and should remain explicitly IJHS-specific in role unless generalized to other portals
- `pipeline/02-patch.py` should be decomposed conceptually into normalization rules and curated overrides
- `pipeline/03-classify.py` belongs to enrichment, not to the definition of the core pipeline
- `ops/migrate_index.py` is either assembly or legacy projection depending on whether it constructs canonical corpus state or only emits old-shaped outputs

This is not only a naming cleanup. It is how the PRD avoids encoding today's historical script sequence as tomorrow's architecture.

## Canonical Schema Direction
The internal assembled artifact may be stored as SQLite for maintainability and extensibility.

Preferred internal artifact:
- `spasta-corpus.sqlite`

Preferred web/deploy projection:
- `patra-darpan.json`

Optional compatibility projections:
- `exports/index.tsv`
- `exports/ijhs.tsv`
- `exports/ijhs-classified.tsv` if a downstream transition period still requires it

Rationale:
- SQLite is better suited for growth into richer metadata, processing status, chunks, and vectors.
- JSON is easier for Netlify/web projection.
- TSV remains useful as a compatibility export, not as the canonical authority.

This PRD does not require SQLite specifically if another internal representation proves clearly better, but it does require one canonical assembled authority that is richer and more explicit than today's TSV chain.

Working assumption:
- `spasta-corpus.sqlite` is a generated canonical artifact and should not be git-managed by default
- generated JSON or TSV projections should also remain untracked by default
- if any generated artifacts are later git-managed for review or deployment convenience, they should be human-reviewable projections such as JSON or TSV rather than the canonical binary database

## Canonical Entity Expectations
The canonical model should support at least the following entities or equivalent tables/views.

### Document
- stable `doc_id`
- `entry_type` such as `pdf`, `link`, `html`
- normalized bibliographic metadata
- authorship and curation flags
- source provenance summary
- current workflow status fields

### Document Source Record
- source system or source file
- source-native key if any
- source row identity or import identity
- ingest timestamp or version marker when relevant
- source-specific raw or minimally normalized metadata

### Asset Reference
- stable `asset_id`
- owning `doc_id`
- local path if any
- remote URL if any
- `gcs_key` if any
- file metadata if available
- availability status
- role such as `primary_pdf`, `mirror_pdf`, `external_link`

### Enrichment
- classification fields
- notes on derivation/provenance
- future extraction/chunk/vector status

Important rule:
- `doc_id` identifies the intellectual corpus entry
- `asset_id` identifies a specific access/storage representation
- projection rows must be derivable from these, not treated as peers of them

Working phase-1 default:
- `entry_type` is sufficient as the top-level document discriminator
- finer distinctions should live in asset roles, provenance, enrichment payloads, projection logic, or later schema evolution if needed

## Source Categories To Support
The assembled corpus must support at least these source categories:
- portal-ingest PDFs and metadata, with IJHS as the first implemented example
- derived enrichments over portal-ingest records, including IJHS classification
- curated PDFs, which currently means non-INSA PDFs represented in `corpus/other`
- URL-only external corpus entries
- future curated content enrichments independent of source of acquisition

## Integration With Existing Systems
### Patra Darpan
Patra Darpan should eventually consume a projection of the assembled corpus rather than the current hand-shaped TSV chain.

The transition requirement is not "new data shape at any cost." The requirement is "new canonical authority, old UI compatibility until the switch is safe."

### GCS Sync
GCS sync should eventually validate or project against canonical assembled asset records rather than rely on an independent operational notion of what should exist.

## Migration Strategy
Migration should be additive, read-only first, and projection-driven.

### Phase 0 Assumption
The legacy pipeline remains the live system of operation during the initial `spasta-corpus` build-out.

### Migration Contract
- existing live inputs continue to exist
- shared PDFs remain in the live repo's asset store
- `spasta-corpus` reads legacy inputs and shared assets without mutating the live flow
- new projections are compared against existing consumer artifacts before any switchover
- legacy steps such as "patch" are treated as evidence of required normalization/curation behavior, not as canonical phase names to preserve forever
- portal-ingest and curated-ingest inputs should converge into the same downstream build contract

The primary migration validation target is `corpus/index.tsv`, which is the current unified projection consumed by `ops/build_data.py`. `corpus/ijhs.tsv` remains important as a source input and as a normalization check for portal-ingest behavior, but it is not the primary consumer-facing comparison target.

### Migration Objective
The first successful milestone is not full cutover. It is proof that one canonical assembly can reproduce the current consumer-relevant views closely enough to make migration decisions explicit.

### Cutover Standard
No consumer should switch to the new assembly layer until:
- required compatibility projections are defined
- validation failures are visible and actionable
- known identity edge cases are handled explicitly
- the shared asset-root configuration is stable in worktree use

## Constraints
- Existing PDFs in the live repo's `corpus/{ijhs,other}` are not git-managed here and must not be duplicated.
- The live Patra Darpan checkout must remain maintainable during feature development.
- The new feature must tolerate worktree-based development against a shared asset root.
- Netlify/web consumers are better served by JSON projections than SQLite directly.
- The document must preserve the historical messiness of the current pipeline as design context, not erase it.

## Risks
- Historical data will expose identity edge cases when normalized into a canonical model.
- Source-specific quirks may tempt reintroduction of ad hoc exceptions into the new assembly layer.
- If compatibility projections are underspecified, migration will stall because existing consumers cannot switch safely.
- If the canonical model is tied too closely to current filenames or URLs, future corpus growth will inherit today's accidental structure.
- If overrides are allowed without a clear layer, the new system will reproduce the same ambiguity under cleaner names.
- If the live repo and feature worktree disagree about corpus root or asset availability, migration validation will produce false confidence.

## Phase Plan
### Phase 1: PRD And Schema Framing
- Define the problem and authority boundaries.
- Define canonical concepts, projection strategy, and migration constraints.
- Agree on worktree and shared corpus-root topology.
- Decide the minimum source-input files required for curated PDFs, URL-only entries, and overrides.
- Define the vocabulary and directory organization so the new system is corpus-wide rather than implicitly IJHS-centric.
- Define the build graph and stage contracts so repeatable and incremental execution is explicit.

### Phase 2: Read-Only Assembly Prototype
- Build a prototype reader over existing source files and shared local assets.
- Assemble into a canonical model without changing the live flow.
- Validate assumptions against current `index.tsv` and serving outputs such as `data.js`.

### Phase 3: Canonical Projection
- Emit `patra-darpan.json` from the assembled corpus.
- Emit compatibility TSVs where needed.
- Compare outputs against current consumers and document deliberate differences.

### Phase 4: Integration
- Switch Patra Darpan build path to consume the new projection.
- Bring GCS validation/sync into consistency with canonical asset metadata.

### Phase 5: Enrichment Growth
- Add extracted content metadata.
- Add chunked content representations.
- Add embedding/vector metadata and processing status.

## Success Criteria
- A single canonical assembly process can represent the current corpus without manual edits to generated stores.
- The assembled corpus can project a Patra Darpan web artifact compatible with current UI needs.
- The new system can refer to shared local PDFs without duplicating them.
- The feature can be developed in its own worktree without destabilizing the live checkout.
- The design leaves room for future content extracts and vectors without redesigning the storage model again.

## Current Working Defaults
- `doc_id` should be a deterministic, stable, reasonably short string once assigned.
- For phase-1 portal-ingest IJHS entries, mint `doc_id` from `Path(gcs_key).stem`.
- For phase-1 curated PDF entries under `corpus/other`, mint `doc_id` from the local filename stem.
- For phase-1 URL-only entries, mint `doc_id` from a short source-prefixed slug derived from the normalized title.
- Append collision suffixes such as `-02`, `-03`, and so on only when an actual collision is observed.
- Once assigned, treat `doc_id` as canonical; do not casually re-derive it from storage properties later.
- `spasta-corpus.sqlite` should be treated as generated and not committed by default.
- Generated JSON and TSV projections should also remain untracked by default; that can be revisited later if review, deployment, or migration needs justify it.
- `entry_type` is adequate as the phase-1 top-level discriminator.
- Routine curation should not rewrite `doc_id`; identity merges and rekeys are explicit assembly-level actions.
- Local PDF checksum changes should invalidate extraction- and search-derived sidecars for the affected document, while URL-only entries should not trigger PDF-derived rebuilds.
- Force rebuild should support not only `doc_id` and source-feed scopes, but also small canonical selectors such as `entry_type` when operationally useful.

## Open Questions And Decisions Needed
- What exact curated metadata file or files should describe PDFs already present under `corpus/other`, URL-only assets, and manual overrides?
- Which validations are hard requirements in phase 1 versus advisory warnings?
- Which validations are strong enough to block projection output versus merely emit warnings?

## Decision Summary
Proceed with `spasta-corpus` as an isolated corpus assembly feature that:
- preserves historical context explicitly, including the current pipeline's messiness
- reuses the shared local PDF corpus in the live repo without duplication
- treats legacy TSVs and serving artifacts as migration inputs or compatibility surfaces rather than canonical authority
- establishes explicit authority boundaries between source inputs, canonical assembly, asset references, validation, and projections
- produces assembled outputs for future Patra Darpan integration
