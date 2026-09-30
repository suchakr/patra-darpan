from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from lib.decode_lab.costs import (
    call_cost_fields,
    duration_seconds,
    summarize_fallbacks,
    write_run_history,
)


class DecodeCostTests(unittest.TestCase):
    def test_call_cost_fields_uses_flex_rates_and_thinking_tokens(self) -> None:
        response = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=1_000_000,
                cached_content_token_count=100_000,
                candidates_token_count=200_000,
                thoughts_token_count=50_000,
            )
        )

        fields = call_cost_fields(
            model_name="gemini-3-flash-preview",
            service_tier="flex",
            response=response,
            cache_hit=False,
        )

        self.assertEqual(fields["cost_status"], "estimated")
        self.assertEqual(fields["usage"]["thoughts_token_count"], 50_000)
        self.assertEqual(fields["billable_input_tokens"], 900_000)
        self.assertEqual(fields["billable_output_tokens"], 250_000)
        self.assertEqual(fields["estimated_cost_usd"], 0.605)

    def test_local_cache_hit_is_zero_cost(self) -> None:
        fields = call_cost_fields(
            model_name="gemini-3-flash-preview",
            service_tier="standard",
            response=None,
            cache_hit=True,
        )

        self.assertEqual(fields["cost_status"], "local_cache_hit")
        self.assertEqual(fields["estimated_cost_usd"], 0.0)

    def test_summarize_fallbacks_separates_api_and_local_cache_calls(self) -> None:
        fallbacks = [
            {
                "fallback_type": "gemini_pdf_extract",
                "status": "partial",
                "cache_hit": False,
                "elapsed_seconds": 1.2,
                "usage": {
                    "prompt_token_count": 1_000_000,
                    "cached_content_token_count": 100_000,
                    "candidates_token_count": 200_000,
                    "thoughts_token_count": 50_000,
                },
                "estimated_cost_usd": 0.605,
            },
            {
                "fallback_type": "gemini_pdf_extract",
                "status": "partial",
                "cache_hit": True,
                "elapsed_seconds": 0.0,
                "usage": {},
                "estimated_cost_usd": 0.0,
            },
            {"fallback_type": "deterministic_postprocess", "status": "success"},
        ]

        summary = summarize_fallbacks(fallbacks)

        self.assertEqual(summary["gemini_calls"], 2)
        self.assertEqual(summary["api_calls"], 1)
        self.assertEqual(summary["cache_hits"], 1)
        self.assertEqual(summary["status"], "estimated")
        self.assertEqual(summary["estimated_cost_usd"], 0.605)
        self.assertEqual(summary["known_estimated_cost_usd"], 0.605)
        self.assertEqual(summary["recorded_thinking_tokens"], 50_000)

    def test_history_reconstructs_unknown_cost_for_old_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            run_dir = root / "old-run"
            run_dir.mkdir()
            (run_dir / "run-manifest.json").write_text(
                json.dumps(
                    {
                        "run_id": "old-run",
                        "started_at": "2026-09-19T10:00:00Z",
                        "finished_at": "2026-09-19T10:00:02Z",
                        "extractor": "gemini:3-flash-med",
                        "service_tier_requested": "standard",
                        "selected_doc_ids": ["doc-1"],
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "fallbacks.jsonl").write_text("", encoding="utf-8")
            output_path = root / "reports" / "decode-run-history.tsv"

            write_run_history(root, output_path)

            rows = output_path.read_text(encoding="utf-8").splitlines()
            self.assertTrue(rows[0].startswith("run_id\tstarted_at"))
            self.assertEqual(
                rows[1].split("\t")[0:4],
                [
                    "old-run",
                    "2026-09-19T10:00:00Z",
                    "2026-09-19T10:00:02Z",
                    "2.0",
                ],
            )
            self.assertEqual(rows[1].split("\t")[17], "not_applicable")

    def test_duration_seconds_handles_iso_z_timestamps(self) -> None:
        self.assertEqual(
            duration_seconds("2026-09-19T10:00:00Z", "2026-09-19T10:00:01Z"),
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
