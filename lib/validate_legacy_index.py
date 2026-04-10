from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from lib.config import EXPORTS_DIR, REFERENCE_LEGACY_DIR, REPORTS_DIR


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def validate_legacy_index(
    exported_path: Path | None = None, legacy_path: Path | None = None
) -> Path:
    if exported_path is None:
        exported_path = EXPORTS_DIR / "index.tsv"
    if legacy_path is None:
        legacy_path = REFERENCE_LEGACY_DIR / "index.tsv"

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "legacy-index-validation.md"

    exported_rows = _read_tsv(exported_path)
    legacy_rows = _read_tsv(legacy_path)

    exported_header = list(exported_rows[0].keys()) if exported_rows else []
    legacy_header = list(legacy_rows[0].keys()) if legacy_rows else []

    exported_entry_types = Counter(row.get("entry_type", "") for row in exported_rows)
    legacy_entry_types = Counter(row.get("entry_type", "") for row in legacy_rows)

    exported_keys = {
        (row.get("journal", ""), row.get("paper", ""), row.get("url", ""), row.get("entry_type", ""))
        for row in exported_rows
    }
    legacy_keys = {
        (row.get("journal", ""), row.get("paper", ""), row.get("url", ""), row.get("entry_type", ""))
        for row in legacy_rows
    }

    missing_from_export = sorted(legacy_keys - exported_keys)[:20]
    extra_in_export = sorted(exported_keys - legacy_keys)[:20]

    exported_nonempty_subject = sum(1 for row in exported_rows if row.get("subject", "").strip())
    legacy_nonempty_subject = sum(1 for row in legacy_rows if row.get("subject", "").strip())
    exported_nonempty_category = sum(1 for row in exported_rows if row.get("category", "").strip())
    legacy_nonempty_category = sum(1 for row in legacy_rows if row.get("category", "").strip())

    lines = [
        "# Legacy Index Validation",
        "",
        f"- exported path: `{exported_path}`",
        f"- legacy path: `{legacy_path}`",
        "",
        "## Row Counts",
        f"- exported rows: {len(exported_rows)}",
        f"- legacy rows: {len(legacy_rows)}",
        "",
        "## Headers",
        f"- exported header matches legacy: {exported_header == legacy_header}",
        "",
        "## Entry Type Counts",
        f"- exported: {dict(exported_entry_types)}",
        f"- legacy: {dict(legacy_entry_types)}",
        "",
        "## Enrichment Coverage",
        f"- exported non-empty `subject`: {exported_nonempty_subject}",
        f"- legacy non-empty `subject`: {legacy_nonempty_subject}",
        f"- exported non-empty `category`: {exported_nonempty_category}",
        f"- legacy non-empty `category`: {legacy_nonempty_category}",
        "",
        "## Keyed Row Presence",
        f"- missing from export by `(journal, paper, url, entry_type)`: {len(legacy_keys - exported_keys)}",
        f"- extra in export by `(journal, paper, url, entry_type)`: {len(exported_keys - legacy_keys)}",
        "",
    ]

    if missing_from_export:
        lines.append("### Missing From Export")
        lines.extend(
            f"- journal={j!r}, paper={p!r}, url={u!r}, entry_type={e!r}"
            for j, p, u, e in missing_from_export
        )
        lines.append("")

    if extra_in_export:
        lines.append("### Extra In Export")
        lines.extend(
            f"- journal={j!r}, paper={p!r}, url={u!r}, entry_type={e!r}"
            for j, p, u, e in extra_in_export
        )
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
