"""Markdown assembler for the Darpan Decode Lab.

Reads the artifacts from a completed run directory and produces one
``document.md`` per PDF.  The assembled Markdown shows:

- Baseline extracted text for each page
- Accepted fallback table text spliced in where available
- Risky-span markers around garbled text (visible but skimmable)
- Extraction-gap comments for unresolved risks without fallbacks
- Image reference comments from the image inventory

Usage::

    from lib.decode_lab.assembler import assemble_run
    assemble_run(run_dir=Path(".build~/decode-lab/my-run"))

CLI integration via the runner::

    uv run python scripts/run_decode_lab.py --assemble-only --run-id my-run
    uv run python scripts/run_decode_lab.py --run-id my-run --fallback gemini --assemble
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def assemble_run(run_dir: Path) -> list[Path]:
    """Assemble document.md for every doc in *run_dir*.

    Returns the list of document.md paths written.
    """
    tables = _load_jsonl(run_dir / "tables.jsonl")
    risks = _load_jsonl(run_dir / "risks.jsonl")
    images = _load_jsonl(run_dir / "images.jsonl")
    fallbacks = _load_jsonl(run_dir / "fallbacks.jsonl")

    # Index helpers
    tables_by_page: dict[tuple[str, int], list[dict]] = {}
    for t in tables:
        key = (t["doc_id"], t["page_number"])
        tables_by_page.setdefault(key, []).append(t)

    risks_by_page: dict[tuple[str, int], list[dict]] = {}
    for r in risks:
        if r.get("page_number") is not None:
            key = (r["doc_id"], r["page_number"])
            risks_by_page.setdefault(key, []).append(r)

    images_by_page: dict[tuple[str, int], list[dict]] = {}
    for img in images:
        key = (img["doc_id"], img["page_number"])
        images_by_page.setdefault(key, []).append(img)

    # Accepted fallback text keyed by fallback tag
    accepted_fallbacks: dict[str, Path] = {}
    for fb in fallbacks:
        if fb.get("status") == "success" and fb.get("recommended_action") == "accept":
            tid = fb["fallback_id"].replace("-nakshatra-lookup", "").replace("-gemini-combined", "")
            doc_dir = run_dir / "by-doc" / fb["doc_id"] / "fallbacks"
            cleaned = doc_dir / f"{tid}_cleaned.txt"
            if cleaned.exists():
                accepted_fallbacks[tid] = cleaned

    # Index which pages have accepted table fallbacks
    pages_with_fallback_tables: dict[tuple[str, int], str] = {}
    for t in tables:
        tid_safe = t["table_id"].replace(":", "-")
        if tid_safe in accepted_fallbacks:
            pages_with_fallback_tables[(t["doc_id"], t["page_number"])] = tid_safe

    # Index which pages have accepted page-level fallbacks (for raster/scanned)
    pages_with_fallback_text: dict[tuple[str, int], Path] = {}
    for fb in fallbacks:
        if (
            fb.get("status") == "success"
            and fb.get("recommended_action") == "accept"
            and fb.get("fallback_type") == "deterministic_postprocess"
            and fb["fallback_id"].endswith("-nakshatra-lookup")
        ):
            # Check if this is a page-level fallback (not a table fallback)
            base = fb["fallback_id"].replace("-nakshatra-lookup", "")
            # Page fallbacks have IDs like "doc_id-p0001", table ones like "doc_id-p0001-t0001"
            doc_dir = run_dir / "by-doc" / fb["doc_id"] / "fallbacks"
            cleaned = doc_dir / f"{base}_cleaned.txt"
            if cleaned.exists() and fb.get("bbox") is None:
                key = (fb["doc_id"], fb["page_number"])
                pages_with_fallback_text[key] = cleaned

    # Detect docs with Gemini page-chunk extracts (from --extractor gemini:*)
    # These are complete Markdown files — use them directly instead of
    # stitching pdftotext pages.
    docs_with_gemini_chunks: dict[str, list[Path]] = {}
    for fb in fallbacks:
        if (
            fb.get("status") == "success"
            and fb.get("recommended_action") == "accept"
            and fb.get("fallback_type") == "deterministic_postprocess"
            and fb["fallback_id"].endswith("-nakshatra-lookup")
            and fb.get("page_start") is not None  # page-chunk (not single-page)
        ):
            base = fb["fallback_id"].replace("-nakshatra-lookup", "")
            doc_dir = run_dir / "by-doc" / fb["doc_id"] / "fallbacks"
            # Try .md first (new gemini_extract), then .txt (legacy)
            cleaned = doc_dir / f"{base}_cleaned.md"
            if not cleaned.exists():
                cleaned = doc_dir / f"{base}_cleaned.txt"
            if cleaned.exists():
                docs_with_gemini_chunks.setdefault(fb["doc_id"], []).append(cleaned)

    written: list[Path] = []
    by_doc = run_dir / "by-doc"
    if not by_doc.exists():
        return written

    for doc_dir in sorted(by_doc.iterdir()):
        if not doc_dir.is_dir():
            continue
        doc_id = doc_dir.name
        source_path = doc_dir / "source.json"
        if not source_path.exists():
            continue
        source = json.loads(source_path.read_text(encoding="utf-8"))

        # If this doc has Gemini page-chunk extracts, use those directly
        if doc_id in docs_with_gemini_chunks:
            from lib.decode_lab.image_extract import replace_figure_placeholders
            from lib.decode_lab.markdown_fixups import apply_markdown_fixups

            chunk_files = sorted(docs_with_gemini_chunks[doc_id])
            lines: list[str] = []
            lines.append(f"# {source.get('title', doc_id)}")
            lines.append("")
            _emit_metadata(lines, source)
            lines.append("")
            lines.append("<!-- source: gemini page-chunk extraction -->")
            lines.append("")
            for chunk_file in chunk_files:
                chunk_text = chunk_file.read_text(encoding="utf-8").rstrip()
                chunk_text = replace_figure_placeholders(chunk_text, doc_id)
                chunk_text = apply_markdown_fixups(chunk_text)
                lines.append(chunk_text)
                lines.append("")
            doc_md_path = doc_dir / "document.md"
            doc_md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            written.append(doc_md_path)
            continue

        # Otherwise, fall back to per-page pdftotext assembly
        pages_dir = doc_dir / "pages"
        page_files = sorted(pages_dir.glob("p*.txt"))
        if not page_files:
            continue

        lines = []
        lines.append(f"# {source.get('title', doc_id)}")
        lines.append("")
        _emit_metadata(lines, source)
        lines.append("")

        for page_file in page_files:
            # Extract page number from filename p0001.txt -> 1
            page_num = int(page_file.stem.lstrip("p"))
            page_text = page_file.read_text(encoding="utf-8", errors="replace").rstrip()
            page_key = (doc_id, page_num)

            lines.append(f"## Page {page_num}")
            lines.append("")

            page_risks = risks_by_page.get(page_key, [])
            page_images = images_by_page.get(page_key, [])
            page_tables = tables_by_page.get(page_key, [])

            has_fallback_table = page_key in pages_with_fallback_tables
            has_fallback_page = page_key in pages_with_fallback_text
            risky_types = {r["risk_type"] for r in page_risks}
            is_risky = bool(risky_types - {"font_missing_unicode_map"})

            # Emit the page content
            if has_fallback_page:
                # Full-page fallback (raster/scanned) — use Gemini-extracted text
                fb_path = pages_with_fallback_text[page_key]
                fb_text = fb_path.read_text(encoding="utf-8").rstrip()
                lines.append(f"<!-- fallback: gemini full-page extraction -->")
                lines.append(fb_text)
                lines.append("")
            elif has_fallback_table:
                fallback_tid = pages_with_fallback_tables[page_key]
                fallback_path = accepted_fallbacks[fallback_tid]
                fallback_text = fallback_path.read_text(encoding="utf-8").rstrip()

                # Find the table caption to use as a heading
                table_meta = None
                for t in page_tables:
                    if t["table_id"].replace(":", "-") == fallback_tid:
                        table_meta = t
                        break

                caption = (table_meta or {}).get("caption", "Table")

                # Emit baseline text before the table region
                # (for now, emit the fallback table as the primary content
                #  since splicing at exact line boundaries requires more work)
                if is_risky and not _text_is_only_table(page_text, table_meta):
                    _emit_risky_text(lines, page_text, page_risks, before_table=True)
                    lines.append("")

                lines.append(f"### {caption}")
                lines.append("")
                _emit_fallback_table(lines, fallback_text)
                lines.append("")

                if is_risky:
                    _emit_remaining_gaps(lines, page_num, page_risks, has_table_fallback=True)
            elif is_risky:
                _emit_risky_text(lines, page_text, page_risks)
                lines.append("")
                _emit_table_candidates(lines, page_tables, fallback_status="none")
                _emit_remaining_gaps(lines, page_num, page_risks, has_table_fallback=False)
            else:
                # Clean page — emit baseline text directly
                lines.append(page_text)
                lines.append("")
                _emit_table_candidates(lines, page_tables, fallback_status="none")

            # Image references
            for img in page_images:
                img_id = img.get("image_id", "?")
                w = img.get("width", "?")
                h = img.get("height", "?")
                enc = img.get("encoding", "?")
                lines.append(f"<!-- image: {img_id}, page {page_num}, {w}x{h}, {enc} -->")

            lines.append("")

        doc_md_path = doc_dir / "document.md"
        doc_md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        written.append(doc_md_path)

    return written


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _emit_metadata(lines: list[str], source: dict) -> None:
    for key in ["author_display", "year", "journal_label", "source_url"]:
        val = source.get(key, "")
        if val:
            label = key.replace("_", " ").title()
            lines.append(f"- {label}: {val}")


def _emit_risky_text(
    lines: list[str],
    page_text: str,
    page_risks: list[dict],
    before_table: bool = False,
) -> None:
    """Emit page text with risky-span markers around garbled sections."""
    risk_summary = ", ".join(
        f"{r['risk_type']} ({r.get('evidence', '').split('.')[0]})"
        for r in page_risks
        if r["risk_type"] in {"control_characters", "private_use_glyphs"}
    )
    if risk_summary:
        lines.append(f"<!-- risky-span: {risk_summary} -->")
    lines.append(page_text)
    if risk_summary:
        lines.append("<!-- end-risky-span -->")


def _emit_remaining_gaps(
    lines: list[str],
    page_num: int,
    page_risks: list[dict],
    has_table_fallback: bool,
) -> None:
    """Emit extraction-gap comments for unresolved risks."""
    gap_risks = [
        r for r in page_risks
        if r["risk_type"] in {"control_characters", "low_text_density", "private_use_glyphs"}
    ]
    if not gap_risks:
        return

    for r in gap_risks:
        risk_type = r["risk_type"]
        evidence = r.get("evidence", "")
        action = r.get("recommended_action", "inspect")
        scope = "non-table spans" if has_table_fallback else "full page"
        lines.append(
            f"<!-- extraction-gap: page {page_num}, {risk_type}, {scope} -->"
        )
        lines.append(f"<!-- evidence: {evidence} -->")
        lines.append(f"<!-- recommended: {action} -->")


def _emit_table_candidates(
    lines: list[str],
    page_tables: list[dict],
    fallback_status: str,
) -> None:
    """Emit annotations for table candidates that have no accepted fallback."""
    if not page_tables:
        return
    for t in page_tables:
        caption = t.get("caption", "Table")
        rows = t.get("data_row_count", "?")
        bbox = t.get("bbox")
        bbox_str = f", bbox {bbox}" if bbox else ""
        lines.append(f"### {caption}")
        lines.append("")
        lines.append(
            f"<!-- table-candidate: {t['table_id']}, {rows} data rows{bbox_str} -->"
        )
        if fallback_status == "none":
            lines.append(
                "<!-- no fallback run yet — rerun with --fallback gemini --assemble to extract -->"
            )
        lines.append("")


def _emit_fallback_table(lines: list[str], fallback_text: str) -> None:
    """Emit accepted fallback table text, converting pipe-separated to Markdown."""
    raw_lines = fallback_text.strip().splitlines()
    if not raw_lines:
        return

    # Detect if it's already pipe-separated (our Gemini output format)
    if "|" in raw_lines[0]:
        # Convert to proper Markdown table
        for i, raw_line in enumerate(raw_lines):
            clean = raw_line.strip()
            if clean.startswith("```"):
                continue  # skip code fences if present
            if not clean:
                continue
            # Ensure leading/trailing pipes
            if not clean.startswith("|"):
                clean = "| " + clean
            if not clean.endswith("|"):
                clean = clean + " |"
            lines.append(clean)
            # Add separator after first header row
            if i == 0:
                col_count = clean.count("|") - 1
                lines.append("|" + "---|" * max(col_count, 1))
    else:
        # Plain text fallback — emit as a fenced code block
        lines.append("```")
        lines.append(fallback_text.strip())
        lines.append("```")


def _text_is_only_table(page_text: str, table_meta: dict | None) -> bool:
    """Rough check: does the table span most of the page text?"""
    if table_meta is None:
        return False
    extent_start = table_meta.get("extent_line_start", 0)
    extent_end = table_meta.get("extent_line_end", 0)
    page_lines = page_text.splitlines()
    if not page_lines:
        return True
    table_span = extent_end - extent_start + 1
    return table_span >= len(page_lines) * 0.7
