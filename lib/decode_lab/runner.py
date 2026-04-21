from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.config import BUILD_DIR, EXPORTS_DIR, PROJECT_ROOT, resolve_shared_asset_root
from lib.decode_lab.campaign_sets import (
    DEFAULT_CAMPAIGN_SET,
    list_campaign_sets,
    resolve_doc_selection,
)


SCHEMA_VERSION = "decode-lab.v0.1"

PAGE_TEXT_MIN_CHARS = 25


@dataclass(frozen=True)
class IndexRecord:
    doc_id: str
    title: str
    author_display: str
    year: str
    journal_label: str
    source_url: str
    gcs_key: str
    local_pdf_path: Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Darpan Decode Lab: extract, audit, and assemble PDF content.\n\n"
            "Default mode runs deterministic extraction (pdftotext, pdffonts, etc.)\n"
            "on the micro-5 corpus and writes JSONL artifacts + per-doc review.md.\n\n"
            "Add --extractor gemini:<model> to run full-document Gemini extraction\n"
            "on all pages (PDF sent directly, 5-page chunks, with nak\u1e63atra lookup).\n"
            "Models: flash-lite, flash, 3-flash-med, 3-flash.\n\n"
            "Add --fallback gemini for legacy per-page PNG fallback on risky pages.\n"
            "Add --assemble to produce document.md Markdown for each PDF.\n"
            "Use --assemble-only to assemble a previous run without re-extracting."
        ),
        epilog=(
            "Examples:\n"
            "  Decode next 10 unfinished docs in a campaign:\n"
            "    uv run python scripts/run_decode_lab.py --set astro-math-indic-raster \\\n"
            "      --run-id build-astro-math-indic-raster --extractor gemini:3-flash-med \\\n"
            "      --tier standard --batch-size 10 --assemble\n\n"
            "  Reassemble an existing run after assembler/Markdown fixups:\n"
            "    uv run python scripts/run_decode_lab.py --assemble-only \\\n"
            "      --run-id build-astro-math-indic-raster\n\n"
            "  Fresh Gemini repair for one suspect document, bypassing response cache:\n"
            "    uv run python scripts/run_decode_lab.py --doc-id DOC_ID \\\n"
            "      --run-id repair-DOC_ID --extractor gemini:3-flash-med \\\n"
            "      --tier standard --bypass-gemini-cache --force --assemble\n\n"
            "  Pagewise repair when a 5-page Gemini chunk fails:\n"
            "    uv run python scripts/run_decode_lab.py --doc-id DOC_ID \\\n"
            "      --run-id repair-DOC_ID-pagewise --extractor gemini:3-flash-med \\\n"
            "      --tier standard --bypass-gemini-cache --gemini-chunk-size 1 \\\n"
            "      --force --assemble\n\n"
            "  After a repair run, update decoded-corpus/ with:\n"
            "    uv run python scripts/build_decoded_corpus.py --from-run repair-DOC_ID \\\n"
            "      --replace-doc DOC_ID"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--set",
        action="append",
        dest="campaign_sets",
        choices=list_campaign_sets() or None,
        help=(
            "Campaign set to include (repeatable). "
            f"Defaults to {DEFAULT_CAMPAIGN_SET!r}. "
            "Set files live under decode-lab/sets/."
        ),
    )
    parser.add_argument(
        "--doc-id",
        action="append",
        help=(
            "Document ID to include (repeatable). Can be combined with --set. "
            f"Defaults to the {DEFAULT_CAMPAIGN_SET!r} campaign set when neither "
            "--set nor --doc-id is provided."
        ),
    )
    parser.add_argument(
        "--index-tsv",
        type=Path,
        default=EXPORTS_DIR / "index.tsv",
        help="Path to the Patra Darpan index.tsv projection. "
        "Default: exports/index.tsv.",
    )
    parser.add_argument(
        "--pdf-root",
        type=Path,
        default=resolve_shared_asset_root(),
        help="Local PDF corpus root (contains ijhs/ and other/). "
        "Default: sibling patra-darpan/corpus.",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=BUILD_DIR / "decode-lab",
        help="Parent directory for run output packets. "
        "Default: .build~/decode-lab.",
    )
    parser.add_argument(
        "--run-id",
        help="Explicit run ID (becomes the output subdirectory name). "
        "Default: UTC timestamp.",
    )
    parser.add_argument(
        "--extractor",
        default="local",
        help="Extraction mode. "
        "'local': deterministic only (default, no API calls). "
        "'gemini:flash-lite': Gemini 2.5 Flash Lite, no thinking (~$5.65/corpus). "
        "'gemini:flash': Gemini 2.5 Flash, medium thinking. "
        "'gemini:3-flash-med': Gemini 3 Flash Preview, medium thinking. "
        "'gemini:3-flash': Gemini 3 Flash Preview, high thinking (~$43/corpus). "
        "Gemini modes send the PDF directly in 5-page chunks with the "
        "Studio-refined prompt and nak\u1e63atra lookup. "
        "Requires GEMINI_API_KEY in environment.",
    )
    parser.add_argument(
        "--tier",
        choices=["standard", "flex"],
        default="standard",
        help="Gemini synchronous inference service tier for --extractor gemini:* runs. "
        "'standard' is the default. 'flex' requests cost-optimized, lower-priority "
        "traffic and is only used for Gemini extraction calls.",
    )
    parser.add_argument(
        "--bypass-gemini-cache",
        action="store_true",
        default=False,
        help="For --extractor gemini:* runs, call Gemini even when cached chunk "
        "responses exist. The new responses still update the cache. Use for "
        "targeted repair when cached Markdown is suspect.",
    )
    parser.add_argument(
        "--gemini-chunk-size",
        type=int,
        default=None,
        help="Override Gemini extraction chunk size in pages. Useful for targeted "
        "repair when a 5-page chunk fails, for example --gemini-chunk-size 1.",
    )
    parser.add_argument(
        "--fallback",
        choices=["none", "gemini"],
        default="none",
        help="(Legacy) Per-page PNG fallback for risky pages. "
        "Prefer --extractor gemini:* for new runs. "
        "'none': no legacy fallback. "
        "'gemini': render+crop risky pages via Gemini 2.0 Flash.",
    )
    parser.add_argument(
        "--assemble",
        action="store_true",
        default=False,
        help="Assemble document.md eagerly after each document finishes. "
        "Combines baseline text, fallback tables, risk markers, image refs, "
        "and Gemini chunks into one readable Markdown file per document.",
    )
    parser.add_argument(
        "--assemble-lazy",
        action="store_true",
        default=False,
        help="When used with --assemble, preserve the older batch behavior: "
        "assemble all documents only after extraction for the full run finishes.",
    )
    parser.add_argument(
        "--assemble-only",
        action="store_true",
        default=False,
        help="Skip extraction entirely and assemble document.md from an "
        "existing run directory. Requires --run-id pointing to a previous run. "
        "Useful for re-assembling after manual edits to fallback outputs.",
    )
    parser.add_argument(
        "--batch-size",
        "--batch",
        type=int,
        default=None,
        help="Process the next N unfinished documents from the selected set. "
        "Batching happens after completed docs in the run are skipped. "
        "Default: process all unfinished selected documents.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help="Compatibility alias. Runs are upsert-by-default: existing run "
        "directories are reused, completed docs are skipped, and unfinished "
        "docs are processed.",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        default=False,
        help="Reuse an existing run directory to repair failed or partial work. "
        "Runs are upsert-by-default; this flag is retained to make repair "
        "intent explicit in command history.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Delete and recreate an existing run directory. Destructive; "
        "prefer --resume or --repair for long Gemini runs.",
    )
    return parser


