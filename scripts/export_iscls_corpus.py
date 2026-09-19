#!/usr/bin/env python3
"""Export accepted decoded papers into a Sanchaya ISCLS worktree."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.iscls_export import DEFAULT_GCS_BUCKET, export_documents, write_audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or apply a deterministic export of decoded Patra Darpan Markdown "
            "and media into a Sanchaya worktree. Indexes are built separately."
        )
    )
    parser.add_argument("--decoded-root", type=Path, default=ROOT / "decoded-corpus")
    parser.add_argument(
        "--sanchaya-root",
        type=Path,
        default=Path(os.environ.get("SANCHAYA_REPO_ROOT", "~/projects/sanchaya")).expanduser(),
    )
    parser.add_argument("--index-tsv", type=Path, default=ROOT / "exports" / "index.tsv")
    parser.add_argument("--doc-id", action="append", default=[], help="Export only this doc ID (repeatable).")
    parser.add_argument("--gcs-bucket", default=DEFAULT_GCS_BUCKET)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the projection. Without this flag the command is a dry-run.",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Replace an existing exported paper directory when its content differs.",
    )
    parser.add_argument("--audit-output", type=Path, help="Optional JSON audit report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = export_documents(
        decoded_root=args.decoded_root,
        sanchaya_root=args.sanchaya_root,
        doc_ids=args.doc_id or None,
        index_tsv=args.index_tsv,
        gcs_bucket=args.gcs_bucket,
        apply=args.apply,
        replace_existing=args.replace_existing,
    )
    if args.audit_output:
        write_audit(args.audit_output, result)
    mode = "Applied" if args.apply else "Dry-run"
    print(f"{mode}: selected={len(result.selected)} exported={len(result.exported)} skipped={len(result.skipped)}")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
