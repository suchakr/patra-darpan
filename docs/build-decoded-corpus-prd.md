# Build Decoded Corpus PRD

## Purpose

Move Patra Darpan PDF extraction from exploration runs to a durable generated
corpus artifact.

The goal is a stable directory tree of Markdown documents, media, manifests,
and quality signals for PDFs in the corpus. This tree is consumed by future
indexing, retrieval, and web projections. It is not the raw Decode Lab run
directory.

## Background

Current Decode Lab output lives under:

```text
.build~/decode-lab/<run-id>/by-doc/<doc-id>/document.md
```

This served exploration well, but it is not a stable application contract:

- `<run-id>` is execution history, not corpus identity.
- The same `doc_id` can appear in many runs.
- Apps should not know which run "won".
- `.build~` is disposable run evidence.
- Repair/resume artifacts should not leak into consumers.

## Decision Summary

- Durable artifact root: `decoded-corpus/`.
- Decode Lab run root remains `.build~/decode-lab/`.
- Source corpus remains `corpus/`.
- `decoded-corpus/` is not tracked in git initially.
- Media is copied into the durable artifact, not symlinked to `.cache/`.
- Web does not read directly from `decoded-corpus/`; it consumes later
  projections.
- One canonical decoded artifact per `doc_id` at first.
- First priority corpus: `astro-math-indic`.

## Directory Contract

```text
decoded-corpus/
  README.md
  manifest.jsonl
  audit.md
  by-doc/
    <doc-id>/
      document.md
      manifest.json
      quality.json
      source.pdf -> ../../../corpus/...
      media/
        p0007_fig01.jpg
        p0008_fig02.jpg
        p0001_page.png
```

`document.md` is the canonical readable Markdown extraction for the document.

`manifest.json` records provenance, including source PDF, source checksum,
extractor, model, prompt hash, run ID, generation timestamp, and artifact paths.

`quality.json` records extraction warnings and quality signals, such as failed
chunks, unresolved figure placeholders, `<<<CONTINUE>>>` markers, and other
known repair/audit signals.

`media/` contains copied media files used by `document.md`. The name is broader
than `images/` because the directory may later include figure crops, page scans,
table crops, and related media.

Top-level `manifest.jsonl` contains one row per built document so agents and
applications do not need to crawl the tree.

## Build Command

The build command is:

```bash
uv run python scripts/build_decoded_corpus.py --from-run <run-id>
```

`build_decoded_corpus.py` builds the durable corpus artifact from accepted
Decode Lab outputs.

Default behavior:

- Read `.build~/decode-lab/<run-id>/by-doc/<doc-id>/document.md`.
- Copy `document.md` into `decoded-corpus/by-doc/<doc-id>/`.
- Copy media into `decoded-corpus/by-doc/<doc-id>/media/`.
- Create a `source.pdf` symlink to the original corpus PDF.
- Write per-doc `manifest.json`.
- Write per-doc `quality.json`.
- Update top-level `manifest.jsonl`.
- Update top-level `audit.md`.
- Refuse to overwrite existing built docs.

Explicit replacement modes:

```bash
uv run python scripts/build_decoded_corpus.py \
  --from-run repair-run \
  --replace-doc Vol43_4_1_PGondhalekar
```

```bash
uv run python scripts/build_decoded_corpus.py \
  --from-run astro-math-indic-50-3flash-med-flex \
  --replace-set astro-math-indic-50
```

Destructive broad replacement should require an explicit `--force` if ever
added.

## Cache Semantics

Gemini response cache should identify semantic output, not execution SLA.

Current cache identity includes:

```text
config_name + model_name + service_tier + prompt + PDF bytes
```

Desired cache identity:

```text
config_name + model_name + prompt + PDF bytes
```

`service_tier` should remain in metadata, but not in the cache key, because it
is expected to control SLA/routing rather than output semantics.

Patch plan:

