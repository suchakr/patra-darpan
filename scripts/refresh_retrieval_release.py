#!/usr/bin/env python3
"""Refresh release provenance without rebuilding chunks or embeddings.

This command is for a narrow but important case: the selected source bytes are
unchanged, but the Sanchaya Git revision (and therefore the lexical/catalog
provenance) has moved.  It verifies the selected source hashes, rewrites only
the entity-artifact revision fields, audits the existing Qdrant payload keys,
and assembles a new immutable release.  It never calls the vector builder and
never deletes or recreates a Qdrant collection.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import load_release


CHUNK_KEY_FIELDS = ("chunk_id", "content_sha256", "repo_path", "logical_location")


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"expected JSON object at {path}:{line_no}")
            rows.append(value)
    return rows


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


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


def require_clean_checkout(root: Path) -> None:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root.resolve()}",
            "-C",
            str(root.resolve()),
            "status",
            "--porcelain",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    if result.stdout.strip():
        raise RuntimeError(f"Sanchaya checkout is not clean: {root}")


def source_path(sanchaya_root: Path, repo_path: str) -> Path:
    relative = Path(repo_path)
    if relative.is_absolute() or "\\" in repo_path or ".." in relative.parts:
        raise ValueError(f"manifest path is not a safe repository-relative path: {repo_path!r}")
    root = sanchaya_root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"manifest path escapes Sanchaya root: {repo_path!r}") from exc
    return candidate


def verify_selected_source_hashes(manifest: dict[str, Any], sanchaya_root: Path) -> dict[str, int]:
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("input manifest has no selected sources")
    checked = 0
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("input manifest contains a non-object source row")
        repo_path = str(source.get("repo_path") or "")
        expected = str(source.get("content_sha256") or "")
        if not repo_path or len(expected) != 64:
            raise ValueError(f"source row lacks repo_path/content_sha256: {source!r}")
        path = source_path(sanchaya_root, repo_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        actual = sha256_file(path)
        if actual != expected:
            raise ValueError(
                f"selected source changed: {repo_path} expected {expected} but found {actual}"
            )
        checked += 1
    return {"source_count": checked, "hash_mismatch_count": 0}


def update_manifest(
    manifest: dict[str, Any],
    *,
    sanchaya_root: Path,
    sanchaya_commit: str,
    corpus_manifest: Path,
) -> dict[str, Any]:
    updated = copy.deepcopy(manifest)
    sanchaya = dict(updated.get("sanchaya") or {})
    sanchaya.update(
        {
            "root": str(sanchaya_root),
            "commit": sanchaya_commit,
            "status": "clean",
            "corpus_manifest_sha256": sha256_file(corpus_manifest),
        }
    )
    updated["sanchaya"] = sanchaya
    updated["generated_at"] = utc_now()
    return updated


def rewrite_corpus_revision(
    rows: Iterable[dict[str, Any]], *, old_revision: str, new_revision: str, label: str
) -> list[dict[str, Any]]:
    rewritten: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=1):
        current = str(row.get("corpus_revision") or "")
        if current != old_revision:
            raise ValueError(
                f"{label} row {row_number} has corpus_revision={current!r}; "
                f"expected active release revision {old_revision!r}"
            )
        updated = dict(row)
        updated["corpus_revision"] = new_revision
        rewritten.append(updated)
    return rewritten


def chunk_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    values = tuple(str(row.get(field) or "") for field in CHUNK_KEY_FIELDS)
    if not all(values):
        raise ValueError(f"chunk row lacks the stable reuse key: {row!r}")
    return values  # type: ignore[return-value]


def chunk_inventory_digest(rows: Iterable[dict[str, Any]]) -> str:
    keys = [chunk_key(row) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("chunk inventory contains duplicate reuse keys")
    chunk_ids = [key[0] for key in keys]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise ValueError("chunk inventory contains duplicate chunk IDs")
    digest = hashlib.sha256()
    for key in sorted(keys):
        digest.update(json.dumps(key, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def point_id_for_chunk(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def vector_size(collection_info: Any) -> int:
    params = getattr(getattr(collection_info, "config", None), "params", None)
    vectors = getattr(params, "vectors", None)
    if isinstance(vectors, dict):
        if "size" in vectors:
            return int(vectors["size"])
        if len(vectors) == 1:
            vectors = next(iter(vectors.values()))
    size = getattr(vectors, "size", None)
    if size is None:
        raise ValueError("Qdrant collection does not expose a vector dimension")
    return int(size)


def vector_distance(collection_info: Any) -> str:
    params = getattr(getattr(collection_info, "config", None), "params", None)
    vectors = getattr(params, "vectors", None)
    if isinstance(vectors, dict) and len(vectors) == 1:
        vectors = next(iter(vectors.values()))
    distance = getattr(vectors, "distance", None)
    return str(getattr(distance, "value", distance) or "unknown").lower()


def verify_existing_vectors(
    *,
    qdrant_url: str,
    collection: str,
    chunks: list[dict[str, Any]],
    dimensions: int,
) -> dict[str, Any]:
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError("metadata-only refresh needs qdrant-client for the reuse audit") from exc

    expected_keys = {chunk_key(row) for row in chunks}
    expected_ids = {point_id_for_chunk(key[0]) for key in expected_keys}
    client = QdrantClient(url=qdrant_url)
    if not client.collection_exists(collection):
        raise RuntimeError(f"Qdrant collection does not exist: {collection}")
    info = client.get_collection(collection)
    observed_dimensions = vector_size(info)
    if observed_dimensions != dimensions:
        raise ValueError(
            f"Qdrant dimension mismatch for {collection}: "
            f"release={dimensions} collection={observed_dimensions}"
        )

    point_ids: set[str] = set()
    observed_keys: set[tuple[str, str, str, str]] = set()
    offset: Any = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            point_ids.add(str(point.id))
            payload = point.payload or {}
            observed_keys.add(chunk_key(payload))
        if next_offset is None:
            break
        offset = next_offset

    if point_ids != expected_ids:
        missing = len(expected_ids - point_ids)
        extra = len(point_ids - expected_ids)
        raise ValueError(f"Qdrant point ID set differs from chunks: missing={missing} extra={extra}")
    if observed_keys != expected_keys:
        missing = len(expected_keys - observed_keys)
        extra = len(observed_keys - expected_keys)
        raise ValueError(f"Qdrant payload key set differs from chunks: missing={missing} extra={extra}")
    if len(point_ids) != len(chunks):
        raise ValueError(f"Qdrant point count differs from chunks: points={len(point_ids)} chunks={len(chunks)}")

    return {
        "chunk_key": ",".join(CHUNK_KEY_FIELDS),
        "chunk_inventory_sha256": chunk_inventory_digest(chunks),
        "point_count": len(point_ids),
        "dimensions": observed_dimensions,
        "distance": vector_distance(info),
    }


def release_id_for_revision(current_id: str, old_revision: str, new_revision: str) -> str:
    short_old = {old_revision[:7], old_revision[:8]}
    prefix, separator, suffix = current_id.rpartition("-")
    if separator and suffix in short_old:
        return f"{prefix}-{new_revision[:7]}"
    return f"{current_id}-refresh-{new_revision[:7]}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-release", type=Path, default=None)
    parser.add_argument(
        "--release-root",
        type=Path,
        default=Path(os.environ.get("RETRIEVAL_RELEASE_ROOT", ROOT / ".local/retrieval/releases")),
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=Path(os.environ.get("RETRIEVAL_BUILD_ROOT", ROOT / ".local/retrieval")),
    )
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
        "--qdrant-url",
        default=os.environ.get("QDRANT_URL", os.environ.get("RETRIEVAL_QDRANT_URL", "http://127.0.0.1:6333")),
    )
    parser.add_argument("--release-id")
    parser.add_argument(
        "--notes",
        default="Metadata-only Sanchaya revision refresh; selected source bytes and Qdrant vectors were equivalence-verified.",
    )
    parser.add_argument("--activate", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args()


def create_release(
    *,
    args: argparse.Namespace,
    release_id: str,
    manifest: Path,
    chunks: Path,
    chunk_build: Path,
    mentions: Path,
    registry: Path,
    entity_build: Path,
    vector_run: Path,
) -> Path:
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
        "--notes",
        args.notes,
        "--no-activate",
    ]
    subprocess.run(command, check=True)
    return args.release_root / release_id / "release.json"


def activate_release(release_root: Path, release_path: Path, expected_current_id: str) -> None:
    active_path = release_root / "active-release.json"
    if active_path.is_file():
        current = read_json(active_path)
        if str(current.get("release_id") or "") != expected_current_id:
            raise RuntimeError("active release changed while refresh was being assembled")
    release_json = release_path.read_text(encoding="utf-8")
    active_tmp = release_root / f".active-release.{os.getpid()}.tmp"
    active_tmp.write_text(release_json, encoding="utf-8")
    os.replace(active_tmp, active_path)


def validate_reused_release(
    release: Any,
    *,
    expected_release_id: str,
    previous_release_id: str,
    sanchaya_revision: str,
    collection: str,
    inventory_sha256: str,
    point_count: int,
) -> None:
    if release.release_id != expected_release_id:
        raise ValueError(
            f"staged release ID mismatch: expected {expected_release_id} found {release.release_id}"
        )
    if release.corpus_revision != sanchaya_revision:
        raise ValueError("staged release does not declare the refreshed Sanchaya revision")
    vector = release.record.get("artifacts", {}).get("vector_index", {})
    if vector.get("collection") != collection:
        raise ValueError("staged release points at a different Qdrant collection")
    if vector.get("reused_from_release") != previous_release_id or vector.get("reuse_verified") is not True:
        raise ValueError("staged release lacks verified vector reuse provenance")
    basis = vector.get("reuse_basis") or {}
    if basis.get("chunk_inventory_sha256") != inventory_sha256 or int(basis.get("point_count") or -1) != point_count:
        raise ValueError("staged release vector reuse proof does not match the current audit")


def main() -> int:
    args = parse_args()
    for name in (
        "release_root",
        "work_root",
        "sanchaya_root",
        "patra_darpan_root",
        "catalog_sqlite",
        "ontology",
    ):
        value = getattr(args, name)
        setattr(args, name, value.expanduser().resolve())
    current_pointer = args.current_release or Path(
        os.environ.get("RETRIEVAL_ACTIVE_RELEASE", args.release_root / "active-release.json")
    )
    current_pointer = current_pointer.expanduser().resolve()
    args.release_root.mkdir(parents=True, exist_ok=True)

    current_release = load_release(current_pointer)
    old_release_id = current_release.release_id
    old_revision = current_release.corpus_revision
    if old_revision == "unknown":
        raise ValueError("active release does not declare a Sanchaya revision")
    old_manifest = read_json(current_release.artifact_path("input_manifest"))
    manifest_revision = str(old_manifest.get("sanchaya", {}).get("commit") or "")
    if manifest_revision != old_revision:
        raise ValueError(
            f"active release/input manifest revision mismatch: release={old_revision} manifest={manifest_revision}"
        )

    require_clean_checkout(args.sanchaya_root)
    new_revision = git_revision(args.sanchaya_root)
    if new_revision == old_revision:
        raise ValueError(f"Sanchaya HEAD is already the active release revision: {new_revision}")

    corpus_manifest = args.sanchaya_root / "patra-darpan/catalog/corpus-manifest.jsonl"
    if not corpus_manifest.is_file():
        raise FileNotFoundError(corpus_manifest)
    source_stats = verify_selected_source_hashes(old_manifest, args.sanchaya_root)
    new_manifest = update_manifest(
        old_manifest,
        sanchaya_root=args.sanchaya_root,
        sanchaya_commit=new_revision,
        corpus_manifest=corpus_manifest,
    )

    old_chunks_path = current_release.artifact_path("chunks")
    old_chunks = read_jsonl(old_chunks_path)
    if not old_chunks:
        raise ValueError("active release has an empty chunk inventory")
    inventory_sha256 = chunk_inventory_digest(old_chunks)
    vector_descriptor = current_release.record.get("artifacts", {}).get("vector_index", {})
    embedding = current_release.record.get("pipeline", {}).get("embedding", {})
    collection = str(vector_descriptor.get("collection") or "")
    dimensions = int(vector_descriptor.get("dimensions") or embedding.get("dimensions") or 0)
    model = str(embedding.get("model") or "")
    if not collection or not dimensions or not model:
        raise ValueError("active release lacks complete vector provenance")
    reuse_audit = verify_existing_vectors(
        qdrant_url=args.qdrant_url,
        collection=collection,
        chunks=old_chunks,
        dimensions=dimensions,
    )

    release_id = args.release_id or release_id_for_revision(old_release_id, old_revision, new_revision)
    release_dir = args.release_root / release_id
    work_dir = args.work_root / "refresh" / release_id
    if release_dir.exists() or work_dir.exists():
        staged_path = release_dir / "release.json"
        if not args.activate or not release_dir.is_dir() or not staged_path.is_file() or not work_dir.is_dir():
            raise FileExistsError(
                f"refresh artifacts already exist; inspect or use the matching staged release: {release_dir}"
            )
        staged_release = load_release(staged_path)
        validate_reused_release(
            staged_release,
            expected_release_id=release_id,
            previous_release_id=old_release_id,
            sanchaya_revision=new_revision,
            collection=collection,
            inventory_sha256=inventory_sha256,
            point_count=reuse_audit["point_count"],
        )
        activate_release(args.release_root, staged_path, old_release_id)
        print(
            json.dumps(
                {
                    "release_id": release_id,
                    "previous_release_id": old_release_id,
                    "sanchaya_revision": new_revision,
                    "active": True,
                    "source_count": source_stats["source_count"],
                    "chunk_count": len(old_chunks),
                    "entity_mention_count": int(
                        current_release.record.get("metrics", {}).get("mention_count", 0)
                    ),
                    "vector_collection": collection,
                    "vector_point_count": reuse_audit["point_count"],
                    "vector_rebuilt": False,
                    "work_dir": str(work_dir),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    work_dir.mkdir(parents=True)

    manifest_path = work_dir / "input-manifest.json"
    chunks_path = work_dir / "chunks.jsonl"
    chunk_build_path = work_dir / "chunk-build.json"
    mentions_path = work_dir / "entity-mentions.jsonl"
    registry_path = work_dir / "entity-registry.jsonl"
    entity_build_path = work_dir / "entity-build.json"
    vector_run_path = work_dir / "vector-run.json"
    write_json(manifest_path, new_manifest)
    shutil.copy2(old_chunks_path, chunks_path)

    old_mentions = read_jsonl(current_release.artifact_path("entity_mentions"))
    old_registry = read_jsonl(current_release.artifact_path("entity_registry"))
    write_jsonl(
        mentions_path,
        rewrite_corpus_revision(
            old_mentions,
            old_revision=old_revision,
            new_revision=new_revision,
            label="entity mention",
        ),
    )
    write_jsonl(
        registry_path,
        rewrite_corpus_revision(
            old_registry,
            old_revision=old_revision,
            new_revision=new_revision,
            label="entity registry",
        ),
    )

    old_chunker = current_release.record.get("pipeline", {}).get("chunker", {})
    old_entity = current_release.record.get("pipeline", {}).get("entity_extractor", {})
    old_metrics = current_release.record.get("metrics", {})
    write_json(
        chunk_build_path,
        {
            "schema_version": "retrieval.chunk-build.v1",
            "chunker_version": str(old_chunker.get("version") or "unknown"),
            "sanchaya_commit": new_revision,
            "source_count": len(new_manifest.get("sources") or []),
            "chunk_count": len(old_chunks),
            "reuse_verified": True,
            "reused_from_release": old_release_id,
            "chunk_inventory_sha256": inventory_sha256,
        },
    )
    write_json(
        entity_build_path,
        {
            "schema_version": "retrieval.entity-build.v1",
            "extractor_version": str(old_entity.get("version") or "unknown"),
            "corpus_revision": new_revision,
            "chunks_seen": len(old_chunks),
            "mention_count": len(old_mentions),
            "document_count_with_mentions": int(old_metrics.get("entity_document_count", 0)),
            "reuse_verified": True,
            "reused_from_release": old_release_id,
        },
    )
    write_json(
        vector_run_path,
        {
            "schema_version": "retrieval.vector-build.v1",
            "created_at": utc_now(),
            "model": model,
            "collection": collection,
            "qdrant_url": args.qdrant_url,
            "chunks_path": str(chunks_path),
            "chunks_sha256": sha256_file(chunks_path),
            "full_chunk_count": len(old_chunks),
            "chunk_count": len(old_chunks),
            "dimensions": dimensions,
            "normalized": bool(embedding.get("normalized", True)),
            "reused_from_release": old_release_id,
            "reuse_verified": True,
            "reuse_basis": {
                "chunk_key": reuse_audit["chunk_key"],
                "chunk_inventory_sha256": reuse_audit["chunk_inventory_sha256"],
                "point_count": reuse_audit["point_count"],
            },
        },
    )

    new_release_path = create_release(
        args=args,
        release_id=release_id,
        manifest=manifest_path,
        chunks=chunks_path,
        chunk_build=chunk_build_path,
        mentions=mentions_path,
        registry=registry_path,
        entity_build=entity_build_path,
        vector_run=vector_run_path,
    )
    # Validate every copied file and the release shape before changing the
    # active pointer.  The old release remains untouched on any failure.
    new_release = load_release(new_release_path)
    validate_reused_release(
        new_release,
        expected_release_id=release_id,
        previous_release_id=old_release_id,
        sanchaya_revision=new_revision,
        collection=collection,
        inventory_sha256=inventory_sha256,
        point_count=reuse_audit["point_count"],
    )
    if args.activate:
        activate_release(args.release_root, new_release_path, old_release_id)

    print(
        json.dumps(
            {
                "release_id": release_id,
                "previous_release_id": old_release_id,
                "sanchaya_revision": new_revision,
                "active": bool(args.activate),
                "source_count": source_stats["source_count"],
                "chunk_count": len(old_chunks),
                "entity_mention_count": len(old_mentions),
                "vector_collection": collection,
                "vector_point_count": reuse_audit["point_count"],
                "vector_rebuilt": False,
                "work_dir": str(work_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
