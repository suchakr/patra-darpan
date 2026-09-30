#!/usr/bin/env python3
"""Evaluate one Qdrant candidate against the checked-in query contract."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.iscls_eval import rank_metrics, summarize_judged
from lib.iscls_gemini import embed_one, prepare_query


def query_text(model_name: str, text: str) -> str:
    lowered = model_name.lower()
    if "e5" in lowered:
        return "query: " + text
    if "gemini-embedding-2" in lowered:
        return prepare_query(text)
    return text


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Vector run.json written by run_iscls_vector_build.py")
    parser.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "tests/fixtures/iscls/semantic-embedding-bakeoff-queries.jsonl",
    )
    parser.add_argument("--qdrant-url", default=None)
    parser.add_argument("--output-dir", type=Path, default=ROOT / ".local/iscls-bakeoff/evaluations")
    parser.add_argument("--limit", type=int, default=5)
    return parser.parse_args()


def _points(response: Any) -> list[Any]:
    if hasattr(response, "points"):
        return list(response.points)
    return list(response)


def main() -> int:
    args = parse_args()
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise SystemExit("Evaluation needs qdrant-client in the bakeoff environment.") from exc
    run = json.loads(args.run.read_text(encoding="utf-8"))
    model_name = str(run["model"])
    collection = str(run["collection"])
    client = QdrantClient(url=args.qdrant_url or str(run.get("qdrant_url") or "http://127.0.0.1:6333"))
    is_gemini = "gemini-embedding-2" in model_name.lower()
    if is_gemini:
        from google import genai

        gemini_client = genai.Client()
        dimensions = int(run.get("dimensions") or 768)
        model = None
    else:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise SystemExit("Local evaluation needs sentence-transformers in the bakeoff environment.") from exc
        gemini_client = None
        dimensions = None
        model = SentenceTransformer(model_name)
    rows: list[dict[str, Any]] = []
    started = time.monotonic()
    for query in load_jsonl(args.queries):
        prepared_query = query_text(model_name, str(query["text"]))
        if is_gemini:
            vector = embed_one(gemini_client, prepared_query, model=model_name, dimensions=dimensions)
        else:
            vector = model.encode(
                [prepared_query],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )[0].tolist()
        if hasattr(client, "query_points"):
            response = client.query_points(
                collection_name=collection,
                query=vector,
                limit=args.limit,
                with_payload=True,
            )
        else:
            response = client.search(
                collection_name=collection,
                query_vector=vector,
                limit=args.limit,
                with_payload=True,
            )
        hits = []
        for point in _points(response):
            payload = dict(getattr(point, "payload", None) or {})
            hits.append(
                {
                    "score": float(getattr(point, "score", 0.0)),
                    "chunk_id": payload.get("chunk_id"),
                    "document_id": payload.get("document_id"),
                    "repo_path": payload.get("repo_path"),
                    "logical_location": payload.get("logical_location"),
                }
            )
        expected_documents = [str(value) for value in query.get("expected_document_ids", [])]
        expected_paths = [str(value) for value in query.get("expected_source_paths", [])]
        hit_paths = [str(hit.get("repo_path")) for hit in hits]
        path_coverage = (
            len(set(hit_paths) & set(expected_paths)) / len(set(expected_paths))
            if expected_paths
            else None
        )
        metrics = rank_metrics([str(hit.get("document_id")) for hit in hits], expected_documents, args.limit)
        metrics["source_path_coverage"] = path_coverage
        rows.append(
            {
                "query_id": query["query_id"],
                "split": query.get("split"),
                "class": query.get("class"),
                "script": query.get("script"),
                "text": query["text"],
                "expected_document_ids": expected_documents,
                "expected_source_paths": expected_paths,
                "metrics": metrics,
                "hits": hits,
            }
        )
    summary = {
        "schema_version": "iscls.evaluation.v1",
        "model": model_name,
        "collection": collection,
        "run_manifest": str(args.run),
        "query_file": str(args.queries),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "summary": summarize_judged(rows),
        "open_ended_count": sum(row["metrics"]["recall_at_k"] is None for row in rows),
        "source_path_coverage": (
            sum(float(row["metrics"]["source_path_coverage"]) for row in rows if row["metrics"].get("source_path_coverage") is not None)
            / sum(row["metrics"].get("source_path_coverage") is not None for row in rows)
            if any(row["metrics"].get("source_path_coverage") is not None for row in rows)
            else None
        ),
    }
    slug = collection.replace("/", "_")
    output_dir = args.output_dir / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
