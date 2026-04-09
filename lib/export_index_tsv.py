from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from lib.config import EXPORTS_DIR, SQLITE_PATH


INDEX_COLUMNS = [
    "journal",
    "paper",
    "subject",
    "category",
    "author",
    "url",
    "size_in_kb",
    "year",
    "ju_url",
    "cahc_authored",
    "entry_type",
    "source",
    "gcs_key",
    "gcs_synced",
]


def _source_label(source_type: str, remote_url: str) -> str:
    if source_type == "portal_ijhs_metadata":
        return "portal_ijhs"
    if source_type == "curated_pdf_metadata":
        return "curated_pdf"
    if source_type == "curated_link_metadata":
        host = urlparse(remote_url).netloc.lower()
        if "swarajyamag.com" in host:
            return "swarajya"
        return "curated_link"
    return source_type


def export_index_tsv(output_path: Path | None = None) -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        output_path = EXPORTS_DIR / "index.tsv"

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT
                d.doc_id,
                d.entry_type,
                d.title,
                d.author_display,
                d.year,
                d.journal_label,
                d.cahc_authored,
                d.source_root,
                ds.source_type,
                ds.raw_metadata_json,
                ar.local_rel_path,
                ar.remote_url,
                ar.gcs_key,
                ar_mirror.remote_url AS mirror_url
            FROM documents d
            JOIN document_sources ds ON ds.doc_id = d.doc_id
            JOIN asset_refs ar ON ar.doc_id = d.doc_id
            LEFT JOIN asset_refs ar_mirror
              ON ar_mirror.doc_id = d.doc_id
             AND ar_mirror.asset_role = 'mirror_pdf'
            WHERE ar.asset_id = d.doc_id || ':primary'
            ORDER BY ds.source_path, ds.source_row_id
            """
        ).fetchall()
    finally:
        conn.close()

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS, delimiter="\t")
        writer.writeheader()

        for row in rows:
            raw = json.loads(row["raw_metadata_json"])
            remote_url = row["remote_url"] or ""
            size_in_kb = raw.get("size_in_kb", "")
            if row["entry_type"] == "link" and not str(size_in_kb).strip():
                size_in_kb = "0"
            writer.writerow(
                {
                    "journal": row["journal_label"] or "",
                    "paper": row["title"] or "",
                    "subject": "",
                    "category": "",
                    "author": row["author_display"] or "",
                    "url": remote_url,
                    "size_in_kb": size_in_kb,
                    "year": row["year"] or "",
                    "ju_url": row["mirror_url"] or "",
                    "cahc_authored": "true" if row["cahc_authored"] else "false",
                    "entry_type": row["entry_type"] or "",
                    "source": _source_label(row["source_type"], remote_url),
                    "gcs_key": row["gcs_key"] or "",
                    "gcs_synced": "false",
                }
            )

    return output_path
