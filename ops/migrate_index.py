#!/usr/bin/env python3
"""
migrate_index.py — Step 4 of feat/unified-corpus

Reads  : corpus/ijhs-classified.tsv  (9 columns, source of truth)
Writes : corpus/index.tsv            (9 + 5 new columns, new source of truth)

New columns added:
  entry_type   : 'pdf' for all existing rows (they are PDFs)
  source       : 'insa' for all existing rows (scraped from INSA)
  cahc_authored: 'true' if ju_url contains 'jainuniversity.ac.in', else 'false'
  gcs_key      : 'ijhs/<basename_of_INSA_url>'  (for IJHS papers)
                 'other/<basename_of_ju_url>'    (for non-IJHS papers with only ju_url)
                 ''                              (if no url at all)
  gcs_synced   : 'false' for all (sync status managed by sync_gcs.py)

NOTE: bootstrap-ingest.py will later correct gcs_synced=true for rows already
in GCS, and reclassify non-IJHS CAHC papers (gcs_key other→...). This script
is intentionally conservative.

Usage:
    python ops/migrate_index.py [--dry-run]
"""

import csv
import sys
from pathlib import Path

CORPUS_DIR = Path(__file__).parent.parent / "corpus"
SOURCE_TSV = CORPUS_DIR / "ijhs-classified.tsv"
OUTPUT_TSV = CORPUS_DIR / "index.tsv"

# Existing columns in ijhs-classified.tsv
SOURCE_FIELDS = ["journal", "paper", "subject", "category", "author",
                 "url", "size_in_kb", "year", "ju_url", "cahc_authored"]

# New columns being added
NEW_FIELDS = ["entry_type", "source", "gcs_key", "gcs_synced"]

ALL_FIELDS = SOURCE_FIELDS + NEW_FIELDS


def derive_gcs_key(url: str, ju_url: str) -> str:
    """
    Derive the canonical GCS key for a paper.

    Rule:
      - If the row has an INSA url → IJHS paper → gcs_key = ijhs/<basename>
      - If no INSA url but has ju_url → non-IJHS CAHC paper → gcs_key = other/<basename>
      - If neither → empty string (edge case; pipeline will handle separately)
    """
    url = (url or "").strip()
    ju_url = (ju_url or "").strip()

    if url:
        return f"ijhs/{Path(url).name}"
    elif ju_url:
        return f"other/{Path(ju_url).name}"
    return ""


def migrate(dry_run: bool = False) -> None:
    if not SOURCE_TSV.exists():
        print(f"ERROR: Source file not found: {SOURCE_TSV}", file=sys.stderr)
        sys.exit(1)

    if OUTPUT_TSV.exists() and not dry_run:
        print(f"WARNING: {OUTPUT_TSV} already exists — will overwrite.")

    rows_written = 0
    cahc_count = 0
    non_ijhs_cahc = 0
    no_url_count = 0

    out_rows = []

    with SOURCE_TSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")

        # Validate source has expected columns
        if reader.fieldnames != SOURCE_FIELDS:
            print(f"WARNING: Unexpected source columns: {reader.fieldnames}")
            print(f"         Expected:                  {SOURCE_FIELDS}")

        for row in reader:
            url     = (row.get("url") or "").strip()
            ju_url  = (row.get("ju_url") or "").strip()

            cahc_raw = str(row.get("cahc_authored", "")).strip().lower()
            cahc = cahc_raw == "true"
            gcs_key = derive_gcs_key(url, ju_url)

            new_row = {
                **{f: row.get(f, "") for f in SOURCE_FIELDS},
                "entry_type"   : "pdf",
                "source"       : "insa",
                "gcs_key"      : gcs_key,
                "gcs_synced"   : "false",
            }
            
            # Normalize cahc_authored to string 'true' / 'false'
            new_row["cahc_authored"] = "true" if cahc else "false"

            out_rows.append(new_row)
            rows_written += 1
            if cahc:
                cahc_count += 1
                if not url:
                    non_ijhs_cahc += 1
            if not gcs_key:
                no_url_count += 1

    # Report
    print(f"Source rows      : {rows_written}")
    print(f"CAHC-authored    : {cahc_count}")
    print(f"Non-IJHS CAHC    : {non_ijhs_cahc}  (no INSA url; gcs_key=other/...)")
    print(f"No URL at all    : {no_url_count}  (gcs_key left empty)")

    if dry_run:
        print("\n[dry-run] No file written.")
        print(f"Sample output row:\n  {out_rows[0] if out_rows else '(none)'}")
        return

    with OUTPUT_TSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ALL_FIELDS, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nWritten: {OUTPUT_TSV}  ({rows_written} rows)")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    migrate(dry_run=dry_run)
