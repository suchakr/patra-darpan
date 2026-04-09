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
from lib.config import IJHS_TSV_PATH, SHARED_IJHS_PDF_ROOT, SHARED_OTHER_PDF_ROOT


def file_version(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def _slugify(value: str) -> str:
    lowered = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", lowered)
    compact = re.sub(r"-{2,}", "-", normalized).strip("-")
    return compact or "untitled"


def _normalized_year_for_row(row: dict[str, str]) -> str:
    explicit_year = _clean_text(row.get("year"))
    if explicit_year:
        return explicit_year

    journal_label = _clean_text(row.get("journal"))
    match = re.search(r"IJHS\D\d+\D(\d{4})\D", journal_label, re.IGNORECASE)
    if match:
        return match.group(1)

    return ""


def _path_stem_from_url(url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    candidate = Path(parsed.path).name
    if not candidate:
        return None
    return Path(candidate).stem or None


def _remote_url_for_row(row: dict[str, str]) -> str:
    ju_url = _clean_text(row.get("ju_url"))
    url = _clean_text(row.get("url"))
    return ju_url or url


def _local_rel_path_for_row(row: dict[str, str]) -> str | None:
    remote_url = _remote_url_for_row(row)
    stem_name = Path(urlparse(remote_url).path).name if remote_url else ""
    if not stem_name:
        return None

    ijhs_candidate = SHARED_IJHS_PDF_ROOT / stem_name
    if ijhs_candidate.exists():
        return f"ijhs/{stem_name}"

    other_candidate = SHARED_OTHER_PDF_ROOT / stem_name
    if other_candidate.exists():
        return f"other/{stem_name}"

    return None


def _entry_type_for_row(row: dict[str, str]) -> str:
    remote_url = _remote_url_for_row(row)
    return "pdf" if remote_url.lower().endswith(".pdf") else "link"


def _base_doc_id_for_row(row: dict[str, str], row_number: int) -> str:
    remote_url = _remote_url_for_row(row)
    stem = _path_stem_from_url(remote_url)
    if stem:
        return stem
    title = _clean_text(row.get("paper"))
    return f"ijhs-row-{row_number:04d}-{_slugify(title)}"


def load_ijhs_tsv(
    conn: sqlite3.Connection,
    cahc_authored_registry_entries: list[str],
    mirror_map: dict[str, str],
) -> int:
    source_version = file_version(IJHS_TSV_PATH)
    ingested_at = datetime.now(UTC).isoformat()
    inserted = 0
    seen_doc_ids: dict[str, int] = {}

    with IJHS_TSV_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row_number, row in enumerate(reader, start=1):
            base_doc_id = _base_doc_id_for_row(row, row_number)
            seen_count = seen_doc_ids.get(base_doc_id, 0) + 1
            seen_doc_ids[base_doc_id] = seen_count
            doc_id = base_doc_id if seen_count == 1 else f"{base_doc_id}-{seen_count:02d}"
            local_rel_path = _local_rel_path_for_row(row)
            remote_url = _remote_url_for_row(row)
            cahc_authored = infer_cahc_authored(
                cahc_authored_registry_entries,
                remote_url=remote_url,
                local_rel_path=local_rel_path,
            )
            mirror_url = mirror_map.get(remote_url, "")
            title = _clean_text(row.get("paper"))
            author_display = _clean_text(row.get("author"))
            year = _normalized_year_for_row(row)
            journal_label = _clean_text(row.get("journal"))
            entry_type = _entry_type_for_row(row)
            source_row_id = f"ijhs:{row_number:05d}"
            gcs_key = local_rel_path

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
                    entry_type,
                    title,
                    author_display,
                    year,
                    journal_label,
                    1 if cahc_authored else 0,
                    "ijhs.tsv",
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
                    source_row_id,
                    doc_id,
                    "portal_ijhs_metadata",
                    str(IJHS_TSV_PATH),
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
                    "primary_pdf" if entry_type == "pdf" else "external_link",
                    local_rel_path,
                    remote_url,
                    gcs_key,
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
        ("ijhs_source_version", source_version),
    )
    return inserted
