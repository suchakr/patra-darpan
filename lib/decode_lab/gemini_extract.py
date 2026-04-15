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
from pathlib import Path
from typing import Any

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
    service_tier: str,
) -> str:
    """Deterministic cache key from config + model + prompt + PDF content.

    Uses config_name (e.g. '3-flash' vs '3-flash-med') to differentiate
    thinking levels on the same underlying model.
    """
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
        if data.get("cache_key") == key:
            return data["response_text"]
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def _cache_put(key: str, response_text: str, model_name: str, service_tier: str) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _CACHE_DIR / f"{key[:16]}.json"
    path.write_text(
        json.dumps(
            {
                "cache_key": key,
                "model_name": model_name,
                "service_tier": service_tier,
                "response_text": response_text,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _call_gemini(
    pdf_bytes: bytes,
    prompt: str,
    config: ModelConfig,
    *,
    uploaded_file: Any = None,
    service_tier: str = "standard",
) -> tuple[str, dict[str, Any]]:
    """Send PDF + prompt to Gemini.  Uses disk cache; API key required on miss.

    If *uploaded_file* is provided (a Gemini File API reference), it is used
    instead of re-uploading the raw bytes.  This avoids O(N²) token waste
    when processing a document in multiple page-range chunks.
    """
    key = _cache_key(config.name, config.model_name, prompt, pdf_bytes, service_tier)
    cached = _cache_get(key)
    if cached is not None:
        return cached, {"cache_hit": True, "elapsed_seconds": 0.0}

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
    text = response.text
    _cache_put(key, text, config.model_name, service_tier)
    return text, {"cache_hit": False, "elapsed_seconds": round(elapsed, 3)}


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

    # Upload PDF once via File API if we have uncached chunks
    # (avoids re-sending the full PDF bytes for every chunk)
    uploaded_file: Any = None
    uncached_chunks = 0
    for ci in range(num_chunks):
        sp = ci * chunk_size + 1
        ep = min((ci + 1) * chunk_size, page_count)
        key = _cache_key(
            config.name,
            config.model_name,
            config.prompt_for_pages(sp, ep),
            pdf_bytes,
            service_tier,
        )
        if _cache_get(key) is None:
            uncached_chunks += 1
    if uncached_chunks > 0:
        try:
            uploaded_file = _upload_pdf(pdf_path)
        except Exception:
            uploaded_file = None  # fall back to raw bytes

    for chunk_idx in range(num_chunks):
        start_page = chunk_idx * chunk_size + 1
        end_page = min((chunk_idx + 1) * chunk_size, page_count)
        chunk_tag = f"{doc_id}-p{start_page:04d}-p{end_page:04d}"

        prompt = config.prompt_for_pages(start_page, end_page)
        prompt_sha = config.prompt_sha256(start_page, end_page)

        # --- Gemini call ---
        try:
            gemini_text, call_meta = _call_gemini(
                pdf_bytes,
                prompt,
                config,
                uploaded_file=uploaded_file,
                service_tier=service_tier,
            )
        except Exception as exc:
            fallback_records.append(
                _error_record(
                    doc_id,
                    start_page,
                    end_page,
                    config,
                    f"Gemini call failed: {exc}",
                    service_tier,
                )
            )
            continue

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
            "elapsed_seconds": 0.0,
        }
        fallback_records.append(lookup_record)

    return fallback_records


def _error_record(
    doc_id: str,
    start_page: int,
    end_page: int,
    config: ModelConfig,
    reason: str,
    service_tier: str,
) -> dict[str, Any]:
    return {
        "fallback_id": f"{doc_id}-p{start_page:04d}-p{end_page:04d}-gemini-extract",
        "doc_id": doc_id,
        "page_start": start_page,
        "page_end": end_page,
        "bbox": None,
        "fallback_type": "gemini_pdf_extract",
        "tool_or_model": config.model_name,
        "tool_or_model_version": config.name,
        "prompt_sha256": None,
        "input_sha256": None,
        "output_sha256": None,
        "status": "failure",
        "status_reason": reason,
        "recommended_action": "no-action",
        "service_tier_requested": service_tier,
        "cache_hit": False,
        "elapsed_seconds": None,
    }
