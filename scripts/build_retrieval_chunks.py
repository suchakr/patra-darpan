#!/usr/bin/env python3
"""Build the shared deterministic retrieval chunk inventory."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_chunks import (
    CHUNKER_VERSION,
    DEFAULT_MAX_TOKENS,
    DEFAULT_OVERLAP_TOKENS,
    DEFAULT_TARGET_TOKENS,
    make_chunks_for_source,
    sha256_file,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-manifest",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "input-manifest.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "chunks.jsonl",
    )
    parser.add_argument("--target-tokens", type=int, default=DEFAULT_TARGET_TOKENS)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--overlap-tokens", type=int, default=DEFAULT_OVERLAP_TOKENS)
    return parser.parse_args()


def build_chunks(input_manifest: dict[str, Any], *, target_tokens: int, max_tokens: int, overlap_tokens: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sanchaya_root = Path(str(input_manifest["sanchaya"]["root"])).expanduser()
    expected_commit = str(input_manifest["sanchaya"]["commit"])
    all_chunks: list[dict[str, Any]] = []
    source_stats: list[dict[str, Any]] = []
    for source in input_manifest["sources"]:
        path = sanchaya_root / str(source["repo_path"])
        actual_hash = sha256_file(path)
        if actual_hash != source["content_sha256"]:
            raise ValueError(f"source changed after manifest creation: {source['repo_path']}")
        text = path.read_text(encoding="utf-8")
        chunks = make_chunks_for_source(
            source,
            text,
            target_tokens=target_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        all_chunks.extend(chunks)
        source_stats.append(
            {
                "source_id": source["source_id"],
                "repo_path": source["repo_path"],
                "bytes": source["bytes"],
                "chunks": len(chunks),
                "tokens": sum(int(chunk["token_estimate"]) for chunk in chunks),
                "forced_splits": sum(bool(chunk["forced_split"]) for chunk in chunks),
            }
        )
    summary = {
        "schema_version": "retrieval.chunk-build.v1",
        "chunker_version": CHUNKER_VERSION,
        "sanchaya_commit": expected_commit,
        "source_count": len(source_stats),
        "chunk_count": len(all_chunks),
        "target_tokens": target_tokens,
        "max_tokens": max_tokens,
        "overlap_tokens": overlap_tokens,
        "forced_split_count": sum(bool(chunk["forced_split"]) for chunk in all_chunks),
        "token_estimate_total": sum(int(chunk["token_estimate"]) for chunk in all_chunks),
        "kind_counts": dict(Counter(str(chunk["kind"]) for chunk in all_chunks)),
        "source_stats": source_stats,
    }
    return all_chunks, summary


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    input_manifest = json.loads(args.input_manifest.read_text(encoding="utf-8"))
    chunks, summary = build_chunks(
        input_manifest,
        target_tokens=args.target_tokens,
        max_tokens=args.max_tokens,
        overlap_tokens=args.overlap_tokens,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n")
    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    summary_path = args.output.with_name("chunk-build.json")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output}: sources={summary['source_count']} chunks={summary['chunk_count']} "
        f"tokens≈{summary['token_estimate_total']} forced_splits={summary['forced_split_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
