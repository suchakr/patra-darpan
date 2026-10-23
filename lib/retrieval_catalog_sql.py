"""Bounded SQL over a public projection of one verified release catalogue.

Design: preserve source artifacts, expose views only, and execute untrusted SQL
in a disposable process with no catalogue path or credential passed to it.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from contextvars import ContextVar
import hashlib
import hmac
import json
import logging
import multiprocessing
import re
import secrets
import sqlite3
import threading
import time
import unicodedata
from typing import Any

from lib.retrieval_catalog import CatalogAdapter

SCHEMA_VERSION = "retrieval.catalog-sql.v1"
NORMALIZATION_VERSION = "catalog-names-years.v1"
MAX_SQL_BYTES = 8192
MAX_ROWS = 1000
WIRE_BUDGET = 63000  # Includes duplicate text/structured content; reserve RPC envelope.
DEADLINE_SECONDS = 5.0
LOG = logging.getLogger("retrieval.catalog_sql")
BEARER_SQL_ID: ContextVar[str | None] = ContextVar("catalog_sql_bearer_id", default=None)
_TOKEN_SALT = secrets.token_bytes(32)

# Explicit alias evidence: corpus/ijhs.tsv, IJHS 19 (1984) issue 1 and
# IJHS 26 (1991) issues 1–2: author fields and PDF basenames cross the spellings.
AUTHOR_ALIASES = {
    "s mahdihassan": ("author:s-mahdihassan", "S Mahdihassan"),
    "s mahadihassan": ("author:s-mahdihassan", "S Mahdihassan"),
}

VIEW_COLUMNS = {
    "documents_v": {
        "document_id": "TEXT", "title": "TEXT nullable", "year": "INTEGER nullable",
        "year_raw": "TEXT nullable", "journal": "TEXT nullable", "source_kind": "TEXT",
        "source_collection": "TEXT", "document_type": "TEXT",
        "indexed_in_release": "INTEGER 0|1", "pdf_uri": "TEXT nullable",
    },
    "authors_v": {
        "document_id": "TEXT", "author_id": "TEXT nullable", "author_norm": "TEXT nullable",
        "author_raw": "TEXT", "author_name_raw": "TEXT", "position": "INTEGER 1-based",
        "resolution_status": "TEXT alias|unreviewed|ambiguous",
    },
    "subjects_v": {"document_id": "TEXT", "subject": "TEXT", "provenance": "TEXT"},
    "coverage_v": {"source_kind": "TEXT", "source_collection": "TEXT",
                   "indexed_in_release": "INTEGER 0|1", "document_count": "INTEGER"},
}

EXAMPLES = [
    {"question": "Which authors have the most catalogued works?",
     "sql": "SELECT author_id, author_norm, COUNT(DISTINCT document_id) AS works "
            "FROM authors_v WHERE author_id IS NOT NULL GROUP BY author_id, author_norm "
            "ORDER BY works DESC, author_id LIMIT 20"},
    {"question": "How are Patra Darpaṇa records distributed by decade, including unknown dates?",
     "sql": "SELECT CASE WHEN year IS NULL THEN 'unknown' ELSE CAST((year / 10) * 10 AS TEXT) END "
            "AS decade, COUNT(*) AS records, SUM(indexed_in_release) AS full_text "
            "FROM documents_v WHERE source_kind = 'patra-darpan' GROUP BY decade ORDER BY decade"},
]

_TABLES = {"documents_v": "_documents", "authors_v": "_authors", "subjects_v": "_subjects",
           "coverage_v": "_documents"}
_FUNCTIONS = frozenset("count sum avg min max total group_concat coalesce ifnull nullif "
                       "lower upper trim ltrim rtrim substr substring replace instr length "
                       "abs round typeof unicode like glob".split())
_SCHEMA = """
CREATE TABLE _documents(document_id TEXT PRIMARY KEY, title TEXT, year INTEGER, year_raw TEXT,
 journal TEXT, source_kind TEXT, source_collection TEXT, document_type TEXT,
 indexed_in_release INTEGER, pdf_uri TEXT);
CREATE TABLE _authors(document_id TEXT, author_id TEXT, author_norm TEXT, author_raw TEXT,
 author_name_raw TEXT, position INTEGER, resolution_status TEXT);
