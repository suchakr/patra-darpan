# ISCLS Semantic Embedding Bakeoff

## Status

Planning note. This is an offline evaluation stage before the Zoekt/MCP
adapter. It does not change the read-only online contract or production
services.

## Purpose

Choose a semantic indexing configuration that works for the actual Indic and
Patra Darpan material, with measured quality, size, latency, and cost. The
bakeoff must be repeatable and must use the same identity and provenance
contracts that the later vector projection will use.

## Working boundaries

```text
~/projects/patra-darpan-pdf-semantic-index   bakeoff code, docs, reports
~/projects/sanchaya                        read-only corpus checkout
~/projects/sanchaya-zoekt                  unchanged during the bakeoff
```

The runner reads the Sanchaya checkout directly at a recorded Git commit. It
does not export, edit, or commit corpus files. “Frozen snapshot” means a clean,
revision-pinned checkout, not a second copy of the repository.

Generated chunks, embeddings, Qdrant data, and reports live under a
gitignored local area such as `.local/iscls-bakeoff/`.

## Evaluation inputs

### Primary judged corpus

Use the existing 29-document `decode-lab/sets/audit-set.txt` selection after
its accepted Markdown has been projected into Sanchaya. These documents provide
reviewed astronomy, mathematics, historical, table, IAST, and Devanagari
material.

### Sanchaya coverage probe

Use 30 read-only Sanchaya files:

- 24 representative `Jyotisham/` files covering Devanagari, IAST, mixed/OCR,
  mathematical, astronomical, and translated material;
- `Vedic texts/AV/atharvaveda parishishta.txt`;
- `gretil/sa_atharvavedapariziSTas.txt`;
- `Puranani/brahmanda purana.txt`;
- `gretil/sa_brahmANDapurANa.txt`;
- `Bauddha/shardula karnavadanam.txt`; and
- `gretil/sa_zArdUlakarNAvadAna.txt`.

The exact 24-file list is recorded in the input manifest before the first
embedding run. The probe is reported separately from the primary relevance
score so a large source file or an open-ended discovery query cannot distort
the judged paper benchmark.

The first input pass is now runnable with the read-only checkout:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/prepare_iscls_bakeoff.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/build_iscls_chunks.py
```

The current manifest records Sanchaya commit
`c6d35eb057aec2e8d7aafc8c40a430ce8333e971`, 29 judged papers, and 30 probe
files. The initial inventory contains 3,625 chunks and about 1.29 million
whitespace-token estimates; 1,375 chunks use the long-block fallback and 112
are table chunks. These are inventory measurements, not model-token counts.
The fallback rate is a review gate: inspect representative verses, OCR text,
and tables before embedding, and revise `chunker_v1` once if the boundaries
are visibly poor.

## Query set

Create `docs/iscls/semantic-embedding-bakeoff-queries.jsonl` with:

- 18 development queries;
- 6 held-out queries; and
- 8 Sanchaya probe queries.

Each row records `query_id`, query text, query class, script, expected document
IDs or source paths, and a short relevance note. Query classes include
conceptual paraphrase, transliteration variation, Devanagari, IAST, mixed
script, entity/work linkage, table or method questions, and open-ended source
discovery.

The checked-in query file currently contains those 32 rows. Generated input,
chunk, model, and Qdrant artifacts remain under `.local/iscls-bakeoff/` and
are intentionally not committed.

The initial held-out questions include:

1. Are nakṣatras only lunar mansions, or are they also used as solar, seasonal,
   and calendrical markers?
2. What is the significance of the Māghādi scheme, and how does the
   Brahmāṇḍa Purāṇa calendar beginning with the Sun at Maghā relate to rain or
   the summer solstice?
3. Does the Atharvaveda Pariśiṣṭa list nakṣatra shapes and counts? Find other
   sources, including Śārdūla sources, that make similar references.
4. Find occurrences of Śraviṣṭhā and Dhaniṣṭhā, including Devanagari and
   transliteration variants, and report how each source treats them.

Closed questions receive document-level relevance judgments first. Finalist
models receive chunk-level inspection. Open-ended occurrence and source-
discovery questions receive a coverage report rather than a forced top-five
gold label.

## Common semantic input

All candidate models use the same deterministic `chunker_v1` input:

- preserve headings, paragraphs, verses, tables, page markers, and original
  scripts;
- embed title, heading path, and chunk text;
- keep catalog metadata, URLs, IDs, and JSON out of the embedded text;
- target approximately 384 tokens;
- hard limit approximately 480 tokens;
- use approximately 48-token overlap only when a long block must be split; and
- derive stable chunk IDs from document identity, logical location, chunker
  version, and text hash.

The chunk inventory is measured before model comparison. If the inventory
shows that this policy damages tables, verses, or short sections, revise the
chunker once and rerun every candidate on the same revised chunks.

## Candidate embedders

Run three arms when the paid budget permits:

1. `intfloat/multilingual-e5-base` as the local baseline;
2. `BAAI/bge-m3` as the local challenger; and
3. `gemini-embedding-2` as the paid challenger, using 768 output dimensions
   initially.

Pin exact model revisions and record them in every build. Gemini supports
8,192-token text inputs and configurable output dimensions; the current Google
standard text price is $0.20 per million tokens. See the [Gemini embedding
documentation](https://ai.google.dev/gemini-api/docs/embeddings) and
[pricing](https://ai.google.dev/gemini-api/docs/pricing).

The Gemini arm has a hard budget cap of **$0.50**. Perform a token preflight
before any API call and stop at **$0.40** to reserve retry and query headroom.
If the full probe exceeds the cap, retain the full 29-paper judged run and
reduce the paid probe selection. Do not send PDFs or images in this text
embedding bakeoff.

## Local vector infrastructure

Run Qdrant in a standalone local Compose profile owned by the semantic
repository. Create one isolated collection per candidate model. Keep the
Qdrant volume outside Git and publish no public port.

The checked-in local profile is `docker-compose.iscls-bakeoff.yml`:

```bash
docker compose -f docker-compose.iscls-bakeoff.yml up -d qdrant
uv run --with sentence-transformers --with qdrant-client \
  python scripts/run_iscls_vector_build.py \
  --model intfloat/multilingual-e5-base --recreate
