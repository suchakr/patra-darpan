from __future__ import annotations

import sqlite3

from lib.cahc_registry import read_cahc_pdf_mirror_rows


def load_cahc_pdf_mirrors(
    conn: sqlite3.Connection,
    mirror_rows: list[dict[str, str]] | None = None,
) -> int:
    rows = mirror_rows or read_cahc_pdf_mirror_rows()
    for row in rows:
        conn.execute(
            """
            INSERT INTO cahc_pdf_mirror_registry_entries (
                source_url,
                mirror_url
            ) VALUES (?, ?)
            """,
            ((row.get("source_url") or "").strip(), (row.get("mirror_url") or "").strip()),
        )
    return len(rows)
