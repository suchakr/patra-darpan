# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pandas",
# ]
# ///
"""
bootstrap-ingest.py — Step 10 of feat/unified-corpus

One-time script to integrate existing JUNI (cached_papers/rni/) PDFs into
the unified corpus architecture.

What it does:
  Job A: Tag existing IJHS rows in index.tsv that have ju_url → cahc_authored=true
  Job B: Copy non-IJHS CAHC PDFs to corpus/other/ and append new rows to index.tsv
  Job C: Print a summary report

It does NOT: upload to GCS (use sync_gcs.py for that), delete any files, or
touch ijhs.tsv / ijhs-classified.tsv.

Usage:
    uv run pipeline/bootstrap-ingest.py [--dry-run]
"""
import csv
import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
JUNI_DIR = Path.home() / "projects/cahcblr.github.io/assets/cached_papers/rni"
CORPUS_OTHER = PROJECT_ROOT / "corpus/other"
INDEX_TSV = PROJECT_ROOT / "corpus/index.tsv"

# --- Classification rules ---
# Files matching INSA Vol naming → IJHS papers (already in corpus/ijhs/)
# Files matching these prefixes → non-IJHS CAHC papers → go to corpus/other/
# Everything else → CAHC research papers → also corpus/other/

SKIP_FILES = {
    "cahc-rni-papers.zip",   # archive, not a paper
    "index.html",            # web page
    "index.md",              # web page
}

# Files with "$" prefix are URL-encoding artifacts — skip
def is_dollar_prefixed(name):
    return name.startswith("$")

# IJHS-pattern files (Vol*) — already in corpus/ijhs/, don't duplicate
def is_ijhs_pattern(name):
    lower = name.lower()
    return lower.startswith("vol") or lower.startswith("0") and "_" in lower[:5]

# More precise: check if file is already in corpus/ijhs/
def is_in_corpus_ijhs(name):
    return (PROJECT_ROOT / "corpus/ijhs" / name).exists()


def load_index():
    """Load index.tsv as list of dicts."""
    rows = []
    with INDEX_TSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            rows.append(row)
    return reader.fieldnames, rows


def save_index(fieldnames, rows):
    """Write rows back to index.tsv."""
    with INDEX_TSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def derive_metadata_from_filename(filename):
    """
    Best-effort metadata derivation from JUNI filename.
    Returns (journal, paper_title, author).
    """
    stem = Path(filename).stem

    # AJPEM papers
    if stem.startswith("ajpem_"):
        parts = stem.split("_", 2)
        year = parts[1] if len(parts) > 1 else ""
        title = parts[2].replace("_", " ").title() if len(parts) > 2 else stem
        return "AJPEM", title, "R N Iyengar"

    # ALT papers
    if stem.startswith("alt_"):
        parts = stem.split("_", 2)
        year = parts[1] if len(parts) > 1 else ""
        title = parts[2].replace("_", " ").title() if len(parts) > 2 else stem
        return "ALT", title, "R N Iyengar"

    # QJMS papers
    if stem.startswith("QJMS_"):
        title = stem.replace("_", " ")
        return "QJMS", title, "R N Iyengar"

    # RNI-prefixed
    if stem.startswith("rni-"):
        title = stem.replace("rni-", "").replace("-", " ").title()
        return "Other", title, "R N Iyengar"

    # Mahisvini
    if "mahisvini" in stem.lower():
        title = stem.replace("_", " ").title()
        return "Mahisvini", title, "R N Iyengar"

    # IJTS
    if stem.startswith("ijts_"):
        parts = stem.split("_", 2)
        title = parts[2].replace("_", " ").title() if len(parts) > 2 else stem
        return "IJTS", title, "R N Iyengar"

    # time-2015, vddhagargiya, etc (general CAHC papers)
    title = stem.replace("_", " ").replace("-", " ").title()
    return "Other", title, "R N Iyengar"


