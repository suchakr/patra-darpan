# Darpan Decode Lab

## Status
Exploration note for the PDF text and semantic indexing feature. This is a pre-implementation artifact: the goal is to define the sample corpus, method, and acceptance criteria before adding indexing code.

## Motivation
Patra Darpan is the source of truth for corpus metadata. Any text index, semantic index, graph, or retrieval layer should be a derived sidecar that can be rebuilt from canonical corpus rows and local PDF mirrors.

Before processing the full corpus, we need a small repeatable exercise that teaches us which extraction workflow preserves:
- page-level provenance
- Unicode and Indic fidelity
- layout order and bounding boxes
- tables and images
- failure evidence for scanned, malformed, or font-encoded PDFs

The prior Manthana and Vimarsha attempts suggest that a tiny corpus is the right forcing function. A broad ingestion stack became brittle, while a small curated set made extraction failures visible enough to debug. The lab should therefore optimize for traceable experiments and audit reports, not a product UI.

## Name
Use **Darpan Decode Lab** as the short conversational name.

Shorthand: `decode-lab`.

## Prior Evidence
Relevant prior traces:
- Vimarsha has `tiny.corpus`, a 10-PDF IJHS sample focused on extraction stress cases.
- Manthana has `mini_set.json`, a 5-PDF quick validation set, and `golden_set.json`, a 20-PDF set with explicit text/raster distribution.
- Manthana notes show PyMuPDF could fail on native Devanagari extraction even when Latin text and transliterated Sanskrit were mostly usable.
- Vimarsha `p2m_gk` notes suggest Gemini 3 Flash performed well on a small AK Bag pilot, but that should remain an evaluated fallback rather than an always-on default.
- MinerU was observed to use MLX/Metal locally, but a 12-page modern PDF (`1.pdf`) entered a slow VLM extraction phase and was aborted after about 17 minutes. This is too slow for a default corpus pass.
- `pdftotext` and PyMuPDF extract the main prose of `1.pdf` well, but both garble some Shobhika/native Indic footnote spans because the PDF text mapping is unreliable. This is exactly the kind of error the lab must catch instead of silently indexing.

## Sample Corpus
The source of truth for each document remains the Patra Darpan canonical row. The lab sample should be expressed by canonical `doc_id` plus local PDF path. The micro-set PDFs are expected to be locally available, so the first lab runs should not depend on GCS, network mirrors, or remote fetches. Current phase-1 technical design mints IJHS `doc_id` values from `Path(gcs_key).stem`; the issue label from `exports/index.tsv` is supporting metadata, not the document identity.

Start with a micro-set of five documents:

| Role | `doc_id` | PDF key | Issue label | Why it is included |
| --- | --- | --- | --- | --- |
| modern text with risky Indic spans | `1` | `ijhs/1.pdf` | `IJHS-56-2021-Issue-3&4` | Born-digital prose extracts well, but native Indic footnotes show font/unicode risk. |
| modern text with Indic astronomy content | `01_58_4` | `ijhs/01_58_4.pdf` | `IJHS-58-2023-Issue-4` | Tests current IJHS text layer, Indic terms, and CAHC-authored metadata. |
| early raster/math/Sanskrit stress case | `Vol01_1_8_AKBag` | `ijhs/Vol01_1_8_AKBag.pdf` | `IJHS-1-1966-Issue-1` | Prior Gemini pilot target; useful for OCR, Sanskrit, equations, and tables. |
| raster/legacy astronomy stress case | `Vol26_1_1_KDAbhyankar` | `ijhs/Vol26_1_1_KDAbhyankar.pdf` | `IJHS-26-1991-Issue-1` | Prior Manthana mini-set item; useful for raster OCR and nakshatra vocabulary. |
| text-layer astronomy comparison | `Vol44_4_1_PGondhalekar` | `ijhs/Vol44_4_1_PGondhalekar.pdf` | `IJHS-44-2009-Issue-4` | Prior golden-set text PDF; useful as a non-author modern text-layer comparison. |

Then expand to the full Vimarsha tiny corpus:

