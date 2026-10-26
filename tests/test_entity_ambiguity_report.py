from __future__ import annotations

import unittest

from scripts.report_entity_ambiguity_counts import removed_marker_forms


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


if __name__ == "__main__":
    unittest.main()
