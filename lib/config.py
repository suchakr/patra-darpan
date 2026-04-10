from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CORPUS_DIR = PROJECT_ROOT / "corpus"

BUILD_DIR = PROJECT_ROOT / ".build~"
EXPORTS_DIR = PROJECT_ROOT / "exports"
REPORTS_DIR = PROJECT_ROOT / "reports"
REFERENCE_LEGACY_DIR = PROJECT_ROOT / "reference" / "legacy"
SCRATCH_DIR = PROJECT_ROOT / "scratch~"

SQLITE_PATH = BUILD_DIR / "spasta-corpus.sqlite"
SCHEMA_PATH = PROJECT_ROOT / "lib" / "schema.sql"

IJHS_TSV_PATH = CORPUS_DIR / "ijhs.tsv"
CURATED_PDFS_TSV_PATH = CORPUS_DIR / "curated-pdfs.tsv"
CURATED_LINKS_TSV_PATH = CORPUS_DIR / "curated-links.tsv"
CAHC_AUTHORED_REGISTRY_PATH = CORPUS_DIR / "cahc_authored_registry.txt"
CAHC_PDF_MIRRORS_TSV_PATH = CORPUS_DIR / "cahc-pdf-mirrors.tsv"


def _is_shared_asset_root(path: Path) -> bool:
    return (path / "ijhs").exists() and (path / "other").exists()


def resolve_shared_asset_root(project_root: Path | None = None) -> Path:
    if project_root is None:
        project_root = PROJECT_ROOT

    corpus_dir = project_root / "corpus"
    candidates: list[Path] = []
    env_path = os.getenv("SHARED_ASSET_ROOT")
    if env_path:
        candidates.append(Path(env_path).expanduser())

    # Post-merge main-checkout case: the shared PDFs live directly under this repo.
    candidates.append(corpus_dir)

    # Worktree / sibling-checkout case used during the spasta-corpus transition.
    candidates.append(project_root.parent / "patra-darpan" / "corpus")

    seen: set[Path] = set()
    normalized_candidates: list[Path] = []
    for candidate in candidates:
        normalized = candidate.expanduser()
        if normalized not in seen:
            normalized_candidates.append(normalized)
            seen.add(normalized)

    for candidate in normalized_candidates:
        if _is_shared_asset_root(candidate):
            return candidate

    # Fall back to the highest-priority candidate so callers can still report a
    # useful missing-path warning.
    return normalized_candidates[0]


SHARED_ASSET_ROOT = resolve_shared_asset_root()
SHARED_IJHS_PDF_ROOT = SHARED_ASSET_ROOT / "ijhs"
SHARED_OTHER_PDF_ROOT = SHARED_ASSET_ROOT / "other"


def ensure_runtime_dirs() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
