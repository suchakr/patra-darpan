#!/usr/bin/env python3
"""Run a small, repeatable smoke check against one active retrieval release."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import RetrievalError, RetrievalService, load_release


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="What is the significance of the Maghadi scheme?")
    parser.add_argument("--entity", default="Śraviṣṭhā")
    parser.add_argument("--mode", choices=("lexical", "vector", "hybrid"), default="hybrid")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--skip-vector", action="store_true")
    parser.add_argument("--skip-lexical", action="store_true")
    parser.add_argument("--require-backends", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    release = load_release()
    ontology = os.getenv("RETRIEVAL_ONTOLOGY_PATH", str(ROOT / "ontology/jyotisha-v0.3.json"))
    service = RetrievalService(
        release,
        ontology_path=ontology,
        zoekt_url=os.getenv("ZOEKT_URL") or os.getenv("RETRIEVAL_ZOEKT_URL"),
        qdrant_url=os.getenv("QDRANT_URL") or os.getenv("RETRIEVAL_QDRANT_URL"),
    )
    lookup = service.entities.lookup(args.entity, limit=args.limit)
    if not lookup["results"]:
        raise SystemExit(f"entity lookup returned no result: {args.entity}")
    entity_id = str(lookup["results"][0]["entity_id"])
    mentions = service.entities.list_mentions(entity_id, limit=args.limit)
    first_chunk = next(iter(service.passages.by_id), None)
    passage = service.passages.fetch(chunk_id=first_chunk, limit=1) if first_chunk else {"passages": []}

    result: dict[str, object] = {
        "release_id": release.release_id,
        "corpus_revision": release.corpus_revision,
        "entity_id": entity_id,
        "mention_total": mentions["total"],
        "passage_fetch": len(passage["passages"]),
    }
    if args.skip_lexical:
        result["lexical"] = "skipped"
    else:
        lexical = service.search(args.query, mode="lexical", limit=args.limit)
        result["lexical"] = {
            "count": len(lexical["results"]),
            "errors": lexical["backend_errors"],
        }
    if args.skip_vector:
        result["vector"] = "skipped"
    else:
        vector = service.search(args.query, mode="vector", limit=args.limit)
        result["vector"] = {
            "count": len(vector["results"]),
            "errors": vector["backend_errors"],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.require_backends:
        required = [name for name, skipped in (("lexical", args.skip_lexical), ("vector", args.skip_vector)) if not skipped]
        for name in required:
            value = result.get(name)
            # A healthy backend may legitimately return no match for a query;
            # availability is established by an empty error map, not by hit
            # count.
            if not isinstance(value, dict) or value.get("errors"):
                return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RetrievalError as exc:
        print(json.dumps({"schema_version": "retrieval.error.v1", "error": str(exc)}, indent=2), file=sys.stderr)
        raise SystemExit(2) from exc
