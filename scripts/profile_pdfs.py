from __future__ import annotations

import argparse
import csv
import hashlib
import json
import mimetypes
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lib.config import BUILD_DIR, REPORTS_DIR, SQLITE_PATH, resolve_shared_asset_root
from lib.decode_lab.campaign_sets import list_campaign_sets, read_campaign_set


PROFILE_VERSION = "pdf_profile.v1"
CACHE_ROOT = PROJECT_ROOT / ".cache" / "pdf-profiles"
TOKEN_CACHE_DIR = CACHE_ROOT / "gemini-token-count"
CONTEXT_CACHE_TOKEN_THRESHOLD = 32_768
PAGE_TEXT_MIN_CHARS = 25


@dataclass(frozen=True)
class ProfileTarget:
    doc_id: str
    title: str
    asset_id: str
    local_rel_path: str | None
    gcs_key: str | None
    remote_url: str | None
    previous_checksum: str | None


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Profile primary PDF assets and populate asset_refs file facts plus "
            "pdf_profiles. Defaults to all primary PDFs, local-only, incremental."
        )
    )
    parser.add_argument(
        "--doc-id",
        action="append",
        help="Canonical document ID to profile. Repeatable. Defaults to all primary PDFs.",
    )
    parser.add_argument(
        "--set",
        action="append",
        dest="campaign_sets",
        choices=list_campaign_sets() or None,
        help="Campaign set to profile. Repeatable. Set files live under decode-lab/sets/.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=SQLITE_PATH,
        help="Canonical SQLite database to update. Default: .build~/spasta-corpus.sqlite.",
    )
    parser.add_argument(
        "--pdf-root",
        type=Path,
        default=resolve_shared_asset_root(),
        help="Local PDF corpus root. Default: resolved shared corpus root.",
    )
    parser.add_argument(
        "--token-count",
        choices=["none", "gemini"],
        default="none",
        help="Optional token counting. Default none avoids network/API calls.",
    )
    parser.add_argument(
        "--token-model",
        default="gemini-3-flash-preview",
        help="Gemini model name used for count_tokens when --token-count gemini.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute profiles even when checksum and profile version match.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Profile only the first N selected targets. Intended for smoke tests.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        help="Print one progress line every N targets. Default: 25.",
    )
    parser.add_argument(
        "--tool-timeout-seconds",
        type=int,
        default=30,
        help="Timeout for each local Poppler command. Default: 30 seconds.",
    )
    parser.add_argument(
        "--run-id",
        help=(
            "Optional audit/debug run label. When provided, writes run evidence "
            "under .build~/pdf-profile-runs/<run-id>/."
        ),
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Directory for pdf-profile.tsv and pdf-profile-audit.md.",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    run_profile(args)


def run_profile(args: argparse.Namespace) -> Path | None:
    if not args.db.exists():
        raise SystemExit(
            f"SQLite database not found: {args.db}. Run "
            "`uv run python scripts/build_corpus_metadata.py` first."
        )

    selected_doc_ids = _resolve_selected_doc_ids(args)
    tools = _available_tools(["pdfinfo", "pdffonts", "pdfimages", "pdftotext"])
    started_at = _utc_now()

    run_dir: Path | None = None
    changed_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        _assert_profile_schema(conn)
        targets = _load_targets(conn, selected_doc_ids)
        if args.limit is not None:
            targets = targets[: args.limit]
        total_targets = len(targets)
        for index, target in enumerate(targets, start=1):
            if index == 1 or index == total_targets or (
                args.progress_every > 0 and index % args.progress_every == 0
            ):
                print(f"[{index}/{total_targets}] profiling {target.doc_id}", flush=True)
            try:
                result = _profile_one(conn, target, args, tools)
            except Exception as exc:
                failure_rows.append(
                    {
                        "doc_id": target.doc_id,
                        "asset_id": target.asset_id,
                        "status": "failed",
                        "status_reason": str(exc),
                    }
                )
                continue
            if result["status"] == "skipped":
                skipped_rows.append(result)
            else:
                changed_rows.append(result)
        conn.commit()
        write_profile_reports(conn, args.reports_dir)
    finally:
        conn.close()

    if args.run_id:
        run_dir = BUILD_DIR / "pdf-profile-runs" / args.run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        _write_json(
            run_dir / "run-manifest.json",
            {
                "run_id": args.run_id,
                "started_at": started_at,
                "finished_at": _utc_now(),
                "command": sys.argv,
                "db": str(args.db),
                "pdf_root": str(args.pdf_root),
                "selected_doc_ids": selected_doc_ids,
                "campaign_sets": getattr(args, "campaign_sets", None) or [],
                "token_count": args.token_count,
                "token_model": args.token_model if args.token_count == "gemini" else None,
                "profile_version": PROFILE_VERSION,
                "tool_paths": tools,
            },
        )
        _write_jsonl(run_dir / "changed-assets.jsonl", changed_rows)
        _write_jsonl(run_dir / "skipped-assets.jsonl", skipped_rows)
        _write_jsonl(run_dir / "failures.jsonl", failure_rows)

    print(f"Profiled changed: {len(changed_rows)}")
    print(f"Profiled skipped: {len(skipped_rows)}")
    print(f"Profiled failed: {len(failure_rows)}")
    print(f"Wrote {args.reports_dir / 'pdf-profile.tsv'}")
    print(f"Wrote {args.reports_dir / 'pdf-profile-audit.md'}")
    if run_dir:
        print(f"Wrote {run_dir}")
    return run_dir


def _resolve_selected_doc_ids(args: argparse.Namespace) -> list[str] | None:
    selected: list[str] = []
    seen: set[str] = set()
    for set_name in getattr(args, "campaign_sets", None) or []:
        for doc_id in read_campaign_set(set_name):
            if doc_id not in seen:
                selected.append(doc_id)
                seen.add(doc_id)
    for doc_id in args.doc_id or []:
        if doc_id not in seen:
            selected.append(doc_id)
            seen.add(doc_id)
    return selected or None


def _assert_profile_schema(conn: sqlite3.Connection) -> None:
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }
    missing = {"asset_refs", "pdf_profiles", "primary_pdf_profiles"} - tables
    if missing:
        raise SystemExit(
            "SQLite schema is missing "
            + ", ".join(sorted(missing))
            + ". Rebuild with `uv run python scripts/build_corpus_metadata.py`."
        )


