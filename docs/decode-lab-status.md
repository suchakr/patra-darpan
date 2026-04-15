# Decode Lab Status

## Purpose
This document records where the Darpan Decode Lab stands as of 2026-04-15.
It covers the layered extraction architecture, what has been built and proven,
and what remains before the micro-5 corpus can produce faithful Markdown
representations of each PDF.

The design contract, output schema, and acceptance criteria live in
[docs/pdf-decoding-lab.md](pdf-decoding-lab.md).  This document is the
progress companion.

## Goal
Produce a Markdown representation of each PDF in the corpus that contains:
- Prose text blocks (English and Indic, with correct IAST diacritics)
- Tables (structured, preserving Greek letters and Sanskrit terms)
- Image references (with page and bounding box provenance)
- Honest gap markers where extraction failed

## Architecture Layers

### Layer 1: Deterministic baseline — DONE
Local Poppler CLI tools extract text and metadata from each PDF.
No network, no API calls, runs in ~2 seconds for the micro-5 set.

Tools: `pdfinfo`, `pdffonts`, `pdfimages -list`, `pdftotext -layout`,
`pdftotext -bbox-layout`.

Produces per page:
- `pages/p0001.txt` — extracted text
- `pages/p0001.risks.jsonl` — risks detected on this page
- `pages/p0001.blocks.jsonl` — PyMuPDF spans (empty unless fitz available)

Produces per document:
- `extractors/` — raw tool outputs
- `profile.json` — extraction status and tool verdicts
- `review.md` — human-readable diagnostic summary

Produces per run:
- `documents.jsonl`, `pages.jsonl`, `chunks.jsonl`, `risks.jsonl`,
  `images.jsonl`, `tables.jsonl`, `fallbacks.jsonl`,
  `retrieval-samples.jsonl`, `run-manifest.json`, `audit.md`

### Layer 2: Risk detection — DONE
Flags pages and fonts where the extracted text is untrustworthy.
Risk types detected:
- `control_characters` — garbled Indic/Sanskrit text from broken font maps
- `font_missing_unicode_map` — fonts that lack Unicode mapping tables
- `low_text_density` — scanned or raster pages with little/no text layer
- `private_use_glyphs` — Unicode Private Use Area characters

### Layer 3: Table candidate detection — DONE
Detects table regions in the extracted text using caption and layout heuristics.
Enriched metadata includes:
- `caption` — the table caption line
- `extent_line_start` / `extent_line_end` — text line range
- `data_row_count` — estimated data rows
- `bbox` — approximate bounding box in PDF points from `pdftotext -bbox-layout`

### Layer 4: Gemini PDF-native extraction — DONE
Sends the source PDF directly to Gemini (not rendered PNGs) with a
page-range prompt derived from AI Studio experimentation.  Processes
documents in 5-page chunks.  Model presets:

- `flash-lite` — Gemini 2.5 Flash Lite, no thinking (~$5.65/corpus)
- `flash` — Gemini 2.5 Flash, built-in thinking
- `3-flash` — Gemini 3 Flash Preview, HIGH thinking (~$43/corpus)
- `3-flash-med` — Gemini 3 Flash Preview, MEDIUM thinking (**recommended default**)

The prompt handles both born-digital and scanned PDFs uniformly:
IAST diacritics, Devanagari script, Greek letters, LaTeX math,
table structure, footnotes, and figure placeholders with `figure-meta`
annotations for image matching.

Each chunk produces two fallback records (Gemini + nakṣatra lookup)
with SHA-256 provenance chain.  All calls are disk-cached by
SHA-256(config_name + model_name + prompt + PDF bytes).

Runner integration: `--extractor gemini:3-flash-med` (recommended),
`gemini:flash-lite`, `gemini:flash`, or `gemini:3-flash`.
Default: `--extractor local` (deterministic only).

### Layer 5: Image extraction — DONE
Extracts figures from PDFs and caches them globally.

**Native PDFs** (like `1.pdf`): `pdfimages -j` extracts embedded JPEGs.
Stencils/watermarks filtered by file type (PBM = stencil, skip).
For `1.pdf`: 3 figure JPEGs extracted (p07, p08, p10), 12 watermarks skipped.

**Scanned PDFs** (like AKBag): each page rendered to PNG at 150 DPI
via `pdftoppm`.  For AKBag: 7 page PNGs extracted.

Image cache: `.cache/images/<doc_id>/`.  Keyed by doc_id, extracted
once per PDF content (SHA-256 manifest).  Run directories symlink
`by-doc/<doc_id>/images/` to the cache.  No duplication across runs.

Gemini prompt produces figure placeholders with metadata:
```
![caption](figure-N-placeholder)
<!-- figure-meta: page=N, position=top|middle|bottom, type=graph|diagram -->
```
Assembler post-processing replaces placeholders with real cached paths:
`![caption](images/p07_fig01.jpg)`

