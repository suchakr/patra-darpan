from __future__ import annotations

import csv
from pathlib import Path

from lib.config import CAHC_AUTHORED_REGISTRY_PATH, CAHC_PDF_MIRRORS_TSV_PATH


def read_cahc_authored_registry_entries(path: Path = CAHC_AUTHORED_REGISTRY_PATH) -> list[str]:
    entries: list[str] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            entries.append(stripped)
    return entries


def registry_entry_matches(
    registry_entry: str,
    remote_url: str = "",
    local_rel_path: str | None = None,
) -> bool:
    needle = registry_entry.lstrip("$")
    if not needle:
        return False

    haystacks = [remote_url or ""]
    if local_rel_path:
        haystacks.append(local_rel_path)
        haystacks.append(Path(local_rel_path).name)

    return any(needle in haystack for haystack in haystacks)


def infer_cahc_authored(
    registry_entries: list[str],
    remote_url: str = "",
    local_rel_path: str | None = None,
) -> bool:
    return any(
        registry_entry_matches(entry, remote_url=remote_url, local_rel_path=local_rel_path)
        for entry in registry_entries
    )


def read_cahc_pdf_mirror_rows(
    path: Path = CAHC_PDF_MIRRORS_TSV_PATH,
) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def mirror_map_by_source_url(
    mirror_rows: list[dict[str, str]],
) -> dict[str, str]:
    return {
        (row.get("source_url") or "").strip(): (row.get("mirror_url") or "").strip()
        for row in mirror_rows
        if (row.get("source_url") or "").strip() and (row.get("mirror_url") or "").strip()
    }
