from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = ROOT / "docker-compose.retrieval.yml"


class ComposeOntologyDefaultTests(unittest.TestCase):
    def test_both_mcp_services_default_to_v04_without_an_override(self) -> None:
        compose = COMPOSE_FILE.read_text(encoding="utf-8")
        expected = (
            "RETRIEVAL_ONTOLOGY_PATH: "
            "${RETRIEVAL_ONTOLOGY_PATH:-/app/ontology/jyotisha-v0.4.0.json}"
        )

        for service in ("retrieval-mcp", "retrieval-mcp-oauth"):
            with self.subTest(service=service):
                service_pattern = (
                    rf"(?ms)^  {re.escape(service)}:\n"
                    r"(?P<body>.*?)(?=^  [A-Za-z0-9_-]+:[ \t]*$"
                    r"|^networks:[ \t]*$|^volumes:[ \t]*$|\Z)"
                )
                section = re.search(
                    service_pattern, compose
                )
                self.assertIsNotNone(section, f"Missing Compose service {service}")
                self.assertIn(expected, section.group("body"))
                self.assertNotIn(
                    "RETRIEVAL_ONTOLOGY_PATH:-/app/ontology/jyotisha-v0.3.json",
                    section.group("body"),
                )


if __name__ == "__main__":
    unittest.main()