def _load_targets(
    conn: sqlite3.Connection, selected_doc_ids: list[str] | None
) -> list[ProfileTarget]:
    params: list[str] = []
    where = "WHERE ar.asset_role = 'primary_pdf'"
    if selected_doc_ids:
        placeholders = ", ".join("?" for _ in selected_doc_ids)
        where += f" AND d.doc_id IN ({placeholders})"
        params.extend(selected_doc_ids)

    rows = conn.execute(
        f"""
        SELECT
            d.doc_id,
            d.title,
            ar.asset_id,
            ar.local_rel_path,
            ar.gcs_key,
            ar.remote_url,
            ar.checksum AS previous_checksum
        FROM documents d
        JOIN asset_refs ar ON ar.doc_id = d.doc_id
        {where}
        ORDER BY d.doc_id
        """,
        params,
    ).fetchall()
    return [
        ProfileTarget(
            doc_id=row["doc_id"],
            title=row["title"],
            asset_id=row["asset_id"],
            local_rel_path=row["local_rel_path"],
            gcs_key=row["gcs_key"],
            remote_url=row["remote_url"],
            previous_checksum=row["previous_checksum"],
        )
        for row in rows
    ]


def _profile_one(
    conn: sqlite3.Connection,
    target: ProfileTarget,
    args: argparse.Namespace,
    tools: dict[str, str | None],
) -> dict[str, Any]:
    pdf_path = _pdf_path_for_target(args.pdf_root, target)
    if not pdf_path or not pdf_path.exists():
        return {
            "doc_id": target.doc_id,
            "asset_id": target.asset_id,
            "status": "failed",
            "status_reason": "Local PDF not found",
            "local_rel_path": target.local_rel_path,
        }

    checksum = _sha256_file(pdf_path)
    file_size_bytes = pdf_path.stat().st_size
    mime_type = mimetypes.guess_type(pdf_path.name)[0] or "application/pdf"

    existing = conn.execute(
        "SELECT * FROM pdf_profiles WHERE asset_id = ?", (target.asset_id,)
    ).fetchone()
    token_model = args.token_model if args.token_count == "gemini" else None
    needs_token_count = (
        args.token_count == "gemini"
        and (
            existing is None
            or existing["estimated_tokens"] is None
            or existing["token_model"] != token_model
        )
    )
    dirty = (
        args.force
        or existing is None
        or target.previous_checksum != checksum
        or existing["profile_version"] != PROFILE_VERSION
        or needs_token_count
    )

    _update_asset_facts(conn, target.asset_id, file_size_bytes, checksum, mime_type)

    if not dirty:
        return {
            "doc_id": target.doc_id,
            "asset_id": target.asset_id,
            "status": "skipped",
            "status_reason": "checksum and profile version unchanged",
            "checksum": checksum,
        }

    profile = _compute_local_profile(
        target.doc_id,
        pdf_path,
        tools,
        args.tool_timeout_seconds,
    )
    estimated_tokens: int | None = None
    context_cache_eligible: int | None = None
    if args.token_count == "gemini":
        estimated_tokens = _gemini_token_count(pdf_path, checksum, args.token_model)
        context_cache_eligible = (
            1 if estimated_tokens >= CONTEXT_CACHE_TOKEN_THRESHOLD else 0
        )
    elif existing is not None and existing["estimated_tokens"] is not None:
        estimated_tokens = existing["estimated_tokens"]
        token_model = existing["token_model"]
        context_cache_eligible = existing["context_cache_eligible"]

    conn.execute(
        """
        INSERT INTO pdf_profiles (
            asset_id,
            doc_type,
            page_count,
            text_page_count,
            raster_page_count,
            image_count,
            table_candidate_count,
            fonts_missing_unicode_map_count,
            estimated_tokens,
            token_model,
            context_cache_eligible,
            profile_version,
            profiled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asset_id) DO UPDATE SET
            doc_type = excluded.doc_type,
            page_count = excluded.page_count,
            text_page_count = excluded.text_page_count,
            raster_page_count = excluded.raster_page_count,
            image_count = excluded.image_count,
            table_candidate_count = excluded.table_candidate_count,
            fonts_missing_unicode_map_count = excluded.fonts_missing_unicode_map_count,
            estimated_tokens = excluded.estimated_tokens,
            token_model = excluded.token_model,
            context_cache_eligible = excluded.context_cache_eligible,
            profile_version = excluded.profile_version,
            profiled_at = excluded.profiled_at
        """,
        (
            target.asset_id,
            profile["doc_type"],
            profile["page_count"],
            profile["text_page_count"],
            profile["raster_page_count"],
            profile["image_count"],
            profile["table_candidate_count"],
            profile["fonts_missing_unicode_map_count"],
            estimated_tokens,
            token_model,
            context_cache_eligible,
            PROFILE_VERSION,
            _utc_now(),
        ),
    )
    return {
        "doc_id": target.doc_id,
        "asset_id": target.asset_id,
        "status": "profiled",
        "checksum": checksum,
        **profile,
        "estimated_tokens": estimated_tokens,
        "token_model": token_model,
        "context_cache_eligible": context_cache_eligible,
    }


