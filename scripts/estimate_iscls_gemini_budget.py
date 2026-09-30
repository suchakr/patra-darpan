#!/usr/bin/env python3
"""Preflight Gemini embedding spend without making an API call."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.iscls_budget import (
    DEFAULT_HARD_CAP_USD,
    DEFAULT_STOP_USD,
    GEMINI_TEXT_USD_PER_MILLION_TOKENS,
    estimate_embedding_budget,
)


def token_estimate(text: str) -> int:
    return len(text.split())


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chunks", type=Path, default=ROOT / ".local/iscls-bakeoff/chunks.jsonl")
    parser.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "tests/fixtures/iscls/semantic-embedding-bakeoff-queries.jsonl",
    )
    parser.add_argument("--split", choices=["all", "dev", "heldout", "probe"], default="all")
    parser.add_argument("--hard-cap-usd", type=float, default=DEFAULT_HARD_CAP_USD)
    parser.add_argument("--stop-usd", type=float, default=DEFAULT_STOP_USD)
    parser.add_argument("--price-per-million", type=float, default=GEMINI_TEXT_USD_PER_MILLION_TOKENS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    chunks = load_jsonl(args.chunks)
    queries = load_jsonl(args.queries)
    if args.split != "all":
        queries = [query for query in queries if query.get("split") == args.split]
    corpus_tokens = sum(token_estimate(str(chunk.get("embed_text") or chunk.get("text") or "")) for chunk in chunks)
    query_tokens = sum(token_estimate(str(query.get("text") or "")) for query in queries)
    estimate = estimate_embedding_budget(
        corpus_tokens,
        query_tokens,
        price_per_million=args.price_per_million,
        hard_cap_usd=args.hard_cap_usd,
        stop_usd=args.stop_usd,
    )
    output = {
        "corpus_chunks": len(chunks),
        "query_count": len(queries),
        "corpus_tokens_estimate": estimate.corpus_tokens,
        "query_tokens_estimate": estimate.query_tokens,
        "total_tokens_estimate": estimate.total_tokens,
        "price_per_million_tokens_usd": args.price_per_million,
        "estimated_cost_usd": round(estimate.estimated_cost_usd, 6),
        "stop_usd": args.stop_usd,
        "hard_cap_usd": args.hard_cap_usd,
        "status": "under_stop" if estimate.under_stop else "over_stop",
    }
    print(json.dumps(output, indent=2))
    return 0 if estimate.under_cap else 2


if __name__ == "__main__":
    raise SystemExit(main())
