from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.report_entity_ambiguity_counts import mentions_from_artifact, removed_marker_forms


class RemovedAmbiguityMarkerTests(unittest.TestCase):
    def test_reports_markers_removed_from_current_target(self) -> None:
        previous = {
            "entities": [
                {
                    "id": "jyotisha:concept_pata",
                    "preferred_label": "Pāta",
                    "attributes": {
                        "ambiguous_aliases": [
                            {"form": "Node", "sense": "ordinary English word"}
                        ]
                    },
                }
            ]
        }
        current = {
            "entities": [
                {
                    "id": "jyotisha:concept_pata",
                    "preferred_label": "Pāta",
                    "attributes": {},
                }
            ]
        }

        self.assertEqual(
            removed_marker_forms(previous, current),
            [("jyotisha:concept_pata", "Node", "Pāta")],
        )

    def test_precomputed_mentions_are_bound_to_the_requested_corpus_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mentions.jsonl"
            path.write_text(json.dumps({"corpus_revision": "revision-a"}) + "\n", encoding="utf-8")
            self.assertEqual(mentions_from_artifact(path, "revision-a")[0]["corpus_revision"], "revision-a")
            with self.assertRaisesRegex(ValueError, "do not match corpus revision"):
                mentions_from_artifact(path, "revision-b")


if __name__ == "__main__":
    unittest.main()