| `doc_id` | PDF key | Issue label | Note |
| --- | --- | --- | --- |
| `Vol01_1_2_JRRavetz` | `ijhs/Vol01_1_2_JRRavetz.pdf` | `IJHS-1-1966-Issue-1` | Scientific revolution sample. |
| `Vol01_1_4_DJDSPrice` | `ijhs/Vol01_1_4_DJDSPrice.pdf` | `IJHS-1-1966-Issue-1` | Babylonian arithmetic sample. |
| `Vol35_3_2_KDAbhyankar` | `ijhs/Vol35_3_2_KDAbhyankar.pdf` | `IJHS-35-2000-Issue-3` | Babylonian source / astronomy sample. |
| `Vol37_1_3_KDAbhyankar` | `ijhs/Vol37_1_3_KDAbhyankar.pdf` | `IJHS-37-2002-Issue-1` | Unequal nakshatra divisions sample. |
| `Vol41_1_1_RNIyengar` | `ijhs/Vol41_1_1_RNIyengar.pdf` | `IJHS-41-2006-Issue-1` | Krsna-lore astronomy sample. |

## Campaign Sets
A campaign set is a named, ordered list of canonical `doc_id` values used for repeatable profiling, decoding, and audit work. The set is the reusable document selection. A run ID is one execution label over that selection.

Campaign set files live under:

```text
decode-lab/sets/
  micro-2.txt
  micro-5.txt
  astro-math-indic-10.txt
```

Each set file uses one `doc_id` per non-empty, non-comment line. Comments explain why the set exists. The same campaign set definition should be used by both PDF profiling and Decode Lab extraction.

Current operational examples:

```bash
uv run python scripts/run_decode_lab.py --set micro-2 --run-id local-micro2 --assemble
uv run python scripts/profile_pdfs.py --set micro-2
uv run python scripts/generate_campaign_sets.py astro math indic raster native 10 --name astro-math-indic-10
```

Terminology:

| Term | Meaning |
| --- | --- |
| Campaign set | Reusable document selection, for example `micro-2` or `small-astro-math`. |
| Run ID | One execution label, for example `flex-micro2-3flash-med`. |
| Extractor | Decode method, for example `local` or `gemini:3-flash-med`. |
| Profile | Durable per-PDF facts stored in SQLite. |

Generated campaign sets use a deliberately small recipe interface:

```bash
uv run python scripts/generate_campaign_sets.py <hints...> <count> --name <set-name>
```

The generator reads `exports/index.tsv` for `subject/category` and joins it
to SQLite `primary_pdf_profiles`. Positional words are hints, not a full query
language. Unique partial matches are accepted (`tab` -> `tables`); ambiguous
partials fail. Existing `.txt` or `.notes.md` files are never overwritten
unless `--force` is supplied. The command prints the effective normalized
recipe before writing files.

## Exploration Method
Run the lab as an offline profiling and extraction campaign.

1. Resolve documents from Patra Darpan metadata.
   - Use `exports/index.tsv` and future canonical SQLite rows as the document authority.
   - Resolve `gcs_key` values to the local ignored mirror, for example `corpus/ijhs/` when available.
   - Record source URL, mirror path, file size, and SHA-256.

2. Profile each PDF before extraction.
   - Record page count and producer metadata.
   - Run font analysis and flag fonts with missing Unicode maps.
   - Estimate text-layer coverage versus raster/image coverage per page.
   - Record image inventory and page dimensions.

3. Run deterministic baseline extraction first.
   - Use local command-line extractors such as `pdfinfo`, `pdffonts`, `pdfimages`, `pdftotext -layout`, `pdftotext -bbox-layout`, and PyMuPDF through `uv`.
   - Keep raw extractor outputs as build artifacts, not hand-edited files.
   - Preserve page number and bounding box data where available.

4. Detect risk instead of silently cleaning it.
   - Flag control characters, private-use glyphs, replacement characters, suspicious symbol-heavy spans, and known risky fonts.
   - Flag pages with unexpectedly low extracted text density.
   - Flag expected Indic/script spans that vanish or degrade in deterministic extraction.

