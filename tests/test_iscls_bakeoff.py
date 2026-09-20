from __future__ import annotations

import unittest

from lib.iscls_bakeoff import (
    CHUNKER_VERSION,
    chunk_blocks,
    make_chunks_for_source,
    parse_blocks,
)
from lib.iscls_eval import rank_metrics, summarize_judged


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
        metrics = rank_metrics(["d2", "d1", "d3"], ["d1"], 5)
        self.assertEqual(metrics["recall_at_k"], 1.0)
        self.assertEqual(metrics["matched_count"], 1)
        summary = summarize_judged([{"script": "Devanagari", "metrics": metrics}])
        self.assertEqual(summary["judged_count"], 1)
        self.assertEqual(summary["by_script"]["Devanagari"]["recall_at_5"], 1.0)


if __name__ == "__main__":
    unittest.main()