Image naming: `p<page>_fig<N>.<ext>` (per-page numbering).
For scanned pages: `p<page>_page.png`.

### Layer 6: Document-level Markdown assembly — DONE
Assembles one `document.md` per PDF from run artifacts.

When Gemini page-chunk extracts exist (from `--extractor gemini:*`),
uses them directly as the primary content source — concatenated in
chunk order with metadata header.

Otherwise falls back to per-page pdftotext assembly with:
- Spliced fallback table text where accepted
- Table candidate annotations where no fallback
- Risky-span markers around garbled text
- Extraction-gap comments for unresolved risks
- Image reference comments

Runner integration: `--assemble` flag (after extraction) or
`--assemble-only` flag (re-assemble a previous run).

## Current Dev Workflow

```bash
# Profile all primary PDFs locally and refresh planning reports
uv run python scripts/profile_pdfs.py

# Smoke the all-doc default path without profiling the whole corpus
uv run python scripts/profile_pdfs.py --limit 5 --progress-every 1

# Profile a reusable campaign set
uv run python scripts/profile_pdfs.py --set micro-2

# Generate a campaign set from metadata + profile hints
uv run python scripts/generate_campaign_sets.py astro math indic raster native 10 --name astro-math-indic-10

# Deterministic pass only (no API calls, ~2 seconds for micro-5)
uv run python scripts/run_decode_lab.py --run-id my-run

# Deterministic pass over a reusable campaign set
uv run python scripts/run_decode_lab.py --set micro-2 --run-id local-micro2 --assemble

# Recommended: Gemini 3 Flash with MEDIUM thinking + assembly
GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --run-id my-run --extractor gemini:3-flash-med --assemble

# Best quality (HIGH thinking, slower, ~3x cost)
GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --run-id my-run --extractor gemini:3-flash --assemble

# Re-assemble a previous run without re-extracting
uv run python scripts/run_decode_lab.py --assemble-only --run-id my-run

# Inspect results
cat .build~/decode-lab/my-run/audit.md
cat .build~/decode-lab/my-run/by-doc/1/document.md
ls  .build~/decode-lab/my-run/by-doc/1/images/

# Self-documenting help
uv run python scripts/run_decode_lab.py --help
```

## Micro-2 Eval Results (1.pdf + AKBag)

Validated with both `3-flash` (HIGH) and `3-flash-med` (MEDIUM):

| doc_id | Pages | Chunks | Figures extracted | Image cache |
| --- | --- | --- | --- | --- |
| `1` | 12 | 3 | 3 JPEGs (Fig 1-3, 628-728KB) | `.cache/images/1/` |
| `Vol01_1_8_AKBag` | 7 | 2 | 7 page PNGs (scanned) | `.cache/images/Vol01_1_8_AKBag/` |

Figure placeholders replaced with real cached paths in `document.md`.

## Full Local PDF Profile Results

Completed on 2026-04-15 with:

```bash
uv run python scripts/profile_pdfs.py --run-id full-local-profile-20260415 --progress-every 25
```

Results:

| Metric | Count |
| --- | ---: |
| Primary PDF assets | 2004 |
| Profiled assets | 2004 |
| Failed assets | 0 |
| `digital` | 960 |
| `raster` | 983 |
| `mixed` | 53 |
| `unknown` | 8 |

Outputs:

- `reports/pdf-profile.tsv`
- `reports/pdf-profile-audit.md`
- `.build~/pdf-profile-runs/full-local-profile-20260415/`

All Gemini token counts remain unknown until explicitly populated with
`profile_pdfs.py --token-count gemini`.

## Proven Recipes

### Gemini table extraction (tested on 3 tables, 2 PDFs)
- Combined correction+extraction prompt handles both corruption patterns
  without modification
- Nakṣatra lookup covers ~40 known OCR/encoding variants
- Greek letters (α β γ δ ε ζ η λ) correctly resolved by the prompt
- IAST vowel diacritics (ā ī ū) preserved by Gemini
- IAST underdot consonants (ṛ ṇ ṣ ṭ ḍ) need the lookup for ~6 names per table
- Multi-row headers preserved when markdown syntax is suppressed in the prompt

### Tesseract (tested, rejected for this use case)
- `san` and `san+hin` models hallucinate Devanagari over Latin text
- `Devanagari` script model recovers structure but drops all diacritics and
  mangles Greek letters
- Useful finding: this corpus is predominantly Latin+IAST+Greek, not native
  Devanagari script

## Risk Priority (revised 2026-04-14)

With `--extractor gemini:3-flash`, all risk types are resolved in a single
pass.  The Gemini PDF-native extraction handles born-digital garble,
scanned pages, and table structure uniformly.  Risk detection (Layer 2)
remains useful as a baseline diagnostic but is no longer the gating
factor for extraction quality.

## Model Selection (decided 2026-04-14)

Eval compared `3-flash` (HIGH thinking) vs `3-flash-med` (MEDIUM thinking)
on micro-2 (`1.pdf` + AKBag):

