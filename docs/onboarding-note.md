# Patra Darpan Semantic Index — Onboarding Note

## Snapshot — 2026-04-15

Current working branch/worktree: `feat/pdf-semantic-index` in
`/Users/sunder/projects/patra-darpan-pdf-semantic-index`.

This note is a handoff snapshot. The authoritative design contract is
`docs/pdf-decoding-lab.md`; the running progress log is
`docs/decode-lab-status.md`.

What is now in place:

- Campaign sets are tracked text files under `decode-lab/sets/`.
  `micro-2`, `micro-5`, and `astro-math-indic-10` are present.
- PDF profile state lives in SQLite via `asset_refs` file facts,
  `pdf_profiles`, and the `primary_pdf_profiles` view.
- Full local PDF profiling completed for all primary PDFs:
  - primary PDF assets: 2004
  - profiled assets: 2004
  - failures: 0
  - document types: `digital` 960, `raster` 983, `mixed` 53, `unknown` 8
- Profile reports are generated at `reports/pdf-profile.tsv` and
  `reports/pdf-profile-audit.md`.
- Campaign set generation is available:

```bash
uv run python scripts/generate_campaign_sets.py astro math indic raster native 10 --name astro-math-indic-10
```

The generator uses `exports/index.tsv` for `subject/category` and joins it
to SQLite `primary_pdf_profiles`. Positional words are hints; unique partials
such as `tab` -> `tables` are accepted. Existing `.txt` or `.notes.md` set
files are not overwritten unless `--force` is supplied.

Important commands:

```bash
uv run python scripts/build_corpus_metadata.py
uv run python scripts/profile_pdfs.py --progress-every 25
uv run python scripts/profile_pdfs.py --set micro-2
uv run python scripts/run_decode_lab.py --set micro-2 --run-id local-micro2 --assemble

GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --set micro-2 --run-id flex-micro2-3flash-med \
  --extractor gemini:3-flash-med --tier flex --assemble
```

Run repair semantics:

- Existing `--run-id` fails by default to protect evidence.
- Use `--resume` to continue/retry an interrupted run.
- Use `--repair` to reuse a run directory and fix failed/partial chunks.
- Use `--force` only when intentionally deleting/recreating the run.
- `--assemble` now assembles eagerly after each document. Use
  `--assemble --assemble-lazy` for the older batch-at-end behavior.

Current model decision: `gemini:3-flash-med` is the recommended default for
corpus-scale Decode Lab extraction. HIGH thinking remains available via
`gemini:3-flash` for hard documents.

Current caveats:

- Gemini token counts are still `NULL` unless explicitly populated with
  `profile_pdfs.py --token-count gemini`.
- `<<<CONTINUE>>>` marker classification is backlogged. The known examples
  appear to be chunk-boundary/reference-tail noise, but this should be
  classified before corpus-scale decode.
- `subject/category` are projection-time enrichment from `exports/index.tsv`,
  not first-class SQLite columns. For campaign set generation today, join
  `exports/index.tsv` to `primary_pdf_profiles`.

Recommended next workflow:

```bash
uv run python scripts/profile_pdfs.py --set astro-math-indic-10 --token-count gemini
GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --set astro-math-indic-10 \
  --run-id astro-math-indic-10-3flash-med-flex \
  --extractor gemini:3-flash-med --tier flex --repair --assemble
```

---

Hi Ramana. Here's what this project is, what we've built so far, and how
the extraction pipeline works.

## What is Patra Darpan?

Patra Darpan is a corpus of ~2000 academic papers from the Indian Journal
for History of Science (IJHS). The papers cover Indian astronomy,
mathematics, medicine, and related history of science topics. Many papers
contain Sanskrit verses, IAST transliteration with diacritics (ā ī ū ṛ ṣ ṭ),
Greek astronomical symbols (α β γ δ), tables with nakṣatra data, and
mathematical expressions.

The live site is a search/browse interface backed by metadata in TSV files.
The PDFs themselves live in a local corpus (`../patra-darpan/corpus/ijhs/`).

## What is the Semantic Index initiative?

We want to make the **content** of these PDFs searchable — not just the
metadata. That means extracting the text, tables, and images from each PDF
into a structured Markdown representation that can be indexed for search.

The challenge: the corpus spans 60 years (1966–2026). Older papers are
scanned raster images. Newer ones are born-digital but sometimes have
broken font mappings that garble Indic text. Some papers have complex
tables with mixed scripts.

## The Decode Lab

Before building a search index over 2000 PDFs, we built a small
extraction lab on a 5-PDF micro-set to figure out what works. The lab is
in this repo under `lib/decode_lab/`.

