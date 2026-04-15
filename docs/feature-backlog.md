# Feature Backlog

This file tracks candidate features that are valuable enough to remember, but
not yet committed enough to become design decisions or active implementation.

Each feature block should stay short and operational.

## Template

### Feature: <name>
Status: proposed

Problem:
- what concrete pain or confusion this feature removes

Users:
- who benefits directly

Proposed shape:
- what the feature roughly does

Why now / later:
- why it is worth remembering now
- why it is not already implemented

Notes:
- constraints, non-goals, or open questions

## Backlog

### Feature: Guided add-item workflow
Status: proposed

Problem:
- adding a new paper or article currently requires remembering too many moving
  parts
- maintainers and agents must know which TSV to edit, where the PDF should
  live, when mirror metadata is needed, and which rebuild steps to run
- the README now explains the workflow honestly, but the workflow itself still
  feels heavier than it should

Users:
- maintainers adding new IJHS PDFs
- maintainers adding new curated PDFs
- maintainers adding new URL-only articles
- AI agents asked to "add this new item"

Proposed shape:
- provide a small guided helper for adding one new item
- let the helper choose among:
  - IJHS PDF-backed item
  - curated PDF-backed item
  - URL-only item
- have it generate or append the right metadata row
- optionally update:
  - `corpus/cahc-pdf-mirrors.tsv`
  - `corpus/cahc_authored_registry.txt`
- remind or assist with PDF placement in the shared asset root
- optionally run the standard follow-up commands:
  - canonical build
  - `index.tsv` export
  - audit
  - Patra Darpan `data.js` export

Why now / later:
- worth capturing now because the current add-item path is a recurring source
  of cognitive load
- not yet implemented because the current priority has been making the
  root-input and projection contracts explicit first

Notes:
- should reduce operator burden without hiding root-input concepts completely
- should not silently mutate unrelated metadata
- may start as a single script and later become a more guided tool if needed

### Feature: Card link-source chips
Status: proposed

Problem:
- current card behavior can be hard to interpret because the UI chooses among
  `url`, `ju_url`, `localPath`, and `gcs_key` based on runtime mode without
  showing that choice clearly
- even maintainers can find it hard to understand which endpoint a click will
  use

Users:
- Patra Darpan readers
- maintainers reviewing local vs Netlify behavior
- AI agents validating the web UX

Proposed shape:
- show compact chips on each card for the relevant link targets, such as:
  - `INSA`
  - `JU`
  - `Local`
  - `GCS`
  - `URL`
- visibly highlight the currently preferred target in the active mode
- never light up `Local` in deployed Netlify mode

Why now / later:
- worth capturing now because the link model is now explicit enough to improve
  the UX safely
- not yet implemented because the runtime behavior and documentation needed to
  be clarified first

Notes:
- this is a UX feature, not a metadata feature
- should be designed after local and Netlify behavior are verified to be
  trustworthy

### Feature: Clean full paths out of generated reports
Status: proposed

Problem:
- some generated reports still contain machine-specific absolute paths
- those paths are noisy in git history and misleading after merge or clone
- the durable docs are being cleaned up, but the generated artifacts still lag

Users:
- maintainers reviewing reports across machines
- AI agents relying on report text after clone or merge

Proposed shape:
- make report generators prefer repo-relative paths or durable sibling-checkout
  wording where possible
- keep absolute machine paths out of human-facing report output unless the path
  itself is the subject of the report

Why now / later:
- worth capturing now because the durable docs have already moved to
  merge-safe wording
- not yet implemented because report cleanup is lower priority than making the
  main pipeline and docs truthful

Notes:
- generated reports do not need the same level of polish as primary docs
- some reports may still need exact paths for debugging, so this should be
  handled selectively rather than by blanket stripping

### Feature: Decode Lab CONTINUE marker classification
Status: proposed

Problem:
- Gemini MEDIUM extraction can emit `<<<CONTINUE>>>` at chunk boundaries even
  when the text resumes cleanly in the next chunk
- the marker is noisy in assembled `document.md`
- blindly deleting it would hide a real truncation signal when content is
  actually missing

Users:
- maintainers reviewing Decode Lab Markdown outputs
- agents comparing extraction quality across Gemini model presets
- future indexing code that should not ingest unresolved extraction markers

Proposed shape:
- classify each marker as one of:
  - fatal truncation
  - handled chunk-boundary continuation
  - duplicate reference-tail noise
  - retry/split needed
- remove or replace handled markers in `document.md` with a quiet provenance
  comment
- avoid duplicate chunk-local reference blocks when the real references section
  appears later
- record marker evidence in provenance, likely `fallbacks.jsonl` or a small
  `continuations.jsonl`

Why now / later:
- worth capturing now because `3-flash-med` has emitted markers in multiple
  successful-looking runs, while `3-flash` HIGH did not show the marker for at
  least AKBag pages 1-5
- not implemented now because the current priority is validating Flex and the
  micro-set extraction path rather than polishing assembler noise

Notes:
- known example: `Vol01_1_8_AKBag` under `flex-micro2-3flash-med` has a
  marker after an incomplete phrase, but the sentence resumes in the next chunk
  and references are repeated later
- this is not considered blocking for micro-set exploration