```

The vector builder is deliberately separate from Zoekt and MCP. It writes a
run manifest under `.local/iscls-bakeoff/runs/`, records the chunk inventory
hash, and stores only searchable payload/provenance in Qdrant; full chunk text
continues to come from the chunk inventory and later shared chunk store.

After a candidate collection is built, evaluate it with:

```bash
uv run --with sentence-transformers --with qdrant-client \
  python scripts/evaluate_iscls_vectors.py \
  --run .local/iscls-bakeoff/runs/iscls_intfloat_multilingual_e5_base/run.json
```

Qdrant stores vectors, chunk IDs, corpus revision, and filterable provenance.
The chunk store remains the source for full text and media references. The
evaluator talks directly to Qdrant; MCP and the Zoekt adapter are out of scope
until a model is selected.

## Measurements and decision rule

For every candidate, record:

- Recall@5 and nDCG@5 on closed held-out queries;
- results by English, IAST, Devanagari, and mixed-script groups;
- top-chunk manual quality;
- token count, build duration, and throughput;
- peak memory and model download size;
- vector/Qdrant collection size; and
- query latency.

Select a model only when it gives a clear held-out quality improvement without
a serious Indic-script failure or an unacceptable resource/cost profile. A
small quality difference favors the local model because it removes API
dependency and recurring spend.

## Task breakdown and estimate

| Task | Output | Engineering time |
| --- | --- | ---: |
| Durable note and input contract | this note, query/schema decision | 2–4 hours |
| Read-only Sanchaya validation | clean commit, 29-paper selection, 30-file probe manifest | 3–6 hours |
| Chunk inventory and `chunker_v1` | token statistics, stable chunk fixture | 4–8 hours |
| Query preparation and labels | 24 judged queries plus 8 probe queries and expected evidence | 4–8 hours |
| Local embedder runner | E5/BGE build and evaluation commands | 4–8 hours |
| Standalone Qdrant profile | persistent local collections and health checks | 2–4 hours |
| Gemini capped run | token preflight, budget guard, third collection | 1–3 hours |
| Evaluation report | quality/resource comparison and recommendation | 4–8 hours |

These task ranges overlap; they are not additive. The active critical path is
expected to be **3–5 working days**. With model downloads, manual relevance
review, and discussion of failures, the calendar estimate is **4–7 days**.

The main uncertainty is chunk and relevance review; embedding runtime itself
should be shorter.

## Implementation checkpoint

The contract and first runnable scaffolding are committed separately:

- `28543f6` — bakeoff contract, query file, budget and exit criteria;
- `05fe09b` — read-only input manifest, deterministic chunk inventory, local
  Qdrant profile, and optional local vector builder; and
- `11a5760` — Qdrant evaluator with Recall@5, nDCG@5, script grouping, and
  open-ended source-path coverage.

Remaining hands-on work after this scaffold is approximately **2–4 working
days**: inspect and, if needed, revise chunk boundaries; install and run the
two local candidates; run the capped Gemini arm only if its preflight fits the
approved budget; perform manual top-result judgments; and write the comparison
report. Model downloads, hardware speed, and manual review are the variables.

## Exit criteria

The bakeoff is complete when:

- the input commit and file manifest are recorded;
- every candidate uses identical chunks and queries;
- the Gemini spend guard is tested and remains under the approved cap;
- Qdrant collections are reproducible locally;
- quality, script coverage, size, latency, and cost are reported; and
- one model/chunker configuration is selected for the 120-paper plus selected
  Jyotisha vector projection.

Only after this gate do we integrate the chosen vector projection into the
normal ISCLS build path and add the thin Zoekt/MCP adapter.
