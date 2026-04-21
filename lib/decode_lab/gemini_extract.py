"""Gemini PDF extraction for the Darpan Decode Lab.

Sends the source PDF directly to Gemini (not rendered PNGs) with a
page-range prompt, then applies the deterministic nakṣatra lookup.
Processes documents in page-sized chunks (default 5 pages per call).

All Gemini calls are disk-cached by SHA-256(model + prompt + pdf bytes).
Different model configs produce separate cache entries.

Usage::

    from lib.decode_lab.gemini_extract import extract_document
    from lib.decode_lab.model_configs import get_model_config

    chunks = extract_document(
        pdf_path=Path("corpus/ijhs/1.pdf"),
        page_count=12,
        doc_id="1",
        config=get_model_config("flash"),
        work_dir=Path(".build~/decode-lab/run/by-doc/1/fallbacks"),
    )
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any
from datetime import UTC, datetime

from lib.config import PROJECT_ROOT
from lib.decode_lab.model_configs import ModelConfig
from lib.decode_lab.nakshatra_lookup import apply_nakshatra_corrections


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------

_CACHE_DIR = PROJECT_ROOT / ".cache" / "gemini"


def _cache_key(
    config_name: str,
    model_name: str,
    prompt: str,
    pdf_bytes: bytes,
) -> str:
    """Deterministic cache key from config + model + prompt + PDF content.

    Uses config_name (e.g. '3-flash' vs '3-flash-med') to differentiate
    thinking levels on the same underlying model.
    """
    h = hashlib.sha256()
    h.update(config_name.encode("utf-8"))
    h.update(model_name.encode("utf-8"))
    h.update(prompt.encode("utf-8"))
    h.update(pdf_bytes)
    return h.hexdigest()


def _legacy_cache_key(
    config_name: str,
    model_name: str,
    prompt: str,
    pdf_bytes: bytes,
    service_tier: str,
) -> str:
    """Old cache key that included service tier in semantic identity."""
    h = hashlib.sha256()
    h.update(config_name.encode("utf-8"))
    h.update(model_name.encode("utf-8"))
    h.update(service_tier.encode("utf-8"))
    h.update(prompt.encode("utf-8"))
    h.update(pdf_bytes)
    return h.hexdigest()


def _cache_get(key: str) -> str | None:
    path = _CACHE_DIR / f"{key[:16]}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("cache_key") == key and isinstance(data.get("response_text"), str):
            return data["response_text"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _cache_put(
    key: str,
    response_text: str,
    model_name: str,
    service_tier: str,
    *,
    legacy_cache_key: str | None = None,
) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{key[:16]}.json"
    path.write_text(
        json.dumps(
            {
                "cache_key": key,
                "model_name": model_name,
                "service_tier": service_tier,
                "legacy_cache_key": legacy_cache_key,
                "response_text": response_text,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _cache_lookup(
    *,
    config: ModelConfig,
    prompt: str,
    pdf_bytes: bytes,
    service_tier: str,
) -> tuple[str | None, dict[str, Any]]:
    key = _cache_key(config.name, config.model_name, prompt, pdf_bytes)
    cached = _cache_get(key)
    if cached is not None:
        return cached, {"cache_key": key, "cache_hit": True, "legacy_cache_hit": False}

    legacy_tiers = [service_tier, "standard", "flex"]
    seen: set[str] = set()
    for tier in legacy_tiers:
        if tier in seen:
            continue
        seen.add(tier)
        legacy_key = _legacy_cache_key(
            config.name,
            config.model_name,
            prompt,
            pdf_bytes,
            tier,
        )
        cached = _cache_get(legacy_key)
        if cached is not None:
            _cache_put(
                key,
                cached,
                config.model_name,
                service_tier,
                legacy_cache_key=legacy_key,
            )
            return cached, {
                "cache_key": key,
                "cache_hit": True,
                "legacy_cache_hit": True,
                "legacy_service_tier": tier,
            }
    return None, {"cache_key": key, "cache_hit": False, "legacy_cache_hit": False}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _progress(message: str) -> None:
    print(f"[{_utc_now()}] {message}", flush=True)


def _call_gemini(
    pdf_bytes: bytes,
    prompt: str,
    config: ModelConfig,
    *,
    uploaded_file: Any = None,
    service_tier: str = "standard",
    bypass_cache: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Send PDF + prompt to Gemini.  Uses disk cache; API key required on miss.

    If *uploaded_file* is provided (a Gemini File API reference), it is used
    instead of re-uploading the raw bytes.  This avoids O(N²) token waste
    when processing a document in multiple page-range chunks.
    """
    cache_meta = {
        "cache_key": _cache_key(config.name, config.model_name, prompt, pdf_bytes),
        "legacy_cache_hit": False,
    }
    if not bypass_cache:
        cached, cache_meta = _cache_lookup(
            config=config,
            prompt=prompt,
            pdf_bytes=pdf_bytes,
            service_tier=service_tier,
        )
        if cached is not None:
            return cached, {
                "cache_hit": True,
                "legacy_cache_hit": cache_meta["legacy_cache_hit"],
                "elapsed_seconds": 0.0,
            }

    from google import genai  # deferred import — only on cache miss
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY not set.  Export it or add to .env before running "
            "with --extractor gemini:*."
        )

    client = genai.Client(api_key=api_key)

    gen_config_kwargs: dict[str, Any] = {}
    if config.thinking_level:
        gen_config_kwargs["thinking_config"] = types.ThinkingConfig(
            thinking_level=config.thinking_level,
        )
    if service_tier != "standard":
        gen_config_kwargs["http_options"] = types.HttpOptions(
            extra_body={"service_tier": service_tier}
        )

    gen_config = types.GenerateContentConfig(**gen_config_kwargs) if gen_config_kwargs else None

    # Use uploaded file reference if available, otherwise send raw bytes
    if uploaded_file is not None:
        pdf_content = uploaded_file
    else:
        pdf_content = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

    import time

    started = time.monotonic()
    response = client.models.generate_content(
        model=config.model_name,
        contents=[pdf_content, prompt],
        config=gen_config,
    )
    elapsed = time.monotonic() - started
    text = _response_text(response)
    if text is None:
        raise RuntimeError(_empty_response_reason(response))
    _cache_put(cache_meta["cache_key"], text, config.model_name, service_tier)
    return text, {
        "cache_hit": False,
        "legacy_cache_hit": False,
        "elapsed_seconds": round(elapsed, 3),
    }