def run_decode_lab(args: argparse.Namespace) -> Path:
    selected_doc_ids, resolved_sets = resolve_doc_selection(
        set_names=getattr(args, "campaign_sets", None),
        doc_ids=args.doc_id,
    )
    batch_size = getattr(args, "batch_size", None)
    if batch_size is not None and batch_size < 1:
        raise ValueError("--batch-size must be a positive integer")
    started_at = _utc_now()
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = args.out_root / run_id
    run_existed = run_dir.exists()
    if run_dir.exists():
        if getattr(args, "force", False):
            _progress(f"force removing existing run_dir={run_dir}")
            shutil.rmtree(run_dir)
            run_dir.mkdir(parents=True, exist_ok=False)
        else:
            _progress(f"reusing existing run_dir={run_dir} mode=upsert")
            run_dir.mkdir(parents=True, exist_ok=True)
    else:
        _progress(f"creating run_dir={run_dir} mode=upsert")
        run_dir.mkdir(parents=True, exist_ok=False)
    if getattr(args, "force", False):
        run_existed = False

    records = _load_index_records(args.index_tsv, args.pdf_root, selected_doc_ids)
    available_tools = _available_tools(["pdfinfo", "pdffonts", "pdfimages", "pdftotext"])

    existing_rows = _load_run_tables(run_dir) if run_existed else _empty_run_tables()
    documents: list[dict[str, Any]] = existing_rows["documents"]
    pages: list[dict[str, Any]] = existing_rows["pages"]
    chunks: list[dict[str, Any]] = existing_rows["chunks"]
    risks: list[dict[str, Any]] = existing_rows["risks"]
    images: list[dict[str, Any]] = existing_rows["images"]
    tables: list[dict[str, Any]] = existing_rows["tables"]
    fallbacks: list[dict[str, Any]] = existing_rows["fallbacks"]

    require_document_md = bool(getattr(args, "assemble", False))
    complete_doc_ids = {
        doc_id
        for doc_id in selected_doc_ids
        if _doc_is_complete(
            run_dir / "by-doc" / doc_id,
            require_document_md=require_document_md,
            extractor=getattr(args, "extractor", "local"),
        )
    }
    unfinished_doc_ids = [doc_id for doc_id in selected_doc_ids if doc_id not in complete_doc_ids]
    process_doc_ids = unfinished_doc_ids[:batch_size] if batch_size is not None else unfinished_doc_ids
    total_docs = len(process_doc_ids)
    _progress(
        f"decode run start run_id={run_id} selected={len(selected_doc_ids)} "
        f"complete={len(complete_doc_ids)} unfinished={len(unfinished_doc_ids)} "
        f"batch_size={batch_size or 'all'} processing={total_docs} "
        f"extractor={getattr(args, 'extractor', 'local')} "
        f"tier={getattr(args, 'tier', 'standard')}"
    )

    for doc_index, doc_id in enumerate(process_doc_ids, start=1):
        _progress(f"[{doc_index}/{total_docs}] document start doc_id={doc_id}")
        documents, pages, chunks, risks, images, tables, fallbacks = _drop_doc_rows(
            doc_id=doc_id,
            documents=documents,
            pages=pages,
            chunks=chunks,
            risks=risks,
            images=images,
            tables=tables,
            fallbacks=fallbacks,
        )
        record = records.get(doc_id)
        if record is None:
            documents.append(
                {
                    "doc_id": doc_id,
                    "title": "",
                    "author_display": "",
                    "year": "",
                    "source_url": "",
                    "local_pdf_path": "",
                    "sha256": "",
                    "byte_size": None,
                    "page_count": None,
                    "status": "missing_index_record",
                    "status_reason": f"{doc_id} was not found in {args.index_tsv}",
                }
            )
            _progress(f"[{doc_index}/{total_docs}] document missing doc_id={doc_id}")
            continue

        doc_dir = run_dir / "by-doc" / record.doc_id
        _create_doc_dirs(doc_dir)
        source = _source_payload(record)
        _write_json(doc_dir / "source.json", source)

        doc_result = _process_document(
            record=record,
            doc_dir=doc_dir,
            available_tools=available_tools,
        )

        extractor = getattr(args, 'extractor', 'local')
        if extractor.startswith('gemini:'):
            model_key = extractor.split(':', 1)[1]
            doc_result["fallbacks"].extend(
                _run_gemini_extract(
                    record=record,
                    doc_dir=doc_dir,
                    page_count=doc_result["document"].get("page_count") or 0,
                    model_key=model_key,
                    service_tier=getattr(args, "tier", "standard"),
                    bypass_cache=getattr(args, "bypass_gemini_cache", False),
                    chunk_size_override=getattr(args, "gemini_chunk_size", None),
                )
            )
        elif getattr(args, 'fallback', 'none') == 'gemini':
            doc_result["fallbacks"].extend(
                _run_table_fallbacks(
                    record=record,
                    doc_dir=doc_dir,
                    tables=doc_result["tables"],
                    risks=doc_result["risks"],
                )
            )
            doc_result["fallbacks"].extend(
                _run_page_fallbacks(
                    record=record,
                    doc_dir=doc_dir,
                    tables=doc_result["tables"],
                    risks=doc_result["risks"],
                )
            )
        # Extract images and create cache symlink
        doc_sha = doc_result["document"].get("sha256", "")
        if doc_sha and record.local_pdf_path.exists():
            from lib.decode_lab.image_extract import extract_images, ensure_image_symlink

            doc_result["images"] = extract_images(
                pdf_path=record.local_pdf_path,
                doc_id=record.doc_id,
                pdf_sha256=doc_sha,
                images_jsonl=doc_result["images"],
            )
            ensure_image_symlink(doc_dir, record.doc_id)

        documents.append(doc_result["document"])
        pages.extend(doc_result["pages"])
        chunks.extend(doc_result["chunks"])
        risks.extend(doc_result["risks"])
        images.extend(doc_result["images"])
        tables.extend(doc_result["tables"])
        fallbacks.extend(doc_result["fallbacks"])

        _write_json(
            doc_dir / "manifest.json",
            _doc_manifest(record.doc_id, doc_result, doc_dir, run_dir),
        )
        _write_review_md(doc_dir / "review.md", record, doc_result)
        if getattr(args, "assemble", False) and not getattr(args, "assemble_lazy", False):
            _write_run_tables(
                run_dir=run_dir,
                documents=documents,
                pages=pages,
                chunks=chunks,
                risks=risks,
                images=images,
                tables=tables,
                fallbacks=fallbacks,
                retrieval_samples=_build_retrieval_samples(chunks),
            )
            from lib.decode_lab.assembler import assemble_run

            written = assemble_run(run_dir)
            doc_md = doc_dir / "document.md"
            if doc_md in written or doc_md.exists():
                _progress(f"assembled document doc_id={record.doc_id} path={doc_md}")
        _progress(
            f"[{doc_index}/{total_docs}] document done doc_id={record.doc_id} "
            f"status={doc_result['document']['status']} "
            f"pages={doc_result['document'].get('page_count')} "
            f"fallbacks={len(doc_result['fallbacks'])}"
        )
    if not process_doc_ids:
        _progress("decode run upsert found no unfinished selected documents")

    retrieval_samples = _build_retrieval_samples(chunks)

    _write_run_tables(
        run_dir=run_dir,
        documents=documents,
        pages=pages,
        chunks=chunks,
        risks=risks,
        images=images,
        tables=tables,
        fallbacks=fallbacks,
        retrieval_samples=retrieval_samples,
    )

    finished_at = _utc_now()

    # Resolve model config for logging (if Gemini extractor is used)
    extractor_flag = getattr(args, 'extractor', 'local')
    model_config_log: dict[str, Any] = {}
    if extractor_flag.startswith('gemini:'):
        from lib.decode_lab.model_configs import get_model_config

        _cfg = get_model_config(extractor_flag.split(':', 1)[1])
        model_config_log = {
            "config_name": _cfg.name,
            "api_model": _cfg.model_name,
            "thinking_level": _cfg.thinking_level,
            "chunk_size": _cfg.chunk_size,
            "prompt_template_sha256": hashlib.sha256(
                _cfg.prompt_template.encode("utf-8")
            ).hexdigest(),
            "prompt_template": _cfg.prompt_template,
        }

    _write_json(
        run_dir / "run-manifest.json",
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": finished_at,
            "command": sys.argv,
            "project_root": str(PROJECT_ROOT),
            "index_tsv": str(args.index_tsv),
            "pdf_root": str(args.pdf_root),
            "out_root": str(args.out_root),
            "selected_doc_ids": selected_doc_ids,
            "campaign_sets": resolved_sets,
            "tool_paths": available_tools,
            "pymupdf_available": _pymupdf_available(),
            "extractor": extractor_flag,
            "model_config": model_config_log or None,
            "service_tier_requested": getattr(args, "tier", "standard"),
            "bypass_gemini_cache": getattr(args, "bypass_gemini_cache", False),
            "gemini_chunk_size_override": getattr(args, "gemini_chunk_size", None),
            "fallback_mode": getattr(args, 'fallback', 'none'),
        },
    )
    _write_audit_md(
        run_dir / "audit.md",
        selected_doc_ids=selected_doc_ids,
        documents=documents,
        pages=pages,
        risks=risks,
        chunks=chunks,
        images=images,
        retrieval_samples=retrieval_samples,
        extractor=extractor_flag,
        model_config_log=model_config_log,
        fallbacks=fallbacks,
    )
    _progress(f"decode run done run_id={run_id} run_dir={run_dir}")
    return run_dir


