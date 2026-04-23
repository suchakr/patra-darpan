#!/usr/bin/env python3
"""Build static Patra Darpan Search Lab artifacts from decoded-corpus."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import html
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DECODED_ROOT = ROOT / "decoded-corpus"
DEFAULT_OUTPUT = ROOT / "web" / "assets" / "data" / "search-corpus.json"
DEFAULT_SMOKE_REPORT = ROOT / "reports" / "search-smoke.md"
DEFAULT_SET_DIR = ROOT / "decode-lab" / "sets"
DEFAULT_MEDIA_OUTPUT = ROOT / "web" / "assets" / "search-media"
DEFAULT_INDEX_TSV = ROOT / "exports" / "index.tsv"

SMOKE_QUERIES = [
    "Yājñavalkya cycle",
    "Saptarṣi era",
    "pandiagonal magic square",
    "Nārāyaṇa Paṇḍita magic square",
    "Vedāṅga Jyotiṣa solstice",
    "intercalary month Vedic texts",
    "Sūrya Siddhānta planetary nodes",
    "Jñānarāja sine table",
    "Yuktibhāṣā Jyesthadeva",
    "circle square conversion Sundararaja",
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "era",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a static lexical search corpus from decoded-corpus Markdown. "
            "The audit set is the default validation target, but the builder can "
            "project any decoded set, explicit doc IDs, or all decoded docs."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  uv run python scripts/build_search_index.py --set audit-set
  uv run python scripts/build_search_index.py --set astro-math-indic-10
  uv run python scripts/build_search_index.py --doc-id Vol28_1_2_SCKak
  uv run python scripts/build_search_index.py --all-decoded
  uv run python scripts/build_search_index.py --set audit-set --output /tmp/search-corpus.json
  uv run python scripts/build_search_index.py --set audit-set --media-mode captions
""",
    )
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=[],
        help="Campaign set name under decode-lab/sets/ (repeatable).",
    )
    parser.add_argument(
        "--doc-id",
        dest="doc_ids",
        action="append",
        default=[],
        help="Specific decoded document ID to include (repeatable).",
    )
    parser.add_argument(
        "--all-decoded",
        action="store_true",
        help="Include every doc_id present in decoded-corpus/manifest.jsonl.",
    )
    parser.add_argument(
        "--decoded-root",
        type=Path,
        default=DEFAULT_DECODED_ROOT,
        help="Decoded corpus root. Default: decoded-corpus/.",
    )
    parser.add_argument(
        "--set-dir",
        type=Path,
        default=DEFAULT_SET_DIR,
        help="Directory containing set .txt files. Default: decode-lab/sets/.",
    )
    parser.add_argument(
        "--index-tsv",
        type=Path,
        default=DEFAULT_INDEX_TSV,
        help="Patra Darpan index.tsv projection used to enrich access metadata. Default: exports/index.tsv.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output JSON path. Default: web/assets/data/search-corpus.json.",
    )
    parser.add_argument(
        "--smoke-report",
        type=Path,
        default=DEFAULT_SMOKE_REPORT,
        help="Smoke report path. Default: reports/search-smoke.md.",
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=1200,
        help="Soft maximum words per chunk before splitting paragraphs. Default: 1200.",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=500,
        help="Preferred minimum words when merging paragraphs. Default: 500.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Write only the JSON corpus artifact, not reports/search-smoke.md.",
    )
    parser.add_argument(
        "--media-mode",
        choices=["none", "captions", "figures"],
        default="figures",
        help=(
            "Attachment handling. none omits attachments; captions records table/figure/page-image "
            "metadata only; figures also copies true .jpg/.jpeg figures. Default: figures."
        ),
    )
    parser.add_argument(
        "--media-output",
        type=Path,
        default=DEFAULT_MEDIA_OUTPUT,
        help="Directory for copied true figures. Default: web/assets/search-media/.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_manifest(decoded_root: Path) -> dict[str, dict[str, Any]]:
    manifest_path = decoded_root / "manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing decoded corpus manifest: {manifest_path}")

    rows: dict[str, dict[str, Any]] = {}
    with manifest_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {manifest_path}:{line_no}: {exc}") from exc
            doc_id = row.get("doc_id")
            if doc_id:
                rows[doc_id] = row
    return rows


