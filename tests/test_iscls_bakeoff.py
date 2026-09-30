from __future__ import annotations

import unittest

from lib.iscls_bakeoff import (
    CHUNKER_VERSION,
    chunk_blocks,
    make_chunks_for_source,
    parse_blocks,
)
from lib.iscls_eval import rank_metrics, summarize_judged
from lib.iscls_budget import estimate_embedding_budget
from lib.iscls_gemini import prepare_document, prepare_query
from scripts.run_iscls_gemini_build import partition_chunks
from scripts.run_iscls_vector_build import select_chunks


class IsclsBakeoffChunkTests(unittest.TestCase):
    def test_linewise_plain_text_preserves_short_lines(self) -> None:
        blocks = parse_blocks("śloka one\nśloka two\nśloka three\n")
        self.assertEqual([block.text for block in blocks], ["śloka one", "śloka two", "śloka three"])

    def test_heading_context_and_tables_are_retained(self) -> None:
        text = "# Nakṣatra\n\nA short paragraph.\n\n| name | count |\n| --- | --- |\n| Maghā | 1 |\n"
        chunks = make_chunks_for_source(
            {"source_id": "sanchaya:test", "document_id": "sanchaya:test", "repo_path": "x.txt", "title": "Test"},
            text,
            target_tokens=20,
            max_tokens=30,
            overlap_tokens=4,
        )
        self.assertEqual(chunks[0]["heading_path"], ["Nakṣatra"])
        self.assertIn("Maghā", "\n".join(chunk["text"] for chunk in chunks))
        self.assertTrue(any(chunk["kind"] == "table" for chunk in chunks))
        self.assertTrue(all(chunk["chunker_version"] == CHUNKER_VERSION for chunk in chunks))

    def test_long_block_is_bounded_and_ids_are_stable(self) -> None:
        text = " ".join(["देव"] * 120)
        source = {"source_id": "sanchaya:test", "document_id": "sanchaya:test", "repo_path": "x.txt", "title": "Test"}
        first = make_chunks_for_source(source, text, target_tokens=16, max_tokens=20, overlap_tokens=3)
        second = make_chunks_for_source(source, text, target_tokens=16, max_tokens=20, overlap_tokens=3)
        self.assertEqual([chunk["chunk_id"] for chunk in first], [chunk["chunk_id"] for chunk in second])
        self.assertGreater(len(first), 1)
        self.assertTrue(all(chunk["token_estimate"] <= 20 for chunk in first))
        self.assertTrue(all(chunk["forced_split"] for chunk in first))

    def test_invalid_limits_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            chunk_blocks(parse_blocks("text"), target_tokens=0)
        with self.assertRaises(ValueError):
            chunk_blocks(parse_blocks("text"), target_tokens=10, max_tokens=10, overlap_tokens=10)

    def test_rank_metrics_and_script_summary(self) -> None:
        metrics = rank_metrics(["d1", "d1", "d2", "d3"], ["d1"], 5)
        self.assertEqual(metrics["recall_at_k"], 1.0)
        self.assertEqual(metrics["matched_count"], 1)
        self.assertLessEqual(metrics["ndcg_at_k"], 1.0)
        summary = summarize_judged([{"script": "Devanagari", "metrics": metrics}])
        self.assertEqual(summary["judged_count"], 1)
        self.assertEqual(summary["by_script"]["Devanagari"]["recall_at_5"], 1.0)

    def test_gemini_budget_preflight_has_stop_and_cap_states(self) -> None:
        estimate = estimate_embedding_budget(1_000_000, 100_000)
        self.assertAlmostEqual(estimate.estimated_cost_usd, 0.22)
        self.assertTrue(estimate.under_stop)
        over_stop = estimate_embedding_budget(2_100_000)
        self.assertFalse(over_stop.under_stop)
        self.assertTrue(over_stop.under_cap)

    def test_calibration_selection_is_round_robin_and_stable(self) -> None:
        chunks = [
            {"source_id": "b", "chunk_id": "b1"},
            {"source_id": "b", "chunk_id": "b2"},
            {"source_id": "a", "chunk_id": "a1"},
            {"source_id": "a", "chunk_id": "a2"},
        ]
        selected = select_chunks(chunks, 3)
        self.assertEqual([chunk["chunk_id"] for chunk in selected], ["a1", "b1", "a2"])

    def test_gemini_retrieval_format_is_shared_for_documents_and_queries(self) -> None:
        document = prepare_document(
            {
                "title": "Fallback title",
                "heading_path": ["Nakṣatra", "Maghā"],
                "embed_text": "Sun at Maghā heralds the season.",
            }
        )
        self.assertTrue(document.startswith("title: Nakṣatra / Maghā | text: "))
        self.assertEqual(
            prepare_query("What is the significance of Maghadi?"),
            "task: search result | query: What is the significance of Maghadi?",
        )

    def test_gemini_batch_partition_respects_guarded_budget(self) -> None:
        chunks = [
            {"chunk_id": "a", "token_estimate": 100},
            {"chunk_id": "b", "token_estimate": 100},
            {"chunk_id": "c", "token_estimate": 100},
        ]
        groups = partition_chunks(chunks, safety_factor=2, token_budget=250)
        self.assertEqual([[row["chunk_id"] for row in group] for group in groups], [["a"], ["b"], ["c"]])


if __name__ == "__main__":
    unittest.main()
