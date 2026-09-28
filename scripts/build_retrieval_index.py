#!/usr/bin/env python3
"""Build one reproducible retrieval release from a Sanchaya source scope.

This is the one-shot indexer used by the Compose builder.  The MCP runtime is
read-only and starts after this job has materialized chunks, entity JSONL, the
E5/Qdrant collection, and an active release record.  Re-running the command
for an already active release is a no-op; ``--force`` deliberately rebuilds
the deterministic collection and release.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_retrieval_chunks import build_chunks
from scripts.build_retrieval_entities import build_summary, iter_mentions, registry_from_mentions
from scripts.prepare_retrieval_manifest import build_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sanchaya-root",
        type=Path,
        default=Path(os.environ.get("SANCHAYA_REPO_ROOT", "~/projects/sanchaya")).expanduser(),
    )
    parser.add_argument(
        "--patra-darpan-root",
        type=Path,
        default=Path(os.environ.get("PATRA_DARPAN_ROOT", ROOT)),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path(os.environ.get("RETRIEVAL_BUILD_ROOT", ROOT / ".local/retrieval")),
    )
    parser.add_argument(
        "--release-root",
        type=Path,
        default=Path(os.environ.get("RETRIEVAL_RELEASE_ROOT", ROOT / ".local/retrieval/releases")),
    )
    parser.add_argument(
        "--catalog-sqlite",
        type=Path,
        default=Path(
            os.environ.get(
                "RETRIEVAL_CANONICAL_CATALOG",
                ROOT.parent / "patra-darpan" / ".build~" / "spasta-corpus.sqlite",
            )
        ),
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=Path(os.environ.get("RETRIEVAL_ONTOLOGY_PATH", ROOT / "ontology/jyotisha-v0.3.json")),
    )
    parser.add_argument(
        "--audit-set",
        type=Path,
        default=ROOT / "decode-lab" / "sets" / "audit-set.txt",
    )
    parser.add_argument(
        "--paper-scope",
        choices=("audit", "all"),
        default=os.environ.get("RETRIEVAL_PAPER_SCOPE", "all"),
    )
    parser.add_argument(
        "--sanchaya-scope",
        choices=("probe", "jyotisham", "all"),
        default=os.environ.get("RETRIEVAL_SANCHAYA_SCOPE", "jyotisham"),
    )
    parser.add_argument("--model", default=os.environ.get("RETRIEVAL_VECTOR_MODEL", "intfloat/multilingual-e5-base"))
    parser.add_argument("--collection", default=os.environ.get("RETRIEVAL_VECTOR_COLLECTION"))
    parser.add_argument("--qdrant-url", default=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("RETRIEVAL_VECTOR_BATCH_SIZE", "32")))
    parser.add_argument("--device", default=os.environ.get("RETRIEVAL_EMBEDDING_DEVICE"))
    parser.add_argument("--target-tokens", type=int, default=384)
    parser.add_argument("--max-tokens", type=int, default=480)
    parser.add_argument("--overlap-tokens", type=int, default=48)
    parser.add_argument("--release-id")
    parser.add_argument("--force", action="store_true", help="rebuild an existing deterministic release")
    parser.add_argument("--no-activate", action="store_true")
    return parser.parse_args()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def safe_collection_name(model: str, scope: str, commit: str) -> str:
    model_part = "e5" if "e5" in model.casefold() else "vector"
    return f"sanchaya-vector-{model_part}-{scope}-{commit[:8]}"


def run_vector_build(args: argparse.Namespace, *, chunks: Path, output_dir: Path, collection: str) -> Path:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_retrieval_vector_build.py"),
        "--chunks",
        str(chunks),
        "--model",
        args.model,
        "--collection",
        collection,
        "--qdrant-url",
        args.qdrant_url,
        "--batch-size",
        str(args.batch_size),
        "--output-dir",
        str(output_dir),
        "--recreate",
    ]
    if args.device:
        command.extend(["--device", args.device])
    subprocess.run(command, check=True)
    return output_dir / collection / "run.json"


def run_release_build(args: argparse.Namespace, *, manifest: Path, chunks: Path, chunk_build: Path, mentions: Path, registry: Path, entity_build: Path, vector_run: Path, release_id: str) -> None:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "create_retrieval_release.py"),
        "--sanchaya-root",
        str(args.sanchaya_root),
        "--patra-darpan-root",
        str(args.patra_darpan_root),
        "--release-root",
        str(args.release_root),
        "--catalog-sqlite",
        str(args.catalog_sqlite),
        "--input-manifest",
        str(manifest),
        "--source-manifest",
        str(manifest),
        "--chunks",
        str(chunks),
        "--mentions",
        str(mentions),
        "--registry",
        str(registry),
        "--chunk-build",
        str(chunk_build),
        "--entity-build",
        str(entity_build),
        "--vector-run",
        str(vector_run),
        "--ontology",
        str(args.ontology),
        "--release-id",
        release_id,
    ]
    if args.no_activate:
        command.append("--no-activate")
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    for path_name in ("sanchaya_root", "patra_darpan_root", "work_root", "release_root", "catalog_sqlite", "ontology", "audit_set"):
        value = getattr(args, path_name)
        if isinstance(value, Path):
            setattr(args, path_name, value.expanduser().resolve())
    args.work_root.mkdir(parents=True, exist_ok=True)

    manifest_value = build_manifest(
        args.sanchaya_root,
        args.audit_set,
        paper_scope=args.paper_scope,
        sanchaya_scope=args.sanchaya_scope,
    )
    sanchaya_commit = str(manifest_value["sanchaya"]["commit"])
    # Keep the release suffix aligned with the repository's conventional short
    # revision (and with the releases produced before this orchestrator was
    # added).  The vector collection keeps its eight-character suffix because
    # it is an implementation name, while the release ID is the human-facing
    # publication handle.
    release_id = args.release_id or f"retrieval-{args.sanchaya_scope}-{args.paper_scope}-{sanchaya_commit[:7]}"
    release_dir = args.release_root / release_id
    active_path = args.release_root / "active-release.json"
    active = json.loads(active_path.read_text(encoding="utf-8")) if active_path.is_file() else {}
    if release_dir.exists() and (release_dir / "release.json").is_file() and not args.force:
        if active.get("release_id") == release_id:
            print(json.dumps({"release_id": release_id, "status": "reused", "active": True}, indent=2))
            return 0
        raise FileExistsError(f"release exists but is not active: {release_dir}; use --force only for a deliberate rebuild")
    if release_dir.exists() and args.force:
        if active.get("release_id") == release_id:
            raise RuntimeError(
                f"refusing to delete active release {release_id}; use a new --release-id for a staged rebuild"
            )
        shutil.rmtree(release_dir)

    manifest_path = args.work_root / "input-manifest.json"
    chunks_path = args.work_root / "chunks.jsonl"
    chunk_build_path = args.work_root / "chunk-build.json"
    mentions_path = args.work_root / "entity-mentions.jsonl"
    registry_path = args.work_root / "entity-registry.jsonl"
    entity_build_path = args.work_root / "entity-build.json"
    write_json(manifest_path, manifest_value)

    chunks, chunk_summary = build_chunks(
        manifest_value,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    write_jsonl(chunks_path, chunks)
    write_json(chunk_build_path, chunk_summary)

    ontology = json.loads(args.ontology.read_text(encoding="utf-8"))
    mentions = list(iter_mentions(chunks, ontology, corpus_revision=sanchaya_commit))
    registry = registry_from_mentions(ontology, mentions, corpus_revision=sanchaya_commit)
    write_jsonl(mentions_path, mentions)
    write_jsonl(registry_path, registry)
    write_json(
        entity_build_path,
        build_summary(
            ontology=ontology,
            chunks_seen=len(chunks),
            mentions=mentions,
            registry=registry,
            corpus_revision=sanchaya_commit,
        ),
    )

    collection = args.collection or safe_collection_name(args.model, args.sanchaya_scope, sanchaya_commit)
    vector_run = run_vector_build(args, chunks=chunks_path, output_dir=args.work_root / "runs", collection=collection)
    run_release_build(
        args,
        manifest=manifest_path,
        chunks=chunks_path,
        chunk_build=chunk_build_path,
        mentions=mentions_path,
        registry=registry_path,
        entity_build=entity_build_path,
        vector_run=vector_run,
        release_id=release_id,
    )
    print(
        json.dumps(
            {
                "release_id": release_id,
                "status": "ready",
                "paper_scope": args.paper_scope,
                "sanchaya_scope": args.sanchaya_scope,
                "source_count": len(manifest_value["sources"]),
                "chunk_count": len(chunks),
                "mention_count": len(mentions),
                "vector_collection": collection,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