def _load_index_records(
    index_tsv: Path, pdf_root: Path, selected_doc_ids: list[str]
) -> dict[str, IndexRecord]:
    selected = set(selected_doc_ids)
    records: dict[str, IndexRecord] = {}
    with index_tsv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            gcs_key = row.get("gcs_key", "")
            if not gcs_key:
                continue
            doc_id = Path(gcs_key).stem
            if doc_id not in selected:
                continue
            records[doc_id] = IndexRecord(
                doc_id=doc_id,
                title=row.get("paper", ""),
                author_display=row.get("author", ""),
                year=row.get("year", ""),
                journal_label=row.get("journal", ""),
                source_url=row.get("url", ""),
                gcs_key=gcs_key,
                local_pdf_path=pdf_root / gcs_key,
            )
    return records


def _process_document(
    record: IndexRecord,
    doc_dir: Path,
    available_tools: dict[str, str | None],
) -> dict[str, Any]:
    extractors_dir = doc_dir / "extractors"
    pages_dir = doc_dir / "pages"
    risks: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    images: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    fallbacks: list[dict[str, Any]] = []

    document = {
        "doc_id": record.doc_id,
        "title": record.title,
        "author_display": record.author_display,
        "year": record.year,
        "source_url": record.source_url,
        "local_pdf_path": str(record.local_pdf_path),
        "sha256": "",
        "byte_size": None,
        "page_count": None,
        "status": "pending",
        "status_reason": "",
    }

    if not record.local_pdf_path.exists():
        document["status"] = "missing_pdf"
        document["status_reason"] = f"Local PDF not found: {record.local_pdf_path}"
        _write_json(doc_dir / "profile.json", {"document": document, "extractors": {}})
        return _doc_result(document, pages, chunks, risks, images, tables, fallbacks)

    _ensure_source_pdf_symlink(record.local_pdf_path, doc_dir / "source.pdf")
    document["sha256"] = _sha256_file(record.local_pdf_path)
    document["byte_size"] = record.local_pdf_path.stat().st_size

    extractor_status: dict[str, Any] = {}
    pdfinfo_text = _run_to_text_file(
        ["pdfinfo", str(record.local_pdf_path)],
        extractors_dir / "pdfinfo.txt",
        available_tools,
    )
    extractor_status["pdfinfo"] = pdfinfo_text["status"]
    page_count = _parse_page_count(pdfinfo_text.get("stdout", ""))
    document["page_count"] = page_count

    pdffonts_text = _run_to_text_file(
        ["pdffonts", str(record.local_pdf_path)],
        extractors_dir / "pdffonts.txt",
        available_tools,
    )
    extractor_status["pdffonts"] = pdffonts_text["status"]
    risks.extend(_font_risks(record.doc_id, pdffonts_text.get("stdout", "")))

    pdfimages_text = _run_to_text_file(
        ["pdfimages", "-list", str(record.local_pdf_path)],
        extractors_dir / "pdfimages.txt",
        available_tools,
    )
    extractor_status["pdfimages"] = pdfimages_text["status"]
    images.extend(_parse_pdfimages(record.doc_id, pdfimages_text.get("stdout", "")))

    layout_path = extractors_dir / "pdftotext-layout.txt"
    layout_result = _run_to_output_file(
        ["pdftotext", "-layout", str(record.local_pdf_path), str(layout_path)],
        layout_path,
        available_tools,
    )
    extractor_status["pdftotext_layout"] = layout_result["status"]

    bbox_path = extractors_dir / "pdftotext-bbox.html"
    bbox_result = _run_to_output_file(
        ["pdftotext", "-bbox-layout", str(record.local_pdf_path), str(bbox_path)],
        bbox_path,
        available_tools,
    )
    extractor_status["pdftotext_bbox_layout"] = bbox_result["status"]

    pymupdf_status = _write_pymupdf_blocks(record.local_pdf_path, doc_dir, risks)
    extractor_status["pymupdf_blocks"] = pymupdf_status

    if page_count is None:
        page_count = _fallback_page_count_from_layout(layout_path)
        document["page_count"] = page_count

    for page_number in range(1, (page_count or 0) + 1):
        page_path = pages_dir / f"p{page_number:04d}.txt"
        blocks_path = pages_dir / f"p{page_number:04d}.blocks.jsonl"
        if not blocks_path.exists():
            _write_jsonl(blocks_path, [])
        page_result = _run_to_output_file(
            [
                "pdftotext",
                "-layout",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                str(record.local_pdf_path),
                str(page_path),
            ],
            page_path,
            available_tools,
        )
        page_text = page_path.read_text(encoding="utf-8", errors="replace") if page_path.exists() else ""
        page_risks = _text_risks(record.doc_id, page_number, page_text, "pdftotext-layout")
        if len(page_text.strip()) < PAGE_TEXT_MIN_CHARS:
            page_risks.append(
                {
                    "risk_id": _risk_id(record.doc_id, page_number, "low_text_density", len(risks) + len(page_risks)),
                    "doc_id": record.doc_id,
                    "page_number": page_number,
                    "risk_type": "low_text_density",
                    "severity": "warning",
                    "extractor": "pdftotext-layout",
                    "bbox": None,
                    "font_name": None,
                    "evidence": f"Only {len(page_text.strip())} non-whitespace characters extracted.",
                    "recommended_action": "Profile as scanned, image-only, or malformed text layer before indexing.",
                }
            )
        risks.extend(page_risks)
        page_tables = _table_candidates(
            record.doc_id, page_number, page_text, len(tables),
            bbox_html_path=bbox_path,
        )
        tables.extend(page_tables)

        page_risk_types = sorted({risk["risk_type"] for risk in page_risks})
        page_image_count = sum(1 for image in images if image.get("page_number") == page_number)
        page_row = {
            "page_id": f"{record.doc_id}:p{page_number:04d}",
            "doc_id": record.doc_id,
            "page_number": page_number,
            "width": None,
            "height": None,
            "text_char_count": len(page_text),
            "extractor": "pdftotext-layout",
            "extraction_status": page_result["status"],
            "risk_count": len(page_risks),
            "image_count": page_image_count,
            "table_count": len(page_tables),
        }
        pages.append(page_row)
        _write_jsonl(pages_dir / f"p{page_number:04d}.risks.jsonl", page_risks)

        if page_text.strip():
            chunks.append(
                {
                    "chunk_id": f"{record.doc_id}:p{page_number:04d}:c0001",
                    "doc_id": record.doc_id,
                    "page_start": page_number,
                    "page_end": page_number,
                    "chunk_ordinal": 1,
                    "text": page_text.strip(),
                    "text_sha256": _sha256_text(page_text.strip()),
                    "extractor": "pdftotext-layout",
                    "extraction_version": SCHEMA_VERSION,
                    "risk_flags": page_risk_types,
                }
            )

    document["status"] = "ok" if document["page_count"] else "failed"
    document["status_reason"] = "" if document["status"] == "ok" else "Could not determine page count."

    _write_json(
        doc_dir / "profile.json",
        {
            "document": document,
            "extractors": extractor_status,
            "risk_count": len(risks),
            "image_count": len(images),
            "table_count": len(tables),
            "chunk_count": len(chunks),
        },
    )
    return _doc_result(document, pages, chunks, risks, images, tables, fallbacks)


