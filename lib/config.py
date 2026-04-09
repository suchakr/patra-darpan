from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CORPUS_DIR = PROJECT_ROOT / "corpus"
SHARED_ASSET_ROOT = Path("/Users/sunder/projects/patra-darpan/corpus")
SHARED_IJHS_PDF_ROOT = SHARED_ASSET_ROOT / "ijhs"
SHARED_OTHER_PDF_ROOT = SHARED_ASSET_ROOT / "other"

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


def ensure_runtime_dirs() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    REFERENCE_LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