def read_index_lookup(index_tsv: Path) -> dict[str, dict[str, str]]:
    if not index_tsv.exists():
        raise FileNotFoundError(f"Missing index.tsv for access metadata enrichment: {index_tsv}")

    rows: dict[str, dict[str, str]] = {}
    with index_tsv.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            gcs_key = (row.get("gcs_key") or "").strip()
            if not gcs_key:
                continue
            rows[gcs_key] = row
            stem = gcs_key.rsplit("/", 1)[-1].removesuffix(".pdf")
            if stem:
                rows.setdefault(stem, row)
    return rows


def read_set_doc_ids(set_dir: Path, set_name: str) -> list[str]:
    path = set_dir / f"{set_name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Missing set file for --set {set_name!r}: {path}")

    doc_ids: list[str] = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            doc_ids.append(line)
    return doc_ids


def select_doc_ids(args: argparse.Namespace, manifest_rows: dict[str, dict[str, Any]]) -> list[str]:
    selected: list[str] = []
    seen: set[str] = set()

    def add(doc_id: str) -> None:
        if doc_id not in seen:
            seen.add(doc_id)
            selected.append(doc_id)

    for set_name in args.sets:
        for doc_id in read_set_doc_ids(args.set_dir, set_name):
            add(doc_id)

    for doc_id in args.doc_ids:
        add(doc_id)

    if args.all_decoded:
        for doc_id in manifest_rows:
            add(doc_id)

    if not selected:
        for doc_id in read_set_doc_ids(args.set_dir, "audit-set"):
            add(doc_id)
    return selected


