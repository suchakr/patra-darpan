from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import EXPORTS_DIR, REPORTS_DIR, SQLITE_PATH
from lib.decode_lab.campaign_sets import SETS_DIR, list_campaign_sets, read_campaign_set


SUBJECT_HINTS = {
    "astro": "Astronomy",
    "astronomy": "Astronomy",
    "math": "Math",
    "mathematics": "Math",
}
CATEGORY_HINTS = {
    "indic": "Indic",
    "western": "Western",
    "arabic": "Arabic",
    "fareast": "Fareast",
    "other": "Other",
}
DOC_TYPE_HINTS = {
    "digital": "digital",
    "raster": "raster",
    "mixed": "mixed",
    "unknown": "unknown",
}
PREFERENCE_HINTS = {
    "native": "native",
    "table": "tables",
    "tables": "tables",
    "image": "images",
    "images": "images",
    "font": "font-risk",
    "font-risk": "font-risk",
}
ALL_HINTS = {
    **SUBJECT_HINTS,
    **CATEGORY_HINTS,
    **DOC_TYPE_HINTS,
    **PREFERENCE_HINTS,
}

NATIVE_PATTERN = re.compile(
    r"("
    r"[āīūṛṝḷḹṅñṭḍṇśṣṃḥĀĪŪṚṜḶḸṄÑṬḌṆŚṢṂḤ]"
    r"|sanskrit|vedic|veda|vedā|jyoti|jyotiṣ|siddh|nakṣ|naksh|garga|"
    r"parāś|parasara|vrddha|vṛddha|surya|sūrya|graha|tithi|pañc|panc"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Candidate:
    doc_id: str
    title: str
    subject: str
    category: str
    year: str
    journal: str
    gcs_key: str
    doc_type: str
    page_count: int | None
    image_count: int
    table_candidate_count: int
    fonts_missing_unicode_map_count: int


@dataclass(frozen=True)
class EffectiveArgs:
    name: str
    count: int
    subjects: tuple[str, ...]
    categories: tuple[str, ...]
    doc_types: tuple[str, ...]
    preferences: tuple[str, ...]
    raw_hints: tuple[str, ...]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate Decode Lab campaign sets from exports/index.tsv joined "
            "to primary_pdf_profiles. Positional words are selection hints."
        )
    )
    parser.add_argument(
        "recipe",
        nargs="+",
        help=(
            "Hints plus one count, for example: astro math indic raster native 10. "
            "Unique partial hints are accepted, e.g. tab -> tables."
        ),
    )
    parser.add_argument("--name", required=True, help="Campaign set name to write.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing .txt/.notes.md set file.",
    )
    parser.add_argument(
        "--index-tsv",
        type=Path,
        default=EXPORTS_DIR / "index.tsv",
        help="Compatibility projection carrying subject/category.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=SQLITE_PATH,
        help="SQLite database containing primary_pdf_profiles.",
    )
    parser.add_argument(
        "--sets-dir",
        type=Path,
        default=SETS_DIR,
        help="Directory where campaign set files are written.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory where campaign-set-audit.md is written.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    effective = parse_recipe(args.recipe, args.name)
    print_effective_args(effective)

    candidates = load_candidates(args.index_tsv, args.db)
    selected = select_candidates(candidates, effective)
    if len(selected) < effective.count:
        print(
            f"Warning: requested {effective.count} rows but only found {len(selected)}.",
            file=sys.stderr,
        )

    write_set(effective, selected, args.sets_dir, force=args.force)
    write_audit(args.sets_dir, args.reports_dir, candidates)

    print(f"Wrote {args.sets_dir / (effective.name + '.txt')}")
    print(f"Wrote {args.sets_dir / (effective.name + '.notes.md')}")
    print(f"Wrote {args.reports_dir / 'campaign-set-audit.md'}")


def parse_recipe(tokens: list[str], name: str) -> EffectiveArgs:
    count_tokens = [token for token in tokens if token.isdigit()]
    if len(count_tokens) != 1:
        raise SystemExit("Recipe must contain exactly one integer count.")
    count = int(count_tokens[0])
    if count < 1:
        raise SystemExit("Count must be positive.")

    raw_hints = [token for token in tokens if not token.isdigit()]
    normalized = [normalize_hint(token) for token in raw_hints]
    subjects = tuple(
        sorted({SUBJECT_HINTS[hint] for hint in normalized if hint in SUBJECT_HINTS})
    )
    categories = tuple(
        sorted({CATEGORY_HINTS[hint] for hint in normalized if hint in CATEGORY_HINTS})
    )
    doc_types = tuple(
        sorted({DOC_TYPE_HINTS[hint] for hint in normalized if hint in DOC_TYPE_HINTS})
    )
    preferences = tuple(
        sorted({PREFERENCE_HINTS[hint] for hint in normalized if hint in PREFERENCE_HINTS})
    )

    return EffectiveArgs(
        name=name,
        count=count,
        subjects=subjects,
        categories=categories,
        doc_types=doc_types,
        preferences=preferences,
        raw_hints=tuple(raw_hints),
    )


def normalize_hint(token: str) -> str:
    lowered = token.strip().lower()
    if lowered in ALL_HINTS:
        return lowered
    matches = sorted(key for key in ALL_HINTS if key.startswith(lowered))
    if not matches:
        raise SystemExit(f"Unknown campaign hint: {token!r}")
    mapped_values = {ALL_HINTS[key] for key in matches}
    if len(mapped_values) > 1:
        raise SystemExit(
            f"Ambiguous campaign hint {token!r}; matches: {', '.join(matches)}"
        )
    # Pick the shortest exact key for stable reporting, e.g. tab -> table.
    return sorted(matches, key=lambda value: (len(value), value))[0]


def print_effective_args(effective: EffectiveArgs) -> None:
    print("Effective campaign recipe:")
    print(f"  name: {effective.name}")
    print(f"  count: {effective.count}")
    print(f"  raw_hints: {', '.join(effective.raw_hints) or '(none)'}")
    print(
        "  hard_filters: "
        f"subjects={list(effective.subjects) or 'any'}, "
        f"categories={list(effective.categories) or 'any'}, "
        f"doc_types={list(effective.doc_types) or 'any'}"
    )
    print(f"  preferences: {list(effective.preferences) or 'none'}")


def load_candidates(index_tsv: Path, db_path: Path) -> list[Candidate]:
    if not index_tsv.exists():
        raise SystemExit(f"index.tsv not found: {index_tsv}")
    if not db_path.exists():
        raise SystemExit(f"SQLite database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        profiles = {
            row["gcs_key"]: row
            for row in conn.execute("SELECT * FROM primary_pdf_profiles")
            if row["gcs_key"]
        }
    finally:
        conn.close()

    candidates: list[Candidate] = []
    with index_tsv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("entry_type") != "pdf":
                continue
            profile = profiles.get(row.get("gcs_key", ""))
            if profile is None or not profile["profile_version"]:
                continue
            candidates.append(
                Candidate(
                    doc_id=profile["doc_id"],
                    title=row.get("paper", ""),
                    subject=row.get("subject", ""),
                    category=row.get("category", ""),
                    year=row.get("year", ""),
                    journal=row.get("journal", ""),
                    gcs_key=row.get("gcs_key", ""),
                    doc_type=profile["doc_type"] or "unknown",
                    page_count=profile["page_count"],
                    image_count=profile["image_count"] or 0,
                    table_candidate_count=profile["table_candidate_count"] or 0,
                    fonts_missing_unicode_map_count=(
                        profile["fonts_missing_unicode_map_count"] or 0
                    ),
                )
            )
    return candidates


def select_candidates(
    candidates: list[Candidate],
    effective: EffectiveArgs,
) -> list[Candidate]:
    filtered = [
        candidate
        for candidate in candidates
        if not effective.subjects or candidate.subject in effective.subjects
        if not effective.categories or candidate.category in effective.categories
        if not effective.doc_types or candidate.doc_type in effective.doc_types
    ]
    ranked = sorted(
        filtered,
        key=lambda candidate: (
            score_candidate(candidate, effective),
            -(candidate.page_count or 0),
            candidate.doc_id,
        ),
        reverse=True,
    )
    return ranked[: effective.count]


def score_candidate(candidate: Candidate, effective: EffectiveArgs) -> int:
    score = 0
    if "native" in effective.preferences and native_signal(candidate):
        score += 100
    if "tables" in effective.preferences:
        score += min(candidate.table_candidate_count, 20) * 5
    if "images" in effective.preferences:
        score += min(candidate.image_count, 100)
    if "font-risk" in effective.preferences:
        score += min(candidate.fonts_missing_unicode_map_count, 100)
    # Keep the default deterministic and slightly prefer richer documents.
    score += min(candidate.table_candidate_count, 10)
    score += min(candidate.image_count, 20)
    if candidate.fonts_missing_unicode_map_count:
        score += 2
    return score


def native_signal(candidate: Candidate) -> bool:
    haystack = " ".join([candidate.title, candidate.journal, candidate.gcs_key])
    return bool(NATIVE_PATTERN.search(haystack))


def write_set(
    effective: EffectiveArgs,
    selected: list[Candidate],
    sets_dir: Path,
    *,
    force: bool,
) -> None:
    sets_dir.mkdir(parents=True, exist_ok=True)
    set_path = sets_dir / f"{effective.name}.txt"
    notes_path = sets_dir / f"{effective.name}.notes.md"
    existing = [path for path in [set_path, notes_path] if path.exists()]
    if existing and not force:
        lines = [
            f"Refusing to overwrite existing campaign set: {effective.name}",
            "Existing files:",
            *[f"  {path}" for path in existing],
            "",
            "Use --force to overwrite, or choose a new --name.",
        ]
        raise SystemExit("\n".join(lines))

    set_lines = [
        "# Generated by scripts/generate_campaign_sets.py",
        f"# Name: {effective.name}",
        f"# Count: {len(selected)}",
        f"# Raw hints: {', '.join(effective.raw_hints)}",
        f"# Subjects: {', '.join(effective.subjects) or 'any'}",
        f"# Categories: {', '.join(effective.categories) or 'any'}",
        f"# Doc types: {', '.join(effective.doc_types) or 'any'}",
        f"# Preferences: {', '.join(effective.preferences) or 'none'}",
        "",
    ]
    set_lines.extend(candidate.doc_id for candidate in selected)
    set_path.write_text("\n".join(set_lines).rstrip() + "\n", encoding="utf-8")

    notes_lines = [
        f"# {effective.name} Notes",
        "",
        "Generated by `scripts/generate_campaign_sets.py`.",
        "",
        "## Effective Recipe",
        "",
        f"- requested count: {effective.count}",
        f"- raw hints: {', '.join(effective.raw_hints)}",
        f"- subjects: {', '.join(effective.subjects) or 'any'}",
        f"- categories: {', '.join(effective.categories) or 'any'}",
        f"- doc types: {', '.join(effective.doc_types) or 'any'}",
        f"- preferences: {', '.join(effective.preferences) or 'none'}",
        "",
        "## Selected Documents",
        "",
        "| doc_id | subject | category | doc_type | pages | tables | images | font risk | why selected |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for candidate in selected:
        notes_lines.append(
            "| "
            + " | ".join(
                [
                    f"`{candidate.doc_id}`",
                    candidate.subject,
                    candidate.category,
                    candidate.doc_type,
                    str(candidate.page_count or ""),
                    str(candidate.table_candidate_count),
                    str(candidate.image_count),
                    str(candidate.fonts_missing_unicode_map_count),
                    why_selected(candidate, effective),
                ]
            )
            + " |"
        )
    notes_path.write_text("\n".join(notes_lines).rstrip() + "\n", encoding="utf-8")


def why_selected(candidate: Candidate, effective: EffectiveArgs) -> str:
    reasons: list[str] = []
    if candidate.subject in effective.subjects:
        reasons.append(candidate.subject)
    if candidate.category in effective.categories:
        reasons.append(candidate.category)
    if candidate.doc_type in effective.doc_types:
        reasons.append(candidate.doc_type)
    if "native" in effective.preferences and native_signal(candidate):
        reasons.append("native-title signal")
    if candidate.table_candidate_count:
        reasons.append(f"{candidate.table_candidate_count} table candidates")
    if candidate.image_count:
        reasons.append(f"{candidate.image_count} images")
    if candidate.fonts_missing_unicode_map_count:
        reasons.append(f"{candidate.fonts_missing_unicode_map_count} font-map risks")
    return "; ".join(reasons) or "matched filters"


def write_audit(sets_dir: Path, reports_dir: Path, candidates: list[Candidate]) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    by_doc_id = {candidate.doc_id: candidate for candidate in candidates}
    lines = ["# Campaign Set Audit", ""]
    for set_name in list_campaign_sets(sets_dir):
        try:
            doc_ids = read_campaign_set(set_name, sets_dir)
        except Exception as exc:
            lines.extend([f"## {set_name}", "", f"- error: {exc}", ""])
            continue
        selected = [by_doc_id[doc_id] for doc_id in doc_ids if doc_id in by_doc_id]
        subjects = Counter(candidate.subject for candidate in selected)
        categories = Counter(candidate.category for candidate in selected)
        doc_types = Counter(candidate.doc_type for candidate in selected)
        missing = [doc_id for doc_id in doc_ids if doc_id not in by_doc_id]
        lines.extend(
            [
                f"## {set_name}",
                "",
                f"- rows: {len(doc_ids)}",
                f"- matched profile rows: {len(selected)}",
                f"- missing profile/index rows: {len(missing)}",
                f"- subjects: {dict(sorted(subjects.items()))}",
                f"- categories: {dict(sorted(categories.items()))}",
                f"- doc_types: {dict(sorted(doc_types.items()))}",
                "",
            ]
        )
        if missing:
            lines.append("Missing:")
            lines.extend(f"- `{doc_id}`" for doc_id in missing[:20])
            if len(missing) > 20:
                lines.append(f"- ... {len(missing) - 20} more")
            lines.append("")
    (reports_dir / "campaign-set-audit.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
