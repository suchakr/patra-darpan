# Spasta Corpus Decisions

This file records important design and tactical decisions that are stable enough
to guide implementation, but do not all need to live in the PRD.

## 2026-04-08

### Decision: `corpus/` is root-input-only
Status: active

The feature worktree's `corpus/` directory is reserved for root inputs only.
Derived artifacts must not live there.

Rationale:
- keeps the assembly boundary legible
- prevents root inputs from being mixed with generated operational state
- makes it easier for both humans and agents to reason about what canonical
  assembly is allowed to read directly

### Decision: shared PDF assets remain external
Status: active

Shared PDF assets remain outside the feature worktree at:
- `/Users/sunder/projects/patra-darpan/corpus/ijhs/`
- `/Users/sunder/projects/patra-darpan/corpus/other/`

These are treated as read-only asset roots from the point of view of
`spasta-corpus`.

Rationale:
- avoids duplication of binaries
- preserves the live repo as the owner of the shared asset store
- allows the feature worktree to evolve metadata and assembly logic without
  destabilizing asset storage

### Decision: `01-scrape.py` is pre-root-input, not part of `spasta-corpus`
Status: active

`pipeline/01-scrape.py` is treated as an upstream refresh utility that can
populate the `ijhs.tsv` root input, but it is not part of the
`spasta-corpus` pipeline contract.

Rationale:
- keeps canonical assembly independent of network and Selenium flakiness
- lets `spasta-corpus` stay responsible only for normalization onward
- preserves a clean boundary between upstream refresh and canonical build

### Decision: current root metadata set
Status: active

Current root metadata inputs in the feature worktree are:
- `corpus/ijhs.tsv`
- `corpus/cahc_authored_registry.txt`
- `corpus/cahc-pdf-mirrors.tsv`
- `corpus/curated-pdfs.tsv`
- `corpus/curated-links.tsv`

Current non-root migration reference files are:
- `reference/legacy/ijhs.tsv`
- `reference/legacy/ijhs-classified.tsv`
- `reference/legacy/index.tsv`

Rationale:
- `ijhs-classified.tsv` is derived enrichment over `ijhs.tsv`
- `index.tsv` is a legacy projection and migration comparison artifact

### Decision: current messy `ijhs.tsv` is migration baggage, not target shape
Status: active

The current `main` branch has a historically messy layout in which `ijhs.tsv`
acts as a sum of portal-derived metadata and additional non-IJHS metadata
imported through legacy flows.

The cleanup direction in `spasta-corpus` is:
- keep `ijhs.tsv` as portal-derived root metadata
- move curated non-IJHS local PDF metadata into `curated-pdfs.tsv`
- move curated URL-only metadata into `curated-links.tsv`
- retain pre-cleanup legacy TSVs under `reference/legacy/` for comparison

Rationale:
- preserves compatibility with the current world while making the target input
  model explicit

### Decision: narrow CAHC authorship patch remains separate for now
Status: active

`cahc_authored_registry.txt` remains a narrow manual patch input for CAHC
authorship tagging. A general-purpose override file is deferred.

Rationale:
- avoids overlapping `curated-overrides.tsv` with an already existing narrow
  patch mechanism
- keeps phase-1 input concepts small

### Decision: CAHC mirror URLs are a separate root input
Status: active

CAHC-managed mirror URLs are stored in `corpus/cahc-pdf-mirrors.tsv` with
columns:
- `source_url`
- `mirror_url`

Rationale:
- keeps mirror information out of row-level metadata TSVs
- makes mirror relationships explicit and reviewable
- maps naturally to multiple asset references per document

### Decision: root metadata TSVs may be smaller than legacy index.tsv
Status: active

The root metadata files are intentionally cleaner than `reference/legacy/index.tsv`.
The canonical build is responsible for reconstructing a legacy-compatible
projection.

Current root shapes are:
- `corpus/ijhs.tsv`
  - `journal, paper, url, size_in_kb, author`
- `corpus/curated-pdfs.tsv`
  - `journal, paper, url, size_in_kb, year, author`
- `corpus/curated-links.tsv`
  - `journal, paper, url, year, author`

Additional rules:
- IJHS `year` is derived from the journal naming convention during assembly
- `cahc_authored` is inferred from `corpus/cahc_authored_registry.txt`
- mirror URLs are inferred from `corpus/cahc-pdf-mirrors.tsv`

Rationale:
- avoids duplicated root facts when a field is safely derivable
- keeps root inputs closer to the real source distinctions
- preserves compatibility pressure in the projection layer, where it belongs

### Decision: derived artifact directory roles
Status: active

The feature worktree uses these directory roles:
- `corpus/`
  root inputs, git-managed
- `.build~/`
  generated machine state, not git-managed
- `exports/`
  generated text projections, git-managed when useful
- `reports/`
  generated text validation outputs, git-managed when useful
- `reference/legacy/`
  legacy comparison artifacts, git-managed
- `scratch~/`
  ephemeral helpers and one-off work, not git-managed

Rationale:
- gives every artifact class a home
- keeps machine clutter out of git
- preserves human-reviewable text outputs and comparison fixtures

### Decision: initial durable script names
Status: active

The first durable phase-1 script names are:
- `scripts/build_corpus_metadata.py`
- `scripts/export_index_tsv.py`
- `scripts/validate_legacy_index.py`

Rationale:
- `build_corpus_metadata.py` is more precise than `build_corpus.py` for the
  current phase
- `export_index_tsv.py` is clear and output-specific
- `validate_legacy_index.py` is durable because legacy comparison artifacts are
  intended to live under `reference/legacy/`

### Decision: use a flat `scripts/` plus `lib/` layout at phase 1
Status: active

The phase-1 code layout is intentionally flat:
- `scripts/`
  thin runnable entrypoints
- `lib/`
  shared implementation code and non-entrypoint assets such as `schema.sql`

Nested package structure such as `spasta_corpus/`, `sources/`, or `db/` is
deferred until the code volume clearly justifies it.

Rationale:
- keeps the first implementation legible
- avoids introducing framework-like structure before the pipeline itself is
  stable
- cleanly separates runnable entrypoints from reusable code without extra
  hierarchy

### Decision: all project Python execution uses `uv run python`
Status: active

All project Python commands must be run through `uv` rather than ambient system
Python.

Examples:
- `uv run python scripts/build_corpus_metadata.py`
- `uv run python scripts/export_index_tsv.py`
- `uv run python scripts/validate_legacy_index.py`

Rationale:
- keeps the execution environment reproducible
- avoids accidental dependence on system-installed packages
- makes clone-to-clone behavior more stable for both humans and agents

## Open Tactical Items

These are important, but not yet fixed enough to promote to decisions:
- whether `exports/` and `reports/` should always be committed or only selected
  files should be tracked