def bootstrap(dry_run=False):
    if not JUNI_DIR.exists():
        print(f"ERROR: JUNI directory not found: {JUNI_DIR}", file=sys.stderr)
        sys.exit(1)

    if not INDEX_TSV.exists():
        print(f"ERROR: index.tsv not found. Run migrate_index.py first.", file=sys.stderr)
        sys.exit(1)

    fieldnames, rows = load_index()

    # Build lookup of existing index rows by both ju_url AND url basenames
    existing_basenames = set()
    for row in rows:
        for col in ["ju_url", "url"]:
            val = (row.get(col) or "").strip()
            if val:
                existing_basenames.add(Path(val).name)

    # Scan JUNI
    juni_files = sorted(os.listdir(JUNI_DIR))

    # Counters
    skipped = []
    already_in_ijhs = []
    already_in_index = []
    new_other = []

    for filename in juni_files:
        filepath = JUNI_DIR / filename

        # Skip non-files
        if not filepath.is_file():
            continue

        # Skip non-PDFs and junk
        if filename in SKIP_FILES:
            skipped.append((filename, "skip list"))
            continue
        if is_dollar_prefixed(filename):
            skipped.append((filename, "$-prefixed artifact"))
            continue
        if not filename.lower().endswith(".pdf"):
            skipped.append((filename, "not a PDF"))
            continue

        # Already in corpus/ijhs/?
        if is_in_corpus_ijhs(filename):
            already_in_ijhs.append(filename)
            continue

        # Already referenced in index.tsv via ju_url or url?
        if filename in existing_basenames:
            already_in_index.append(filename)
            continue

        # This is a non-IJHS CAHC paper → goes to corpus/other/
        new_other.append(filename)

    # --- Report ---
    print(f"JUNI files scanned:       {len(juni_files)}")
    print(f"Skipped (junk/non-PDF):   {len(skipped)}")
    print(f"Already in corpus/ijhs/:  {len(already_in_ijhs)}")
    print(f"Already in index.tsv:     {len(already_in_index)}")
    print(f"New → corpus/other/:      {len(new_other)}")

    if skipped:
        print("\n  Skipped:")
        for name, reason in skipped:
            print(f"    {name}  ({reason})")

    if already_in_ijhs:
        print(f"\n  Already in corpus/ijhs/ ({len(already_in_ijhs)}):")
        for name in already_in_ijhs[:5]:
            print(f"    {name}")
        if len(already_in_ijhs) > 5:
            print(f"    ... and {len(already_in_ijhs) - 5} more")

    if new_other:
        print(f"\n  New non-IJHS papers for corpus/other/ ({len(new_other)}):")
        for name in new_other:
            journal, title, author = derive_metadata_from_filename(name)
            print(f"    {name}  →  [{journal}] {title}")

    # --- Job A: Tag cahc_authored in existing rows ---
    tagged = 0
    for row in rows:
        ju = (row.get("ju_url") or "").strip()
        if ju and "jainuniversity.ac.in" in ju:
            if row.get("cahc_authored") != "true":
                row["cahc_authored"] = "true"
                tagged += 1
    print(f"\n  Job A: Tagged {tagged} existing rows as cahc_authored=true")

    # --- Job B: Copy files and append rows ---
    if new_other:
        if not dry_run:
            CORPUS_OTHER.mkdir(parents=True, exist_ok=True)

        for filename in new_other:
            src = JUNI_DIR / filename
            dst = CORPUS_OTHER / filename
            journal, title, author = derive_metadata_from_filename(filename)

            # Get file size
            size_kb = src.stat().st_size // 1024

            new_row = {
                "journal": journal,
                "paper": title,
                "subject": "",       # to be classified later
                "category": "Indic",
                "author": author,
                "url": "",           # no INSA url
                "size_in_kb": str(size_kb),
                "year": "",
                "ju_url": f"https://cahc.jainuniversity.ac.in/assets/cached_papers/rni/{filename}",
                "entry_type": "pdf",
                "source": "ingest",
                "cahc_authored": "true",
                "gcs_key": f"other/{filename}",
                "gcs_synced": "false",
            }
            rows.append(new_row)

            if not dry_run:
                shutil.copy2(str(src), str(dst))

        print(f"  Job B: {'Would copy' if dry_run else 'Copied'} {len(new_other)} files to corpus/other/")
        print(f"  Job B: {'Would append' if dry_run else 'Appended'} {len(new_other)} rows to index.tsv")

    # --- Save ---
    if not dry_run:
        save_index(fieldnames, rows)
        print(f"\n  Saved index.tsv ({len(rows)} total rows)")
    else:
        print(f"\n  [dry-run] No files copied, no rows saved. Would result in {len(rows)} rows.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    bootstrap(dry_run=dry_run)
