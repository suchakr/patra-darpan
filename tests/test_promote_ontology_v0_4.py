from __future__ import annotations

import unittest

from scripts.promote_ontology_v0_4 import promote


class PromoteOntologyV04Tests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "ontology_id": "test",
            "version": "0.3.1",
            "entities": [{
                "id": "test:moon",
                "type": "lunar_mansion",
                "preferred_label": "Śāstra",
                "aliases": ["शास्त्र"],
                "attributes": {},
            }],
            "sources": [],
        }
        self.proposal = {
            "_meta": {"round": "v0.4"},
            "test:moon": {
                "contextual_synonyms": [
                    {"form": "दस्रभ", "status": "provisional", "review": {"by": "reviewer"}},
                    {"form": "not copied", "status": "rejected"},
                ],
                "spelling_variants": [
                    {"form": "Sastra-alt", "status": "provisional", "evidence": ["source:1"]},
                    {"form": "not copied either", "status": "candidate"},
                ],
            },
        }

    def test_copies_only_provisional_items_and_preserves_review_provenance(self):
        result, counts = promote(self.base, self.proposal, expected_items=2)
        entity = result["entities"][0]
        self.assertEqual(result["version"], "0.4.0")
        self.assertEqual(counts, {
            "items": 2, "contextual_synonyms": 1, "spelling_variants": 1,
        })
        self.assertEqual(entity["attributes"]["contextual_synonyms"][0]["status"], "provisional")
        self.assertEqual(entity["attributes"]["contextual_synonyms"][0]["review"]["by"], "reviewer")
        self.assertEqual(entity["attributes"]["variant_evidence"][0]["evidence"], ["source:1"])
        self.assertIn("Sastra-alt", entity["aliases"])
        self.assertNotIn("not copied", str(entity))
        self.assertIn("provisional is not expert approval", entity["v04_changes"][0])
        self.assertEqual(result["generation"]["validation"]["explicit_alias_entries"], 2)
        self.assertEqual(result["generation"]["validation"]["unique_normalized_aliases_including_preferred_labels"], 3)
        self.assertEqual(result["generation"]["validation"]["ambiguous_alias_entries"], 0)

    def test_rejects_a_changed_provisional_item_count(self):
        with self.assertRaisesRegex(ValueError, "expected 39 provisional items"):
            promote(self.base, self.proposal)

    def test_requires_v031_base(self):
        base = {**self.base, "version": "0.3.0"}
        with self.assertRaisesRegex(ValueError, "based on ontology version 0.3.1"):
            promote(base, self.proposal, expected_items=2)

    def test_rejects_new_cross_entity_alias_collision(self):
        base = {
            **self.base,
            "entities": [
                *self.base["entities"],
                {"id": "test:other", "type": "work", "preferred_label": "Sastra-alt", "aliases": []},
            ],
        }
        with self.assertRaisesRegex(ValueError, "introduce cross-entity collisions"):
            promote(base, self.proposal, expected_items=2)


if __name__ == "__main__":
    unittest.main()