| Metric | HIGH | MEDIUM |
| --- | --- | --- |
| IAST nakṣatra names | 8/8 correct | 8/8 correct |
| Devanagari chars (pages 1-5) | 1041 | 1057 |
| IAST diacritics (pages 1-5) | 488 | 485 |
| document.md size (1.pdf) | 65.2K | 65.2K |
| API time (5 chunks) | ~9 min | ~3 min |

Decision: **`3-flash-med` (MEDIUM thinking) is the corpus-scale default.**
Same quality as HIGH at lower cost and 3× faster.  HIGH is available
via `--extractor gemini:3-flash` for specific documents if needed.

## Gemini Response Cache (decided 2026-04-13, implemented)

All Gemini calls are disk-cached.  Cache key: SHA-256 of
(config_name + model_name + prompt + PDF bytes).  The config name
is included to differentiate thinking levels on the same model
(e.g. `3-flash` vs `3-flash-med` on `gemini-3-flash-preview`).

Cache location: `.cache/gemini/<sha256_prefix>.json`.
Re-runs with the same config and PDF are free.

## Current Design Decisions (updated 2026-04-15)

- Campaign sets are tracked text files under `decode-lab/sets/`.
- `micro-2` and `micro-5` are campaign sets, not hidden runner constants.
- Run IDs are execution labels; they are not `doc_id`s and not campaign set definitions.
- `run_decode_lab.py` defaults to the `micro-5` campaign set.
- `profile_pdfs.py` defaults to all primary PDF assets because profiling is cheap planning infrastructure.
- SQLite is canonical for PDF profile state: `asset_refs` file facts plus `pdf_profiles`.
- `reports/pdf-profile.tsv` and `reports/pdf-profile-audit.md` are regenerated projections for humans and agents.
- `.cache/pdf-profiles/` is only for reusable expensive calls such as Gemini token counts; it is safe to delete.
- `.build~/pdf-profile-runs/<run_id>/` is optional run evidence/debug output; it is not canonical and not a cache.
- Gemini token counting is opt-in via `profile_pdfs.py --token-count gemini`.
- Campaign set generation reads `exports/index.tsv` for `subject/category`
  and joins it to SQLite `primary_pdf_profiles`.
- `subject/category` remain projection-time enrichment, not first-class
  SQLite columns.
- Generated campaign sets refuse to overwrite existing `.txt` or `.notes.md`
  files unless `--force` is supplied.

## Files Added or Modified

### New tracked files
- `decode-lab/sets/README.md` — campaign set contract
- `decode-lab/sets/micro-2.txt` — two-document confidence set
- `decode-lab/sets/micro-5.txt` — first five-document Decode Lab set
- `decode-lab/sets/astro-math-indic-10.txt` — generated raster Indic Astronomy/Math set
- `decode-lab/sets/astro-math-indic-10.notes.md` — generated set rationale
- `lib/decode_lab/campaign_sets.py` — shared campaign set loader
- `lib/decode_lab/nakshatra_lookup.py` — canonical nakṣatra variant dictionary
- `lib/decode_lab/gemini_fallback.py` — legacy per-page PNG fallback pipeline
- `lib/decode_lab/gemini_extract.py` — PDF-native page-chunk extraction
- `lib/decode_lab/model_configs.py` — four Gemini model presets + prompt
- `lib/decode_lab/image_extract.py` — image extraction, caching, placeholder replacement
- `lib/decode_lab/assembler.py` — Markdown assembly from run artifacts
- `scripts/profile_pdfs.py` — local PDF profiling plus optional Gemini token counting
- `scripts/generate_campaign_sets.py` — exploratory campaign set generator
- `docs/decode-lab-status.md` — this document

### Modified tracked files
- `lib/decode_lab/runner.py` — `--extractor gemini:*`, `--fallback gemini`,
  `--assemble`, `--assemble-only`, and `--set` flags; image extraction +
  symlinks; model config logging in run-manifest.json and audit.md
- `lib/schema.sql` — `asset_refs` file facts, `pdf_profiles`, and
  `primary_pdf_profiles`
- `scripts/run_decode_lab.py` — assembly and extractor CLI integration

### Untracked scratch evidence
- `scratch~/decode-lab/fallback-experiment-2026-04-13/` — raw experiment artifacts

## Next Steps
1. Run Gemini token count for `astro-math-indic-10`
2. Decode `astro-math-indic-10` with `gemini:3-flash-med --tier flex`
3. Generate broader `astro-math-full` / `astro-math-10` campaign sets
4. Handle `<<<CONTINUE>>>` truncation detection before corpus scale
5. Prepare for corpus-scale run: estimate cost, plan batching, verify
   cache behaviour across the full 2004-PDF corpus
6. Design the chunk-to-search pipeline: how `document.md` feeds into
   FTS5/vector indexing for the Spasta Corpus search sidecars