The 5 test PDFs:
- `1.pdf` — 2021 born-digital, good English but garbled Sanskrit footnotes
- `01_58_4.pdf` — 2023 born-digital, clean
- `Vol01_1_8_AKBag.pdf` — 1966 scanned, zero text layer
- `Vol26_1_1_KDAbhyankar.pdf` — 1991 scanned, zero text layer
- `Vol44_4_1_PGondhalekar.pdf` — 2009 born-digital, clean text with tables

## The Extractor Design Pattern

The key insight: **local deterministic tools first, then Gemini for what
they can't handle.**

### Step 1: Local baseline (always runs, free, instant)

```
pdfinfo     → page count, producer metadata
pdffonts    → font inventory, Unicode map flags
pdfimages   → image inventory (page, dimensions)
pdftotext   → text extraction per page + bounding boxes
```

This gives us text for born-digital PDFs and tells us exactly where the
problems are: which pages have garbled text (control characters), which
fonts are missing Unicode maps, which pages are scanned with no text.

### Step 2: Risk detection (deterministic)

Instead of silently indexing garbage, we flag it:
- `control_characters` — garbled Indic/Sanskrit text
- `low_text_density` — scanned pages with zero or near-zero text
- `font_missing_unicode_map` — suspect fonts
- `private_use_glyphs` — non-standard Unicode characters

### Step 3: Gemini extraction (on-demand, cached)

Send the **source PDF directly** to Gemini (not rendered images) with a
page-range prompt. Process in 5-page chunks. The prompt is tuned for
this domain:

- IAST diacritics: exact UTF-8 Unicode
- Devanagari: original script, not romanised
- Greek letters: preserved
- Math: LaTeX notation
- Tables: Markdown pipe syntax with multi-row headers
- Footnotes: `[^n]` Markdown syntax
- Figures: `![caption](placeholder)` with position annotation

Four model presets for cost/quality tradeoff:
- `flash-lite` — cheapest, ~$5.65 for the full corpus
- `flash` — balanced
- `3-flash` — HIGH thinking, best quality, slower/higher cost
- `3-flash-med` — MEDIUM thinking, current recommended default

### Step 4: Nakṣatra lookup (deterministic, free)

A small Python dictionary of ~40 known OCR/encoding variants for the
27 traditional nakṣatra names. Fixes things like `Krttikā → Kṛttikā`
that Gemini sometimes misses. Applied automatically after every Gemini
call.

### Step 5: Image extraction

Gemini identifies figures and produces `![caption](figure-N-placeholder)`
with a metadata annotation:

```
![Fig. 1 Yearly variation of the nakṣatra location error...](images/p07_fig01.jpg)
<!-- figure-meta: page=7, position=bottom, type=graph -->
```

The actual image files come from `pdfimages` (Poppler), not from Gemini.
Two cases:

- **Native PDFs**: real figures are separate JPEG objects in the PDF.
  Watermarks/logos filtered by size. Extract with `pdfimages -j`,
  match to Gemini placeholders by page number.
- **Scanned PDFs**: every page IS the image. The rendered page scan
  becomes the figure image. Caption tells the reader where to look.

Image cache: `.cache/images/<doc_id>/p07_fig01.jpg`. Extracted once per
PDF, shared across all runs. Run directories symlink to the cache.

### Step 6: Assembly

Concatenate the Gemini chunk outputs into one `document.md` per PDF.
This is what you read — a Markdown file with the full paper content.

## Table extraction outcomes

The nakṣatra table in `1.pdf` (27 rows, 11 columns, mixed IAST + Greek +
numerical data) was the hardest extraction target. We tested progressively:

1. **pdftotext baseline**: table structure detected (caption, bbox, 27 rows)
   but Indic text garbled as control characters, Greek letters missing.
2. **Tesseract**: `san` model hallucinated Devanagari over Latin text.
   `Devanagari` script model recovered structure but dropped all diacritics
   and mangled Greek letters (β→ß, δ→8, γ→y). Rejected.
3. **Gemini 2.0 Flash (plain prompt)**: recovered structure, but cedilla
   for ṣ (ş instead of ṣ), ß for β. Partial.
4. **Gemini 2.0 Flash (combined correction + extraction prompt)**: fixed
   all Greek letters. IAST vowel diacritics (ā ī ū) correct. Underdotted
   consonants (ṛ ṇ ḍ) still missed ~6 names.
5. **Nakṣatra lookup post-step**: deterministic fix for the remaining 6
   names. Final output: all 27 nakṣatra names correct IAST, all Greek
   letters correct, table structure preserved.
6. **Gemini 3 Flash with HIGH thinking**: produced correct IAST natively
   for most names. Lookup needed for only ~2-3 corrections. Also output
   Devanagari verses, LaTeX math, and proper footnote syntax.

Tested on 3 tables from 2 different PDFs with different corruption
patterns. The recipe generalises.

## What we learned

