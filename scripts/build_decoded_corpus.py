from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import BUILD_DIR, PROJECT_ROOT
from lib.decode_lab.campaign_sets import read_campaign_set


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build decoded-corpus/ from accepted Decode Lab outputs.",
        epilog=(
            "Incremental sequence:\n"
            "  1. Run without replacement flags to build only missing docs; existing docs are skipped.\n"
            "  2. Use --replace-doc DOC_ID to rebuild one existing doc.\n"
            "  3. Use --replace-set SET_NAME to rebuild existing docs in a campaign set.\n"
            "  4. Use --force only when every selected doc should be rebuilt.\n\n"
            "Examples:\n"
            "  Build only missing docs from a run:\n"
            "    uv run python scripts/build_decoded_corpus.py --from-run build-astro-math-indic-raster\n\n"
            "  Replace one decoded doc from a targeted repair run:\n"
            "    uv run python scripts/build_decoded_corpus.py --from-run repair-DOC_ID \\\n"
            "      --replace-doc DOC_ID\n\n"
            "  Replace docs in an audited campaign set after reassembly:\n"
            "    uv run python scripts/build_decoded_corpus.py --from-run build-astro-math-indic-raster \\\n"
            "      --replace-set audit-set\n\n"
            "  Rebuild a full generated run intentionally:\n"
            "    uv run python scripts/build_decoded_corpus.py --from-run build-astro-math-indic-raster \\\n"
            "      --force"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--from-run", required=True, help="Decode Lab run ID to build from.")
    parser.add_argument(
        "--run-root",
        type=Path,
        default=BUILD_DIR / "decode-lab",
        help="Decode Lab run root. Default: .build~/decode-lab.",
    )
    parser.add_argument(
        "--decoded-root",
        type=Path,
        default=PROJECT_ROOT / "decoded-corpus",
        help="Decoded corpus output root. Default: decoded-corpus/.",
    )
    parser.add_argument(
        "--doc-id",
        action="append",
        help="Only build this doc_id from the run (repeatable). Default: all docs in run.",
    )
    parser.add_argument(
        "--replace-doc",
        action="append",
        default=[],
        help="Allow replacing this existing decoded doc_id (repeatable).",
    )
    parser.add_argument(
        "--replace-set",
        action="append",
        default=[],
        help="Allow replacing docs listed in this campaign set (repeatable).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing every selected existing decoded doc.",
    )
    args = parser.parse_args()

    run_dir = args.run_root / args.from_run
    if not run_dir.exists():
        parser.error(f"Run directory does not exist: {run_dir}")

    replace_doc_ids = set(args.replace_doc)
    for set_name in args.replace_set:
        replace_doc_ids.update(read_campaign_set(set_name))

    doc_ids = args.doc_id or _run_doc_ids(run_dir)
    if not doc_ids:
        parser.error(f"No document directories found in {run_dir / 'by-doc'}")

    decoded_root = args.decoded_root
    by_doc_root = decoded_root / "by-doc"
    built_rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    failures: list[str] = []

    for doc_id in doc_ids:
        try:
            row = _build_doc(
                run_dir=run_dir,
                run_id=args.from_run,
                decoded_root=decoded_root,
                by_doc_root=by_doc_root,
                doc_id=doc_id,
                allow_replace=args.force or doc_id in replace_doc_ids,
            )
            if row["action"] == "skipped":
                skipped.append(doc_id)
                print(f"Skipped existing {doc_id}")
            else:
                built_rows.append(row)
                print(f"Built {doc_id}")
        except Exception as exc:  # keep building other docs
            failures.append(f"{doc_id}: {exc}")
            print(f"Failed {doc_id}: {exc}", file=sys.stderr)

    _write_top_level_outputs(decoded_root, built_rows)

    print(f"Wrote {decoded_root}")
    print(f"Built: {len(built_rows)}")
    print(f"Skipped existing: {len(skipped)}")
    print(f"Failed: {len(failures)}")
    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        raise SystemExit(1)


def _run_doc_ids(run_dir: Path) -> list[str]:
    rows = _read_jsonl(run_dir / "documents.jsonl")
    doc_ids = [str(row["doc_id"]) for row in rows if row.get("doc_id")]
    if doc_ids:
        return doc_ids
    by_doc = run_dir / "by-doc"
    if not by_doc.exists():
        return []
    return sorted(
        path.name for path in by_doc.iterdir() if path.is_dir() and (path / "document.md").exists()
    )


def _build_doc(
    *,
    run_dir: Path,
    run_id: str,
    decoded_root: Path,
    by_doc_root: Path,
    doc_id: str,
    allow_replace: bool,
) -> dict[str, Any]:
    src_doc_dir = run_dir / "by-doc" / doc_id
    src_md = src_doc_dir / "document.md"
    if not src_md.exists():
        raise FileNotFoundError(f"document.md missing: {src_md}")

    dest_doc_dir = by_doc_root / doc_id
    if dest_doc_dir.exists():
        if not allow_replace:
            existing_row = _existing_manifest_row(dest_doc_dir, decoded_root)
            existing_row["action"] = "skipped"
            return existing_row
        shutil.rmtree(dest_doc_dir)

    media_dir = dest_doc_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    md_text = src_md.read_text(encoding="utf-8")
    md_text = md_text.replace("](images/", "](media/")
    md_text = md_text.replace("image=images/", "image=media/")
    dest_md = dest_doc_dir / "document.md"
    dest_md.write_text(md_text, encoding="utf-8")

    media_files = _copy_media(src_doc_dir / "images", media_dir)
    source = _read_json(src_doc_dir / "source.json") or {}
    source_pdf = _link_source_pdf(source, dest_doc_dir)
    run_manifest = _read_json(run_dir / "run-manifest.json") or {}
    extraction_state = _read_json(src_doc_dir / "extraction-state.json") or {}
    quality = _quality_payload(md_text, extraction_state)
    manifest = {
        "doc_id": doc_id,
        "status": "ok" if not quality["errors"] else "warning",
        "generated_at": _utc_now(),
        "decoded_corpus_version": "decoded-corpus.v0.1",
        "source": source,
        "source_pdf": _rel_or_abs(source_pdf, decoded_root) if source_pdf else None,
        "source_pdf_sha256": _sha256_file(source_pdf) if source_pdf and source_pdf.exists() else None,
        "run_id": run_id,
        "run_dir": _rel_or_abs(run_dir, decoded_root),
        "extractor": run_manifest.get("extractor"),
        "model_config": run_manifest.get("model_config"),
        "service_tier_requested": run_manifest.get("service_tier_requested"),
        "document_md": _rel_or_abs(dest_md, decoded_root),
        "document_md_sha256": _sha256_text(md_text),
        "media_dir": _rel_or_abs(media_dir, decoded_root),
        "media_files": media_files,
        "quality": _rel_or_abs(dest_doc_dir / "quality.json", decoded_root),
    }

    _write_json(dest_doc_dir / "manifest.json", manifest)
    _write_json(dest_doc_dir / "quality.json", quality)
    return {
        "action": "built",
        "doc_id": doc_id,
        "status": manifest["status"],
        "document_md": manifest["document_md"],
        "media_dir": manifest["media_dir"],
        "source_pdf": manifest["source_pdf"],
        "run_id": run_id,
        "warning_count": len(quality["warnings"]),
        "error_count": len(quality["errors"]),
    }


def _existing_manifest_row(dest_doc_dir: Path, decoded_root: Path) -> dict[str, Any]:
    manifest = _read_json(dest_doc_dir / "manifest.json")
    quality = _read_json(dest_doc_dir / "quality.json") or {}
    if not isinstance(manifest, dict):
        manifest = {}
    warnings = quality.get("warnings") if isinstance(quality, dict) else []
    errors = quality.get("errors") if isinstance(quality, dict) else []
    return {
        "doc_id": dest_doc_dir.name,
        "status": manifest.get("status", "unknown"),
        "document_md": manifest.get(
            "document_md",
            _rel_or_abs(dest_doc_dir / "document.md", decoded_root),
        ),
        "media_dir": manifest.get(
            "media_dir",
            _rel_or_abs(dest_doc_dir / "media", decoded_root),
        ),
        "source_pdf": manifest.get("source_pdf"),
        "run_id": manifest.get("run_id"),
        "warning_count": len(warnings) if isinstance(warnings, list) else 0,
        "error_count": len(errors) if isinstance(errors, list) else 0,
    }


def _copy_media(src_images_dir: Path, dest_media_dir: Path) -> list[str]:
    if not src_images_dir.exists():
        return []
    copied: list[str] = []
    for src in sorted(src_images_dir.iterdir()):
        if src.name.startswith(".") or not src.is_file():
            continue
        dest = dest_media_dir / src.name
        shutil.copy2(src, dest)
        copied.append(src.name)
    return copied


def _link_source_pdf(source: dict[str, Any], dest_doc_dir: Path) -> Path | None:
    raw_path = source.get("local_pdf_path")
    if not raw_path:
        return None
    source_pdf = Path(raw_path)
    link_path = dest_doc_dir / "source.pdf"
    if link_path.exists() or link_path.is_symlink():
        link_path.unlink()
    try:
        rel_target = os.path.relpath(source_pdf, start=dest_doc_dir)
        link_path.symlink_to(rel_target)
    except OSError:
        link_path.symlink_to(source_pdf)
    return source_pdf


def _quality_payload(md_text: str, extraction_state: dict[str, Any]) -> dict[str, Any]:
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    continue_count = md_text.count("<<<CONTINUE>>>")
    if continue_count:
        warnings.append({"type": "continue_marker", "count": continue_count})

    page_render_count = md_text.count("figure-resolved-page-render:")
    if page_render_count:
        warnings.append({"type": "figure_resolved_page_render", "count": page_render_count})

    hidden_page_render_count = md_text.count("figure-resolved-page-render-hidden:")
    if hidden_page_render_count:
        warnings.append(
            {"type": "figure_resolved_page_render_hidden", "count": hidden_page_render_count}
        )

    unresolved_marker_count = md_text.count("figure-unresolved:")
    if unresolved_marker_count:
        warnings.append({"type": "figure_unresolved", "count": unresolved_marker_count})

    legacy_figure_warning_count = md_text.count("figure-placeholder-warning")
    if legacy_figure_warning_count:
        warnings.append(
            {"type": "legacy_figure_placeholder_warning", "count": legacy_figure_warning_count}
        )

    unresolved = sorted(set(re.findall(r"\]\(([^)\n]*placeholder[^)\n]*)\)", md_text)))
    if unresolved:
        warnings.append({"type": "unresolved_placeholders", "values": unresolved})

    chunks = extraction_state.get("gemini_chunks") if isinstance(extraction_state, dict) else None
    if isinstance(chunks, list):
        failed = [chunk for chunk in chunks if chunk.get("status") != "success"]
        if failed:
            errors.append({"type": "failed_chunks", "count": len(failed), "chunks": failed})

    return {
        "status": "ok" if not errors else "warning",
        "warnings": warnings,
        "errors": errors,
        "checked_at": _utc_now(),
    }


def _write_top_level_outputs(decoded_root: Path, built_rows: list[dict[str, Any]]) -> None:
    decoded_root.mkdir(parents=True, exist_ok=True)
    existing_rows = {
        row["doc_id"]: row
        for row in _read_jsonl(decoded_root / "manifest.jsonl")
        if row.get("doc_id")
    }
    for row in built_rows:
        existing_rows[row["doc_id"]] = row

    rows = [existing_rows[doc_id] for doc_id in sorted(existing_rows)]
    with (decoded_root / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    ok_count = sum(1 for row in rows if row.get("status") == "ok")
    warning_count = len(rows) - ok_count
    audit = [
        "# Decoded Corpus Audit",
        "",
        f"- generated_at: {_utc_now()}",
        f"- documents: {len(rows)}",
        f"- ok: {ok_count}",
        f"- warning: {warning_count}",
        "",
    ]
    for row in rows:
        audit.append(
            f"- `{row['doc_id']}`: {row.get('status')} "
            f"warnings={row.get('warning_count', 0)} errors={row.get('error_count', 0)}"
        )
    (decoded_root / "audit.md").write_text("\n".join(audit) + "\n", encoding="utf-8")

    readme = decoded_root / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Decoded Corpus\n\n"
            "Durable generated Markdown and media artifacts built from Decode Lab runs.\n"
            "This directory is generated and is not the source PDF corpus.\n",
            encoding="utf-8",
        )


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


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rel_or_abs(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    main()
