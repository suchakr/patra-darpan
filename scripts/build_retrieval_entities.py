#!/usr/bin/env python3
"""Build deterministic retrieval entity mentions and registry projections.

The input is the shared chunk inventory.  Each chunk is an extraction window
for this first vertical slice; the mention contract keeps the window and chunk
link explicit so a later paragraph/verse extractor can replace this boundary
without changing the graph projection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_entities import (
    build_summary,
    iter_mentions,
    read_jsonl,
    registry_from_mentions,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunks",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "chunks.jsonl",
        help="shared retrieval chunk JSONL",
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=ROOT / "ontology" / "jyotisha-v0.3.json",
        help="repository-owned versioned ontology JSON",
    )
    parser.add_argument(
        "--mentions",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "entity-mentions.jsonl",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "entity-registry.jsonl",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "entity-build.json",
    )
    parser.add_argument(
        "--chunk-build",
        type=Path,
        default=None,
        help="optional chunk-build.json used to read the corpus revision",
    )
    parser.add_argument(
        "--corpus-revision",
        default=None,
        help="override the corpus revision recorded in output",
    )
    return parser.parse_args()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _corpus_revision(args: argparse.Namespace) -> str:
    if args.corpus_revision:
        return str(args.corpus_revision)
    summary_path = args.chunk_build or args.chunks.with_name("chunk-build.json")
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        revision = str(summary.get("sanchaya_commit") or "")
        if revision:
            return revision
    return "unknown"


def main() -> int:
    args = parse_args()
    ontology = json.loads(args.ontology.read_text(encoding="utf-8"))
    if not isinstance(ontology, dict):
        raise ValueError("ontology must contain a JSON object")
    chunks = list(read_jsonl(args.chunks))
    revision = _corpus_revision(args)
    mentions = list(iter_mentions(chunks, ontology, corpus_revision=revision))
    registry = registry_from_mentions(ontology, mentions, corpus_revision=revision)
    summary = build_summary(
        ontology=ontology,
        chunks_seen=len(chunks),
        mentions=mentions,
        registry=registry,
        corpus_revision=revision,
    )
    _write_jsonl(args.mentions, mentions)
    _write_jsonl(args.registry, registry)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote mentions={args.mentions} ({summary['mention_count']}), "
        f"registry={args.registry} ({summary['seed_entity_count']} seeds, "
        f"{summary['observed_entity_count']} observed), revision={revision}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
