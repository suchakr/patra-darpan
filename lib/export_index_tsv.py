from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse

from lib.config import EXPORTS_DIR, REFERENCE_LEGACY_DIR, SQLITE_PATH


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


LEGACY_INDEX_PATH = REFERENCE_LEGACY_DIR / "index.tsv"

# Projection-only fallback for rows that do not exist in legacy index.tsv.
# Keep this small. If it grows beyond a handful of entries, promote it into a
# more explicit enrichment source.
INDEX_ENRICHMENT_FALLBACKS: dict[
    tuple[str, str, str, str], dict[str, str]
] = {
    (
        "SwarajyaMag",
        "Did India Lack Historical Consciousness, Or Is It Just That India Understood Time Differently?",
        "https://swarajyamag.com/ideas/did-india-lack-historical-consciousness-or-is-it-just-that-india-understood-time-differently",
        "link",
    ): {"subject": "Culture", "category": "Indic"},
    (
        "IJHS-31-1996-Issue-4",
        "BookReview",
        "https://insa.nic.in/(S(eh1ucortlbqqezipwgliy3mn))/writereaddata/UpLoadedFiles/IJHS/Vol31_4_7_BookReview.pdf",
        "pdf",
    ): {"subject": "General", "category": "Other"},
    (
        "IJHS-47-2012-Issue-3",
        "The Violin and the Genesis of the Bose Institute in Calcutta",
        "https://insa.nic.in/(S(eh1ucortlbqqezipwgliy3mn))/writereaddata/UpLoadedFiles/IJHS/Vol47_3_4_PKBandyopadhyay.pdf",
        "pdf",
    ): {"subject": "Music", "category": "Indic"},
    (
        "IJHS-36-2001-Issue-3&4",
        "SADRATNAMĀLĀ OF ŚANKARAVARMAN",
        "https://insa.nic.in/(S(eh1ucortlbqqezipwgliy3mn))/writereaddata/UpLoadedFiles/IJHS/sadratnamaala-ihjs-2001-issue3&4.pdf",
        "pdf",
    ): {"subject": "Astronomy", "category": "Indic"},
    (
        "Karnataka Sanskrit 8.1",
        "The Scope of Aṣṭādaśavarṇana in the Mahākāvya Mathurābhyudaya",
        "https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/The_Scope_of_Ashtadashavarnana.pdf",
        "pdf",
    ): {"subject": "Culture", "category": "Indic"},
    (
        "Shodhsamhita XI.2",
        "A Comparative Analysis of the Kaṁsavadha Episode Across Various Purāṇic Texts",
        "https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/A_Comparitive_analysis_of_Kamsavadha_episode_in_Puranic_Texts.pdf",
        "pdf",
    ): {"subject": "Culture", "category": "Indic"},
}


def _load_legacy_enrichment() -> dict[tuple[str, str, str, str], dict[str, str]]:
    if not LEGACY_INDEX_PATH.exists():
        return {}

    with LEGACY_INDEX_PATH.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        return {
            (
                row.get("journal", ""),
                row.get("paper", ""),
                row.get("url", ""),
                row.get("entry_type", ""),
            ): {
                "subject": row.get("subject", ""),
                "category": row.get("category", ""),
            }
            for row in rows
        }


def _source_label(source_type: str, remote_url: str) -> str:
    if source_type == "portal_ijhs_metadata":
        return "insa"
    if source_type == "curated_pdf_metadata":
        return "insa"
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

    legacy_enrichment = _load_legacy_enrichment()

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
            row_key = (
                row["journal_label"] or "",
                row["title"] or "",
                remote_url,
                row["entry_type"] or "",
            )
            enrichment = legacy_enrichment.get(row_key)
            if not enrichment or (
                not enrichment.get("subject", "").strip()
                and not enrichment.get("category", "").strip()
            ):
                enrichment = INDEX_ENRICHMENT_FALLBACKS.get(
                    row_key, {"subject": "", "category": ""}
                )
            size_in_kb = raw.get("size_in_kb", "")
            if row["entry_type"] == "link" and not str(size_in_kb).strip():
                size_in_kb = "0"
            writer.writerow(
                {
                    "journal": row["journal_label"] or "",
                    "paper": row["title"] or "",
                    "subject": enrichment["subject"],
                    "category": enrichment["category"],
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