def _response_text(response: Any) -> str | None:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text

    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str) and part_text:
                parts.append(part_text)
    if parts:
        return "\n".join(parts)
    return None


def _empty_response_reason(response: Any) -> str:
    details: dict[str, Any] = {"error": "Gemini response contained no text"}
    candidates = getattr(response, "candidates", None)
    if candidates:
        details["candidate_count"] = len(candidates)
        first = candidates[0]
        for attr in ("finish_reason", "finish_message"):
            value = getattr(first, attr, None)
            if value is not None:
                details[attr] = str(value)
        safety = getattr(first, "safety_ratings", None)
        if safety is not None:
            details["safety_ratings"] = str(safety)
    prompt_feedback = getattr(response, "prompt_feedback", None)
    if prompt_feedback is not None:
        details["prompt_feedback"] = str(prompt_feedback)
    return json.dumps(details, ensure_ascii=False)


def _upload_pdf(pdf_path: Path) -> Any:
    """Upload a PDF via the Gemini File API.  Returns the file reference."""
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    client = genai.Client(api_key=api_key)
    return client.files.upload(file=pdf_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_document(
    *,
    pdf_path: Path,
    page_count: int,
    doc_id: str,
    config: ModelConfig,
    work_dir: Path,
    service_tier: str = "standard",
    bypass_cache: bool = False,
) -> list[dict[str, Any]]:
    """Extract a full document via Gemini in page-sized chunks.

    Returns a list of fallback records (2 per chunk: Gemini + lookup)
    ready to be appended to fallbacks.jsonl.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    pdf_bytes = pdf_path.read_bytes()
    pdf_sha = _sha256_bytes(pdf_bytes)

    chunk_size = config.chunk_size
    num_chunks = math.ceil(page_count / chunk_size)
    fallback_records: list[dict[str, Any]] = []
    chunk_states: list[dict[str, Any]] = []
    _progress(
        f"gemini extract start doc_id={doc_id} pages={page_count} "
        f"chunks={num_chunks} model={config.name}/{config.model_name} "
        f"tier={service_tier} bypass_cache={bypass_cache}"
    )

    # Upload PDF once via File API if we have uncached chunks
    # (avoids re-sending the full PDF bytes for every chunk)
    uploaded_file: Any = None
    uncached_chunks = 0
    for ci in range(num_chunks):
        sp = ci * chunk_size + 1
        ep = min((ci + 1) * chunk_size, page_count)
        cached = None
        if not bypass_cache:
            cached, _cache_meta = _cache_lookup(
                config=config,
                prompt=config.prompt_for_pages(sp, ep),
                pdf_bytes=pdf_bytes,
                service_tier=service_tier,
            )
        if cached is None:
            uncached_chunks += 1
    _progress(
        f"gemini cache scan doc_id={doc_id} chunks={num_chunks} "
        f"uncached={uncached_chunks}"
    )
    if uncached_chunks > 0:
        try:
            _progress(f"gemini upload start doc_id={doc_id} pdf={pdf_path.name}")
            uploaded_file = _upload_pdf(pdf_path)
            _progress(
                f"gemini upload done doc_id={doc_id} "
                f"mode={'file-api' if uploaded_file is not None else 'raw-bytes'}"
            )
        except Exception:
            uploaded_file = None  # fall back to raw bytes
            _progress(f"gemini upload failed doc_id={doc_id}; falling back to raw bytes")

    for chunk_idx in range(num_chunks):
        start_page = chunk_idx * chunk_size + 1
        end_page = min((chunk_idx + 1) * chunk_size, page_count)
        chunk_tag = f"{doc_id}-p{start_page:04d}-p{end_page:04d}"

        prompt = config.prompt_for_pages(start_page, end_page)
        prompt_sha = config.prompt_sha256(start_page, end_page)
        cached = None
        if not bypass_cache:
            cached, _cache_meta = _cache_lookup(
                config=config,
                prompt=prompt,
                pdf_bytes=pdf_bytes,
                service_tier=service_tier,
            )
        cache_state = "hit" if cached is not None else "miss"
        _progress(
            f"gemini chunk start doc_id={doc_id} "
            f"chunk={chunk_idx + 1}/{num_chunks} pages={start_page}-{end_page} "
            f"cache={cache_state}"
        )

        # --- Gemini call ---
        gemini_text = ""
        call_meta: dict[str, Any] = {}
        last_error: Exception | None = None
        max_attempts = 3 if cache_state == "miss" else 1
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    _progress(
                        f"gemini chunk retry doc_id={doc_id} "
                        f"chunk={chunk_idx + 1}/{num_chunks} pages={start_page}-{end_page} "
                        f"attempt={attempt}/{max_attempts}"
                    )
                gemini_text, call_meta = _call_gemini(
                    pdf_bytes,
                    prompt,
                    config,
                    uploaded_file=uploaded_file,
                    service_tier=service_tier,
                    bypass_cache=bypass_cache,
                )
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                if attempt >= max_attempts or not _is_retryable_error(exc):
                    break
                time.sleep(min(60, 10 * attempt))

        if last_error is not None:
            error_record = _error_record(
                doc_id,
                start_page,
                end_page,
                config,
                f"Gemini call failed: {last_error}",
                service_tier,
                prompt_sha256=prompt_sha,
                input_sha256=pdf_sha,
            )
            error_path = work_dir / f"{chunk_tag}_error.json"
            _write_json(error_path, error_record)
            fallback_records.append(error_record)
            chunk_states.append(
                {
                    "page_start": start_page,
                    "page_end": end_page,
                    "status": "failure",
                    "retryable": error_record["retryable"],
                    "error_artifact": error_path.name,
                    "status_reason": error_record["status_reason"],
                }
            )
            _write_extraction_state(
                work_dir.parent,
                doc_id,
                config,
                service_tier,
                page_count,
                chunk_size,
                chunk_states,
            )
            _progress(
                f"gemini chunk failed doc_id={doc_id} "
                f"chunk={chunk_idx + 1}/{num_chunks} pages={start_page}-{end_page} "
                f"retryable={error_record['retryable']} error={last_error}"
            )
            continue
        _progress(
            f"gemini chunk done doc_id={doc_id} "
            f"chunk={chunk_idx + 1}/{num_chunks} pages={start_page}-{end_page} "
            f"cache_hit={call_meta['cache_hit']} "
            f"elapsed_seconds={call_meta['elapsed_seconds']}"
        )

        gemini_out_path = work_dir / f"{chunk_tag}_gemini.md"
        gemini_out_path.write_text(gemini_text, encoding="utf-8")
        gemini_sha = _sha256_text(gemini_text)

        gemini_record: dict[str, Any] = {
            "fallback_id": f"{chunk_tag}-gemini-extract",
            "doc_id": doc_id,
            "page_start": start_page,
            "page_end": end_page,
            "bbox": None,
            "fallback_type": "gemini_pdf_extract",
            "tool_or_model": config.model_name,
            "tool_or_model_version": config.name,
            "prompt_sha256": prompt_sha,
            "input_sha256": pdf_sha,
            "output_sha256": gemini_sha,
            "status": "partial",
            "status_reason": f"Gemini extraction pages {start_page}-{end_page}; nakṣatra lookup pending.",
            "recommended_action": "nakshatra-lookup",
            "service_tier_requested": service_tier,
            "cache_hit": call_meta["cache_hit"],
            "bypass_cache": bypass_cache,
            "elapsed_seconds": call_meta["elapsed_seconds"],
        }
        fallback_records.append(gemini_record)

        # --- Deterministic lookup ---
        cleaned_text = apply_nakshatra_corrections(gemini_text)
        cleaned_out_path = work_dir / f"{chunk_tag}_cleaned.md"
        cleaned_out_path.write_text(cleaned_text, encoding="utf-8")
        cleaned_sha = _sha256_text(cleaned_text)

        changed = gemini_sha != cleaned_sha
        lookup_record: dict[str, Any] = {
            "fallback_id": f"{chunk_tag}-nakshatra-lookup",
            "doc_id": doc_id,
            "page_start": start_page,
            "page_end": end_page,
            "bbox": None,
            "fallback_type": "deterministic_postprocess",
            "tool_or_model": "python-nakshatra-lookup",
            "tool_or_model_version": "v1",
            "prompt_sha256": None,
            "input_sha256": gemini_sha,
            "output_sha256": cleaned_sha,
            "status": "success",
            "status_reason": (
                f"Nakṣatra lookup applied ({'corrections made' if changed else 'no changes needed'})."
            ),
            "recommended_action": "accept",
            "service_tier_requested": service_tier,
            "cache_hit": call_meta["cache_hit"],
            "bypass_cache": bypass_cache,
            "elapsed_seconds": 0.0,
        }
        fallback_records.append(lookup_record)
        chunk_states.append(
            {
                "page_start": start_page,
                "page_end": end_page,
                "status": "success",
                "retryable": False,
                "gemini_artifact": f"{chunk_tag}_gemini.md",
                "cleaned_artifact": f"{chunk_tag}_cleaned.md",
                "cache_hit": call_meta["cache_hit"],
                "bypass_cache": bypass_cache,
                "elapsed_seconds": call_meta["elapsed_seconds"],
            }
        )
        _write_extraction_state(
            work_dir.parent,
            doc_id,
            config,
            service_tier,
            page_count,
            chunk_size,
            chunk_states,
        )

    _progress(f"gemini extract done doc_id={doc_id} records={len(fallback_records)}")
    return fallback_records


def _error_record(
    doc_id: str,
    start_page: int,
    end_page: int,
    config: ModelConfig,
    reason: str,
    service_tier: str,
    prompt_sha256: str | None = None,
    input_sha256: str | None = None,
) -> dict[str, Any]:
    retryable = _is_retryable_error_text(reason)
    return {
        "fallback_id": f"{doc_id}-p{start_page:04d}-p{end_page:04d}-gemini-extract",
        "doc_id": doc_id,
        "page_start": start_page,
        "page_end": end_page,
        "bbox": None,
        "fallback_type": "gemini_pdf_extract",
        "tool_or_model": config.model_name,
        "tool_or_model_version": config.name,
        "prompt_sha256": prompt_sha256,
        "input_sha256": input_sha256,
        "output_sha256": None,
        "status": "failure",
        "status_reason": reason,
        "recommended_action": "retry" if retryable else "inspect",
        "service_tier_requested": service_tier,
        "cache_hit": False,
        "elapsed_seconds": None,
        "retryable": retryable,
        "created_at": _utc_now(),
    }


def _is_retryable_error(exc: Exception) -> bool:
    return _is_retryable_error_text(str(exc))


def _is_retryable_error_text(text: str) -> bool:
    retryable_markers = [
        "429",
        "500",
        "502",
        "503",
        "504",
        "UNAVAILABLE",
        "DEADLINE_EXCEEDED",
        "RESOURCE_EXHAUSTED",
        "high demand",
        "temporarily",
        "timeout",
        "timed out",
    ]
    folded = text.casefold()
    return any(marker.casefold() in folded for marker in retryable_markers)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_extraction_state(
    doc_dir: Path,
    doc_id: str,
    config: ModelConfig,
    service_tier: str,
    page_count: int,
    chunk_size: int,
    chunk_states: list[dict[str, Any]],
) -> None:
    _write_json(
        doc_dir / "extraction-state.json",
        {
            "doc_id": doc_id,
            "page_count": page_count,
            "chunk_size": chunk_size,
            "tool_or_model": config.model_name,
            "tool_or_model_version": config.name,
            "service_tier_requested": service_tier,
            "updated_at": _utc_now(),
            "gemini_chunks": chunk_states,
        },
    )