def _create_doc_dirs(doc_dir: Path) -> None:
    (doc_dir / "extractors").mkdir(parents=True, exist_ok=True)
    (doc_dir / "pages").mkdir(parents=True, exist_ok=True)
    (doc_dir / "fallbacks").mkdir(parents=True, exist_ok=True)


def _run_gemini_extract(
    *,
    record: IndexRecord,
    doc_dir: Path,
    page_count: int,
    model_key: str,
    service_tier: str,
    bypass_cache: bool,
    chunk_size_override: int | None,
) -> list[dict[str, Any]]:
    """Run full-document Gemini extraction using the PDF-native pipeline."""
    from lib.decode_lab.gemini_extract import extract_document
    from lib.decode_lab.model_configs import get_model_config

    config = get_model_config(model_key)
    if chunk_size_override is not None:
        if chunk_size_override < 1:
            raise ValueError("--gemini-chunk-size must be a positive integer")
        config = replace(config, chunk_size=chunk_size_override)
    if page_count < 1:
        return []
    return extract_document(
        pdf_path=record.local_pdf_path,
        page_count=page_count,
        doc_id=record.doc_id,
        config=config,
        work_dir=doc_dir / "fallbacks",
        service_tier=service_tier,
        bypass_cache=bypass_cache,
    )