5. Try targeted fallbacks only where risk is detected.
   - Prefer page or crop-level fallback over whole-document VLM extraction.
   - Evaluate Gemini cloud extraction on flagged pages/crops with model name, prompt hash, and output hash recorded.
   - Evaluate OCR only after the required Indic language data is installed and recorded.
   - Keep MinerU as a timeout-limited heavy fallback, not as the default path.

6. Produce an audit packet.
   - Store generated lab artifacts under a rebuildable path such as `.build~/decode-lab/<run_id>/`.
   - Include per-document manifests, raw extractor outputs, risk flags, sample chunks, table/image inventories, and fallback comparisons.
   - Produce one human-readable report summarizing what worked, what failed, and what should become the first indexing milestone.

## PDF Profile Stage
PDF profiling is a derived enrichment over canonical document metadata and local PDF assets. It is not root input metadata and should be rebuildable.

Durable profile state lives in SQLite:

```text
asset_refs
  file_size_bytes
  checksum
  mime_type

pdf_profiles
  asset_id
  doc_type
  page_count
  text_page_count
  raster_page_count
  image_count
  table_candidate_count
  fonts_missing_unicode_map_count
  estimated_tokens
  token_model
  context_cache_eligible
  profile_version
  profiled_at

primary_pdf_profiles
  convenience view joining documents, primary asset_refs, and pdf_profiles
```

The `asset_refs` table records the document-to-asset relationship and file facts. The `pdf_profiles` table records what the PDF looks like. The `primary_pdf_profiles` view is the simple planning surface for humans, agents, and future decode orchestration.

The default profiler should be local-only and incremental:

```bash
uv run python scripts/profile_pdfs.py
```

Full local profiling completed successfully on 2026-04-15:

| Metric | Count |
| --- | ---: |
| Primary PDF assets | 2004 |
| Profiled assets | 2004 |
| Failures | 0 |
| `digital` | 960 |
| `raster` | 983 |
| `mixed` | 53 |
| `unknown` | 8 |

Gemini token counting is explicit because it uses a network/API call:

```bash
uv run python scripts/profile_pdfs.py --set micro-2 --token-count gemini
```

Profile locations:

| Location | Role |
| --- | --- |
| SQLite `pdf_profiles` | Canonical durable profile state. |
| `reports/pdf-profile.tsv` | Human/agent planning projection. |
| `reports/pdf-profile-audit.md` | Small summary of coverage and gaps. |
| `.cache/pdf-profiles/gemini-token-count/` | Reusable expensive token-count results keyed by checksum and model. Safe to delete. |
| `.build~/pdf-profile-runs/<run_id>/` | Optional run evidence when `--run-id` is supplied; not canonical and not a cache. |

The decode runner's `--extractor` option remains authoritative. Profile data may guide planning, token-count/context-cache decisions, and campaign construction, but it should not silently override an explicit extractor choice.

## Run Repair and Assembly Semantics
Decode Lab run directories are evidence packets. The default behavior remains
accident-proof: an existing `--run-id` aborts unless the user explicitly asks
to reuse or replace it.

| Flag | Meaning |
| --- | --- |
| default | Create a new run directory; fail if it already exists. |
| `--resume` | Reuse an existing run directory and continue/retry work. Successful Gemini chunks are served from cache; missing or failed chunks are attempted again. |
| `--repair` | Reuse an existing run directory to fix failed or partial work. First implementation shares resume mechanics and reassembles affected documents when `--assemble` is supplied. |
| `--force` | Delete and recreate the run directory. Destructive; prefer `--resume` or `--repair` for long Gemini runs. |

Assembly behavior:

| Flag | Meaning |
| --- | --- |
| `--assemble` | Eager assembly. Write `document.md` after each document finishes extraction, so long runs can be reviewed before the whole campaign ends. |
| `--assemble --assemble-lazy` | Legacy batch behavior. Assemble all documents only after extraction for the full run finishes. |
| `--assemble-only` | Do no extraction; assemble an existing run from current artifacts. |

Gemini chunk failures must be recorded inside the run, not just visible in
terminal logs. Failed chunks write per-document error artifacts under
`by-doc/<doc_id>/fallbacks/*_error.json` and update
`by-doc/<doc_id>/extraction-state.json`. Repair/resume flows should be able to
reason from these artifacts without requiring the user to paste logs.

