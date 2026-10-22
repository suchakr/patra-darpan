"""Content-addressed embedding reuse; never mutate the serving collection.

Approved design: plan first, copy compatible vectors into an isolated candidate,
encode only cache misses, and retain the previous release for rollback.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def model_text(model_name: str, text: str) -> str:
    return ("passage: " if "e5" in model_name.lower() else "") + text


def embedding_configuration(model: Any, model_name: str) -> dict[str, Any]:
    """Fingerprint actual loaded weights/tokenizer, not a mutable model alias."""
    import torch

    weights = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        tensor = tensor.detach().cpu().contiguous()
        weights.update(json.dumps([name, str(tensor.dtype), list(tensor.shape)]).encode())
        weights.update(memoryview(tensor.reshape(-1).view(torch.uint8).numpy()))
    tokenizer = model.tokenizer
    if not getattr(tokenizer, "backend_tokenizer", None):
        raise ValueError("incremental indexing requires a serializable fast tokenizer")
    modules = [{"class": type(module).__module__ + "." + type(module).__qualname__,
                "configuration": module.get_config_dict()} for module in model._modules.values()
               if hasattr(module, "get_config_dict")]
    config = getattr(getattr(model._first_module(), "auto_model", None), "config", None)
    return {
        "schema_version": "retrieval.embedding-configuration.v1",
        "model": model_name,
        "resolved_revision": getattr(config, "_commit_hash", None),
        "weights_sha256": weights.hexdigest(),
        "tokenizer_sha256": hashlib.sha256(tokenizer.backend_tokenizer.to_str().encode()).hexdigest(),
        "module_configuration_sha256": digest(modules),
        "max_seq_length": int(model.max_seq_length),
        "dimensions": int(model.get_sentence_embedding_dimension()),
        "normalized": True,
        "precision": "float32",
        "document_prefix": "passage: " if "e5" in model_name.lower() else "",
        "query_prefix": "query: " if "e5" in model_name.lower() else "",
        "default_prompt_name": getattr(model, "default_prompt_name", None),
        "prompts": getattr(model, "prompts", {}),
        "truncate_dim": getattr(model, "truncate_dim", None),
        "libraries": {name: importlib.metadata.version(name) for name in
                      ("sentence-transformers", "transformers", "tokenizers", "torch")},
    }


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def embedding_key(chunk: dict[str, Any], configuration: dict[str, Any]) -> str:
    return digest({"configuration": digest(configuration),
                   "input": model_text(configuration["model"], str(chunk["embed_text"]))})


def payload_for(chunk: dict[str, Any], configuration: dict[str, Any]) -> dict[str, Any]:
    fields = ("chunk_id", "source_id", "document_id", "source_kind", "repo_path",
              "heading_path", "logical_location", "content_sha256", "chunker_version", "script_counts")
    return {**{key: chunk.get(key) for key in fields},
            "embedding_key": embedding_key(chunk, configuration),
            "embedding_fingerprint": digest(configuration)}


def validate_inventory(chunks: list[dict[str, Any]]) -> None:
    ids = [str(chunk["chunk_id"]) for chunk in chunks]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("chunk inventory must be nonempty with unique chunk IDs")
    for chunk in chunks:
        if not str(chunk.get("embed_text", "")).strip():
            raise ValueError(f"empty embedding input: {chunk['chunk_id']}")


def plan_reuse(old_chunks: list[dict[str, Any]], chunks: list[dict[str, Any]],
               old_embedding: dict[str, Any], configuration: dict[str, Any],
               legacy_attestation: str | None = None) -> dict[str, Any]:
    validate_inventory(old_chunks)
    validate_inventory(chunks)
    fingerprint = digest(configuration)
    old_configuration = old_embedding.get("configuration")
    legacy = not old_configuration
    if old_configuration:
        if old_embedding.get("fingerprint") != digest(old_configuration):
            raise ValueError("previous embedding configuration fingerprint is corrupt")
        compatible = old_configuration == configuration
    else:
        compatible = (old_embedding.get("model") == configuration["model"]
                      and old_embedding.get("dimensions") == configuration["dimensions"]
                      and old_embedding.get("normalized") is True)
        if legacy_attestation and legacy_attestation != fingerprint:
            raise ValueError("legacy model attestation must match the displayed embedding fingerprint")
    old_keys = {embedding_key(chunk, configuration): chunk["chunk_id"] for chunk in old_chunks} if compatible else {}
    reuse = {chunk["chunk_id"]: old_keys[embedding_key(chunk, configuration)] for chunk in chunks
             if embedding_key(chunk, configuration) in old_keys}
    old_ids = {chunk["chunk_id"] for chunk in old_chunks}
    new_ids = {chunk["chunk_id"] for chunk in chunks}
    def documents(rows):
        grouped = {}
        for row in rows:
            grouped.setdefault(row["document_id"], []).append(embedding_key(row, configuration))
        return grouped
    old_documents, new_documents = documents(old_chunks), documents(chunks)
    shared_documents = old_documents.keys() & new_documents.keys()
    return {
        "embedding_fingerprint": fingerprint,
        "configuration": configuration,
        "compatible": compatible,
        "legacy_attestation_required": legacy and compatible and bool(reuse) and not legacy_attestation,
        "legacy_attestation_supplied": legacy and compatible and bool(legacy_attestation),
        "old_chunks": len(old_chunks), "target_chunks": len(chunks),
        "reuse_chunks": len(reuse), "embed_chunks": len(chunks) - len(reuse),
        "removed_chunk_ids": len(old_ids - new_ids),
        "new_chunk_ids": len(new_ids - old_ids),
        "added_documents": len(new_documents.keys() - old_documents.keys()),
        "removed_documents": len(old_documents.keys() - new_documents.keys()),
        "changed_documents": sum(old_documents[key] != new_documents[key] for key in shared_documents),
        "unchanged_documents": sum(old_documents[key] == new_documents[key] for key in shared_documents),
        "reuse_from": reuse,
    }


def scan_points(client: Any, collection: str, *, vectors: bool = False) -> dict[str, Any]:
    result = {}
    offset = None
    while True:
        rows, offset = client.scroll(collection_name=collection, limit=256, offset=offset,
                                     with_payload=True, with_vectors=vectors)
        for point in rows:
            identifier = str(point.id)
            if identifier in result:
                raise ValueError("duplicate point ID while scrolling collection")
            result[identifier] = point
        if offset is None:
            break
    return result


def check_collection(client: Any, collection: str, dimensions: int) -> None:
    info = client.get_collection(collection)
    params = info.config.params.vectors
    if isinstance(params, dict):
        raise ValueError("incremental indexing requires a single unnamed vector")
    distance = str(getattr(params.distance, "value", params.distance)).lower()
    if int(params.size) != dimensions or distance != "cosine":
        raise ValueError("collection dimensions/distance do not match the embedding configuration")


def validate_points(points: dict[str, Any], chunks: list[dict[str, Any]],
                    configuration: dict[str, Any], *, legacy: bool = False,
                    subset: bool = False, vectors: bool = False) -> None:
    expected = {point_id(chunk["chunk_id"]): chunk for chunk in chunks}
    if set(points) - expected.keys() or (not subset and set(points) != expected.keys()):
        raise ValueError("collection point IDs differ from the declared chunk inventory")
    for identifier, point in points.items():
        payload = point.payload or {}
        wanted = payload_for(expected[identifier], configuration)
        if legacy:
            wanted = {key: wanted[key] for key in
                      ("chunk_id", "content_sha256", "repo_path", "logical_location", "chunker_version")}
        if any(payload.get(key) != value for key, value in wanted.items()):
            raise ValueError(f"collection payload mismatch for {wanted['chunk_id']}")
        if vectors:
            validate_vector(point.vector, configuration["dimensions"])


def validate_vector(vector: Any, dimensions: int) -> list[float]:
    if not isinstance(vector, (list, tuple)) or len(vector) != dimensions:
        raise ValueError("embedding vector has wrong dimension/type")
    values = [float(value) for value in vector]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("embedding vector contains non-finite values")
    if abs(sum(value * value for value in values) - 1.0) > 0.002:
        raise ValueError("embedding vector is not unit normalized")
    return values


def verified_point_ids(client: Any, collection: str, chunks: list[dict[str, Any]],
                       configuration: dict[str, Any], *, subset: bool = False) -> set[str]:
    """Validate vectors pagewise rather than retaining all vector arrays in RAM."""
    expected = {point_id(chunk["chunk_id"]): chunk for chunk in chunks}
    seen = set()
    offset = None
    while True:
        rows, offset = client.scroll(collection_name=collection, limit=256, offset=offset,
                                     with_payload=True, with_vectors=True)
        page = {str(point.id): point for point in rows}
        if len(page) != len(rows) or seen & page.keys() or page.keys() - expected.keys():
            raise ValueError("unexpected or duplicate candidate point IDs")
        validate_points(page, [expected[key] for key in page], configuration, vectors=True)
        seen.update(page)
        if offset is None:
            break
    if not subset and seen != expected.keys():
        raise ValueError("candidate point IDs differ from the declared chunk inventory")
    return seen


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def build_candidate(*, client: Any, model: Any, point_factory: Any,
                    old_collection: str, collection: str, chunks: list[dict[str, Any]],
                    old_chunks: list[dict[str, Any]], plan: dict[str, Any],
                    checkpoint: Path, create_collection: Any, batch_size: int = 32,
                    max_embed_chunks: int = 2000) -> dict[str, Any]:
    """Resume only a matching owned candidate; acknowledged points are checkpoints."""
    if not collection or collection == old_collection:
        raise ValueError("candidate must differ from the serving collection")
    if batch_size < 1 or max_embed_chunks < 0:
        raise ValueError("invalid batch size or embedding budget")
    if plan["legacy_attestation_required"]:
        raise ValueError("legacy release lacks exact model identity; explicit --legacy-model-attestation required")
    if plan["embed_chunks"] > max_embed_chunks:
        raise ValueError(f"embedding budget exceeded: {plan['embed_chunks']} > {max_embed_chunks}")
    config = plan["configuration"]
    if digest(config) != plan["embedding_fingerprint"]:
        raise ValueError("build plan fingerprint is corrupt")
    identity = digest({"old_collection": old_collection, "collection": collection,
                       "chunks": chunks, "plan": plan})
    exists = client.collection_exists(collection)
    state = json.loads(checkpoint.read_text()) if checkpoint.exists() else None
    if state and state.get("job_identity") != identity:
        raise ValueError("candidate checkpoint belongs to a different build")
    if exists and not state:
        raise ValueError("refusing to overwrite an unowned existing candidate collection")
    state = state or {"job_identity": identity, "collection": collection, "completed": 0}
    atomic_json(checkpoint, state)
    if not exists:
        create_collection(collection, config["dimensions"])
    check_collection(client, collection, config["dimensions"])
    done = verified_point_ids(client, collection, chunks, config, subset=True)
    resumed = len(done)
    reused = encoded = 0
    old_by_id = {chunk["chunk_id"]: chunk for chunk in old_chunks}
    pending = [chunk for chunk in chunks if point_id(chunk["chunk_id"]) not in done]
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        copy_batch = [chunk for chunk in batch if chunk["chunk_id"] in plan["reuse_from"]]
        encode_batch = [chunk for chunk in batch if chunk["chunk_id"] not in plan["reuse_from"]]
        source_ids = {plan["reuse_from"][chunk["chunk_id"]] for chunk in copy_batch}
        source_points = client.retrieve(collection_name=old_collection,
                                        ids=[point_id(identifier) for identifier in sorted(source_ids)],
                                        with_payload=True, with_vectors=True) if source_ids else []
        source_points = {str(point.id): point for point in source_points}
        old_config = config
        validate_points(source_points, [old_by_id[i] for i in sorted(source_ids)], old_config,
                        legacy=plan["legacy_attestation_supplied"], vectors=True)
        vectors = {}
        for chunk in copy_batch:
            source_id = plan["reuse_from"][chunk["chunk_id"]]
            vectors[chunk["chunk_id"]] = source_points[point_id(source_id)].vector
        if encode_batch:
            values = model.encode([model_text(config["model"], chunk["embed_text"]) for chunk in encode_batch],
                                  batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True,
                                  show_progress_bar=False)
            if len(values) != len(encode_batch):
                raise ValueError("encoder returned an incomplete batch")
            for chunk, vector in zip(encode_batch, values, strict=True):
                vectors[chunk["chunk_id"]] = vector.tolist() if hasattr(vector, "tolist") else vector
        points = [point_factory(id=point_id(chunk["chunk_id"]),
                                vector=validate_vector(vectors[chunk["chunk_id"]], config["dimensions"]),
                                payload=payload_for(chunk, config)) for chunk in batch]
        client.upsert(collection_name=collection, points=points, wait=True)
        reused += len(copy_batch)
        encoded += len(encode_batch)
        state.update(completed=resumed + reused + encoded)
        atomic_json(checkpoint, state)
    verified_point_ids(client, collection, chunks, config)
    return {"chunk_count": len(chunks), "reused_this_run": reused,
            "embedded_this_run": encoded, "resumed_points": resumed,
            "verified": True, "job_identity": identity}
