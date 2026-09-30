"""Usage accounting and cost estimates for Decode Lab Gemini runs.

The runner records provider usage when the Gemini SDK returns it. Prices are
kept as a small versioned snapshot so historical estimates remain interpretable
after provider pricing changes. Unknown model or usage combinations stay
unknown instead of receiving a guessed price.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from lib.config import PROJECT_ROOT


PRICING_SOURCE_URL = "https://ai.google.dev/gemini-api/docs/pricing"
PRICING_TABLE_VERSION = "2026-09-19"
HISTORY_COLUMNS = [
    "run_id",
    "started_at",
    "finished_at",
    "duration_seconds",
    "extractor",
    "service_tier_requested",
    "selected_doc_count",
    "gemini_calls",
    "api_calls",
    "cache_hits",
    "failed_calls",
    "recorded_input_tokens",
    "recorded_cached_input_tokens",
    "recorded_output_tokens",
    "recorded_thinking_tokens",
    "estimated_cost_usd",
    "known_estimated_cost_usd",
    "cost_status",
    "run_dir",
]


# Prices are USD per million tokens. Update the version and source date when
# provider pricing changes. The active 3-flash preview path is included along
# with the two older presets still exposed by the CLI.
_PRICING: dict[tuple[str, str], dict[str, float]] = {
    ("gemini-3-flash-preview", "standard"): {
        "input_usd_per_million": 0.50,
        "output_usd_per_million": 3.00,
        "cached_input_usd_per_million": 0.05,
    },
    ("gemini-3-flash-preview", "flex"): {
        "input_usd_per_million": 0.25,
        "output_usd_per_million": 1.50,
        "cached_input_usd_per_million": 0.05,
    },
    ("gemini-2.5-flash", "standard"): {
        "input_usd_per_million": 0.30,
        "output_usd_per_million": 2.50,
        "cached_input_usd_per_million": 0.03,
    },
    ("gemini-2.5-flash", "flex"): {
        "input_usd_per_million": 0.15,
        "output_usd_per_million": 1.25,
        "cached_input_usd_per_million": 0.03,
    },
    ("gemini-2.5-flash-lite", "standard"): {
        "input_usd_per_million": 0.10,
        "output_usd_per_million": 0.40,
        "cached_input_usd_per_million": 0.01,
    },
    ("gemini-2.5-flash-lite", "flex"): {
        "input_usd_per_million": 0.05,
        "output_usd_per_million": 0.20,
        "cached_input_usd_per_million": 0.01,
    },
}


def pricing_snapshot(model_name: str, service_tier: str) -> dict[str, Any] | None:
    rates = _PRICING.get((model_name, service_tier))
    if rates is None:
        return None
    return {
        "model": model_name,
        "service_tier": service_tier,
        "currency": "USD",
        "input_usd_per_million": rates["input_usd_per_million"],
        "output_usd_per_million": rates["output_usd_per_million"],
        "cached_input_usd_per_million": rates["cached_input_usd_per_million"],
        "pricing_table_version": PRICING_TABLE_VERSION,
        "pricing_snapshot_date": PRICING_TABLE_VERSION,
        "pricing_source": PRICING_SOURCE_URL,
    }


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def usage_metadata_dict(metadata: Any) -> dict[str, int]:
    """Normalize a Gemini SDK usage object or mapping into integer fields."""
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        source = metadata
    elif hasattr(metadata, "model_dump"):
        source = metadata.model_dump(exclude_none=True)
    else:
        source = {
            name: getattr(metadata, name, None)
            for name in (
                "prompt_token_count",
                "cached_content_token_count",
                "candidates_token_count",
                "thoughts_token_count",
                "tool_use_prompt_token_count",
                "total_token_count",
            )
        }

    fields: dict[str, int] = {}
    for name in (
        "prompt_token_count",
        "cached_content_token_count",
        "candidates_token_count",
        "thoughts_token_count",
        "tool_use_prompt_token_count",
        "total_token_count",
    ):
        value = _as_int(source.get(name))
        if value is not None:
            fields[name] = value
    return fields


def response_usage(response: Any) -> dict[str, int]:
    return usage_metadata_dict(getattr(response, "usage_metadata", None))


def call_cost_fields(
    *,
    model_name: str,
    service_tier: str,
    response: Any | None,
    cache_hit: bool,
) -> dict[str, Any]:
    """Return usage, pricing, and estimate fields for one Gemini call."""
    pricing = pricing_snapshot(model_name, service_tier)
    fields: dict[str, Any] = {
        "usage": response_usage(response) if response is not None else {},
        "pricing": pricing,
        "estimated_cost_usd": None,
        "cost_status": "unknown",
    }

    if cache_hit:
        fields["estimated_cost_usd"] = 0.0
        fields["cost_status"] = "local_cache_hit"
        return fields
    if pricing is None:
        fields["cost_status"] = "pricing_unavailable"
        return fields

    usage = fields["usage"]
    prompt_tokens = usage.get("prompt_token_count")
    cached_tokens = usage.get("cached_content_token_count", 0)
    candidate_tokens = usage.get("candidates_token_count")
    thought_tokens = usage.get("thoughts_token_count", 0)
    if prompt_tokens is None:
        fields["cost_status"] = "usage_unavailable"
        return fields

    if candidate_tokens is None:
        total_tokens = usage.get("total_token_count")
        if total_tokens is not None:
            candidate_tokens = max(total_tokens - prompt_tokens - thought_tokens, 0)
        else:
            fields["cost_status"] = "usage_unavailable"
            return fields

    billable_input_tokens = max(prompt_tokens - cached_tokens, 0)
    billable_output_tokens = candidate_tokens + thought_tokens
    input_cost = billable_input_tokens / 1_000_000 * pricing["input_usd_per_million"]
    cached_cost = cached_tokens / 1_000_000 * pricing["cached_input_usd_per_million"]
    output_cost = billable_output_tokens / 1_000_000 * pricing["output_usd_per_million"]
    fields.update(
        {
            "billable_input_tokens": billable_input_tokens,
            "billable_output_tokens": billable_output_tokens,
            "input_cost_usd": input_cost,
            "cached_input_cost_usd": cached_cost,
            "output_cost_usd": output_cost,
            "estimated_cost_usd": round(input_cost + cached_cost + output_cost, 8),
            "cost_status": "estimated",
        }
    )
    return fields


def _sum_usage(rows: list[dict[str, Any]], key: str) -> int:
    return sum(int((row.get("usage") or {}).get(key) or 0) for row in rows)


def summarize_fallbacks(fallbacks: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize Gemini usage and cost fields from normalized fallback rows."""
    rows = [
        row
        for row in fallbacks
        if row.get("fallback_type") == "gemini_pdf_extract"
    ]
    api_rows = [row for row in rows if not row.get("cache_hit")]
    successful_api_rows = [row for row in api_rows if row.get("status") != "failure"]
    cache_hits = [row for row in rows if row.get("cache_hit")]
    failed = [row for row in rows if row.get("status") == "failure"]
    usage_rows = [row for row in successful_api_rows if row.get("usage")]
    cost_rows = [
        row for row in successful_api_rows if row.get("estimated_cost_usd") is not None
    ]
    known_cost = round(sum(float(row["estimated_cost_usd"]) for row in cost_rows), 8)
    missing_usage = len(successful_api_rows) - len(usage_rows)
    missing_cost = len(successful_api_rows) - len(cost_rows)

    if not rows:
        cost_status = "not_applicable"
    elif not api_rows:
        cost_status = "cache_only" if cache_hits else "unknown"
    elif failed or missing_cost:
        cost_status = "partial" if cost_rows else "unknown"
    else:
        cost_status = "estimated"

    recorded_input_tokens = _sum_usage(usage_rows, "prompt_token_count")
    recorded_cached_input_tokens = _sum_usage(usage_rows, "cached_content_token_count")
    recorded_output_tokens = _sum_usage(usage_rows, "candidates_token_count")
    recorded_thinking_tokens = _sum_usage(usage_rows, "thoughts_token_count")
    return {
        "status": cost_status,
        "currency": "USD",
        "gemini_calls": len(rows),
        "api_calls": len(api_rows),
        "cache_hits": len(cache_hits),
        "failed_calls": len(failed),
        "usage_records": len(usage_rows),
        "usage_missing_calls": missing_usage,
        "recorded_input_tokens": recorded_input_tokens,
        "recorded_cached_input_tokens": recorded_cached_input_tokens,
        "recorded_output_tokens": recorded_output_tokens,
        "recorded_thinking_tokens": recorded_thinking_tokens,
        "estimated_cost_usd": known_cost if not missing_cost and not failed else None,
        "known_estimated_cost_usd": known_cost,
        "api_elapsed_seconds": round(
            sum(float(row.get("elapsed_seconds") or 0) for row in api_rows), 3
        ),
        "pricing_snapshots": _unique_pricing(rows),
    }


