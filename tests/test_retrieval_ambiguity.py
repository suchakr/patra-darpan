from __future__ import annotations

import unittest

from lib.retrieval_entities import build_summary, iter_mentions, registry_from_mentions


class RetrievalAmbiguityTests(unittest.TestCase):
    def ontology(self, *, markers=True):
        entity = {
            "id": "test:moon",
            "type": "celestial_body",
            "preferred_label": "Moon",
            "aliases": ["सोम"],
            "attributes": {},
        }
        if markers:
            entity["attributes"]["ambiguous_aliases"] = [
                {"form": "सोम", "sense": "also a plant and weekday"}
            ]
        return {"ontology_id": "test", "version": "0.3.1" if markers else "0.3.0", "entities": [entity]}

    def chunk(self):
        return {
            "chunk_id": "chunk:1",
            "document_id": "doc:1",
            "text": "सोम is an alias for Moon.",
        }

    def test_flagged_form_is_explicit_and_other_alias_is_unflagged(self):
        ontology = self.ontology()
        mentions = list(iter_mentions([self.chunk()], ontology, corpus_revision="rev"))
        by_form = {row["normalized_form"]: row for row in mentions}
        self.assertIs(by_form["सोम"]["ambiguous"], True)
        self.assertIs(by_form["moon"]["ambiguous"], False)
        self.assertEqual(by_form["सोम"]["schema_version"], "retrieval.entity-mention.v2")

        registry = registry_from_mentions(ontology, mentions, corpus_revision="rev")
        self.assertEqual(registry[0]["mention_assessment"], {
            "total": 2, "flagged": 1, "unflagged": 1, "unassessed": 0,
        })
        summary = build_summary(
            ontology=ontology, chunks_seen=1, mentions=mentions, registry=registry, corpus_revision="rev"
        )
        self.assertEqual(summary["mention_assessment"], registry[0]["mention_assessment"])

    def test_ontology_without_ambiguity_contract_leaves_rows_unassessed(self):
        mentions = list(iter_mentions([self.chunk()], self.ontology(markers=False), corpus_revision="rev"))
        self.assertTrue(mentions)
        self.assertTrue(all("ambiguous" not in row for row in mentions))

    def test_marker_must_name_an_existing_alias(self):
        ontology = self.ontology()
        ontology["entities"][0]["attributes"]["ambiguous_aliases"][0]["form"] = "not an alias"
        with self.assertRaisesRegex(ValueError, "not a declared alias"):
            list(iter_mentions([self.chunk()], ontology, corpus_revision="rev"))


if __name__ == "__main__":
    unittest.main()