def _run_table_fallbacks(
    *,
    record: IndexRecord,
    doc_dir: Path,
    tables: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run Gemini fallback on table candidates that overlap with risky pages."""
    from lib.decode_lab.gemini_fallback import run_gemini_table_fallback

    risky_pages = {
        r["page_number"]
        for r in risks
        if r["risk_type"] in {"control_characters", "low_text_density"}
        and r.get("page_number") is not None
    }
    fallback_records: list[dict[str, Any]] = []
    for table in tables:
        if table.get("bbox") is None:
            continue
        if table["page_number"] not in risky_pages:
            continue
        results = run_gemini_table_fallback(
            pdf_path=record.local_pdf_path,
            page_number=table["page_number"],
            bbox=table["bbox"],
            table_id=table["table_id"],
            doc_id=record.doc_id,
            work_dir=doc_dir / "fallbacks",
        )
        fallback_records.extend(results)
    return fallback_records


def _run_page_fallbacks(
    *,
    record: IndexRecord,
    doc_dir: Path,
    tables: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run Gemini full-page fallback on low_text_density pages.

    Only targets pages that have low_text_density risk AND do not already
    have a table fallback (to avoid duplicate Gemini calls for the same page).
    """
    from lib.decode_lab.gemini_fallback import run_gemini_page_fallback

    low_density_pages = {
        r["page_number"]
        for r in risks
        if r["risk_type"] == "low_text_density"
        and r.get("page_number") is not None
    }
    # Exclude pages already covered by table fallbacks
    table_fallback_pages = {t["page_number"] for t in tables if t.get("bbox")}
    target_pages = sorted(low_density_pages - table_fallback_pages)

    fallback_records: list[dict[str, Any]] = []
    for page_number in target_pages:
        results = run_gemini_page_fallback(
            pdf_path=record.local_pdf_path,
            page_number=page_number,
            doc_id=record.doc_id,
            work_dir=doc_dir / "fallbacks",
        )
        fallback_records.extend(results)
    return fallback_records


def _source_payload(record: IndexRecord) -> dict[str, Any]:
    return {
        "doc_id": record.doc_id,
        "title": record.title,
        "author_display": record.author_display,
        "year": record.year,
        "journal_label": record.journal_label,
        "source_url": record.source_url,
        "gcs_key": record.gcs_key,
        "local_pdf_path": str(record.local_pdf_path),
    }


def _ensure_source_pdf_symlink(source_pdf: Path, link_path: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    link_path.symlink_to(source_pdf)


def _doc_result(
    document: dict[str, Any],
    pages: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    images: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fallbacks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "document": document,
        "pages": pages,
        "chunks": chunks,
        "risks": risks,
        "images": images,
        "tables": tables,
        "fallbacks": fallbacks,
    }


def _doc_manifest(
    doc_id: str, doc_result: dict[str, Any], doc_dir: Path, run_dir: Path
) -> dict[str, Any]:
    rel = lambda path: str(path.relative_to(run_dir))
    return {
        "doc_id": doc_id,
        "status": doc_result["document"]["status"],
        "artifact_paths": {
            "review": rel(doc_dir / "review.md"),
            "source": rel(doc_dir / "source.json"),
            "source_pdf": rel(doc_dir / "source.pdf"),
            "profile": rel(doc_dir / "profile.json"),
            "extractors": rel(doc_dir / "extractors"),
            "pages": rel(doc_dir / "pages"),
            "fallbacks": rel(doc_dir / "fallbacks"),
        },
        "row_counts": {
            "pages": len(doc_result["pages"]),
            "chunks": len(doc_result["chunks"]),
            "risks": len(doc_result["risks"]),
            "images": len(doc_result["images"]),
            "tables": len(doc_result["tables"]),
            "fallbacks": len(doc_result["fallbacks"]),
        },
    }


def _available_tools(tool_names: list[str]) -> dict[str, str | None]:
    return {name: shutil.which(name) for name in tool_names}


def _run_to_text_file(
    command: list[str], output_path: Path, available_tools: dict[str, str | None]
) -> dict[str, Any]:
    tool = Path(command[0]).name
    if not available_tools.get(tool):
        payload = {"status": "skipped", "reason": f"{tool} not found", "stdout": "", "stderr": ""}
        _write_text(output_path, json.dumps(payload, indent=2) + "\n")
        return payload

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    payload = {
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_text(output_path, completed.stdout)
    if completed.stderr:
        _write_text(output_path.with_suffix(output_path.suffix + ".stderr"), completed.stderr)
    return payload


def _run_to_output_file(
    command: list[str], output_path: Path, available_tools: dict[str, str | None]
) -> dict[str, Any]:
    tool = Path(command[0]).name
    if not available_tools.get(tool):
        _write_text(output_path, "")
        return {"status": "skipped", "reason": f"{tool} not found"}

    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.stderr:
        _write_text(output_path.with_suffix(output_path.suffix + ".stderr"), completed.stderr)
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stderr": completed.stderr,
    }


def _write_pymupdf_blocks(pdf_path: Path, doc_dir: Path, risks: list[dict[str, Any]]) -> str:
    if not _pymupdf_available():
        for blocks_path in (doc_dir / "pages").glob("*.blocks.jsonl"):
            _write_jsonl(blocks_path, [])
        _write_jsonl(doc_dir / "extractors" / "pymupdf-blocks.jsonl", [])
        return "skipped"

    import fitz  # type: ignore[import-not-found]

    all_spans: list[dict[str, Any]] = []
    document = fitz.open(pdf_path)
    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            page_spans: list[dict[str, Any]] = []
            page_dict = page.get_text("dict")
            for block_index, block in enumerate(page_dict.get("blocks", [])):
                for line_index, line in enumerate(block.get("lines", [])):
                    for span_index, span in enumerate(line.get("spans", [])):
                        text = span.get("text", "")
                        span_row = {
                            "doc_id": Path(pdf_path).stem,
                            "page_number": page_number,
                            "block_index": block_index,
                            "line_index": line_index,
                            "span_index": span_index,
                            "bbox": span.get("bbox"),
                            "font_name": span.get("font"),
                            "size": span.get("size"),
                            "text": text,
                        }
                        all_spans.append(span_row)
                        page_spans.append(span_row)
                        for risk in _span_text_risks(span_row):
                            risk["risk_id"] = _risk_id(
                                Path(pdf_path).stem,
                                page_number,
                                risk["risk_type"],
                                len(risks),
                            )
                            risks.append(risk)
            _write_jsonl(doc_dir / "pages" / f"p{page_number:04d}.blocks.jsonl", page_spans)
    finally:
        document.close()

    _write_jsonl(doc_dir / "extractors" / "pymupdf-blocks.jsonl", all_spans)
    return "ok"


def _pymupdf_available() -> bool:
    try:
        import fitz  # noqa: F401
    except Exception:
        return False
    return True


def _parse_page_count(pdfinfo_output: str) -> int | None:
    for line in pdfinfo_output.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _fallback_page_count_from_layout(layout_path: Path) -> int | None:
    if not layout_path.exists():
        return None
    text = layout_path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return None
    return max(1, text.count("\f") + 1)


def _font_risks(doc_id: str, pdffonts_output: str) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    for line in pdffonts_output.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] in {"name", "------------------------------------"}:
            continue
        uni = parts[-3]
        if uni == "no":
            risks.append(
                {
                    "risk_id": _risk_id(doc_id, None, "font_missing_unicode_map", len(risks)),
                    "doc_id": doc_id,
                    "page_number": None,
                    "risk_type": "font_missing_unicode_map",
                    "severity": "warning",
                    "extractor": "pdffonts",
                    "bbox": None,
                    "font_name": parts[0],
                    "evidence": line,
                    "recommended_action": "Inspect affected spans before accepting text for indexing.",
                }
            )
    return risks


def _parse_pdfimages(doc_id: str, pdfimages_output: str) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    for line in pdfimages_output.splitlines():
        parts = line.split()
        if len(parts) < 12 or not parts[0].isdigit():
            continue
        images.append(
            {
                "image_id": f"{doc_id}:img{len(images) + 1:04d}",
                "doc_id": doc_id,
                "page_number": int(parts[0]),
                "bbox": None,
                "width": _int_or_none(parts[3]),
                "height": _int_or_none(parts[4]),
                "source": "pdfimages -list",
                "color": parts[5],
                "bits_per_component": _int_or_none(parts[6]),
                "encoding": parts[8],
            }
        )
    return images


def _table_candidates(
    doc_id: str,
    page_number: int,
    text: str,
    existing_count: int,
    *,
    bbox_html_path: Path | None = None,
) -> list[dict[str, Any]]:
    lines = text.splitlines()
    candidates: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        header_window = "\n".join(lines[index : min(len(lines), index + 5)])
        looks_like_table_caption = stripped.startswith("Table ")
        looks_like_nakshatra_header = (
            "Nakṣatra" in header_window
            and "Star Count" in header_window
            and "Yogatārā" in header_window
        )
        if not looks_like_table_caption and not looks_like_nakshatra_header:
            continue

        # When the Nakṣatra header heuristic matches but the current line
        # is not itself the "Table ..." caption, scan forward within the
        # window to find the real caption line.
        caption_index = index
        if looks_like_table_caption:
            caption = stripped
        else:
            caption = _shorten(stripped, 200)
            for j in range(index, min(len(lines), index + 5)):
                if lines[j].strip().startswith("Table "):
                    caption = lines[j].strip()
                    caption_index = j
                    break
        extent_start, extent_end = _estimate_table_extent(lines, caption_index)
        extent_lines = lines[extent_start : extent_end + 1]
        data_row_count = sum(
            1 for el in extent_lines if re.match(r"^\s{0,4}\d{1,3}\s", el)
        )
        evidence_cap = 80
        evidence_lines = extent_lines[:evidence_cap]
        bbox = _table_bbox_from_bbox_html(
            bbox_html_path, page_number, caption
        )

        candidates.append(
            {
                "table_id": f"{doc_id}:p{page_number:04d}:t{existing_count + len(candidates) + 1:04d}",
                "doc_id": doc_id,
                "page_number": page_number,
                "caption": caption,
                "caption_line_index": caption_index,
                "extent_line_start": extent_start,
                "extent_line_end": extent_end,
                "data_row_count": data_row_count,
                "bbox": bbox,
                "extraction_source": "pdftotext-layout heuristic",
                "confidence": "low",
                "status": "candidate",
                "evidence": "\n".join(evidence_lines).strip(),
            }
        )
        break
    return candidates


def _estimate_table_extent(lines: list[str], caption_index: int) -> tuple[int, int]:
    """Return (start, end) line indices for the table body including caption.

    Scans forward from caption_index.  A line is considered part of the table
    if it contains wide interior whitespace (>= 3 consecutive spaces between
    tokens) or starts with a digit row-number pattern.  The extent ends after
    2+ consecutive lines that look like flowing prose.
    """
    wide_gap = re.compile(r"\S\s{3,}\S")
    row_prefix = re.compile(r"^\s{0,6}\d{1,3}\s")
    # Also treat lines that are continuations of multi-line cells as table
    # (indented text without wide gaps, but preceded by a table line).

    end = caption_index
    consecutive_prose = 0
    max_prose_run = 2  # stop after this many consecutive prose lines

    for i in range(caption_index + 1, len(lines)):
        stripped = lines[i].strip()
        if not stripped:
            # blank lines inside tables are common (between rows)
            consecutive_prose = 0
            end = i
            continue
        is_table_line = bool(wide_gap.search(lines[i])) or bool(
            row_prefix.match(lines[i])
        )
        if is_table_line:
            consecutive_prose = 0
            end = i
        else:
            consecutive_prose += 1
            if consecutive_prose >= max_prose_run:
                break
            # single prose-like line might be a continuation row; include it
            end = i
    return caption_index, end


def _table_bbox_from_bbox_html(
    bbox_html_path: Path | None,
    page_number: int,
    caption: str,
) -> list[float] | None:
    """Parse the bbox HTML and return approximate [xMin, yMin, xMax, yMax] for a table.

    Returns None if the bbox HTML is unavailable or the caption cannot be located.
    """
    if bbox_html_path is None or not bbox_html_path.exists():
        return None
    try:
        raw = bbox_html_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    # The bbox HTML is XHTML with <page> elements in document order.
    # Extract the target page's XML fragment to avoid parsing the full doc.
    page_fragments = _split_bbox_pages(raw)
    if page_number < 1 or page_number > len(page_fragments):
        return None
    page_xml = page_fragments[page_number - 1]

    # Strip control characters that are invalid in XML 1.0 (U+0001..U+0008,
    # U+000B, U+000C, U+000E..U+001F) before parsing.  The bbox HTML can
    # contain garbled text from PDFs with broken font mappings.
    page_xml = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", page_xml)

    # Find all <word> elements on this page.
    try:
        wrapped = f"<root>{page_xml}</root>"
        root = ET.fromstring(wrapped)
    except ET.ParseError:
        return None

    words = root.iter("word")
    word_list = []
    for w in words:
        try:
            word_list.append((
                float(w.get("xMin", "0")),
                float(w.get("yMin", "0")),
                float(w.get("xMax", "0")),
                float(w.get("yMax", "0")),
                (w.text or "").strip(),
            ))
        except (ValueError, TypeError):
            continue

    if not word_list:
        return None

    # Find the caption anchor: first word of "Table" in the caption.
    caption_first = caption.split()[0] if caption.split() else "Table"
    anchor_y: float | None = None
    for xmin, ymin, xmax, ymax, text in word_list:
        if text == caption_first:
            anchor_y = ymin
            break

    if anchor_y is None:
        return None

    # Collect all words from the anchor downward on this page.
    # The table typically occupies the majority of the remaining page, but
    # we stop when we encounter the prose zone (a dense block of small-gap words
    # well below the table).  As a simple heuristic, collect all words whose
    # yMin is >= anchor_y and whose yMin is within a generous vertical band.
    # We use the page height from the <page> tag if available.
    table_words = [
        (xmin, ymin, xmax, ymax)
        for xmin, ymin, xmax, ymax, _ in word_list
        if ymin >= anchor_y
    ]
    if not table_words:
        return None

    # Heuristic: find a vertical gap > 20pt between consecutive word rows
    # that would indicate the end of the table and start of prose.
    y_positions = sorted({ymin for _, ymin, _, _ in table_words})
    cutoff_y: float | None = None
    for i in range(len(y_positions) - 1):
        gap = y_positions[i + 1] - y_positions[i]
        if gap > 20.0 and y_positions[i] > anchor_y + 50:
            cutoff_y = y_positions[i]
            break

    if cutoff_y is not None:
        table_words = [
            (xmin, ymin, xmax, ymax)
            for xmin, ymin, xmax, ymax in table_words
            if ymin <= cutoff_y + 15  # small tolerance for last row descenders
        ]

    if not table_words:
        return None

    bbox_xmin = min(xmin for xmin, _, _, _ in table_words)
    bbox_ymin = min(ymin for _, ymin, _, _ in table_words)
    bbox_xmax = max(xmax for _, _, xmax, _ in table_words)
    bbox_ymax = max(ymax for _, _, _, ymax in table_words)
    return [round(bbox_xmin, 1), round(bbox_ymin, 1), round(bbox_xmax, 1), round(bbox_ymax, 1)]


def _split_bbox_pages(html: str) -> list[str]:
    """Split bbox HTML into per-page XML fragments (content between <page> tags)."""
    fragments: list[str] = []
    tag_open = re.compile(r"<page\b[^>]*>")
    tag_close = "</page>"
    pos = 0
    while True:
        m = tag_open.search(html, pos)
        if m is None:
            break
        start = m.start()
        end = html.find(tag_close, m.end())
        if end < 0:
            break
        fragments.append(html[start : end + len(tag_close)])
        pos = end + len(tag_close)
    return fragments


def _text_risks(
    doc_id: str, page_number: int, text: str, extractor: str
) -> list[dict[str, Any]]:
    risks: list[dict[str, Any]] = []
    control_count = sum(1 for char in text if _is_suspicious_control(char))
    private_use_count = sum(1 for char in text if _is_private_use(char))
    replacement_count = text.count("\ufffd")
    for risk_type, count, severity, action in [
        ("control_characters", control_count, "warning", "Inspect text mapping or fallback extraction."),
        ("private_use_glyphs", private_use_count, "warning", "Inspect font mapping and visual page crop."),
        ("replacement_characters", replacement_count, "error", "Treat affected text as unsafe for indexing."),
    ]:
        if count:
            risks.append(
                {
                    "risk_id": _risk_id(doc_id, page_number, risk_type, len(risks)),
                    "doc_id": doc_id,
                    "page_number": page_number,
                    "risk_type": risk_type,
                    "severity": severity,
                    "extractor": extractor,
                    "bbox": None,
                    "font_name": None,
                    "evidence": f"{count} {risk_type} detected on page {page_number}.",
                    "recommended_action": action,
                }
            )
    return risks


def _span_text_risks(span_row: dict[str, Any]) -> list[dict[str, Any]]:
    text = span_row.get("text") or ""
    risk_specs = [
        ("control_characters", sum(1 for char in text if _is_suspicious_control(char))),
        ("private_use_glyphs", sum(1 for char in text if _is_private_use(char))),
        ("replacement_characters", text.count("\ufffd")),
    ]
    risks: list[dict[str, Any]] = []
    for risk_type, count in risk_specs:
        if not count:
            continue
        risks.append(
            {
                "doc_id": span_row["doc_id"],
                "page_number": span_row["page_number"],
                "risk_type": risk_type,
                "severity": "error" if risk_type == "replacement_characters" else "warning",
                "extractor": "pymupdf",
                "bbox": span_row.get("bbox"),
                "font_name": span_row.get("font_name"),
                "evidence": f"{count} {risk_type} in span text: {_shorten(text)}",
                "recommended_action": "Use visual crop or targeted fallback before accepting this span.",
            }
        )
    return risks


def _build_retrieval_samples(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queries = ["nakṣatra", "naksatra", "binomial", "Babylonian"]
    samples: list[dict[str, Any]] = []
    for query in queries:
        needle = query.casefold()
        hits = []
        for chunk in chunks:
            if needle in chunk["text"].casefold():
                hits.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "doc_id": chunk["doc_id"],
                        "page_start": chunk["page_start"],
                        "page_end": chunk["page_end"],
                        "snippet": _snippet(chunk["text"], query),
                        "risk_flags": chunk["risk_flags"],
                    }
                )
            if len(hits) == 3:
                break
        samples.append({"query": query, "method": "casefold_substring", "hits": hits})
    return samples


