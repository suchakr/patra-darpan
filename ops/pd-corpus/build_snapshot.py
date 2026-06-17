from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import resolve_shared_asset_root
from ops.export_patra_darpan_data_js import content_kind_for_paper


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "pd-corpus~"
ROOT_INPUTS = [
    PROJECT_ROOT / "corpus" / "ijhs.tsv",
    PROJECT_ROOT / "corpus" / "curated-pdfs.tsv",
    PROJECT_ROOT / "corpus" / "curated-links.tsv",
    PROJECT_ROOT / "corpus" / "cahc-pdf-mirrors.tsv",
    PROJECT_ROOT / "corpus" / "cahc_authored_registry.txt",
]
REQUIRED_WEB_FILES = [
    PROJECT_ROOT / "web" / "index.html",
    PROJECT_ROOT / "web" / "assets" / "css" / "style.css",
    PROJECT_ROOT / "web" / "assets" / "js" / "app.js",
]
INDEX_TSV = PROJECT_ROOT / "exports" / "index.tsv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the latest browsable Patra Darpan corpus snapshot."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Generated snapshot root. Default: pd-corpus~",
    )
    parser.add_argument(
        "--shared-asset-root",
        type=Path,
        default=None,
        help="PDF asset root with ijhs/ and other/. Defaults to repo conventions.",
    )
    parser.add_argument(
        "--copy-pdfs",
        action="store_true",
        help="Copy PDFs instead of hardlinking. Off by default to avoid space use.",
    )
    parser.add_argument(
        "--sync-target-hint",
        default="sccgdrive:pd-corpus/",
        help="Recorded in manifest only. Default: sccgdrive:pd-corpus/",
    )
    return parser.parse_args()


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit(f"Required file missing: {path}")


def require_dir(path: Path) -> None:
    if not path.is_dir():
        raise SystemExit(f"Required directory missing: {path}")


