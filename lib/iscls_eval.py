"""Metrics and ranking helpers for the ISCLS bakeoff."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Iterable


def dcg_at_k(relevances: Iterable[int], k: int = 5) -> float:
    score = 0.0
    for rank, relevance in enumerate(list(relevances)[:k], start=1):
        score += (2**int(relevance) - 1) / math.log2(rank + 1)
    return score


def rank_metrics(hit_documents: list[str], expected_documents: list[str], k: int = 5) -> dict[str, Any]:
    """Return binary Recall@k and nDCG@k for a document-level judgment."""

    expected = list(dict.fromkeys(expected_documents))
    top = hit_documents[:k]
    relevance = [1 if document in expected else 0 for document in top]
    ideal = [1] * min(len(expected), k)
    return {
        "recall_at_k": (len(set(top) & set(expected)) / len(expected)) if expected else None,
        "ndcg_at_k": (dcg_at_k(relevance, k) / dcg_at_k(ideal, k)) if expected and ideal else None,
        "k": k,
        "expected_count": len(expected),
        "matched_count": len(set(top) & set(expected)),
    }


def summarize_judged(rows: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [row for row in rows if row.get("metrics", {}).get("recall_at_k") is not None]
    if not judged:
        return {"judged_count": 0, "recall_at_5": None, "ndcg_at_5": None, "by_script": {}}
    by_script: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in judged:
        by_script[str(row.get("script") or "unknown")].append(row)

    def avg(key: str, values: list[dict[str, Any]]) -> float | None:
        numbers = [float(item["metrics"][key]) for item in values if item["metrics"].get(key) is not None]
        return sum(numbers) / len(numbers) if numbers else None

    return {
        "judged_count": len(judged),
        "recall_at_5": avg("recall_at_k", judged),
        "ndcg_at_5": avg("ndcg_at_k", judged),
        "by_script": {
            script: {
                "count": len(values),
                "recall_at_5": avg("recall_at_k", values),
                "ndcg_at_5": avg("ndcg_at_k", values),
            }
            for script, values in sorted(by_script.items())
        },
    }