def _write_audit_md(
    path: Path,
    *,
    selected_doc_ids: list[str],
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    images: list[dict[str, Any]],
    retrieval_samples: list[dict[str, Any]],
    extractor: str = "local",
    model_config_log: dict[str, Any] | None = None,
    fallbacks: list[dict[str, Any]] | None = None,
) -> None:
    risk_counts: dict[str, int] = {}
    for risk in risks:
        risk_counts[risk["risk_type"]] = risk_counts.get(risk["risk_type"], 0) + 1
    lines = [
        "# Darpan Decode Lab Audit",
        "",
        f"- schema version: `{SCHEMA_VERSION}`",
        f"- extractor: `{extractor}`",
        f"- selected documents: {', '.join(f'`{doc_id}`' for doc_id in selected_doc_ids)}",
        f"- documents: {len(documents)}",
        f"- pages: {len(pages)}",
        f"- chunks: {len(chunks)}",
        f"- risks: {len(risks)}",
        f"- images: {len(images)}",
        f"- fallbacks: {len(fallbacks or [])}",
        "",
    ]
    if model_config_log:
        lines.extend([
            "## Model Configuration",
            "",
            f"- config: `{model_config_log.get('config_name', '')}`",
            f"- API model: `{model_config_log.get('api_model', '')}`",
            f"- thinking level: `{model_config_log.get('thinking_level', 'none')}`",
            f"- chunk size: {model_config_log.get('chunk_size', '')} pages",
            f"- prompt template SHA-256: `{model_config_log.get('prompt_template_sha256', '')[:16]}...`",
            "",
        ])
    lines.extend([
        "## Documents",
        "",
    ])
    for document in documents:
        lines.append(
            f"- `{document['doc_id']}`: {document['status']} "
            f"({document.get('page_count') or 'unknown'} pages, {document.get('status_reason') or 'no issue'})"
        )
    lines.extend(["", "## Risk Summary", ""])
    if risk_counts:
        for risk_type, count in sorted(risk_counts.items()):
            lines.append(f"- `{risk_type}`: {count}")
    else:
        lines.append("- No risks detected.")
    lines.extend(["", "## Retrieval Samples", ""])
    for sample in retrieval_samples:
        lines.append(f"### {sample['query']}")
        if not sample["hits"]:
            lines.append("- no hits")
        for hit in sample["hits"]:
            lines.append(
                f"- `{hit['chunk_id']}` page {hit['page_start']}: {hit['snippet']}"
            )
        lines.append("")
    _write_text(path, "\n".join(lines).rstrip() + "\n")