## Script Hygiene
The lab should avoid creating a graveyard of half-promoted WIP scripts.

Use three levels:

| Level | Location | Git status | Rule |
| --- | --- | --- | --- |
| Scratch probes | `scratch~/decode-lab/` | untracked | Disposable one-off commands and extractor probes. These may be deleted at any time and must not become dependencies of the lab output contract. |
| Promoted lab runner | `scripts/run_decode_lab.py` plus optional `lib/decode_lab/` | tracked | Only create this once the artifact contract is stable enough to rerun the micro-set. Keep a single CLI entrypoint rather than adding many extractor-specific scripts. |
| Production pipeline | existing `scripts/`, `lib/`, `ops/` roles | tracked | Do not move decode-lab code here until it graduates from exploration into the canonical corpus/search pipeline. |

Practical rules:
- Do not add numbered WIP scripts such as `try_gemini_2.py`, `extract_test_final.py`, or per-PDF scripts under `scripts/`.
- Record ad hoc shell commands in `run-manifest.json` or the per-run `audit.md`, not as permanent repo scripts.
- If a scratch probe becomes necessary for a second run, either keep it in `scratch~/decode-lab/` with no contract dependency or promote the behavior into the single lab runner.
- If a promoted runner grows extractor-specific behavior, expose it as CLI options or internal modules rather than new top-level scripts.
- The first tracked runner should emit the output contract above; it should not be added merely to wrap a single local experiment.

Current promoted runner:

```bash
uv run python scripts/run_decode_lab.py
```

Useful narrow run:

```bash
uv run python scripts/run_decode_lab.py --doc-id 1 --run-id smoke-1
```

The current runner is local-only and deterministic. It uses Poppler CLI tools when available and records PyMuPDF as an explicit extractor status; PyMuPDF spans are emitted only if the environment already provides the `fitz` module. It does not call Gemini, OCR, MinerU, embeddings, or any network service.

## Output Contract
The lab output should be concrete enough for humans and agents to compare runs without freezing the final implementation.

The contract is an artifact contract, not a promise about final extractor internals. Extractors, prompts, chunking rules, and fallback tools may change as long as each run emits the same top-level artifact shapes and explains any schema version change.

Default output root:

```text
.build~/decode-lab/<run_id>/
  run-manifest.json
  audit.md
  documents.jsonl
  pages.jsonl
  chunks.jsonl
  risks.jsonl
  images.jsonl
  tables.jsonl
  fallbacks.jsonl
  retrieval-samples.jsonl
  by-doc/
    <doc_id>/
      source.pdf -> /absolute/path/to/source.pdf
      review.md
      manifest.json
      source.json
      profile.json
      extractors/
        pdftotext-layout.txt
        pdftotext-bbox.html
        pymupdf-blocks.jsonl
      pages/
        p0001.txt
        p0001.blocks.jsonl
        p0001.risks.jsonl
      fallbacks/
        <fallback_id>.json
```

The top-level JSONL files are normalized run tables for agents, validators, and later loaders. They are not the primary human review surface. Each `by-doc/<doc_id>/` directory must materialize the relevant rows for that document so a human can review one PDF without manually stitching `doc_id` across files.

Required file roles:

| Artifact | Role |
| --- | --- |
| `run-manifest.json` | Run identity, schema version, command, tool versions, environment hints, started/finished timestamps, and selected document IDs. |
| `audit.md` | Human-readable result: coverage, failures, risky pages, fallback outcomes, sample chunks, and sample retrieval citations. |
| `documents.jsonl` | One row per input PDF with document metadata, local path, size, checksum, page count, and high-level extraction status. |
| `pages.jsonl` | One row per page with page-level text coverage, image count, table candidates, risk summary, and best available text source. |
| `chunks.jsonl` | Candidate chunks for lexical indexing; every row must cite `doc_id`, page range, chunk ordinal, content hash, and source extractor. |
| `risks.jsonl` | One row per detected risk, such as missing Unicode map, private-use glyph, control-character span, low text density, or suspected OCR need. |
| `images.jsonl` | Image inventory with `doc_id`, page, bounding box when available, dimensions, and extraction source. |
| `tables.jsonl` | Table candidate inventory with `doc_id`, page, bounding box when available, extraction source, and confidence/status. |
| `fallbacks.jsonl` | Targeted fallback attempts, including page/crop, tool or model, prompt hash when relevant, cost/time when known, output hash, and status. |
| `retrieval-samples.jsonl` | A small fixed set of lexical queries and returned chunks with citations; embeddings are optional. |
| `by-doc/<doc_id>/source.pdf` | Symlink to the local source PDF so a reviewer can open the exact input from the packet. |
| `by-doc/<doc_id>/review.md` | Human review view for one document: profile summary, page coverage, high-risk spans, table/image inventory, sample chunks, fallback outcomes, and reviewer notes. |
| `by-doc/<doc_id>/manifest.json` | Per-document materialized index of the document's artifact paths, row counts, risk counts, and extraction status. |

