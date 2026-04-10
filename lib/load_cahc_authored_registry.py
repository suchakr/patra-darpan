from __future__ import annotations

import sqlite3

from lib.cahc_registry import read_cahc_authored_registry_entries


def load_cahc_authored_registry(
    conn: sqlite3.Connection,
    registry_entries: list[str] | None = None,
) -> int:
    entries = registry_entries or read_cahc_authored_registry_entries()
    for entry in entries:
        conn.execute(
            "INSERT INTO cahc_authorship_registry_entries (registry_key) VALUES (?)",
            (entry,),
        )
    return len(entries)
