#!/usr/bin/env python3
"""Validate a clean Sanchaya revision and write a retrieval input manifest.

This command is read-only with respect to Sanchaya.  It records the exact Git
commit, file hashes, and the fixed 29-paper/30-file selection used by the
embedding bakeoff.  Generated output belongs to the semantic-index repo.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_chunks import script_counts, sha256_file, tokenize


JYOTISHAM_PROBE_PATHS = [
    "Jyotisham/Adbhutasagara - मूलम्.csv.txt",
    "Jyotisham/aryabhatiya with bhashya.txt",
    "Jyotisham/aryabhatiya.txt",
    "Jyotisham/bhaskara, bijaganitam.txt",
    "Jyotisham/Bhaskara2, siddhanta shiromani, partial.txt",
    "Jyotisham/brahmasputha siddhanta.txt",
    "Jyotisham/brhat samudrika shastra.txt",
    "Jyotisham/brihajjataka.txt",
    "Jyotisham/chinese astro text with g translate.txt",
    "Jyotisham/IAST suryasiddhanta.txt",
    "Jyotisham/IAST varahamihira, tikinikaya.txt",
    "Jyotisham/IAST-brahmasputasiddhanta.txt",
    "Jyotisham/leelavati bhaskara.txt",
    "Jyotisham/muhurta chintamani.txt",
    "Jyotisham/naradasamhita.txt",
    "Jyotisham/nilakantha, aryabhatiya bhashya.txt",
    "Jyotisham/parashara hora shastra.txt",
    "Jyotisham/Parashara tantra.txt",
    "Jyotisham/parasharatantra ocr.txt",
    "Jyotisham/surya siddhanta.txt",
    "Jyotisham/vedanga jyotisham ric.txt",
    "Jyotisham/vedanga jyotisham yajusha.txt",
    "Jyotisham/vrrddha-gaargiiya-jyotisham.txt",
    "Jyotisham/yogayatra of varahamihira.txt",
]

ANCHOR_PROBE_PATHS = [
    "Vedic texts/AV/atharvaveda parishishta.txt",
    "gretil/sa_atharvavedapariziSTas.txt",
    "Puranani/brahmanda purana.txt",
    "gretil/sa_brahmANDapurANa.txt",
    "Bauddha/shardula karnavadanam.txt",
    "gretil/sa_zArdUlakarNAvadAna.txt",
]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_no}: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"expected object at {path}:{line_no}")
            rows.append(row)
    return rows


def file_record(root: Path, repo_path: str, *, source_id: str, source_kind: str, **extra: Any) -> dict[str, Any]:
    path = root / repo_path
    if not path.is_file():
        raise FileNotFoundError(f"selected source file is missing: {repo_path}")
    text = path.read_text(encoding="utf-8")
    row: dict[str, Any] = {
        "source_id": source_id,
        "source_kind": source_kind,
        "repo_path": repo_path,
        "content_sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "token_estimate": len(tokenize(text)),
        "script_counts": script_counts(text),
    }
    row.update({key: value for key, value in extra.items() if value is not None})
    return row


def load_audit_ids(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def build_manifest(sanchaya_root: Path, audit_set: Path) -> dict[str, Any]:
    status = run_git(sanchaya_root, "status", "--porcelain")
    if status:
        raise RuntimeError(
            "Sanchaya checkout is dirty; commit/stash it before a reproducible bakeoff:\n" + status
        )
    commit = run_git(sanchaya_root, "rev-parse", "HEAD")
    corpus_manifest_path = sanchaya_root / "patra-darpan" / "catalog" / "corpus-manifest.jsonl"
    corpus_rows = read_jsonl(corpus_manifest_path)
    by_doc = {str(row.get("source_doc_id")): row for row in corpus_rows}
    paper_ids = load_audit_ids(audit_set)
    if len(paper_ids) != 29:
        raise ValueError(f"expected 29 audit papers, found {len(paper_ids)} in {audit_set}")

    papers: list[dict[str, Any]] = []
    for doc_id in paper_ids:
        row = by_doc.get(doc_id)
        if row is None:
            raise ValueError(f"audit document is absent from Sanchaya manifest: {doc_id}")
        repo_path = str(row["repo_path"])
        record = file_record(
            sanchaya_root,
            repo_path,
            source_id=str(row["document_id"]),
            source_kind="patra-darpan",
            document_id=row.get("document_id"),
            source_doc_id=doc_id,
            title=row.get("title"),
            categories=row.get("categories", []),
            quality_status=row.get("quality_status"),
            media_prefix=row.get("media_prefix"),
        )
        expected_hash = str(row.get("content_sha256") or "")
        if expected_hash and expected_hash != record["content_sha256"]:
            raise ValueError(f"content hash mismatch for {repo_path}: manifest is stale")
        papers.append(record)

    probes: list[dict[str, Any]] = []
    for repo_path in [*JYOTISHAM_PROBE_PATHS, *ANCHOR_PROBE_PATHS]:
        probes.append(
            file_record(
                sanchaya_root,
                repo_path,
                source_id=f"sanchaya:{repo_path}",
                source_kind="sanchaya",
                document_id=f"sanchaya:{repo_path}",
                title=Path(repo_path).stem,
            )
        )

    return {
        "schema_version": "retrieval.input-manifest.v1",
        "generated_at": utc_now(),
        "sanchaya": {
            "root": str(sanchaya_root),
            "commit": commit,
            "status": "clean",
            "corpus_manifest": "patra-darpan/catalog/corpus-manifest.jsonl",
            "corpus_manifest_sha256": sha256_file(corpus_manifest_path),
        },
        "selection": {
            "audit_set": str(audit_set),
            "paper_count": len(papers),
            "probe_count": len(probes),
            "jyotisham_probe_count": len(JYOTISHAM_PROBE_PATHS),
            "anchor_probe_count": len(ANCHOR_PROBE_PATHS),
        },
        "sources": [*papers, *probes],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sanchaya-root",
        type=Path,
        default=Path(os.environ.get("SANCHAYA_REPO_ROOT", "~/projects/sanchaya")).expanduser(),
    )
    parser.add_argument("--audit-set", type=Path, default=ROOT / "decode-lab" / "sets" / "audit-set.txt")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / ".local" / "retrieval" / "input-manifest.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_manifest(args.sanchaya_root.expanduser().resolve(), args.audit_set.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {args.output}: commit={manifest['sanchaya']['commit']} "
        f"papers={manifest['selection']['paper_count']} probes={manifest['selection']['probe_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