Minimum JSON row fields:

```text
documents.jsonl:
  doc_id, title, author_display, year, source_url, local_pdf_path,
  sha256, byte_size, page_count, status, status_reason

pages.jsonl:
  page_id, doc_id, page_number, width, height, text_char_count,
  extractor, extraction_status, risk_count, image_count, table_count

chunks.jsonl:
  chunk_id, doc_id, page_start, page_end, chunk_ordinal,
  text, text_sha256, extractor, extraction_version, risk_flags

risks.jsonl:
  risk_id, doc_id, page_number, risk_type, severity,
  extractor, bbox, font_name, evidence, recommended_action

fallbacks.jsonl:
  fallback_id, doc_id, page_number, bbox, fallback_type,
  tool_or_model, tool_or_model_version, prompt_sha256,
  input_sha256, output_sha256, status, status_reason
```

Validation rule: a run is not acceptable if it produces `chunks.jsonl` rows for a page with serious unaddressed extraction risks but does not also emit corresponding `risks.jsonl` evidence. The lab may produce partial chunks, but it must not silently convert extraction garbage into indexable text.

Human review rule: a run is not acceptable if validating one document requires a human to manually join top-level JSONL files. The per-document `review.md` and `manifest.json` are required materialized views over the normalized run tables.

## Acceptance Criteria
The lab succeeds when the micro-set produces an audit report that is specific enough to choose an extraction/indexing path.

Minimum acceptance gates:
- Every extracted text unit can trace to `doc_id`, source URL, local file path when available, SHA-256, page number, extractor name/version, and extraction timestamp.
- Main prose extraction is page-stable for text-layer PDFs such as `ijhs/1.pdf` and `ijhs/01_58_4.pdf`.
- Known Indic failure spans in `ijhs/1.pdf` are either correctly decoded or explicitly flagged with page, font, bounding box, and recommended fallback.
- Raster or low-text PDFs are classified as needing OCR/VLM fallback rather than entering the lexical index as empty or garbage text.
- Tables and images are inventoried with page-level provenance; full semantic interpretation of tables and images is not required for the first pass.
- Cloud or VLM outputs are stored as derived, model-versioned sidecars and are not allowed to overwrite deterministic baseline extraction.
- The lab can be rerun without changing canonical corpus metadata.
- The report includes at least one sample lexical retrieval result with citations, but embeddings are optional for this exercise.
- The output packet satisfies the output contract above, including top-level manifests and JSONL files even when some files contain zero rows.

## Non-Goals
- Full-corpus extraction.
- Product UI.
- Final graph database or vector database selection.
- Grand knowledge graph construction.
- Perfect OCR for every script in the corpus.
- Treating cloud model output as canonical text without provenance.

## Assumptions To Confirm
- The micro-set above is the right starting set, or should be reduced further to four PDFs.
- Local PDF mirrors should be mounted or copied into the feature worktree for repeatable runs, since `corpus/ijhs/` and `corpus/other/` are intentionally ignored by git. For the micro-set, the local PDFs are the input and GCS should stay out of the run path.
- Gemini cloud use is acceptable for flagged page/crop experiments, with costs and model versions recorded.
- Indic OCR language data may be installed if deterministic text extraction fails on raster or font-encoded spans.
- `.build~/decode-lab/` is acceptable as the default generated artifact location.
