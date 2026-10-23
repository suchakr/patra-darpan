#!/usr/bin/env python3
"""Exercise catalogue SQL locally, without starting MCP or contacting any backend."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import load_release
from lib.retrieval_catalog import CatalogAdapter
from lib.retrieval_catalog_sql import CatalogSQLService, mcp_envelope


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, help="Saved release.json / active-release.json (operator path)")
    parser.add_argument("--expect-patra-records", type=int)
    parser.add_argument("--expect-indexed-patra-records", type=int)
    args = parser.parse_args()
    release = load_release(args.release)
    catalog = CatalogAdapter(release)
    try:
        service = CatalogSQLService(catalog)
        queries = {
            "coverage": "SELECT source_kind, COUNT(*) AS catalogued, SUM(indexed_in_release) AS indexed "
                        "FROM documents_v GROUP BY source_kind ORDER BY source_kind",
            "authors": service.schema()["examples"][0]["sql"],
            "decades": service.schema()["examples"][1]["sql"],
            "alias": "SELECT author_id,author_norm,COUNT(DISTINCT document_id) AS works FROM authors_v "
                     "WHERE author_id='author:s-mahdihassan' GROUP BY author_id,author_norm",
        }
        results = {}
        for name, query in queries.items():
            result = service.run_sql(query)
            if "error" in result or result["truncated"]:
                raise RuntimeError(f"Incomplete {name} smoke result: {result}")
            if len(json.dumps(mcp_envelope(result), ensure_ascii=False, separators=(",", ":")).encode()) >= 64000:
                raise RuntimeError("MCP result exceeded its byte limit")
            results[name] = result
        pd = next(row for row in results["coverage"]["rows"] if row[0] == "patra-darpan")
        for actual, expected in ((pd[1], args.expect_patra_records), (pd[2], args.expect_indexed_patra_records)):
            if expected is not None and actual != expected:
                raise RuntimeError(f"Expected {expected}, found {actual} at {release.release_id}")
        if sum(row[1] for row in results["decades"]["rows"]) != pd[1]:
            raise RuntimeError("Decade groups did not reconcile with catalogue total")
        print(json.dumps({"status": "passed", "schema": service.schema(), "queries": results},
                         ensure_ascii=False, indent=2))
        return 0
    finally:
        catalog.close()


if __name__ == "__main__":
    raise SystemExit(main())