def plain_markdown(block: str) -> str:
    block = re.sub(r"<!--.*?-->", " ", block, flags=re.DOTALL)
    block = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", block)
    block = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", block)
    block = re.sub(r"`([^`]+)`", r"\1", block)
    block = re.sub(r"\*\*([^*]+)\*\*", r"\1", block)
    block = re.sub(r"\*([^*]+)\*", r"\1", block)
    block = re.sub(r"__([^_]+)__", r"\1", block)
    block = re.sub(r"_([^_]+)_", r"\1", block)
    block = re.sub(r"^\s{0,3}>\s?", "", block, flags=re.MULTILINE)
    block = re.sub(r"^\s{0,3}[-*+]\s+", "", block, flags=re.MULTILINE)
    block = re.sub(r"\[\^([^\]]+)\]", r"\1", block)
    block = html.unescape(block)
    return re.sub(r"\s+", " ", block).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def split_paragraphs(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            text = "\n".join(buf).strip()
            if text:
                paragraphs.append(text)
            buf.clear()

    for line in lines:
        if not line.strip():
            flush()
        else:
            buf.append(line)
    flush()
    return paragraphs


IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


def is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(re.match(r"^:?-{3,}:?$", cell or "") for cell in cells)


def find_table_blocks(block: str) -> list[str]:
    lines = block.splitlines()
    tables: list[str] = []
    index = 0
    while index < len(lines):
        if "|" not in lines[index]:
            index += 1
            continue
        if index + 1 >= len(lines) or not is_table_separator(lines[index + 1]):
            index += 1
            continue

        start = index
        index += 2
        while index < len(lines) and "|" in lines[index].strip():
            index += 1
        tables.append("\n".join(lines[start:index]).strip())
    return tables


def table_dimensions(markdown: str) -> tuple[int, int]:
    rows = [line for line in markdown.splitlines() if "|" in line]
    data_rows = [line for idx, line in enumerate(rows) if idx != 1]
    col_count = 0
    if rows:
        col_count = len([cell for cell in rows[0].strip().strip("|").split("|")])
    return len(data_rows), col_count


def web_media_path(media_output: Path, media_path: Path) -> str:
    try:
        return media_path.resolve().relative_to((ROOT / "web").resolve()).as_posix()
    except ValueError:
        return media_path.as_posix()


def copy_true_figure(
    source_path: Path,
    doc_id: str,
    media_output: Path,
    copied: dict[str, Any],
) -> str | None:
    if not source_path.exists():
        return None

    target_dir = media_output / doc_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source_path.name
    shutil.copy2(source_path, target)
    target_key = str(target.resolve())
    if target_key not in copied["seen"]:
        copied["seen"].add(target_key)
        copied["count"] += 1
        copied["bytes"] += target.stat().st_size
    return web_media_path(media_output, target)


def extract_attachments(
    blocks: list[str],
    doc_root: Path,
    doc_id: str,
    media_mode: str,
    media_output: Path,
    copied: dict[str, Any],
) -> list[dict[str, Any]]:
    if media_mode == "none":
        return []

    attachments: list[dict[str, Any]] = []
    table_seen: set[str] = set()
    image_seen: set[str] = set()

    for block in blocks:
        for table in find_table_blocks(block):
            if table in table_seen:
                continue
            table_seen.add(table)
            row_count, col_count = table_dimensions(table)
            attachments.append(
                {
                    "type": "table",
                    "label": "Table",
                    "markdown": table,
                    "row_count": row_count,
                    "column_count": col_count,
                }
            )

        for match in IMAGE_RE.finditer(block):
            caption = plain_markdown(match.group(1))
            media_ref = match.group(2).strip()
            media_ref = media_ref.split()[0].strip("<>")
            key = f"{caption}\n{media_ref}"
            if key in image_seen:
                continue
            image_seen.add(key)

            suffix = Path(media_ref).suffix.lower()
            source_path = doc_root / media_ref
            source_display = source_path.relative_to(ROOT).as_posix() if source_path.exists() else media_ref
            if suffix in {".jpg", ".jpeg"}:
                web_path = None
                if media_mode == "figures":
                    web_path = copy_true_figure(source_path, doc_id, media_output, copied)
                attachments.append(
                    {
                        "type": "figure",
                        "label": "Figure",
                        "caption": caption,
                        "source_path": source_display,
                        "web_path": web_path,
                    }
                )
            elif suffix == ".png":
                # Page renders are useful evidence pointers, but too large to publish by default.
                attachments.append(
                    {
                        "type": "page_image",
                        "label": "Page image",
                        "caption": caption,
                        "source_path": source_display,
                        "web_path": None,
                    }
                )

    return attachments


def make_heading_path(stack: list[tuple[int, str]]) -> list[str]:
    return [title for _, title in stack]


def sectionize(markdown: str) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    heading_stack: list[tuple[int, str]] = []
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_lines:
            sections.append(
                {
                    "heading_path": make_heading_path(heading_stack),
                    "lines": current_lines,
                }
            )
            current_lines = []

    for raw_line in markdown.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", raw_line)
        if match:
            flush()
            level = len(match.group(1))
            title = plain_markdown(match.group(2))
            heading_stack = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
            heading_stack.append((level, title))
            continue
        current_lines.append(raw_line)
    flush()
    return sections


def build_chunks_for_doc(
    doc: dict[str, Any],
    doc_root: Path,
    markdown: str,
    max_words: int,
    min_words: int,
    media_mode: str,
    media_output: Path,
    copied_media: dict[str, Any],
) -> list[dict[str, Any]]:
    sections = sectionize(markdown)
    chunks: list[dict[str, Any]] = []

    for section in sections:
        paragraphs = split_paragraphs(section["lines"])
        current: list[str] = []
        current_words = 0

        def flush() -> None:
            nonlocal current, current_words
            text = plain_markdown("\n\n".join(current))
            if text:
                attachments = extract_attachments(
                    current,
                    doc_root,
                    doc["doc_id"],
                    media_mode,
                    media_output,
                    copied_media,
                )
                chunk = {
                    **doc,
                    "heading_path": section["heading_path"],
                    "chunk_ordinal": len(chunks) + 1,
                    "text": text,
                    "text_preview": text[:360] + ("..." if len(text) > 360 else ""),
                }
                if attachments:
                    chunk["attachments"] = attachments
                chunks.append(
                    chunk
                )
            current = []
            current_words = 0

        for para in paragraphs:
            para_text = plain_markdown(para)
            if not para_text:
                continue
            para_words = word_count(para_text)
            if current and current_words + para_words > max_words and current_words >= min_words:
                flush()
            current.append(para)
            current_words += para_words
            if current_words > max_words * 1.5:
                flush()
        flush()

    for idx, chunk in enumerate(chunks):
        chunk_id = f"{doc['doc_id']}:c{idx + 1:04d}"
        chunk["chunk_id"] = chunk_id
        chunk["chunk_ordinal"] = idx + 1
        chunk["prev_chunk_id"] = f"{doc['doc_id']}:c{idx:04d}" if idx > 0 else None
        chunk["next_chunk_id"] = f"{doc['doc_id']}:c{idx + 2:04d}" if idx + 1 < len(chunks) else None
    return chunks


def quality_warning_types(quality: dict[str, Any]) -> list[str]:
    warnings = quality.get("warnings") or []
    out: list[str] = []
    for warning in warnings:
        if isinstance(warning, dict) and warning.get("type"):
            out.append(str(warning["type"]))
    return out


def load_doc(
    decoded_root: Path,
    manifest_row: dict[str, Any],
    index_lookup: dict[str, dict[str, str]],
) -> tuple[dict[str, Any], Path, str]:
    doc_id = manifest_row["doc_id"]
    doc_root = decoded_root / "by-doc" / doc_id
    per_doc_manifest_path = doc_root / "manifest.json"
    quality_path = doc_root / "quality.json"
    markdown_path = doc_root / "document.md"

    missing = [p for p in [per_doc_manifest_path, quality_path, markdown_path] if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Decoded doc {doc_id} is missing: {', '.join(str(p) for p in missing)}")

    per_doc_manifest = read_json(per_doc_manifest_path)
    quality = read_json(quality_path)
    source = per_doc_manifest.get("source") or {}
    markdown = markdown_path.read_text(encoding="utf-8")
    index_row = index_lookup.get(source.get("gcs_key") or "") or index_lookup.get(doc_id) or {}
    remote_url = (index_row.get("url") or source.get("source_url") or "").strip()
    ju_url = (index_row.get("ju_url") or "").strip()
    cahc_authored = str(index_row.get("cahc_authored") or "").strip().lower() == "true"

    doc = {
        "doc_id": doc_id,
        "title": source.get("title") or doc_id,
        "author_display": source.get("author_display") or "",
        "year": str(source.get("year") or ""),
        "journal_label": source.get("journal_label") or "",
        "source_url": source.get("source_url") or "",
        "remote_url": remote_url,
        "ju_url": ju_url,
        "gcs_key": source.get("gcs_key") or "",
        "cahc_authored": cahc_authored,
        "decoded_document_path": per_doc_manifest.get("document_md") or manifest_row.get("document_md") or "",
        "quality_status": quality.get("status") or manifest_row.get("status") or "",
        "quality_warnings": quality_warning_types(quality),
        "run_id": per_doc_manifest.get("run_id") or manifest_row.get("run_id") or "",
    }
    return doc, doc_root, markdown


def normalize_search_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.lower()


def tokenize(text: str) -> list[str]:
    normalized = normalize_search_text(text)
    return [t for t in re.findall(r"[\w\u0900-\u097F]+", normalized, flags=re.UNICODE) if t not in STOPWORDS]


def score_chunk(chunk: dict[str, Any], query: str) -> tuple[float, str]:
    query_norm = normalize_search_text(query).strip()
    terms = tokenize(query)
    if not terms:
        return 0.0, ""

    text = chunk.get("text", "")
    fields = " ".join(
        [
            chunk.get("title", ""),
            chunk.get("author_display", ""),
            " ".join(chunk.get("heading_path") or []),
            text,
        ]
    )
    fields_norm = normalize_search_text(fields)
    text_norm = normalize_search_text(text)
    score = 0.0

    if query_norm and query_norm in fields_norm:
        score += 30.0

    for term in terms:
        count = fields_norm.count(term)
        if count:
            score += min(count, 8) * 2.0
        if term in (chunk.get("title") or "").lower():
            score += 8.0
        if term in " ".join(chunk.get("heading_path") or []).lower():
            score += 6.0
        if term in (chunk.get("author_display") or "").lower():
            score += 4.0

    matched_terms = sum(1 for term in set(terms) if term in fields_norm)
    if matched_terms > 1:
        score += matched_terms * 3.0

    preferred_terms = sorted(set(terms), key=len, reverse=True)
    pos = next((text_norm.find(term) for term in preferred_terms if term in text_norm), 0)
    start = max(0, pos - 120)
    end = min(len(text), pos + 240)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return score, snippet


def write_smoke_report(path: Path, artifact: dict[str, Any]) -> None:
    chunks = artifact["chunks"]
    lines = [
        "# Search Smoke Report",
        "",
        f"- Generated at: `{artifact['metadata']['generated_at']}`",
        f"- Document count: {artifact['metadata']['doc_count']}",
        f"- Chunk count: {artifact['metadata']['chunk_count']}",
        "",
    ]

    for query in SMOKE_QUERIES:
        scored: list[tuple[float, dict[str, Any], str]] = []
        for chunk in chunks:
            score, snippet = score_chunk(chunk, query)
            if score > 0:
                scored.append((score, chunk, snippet))
        scored.sort(key=lambda item: (-item[0], item[1]["doc_id"], item[1]["chunk_ordinal"]))

        lines.extend([f"## {query}", ""])
        if not scored:
            lines.extend(["No hits.", ""])
            continue

        score, chunk, snippet = scored[0]
        heading = " > ".join(chunk.get("heading_path") or []) or "(no heading)"
        lines.extend(
            [
                f"- Top result: `{chunk['doc_id']}`",
                f"- Title: {chunk.get('title') or ''}",
                f"- Heading: {heading}",
                f"- Score: {score:.1f}",
                f"- Chunk: `{chunk['chunk_id']}`",
                f"- Snippet: {snippet}",
                "- Credibility: likely relevant; human review recommended",
                "",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    decoded_root = args.decoded_root.resolve()
    manifest_rows = read_manifest(decoded_root)
    index_lookup = read_index_lookup(args.index_tsv.resolve())
    selected_doc_ids = select_doc_ids(args, manifest_rows)

    missing = [doc_id for doc_id in selected_doc_ids if doc_id not in manifest_rows]
    if missing:
        print("Missing selected doc_id(s) from decoded-corpus/manifest.jsonl:", file=sys.stderr)
        for doc_id in missing:
            print(f"  - {doc_id}", file=sys.stderr)
        return 2

    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    copied_media = {"count": 0, "bytes": 0, "seen": set()}
    media_output = args.media_output.resolve()
    for doc_id in selected_doc_ids:
        doc, doc_root, markdown = load_doc(decoded_root, manifest_rows[doc_id], index_lookup)
        doc_chunks = build_chunks_for_doc(
            doc,
            doc_root,
            markdown,
            args.max_words,
            args.min_words,
            args.media_mode,
            media_output,
            copied_media,
        )
        doc["chunk_count"] = len(doc_chunks)
        documents.append(doc)
        chunks.extend(doc_chunks)

    generated_at = utc_now()
    artifact = {
        "schema_version": "search-corpus.v0.1",
        "metadata": {
            "generated_at": generated_at,
            "decoded_root": str(decoded_root),
            "selected_sets": args.sets or ([] if args.doc_ids or args.all_decoded else ["audit-set"]),
            "selected_doc_ids": args.doc_ids,
            "all_decoded": bool(args.all_decoded),
            "doc_count": len(documents),
            "chunk_count": len(chunks),
            "media_mode": args.media_mode,
            "media_output": web_media_path(media_output, media_output),
            "copied_media_count": copied_media["count"],
            "copied_media_bytes": copied_media["bytes"],
            "chunking": {
                "strategy": "markdown-section-first",
                "min_words": args.min_words,
                "max_words": args.max_words,
            },
        },
        "documents": documents,
        "chunks": chunks,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.skip_smoke:
        write_smoke_report(args.smoke_report, artifact)

    print(f"Wrote {args.output} ({len(documents)} docs, {len(chunks)} chunks)")
    if not args.skip_smoke:
        print(f"Wrote {args.smoke_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
