#!/usr/bin/env python3
"""Local audit workbench for decoded-corpus documents."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


TOOL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOL_DIR.parents[1]
STATIC_DIR = TOOL_DIR / "static"
STATE_DIR = TOOL_DIR / ".state"
ANNOTATIONS_LOG = STATE_DIR / "annotations.jsonl"
STATE_FILE = STATE_DIR / "state.json"
DECODED_ROOT = REPO_ROOT / "decoded-corpus"
SETS_ROOT = REPO_ROOT / "decode-lab" / "sets"
MANIFEST_JSONL = DECODED_ROOT / "manifest.jsonl"


def json_response(handler: BaseHTTPRequestHandler, payload: object, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def text_response(
    handler: BaseHTTPRequestHandler,
    body: str,
    status: int = 200,
    content_type: str = "text/plain; charset=utf-8",
) -> None:
    data = body.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def error_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, message: str) -> None:
    json_response(handler, {"error": message}, int(status))


def read_json(path: Path, default: object | None = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise


def load_manifest_index() -> list[dict]:
    docs: list[dict] = []
    if not MANIFEST_JSONL.exists():
        return docs
    for line in MANIFEST_JSONL.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        doc_id = row.get("doc_id")
        detail = load_doc_manifest(doc_id) if doc_id else {}
        source = detail.get("source", {}) if isinstance(detail, dict) else {}
        docs.append(
            {
                "doc_id": doc_id,
                "status": row.get("status"),
                "warning_count": row.get("warning_count", 0),
                "error_count": row.get("error_count", 0),
                "run_id": row.get("run_id"),
                "title": source.get("title"),
                "author_display": source.get("author_display"),
                "year": source.get("year"),
                "journal_label": source.get("journal_label"),
            }
        )
    return sorted(docs, key=lambda item: item.get("doc_id") or "")


def load_decode_sets() -> list[dict]:
    sets: list[dict] = []
    if not SETS_ROOT.exists():
        return sets
    for path in sorted(SETS_ROOT.glob("*.txt")):
        doc_ids: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            doc_ids.append(stripped.split("#", 1)[0].strip())
        sets.append({"name": path.stem, "path": str(path.relative_to(REPO_ROOT)), "doc_ids": doc_ids})
    return sets


def safe_doc_id(doc_id: str) -> str:
    if "/" in doc_id or "\\" in doc_id or doc_id in {"", ".", ".."}:
        raise ValueError("invalid doc id")
    return doc_id


def doc_dir(doc_id: str) -> Path:
    return DECODED_ROOT / "by-doc" / safe_doc_id(doc_id)


def load_doc_manifest(doc_id: str) -> dict:
    return read_json(doc_dir(doc_id) / "manifest.json", {})  # type: ignore[return-value]


def load_doc_quality(doc_id: str) -> dict:
    return read_json(doc_dir(doc_id) / "quality.json", {})  # type: ignore[return-value]


def load_state() -> dict:
    state = read_json(STATE_FILE, {"annotations": {}, "last_doc_id": None})
    if not isinstance(state, dict):
        return {"annotations": {}, "last_doc_id": None}
    state.setdefault("annotations", {})
    return state


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def update_annotation(doc_id: str, annotation: dict) -> dict:
    now = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    normalized = {
        "doc_id": doc_id,
        "updated_at": now,
        "review_status": str(annotation.get("review_status") or "unreviewed"),
        "page": str(annotation.get("page") or "").strip(),
        "location": str(annotation.get("location") or "").strip(),
        "comment": str(annotation.get("comment") or "").strip(),
    }

    state = load_state()
    annotations = state.setdefault("annotations", {})
    annotations[doc_id] = normalized
    state["last_doc_id"] = doc_id
    save_state(state)

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with ANNOTATIONS_LOG.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(normalized, ensure_ascii=False) + "\n")
    return normalized


def clear_annotation(doc_id: str) -> dict:
    now = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    state = load_state()
    annotations = state.setdefault("annotations", {})
    if isinstance(annotations, dict):
        annotations.pop(doc_id, None)
    state["last_doc_id"] = doc_id
    save_state(state)

    cleared = {"doc_id": doc_id, "updated_at": now, "action": "clear"}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with ANNOTATIONS_LOG.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(cleared, ensure_ascii=False) + "\n")
    return cleared


def export_markdown() -> str:
    state = load_state()
    annotations = state.get("annotations", {})
    if not isinstance(annotations, dict):
        annotations = {}
    generated_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    lines = [
        "# Decoder Audit Notes",
        "",
        f"- Generated At: {generated_at}",
        f"- Annotation Count: {len(annotations)}",
        "",
    ]
    for doc_id in sorted(annotations):
        item = annotations[doc_id]
        if not isinstance(item, dict):
            continue
        manifest = load_doc_manifest(doc_id)
        source = manifest.get("source", {}) if isinstance(manifest, dict) else {}
        title = source.get("title") or doc_id
        lines.extend(
            [
                f"## {doc_id}",
                "",
                f"- Title: {title}",
                f"- Review Status: {item.get('review_status', 'unreviewed')}",
                f"- Page: {item.get('page') or ''}",
                f"- Location: {item.get('location') or ''}",
                f"- Updated At: {item.get('updated_at') or ''}",
                "",
                str(item.get("comment") or "").strip() or "_No comment._",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_export() -> Path:
    reports_dir = REPO_ROOT / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = reports_dir / f"decoder-audit-{stamp}.md"
    path.write_text(export_markdown(), encoding="utf-8")
    return path


def serve_file(handler: BaseHTTPRequestHandler, path: Path, content_type: str | None = None) -> None:
    if not path.exists() or not path.is_file():
        error_response(handler, HTTPStatus.NOT_FOUND, "file not found")
        return

    size = path.stat().st_size
    start = 0
    end = size - 1
    status = HTTPStatus.OK
    range_header = handler.headers.get("Range")
    if range_header and range_header.startswith("bytes="):
        range_spec = range_header.removeprefix("bytes=").split(",", 1)[0]
        left, _, right = range_spec.partition("-")
        try:
            if left:
                start = int(left)
            if right:
                end = int(right)
            if start < 0 or end >= size or start > end:
                raise ValueError
            status = HTTPStatus.PARTIAL_CONTENT
        except ValueError:
            handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            handler.send_header("Content-Range", f"bytes */{size}")
            handler.end_headers()
            return

    guessed = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    length = end - start + 1
    handler.send_response(status)
    handler.send_header("Content-Type", guessed)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(length))
    if status == HTTPStatus.PARTIAL_CONTENT:
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    handler.end_headers()

    with path.open("rb") as fp:
        fp.seek(start)
        remaining = length
        while remaining:
            chunk = fp.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)


class AuditDecoderHandler(BaseHTTPRequestHandler):
    server_version = "audit-decoder/0.1"

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            self.route_get(path)
        except ValueError as exc:
            error_response(self, HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001 - local tool should report failures.
            error_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            self.route_post(path)
        except ValueError as exc:
            error_response(self, HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001
            error_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        try:
            self.route_delete(path)
        except ValueError as exc:
            error_response(self, HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # noqa: BLE001
            error_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def route_get(self, path: str) -> None:
        if path in {"/", "/index.html"}:
            serve_file(self, STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if path.startswith("/static/"):
            name = path.removeprefix("/static/")
            static_path = (STATIC_DIR / name).resolve()
            if not static_path.is_relative_to(STATIC_DIR):
                raise ValueError("invalid static path")
            serve_file(self, static_path)
            return
        if path == "/api/docs":
            json_response(self, {"docs": load_manifest_index(), "state": load_state()})
            return
        if path == "/api/sets":
            json_response(self, {"sets": load_decode_sets()})
            return
        if path == "/api/annotations":
            json_response(self, load_state())
            return
        if path == "/api/export-markdown":
            text_response(self, export_markdown(), content_type="text/markdown; charset=utf-8")
            return

        parts = [part for part in path.split("/") if part]
        if len(parts) >= 3 and parts[:2] == ["api", "docs"]:
            doc_id = safe_doc_id(parts[2])
            if len(parts) == 3:
                state = load_state()
                json_response(
                    self,
                    {
                        "manifest": load_doc_manifest(doc_id),
                        "quality": load_doc_quality(doc_id),
                        "annotation": state.get("annotations", {}).get(doc_id),
                    },
                )
                return
            if len(parts) == 4 and parts[3] == "markdown":
                md_path = doc_dir(doc_id) / "document.md"
                text_response(self, md_path.read_text(encoding="utf-8"), content_type="text/markdown; charset=utf-8")
                return
            if len(parts) == 4 and parts[3] == "pdf":
                manifest = load_doc_manifest(doc_id)
                source_pdf = manifest.get("source_pdf") or manifest.get("source", {}).get("local_pdf_path")
                if not source_pdf:
                    error_response(self, HTTPStatus.NOT_FOUND, "source pdf not recorded")
                    return
                serve_file(self, Path(source_pdf), "application/pdf")
                return
            if len(parts) == 5 and parts[3] == "media":
                media_name = parts[4]
                if "/" in media_name or "\\" in media_name or media_name in {"", ".", ".."}:
                    raise ValueError("invalid media path")
                serve_file(self, doc_dir(doc_id) / "media" / media_name)
                return

        error_response(self, HTTPStatus.NOT_FOUND, "not found")

    def route_post(self, path: str) -> None:
        if path == "/api/export-markdown":
            out = write_export()
            json_response(self, {"path": str(out)})
            return
        parts = [part for part in path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "annotations"]:
            doc_id = safe_doc_id(parts[2])
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            annotation = json.loads(body)
            if not isinstance(annotation, dict):
                raise ValueError("annotation must be a JSON object")
            json_response(self, {"annotation": update_annotation(doc_id, annotation)})
            return
        error_response(self, HTTPStatus.NOT_FOUND, "not found")

    def route_delete(self, path: str) -> None:
        parts = [part for part in path.split("/") if part]
        if len(parts) == 3 and parts[:2] == ["api", "annotations"]:
            doc_id = safe_doc_id(parts[2])
            json_response(self, {"cleared": clear_annotation(doc_id)})
            return
        error_response(self, HTTPStatus.NOT_FOUND, "not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local audit-decoder workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if not MANIFEST_JSONL.exists():
        raise SystemExit(f"missing decoded corpus manifest: {MANIFEST_JSONL}")

    server = ThreadingHTTPServer((args.host, args.port), AuditDecoderHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"audit-decoder listening on {url}")
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping audit-decoder")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
