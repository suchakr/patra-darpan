from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import SCHEMA_PATH, SQLITE_PATH, ensure_runtime_dirs
from lib.cahc_registry import mirror_map_by_source_url, read_cahc_authored_registry_entries, read_cahc_pdf_mirror_rows
from lib.load_cahc_authored_registry import load_cahc_authored_registry
from lib.load_cahc_pdf_mirrors import load_cahc_pdf_mirrors
from lib.load_curated_tsv import load_curated_links_tsv, load_curated_pdfs_tsv
from lib.load_ijhs_tsv import load_ijhs_tsv


def main() -> None:
    ensure_runtime_dirs()
    if SQLITE_PATH.exists():
        SQLITE_PATH.unlink()

    conn = sqlite3.connect(SQLITE_PATH)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        cahc_authored_registry_entries = read_cahc_authored_registry_entries()
        mirror_rows_data = read_cahc_pdf_mirror_rows()
        mirror_map = mirror_map_by_source_url(mirror_rows_data)

        registry_rows = load_cahc_authored_registry(conn, cahc_authored_registry_entries)
        mirror_rows = load_cahc_pdf_mirrors(conn, mirror_rows_data)
        ijhs_rows = load_ijhs_tsv(conn, cahc_authored_registry_entries, mirror_map)
        curated_pdf_rows = load_curated_pdfs_tsv(conn, cahc_authored_registry_entries, mirror_map)
        curated_link_rows = load_curated_links_tsv(conn, cahc_authored_registry_entries)
        conn.commit()
    finally:
        conn.close()

    print(f"Built {SQLITE_PATH}")
    print(f"Loaded ijhs.tsv rows: {ijhs_rows}")
    print(f"Loaded curated-pdfs.tsv rows: {curated_pdf_rows}")
    print(f"Loaded curated-links.tsv rows: {curated_link_rows}")
    print(f"Loaded CAHC registry entries: {registry_rows}")
    print(f"Loaded CAHC PDF mirror entries: {mirror_rows}")


if __name__ == "__main__":
    main()
