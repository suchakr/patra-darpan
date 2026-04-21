# audit-set Notes

Manual audit set exported from `reports/decoder-audit-2026-04-18-185402.md`.

Purpose:

- Preserve the reviewed sample as a reusable campaign set.
- Reassemble/rebuild this set after no-cost assembly and media fixes.
- Use it as the first retrieval-confidence sample before more corpus decoding.

Observed issue classes:

- Repeated media URL for multiple figures on the same page.
- Placeholder links left unresolved despite available media.
- Digital PDFs with figure placeholders but no extracted media.
- Captions often omit the printed `Fig. N.` prefix.
- Some media extraction slices are wrong or over-fragmented.
- Scanned PDFs use full-page render fallback by design.

Recommended use:

```bash
uv run python scripts/run_decode_lab.py --assemble-only --run-id build-astro-math-indic-digital
uv run python scripts/run_decode_lab.py --assemble-only --run-id build-astro-math-indic-raster

uv run python scripts/build_decoded_corpus.py --from-run build-astro-math-indic-digital --replace-set audit-set
uv run python scripts/build_decoded_corpus.py --from-run build-astro-math-indic-raster --replace-set audit-set
```
