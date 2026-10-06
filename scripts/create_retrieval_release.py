#!/usr/bin/env python3
"""Materialize a self-describing read-only retrieval release.

The builders write working artifacts under ``.local/retrieval``.  This command
copies the reviewed inputs into one immutable release directory, records the
source and pipeline revisions, and atomically updates ``active-release.json``.
The online adapters read only this release record and its files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_catalog import CATALOG_SCHEMA_VERSION, build_retrieval_catalog


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_revision(root: Path) -> str:
    trusted_root = root.resolve()
    return subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={trusted_root}",
            "-C",
            str(trusted_root),
            "rev-parse",
            "HEAD",
        ],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def git_origin(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return str(root)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def count_jsonl(path: Path) -> int:
    return sum(1 for line in path.open("r", encoding="utf-8") if line.strip())


def require_file(path: Path) -> Path:
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def artifact(record_path: str, source: Path, destination: Path) -> dict[str, str]:
    shutil.copy2(require_file(source), destination)
    return file_artifact(record_path, destination)


def file_artifact(record_path: str, path: Path) -> dict[str, str]:
    return {"path": record_path, "sha256": sha256_file(require_file(path))}


def default_catalog_path() -> Path:
    configured = os.getenv("RETRIEVAL_CANONICAL_CATALOG")
    if configured:
        return Path(configured).expanduser()
    return ROOT.parent / "patra-darpan" / ".build~" / "spasta-corpus.sqlite"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-root", type=Path, default=Path(os.getenv("RETRIEVAL_RELEASE_ROOT", ROOT / ".local/retrieval/releases")))
    parser.add_argument("--sanchaya-root", type=Path, default=Path(os.getenv("SANCHAYA_REPO_ROOT", "/Users/sunder/projects/sanchaya")))
    parser.add_argument("--patra-darpan-root", type=Path, default=ROOT)
    parser.add_argument("--input-manifest", type=Path, default=ROOT / ".local/retrieval/input-manifest.json")
    parser.add_argument(
        "--catalog-sqlite",
        type=Path,
        default=default_catalog_path(),
        help="canonical Patra Darpan SQLite database used for pd:* metadata",
    )
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=ROOT / ".local/retrieval/input-manifest.json",
        help="release-scoped Sanchaya source manifest used for sanchaya:* metadata",
    )
    parser.add_argument("--chunks", type=Path, default=ROOT / ".local/retrieval/chunks.jsonl")
    parser.add_argument("--mentions", type=Path, default=ROOT / ".local/retrieval/entity-mentions.jsonl")
    parser.add_argument("--registry", type=Path, default=ROOT / ".local/retrieval/entity-registry.jsonl")
    parser.add_argument("--chunk-build", type=Path, default=ROOT / ".local/retrieval/chunk-build.json")
    parser.add_argument("--entity-build", type=Path, default=ROOT / ".local/retrieval/entity-build.json")
    parser.add_argument("--vector-run", type=Path, required=True, help="run.json emitted by the vector builder")
    parser.add_argument("--ontology", type=Path, default=ROOT / "ontology/jyotisha-v0.3.json")
    parser.add_argument("--release-id")
    parser.add_argument("--notes", default="Local retrieval release; all online projections are read-only.")
    parser.add_argument("--activate", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def build_record(args: argparse.Namespace, release_id: str, release_dir: Path) -> dict[str, Any]:
    input_manifest = read_json(require_file(args.input_manifest))
    chunk_build = read_json(require_file(args.chunk_build))
    entity_build = read_json(require_file(args.entity_build))
    vector_run = read_json(require_file(args.vector_run))
    sanchaya_commit = str(input_manifest.get("sanchaya", {}).get("commit") or git_revision(args.sanchaya_root))
    if sanchaya_commit != git_revision(args.sanchaya_root):
        raise ValueError("input manifest does not describe current Sanchaya HEAD")
    pd_commit = git_revision(args.patra_darpan_root)

    catalog_source = args.sanchaya_root / "patra-darpan/catalog/corpus-manifest.jsonl"
    catalog_output = release_dir / "retrieval-catalog.sqlite"
    catalog_stats = build_retrieval_catalog(
        args.catalog_sqlite,
        args.source_manifest,
        catalog_output,
        release_id=release_id,
        sanchaya_commit=sanchaya_commit,
        patra_darpan_commit=pd_commit,
    )
    catalog_revision = sha256_file(catalog_output)
    created_at = utc_now()
    artifacts = {
        "input_manifest": artifact(
            f"{release_id}/input-manifest.json",
            args.input_manifest,
            release_dir / "input-manifest.json",
        ),
        "retrieval_catalog": file_artifact(f"{release_id}/retrieval-catalog.sqlite", catalog_output),
        "corpus_manifest": artifact(f"{release_id}/corpus-manifest.jsonl", catalog_source, release_dir / "corpus-manifest.jsonl"),
        "chunks": artifact(f"{release_id}/chunks.jsonl", args.chunks, release_dir / "chunks.jsonl"),
        "entity_mentions": artifact(f"{release_id}/entity-mentions.jsonl", args.mentions, release_dir / "entity-mentions.jsonl"),
        "entity_registry": artifact(f"{release_id}/entity-registry.jsonl", args.registry, release_dir / "entity-registry.jsonl"),
        "lexical_index": {
            "backend": "zoekt",
            "repository": "sanchaya",
            "corpus_commit": sanchaya_commit,
        },
        "vector_index": {
            "backend": "qdrant",
            "collection": str(vector_run.get("collection") or ""),
            "dimensions": int(vector_run.get("dimensions") or 0),
        },
    }
    for key in ("reused_from_release", "reuse_verified", "reuse_basis"):
        if key in vector_run:
            artifacts["vector_index"][key] = vector_run[key]
    if not artifacts["vector_index"]["collection"] or not artifacts["vector_index"]["dimensions"]:
        raise ValueError("vector run does not contain collection and dimensions")

    pipeline = {
        "source_scope": {
            "paper_scope": str(input_manifest.get("selection", {}).get("paper_scope") or "unknown"),
            "sanchaya_scope": str(input_manifest.get("selection", {}).get("sanchaya_scope") or "unknown"),
            "source_count": len(input_manifest.get("sources") or []),
        },
        "ontology": {
            "id": "jyotisha",
            "version": "0.3.0",
            "revision": str(args.ontology.relative_to(ROOT)),
        },
        "catalog": {
            "id": "sqlite-composite-release-catalog",
            "version": CATALOG_SCHEMA_VERSION,
            "revision": catalog_revision,
        },
        "chunker": {
            "id": "structure-aware",
            "version": str(chunk_build.get("chunker_version") or "unknown"),
            "revision": "patra-darpan:working-tree",
        },
        "embedding": {
            "model": str(vector_run.get("model") or ""),
            "revision": "sentence-transformers runtime",
            "dimensions": int(vector_run.get("dimensions") or 0),
            "normalized": bool(vector_run.get("normalized", True)),
        },
        "entity_extractor": {
            "id": "starter-gazetteer",
            "version": str(entity_build.get("extractor_version") or "unknown"),
            "revision": "patra-darpan:working-tree",
        },
    }
    return {
        "schema_version": "retrieval.release.v1",
        "release_id": release_id,
        "status": "ready",
        "created_at": created_at,
        "built_at": created_at,
        "source": {
            "sanchaya_repo": git_origin(args.sanchaya_root),
            "sanchaya_commit": sanchaya_commit,
            "patra_darpan_repo": git_origin(args.patra_darpan_root),
            "patra_darpan_commit": pd_commit,
            "corpus_manifest_sha256": sha256_file(catalog_source),
            "catalog_revision": catalog_revision,
        },
        "pipeline": pipeline,
        "artifacts": artifacts,
        "metrics": {
            "document_count": int(input_manifest.get("selection", {}).get("paper_count", 0)) + int(input_manifest.get("selection", {}).get("probe_count", 0)),
            "catalog_document_count": int(catalog_stats["document_count"]),
            "catalog_patra_darpan_document_count": int(catalog_stats["patra_darpan_document_count"]),
            "catalog_sanchaya_document_count": int(catalog_stats["sanchaya_document_count"]),
            "catalog_indexed_document_count": int(catalog_stats["indexed_document_count"]),
            "catalog_metadata_only_document_count": int(catalog_stats["metadata_only_document_count"]),
            "chunk_count": int(chunk_build.get("chunk_count", count_jsonl(args.chunks))),
            "mention_count": int(entity_build.get("mention_count", count_jsonl(args.mentions))),
            "entity_document_count": int(entity_build.get("document_count_with_mentions", 0)),
            "vector_point_count": int(vector_run.get("chunk_count", 0)),
        },
        "notes": args.notes,
    }


def main() -> int:
    args = parse_args()
    sanchaya_root = args.sanchaya_root.expanduser().resolve()
    args.sanchaya_root = sanchaya_root
    args.patra_darpan_root = args.patra_darpan_root.expanduser().resolve()
    args.catalog_sqlite = args.catalog_sqlite.expanduser().resolve()
    args.source_manifest = args.source_manifest.expanduser().resolve()
    args.release_root = args.release_root.expanduser().resolve()
    vector_run = read_json(require_file(args.vector_run.expanduser().resolve()))
    sanchaya_commit = str(read_json(require_file(args.input_manifest)).get("sanchaya", {}).get("commit") or git_revision(sanchaya_root))
    collection = str(vector_run.get("collection") or "vector")
    release_id = args.release_id or f"local-{sanchaya_commit[:8]}-{collection.removeprefix('sanchaya-vector-')[:32]}"
    release_dir = args.release_root / release_id
    if release_dir.exists():
        raise FileExistsError(f"release already exists: {release_dir}")
    args.release_root.mkdir(parents=True, exist_ok=True)
    release_dir.mkdir(parents=True)
    try:
        record = build_record(args, release_id, release_dir)
        release_json = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
        (release_dir / "release.json").write_text(release_json, encoding="utf-8")
        if args.activate:
            active_tmp = args.release_root / ".active-release.json.tmp"
            active_tmp.write_text(release_json, encoding="utf-8")
            os.replace(active_tmp, args.release_root / "active-release.json")
    except Exception:
        shutil.rmtree(release_dir, ignore_errors=True)
        raise
    print(json.dumps({"release_id": release_id, "release_dir": str(release_dir), "active": bool(args.activate)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
