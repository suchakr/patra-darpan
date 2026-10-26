#!/usr/bin/env python3
"""Build a standalone ontology/entity-only release candidate.

The base release is treated as immutable input. Unchanged catalog, chunk,
manifest and vector-build artifacts are copied with their hashes preserved;
only the ontology snapshot and entity projections are regenerated. The
candidate is written under an explicit output root, never to the configured
release root or active-release pointer. An optional Qdrant audit is read-only.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import EntityAdapter, Release, load_release, read_json
from lib.retrieval_entities import (
    ENTITY_EXTRACTOR_VERSION,
    build_summary,
    iter_mentions,
    read_jsonl,
    registry_from_mentions,
)


CHANGED_ARTIFACTS = {"ontology_snapshot", "entity_mentions", "entity_registry"}
RELEASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,127}$")


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
        capture_output=True,
        text=True,
    ).stdout.strip()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def candidate_release_id(base_release_id: str, ontology_version: str) -> str:
    safe_version = re.sub(r"[^A-Za-z0-9_.-]+", "-", ontology_version)
    value = f"{base_release_id}-entity-{safe_version}"
    if len(value) > 128:
        raise ValueError("derived candidate release ID exceeds 128 characters; pass --release-id")
    return value


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _copy_unchanged_artifact(
    *,
    base: Release,
    name: str,
    descriptor: dict[str, Any],
    output_root: Path,
    release_id: str,
) -> dict[str, Any]:
    source = base.artifact_path(name)
    source_hash = sha256_file(source)
    expected_hash = descriptor.get("sha256")
    if expected_hash and source_hash != str(expected_hash):
        raise ValueError(f"base artifact hash mismatch before copy: {name}")
    relative = f"{release_id}/{Path(str(descriptor['path'])).name}"
    destination = output_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied_hash = sha256_file(destination)
    if copied_hash != source_hash:
        raise ValueError(f"copied artifact hash mismatch: {name}")
    copied = copy.deepcopy(descriptor)
    copied.update(path=relative, sha256=copied_hash)
    return copied


def _write_changed_artifact(
    *, output_root: Path, release_id: str, filename: str, payload: bytes
) -> dict[str, str]:
    relative = f"{release_id}/{filename}"
    destination = output_root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return {"path": relative, "sha256": sha256_file(destination)}


def verify_candidate(
    base: Release,
    candidate_path: Path,
    *,
    ontology_id: str,
    ontology_version: str,
    expected_chunk_count: int,
    expected_mention_count: int,
) -> dict[str, Any]:
    candidate = load_release(candidate_path)
    if candidate.corpus_revision != base.corpus_revision:
        raise ValueError("candidate changed the Sanchaya corpus revision")
    if candidate.record.get("source", {}).get("catalog_revision") != base.record.get("source", {}).get("catalog_revision"):
        raise ValueError("candidate changed the catalog revision")
    base_vector = base.record.get("artifacts", {}).get("vector_index") or {}
    candidate_vector = candidate.record.get("artifacts", {}).get("vector_index") or {}
    stable_vector_keys = ("backend", "collection", "dimensions")
    if any(candidate_vector.get(key) != base_vector.get(key) for key in stable_vector_keys):
        raise ValueError("candidate changed vector-index identity")
    if candidate.record.get("metrics", {}).get("chunk_count") != expected_chunk_count:
        raise ValueError("candidate chunk metric differs from the retained chunk artifact")
    if candidate.record.get("metrics", {}).get("vector_point_count") != expected_chunk_count:
        raise ValueError("base vector-point metric does not match the chunk inventory")
    if candidate.record.get("metrics", {}).get("mention_count") != expected_mention_count:
        raise ValueError("candidate mention metric differs from the rebuilt entity projection")
    ontology_record = candidate.record.get("pipeline", {}).get("ontology", {})
    if ontology_record.get("id") != ontology_id or ontology_record.get("version") != ontology_version:
        raise ValueError("candidate release declares the wrong ontology identity")

    unchanged_verified = []
    for name, descriptor in (base.record.get("artifacts") or {}).items():
        if name in CHANGED_ARTIFACTS or not isinstance(descriptor, dict) or not descriptor.get("path"):
            continue
        candidate_descriptor = candidate.record.get("artifacts", {}).get(name) or {}
        source_hash = sha256_file(base.artifact_path(name))
        candidate_hash = sha256_file(candidate.artifact_path(name))
        if candidate_hash != source_hash or candidate_descriptor.get("sha256") != source_hash:
            raise ValueError(f"retained artifact changed during entity-only build: {name}")
        unchanged_verified.append(name)

    EntityAdapter(candidate, candidate.artifact_path("ontology_snapshot"))
    return {
        "candidate_release_id": candidate.release_id,
        "base_release_id": base.release_id,
        "ontology": f"{ontology_id} {ontology_version}",
        "chunk_count": expected_chunk_count,
        "mention_count": expected_mention_count,
        "unchanged_artifacts_verified": sorted(unchanged_verified),
        "vector_collection": candidate.record["artifacts"]["vector_index"]["collection"],
        "vector_inventory_audit": "not-run (candidate build performs no Qdrant calls)",
        "active_pointer_written": False,
    }


def build_candidate(
    *,
    base_release_path: Path,
    ontology_path: Path,
    output_root: Path,
    release_id: str | None = None,
    patra_darpan_commit: str | None = None,
    qdrant_url: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    base = load_release(base_release_path)
    ontology_path = ontology_path.expanduser().resolve()
    output_root = output_root.expanduser().resolve()
    ontology = read_json(ontology_path)
    ontology_id = str(ontology.get("ontology_id") or "")
    ontology_version = str(ontology.get("version") or "")
    if not ontology_id or not ontology_version:
        raise ValueError("target ontology must declare ontology_id and version")
    base_ontology = read_json(base.artifact_path("ontology_snapshot"))
    previous = base.record.get("pipeline", {}).get("ontology", {})
    if ontology_id != str(previous.get("id") or ""):
        raise ValueError("target ontology ID differs from the base release")
    if ontology_version == str(previous.get("version") or ""):
        raise ValueError("target ontology version is unchanged from the base release")
    if str(base_ontology.get("version") or "") != str(previous.get("version") or ""):
        raise ValueError("base ontology artifact and release metadata disagree")

    chunks = list(read_jsonl(base.artifact_path("chunks")))
    if not chunks:
        raise ValueError("base release has an empty chunk inventory")
    base_metrics = base.record.get("metrics") or {}
    if int(base_metrics.get("chunk_count") or -1) != len(chunks):
        raise ValueError("base chunk metric differs from its chunk artifact")
    if int(base_metrics.get("vector_point_count") or -1) != len(chunks):
        raise ValueError("base vector-point count differs from the retained chunk inventory")

    corpus_revision = base.corpus_revision
    mentions = list(iter_mentions(chunks, ontology, corpus_revision=corpus_revision))
    registry = registry_from_mentions(ontology, mentions, corpus_revision=corpus_revision)
    summary = build_summary(
        ontology=ontology,
        chunks_seen=len(chunks),
        mentions=mentions,
        registry=registry,
        corpus_revision=corpus_revision,
    )

    candidate_id = release_id or candidate_release_id(base.release_id, ontology_version)
    if not RELEASE_ID_PATTERN.fullmatch(candidate_id):
        raise ValueError("candidate release ID must use 3-128 letters, digits, dot, underscore or hyphen")
    if candidate_id == base.release_id:
        raise ValueError("candidate release ID must differ from the base release")
    candidate_dir = output_root / candidate_id
    if candidate_dir.exists():
        raise FileExistsError(f"candidate output already exists: {candidate_dir}")
    if is_within(candidate_dir, base.root):
        raise ValueError("build-only output must be outside the base release root; refusing to stage")
    output_root.mkdir(parents=True, exist_ok=True)
    candidate_dir.mkdir()

    try:
        record = copy.deepcopy(base.record)
        record["release_id"] = candidate_id
        record["status"] = "ready"
        record["created_at"] = utc_now()
        record["built_at"] = record["created_at"]
        record["notes"] = (
            f"Build-only entity refresh from {base.release_id}; chunks, catalog and vector index retained. "
            "This standalone candidate is not staged or activated."
        )
        revision = patra_darpan_commit or git_revision(ROOT)
        record.setdefault("source", {})["patra_darpan_commit"] = revision
        ontology_revision = str(ontology_path)
        try:
            ontology_revision = str(ontology_path.relative_to(ROOT))
        except ValueError:
            pass
        record.setdefault("pipeline", {})["ontology"] = {
            "id": ontology_id,
            "version": ontology_version,
            "revision": ontology_revision,
        }
        record["pipeline"]["entity_extractor"] = {
            "id": "starter-gazetteer",
            "version": ENTITY_EXTRACTOR_VERSION,
            "revision": f"patra-darpan:{revision}",
        }
        record.setdefault("metrics", {})["mention_count"] = int(summary["mention_count"])
        record["metrics"]["entity_document_count"] = int(summary["document_count_with_mentions"])

        artifacts: dict[str, Any] = {}
        for name, descriptor in (base.record.get("artifacts") or {}).items():
            if not isinstance(descriptor, dict) or not descriptor.get("path"):
                artifacts[name] = copy.deepcopy(descriptor)
                continue
            if name in CHANGED_ARTIFACTS:
                continue
            artifacts[name] = _copy_unchanged_artifact(
                base=base,
                name=name,
                descriptor=descriptor,
                output_root=output_root,
                release_id=candidate_id,
            )

        ontology_payload = json.dumps(ontology, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        artifacts["ontology_snapshot"] = _write_changed_artifact(
            output_root=output_root,
            release_id=candidate_id,
            filename="ontology.json",
            payload=ontology_payload,
        )
        mentions_payload = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in mentions
        ).encode("utf-8")
        registry_payload = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in registry
        ).encode("utf-8")
        artifacts["entity_mentions"] = _write_changed_artifact(
            output_root=output_root,
            release_id=candidate_id,
            filename="entity-mentions.jsonl",
            payload=mentions_payload,
        )
        artifacts["entity_registry"] = _write_changed_artifact(
            output_root=output_root,
            release_id=candidate_id,
            filename="entity-registry.jsonl",
            payload=registry_payload,
        )
        record["artifacts"] = artifacts

        if qdrant_url:
            from scripts.refresh_retrieval_release import verify_existing_vectors

            audit = verify_existing_vectors(
                qdrant_url=qdrant_url,
                collection=str(artifacts["vector_index"]["collection"]),
                chunks=chunks,
                dimensions=int(artifacts["vector_index"]["dimensions"]),
            )
            record["artifacts"]["vector_index"].update(
                reused_from_release=base.release_id,
                reuse_verified=True,
                reuse_basis={
                    "chunk_key": audit["chunk_key"],
                    "chunk_inventory_sha256": audit["chunk_inventory_sha256"],
                    "point_count": audit["point_count"],
                },
            )

        release_path = candidate_dir / "release.json"
        write_json(release_path, record)
        verification = verify_candidate(
            base,
            release_path,
            ontology_id=ontology_id,
            ontology_version=ontology_version,
            expected_chunk_count=len(chunks),
            expected_mention_count=len(mentions),
        )
        verification.update(
            release_path=str(release_path),
            entity_extractor_version=ENTITY_EXTRACTOR_VERSION,
            qdrant_audit_performed=bool(qdrant_url),
            active_pointer_written=False,
        )
        return release_path, verification
    except Exception:
        shutil.rmtree(candidate_dir, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-release", type=Path, required=True, help="verified release.json or active-release.json")
    parser.add_argument("--ontology", type=Path, required=True, help="new versioned ontology JSON")
    parser.add_argument("--output-root", type=Path, required=True, help="standalone candidate root outside the release root")
    parser.add_argument("--release-id")
    parser.add_argument("--qdrant-url", help="optional Qdrant URL for a read-only collection/point inventory audit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    release_path, result = build_candidate(
        base_release_path=args.base_release,
        ontology_path=args.ontology,
        output_root=args.output_root,
        release_id=args.release_id,
        qdrant_url=args.qdrant_url,
    )
    print(json.dumps({"status": "build-only-verified", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