def _pdf_path_for_target(pdf_root: Path, target: ProfileTarget) -> Path | None:
    rel_path = target.local_rel_path or target.gcs_key
    if not rel_path:
        return None
    return pdf_root / rel_path


def _compute_local_profile(
    doc_id: str,
    pdf_path: Path,
    tools: dict[str, str | None],
    tool_timeout_seconds: int,
) -> dict[str, Any]:
    pdfinfo = _run_tool(["pdfinfo", str(pdf_path)], tools, tool_timeout_seconds)
    page_count = _parse_page_count(pdfinfo.get("stdout", ""))

    pdffonts = _run_tool(["pdffonts", str(pdf_path)], tools, tool_timeout_seconds)
    fonts_missing_unicode_map_count = _fonts_missing_unicode_map_count(
        pdffonts.get("stdout", "")
    )

    pdfimages = _run_tool(["pdfimages", "-list", str(pdf_path)], tools, tool_timeout_seconds)
    image_count = _pdfimages_count(pdfimages.get("stdout", ""))

    text_page_count = 0
    table_candidate_count = 0
    if page_count:
        for page_number in range(1, page_count + 1):
            page_text = _pdftotext_page(
                pdf_path,
                page_number,
                tools,
                tool_timeout_seconds,
            )
            if len(page_text.strip()) >= PAGE_TEXT_MIN_CHARS:
                text_page_count += 1
            if _has_table_candidate(page_text):
                table_candidate_count += 1

    raster_page_count = (page_count - text_page_count) if page_count is not None else None
    if page_count is None:
        doc_type = "unknown"
    elif text_page_count == page_count:
        doc_type = "digital"
    elif text_page_count == 0:
        doc_type = "raster"
    else:
        doc_type = "mixed"

    return {
        "doc_type": doc_type,
        "page_count": page_count,
        "text_page_count": text_page_count if page_count is not None else None,
        "raster_page_count": raster_page_count,
        "image_count": image_count,
        "table_candidate_count": table_candidate_count,
        "fonts_missing_unicode_map_count": fonts_missing_unicode_map_count,
    }


def _gemini_token_count(pdf_path: Path, checksum: str, model: str) -> int:
    cache_key = hashlib.sha256(f"{checksum}\0{model}".encode("utf-8")).hexdigest()
    cache_path = TOKEN_CACHE_DIR / f"{cache_key[:16]}.json"
    if cache_path.exists():
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        if payload.get("cache_key") == cache_key:
            return int(payload["total_tokens"])

    from google import genai
    from google.genai import types
    import os

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is required for --token-count gemini")

    client = genai.Client(api_key=api_key)
    response = client.models.count_tokens(
        model=model,
        contents=[
            types.Part.from_bytes(
                data=pdf_path.read_bytes(),
                mime_type="application/pdf",
            )
        ],
    )
    total_tokens = int(response.total_tokens)
    TOKEN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(
        cache_path,
        {
            "cache_key": cache_key,
            "checksum": checksum,
            "model": model,
            "total_tokens": total_tokens,
            "created_at": _utc_now(),
        },
    )
    return total_tokens