def _unique_pricing(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        pricing = row.get("pricing")
        if isinstance(pricing, dict):
            key = json.dumps(pricing, sort_keys=True)
            unique[key] = pricing
    return list(unique.values())


def duration_seconds(started_at: str | None, finished_at: str | None) -> float | None:
    if not started_at or not finished_at:
        return None
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((finished - started).total_seconds(), 3)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def write_run_history(run_root: Path, output_path: Path) -> None:
    """Regenerate a compact history view from all run manifests."""
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(run_root.glob("*/run-manifest.json")):
        manifest = _read_json(manifest_path)
        if manifest is None:
            continue
        run_dir = manifest_path.parent
        fallback_summary = summarize_fallbacks(_read_jsonl(run_dir / "fallbacks.jsonl"))
        summary = manifest.get("cost_summary")
        if not isinstance(summary, dict):
            summary = fallback_summary
        rows.append(
            {
                "run_id": manifest.get("run_id", run_dir.name),
                "started_at": manifest.get("started_at", ""),
                "finished_at": manifest.get("finished_at", ""),
                "duration_seconds": manifest.get("duration_seconds")
                or duration_seconds(manifest.get("started_at"), manifest.get("finished_at")),
                "extractor": manifest.get("extractor", ""),
                "service_tier_requested": manifest.get("service_tier_requested", ""),
                "selected_doc_count": len(manifest.get("selected_doc_ids") or []),
                "gemini_calls": summary.get("gemini_calls", 0),
                "api_calls": summary.get("api_calls", 0),
                "cache_hits": summary.get("cache_hits", 0),
                "failed_calls": summary.get("failed_calls", 0),
                "recorded_input_tokens": summary.get("recorded_input_tokens", 0),
                "recorded_cached_input_tokens": summary.get("recorded_cached_input_tokens", 0),
                "recorded_output_tokens": summary.get("recorded_output_tokens", 0),
                "recorded_thinking_tokens": summary.get("recorded_thinking_tokens", 0),
                "estimated_cost_usd": summary.get("estimated_cost_usd"),
                "known_estimated_cost_usd": summary.get("known_estimated_cost_usd", 0),
                "cost_status": summary.get("status", "unknown"),
                "run_dir": _display_run_dir(run_dir),
            }
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HISTORY_COLUMNS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _display_run_dir(run_dir: Path) -> str:
    """Keep the committed history projection portable across checkouts."""
    try:
        return str(run_dir.resolve().relative_to(PROJECT_ROOT.resolve()))
    except ValueError:
        return str(run_dir)