CREATE TABLE _subjects(document_id TEXT, subject TEXT, provenance TEXT);
CREATE VIEW documents_v AS SELECT * FROM _documents;
CREATE VIEW authors_v AS SELECT * FROM _authors;
CREATE VIEW subjects_v AS SELECT * FROM _subjects;
CREATE VIEW coverage_v AS SELECT source_kind, source_collection, indexed_in_release,
 COUNT(*) AS document_count FROM _documents GROUP BY source_kind, source_collection, indexed_in_release;
"""

# SQLite reports a CTE's name as an authorization source just like a stored
# view. Reject references to private identifiers independently of that source.
# Tokenize comments and all SQLite quoting styles, including single-quoted
# identifiers, rather than searching a raw substring or trusting CTE names.
_TOKENS = re.compile(r"--[^\n]*(?:\n|$)|/\*.*?\*/|'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
                     r"`(?:``|[^`])*`|\[[^]]*\]|[\w$]+|.", re.S)


def _private_identifier(query: str) -> bool:
    for match in _TOKENS.finditer(query):
        token = match.group()
        if token.startswith(("--", "/*")):
            continue
        if token[:1] in ("'", '"', "`", "["):
            quote = token[0]
            token = token[1:-1].replace(quote * 2, quote)
        if token.casefold() in set(_TABLES.values()):
            return True
    return False


class CatalogSQLError(ValueError):
    """Safe SQL configuration or validation failure."""


def token_identifier(token: str) -> str:
    """Never retain a credential as a log/quota key."""
    return hmac.new(_TOKEN_SALT, token.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def mcp_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": _json(payload)}],
            "structuredContent": payload, "isError": "error" in payload}


def _wire_size(payload: dict[str, Any]) -> int:
    return len(_json(mcp_envelope(payload)).encode("utf-8"))


def _name_key(name: str) -> str:
    text = unicodedata.normalize("NFC", name).casefold().replace(".", " ")
    return " ".join(text.split())


def _split_authors(raw: str) -> tuple[list[str], bool]:
    # Source feeds sometimes put a journal/publisher label in the author field.
    # Preserve that evidence, but do not rank it as a normalized person.
    if (_name_key(raw) in {"ijhs", "insa", "review report", "reviewreport", "unknown", "n/a", "na"}
            or re.search(r"\bet\s+al\b|\b(?:committee|council|university|society|department|editorial|editors|anonymous)\b",
                         raw, re.I)):
        return [raw], True
    parts = [p.strip(" .") for p in re.split(r"\s+and\s+|\s*&\s*|[;·]", raw, flags=re.I) if p.strip(" .")]
    output = []
    ambiguous = False
    for part in parts:
        if "," not in part:
            output.append(part)
            continue
        comma_parts = [p.strip() for p in part.split(",")]
        if all(re.fullmatch(r"(?:[A-Z]\.?(?:\s+|(?=[A-Z])))*[A-Z]\.?(?:\s+[^,]+)?", p)
               for p in comma_parts):
            output.extend(comma_parts)
        else:
            output.append(part)
            ambiguous = True
    return output or [raw], ambiguous


def _year(raw: Any) -> int | None:
    value = str(raw or "").strip()
    return int(value.split(".")[0]) if re.fullmatch(r"[1-9][0-9]{3}(?:\.0+)?", value) else None


def project_records(records: list[dict[str, Any]]) -> dict[str, list[list[Any]]]:
    """Deterministic public projection; no source files are changed."""
    documents, authors, subjects = [], [], []
    origins = {"portal_ijhs_metadata": "ijhs", "curated_pdf_metadata": "curated-pdfs",
               "curated_link_metadata": "curated-links"}
    for row in sorted(records, key=lambda r: r["document_id"]):
        doc_id, kind = row["document_id"], row["source_kind"]
        refs = row.get("source_refs") or []
        collections = {origins[r["role"]] for r in refs if r.get("role") in origins}
        collection = (next(iter(collections)) if len(collections) == 1 else
                      "mixed" if collections else "sanchaya" if kind == "sanchaya" else "unknown")
        pdf = next((r.get("uri") for r in refs if r.get("role") == "primary_pdf"
                    and str(r.get("uri", "")).startswith(("https://", "http://"))), None)
        documents.append([doc_id, row.get("title"), _year(row.get("year")), row.get("year"),
                          row.get("journal"), kind, collection,
                          "source_text" if kind == "sanchaya" else "unknown",
                          int(bool(row.get("indexed_in_release"))), pdf])
        position = 0
        for raw in row.get("authors") or []:
            raw = str(raw).strip()
            if not raw:
                continue
            names, ambiguous = _split_authors(raw)
            for name in names:
                position += 1
                key = _name_key(name)
                alias = AUTHOR_ALIASES.get(key)
                author_id, norm = (None, None) if ambiguous else (
                    alias if alias else ("author:" + hashlib.sha256(key.encode()).hexdigest()[:24],
                                         " ".join(name.split())))
                authors.append([doc_id, author_id, norm, raw, name, position,
                                "ambiguous" if ambiguous else "alias" if alias else "unreviewed"])
        for subject in sorted({str(s).strip() for s in row.get("categories") or [] if str(s).strip()}):
            subjects.append([doc_id, subject, "release-catalogue-tag"])
    # Pick one stable display spelling for each normalized identity.
    displays: dict[str, str] = {}
    for row in authors:
        if row[1] is not None:
            displays[row[1]] = min(displays.get(row[1], row[2]), row[2])
    for row in authors:
        if row[1] is not None:
            row[2] = displays[row[1]]
    return {"documents": documents, "authors": authors, "subjects": subjects}


def _authorize(action: int, arg1: str | None, arg2: str | None,
               database: str | None, source: str | None) -> int:
    if action == sqlite3.SQLITE_SELECT:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_READ:
        if database == "main" and (arg1 in VIEW_COLUMNS or (source in _TABLES and arg1 == _TABLES[source])):
            return sqlite3.SQLITE_OK
        # SQLite's COUNT(*) / constant projection optimization produces a
        # column-less base read without view provenance. SQLite 3.46 also
        # omits the database name here; 3.50 reports "main". Private identifier
        # validation has already ruled out direct references to these tables.
        if database in (None, "main") and arg1 in _TABLES.values() and arg2 == "" and source is None:
            return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION and (arg2 or "").lower() in _FUNCTIONS:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_RECURSIVE:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def _connection(projection: dict[str, list[list[Any]]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.enable_load_extension(False)
    conn.execute("PRAGMA hard_heap_limit=67108864")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA trusted_schema=OFF")
    if hasattr(conn, "setconfig") and hasattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE"):
        conn.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
    conn.executescript(_SCHEMA)
    for name, columns in (("documents", 10), ("authors", 7), ("subjects", 3)):
        conn.executemany(f"INSERT INTO _{name} VALUES ({','.join('?' for _ in range(columns))})",
                         projection[name])
    conn.commit()
    conn.execute("PRAGMA query_only=ON")
    limits = {"LENGTH": 64000, "SQL_LENGTH": MAX_SQL_BYTES, "COLUMN": 32,
              "EXPR_DEPTH": 30, "COMPOUND_SELECT": 5, "VDBE_OP": 100000,
              "FUNCTION_ARG": 8, "ATTACHED": 0, "VARIABLE_NUMBER": 0}
    for name, limit in limits.items():
        conn.setlimit(getattr(sqlite3, "SQLITE_LIMIT_" + name), limit)
    conn.set_authorizer(_authorize)
    return conn


def _failure(base: dict[str, Any], code: str, message: str) -> dict[str, Any]:
    return {**base, "columns": [], "rows": [], "row_count": 0, "truncated": False,
            "truncation_reason": None, "error": {"code": code, "message": message}}


def _worker(pipe: Any, projection: dict[str, list[list[Any]]], base: dict[str, Any],
            max_rows: int, deadline_seconds: float) -> None:
    """Fresh spawn: only public records and SQL enter this execution context."""
    conn = None
    started = time.monotonic()
    try:
        conn = _connection(projection)
        conn.set_progress_handler(lambda: int(time.monotonic() - started >= deadline_seconds), 1000)
        cursor = conn.execute(base["sql"])
        result = {**base, "columns": [c[0] for c in cursor.description], "rows": [],
                  "row_count": 0, "truncated": False, "truncation_reason": None}
        for row in cursor:
            if len(result["rows"]) >= max_rows:
                result.update(truncated=True, truncation_reason="max_rows")
                break
            result["rows"].append(list(row))
            result["row_count"] = len(result["rows"])
            # Reserve bytes for the longer truncation metadata before accepting a row.
            trial = {**result, "truncated": True, "truncation_reason": "response_bytes"}
            if _wire_size(trial) > WIRE_BUDGET:
                result["rows"].pop()
                result.update(row_count=len(result["rows"]), truncated=True,
                              truncation_reason="response_bytes")
                break
        if _wire_size(result) > WIRE_BUDGET:
            result = _failure(base, "result_too_large", "Column metadata exceeds the response budget.")
    except (sqlite3.Error, MemoryError, ValueError, TypeError) as exc:
        timed_out = time.monotonic() - started >= deadline_seconds
        result = _failure(base, "timeout" if timed_out else "query_rejected",
                          "Query exceeded the execution deadline." if timed_out else
                          "Query rejected: " + str(exc)[:240])
    finally:
        if conn is not None:
            conn.close()
    try:
        pipe.send_bytes(_json(result).encode("utf-8"))
    finally:
        pipe.close()


class CatalogSQLService:
    def __init__(self, catalog: CatalogAdapter, *, deadline_seconds: float = DEADLINE_SECONDS,
                 per_token_limit: int = 12, global_limit: int = 60, concurrency: int = 2):
        if catalog.conn is None or catalog.catalog_schema_version < 2:
            raise CatalogSQLError("Catalogue SQL requires a verified v2 SQLite release catalogue.")
        artifact_hash = catalog.release.artifact_hash("retrieval_catalog")
        if not artifact_hash or artifact_hash != catalog.release.catalog_revision:
            raise CatalogSQLError("Catalogue SQL requires matching artifact and catalogue revisions.")
        records = [catalog._public(row, corpus_revision=catalog.release.corpus_revision)
                   for row in catalog.conn.execute("SELECT * FROM documents ORDER BY doc_id")]
        self.projection = project_records(records)
        self.revisions = {"catalog_revision": catalog.release.catalog_revision,
                          "corpus_revision": catalog.release.corpus_revision,
                          "release_id": catalog.release.release_id,
                          "normalization_version": NORMALIZATION_VERSION}
        self.revisions["analytics_revision"] = hashlib.sha256(_json(
            {"data": self.projection, "aliases": AUTHOR_ALIASES,
             "normalization": NORMALIZATION_VERSION, "schema": SCHEMA_VERSION,
             "view_columns": VIEW_COLUMNS, "view_sql": _SCHEMA}).encode()).hexdigest()
        self.deadline_seconds = min(float(deadline_seconds), DEADLINE_SECONDS)
        self.per_token_limit, self.global_limit = per_token_limit, global_limit
        self._lock = threading.Lock()
        self._tokens: OrderedDict[str, deque[float]] = OrderedDict()
        self._global: deque[float] = deque()
        self._slots = threading.BoundedSemaphore(concurrency)

    def schema(self) -> dict[str, Any]:
        docs, authors, subjects = (self.projection[k] for k in ("documents", "authors", "subjects"))
        return {"schema_version": SCHEMA_VERSION, **self.revisions, "views": VIEW_COLUMNS,
                "examples": EXAMPLES,
                "limits": {"deadline_seconds": DEADLINE_SECONDS, "default_rows": 500,
                           "max_rows": MAX_ROWS, "response_bytes": 64000, "sql_bytes": MAX_SQL_BYTES,
                           "per_token_per_minute": self.per_token_limit,
                           "global_per_minute": self.global_limit},
                "semantics": [
                    "Count catalogue records, not necessarily papers; Patra Darpaṇa document_type is unknown.",
                    "indexed_in_release means this release's passage/vector coverage, not all Zoekt coverage.",
                    "Include year IS NULL when reconciling annual/decade totals; year_raw is preserved.",
                    "COUNT(DISTINCT document_id) per author; co-authorship totals are not additive.",
                    "author_id groups normalized name identities, not disambiguated people; unreviewed may contain homonyms or aliases.",
                    "Ambiguous names have NULL author_id/author_norm. Missing authors have no authors_v row.",
                    "Subject tags are incomplete; subjects_v is not complete subject classification.",
                    "row_count counts returned rows only. Inspect truncated before claiming completeness.",
                    "Use ORDER BY and keyset predicates to page lists that exceed row/byte limits.",
                    "Only listed views and safe functions are queryable; raw tables and pragmas are denied."],
                "safe_functions": sorted(_FUNCTIONS),
                "known_issues": {
                    "unknown_year_documents": sum(d[2] is None for d in docs),
                    "unknown_type_documents": sum(d[7] == "unknown" for d in docs),
                    "missing_author_documents": len({d[0] for d in docs} - {a[0] for a in authors}),
                    "ambiguous_author_occurrences": sum(a[6] == "ambiguous" for a in authors),
                    "unreviewed_author_occurrences": sum(a[6] == "unreviewed" for a in authors),
                    "untagged_documents": len({d[0] for d in docs} - {s[0] for s in subjects})}}

    def _admit(self, token_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            while self._global and self._global[0] <= now - 60:
                self._global.popleft()
            events = self._tokens.setdefault(token_id, deque())
            self._tokens.move_to_end(token_id)
            while events and events[0] <= now - 60:
                events.popleft()
            if len(events) >= self.per_token_limit or len(self._global) >= self.global_limit:
                return False
            events.append(now)
            self._global.append(now)
            while len(self._tokens) > 1024:
                self._tokens.popitem(last=False)
            return True

    def run_sql(self, query: str, max_rows: int = 500, token_id: str = "local") -> dict[str, Any]:
        started = time.monotonic()
        valid_query = isinstance(query, str) and len(query) <= MAX_SQL_BYTES
        if valid_query:
            try:
                valid_query = len(query.encode("utf-8")) <= MAX_SQL_BYTES
            except UnicodeError:
                valid_query = False
        base = {"schema_version": SCHEMA_VERSION, **self.revisions,
                "sql": query if valid_query else ""}
        # Escaped control characters can make even an 8 KiB SQL string exceed
        # the wire cap when echoed twice. Reserve worst-case bounded error text.
        if valid_query and _wire_size(_failure(base, "query_rejected", "\x00" * 300)) > WIRE_BUDGET:
            valid_query = False
            base["sql"] = ""
        if not self._admit(token_id):
            result = _failure(base, "rate_limited", "Catalogue SQL quota exceeded; retry after one minute.")
        elif not valid_query:
            # Do not echo/log oversized or malformed attacker-controlled input.
            result = _failure(base, "invalid_query",
                              "SQL must be valid UTF-8, at most 8192 bytes, and fit the response budget.")
        elif isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= MAX_ROWS:
            result = _failure(base, "invalid_limit", "max_rows must be an integer from 1 to 1000.")
        elif not re.match(r"(?is)^(?:\s|--[^\n]*(?:\n|$)|/\*.*?\*/)*(SELECT|WITH)\b", query):
            result = _failure(base, "query_rejected", "Only one SELECT, optionally with a WITH clause, is allowed.")
        elif _private_identifier(query):
            result = _failure(base, "query_rejected", "Private catalogue identifiers are not queryable.")
        elif not self._slots.acquire(blocking=False):
            result = _failure(base, "busy", "Catalogue SQL concurrency limit reached; retry later.")
        else:
            try:
                result = self._execute(base, max_rows)
            finally:
                self._slots.release()
        LOG.info(_json({"sql": base["sql"], "token_id": token_id,
                        "outcome": result.get("error", {}).get("code", "ok"),
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                        "row_count": result["row_count"]}))
        return result

    def _execute(self, base: dict[str, Any], max_rows: int) -> dict[str, Any]:
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_worker,
                                  args=(sender, self.projection, base, max_rows, self.deadline_seconds),
                                  daemon=True, name="catalog-sql")
        deadline = time.monotonic() + self.deadline_seconds
        try:
            process.start()
            sender.close()
            if receiver.poll(max(0, deadline - time.monotonic())):
                return json.loads(receiver.recv_bytes(WIRE_BUDGET))
            return _failure(base, "timeout", "Query exceeded the five-second execution deadline.")
        except (EOFError, OSError, ValueError):
            return _failure(base, "worker_failed", "Catalogue SQL worker failed safely.")
        finally:
            sender.close()
            receiver.close()
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=0.2)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=0.2)
                process.close()