def _update_asset_facts(
    conn: sqlite3.Connection,
    asset_id: str,
    file_size_bytes: int,
    checksum: str,
    mime_type: str,
) -> None:
    conn.execute(
        """
        UPDATE asset_refs
        SET file_size_bytes = ?,
            checksum = ?,
            mime_type = ?,
            availability_status = 'present'
        WHERE asset_id = ?
        """,
        (file_size_bytes, checksum, mime_type, asset_id),
    )


def write_profile_reports(conn: sqlite3.Connection, reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(
        """
        SELECT *
        FROM primary_pdf_profiles
        ORDER BY doc_id
        """
    ).fetchall()

    columns = [
        "doc_id",
        "title",
        "year",
        "journal_label",
        "gcs_key",
        "file_size_bytes",
        "checksum",
        "doc_type",
        "page_count",
        "text_page_count",
        "raster_page_count",
        "image_count",
        "table_candidate_count",
        "fonts_missing_unicode_map_count",
        "estimated_tokens",
        "token_model",
        "context_cache_eligible",
        "profile_version",
        "profiled_at",
    ]
    with (reports_dir / "pdf-profile.tsv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})

    profiled = [row for row in rows if row["profile_version"]]
    missing = [row for row in rows if not row["profile_version"]]
    by_type: dict[str, int] = {}
    for row in profiled:
        by_type[row["doc_type"]] = by_type.get(row["doc_type"], 0) + 1
    lines = [
        "# PDF Profile Audit",
        "",
        f"Generated: {_utc_now()}",
        "",
        f"- Primary PDF assets: {len(rows)}",
        f"- Profiled assets: {len(profiled)}",
        f"- Missing profiles: {len(missing)}",
        "",
        "## Document Types",
        "",
    ]
    if by_type:
        for doc_type, count in sorted(by_type.items()):
            lines.append(f"- `{doc_type}`: {count}")
    else:
        lines.append("- None profiled yet.")
    lines.extend(["", "## Missing Profiles", ""])
    for row in missing[:50]:
        lines.append(f"- `{row['doc_id']}` {row['gcs_key'] or ''}")
    if len(missing) > 50:
        lines.append(f"- ... {len(missing) - 50} more")
    if not missing:
        lines.append("- None.")
    (reports_dir / "pdf-profile-audit.md").write_text(
        "\n".join(lines).rstrip() + "\n",
        encoding="utf-8",
    )


def _available_tools(tool_names: list[str]) -> dict[str, str | None]:
    return {name: shutil.which(name) for name in tool_names}


def _run_tool(
    command: list[str],
    tools: dict[str, str | None],
    timeout_seconds: int,
) -> dict[str, Any]:
    tool = Path(command[0]).name
    if not tools.get(tool):
        return {"status": "skipped", "stdout": "", "stderr": f"{tool} not found"}
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return {
            "status": "timeout",
            "returncode": None,
            "stdout": stdout,
            "stderr": f"{tool} timed out after {timeout_seconds}s",
        }
    return {
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _pdftotext_page(
    pdf_path: Path,
    page_number: int,
    tools: dict[str, str | None],
    timeout_seconds: int,
) -> str:
    if not tools.get("pdftotext"):
        return ""
    try:
        completed = subprocess.run(
            [
                "pdftotext",
                "-layout",
                "-f",
                str(page_number),
                "-l",
                str(page_number),
                str(pdf_path),
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return ""
    return completed.stdout if completed.returncode == 0 else ""


def _parse_page_count(pdfinfo_output: str) -> int | None:
    for line in pdfinfo_output.splitlines():
        if line.startswith("Pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _fonts_missing_unicode_map_count(pdffonts_output: str) -> int:
    count = 0
    for line in pdffonts_output.splitlines():
        parts = line.split()
        if len(parts) < 6 or parts[0] in {"name", "------------------------------------"}:
            continue
        if parts[-3] == "no":
            count += 1
    return count


def _pdfimages_count(pdfimages_output: str) -> int:
    return sum(
        1
        for line in pdfimages_output.splitlines()
        if line.split() and line.split()[0].isdigit()
    )


def _has_table_candidate(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        header_window = "\n".join(lines[index : min(len(lines), index + 5)])
        if stripped.startswith("Table "):
            return True
        if (
            "Nakṣatra" in header_window
            and "Star Count" in header_window
            and "Yogatārā" in header_window
        ):
            return True
    return False


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    main()