def clean_num(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    if text.lower() == "nan":
        return ""
    if text.endswith(".0"):
        return text[:-2]
    return text


def bool_from_text(value: object) -> bool:
    return str(value or "").strip().lower() == "true"


def float_from_text(value: object) -> float:
    try:
        text = str(value or "").strip()
        if not text or text.lower() == "nan":
            return 0.0
        return float(text)
    except ValueError:
        return 0.0


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def filename_from_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return unquote(Path(parsed.path).name)


def find_source_pdf(asset_root: Path, row: dict[str, str]) -> tuple[Path | None, str]:
    gcs_key = clean_num(row.get("gcs_key", ""))
    if gcs_key:
        candidate = asset_root / gcs_key
        if candidate.is_file():
            return candidate, gcs_key

    filename = filename_from_url(row.get("url", ""))
    if not filename:
        return None, ""
    for collection in ("ijhs", "other"):
        candidate = asset_root / collection / filename
        if candidate.is_file():
            return candidate, f"{collection}/{filename}"
    return None, gcs_key or f"ijhs/{filename}"


def safe_link_or_copy(source: Path, dest: Path, copy_pdfs: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if source.stat().st_ino == dest.stat().st_ino and source.stat().st_dev == dest.stat().st_dev:
            return
        dest.unlink()
    if copy_pdfs:
        shutil.copy2(source, dest)
        return
    try:
        os.link(source, dest)
    except OSError as exc:
        raise SystemExit(
            f"Hardlink failed for {source} -> {dest}: {exc}\n"
            "Refusing to copy PDFs by default. Re-run with --copy-pdfs only if "
            "you accept the extra disk usage."
        ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def patch_index_html(source: Path, dest: Path) -> None:
    html = source.read_text(encoding="utf-8")
    html = html.replace("<title>Patra Darpan</title>", "<title>Patra Darpan Corpus</title>")
    html = html.replace(
        '<a class="search-lab-link" href="search-lab.html">Search Lab</a>',
        '<a class="search-lab-link" href="README.html">Notes</a>',
    )
    html = html.replace(
        '<script src="assets/js/app.js?v=content-kind-20260423"></script>',
        '<script src="assets/js/app.js"></script>',
    )
    dest.write_text(html, encoding="utf-8")


def patch_app_js(source: Path, dest: Path) -> None:
    js = source.read_text(encoding="utf-8")
    old = """        if (isLink) {
            primaryLink = remoteUrl;
        } else {
            // PDFs: mirror first, then archive where available, then original source.
            primaryLink = juUrl || archivedLink || remoteUrl;
        }"""
    new = """        if (isLink) {
            primaryLink = remoteUrl;
        } else if (isLocalMode) {
            // Offline corpus snapshots should open the downloaded local PDF by default.
            primaryLink = paper.localPath || juUrl || remoteUrl;
        } else {
            // PDFs: mirror first, then archive where available, then original source.
            primaryLink = juUrl || archivedLink || remoteUrl;
        }"""
    if old not in js:
        raise SystemExit("Could not patch web app primary-link behavior for offline snapshot.")
    dest.write_text(js.replace(old, new), encoding="utf-8")


def write_readme_html(path: Path, generated_at: str) -> None:
    path.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Patra Darpan Corpus Notes</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.55; max-width: 860px; margin: 40px auto; padding: 0 20px; color: #1f2933; }}
    code, pre {{ background: #f2f4f7; border-radius: 4px; padding: 2px 5px; }}
    a {{ color: #075985; }}
  </style>
</head>
<body>
  <h1>Patra Darpan Corpus</h1>
  <p>This folder is a browsable snapshot of the Patra Darpan corpus generated at {generated_at}.</p>
  <p>Open <a href="index.html">index.html</a> to browse and search the corpus. PDF links point to files under <code>pdfs/</code> in this folder.</p>
  <p>Machine-readable metadata is under <code>metadata/</code>. Checksums are in <code>metadata/checksums.sha256</code>.</p>
  <p>This is a distribution snapshot, not the editable source of truth. The maintained sources are the local Patra Darpan metadata and shared PDF asset roots.</p>
</body>
</html>
""",
        encoding="utf-8",
    )


def append_release_log(path: Path, entry: dict[str, object], existing: str = "") -> None:
    if not existing:
        existing = path.read_text(encoding="utf-8") if path.exists() else "# Release Log\n\n"
    lines = [
        f"## {entry['generated_at']}",
        "",
        f"- git commit: `{entry.get('git_commit') or 'unknown'}`",
        f"- rows: {entry['row_count']}",
        f"- PDF rows: {entry['pdf_row_count']}",
        f"- URL-only rows: {entry['link_row_count']}",
        f"- linked PDFs: {entry['linked_pdf_count']}",
        f"- missing PDFs: {entry['missing_pdf_count']}",
        f"- total PDF bytes: {entry['total_pdf_bytes']}",
        "",
    ]
    path.write_text(existing.rstrip() + "\n\n" + "\n".join(lines), encoding="utf-8")


def main() -> None:
    args = parse_args()
    output_root = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    asset_root = args.shared_asset_root or resolve_shared_asset_root(PROJECT_ROOT)
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

    require_file(INDEX_TSV)
    for path in ROOT_INPUTS:
        require_file(path)
    for path in REQUIRED_WEB_FILES:
        require_file(path)
    require_dir(asset_root / "ijhs")
    require_dir(asset_root / "other")

    existing_release_log = ""
    if output_root.exists():
        release_log_path = output_root / "RELEASE_LOG.md"
        if release_log_path.exists():
            existing_release_log = release_log_path.read_text(encoding="utf-8")
        shutil.rmtree(output_root)

    metadata_root = output_root / "metadata"
    root_inputs_dest = metadata_root / "root-inputs"
    js_dest = output_root / "assets" / "js"
    css_dest = output_root / "assets" / "css"
    pdf_dest_root = output_root / "pdfs"

    root_inputs_dest.mkdir(parents=True)
    js_dest.mkdir(parents=True)
    css_dest.mkdir(parents=True)
    pdf_dest_root.mkdir(parents=True)

    shutil.copy2(INDEX_TSV, metadata_root / "index.tsv")
    for path in ROOT_INPUTS:
        shutil.copy2(path, root_inputs_dest / path.name)
    shutil.copy2(PROJECT_ROOT / "web" / "assets" / "css" / "style.css", css_dest / "style.css")
    patch_index_html(PROJECT_ROOT / "web" / "index.html", output_root / "index.html")
    patch_app_js(PROJECT_ROOT / "web" / "assets" / "js" / "app.js", js_dest / "app.js")
    write_readme_html(output_root / "README.html", generated_at)

    papers: list[dict[str, object]] = []
    missing_pdfs: list[dict[str, str]] = []
    linked_pdf_count = 0
    total_pdf_bytes = 0
    pdf_count_by_collection = {"ijhs": 0, "other": 0}

    with INDEX_TSV.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            entry_type = clean_num(row.get("entry_type", "pdf")) or "pdf"
            paper = {
                "journal": clean_num(row.get("journal", "")),
                "title": clean_num(row.get("paper", "Untitled")),
                "author": clean_num(row.get("author", "Unknown")),
                "category": clean_num(row.get("category", "Uncategorized")),
                "subject": clean_num(row.get("subject", "General")),
                "year": clean_num(row.get("year", "")),
                "remoteUrl": row.get("url", ""),
                "juUrl": clean_num(row.get("ju_url", "")),
                "size": float_from_text(row.get("size_in_kb", 0)),
                "cahc_authored": bool_from_text(row.get("cahc_authored")),
                "entry_type": entry_type,
                "source": clean_num(row.get("source", "insa")),
                "gcs_key": clean_num(row.get("gcs_key", "")),
            }
            paper["content_kind"] = content_kind_for_paper(paper)
            if "jainuniversity" in str(paper["remoteUrl"]) and not paper["juUrl"]:
                paper["juUrl"] = paper["remoteUrl"]

            if entry_type == "pdf":
                source_pdf, relative_key = find_source_pdf(asset_root, row)
                if source_pdf is None:
                    paper["localPath"] = None
                    missing_pdfs.append(
                        {
                            "journal": str(paper["journal"]),
                            "title": str(paper["title"]),
                            "gcs_key": relative_key,
                            "url": str(paper["remoteUrl"]),
                        }
                    )
                else:
                    dest_pdf = pdf_dest_root / relative_key
                    safe_link_or_copy(source_pdf, dest_pdf, args.copy_pdfs)
                    size_bytes = source_pdf.stat().st_size
                    paper["localPath"] = f"pdfs/{relative_key}"
                    if float(paper["size"]) <= 0:
                        paper["size"] = size_bytes / 1024.0
                    linked_pdf_count += 1
                    total_pdf_bytes += size_bytes
                    collection = relative_key.split("/", 1)[0]
                    if collection in pdf_count_by_collection:
                        pdf_count_by_collection[collection] += 1
            else:
                paper["localPath"] = None

            papers.append(paper)

    (js_dest / "data.js").write_text(
        f"const PAPERS = {json.dumps(papers, indent=2, ensure_ascii=False)};\n",
        encoding="utf-8",
    )
    shutil.copy2(PROJECT_ROOT / "web" / "assets" / "js" / "p60.js", js_dest / "p60.js")
    (js_dest / "offline-browse.js").write_text(
        "window.PATRA_DARPAN_OFFLINE_SNAPSHOT = true;\n", encoding="utf-8"
    )

    with (metadata_root / "corpus.jsonl").open("w", encoding="utf-8") as handle:
        for paper in papers:
            handle.write(json.dumps(paper, ensure_ascii=False, sort_keys=True) + "\n")

    row_count = len(papers)
    pdf_row_count = sum(1 for paper in papers if paper.get("entry_type") == "pdf")
    link_row_count = row_count - pdf_row_count
    manifest = {
        "generated_at": generated_at,
        "git_commit": git_commit(),
        "project_root": str(PROJECT_ROOT),
        "source_pdf_root": str(asset_root),
        "output_root": str(output_root),
        "sync_target_hint": args.sync_target_hint,
        "row_count": row_count,
        "pdf_row_count": pdf_row_count,
        "link_row_count": link_row_count,
        "linked_pdf_count": linked_pdf_count,
        "missing_pdf_count": len(missing_pdfs),
        "pdf_count_by_collection": pdf_count_by_collection,
        "total_pdf_bytes": total_pdf_bytes,
        "copy_pdfs": bool(args.copy_pdfs),
        "missing_pdfs": missing_pdfs,
    }
    (metadata_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    append_release_log(output_root / "RELEASE_LOG.md", manifest, existing_release_log)

    checksum_paths = sorted(
        path for path in output_root.rglob("*") if path.is_file()
    )
    with (metadata_root / "checksums.sha256").open("w", encoding="utf-8") as handle:
        for path in checksum_paths:
            if path == metadata_root / "checksums.sha256":
                continue
            rel = path.relative_to(output_root).as_posix()
            handle.write(f"{sha256_file(path)}  {rel}\n")

    if missing_pdfs:
        raise SystemExit(
            f"Built {output_root}, but {len(missing_pdfs)} PDF rows are missing local files. "
            f"See {metadata_root / 'manifest.json'}."
        )

    print(f"Built snapshot: {output_root}")
    print(f"Rows: {row_count}")
    print(f"PDF rows: {pdf_row_count}")
    print(f"URL-only rows: {link_row_count}")
    print(f"Linked PDFs: {linked_pdf_count}")
    print(f"Total PDF bytes: {total_pdf_bytes}")
    print(f"Checksums: {metadata_root / 'checksums.sha256'}")


if __name__ == "__main__":
    main()
