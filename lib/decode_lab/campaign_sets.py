from __future__ import annotations

from pathlib import Path

from lib.config import PROJECT_ROOT


SETS_DIR = PROJECT_ROOT / "decode-lab" / "sets"
DEFAULT_CAMPAIGN_SET = "micro-5"


def campaign_set_path(name: str, sets_dir: Path = SETS_DIR) -> Path:
    candidate = Path(name)
    if candidate.suffix:
        return candidate if candidate.is_absolute() else sets_dir / candidate
    return sets_dir / f"{name}.txt"


def read_campaign_set(name: str, sets_dir: Path = SETS_DIR) -> list[str]:
    path = campaign_set_path(name, sets_dir)
    if not path.exists():
        available = ", ".join(list_campaign_sets(sets_dir)) or "(none)"
        raise FileNotFoundError(
            f"Campaign set not found: {name} ({path}). Available sets: {available}"
        )

    doc_ids: list[str] = []
    seen: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        doc_id = line.split("#", 1)[0].strip()
        if not doc_id:
            continue
        if doc_id in seen:
            raise ValueError(f"Duplicate doc_id {doc_id!r} in {path}:{line_number}")
        seen.add(doc_id)
        doc_ids.append(doc_id)

    if not doc_ids:
        raise ValueError(f"Campaign set {name!r} has no doc_id entries: {path}")
    return doc_ids


def list_campaign_sets(sets_dir: Path = SETS_DIR) -> list[str]:
    if not sets_dir.exists():
        return []
    return sorted(path.stem for path in sets_dir.glob("*.txt"))


def resolve_doc_selection(
    *,
    set_names: list[str] | None,
    doc_ids: list[str] | None,
    default_set: str = DEFAULT_CAMPAIGN_SET,
) -> tuple[list[str], list[str]]:
    names = set_names or []
    explicit_doc_ids = doc_ids or []
    if not names and not explicit_doc_ids:
        names = [default_set]

    selected: list[str] = []
    seen: set[str] = set()
    resolved_sets: list[str] = []

    for name in names:
        resolved_sets.append(name)
        for doc_id in read_campaign_set(name):
            if doc_id not in seen:
                selected.append(doc_id)
                seen.add(doc_id)

    for doc_id in explicit_doc_ids:
        if doc_id not in seen:
            selected.append(doc_id)
            seen.add(doc_id)

    return selected, resolved_sets
