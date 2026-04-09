from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from lib.cahc_registry import infer_cahc_authored
from lib.config import CURATED_LINKS_TSV_PATH, CURATED_PDFS_TSV_PATH, SHARED_OTHER_PDF_ROOT


def file_version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def _slugify(value: str) -> str:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered)
    compact = re.sub(r"-{2,}", "-", normalized).strip("-")
    return compact or "untitled"


def _remote_url_for_row(row: dict[str, str]) -> str:
    url = _clean_text(row.get("url"))
    return url


def _pdf_stem_from_row(row: dict[str, str], row_number: int) -> str:
    remote_url = _remote_url_for_row(row)
    name = Path(urlparse(remote_url).path).name if remote_url else ""
    if name:
        return Path(name).stem
    return f"curated-pdf-{row_number:04d}-{_slugify(_clean_text(row.get('paper')))}"


def _link_doc_id(row: dict[str, str], row_number: int) -> str:
    remote_url = _remote_url_for_row(row)
    path_name = Path(urlparse(remote_url).path).name if remote_url else ""
    source_prefix = _slugify(_clean_text(row.get("journal")) or "link")
    candidate = _slugify(Path(path_name).stem if path_name else _clean_text(row.get("paper")))
    return f"{source_prefix}-{candidate or row_number}"


def load_curated_pdfs_tsv(
    conn: sqlite3.Connection,
    cahc_authored_registry_entries: list[str],
    mirror_map: dict[str, str],
) -> int:
    source_version = file_version(CURATED_PDFS_TSV_PATH)
    ingested_at = datetime.now(UTC).isoformat()
    inserted = 0
    seen_doc_ids: dict[str, int] = {}

    with CURATED_PDFS_TSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            base_doc_id = _pdf_stem_from_row(row, row_number)
            seen_count = seen_doc_ids.get(base_doc_id, 0) + 1
            seen_doc_ids[base_doc_id] = seen_count
            doc_id = base_doc_id if seen_count == 1 else f"{base_doc_id}-{seen_count:02d}"

            remote_url = _remote_url_for_row(row)
            filename = Path(urlparse(remote_url).path).name if remote_url else ""
            local_rel_path = f"other/{filename}" if filename and (SHARED_OTHER_PDF_ROOT / filename).exists() else None
            title = _clean_text(row.get("paper"))
            author_display = _clean_text(row.get("author"))
            year = _clean_text(row.get("year"))
            journal_label = _clean_text(row.get("journal"))
            cahc_authored = infer_cahc_authored(
                cahc_authored_registry_entries,
                remote_url=remote_url,
                local_rel_path=local_rel_path,
            )
            mirror_url = mirror_map.get(remote_url, "")

            conn.execute(
                """
                INSERT INTO documents (
                    doc_id,
                    entry_type,
                    title,
                    author_display,
                    year,
                    journal_label,
                    cahc_authored,
                    source_root
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    "pdf",
                    title,
                    author_display,
                    year,
                    journal_label,
                    1 if cahc_authored else 0,
                    "curated-pdfs.tsv",
                ),
            )

            conn.execute(
                """
                INSERT INTO document_sources (
                    source_row_id,
                    doc_id,
                    source_type,
                    source_path,
                    source_version,
                    raw_metadata_json,
                    ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"curated-pdfs:{row_number:05d}",
                    doc_id,
                    "curated_pdf_metadata",
                    str(CURATED_PDFS_TSV_PATH),
                    source_version,
                    json.dumps(dict(row), ensure_ascii=False, sort_keys=False),
                    ingested_at,
                ),
            )

            conn.execute(
                """
                INSERT INTO asset_refs (
                    asset_id,
                    doc_id,
                    asset_role,
                    local_rel_path,
                    remote_url,
                    gcs_key,
                    availability_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{doc_id}:primary",
                    doc_id,
                    "primary_pdf",
                    local_rel_path,
                    remote_url,
                    local_rel_path,
                    "present" if local_rel_path else "remote_only",
                ),
            )

            if mirror_url:
                conn.execute(
                    """
                    INSERT INTO asset_refs (
                        asset_id,
                        doc_id,
                        asset_role,
                        local_rel_path,
                        remote_url,
                        gcs_key,
                        availability_status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"{doc_id}:mirror",
                        doc_id,
                        "mirror_pdf",
                        local_rel_path,
                        mirror_url,
                        local_rel_path,
                        "present" if local_rel_path else "remote_only",
                    ),
                )

            inserted += 1

    conn.execute(
        "INSERT INTO build_info (key, value) VALUES (?, ?)",
        ("curated_pdfs_source_version", source_version),
    )
    return inserted


def load_curated_links_tsv(
    conn: sqlite3.Connection,
    cahc_authored_registry_entries: list[str],
) -> int:
    source_version = file_version(CURATED_LINKS_TSV_PATH)
    ingested_at = datetime.now(UTC).isoformat()
    inserted = 0
    seen_doc_ids: dict[str, int] = {}

    with CURATED_LINKS_TSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            base_doc_id = _link_doc_id(row, row_number)
            seen_count = seen_doc_ids.get(base_doc_id, 0) + 1
            seen_doc_ids[base_doc_id] = seen_count
            doc_id = base_doc_id if seen_count == 1 else f"{base_doc_id}-{seen_count:02d}"

            remote_url = _remote_url_for_row(row)
            title = _clean_text(row.get("paper"))
            author_display = _clean_text(row.get("author"))
            year = _clean_text(row.get("year"))
            journal_label = _clean_text(row.get("journal"))
            cahc_authored = infer_cahc_authored(
                cahc_authored_registry_entries,
                remote_url=remote_url,
                local_rel_path=None,
            )

            conn.execute(
                """
                INSERT INTO documents (
                    doc_id,
                    entry_type,
                    title,
                    author_display,
                    year,
                    journal_label,
                    cahc_authored,
                    source_root
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    "link",
                    title,
                    author_display,
                    year,
                    journal_label,
                    1 if cahc_authored else 0,
                    "curated-links.tsv",
                ),
            )

            conn.execute(
                """
                INSERT INTO document_sources (
                    source_row_id,
                    doc_id,
                    source_type,
                    source_path,
                    source_version,
                    raw_metadata_json,
                    ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"curated-links:{row_number:05d}",
                    doc_id,
                    "curated_link_metadata",
                    str(CURATED_LINKS_TSV_PATH),
                    source_version,
                    json.dumps(dict(row), ensure_ascii=False, sort_keys=False),
                    ingested_at,
                ),
            )

            conn.execute(
                """
                INSERT INTO asset_refs (
                    asset_id,
                    doc_id,
                    asset_role,
                    local_rel_path,
                    remote_url,
                    gcs_key,
                    availability_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{doc_id}:primary",
                    doc_id,
                    "external_link",
                    None,
                    remote_url,
                    None,
                    "remote_only",
                ),
            )

            inserted += 1

    conn.execute(
        "INSERT INTO build_info (key, value) VALUES (?, ?)",
        ("curated_links_source_version", source_version),
    )
    return inserted