def _write_review_md(path: Path, record: IndexRecord, doc_result: dict[str, Any]) -> None:
    document = doc_result["document"]
    risk_counts: dict[str, int] = {}
    for risk in doc_result["risks"]:
        risk_counts[risk["risk_type"]] = risk_counts.get(risk["risk_type"], 0) + 1
    lines = [
        f"# Decode Review: {record.doc_id}",
        "",
        f"- title: {record.title}",
        f"- author: {record.author_display}",
        f"- year: {record.year}",
        f"- source URL: {record.source_url}",
        f"- local PDF: `{record.local_pdf_path}`",
        "- source PDF symlink: `source.pdf`",
        f"- SHA-256: `{document.get('sha256') or ''}`",
        f"- status: `{document['status']}`",
        f"- page count: {document.get('page_count') or 'unknown'}",
        f"- chunks: {len(doc_result['chunks'])}",
        f"- risks: {len(doc_result['risks'])}",
        f"- images: {len(doc_result['images'])}",
        f"- tables: {len(doc_result['tables'])}",
        "",
        "## Page Coverage",
        "",
    ]
    for page in doc_result["pages"]:
        lines.append(
            f"- page {page['page_number']}: {page['text_char_count']} chars, "
            f"{page['risk_count']} risks, {page['image_count']} images"
        )
    lines.extend(["", "## Risks", ""])
    if risk_counts:
        for risk_type, count in sorted(risk_counts.items()):
            lines.append(f"- `{risk_type}`: {count}")
    else:
        lines.append("- No risks detected.")
    lines.extend(["", "## High-Signal Risk Evidence", ""])
    for risk in doc_result["risks"][:20]:
        lines.append(
            f"- page {risk.get('page_number') or 'n/a'} `{risk['risk_type']}` "
            f"({risk['severity']}): {risk['evidence']}"
        )
    if not doc_result["risks"]:
        lines.append("- None.")
    lines.extend(["", "## Table Candidates", ""])
    for table in doc_result["tables"]:
        caption = table.get("caption") or _first_informative_line(table["evidence"])
        extent_info = ""
        if table.get("extent_line_start") is not None:
            extent_info = (
                f", lines {table['extent_line_start']}-{table['extent_line_end']}"
                f", {table.get('data_row_count', '?')} data rows"
            )
        bbox_info = ""
        if table.get("bbox"):
            b = table["bbox"]
            bbox_info = f", bbox [{b[0]}, {b[1]}, {b[2]}, {b[3]}]"
        lines.append(
            f"- page {table['page_number']} `{table['table_id']}` "
            f"({table['confidence']} confidence{extent_info}{bbox_info}): {caption}"
        )
    if not doc_result["tables"]:
        lines.append("- None.")
    lines.extend(["", "## Sample Chunks", ""])
    for chunk in doc_result["chunks"][:3]:
        lines.append(f"### {chunk['chunk_id']}")
        lines.append("")
        lines.append(_shorten(chunk["text"], 800))
        lines.append("")
    _write_text(path, "\n".join(lines).rstrip() + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _empty_run_tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "documents": [],
        "pages": [],
        "chunks": [],
        "risks": [],
        "images": [],
        "tables": [],
        "fallbacks": [],
    }


