#!/usr/bin/env python3
"""Embed the frozen chunk inventory into one isolated local Qdrant collection.

The heavy dependencies are intentionally optional.  Install them in the
bakeoff environment (for example, ``uv run --with sentence-transformers
--with qdrant-client ...``); importing this script or requesting ``--help``
does not download a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_chunks(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not row.get("chunk_id"):
                raise ValueError(f"invalid chunk row at {path}:{line_no}")
            rows.append(row)
    if not rows:
        raise ValueError(f"chunk inventory is empty: {path}")
    return rows


def model_text(model_name: str, text: str) -> str:
    """Apply the documented input prefix for E5; other candidates use raw text."""

    if "e5" in model_name.lower():
        return "passage: " + text
    return text


def collection_name(model_name: str) -> str:
    safe = "".join(char.lower() if char.isalnum() else "_" for char in model_name).strip("_")
    return "iscls_" + safe[:48]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=ROOT / ".local/iscls-bakeoff/chunks.jsonl")
    parser.add_argument("--model", default="intfloat/multilingual-e5-base")
    parser.add_argument("--collection", help="Override the deterministic collection name")
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".local/iscls-bakeoff/runs")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate this candidate collection")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "Local vector build needs optional dependencies; install "
            "sentence-transformers and qdrant-client in the bakeoff environment."
        ) from exc

    chunks = load_chunks(args.chunks)
    started = time.monotonic()
    model = SentenceTransformer(args.model, device=args.device)
    texts = [model_text(args.model, str(chunk["embed_text"])) for chunk in chunks]
    vectors = model.encode(
        texts,
        batch_size=args.batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    dimension = int(vectors.shape[1])
    collection = args.collection or collection_name(args.model)
    client = QdrantClient(url=args.qdrant_url)
    if args.recreate and client.collection_exists(collection):
        client.delete_collection(collection)
    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=qmodels.VectorParams(size=dimension, distance=qmodels.Distance.COSINE),
        )

    points = []
    for chunk, vector in zip(chunks, vectors, strict=True):
        payload = {
            "chunk_id": chunk["chunk_id"],
            "source_id": chunk["source_id"],
            "document_id": chunk["document_id"],
            "source_kind": chunk.get("source_kind"),
            "repo_path": chunk["repo_path"],
            "heading_path": chunk.get("heading_path", []),
            "logical_location": chunk["logical_location"],
            "content_sha256": chunk["content_sha256"],
            "chunker_version": chunk["chunker_version"],
            "script_counts": chunk.get("script_counts", {}),
        }
        points.append(
            qmodels.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, str(chunk["chunk_id"]))),
                vector=vector.tolist(),
                payload=payload,
            )
        )
    for start in range(0, len(points), args.batch_size):
        client.upsert(collection_name=collection, points=points[start : start + args.batch_size], wait=True)

    run_dir = args.output_dir / collection
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": "iscls.vector-build.v1",
        "created_at": utc_now(),
        "model": args.model,
        "collection": collection,
        "qdrant_url": args.qdrant_url,
        "chunks_path": str(args.chunks),
        "chunks_sha256": file_sha256(args.chunks),
        "chunk_count": len(chunks),
        "dimensions": dimension,
        "normalized": True,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
