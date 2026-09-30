from __future__ import annotations

import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import SCHEMA_PATH, SQLITE_PATH
from lib.cahc_registry import mirror_map_by_source_url, read_cahc_authored_registry_entries, read_cahc_pdf_mirror_rows
from lib.load_cahc_authored_registry import load_cahc_authored_registry
from lib.load_cahc_pdf_mirrors import load_cahc_pdf_mirrors
from lib.load_curated_tsv import load_curated_links_tsv, load_curated_pdfs_tsv
from lib.load_ijhs_tsv import load_ijhs_tsv


def _populate_catalog(database_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(database_path)
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

    return {
        "ijhs_rows": ijhs_rows,
        "curated_pdf_rows": curated_pdf_rows,
        "curated_link_rows": curated_link_rows,
        "registry_rows": registry_rows,
        "mirror_rows": mirror_rows,
    }


def _validate_catalog(database_path: Path) -> None:
    conn = sqlite3.connect(database_path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise sqlite3.DatabaseError(f"catalog integrity check failed: {integrity!r}")

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "documents" not in tables:
            raise sqlite3.DatabaseError("catalog is missing the documents table")
        if conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0:
            raise sqlite3.DatabaseError("catalog contains no documents")
    finally:
        conn.close()


def build_catalog_atomically(database_path: Path = SQLITE_PATH) -> dict[str, int]:
    """Build and validate a sibling temporary catalog before replacing the current one."""
    database_path = Path(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{database_path.name}.",
        suffix=".tmp",
        dir=database_path.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary_name)

    try:
        counts = _populate_catalog(temporary_path)
        _validate_catalog(temporary_path)

        # Keep the existing catalog's access mode on rebuilds. A first build is
        # readable by the host operator and the read-only retrieval containers.
        try:
            mode = stat.S_IMODE(database_path.stat().st_mode)
        except FileNotFoundError:
            mode = 0o644
        os.chmod(temporary_path, mode)

        # The temporary file shares the destination directory, so replacement
        # is atomic and a failed build leaves the previous catalog untouched.
        os.replace(temporary_path, database_path)
        return counts
    finally:
        for suffix in ("", "-journal", "-wal", "-shm"):
            Path(f"{temporary_path}{suffix}").unlink(missing_ok=True)


def main() -> None:
    counts = build_catalog_atomically(SQLITE_PATH)

    print(f"Built {SQLITE_PATH}")
    print(f"Loaded ijhs.tsv rows: {counts['ijhs_rows']}")
    print(f"Loaded curated-pdfs.tsv rows: {counts['curated_pdf_rows']}")
    print(f"Loaded curated-links.tsv rows: {counts['curated_link_rows']}")
    print(f"Loaded CAHC registry entries: {counts['registry_rows']}")
    print(f"Loaded CAHC PDF mirror entries: {counts['mirror_rows']}")


if __name__ == "__main__":
    main()