def _load_run_tables(run_dir: Path) -> dict[str, list[dict[str, Any]]]:
    return {
        "documents": _read_jsonl(run_dir / "documents.jsonl"),
        "pages": _read_jsonl(run_dir / "pages.jsonl"),
        "chunks": _read_jsonl(run_dir / "chunks.jsonl"),
        "risks": _read_jsonl(run_dir / "risks.jsonl"),
        "images": _read_jsonl(run_dir / "images.jsonl"),
        "tables": _read_jsonl(run_dir / "tables.jsonl"),
        "fallbacks": _read_jsonl(run_dir / "fallbacks.jsonl"),
    }


def _drop_doc_rows(
    *,
    doc_id: str,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    images: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fallbacks: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    return (
        [row for row in documents if row.get("doc_id") != doc_id],
        [row for row in pages if row.get("doc_id") != doc_id],
        [row for row in chunks if row.get("doc_id") != doc_id],
        [row for row in risks if row.get("doc_id") != doc_id],
        [row for row in images if row.get("doc_id") != doc_id],
        [row for row in tables if row.get("doc_id") != doc_id],
        [row for row in fallbacks if row.get("doc_id") != doc_id],
    )


def _doc_is_complete(
    doc_dir: Path,
    *,
    require_document_md: bool,
    extractor: str,
) -> bool:
    manifest = _read_json(doc_dir / "manifest.json")
    if not isinstance(manifest, dict) or manifest.get("status") != "ok":
        return False

    if require_document_md:
        document_md = doc_dir / "document.md"
        if not document_md.exists() or document_md.stat().st_size == 0:
            return False

    if extractor.startswith("gemini:"):
        state = _read_json(doc_dir / "extraction-state.json")
        if not isinstance(state, dict):
            return False
        chunks = state.get("gemini_chunks")
        if not isinstance(chunks, list) or not chunks:
            return False
        page_count = state.get("page_count") or 0
        chunk_size = state.get("chunk_size") or 0
        if page_count and chunk_size:
            expected = (page_count + chunk_size - 1) // chunk_size
            if len(chunks) < expected:
                return False
        return all(chunk.get("status") == "success" for chunk in chunks)

    return True


def _write_run_tables(
    *,
    run_dir: Path,
    documents: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    risks: list[dict[str, Any]],
    images: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    fallbacks: list[dict[str, Any]],
    retrieval_samples: list[dict[str, Any]],
) -> None:
    _write_jsonl(run_dir / "documents.jsonl", documents)
    _write_jsonl(run_dir / "pages.jsonl", pages)
    _write_jsonl(run_dir / "chunks.jsonl", chunks)
    _write_jsonl(run_dir / "risks.jsonl", risks)
    _write_jsonl(run_dir / "images.jsonl", images)
    _write_jsonl(run_dir / "tables.jsonl", tables)
    _write_jsonl(run_dir / "fallbacks.jsonl", fallbacks)
    _write_jsonl(run_dir / "retrieval-samples.jsonl", retrieval_samples)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _risk_id(doc_id: str, page_number: int | None, risk_type: str, index: int) -> str:
    page = "doc" if page_number is None else f"p{page_number:04d}"
    return f"{doc_id}:{page}:{risk_type}:{index + 1:04d}"


def _is_suspicious_control(char: str) -> bool:
    return ord(char) < 32 and char not in {"\n", "\r", "\t", "\f"}


def _is_private_use(char: str) -> bool:
    return 0xE000 <= ord(char) <= 0xF8FF


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _shorten(text: str, limit: int = 160) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _snippet(text: str, query: str, radius: int = 80) -> str:
    folded = text.casefold()
    index = folded.find(query.casefold())
    if index < 0:
        return _shorten(text, radius * 2)
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return prefix + " ".join(text[start:end].split()) + suffix


def _first_informative_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("Indian Journal of History of Science"):
            continue
        return stripped
    return ""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _progress(message: str) -> None:
    print(f"[{_utc_now()}] {message}", flush=True)