1. Look up the new tierless key first.
2. On miss, look up legacy tier-specific keys such as `flex` and `standard`.
3. If a legacy hit is found, copy it lazily into the new tierless cache file.
4. Future runs reuse the tierless key.

This avoids a one-time migration script and preserves existing cache value.

## Campaign Expansion

Campaign sets may be nested, for example:

```text
astro-math-indic-10 ⊂ astro-math-indic-50
```

If `astro-math-indic-10` runs first and `astro-math-indic-50` runs later with
the same model, prompt, PDF bytes, and cache key, the first 10 documents benefit
from Gemini response cache hits.

Earlier runner behavior before this build-corpus change:

- Reusing a `run-id` currently requires `--resume`, `--repair`, or `--force`.
- Completed documents are not skipped at document level today.
- Local profiling/image steps run again.
- Gemini chunks should be cache hits where the cache identity matches.
- Run-level JSONL and manifest files are rewritten for the selected set of the
  current invocation.

Desired generation behavior:

- Decode Lab generation runs are upsert-by-default.
- A `run-id` names a mutable work packet.
- Re-invoking the same `run-id` opens or creates that run.
- Completed documents are skipped.
- Partial or failed documents are retried/repaired.
- Missing documents are processed.
- Run-level JSONL and manifest files are regenerated from current run state.
- `--force` is the only whole-run destructive reset.
- `--resume` remains accepted as a compatibility alias, but is no longer
  required.

Batching behavior:

- `--batch-size N` means process the next N unfinished documents from the
  selected campaign set.
- The unfinished-doc filter happens before batch slicing.
- No `--batch-size` means process all unfinished documents in the selected set.

Desired usage:

```bash
GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --set astro-math-indic-50 \
  --run-id build-astro-math \
  --extractor gemini:3-flash-med \
  --tier flex \
  --batch-size 5 \
  --assemble

GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --set astro-math-indic-50 \
  --run-id build-astro-math \
  --extractor gemini:3-flash-med \
  --tier flex \
  --batch-size 15 \
  --assemble

GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --set astro-math-indic-50 \
  --run-id build-astro-math \
  --extractor gemini:3-flash-med \
  --tier flex \
  --assemble
```

This processes first 5 unfinished docs, then next 15 unfinished docs, then all
remaining unfinished docs.

Implemented runner behavior:

- Upsert-by-default run reuse.
- `--batch-size` / `--batch` for next-N unfinished docs.
- Document-level skip for successful docs inside an existing run.
- Keep failed/partial docs repairable from `extraction-state.json`.
- Keep expanded-set runs append-friendly without losing run evidence.

## Disk Space

Disk duplication is acceptable at first:

- `.cache/gemini/` stores API responses.
- `.cache/images/` stores reusable extracted images.
- `.build~/decode-lab/` stores run evidence.
- `decoded-corpus/` stores durable generated corpus output.

Do not make `.build~` or `.cache` link back to `decoded-corpus/`. Those
directories should remain disposable. The durable corpus should survive cache
cleanup and run cleanup.

If disk usage becomes painful later, prefer one of:

- content-addressed media inside `decoded-corpus/`,
- hardlinks during build,
- explicit dedupe tooling.

Avoid ownership inversion between cache/build artifacts and decoded corpus
artifacts.

## Initial Workflow

1. Patch Gemini cache to tierless identity with lazy legacy promotion.
2. Update `scripts/run_decode_lab.py` for upsert-by-default run reuse and
   `--batch-size`.
3. Implement `scripts/build_decoded_corpus.py`.
4. Build already-good `astro-math-indic-10`.
5. Inspect `decoded-corpus/` manually.
6. Generate, decode, and build `astro-math-indic-50`.
7. Decide whether `decoded-corpus/` should remain untracked, partly tracked, or
   externally stored after the 50-doc/full astro-math-indic experience.

## Non-Goals For First Pass

- No vector database selection.
- No graph database selection.
- No web UI consuming raw `decoded-corpus/`.
- No multiple decoded variants per document.
- No attempt to track full generated corpus in git before campaign evidence.
