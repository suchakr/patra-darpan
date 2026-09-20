"""Small Gemini Embedding 2 adapter shared by the bakeoff scripts.

The Google documentation recommends explicit retrieval prefixes for the
text-only Gemini Embedding 2 use case.  Keeping those prefixes here prevents
the corpus runner and query evaluator from silently drifting apart.
"""

from __future__ import annotations

from typing import Any


MODEL_NAME = "gemini-embedding-2"


def prepare_document(chunk: dict[str, Any]) -> str:
    """Format one chunk as a Gemini asymmetric-retrieval document."""

    heading_path = chunk.get("heading_path") or []
    title = " / ".join(str(value) for value in heading_path if value) or str(
        chunk.get("title") or chunk.get("repo_path") or "none"
    )
    text = str(chunk.get("embed_text") or chunk.get("text") or "")
    return f"title: {title} | text: {text}"


def prepare_query(text: str) -> str:
    """Format a search query for Gemini asymmetric retrieval."""

    return f"task: search result | query: {text}"


def embed_one(client: Any, text: str, *, model: str = MODEL_NAME, dimensions: int = 768) -> list[float]:
    """Call Gemini once and return the validated vector."""

    from google.genai import types

    response = client.models.embed_content(
        model=model,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=dimensions),
    )
    embeddings = list(response.embeddings or [])
    if len(embeddings) != 1:
        raise RuntimeError(f"expected one embedding, received {len(embeddings)}")
    values = list(embeddings[0].values or [])
    if len(values) != dimensions:
        raise RuntimeError(f"expected {dimensions} dimensions, received {len(values)}")
    return [float(value) for value in values]