1. **pdftotext is excellent on clean born-digital PDFs.** 62% of the
   corpus is post-2000 and likely has good text layers. No need for
   Gemini on those unless they have font problems.

2. **Scanned PDFs need Gemini.** 25% of the corpus is pre-1990 raster.
   Gemini reads them well, including mathematical notation and Sanskrit.

3. **Broken font mappings are the hardest case.** Some born-digital PDFs
   have fonts that render correctly in viewers but produce control
   characters when text-extracted. Gemini handles these by reading the
   visual rendering.

4. **Caching is essential.** Every Gemini call is cached by SHA-256 of
   (model + prompt + PDF bytes). Re-runs cost nothing. Different model
   presets get separate cache entries.

5. **Gemini 3 Flash with HIGH thinking produces publication-quality
   Markdown** — Devanagari verses, IAST diacritics, LaTeX math, and
   structured tables all correct.

6. **Tesseract was tried and rejected.** The `san` and `san+hin` models
   hallucinated Devanagari over Latin text. The corpus is predominantly
   Latin+IAST+Greek, not native Devanagari.

## Cost analysis for the full 2000-document corpus

The corpus has ~2000 PDFs with this decade distribution:

```
1960s:   46    (raster, needs Gemini)
1970s:  181    (raster, needs Gemini)
1980s:  268    (raster, needs Gemini)
1990s:  257    (mixed — some raster, some early digital)
2000s:  359    (likely born-digital)
2010s:  611    (born-digital)
2020s:  232    (born-digital)
```

Split: ~25% pre-1990 raster, ~13% mixed 1990s, ~62% post-2000 digital.

Average paper is ~12 pages → ~3 Gemini calls per paper (5 pages/chunk).
For 2000 papers: ~6000 Gemini calls.

| Model | Thinking | Cost estimate | Quality |
| --- | --- | --- | --- |
| gemini-2.5-flash-lite | None | ~$6 | Good for clean digital, weaker on scans |
| gemini-2.5-flash | Built-in | ~$15-20 | Good balance |
| gemini-3-flash-preview | HIGH | ~$43 | Publication quality, best on all types |
| gemini-3-flash-preview | MEDIUM | lower than HIGH | Current default from micro-2 evaluation |

**Current recommendation: `gemini:3-flash-med` for corpus-scale Decode Lab
extraction.** The micro-2 comparison showed similar quality to HIGH thinking
with lower cost and roughly 3x faster API time. HIGH remains available for
specific difficult documents.

Alternative: use flash-lite for the 62% clean digital PDFs where
pdftotext already works, and 3-flash only for the 38% that need it.
This halves the cost but doubles the workflow complexity. We haven't
built this hybrid path yet.

All costs are one-time — the cache means re-runs are free.

## How to run it

```bash
# Deterministic only (no API, ~2 seconds)
uv run python scripts/run_decode_lab.py --run-id test1

# With Gemini extraction + assembly
GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --run-id test1 --extractor gemini:3-flash-med --assemble

# Repair/resume a previous cloud run
GEMINI_API_KEY=... uv run python scripts/run_decode_lab.py \
  --run-id test1 --extractor gemini:3-flash-med --repair --assemble

# Just re-assemble a previous run
uv run python scripts/run_decode_lab.py --assemble-only --run-id test1

# See all options
uv run python scripts/run_decode_lab.py --help
```

Output lands in `.build~/decode-lab/<run_id>/`. Each doc gets:
- `document.md` — the readable Markdown (what you want to look at)
- `fallbacks/` — raw Gemini outputs and cleaned versions
- `review.md` — diagnostic summary
- `pages/` — per-page pdftotext baseline

## Code layout

```
lib/decode_lab/
  runner.py          — main pipeline orchestrator
  campaign_sets.py   — shared campaign set loader
  model_configs.py   — Gemini presets + the extraction prompt
  gemini_extract.py  — PDF-native page-chunk extraction with cache
  gemini_fallback.py — legacy per-page PNG fallback (kept for reference)
  nakshatra_lookup.py — deterministic Sanskrit name corrections
  assembler.py       — Markdown assembly from run artifacts

scripts/
  run_decode_lab.py  — CLI entry point
  profile_pdfs.py    — PDF profiling and reports
  generate_campaign_sets.py — campaign set generator

docs/
  pdf-decoding-lab.md    — design contract and acceptance criteria
  decode-lab-status.md   — current progress and decisions
```

## What's next

1. Run `astro-math-indic-10` through `gemini:3-flash-med --tier flex`
2. Populate Gemini token counts for small campaign sets before decoding
3. Handle `<<<CONTINUE>>>` truncation marker classification before corpus scale
4. Use `reports/pdf-profile.tsv` and generated campaign sets to plan
   `astro-math-full` and broader decode batches
5. Build the search index on top of the extracted Markdown
