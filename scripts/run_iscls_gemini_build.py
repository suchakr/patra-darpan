#!/usr/bin/env python3
"""Build one capped Gemini Embedding 2 collection in local Qdrant.

This is intentionally separate from the local SentenceTransformer runner:
Gemini is a remote API and its calls need an explicit cost preflight, retry
policy, and concurrency setting.  The resulting run manifest and Qdrant
payload are otherwise compatible with the local bakeoff arm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.iscls_budget import (  # noqa: E402
    DEFAULT_HARD_CAP_USD,
    DEFAULT_STOP_USD,
    GEMINI_BATCH_TEXT_USD_PER_MILLION_TOKENS,
    GEMINI_TEXT_USD_PER_MILLION_TOKENS,
    estimate_embedding_budget,
)
from lib.iscls_gemini import MODEL_NAME, embed_one, prepare_document  # noqa: E402
from scripts.run_iscls_vector_build import load_chunks, select_chunks  # noqa: E402


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=ROOT / ".local/iscls-bakeoff/chunks.jsonl")
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--collection", default="iscls_gemini_embedding_2_768")
    parser.add_argument("--dimension", type=int, default=768)
    parser.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    parser.add_argument("--batch-size", type=int, default=64, help="Qdrant upsert batch size")
    parser.add_argument("--parallelism", type=int, default=4, help="Concurrent Gemini requests")
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".local/iscls-bakeoff/runs")
    parser.add_argument(
        "--mode",
        choices=["sync", "batch"],
        default="sync",
        help="sync uses concurrent embedContent calls; batch uses the discounted async Batch API",
    )
    parser.add_argument(
        "--price-per-million",
        type=float,
        default=None,
        help="Override the default standard ($0.20/M) or batch ($0.10/M) price",
    )
    parser.add_argument("--stop-usd", type=float, default=DEFAULT_STOP_USD)
    parser.add_argument("--hard-cap-usd", type=float, default=DEFAULT_HARD_CAP_USD)
    parser.add_argument(
        "--cost-safety-factor",
        type=float,
        default=3.5,
        help="Multiply the whitespace-token estimate before the spend guard",
    )
    parser.add_argument("--poll-seconds", type=int, default=10, help="Batch polling interval")
    parser.add_argument("--batch-job-name", help="Resume/poll an existing Batch API job")
    parser.add_argument("--batch-input", type=Path, help="Reuse a previously written batch request JSONL")
    parser.add_argument(
        "--resume-batches",
        action="store_true",
        help="Reuse completed batch result files under the collection run directory",
    )
    parser.add_argument(
        "--batch-token-budget",
        type=int,
        default=400_000,
        help="Guarded Gemini tokens per Batch API job; keep below the Tier 1 500k limit",
    )
    parser.add_argument("--recreate", action="store_true")
    return parser.parse_args()


_thread_state = threading.local()


def _client() -> Any:
    client = getattr(_thread_state, "client", None)
    if client is None:
        from google import genai

        client = genai.Client()
        _thread_state.client = client
    return client


def _embed_with_retry(
    index: int,
    text: str,
    *,
    model: str,
    dimensions: int,
    max_retries: int,
) -> tuple[int, list[float]]:
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return index, embed_one(_client(), text, model=model, dimensions=dimensions)
        except Exception as exc:  # API errors vary across client versions.
            last_error = exc
            if attempt >= max_retries:
                break
            time.sleep(min(30.0, 2.0**attempt))
    assert last_error is not None
    raise RuntimeError(f"Gemini embedding failed for item {index}: {last_error}") from last_error


def _payload(chunk: dict[str, Any]) -> dict[str, Any]:
    return {
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


def _write_batch_input(path: Path, texts: list[str], dimension: int, chunks: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk, text in zip(chunks, texts, strict=True):
            row = {
                "key": str(chunk["chunk_id"]),
                "request": {
                    "output_dimensionality": dimension,
                    "content": {"parts": [{"text": text}]},
                },
            }
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def partition_chunks(
    chunks: list[dict[str, Any]], *, safety_factor: float, token_budget: int
) -> list[list[dict[str, Any]]]:
    """Partition chunks by guarded token estimate for the Batch API queue."""

    if token_budget <= 0:
        raise ValueError("token_budget must be positive")
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    for chunk in chunks:
        guarded = max(1, int(round(int(chunk.get("token_estimate") or 0) * safety_factor)))
        if current and current_tokens + guarded > token_budget:
            groups.append(current)
            current = []
            current_tokens = 0
        current.append(chunk)
        current_tokens += guarded
    if current:
        groups.append(current)
    return groups


def _batch_embedding_values(response: Any, dimension: int) -> list[float]:
    """Read one file/inline batch response across SDK response shapes."""

    response = response or {}
    if isinstance(response, dict):
        embedding = response.get("embedding") or response.get("embeddings")
        if isinstance(embedding, list):
            embedding = embedding[0] if embedding else None
        values = embedding.get("values") if isinstance(embedding, dict) else None
    else:
        embedding = getattr(response, "embedding", None)
        values = getattr(embedding, "values", None) if embedding is not None else None
    values = list(values or [])
    if len(values) != dimension:
        raise RuntimeError(f"batch response has {len(values)} dimensions; expected {dimension}")
    return [float(value) for value in values]


def _read_batch_result_file(path: Path, chunks: list[dict[str, Any]], dimension: int) -> list[list[float]]:
    responses_by_key: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            responses_by_key[str(row.get("key"))] = row
    vectors: list[list[float]] = []
    for chunk in chunks:
        key = str(chunk["chunk_id"])
        row = responses_by_key.get(key)
        if row is None:
            raise RuntimeError(f"batch result missing key {key} in {path}")
        if row.get("error"):
            raise RuntimeError(f"batch result failed for {key}: {row['error']}")
        vectors.append(_batch_embedding_values(row.get("response"), dimension))
    return vectors


def _run_batch(
    *,
    client: Any,
    chunks: list[dict[str, Any]],
    texts: list[str],
    run_dir: Path,
    input_path: Path,
    model: str,
    dimension: int,
    poll_seconds: int,
    existing_job_name: str | None,
) -> tuple[list[list[float]], float, str]:
    """Submit/poll one Gemini embedding batch and return vectors."""

    run_dir.mkdir(parents=True, exist_ok=True)
    saved_results = run_dir / "batch-results.jsonl"
    if saved_results.exists():
        return _read_batch_result_file(saved_results, chunks, dimension), 0.0, "resumed-from-results"
    if existing_job_name:
        job_name = existing_job_name
    else:
        _write_batch_input(input_path, texts, dimension, chunks)
        from google.genai import types

        uploaded = client.files.upload(
            file=str(input_path),
            config=types.UploadFileConfig(mime_type="application/jsonl"),
        )
        job = client.batches.create_embeddings(
            model=model,
            src={"file_name": uploaded.name},
            config={"display_name": f"iscls-{model}-embedding"},
        )
        job_name = job.name
        (run_dir / "batch-job.json").write_text(
            json.dumps(
                {
                    "job_name": job_name,
                    "input_path": str(input_path),
                    "uploaded_file_name": uploaded.name,
                    "created_at": utc_now(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    completed = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"}
    job = client.batches.get(name=job_name)
    while getattr(job.state, "name", job.state) not in completed:
        print(json.dumps({"batch_job": job_name, "state": getattr(job.state, "name", job.state)}), flush=True)
        time.sleep(max(1, poll_seconds))
        job = client.batches.get(name=job_name)
    state = getattr(job.state, "name", job.state)
    if state != "JOB_STATE_SUCCEEDED":
        raise RuntimeError(f"Gemini batch ended in {state}: {getattr(job, 'error', None)}")

    responses_by_key: dict[str, Any] = {}
    destination = job.dest
    if getattr(destination, "file_name", None):
        result_bytes = client.files.download(file=destination.file_name)
        result_path = run_dir / "batch-results.jsonl"
        result_path.write_bytes(result_bytes)
        for line in result_bytes.decode("utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                responses_by_key[str(row.get("key"))] = row
    else:
        for index, item in enumerate(getattr(destination, "inlined_embed_content_responses", []) or []):
            responses_by_key[str(chunks[index]["chunk_id"])] = {
                "key": chunks[index]["chunk_id"],
                "response": getattr(item, "response", None),
                "error": getattr(item, "error", None),
            }

    vectors: list[list[float]] = []
    for chunk in chunks:
        key = str(chunk["chunk_id"])
        row = responses_by_key.get(key)
        if row is None:
            raise RuntimeError(f"batch result missing key {key}")
        if isinstance(row, dict) and row.get("error"):
            raise RuntimeError(f"batch result failed for {key}: {row['error']}")
        response = row.get("response") if isinstance(row, dict) else None
        vectors.append(_batch_embedding_values(response, dimension))
    return vectors, 0.0, job_name


def main() -> int:
    args = parse_args()
    if args.dimension <= 0 or args.parallelism <= 0 or args.batch_size <= 0:
        raise SystemExit("dimension, parallelism, and batch-size must be positive")
    if args.cost_safety_factor <= 0:
        raise SystemExit("cost-safety-factor must be positive")

    if args.poll_seconds <= 0 or args.batch_token_budget <= 0:
        raise SystemExit("poll-seconds must be positive")
    price_per_million = args.price_per_million
    if price_per_million is None:
        price_per_million = (
            GEMINI_BATCH_TEXT_USD_PER_MILLION_TOKENS
            if args.mode == "batch"
            else GEMINI_TEXT_USD_PER_MILLION_TOKENS
        )

    try:
        from qdrant_client import QdrantClient
        from qdrant_client.http import models as qmodels
    except ImportError as exc:
        raise SystemExit("Gemini vector build needs qdrant-client in the bakeoff environment") from exc

    all_chunks = load_chunks(args.chunks)
    chunks = select_chunks(all_chunks, args.max_chunks)
    estimated_tokens = sum(int(chunk.get("token_estimate") or 0) for chunk in chunks)
    guarded_tokens = int(round(estimated_tokens * args.cost_safety_factor))
    estimate = estimate_embedding_budget(
        guarded_tokens,
        price_per_million=price_per_million,
        hard_cap_usd=args.hard_cap_usd,
        stop_usd=args.stop_usd,
    )
    if not estimate.under_cap:
        raise SystemExit(
            f"Gemini preflight exceeds hard cap: ${estimate.estimated_cost_usd:.6f} "
            f"> ${args.hard_cap_usd:.2f}"
        )
    if not estimate.under_stop:
        raise SystemExit(
            f"Gemini preflight exceeds stop threshold: ${estimate.estimated_cost_usd:.6f} "
            f"> ${args.stop_usd:.2f}; reduce --max-chunks or adjust the approved guard"
        )

    started = time.monotonic()
    texts = [prepare_document(chunk) for chunk in chunks]
    run_dir = args.output_dir / args.collection
    run_dir.mkdir(parents=True, exist_ok=True)
    encode_started = time.monotonic()
    batch_job_names: list[str] = []
    if args.mode == "batch":
        from google import genai

        groups = partition_chunks(chunks, safety_factor=args.cost_safety_factor, token_budget=args.batch_token_budget)
        if args.batch_job_name and len(groups) != 1:
            raise SystemExit("--batch-job-name can resume only a single-batch run")
        chunk_positions = {id(chunk): index for index, chunk in enumerate(chunks)}
        complete_vectors = []
        for group_index, group in enumerate(groups, start=1):
            group_texts = [texts[chunk_positions[id(chunk)]] for chunk in group]
            group_dir = run_dir / f"batch-{group_index:03d}"
            group_input = args.batch_input if len(groups) == 1 and args.batch_input else group_dir / "batch-requests.jsonl"
            existing_job = None
            if args.resume_batches:
                job_file = group_dir / "batch-job.json"
                if job_file.exists():
                    existing_job = str(json.loads(job_file.read_text(encoding="utf-8")).get("job_name") or "") or None
            vectors, _, job_name = _run_batch(
                client=genai.Client(),
                chunks=group,
                texts=group_texts,
                run_dir=group_dir,
                input_path=group_input,
                model=args.model,
                dimension=args.dimension,
                poll_seconds=args.poll_seconds,
                existing_job_name=(args.batch_job_name if len(groups) == 1 else existing_job),
            )
            complete_vectors.extend(vectors)
            if job_name != "resumed-from-results":
                batch_job_names.append(job_name)
            elif existing_job:
                batch_job_names.append(existing_job)
            (run_dir / "batch-jobs.json").write_text(
                json.dumps({"jobs": batch_job_names, "completed_batches": group_index}, indent=2) + "\n",
                encoding="utf-8",
            )
        (run_dir / "batch-jobs.json").write_text(
            json.dumps({"jobs": batch_job_names, "batch_count": len(groups)}, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        vectors: list[list[float] | None] = [None] * len(chunks)
        with ThreadPoolExecutor(max_workers=args.parallelism) as executor:
            futures = {
                executor.submit(
                    _embed_with_retry,
                    index,
                    text,
                    model=args.model,
                    dimensions=args.dimension,
                    max_retries=args.max_retries,
                ): index
                for index, text in enumerate(texts)
            }
            for future in as_completed(futures):
                index, vector = future.result()
                vectors[index] = vector
        complete_vectors = [vector for vector in vectors if vector is not None]
        if len(complete_vectors) != len(chunks):
            raise RuntimeError("embedding run did not produce one vector per chunk")
    encode_seconds = time.monotonic() - encode_started

    client = QdrantClient(url=args.qdrant_url)
    if args.recreate and client.collection_exists(args.collection):
        client.delete_collection(args.collection)
    if not client.collection_exists(args.collection):
        client.create_collection(
            collection_name=args.collection,
            vectors_config=qmodels.VectorParams(size=args.dimension, distance=qmodels.Distance.COSINE),
        )

    points = []
    for chunk, vector in zip(chunks, complete_vectors, strict=True):
        points.append(
            qmodels.PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_URL, str(chunk["chunk_id"]))),
                vector=vector,
                payload=_payload(chunk),
            )
        )
    upsert_started = time.monotonic()
    for start in range(0, len(points), args.batch_size):
        client.upsert(collection_name=args.collection, points=points[start : start + args.batch_size], wait=True)
    upsert_seconds = time.monotonic() - upsert_started

    manifest = {
        "schema_version": "iscls.vector-build.v1",
        "created_at": utc_now(),
        "model": args.model,
        "provider": "google-gemini-api",
        "mode": args.mode,
        "embedding_input_format": "gemini-embedding-2-retrieval",
        "collection": args.collection,
        "qdrant_url": args.qdrant_url,
        "chunks_path": str(args.chunks),
        "chunks_sha256": file_sha256(args.chunks),
        "full_chunk_count": len(all_chunks),
        "chunk_count": len(chunks),
        "sample_limit": args.max_chunks,
        "token_estimate_total": estimated_tokens,
        "preflight_token_estimate": guarded_tokens,
        "preflight_safety_factor": args.cost_safety_factor,
        "price_per_million_tokens_usd": price_per_million,
        "preflight_estimated_cost_usd": round(estimate.estimated_cost_usd, 6),
        "stop_usd": args.stop_usd,
        "hard_cap_usd": args.hard_cap_usd,
        "dimensions": args.dimension,
        "normalized": True,
        "parallelism": args.parallelism if args.mode == "sync" else None,
        "max_retries": args.max_retries,
        "batch_job_names": batch_job_names,
        "batch_count": len(batch_job_names) if args.mode == "batch" else None,
        "batch_token_budget": args.batch_token_budget if args.mode == "batch" else None,
        "encode_seconds": round(encode_seconds, 3),
        "upsert_seconds": round(upsert_seconds, 3),
        "encode_chunks_per_second": round(len(chunks) / encode_seconds, 3) if encode_seconds else None,
        "encode_tokens_per_second": round(estimated_tokens / encode_seconds, 3) if encode_seconds else None,
        "raw_vector_bytes": len(chunks) * args.dimension * 4,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    (run_dir / "run.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
