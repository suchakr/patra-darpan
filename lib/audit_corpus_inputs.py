from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from tqdm import tqdm

from lib.cahc_registry import (
    read_cahc_authored_registry_entries,
    read_cahc_pdf_mirror_rows,
    registry_entry_matches,
)
from lib.config import (
    CAHC_AUTHORED_REGISTRY_PATH,
    CAHC_PDF_MIRRORS_TSV_PATH,
    CURATED_LINKS_TSV_PATH,
    CURATED_PDFS_TSV_PATH,
    IJHS_TSV_PATH,
    REPORTS_DIR,
    SHARED_IJHS_PDF_ROOT,
    SHARED_OTHER_PDF_ROOT,
    SQLITE_PATH,
)


DEFAULT_MD_OUT = REPORTS_DIR / "corpus-input-audit.md"
DEFAULT_JSON_OUT = REPORTS_DIR / "corpus-input-audit.json"


@dataclass
class AuditContext:
    root_rows: dict[str, list[dict[str, str]]]
    root_headers: dict[str, list[str]]
    registry_entries: list[str]
    mirror_rows: list[dict[str, str]]
    canonical_documents: list[dict[str, Any]]
    canonical_assets: list[dict[str, Any]]
    canonical_sources: list[dict[str, Any]]
    shared_ijhs_files: list[Path]
    shared_other_files: list[Path]


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _read_tsv_headers(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return reader.fieldnames or []


def _scan_files(root: Path) -> list[Path]:
    files = sorted(root.glob("*.pdf"))
    return [path for path in tqdm(files, desc=f"scan {root.name}", unit="file")]


def load_audit_context() -> AuditContext:
    root_rows = {
        "ijhs.tsv": _read_tsv_rows(IJHS_TSV_PATH),
        "curated-pdfs.tsv": _read_tsv_rows(CURATED_PDFS_TSV_PATH),
        "curated-links.tsv": _read_tsv_rows(CURATED_LINKS_TSV_PATH),
    }
    root_headers = {
        "ijhs.tsv": _read_tsv_headers(IJHS_TSV_PATH),
        "curated-pdfs.tsv": _read_tsv_headers(CURATED_PDFS_TSV_PATH),
        "curated-links.tsv": _read_tsv_headers(CURATED_LINKS_TSV_PATH),
        "cahc-pdf-mirrors.tsv": _read_tsv_headers(CAHC_PDF_MIRRORS_TSV_PATH),
    }
    registry_entries = read_cahc_authored_registry_entries(CAHC_AUTHORED_REGISTRY_PATH)
    mirror_rows = read_cahc_pdf_mirror_rows(CAHC_PDF_MIRRORS_TSV_PATH)

    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        canonical_documents = [
            dict(row)
            for row in conn.execute(
                """
                SELECT doc_id, entry_type, title, author_display, year, journal_label,
                       cahc_authored, source_root
                FROM documents
                ORDER BY source_root, doc_id
                """
            ).fetchall()
        ]
        canonical_assets = [
            dict(row)
            for row in conn.execute(
                """
                SELECT asset_id, doc_id, asset_role, local_rel_path, remote_url,
                       gcs_key, availability_status
                FROM asset_refs
                ORDER BY doc_id, asset_id
                """
            ).fetchall()
        ]
        canonical_sources = [
            dict(row)
            for row in conn.execute(
                """
                SELECT source_row_id, doc_id, source_type, source_path, source_version,
                       raw_metadata_json, ingested_at
                FROM document_sources
                ORDER BY source_path, source_row_id
                """
            ).fetchall()
        ]
    finally:
        conn.close()

    shared_ijhs_files = _scan_files(SHARED_IJHS_PDF_ROOT)
    shared_other_files = _scan_files(SHARED_OTHER_PDF_ROOT)

    return AuditContext(
        root_rows=root_rows,
        root_headers=root_headers,
        registry_entries=registry_entries,
        mirror_rows=mirror_rows,
        canonical_documents=canonical_documents,
        canonical_assets=canonical_assets,
        canonical_sources=canonical_sources,
        shared_ijhs_files=shared_ijhs_files,
        shared_other_files=shared_other_files,
    )


def _issue(severity: str, message: str, **details: Any) -> dict[str, Any]:
    return {"severity": severity, "message": message, "details": details}


_PROCEDURAL_IJHS_TITLE_PATTERNS = [
    r"^notes?$",
    r"^reviews?$",
    r"^book reviews?$",
    r"^news\b",
    r"^notes? and news$",
    r"^announcements?$",
    r"^session\b.*discussion$",
    r"^discussions?$",
    r"^supplement\b",
    r"^supplements$",
    r"^new publications$",
    r"^erratum$",
    r"^contents$",
    r"^editorial$",
    r"^guest editorial$",
    r"^obituary\b",
    r"^orbituay\b",
    r"^book received\b",
    r"^books received\b",
    r"^annual contents\b",
    r"^cumulative index\b",
    r"^notices?\b",
    r"^notice of journals\b",
    r"^conferences?$",
    r"^correspondence\b",
    r"^publication on history of science$",
    r"^academy publications?\b",
    r"^projects approved\b",
    r"^indian national commission\b",
    r"^chama newsletter$",
    r"^form iv$",
    r"^awards and honours$",
]


def _is_expected_authorless_procedural(doc: dict[str, Any]) -> bool:
    if doc.get("source_root") != "ijhs.tsv":
        return False
    title = (doc.get("title") or "").strip()
    if not title:
        return False
    return any(re.match(pattern, title, re.IGNORECASE) for pattern in _PROCEDURAL_IJHS_TITLE_PATTERNS)


def check_root_inventory(ctx: AuditContext) -> dict[str, Any]:
    expected_headers = {
        "ijhs.tsv": ["journal", "paper", "url", "size_in_kb", "author"],
        "curated-pdfs.tsv": ["journal", "paper", "url", "size_in_kb", "year", "author"],
        "curated-links.tsv": ["journal", "paper", "url", "year", "author"],
        "cahc-pdf-mirrors.tsv": ["source_url", "mirror_url"],
    }
    issues: list[dict[str, Any]] = []
    summary = {
        "ijhs_rows": len(ctx.root_rows["ijhs.tsv"]),
        "curated_pdf_rows": len(ctx.root_rows["curated-pdfs.tsv"]),
        "curated_link_rows": len(ctx.root_rows["curated-links.tsv"]),
        "registry_entries": len(ctx.registry_entries),
        "mirror_rows": len(ctx.mirror_rows),
        "shared_ijhs_files": len(ctx.shared_ijhs_files),
        "shared_other_files": len(ctx.shared_other_files),
    }
    for name, expected in expected_headers.items():
        actual = ctx.root_headers.get(name, [])
        if actual != expected:
            issues.append(
                _issue(
                    "error",
                    "Root input header does not match expected shape",
                    root_input=name,
                    expected=expected,
                    actual=actual,
                )
            )
    return {"name": "root_inventory", "summary": summary, "issues": issues}


def _looks_like_pdf_url(value: str) -> bool:
    return urlparse(value).path.lower().endswith(".pdf")


def _is_numeric(value: str) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def check_root_input_validation(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    ijhs_names = {path.name for path in ctx.shared_ijhs_files}
    other_names = {path.name for path in ctx.shared_other_files}
    root_pdf_urls = {
        (row.get("url") or "").strip()
        for name in ("ijhs.tsv", "curated-pdfs.tsv")
        for row in ctx.root_rows[name]
        if (row.get("url") or "").strip()
    }

    summary = {
        "ijhs_missing_required": 0,
        "ijhs_non_pdf_url": 0,
        "ijhs_non_numeric_size": 0,
        "ijhs_unmatched_local_filename": 0,
        "ijhs_unexpected_blank_author": 0,
        "ijhs_expected_authorless": 0,
        "curated_pdfs_missing_required": 0,
        "curated_pdfs_non_pdf_url": 0,
        "curated_pdfs_non_numeric_year": 0,
        "curated_pdfs_blank_size_in_kb": 0,
        "curated_pdfs_unmatched_local_filename": 0,
        "curated_links_missing_required": 0,
        "curated_links_non_numeric_year": 0,
        "mirror_missing_required": 0,
        "mirror_non_pdf_url": 0,
        "mirror_same_source_and_target": 0,
        "mirror_source_unmatched": 0,
        "registry_blank_entries": 0,
        "registry_duplicate_entries": 0,
    }

    seen_registry_entries: set[str] = set()
    duplicate_registry_entries: set[str] = set()
    for entry in ctx.registry_entries:
        if not entry.strip():
            summary["registry_blank_entries"] += 1
        if entry in seen_registry_entries:
            duplicate_registry_entries.add(entry)
        seen_registry_entries.add(entry)
    summary["registry_duplicate_entries"] = len(duplicate_registry_entries)
    for entry in sorted(duplicate_registry_entries):
        issues.append(
            _issue(
                "warning",
                "CAHC authorship registry has duplicate entry",
                registry_entry=entry,
            )
        )

    for row_number, row in enumerate(ctx.root_rows["ijhs.tsv"], start=1):
        journal = (row.get("journal") or "").strip()
        paper = (row.get("paper") or "").strip()
        url = (row.get("url") or "").strip()
        size_in_kb = (row.get("size_in_kb") or "").strip()
        author = (row.get("author") or "").strip()

        missing_fields = [
            field
            for field, value in {
                "journal": journal,
                "paper": paper,
                "url": url,
                "size_in_kb": size_in_kb,
            }.items()
            if not value
        ]
        if missing_fields:
            summary["ijhs_missing_required"] += 1
            issues.append(
                _issue(
                    "error",
                    "IJHS root row is missing required fields",
                    row_number=row_number,
                    missing_fields=missing_fields,
                    paper=paper,
                )
            )

        if url and not _looks_like_pdf_url(url):
            summary["ijhs_non_pdf_url"] += 1
            issues.append(
                _issue(
                    "error",
                    "IJHS root row URL does not look like a PDF",
                    row_number=row_number,
                    url=url,
                )
            )

        if size_in_kb and not _is_numeric(size_in_kb):
            summary["ijhs_non_numeric_size"] += 1
            issues.append(
                _issue(
                    "warning",
                    "IJHS root row size_in_kb is not numeric",
                    row_number=row_number,
                    size_in_kb=size_in_kb,
                    paper=paper,
                )
            )

        if journal and not re.search(r"IJHS\D\d+\D\d{4}\D", journal, re.IGNORECASE):
            issues.append(
                _issue(
                    "warning",
                    "IJHS root row journal does not match expected IJHS pattern",
                    row_number=row_number,
                    journal=journal,
                    paper=paper,
                )
            )

        if url:
            filename = Path(urlparse(url).path).name
            if filename and filename not in ijhs_names:
                summary["ijhs_unmatched_local_filename"] += 1
                issues.append(
                    _issue(
                        "error",
                        "IJHS root row URL basename is missing from shared ijhs asset root",
                        row_number=row_number,
                        filename=filename,
                        url=url,
                    )
                )

        if not author:
            if any(re.match(pattern, paper, re.IGNORECASE) for pattern in _PROCEDURAL_IJHS_TITLE_PATTERNS):
                summary["ijhs_expected_authorless"] += 1
            else:
                summary["ijhs_unexpected_blank_author"] += 1
                issues.append(
                    _issue(
                        "info",
                        "IJHS root row has blank author outside the expected procedural patterns",
                        row_number=row_number,
                        paper=paper,
                        journal=journal,
                    )
                )

    for row_number, row in enumerate(ctx.root_rows["curated-pdfs.tsv"], start=1):
        journal = (row.get("journal") or "").strip()
        paper = (row.get("paper") or "").strip()
        url = (row.get("url") or "").strip()
        size_in_kb = (row.get("size_in_kb") or "").strip()
        year = (row.get("year") or "").strip()

        missing_fields = [
            field
            for field, value in {
                "journal": journal,
                "paper": paper,
                "url": url,
                "year": year,
            }.items()
            if not value
        ]
        if missing_fields:
            summary["curated_pdfs_missing_required"] += 1
            issues.append(
                _issue(
                    "error",
                    "Curated PDF row is missing required fields",
                    row_number=row_number,
                    missing_fields=missing_fields,
                    paper=paper,
                )
            )

        if not size_in_kb:
            summary["curated_pdfs_blank_size_in_kb"] += 1

        if url and not _looks_like_pdf_url(url):
            summary["curated_pdfs_non_pdf_url"] += 1
            issues.append(
                _issue(
                    "error",
                    "Curated PDF URL does not look like a PDF",
                    row_number=row_number,
                    url=url,
                )
            )

        if year and not _is_numeric(year):
            summary["curated_pdfs_non_numeric_year"] += 1
            issues.append(
                _issue(
                    "warning",
                    "Curated PDF year is not numeric",
                    row_number=row_number,
                    year=year,
                    paper=paper,
                )
            )

        if url:
            filename = Path(urlparse(url).path).name
            if filename and filename not in other_names:
                summary["curated_pdfs_unmatched_local_filename"] += 1
                issues.append(
                    _issue(
                        "error",
                        "Curated PDF URL basename is missing from shared other asset root",
                        row_number=row_number,
                        filename=filename,
                        url=url,
                    )
                )

    for row_number, row in enumerate(ctx.root_rows["curated-links.tsv"], start=1):
        journal = (row.get("journal") or "").strip()
        paper = (row.get("paper") or "").strip()
        url = (row.get("url") or "").strip()
        year = (row.get("year") or "").strip()

        missing_fields = [
            field
            for field, value in {
                "journal": journal,
                "paper": paper,
                "url": url,
                "year": year,
            }.items()
            if not value
        ]
        if missing_fields:
            summary["curated_links_missing_required"] += 1
            issues.append(
                _issue(
                    "error",
                    "Curated link row is missing required fields",
                    row_number=row_number,
                    missing_fields=missing_fields,
                    paper=paper,
                )
            )

        if year and not _is_numeric(year):
            summary["curated_links_non_numeric_year"] += 1
            issues.append(
                _issue(
                    "warning",
                    "Curated link year is not numeric",
                    row_number=row_number,
                    year=year,
                    paper=paper,
                )
            )

    seen_mirror_pairs: set[tuple[str, str]] = set()
    for row_number, row in enumerate(ctx.mirror_rows, start=1):
        source_url = (row.get("source_url") or "").strip()
        mirror_url = (row.get("mirror_url") or "").strip()
        if not source_url or not mirror_url:
            summary["mirror_missing_required"] += 1
            issues.append(
                _issue(
                    "error",
                    "Mirror row is missing source_url or mirror_url",
                    row_number=row_number,
                    source_url=source_url,
                    mirror_url=mirror_url,
                )
            )
        if source_url and not _looks_like_pdf_url(source_url):
            summary["mirror_non_pdf_url"] += 1
            issues.append(
                _issue(
                    "warning",
                    "Mirror source_url does not look like a PDF",
                    row_number=row_number,
                    source_url=source_url,
                )
            )
        if mirror_url and not _looks_like_pdf_url(mirror_url):
            summary["mirror_non_pdf_url"] += 1
            issues.append(
                _issue(
                    "warning",
                    "Mirror mirror_url does not look like a PDF",
                    row_number=row_number,
                    mirror_url=mirror_url,
                )
            )
        if source_url and mirror_url and source_url == mirror_url:
            summary["mirror_same_source_and_target"] += 1
            issues.append(
                _issue(
                    "error",
                    "Mirror row uses the same URL for source and mirror",
                    row_number=row_number,
                    source_url=source_url,
                )
            )
        if source_url and source_url not in root_pdf_urls:
            summary["mirror_source_unmatched"] += 1
            issues.append(
                _issue(
                    "warning",
                    "Mirror source_url does not match any PDF-backed root input URL",
                    row_number=row_number,
                    source_url=source_url,
                    mirror_url=mirror_url,
                )
            )
        key = (source_url, mirror_url)
        if source_url and mirror_url and key in seen_mirror_pairs:
            issues.append(
                _issue(
                    "warning",
                    "Mirror registry contains duplicate source/mirror pair",
                    row_number=row_number,
                    source_url=source_url,
                    mirror_url=mirror_url,
                )
            )
        seen_mirror_pairs.add(key)

    return {"name": "root_input_validation", "summary": summary, "issues": issues}


def check_canonical_inventory(ctx: AuditContext) -> dict[str, Any]:
    summary = {
        "documents": len(ctx.canonical_documents),
        "document_sources": len(ctx.canonical_sources),
        "asset_refs": len(ctx.canonical_assets),
        "documents_by_source": dict(
            sorted(Counter(doc["source_root"] for doc in ctx.canonical_documents).items())
        ),
        "documents_by_entry_type": dict(
            sorted(Counter(doc["entry_type"] for doc in ctx.canonical_documents).items())
        ),
    }
    return {"name": "canonical_inventory", "summary": summary, "issues": []}


def check_missing_local_files(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    for asset in ctx.canonical_assets:
        if asset["asset_role"] == "external_link":
            continue
        local_rel_path = asset["local_rel_path"]
        if not local_rel_path:
            issues.append(
                _issue(
                    "warning",
                    "PDF asset has no local_rel_path",
                    doc_id=asset["doc_id"],
                    remote_url=asset["remote_url"],
                )
            )
            continue
        bucket, _, filename = local_rel_path.partition("/")
        root = SHARED_IJHS_PDF_ROOT if bucket == "ijhs" else SHARED_OTHER_PDF_ROOT
        if not (root / filename).exists():
            issues.append(
                _issue(
                    "error",
                    "Mapped PDF file is missing from shared asset root",
                    doc_id=asset["doc_id"],
                    local_rel_path=local_rel_path,
                    remote_url=asset["remote_url"],
                )
            )
    return {
        "name": "missing_local_files",
        "summary": {"issue_count": len(issues)},
        "issues": issues,
    }


def check_orphan_files(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    mapped_paths = {
        asset["local_rel_path"]
        for asset in ctx.canonical_assets
        if asset.get("local_rel_path")
    }

    def has_encoded_alias(rel_path: str) -> bool:
        bucket, _, name = rel_path.partition("/")
        if not bucket or not name:
            return False
        encoded_name = quote(name, safe="'()&,-._")
        if encoded_name == name:
            return False
        return f"{bucket}/{encoded_name}" in mapped_paths

    for path in ctx.shared_ijhs_files:
        rel = f"ijhs/{path.name}"
        if has_encoded_alias(rel):
            continue
        if rel not in mapped_paths:
            issues.append(_issue("warning", "Shared IJHS PDF has no canonical row", local_rel_path=rel))

    for path in ctx.shared_other_files:
        rel = f"other/{path.name}"
        if has_encoded_alias(rel):
            continue
        if rel not in mapped_paths:
            issues.append(_issue("warning", "Shared curated PDF has no canonical row", local_rel_path=rel))

    return {"name": "orphan_files", "summary": {"issue_count": len(issues)}, "issues": issues}


def check_duplicate_asset_mappings(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    local_path_map: dict[str, list[str]] = defaultdict(list)
    remote_url_map: dict[str, list[str]] = defaultdict(list)

    for asset in ctx.canonical_assets:
        if asset.get("local_rel_path"):
            local_path_map[asset["local_rel_path"]].append(asset["doc_id"])
        if asset.get("remote_url"):
            remote_url_map[asset["remote_url"]].append(asset["doc_id"])

    for local_rel_path, doc_ids in sorted(local_path_map.items()):
        unique_doc_ids = sorted(set(doc_ids))
        if len(unique_doc_ids) > 1:
            issues.append(
                _issue(
                    "warning",
                    "Local asset path is assigned to multiple documents",
                    local_rel_path=local_rel_path,
                    doc_ids=unique_doc_ids,
                )
            )

    for remote_url, doc_ids in sorted(remote_url_map.items()):
        unique_doc_ids = sorted(set(doc_ids))
        if len(unique_doc_ids) > 1:
            issues.append(
                _issue(
                    "warning",
                    "Remote URL is assigned to multiple documents",
                    remote_url=remote_url,
                    doc_ids=unique_doc_ids,
                )
            )

    return {
        "name": "duplicate_asset_mappings",
        "summary": {"issue_count": len(issues)},
        "issues": issues,
    }


def check_doc_id_collisions(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    collision_docs = [
        doc for doc in ctx.canonical_documents if doc["doc_id"].endswith(tuple(f"-{i:02d}" for i in range(2, 100)))
    ]
    for doc in collision_docs:
        issues.append(
            _issue(
                "info",
                "doc_id has observed collision suffix",
                doc_id=doc["doc_id"],
                title=doc["title"],
                source_root=doc["source_root"],
            )
        )
    return {
        "name": "doc_id_collisions",
        "summary": {"issue_count": len(issues)},
        "issues": issues,
    }


def check_core_field_quality(ctx: AuditContext) -> dict[str, Any]:
    docs = ctx.canonical_documents
    issues: list[dict[str, Any]] = []

    missing_title = [doc for doc in docs if not (doc.get("title") or "").strip()]
    missing_author = [doc for doc in docs if not (doc.get("author_display") or "").strip()]
    expected_authorless = [doc for doc in missing_author if _is_expected_authorless_procedural(doc)]
    unexpected_missing_author = [doc for doc in missing_author if not _is_expected_authorless_procedural(doc)]
    missing_journal = [doc for doc in docs if not (doc.get("journal_label") or "").strip()]
    missing_entry_type = [doc for doc in docs if not (doc.get("entry_type") or "").strip()]
    missing_year = [doc for doc in docs if not (doc.get("year") or "").strip()]

    for doc in missing_title[:20]:
        issues.append(_issue("error", "Missing core field `title`", doc_id=doc["doc_id"], source_root=doc["source_root"]))
    for doc in unexpected_missing_author[:20]:
        issues.append(_issue("warning", "Missing core field `author_display`", doc_id=doc["doc_id"], source_root=doc["source_root"]))
    for doc in missing_journal[:20]:
        issues.append(_issue("warning", "Missing core field `journal_label`", doc_id=doc["doc_id"], source_root=doc["source_root"]))
    for doc in missing_entry_type[:20]:
        issues.append(_issue("error", "Missing core field `entry_type`", doc_id=doc["doc_id"], source_root=doc["source_root"]))

    year_derivable = 0
    for doc in missing_year:
        journal = doc.get("journal_label") or ""
        if journal.startswith("IJHS-"):
            year_derivable += 1
    summary = {
        "missing_title": len(missing_title),
        "missing_author_display": len(unexpected_missing_author),
        "expected_authorless_procedural_entries": len(expected_authorless),
        "missing_journal_label": len(missing_journal),
        "missing_entry_type": len(missing_entry_type),
        "missing_year": len(missing_year),
        "year_derivable_from_ijhs_journal_label": year_derivable,
    }
    return {"name": "core_field_quality", "summary": summary, "issues": issues}


def check_deferred_field_status(ctx: AuditContext) -> dict[str, Any]:
    source_roots = Counter(doc["source_root"] for doc in ctx.canonical_documents)
    cahc_true_by_source = Counter(
        doc["source_root"] for doc in ctx.canonical_documents if doc["cahc_authored"]
    )
    summary = {
        "documents_by_source_root": dict(sorted(source_roots.items())),
        "cahc_authored_true_by_source_root": dict(sorted(cahc_true_by_source.items())),
        "subject_status": "deferred; export currently leaves subject blank",
        "category_status": "deferred; export currently leaves category blank",
        "cahc_authored_status": "present as a curated label in documents; still needs clearer long-term placement",
    }
    return {"name": "deferred_field_status", "summary": summary, "issues": []}


def check_cahc_registry_mismatches(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    matched_registry_entries: set[str] = set()

    doc_by_id = {doc["doc_id"]: doc for doc in ctx.canonical_documents}
    for asset in ctx.canonical_assets:
        doc = doc_by_id[asset["doc_id"]]
        filename = Path(asset["local_rel_path"]).name if asset.get("local_rel_path") else ""
        remote_url = asset.get("remote_url") or ""
        matched = False
        for entry in ctx.registry_entries:
            if registry_entry_matches(entry, remote_url=remote_url, local_rel_path=asset.get("local_rel_path")):
                matched = True
                matched_registry_entries.add(entry)
        if doc["cahc_authored"] and not matched:
            issues.append(
                _issue(
                    "warning",
                    "Document is marked cahc_authored but has no registry match",
                    doc_id=doc["doc_id"],
                    title=doc["title"],
                    local_rel_path=asset.get("local_rel_path"),
                    remote_url=remote_url,
                )
            )

    for entry in ctx.registry_entries:
        if entry not in matched_registry_entries:
            issues.append(
                _issue(
                    "info",
                    "Registry entry does not match any canonical asset",
                    registry_entry=entry,
                )
            )

    return {
        "name": "cahc_registry_mismatches",
        "summary": {"issue_count": len(issues)},
        "issues": issues,
    }


def check_mirror_registry_mismatches(ctx: AuditContext) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    primary_urls = {
        asset["remote_url"]: asset["doc_id"]
        for asset in ctx.canonical_assets
        if asset.get("asset_role") in {"primary_pdf", "external_link"} and asset.get("remote_url")
    }
    mirror_urls = {
        asset["remote_url"]: asset["doc_id"]
        for asset in ctx.canonical_assets
        if asset.get("asset_role") == "mirror_pdf" and asset.get("remote_url")
    }

    for row in ctx.mirror_rows:
        source_url = (row.get("source_url") or "").strip()
        mirror_url = (row.get("mirror_url") or "").strip()
        if source_url not in primary_urls:
            issues.append(
                _issue(
                    "error",
                    "Mirror registry source_url does not match any canonical primary asset",
                    source_url=source_url,
                    mirror_url=mirror_url,
                )
            )
        if mirror_url not in mirror_urls:
            issues.append(
                _issue(
                    "error",
                    "Mirror registry mirror_url does not match any canonical mirror asset",
                    source_url=source_url,
                    mirror_url=mirror_url,
                )
            )

    return {
        "name": "mirror_registry_mismatches",
        "summary": {"issue_count": len(issues)},
        "issues": issues,
    }


AVAILABLE_CHECKS = {
    "root_inventory": check_root_inventory,
    "root_input_validation": check_root_input_validation,
    "canonical_inventory": check_canonical_inventory,
    "core_field_quality": check_core_field_quality,
    "deferred_field_status": check_deferred_field_status,
    "missing_local_files": check_missing_local_files,
    "orphan_files": check_orphan_files,
    "duplicate_asset_mappings": check_duplicate_asset_mappings,
    "doc_id_collisions": check_doc_id_collisions,
    "cahc_registry_mismatches": check_cahc_registry_mismatches,
    "mirror_registry_mismatches": check_mirror_registry_mismatches,
}


def run_audit(selected_checks: list[str] | None = None) -> dict[str, Any]:
    ctx = load_audit_context()
    check_names = selected_checks or list(AVAILABLE_CHECKS.keys())
    results: list[dict[str, Any]] = []
    for check_name in tqdm(check_names, desc="run checks", unit="check"):
        result = AVAILABLE_CHECKS[check_name](ctx)
        results.append(result)

    severity_counts = Counter(
        issue["severity"] for result in results for issue in result["issues"]
    )

    return {
        "selected_checks": check_names,
        "severity_counts": dict(sorted(severity_counts.items())),
        "results": results,
    }


def write_audit_markdown(data: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Corpus Input Audit",
        "",
        "## Summary",
        f"- checks run: {len(data['selected_checks'])}",
        f"- severity counts: {data['severity_counts'] or {}}",
        "",
    ]

    for result in data["results"]:
        lines.append(f"## {result['name']}")
        summary = result.get("summary", {})
        if summary:
            for key, value in summary.items():
                lines.append(f"- {key}: {value}")
        else:
            lines.append("- no summary")
        issues = result.get("issues", [])
        lines.append(f"- issue_count: {len(issues)}")
        lines.append("")
        if issues:
            sample = issues[:20]
            lines.append("### Sample Issues")
            for issue in sample:
                details = ", ".join(f"{k}={v!r}" for k, v in issue["details"].items())
                lines.append(f"- [{issue['severity']}] {issue['message']}" + (f" ({details})" if details else ""))
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def write_audit_json(data: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit root corpus inputs, shared asset roots, and canonical metadata assembly.",
    )
    parser.add_argument(
        "--check",
        action="append",
        choices=sorted(AVAILABLE_CHECKS.keys()),
        help="Run only the named check. Repeat to run multiple checks.",
    )
    parser.add_argument(
        "--list-checks",
        action="store_true",
        help="List available check names and exit.",
    )
    parser.add_argument(
        "--md-out",
        type=Path,
        default=DEFAULT_MD_OUT,
        help=f"Markdown report output path. Default: {DEFAULT_MD_OUT}",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=DEFAULT_JSON_OUT,
        help=f"JSON report output path. Default: {DEFAULT_JSON_OUT}",
    )
    return parser
