#!/usr/bin/env python3
"""Plan first; reuse compatible embeddings in an isolated release candidate.

Neither planning nor building restarts MCP or touches the serving collection.
Activation is a separate explicit flag after full candidate verification.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.retrieval_adapters import load_release, read_jsonl
from lib.retrieval_release_state import activate_record
from lib.retrieval_vectors import (
    atomic_json, build_candidate, check_collection, digest, embedding_configuration,
    plan_reuse, scan_points, validate_points, verified_point_ids,
)
from scripts.build_retrieval_index import (
    build_chunks, build_manifest, build_summary, iter_mentions, parse_args,
    registry_from_mentions, run_release_build, write_jsonl,
)


def manifest_identity(manifest):
    return {key: value for key, value in manifest.items() if key != 'generated_at'}


def verify_candidate(client, candidate, chunks, configuration, manifest, ontology_bytes):
    if (read_jsonl(candidate.artifact_path('chunks')) != chunks
            or candidate.record['pipeline']['embedding'].get('configuration') != configuration
            or manifest_identity(json.loads(candidate.artifact_path('input_manifest').read_text())) != manifest_identity(manifest)
            or candidate.artifact_path('ontology_snapshot').read_bytes() != ontology_bytes):
        raise ValueError('completed candidate does not match the frozen build inputs')
    collection = candidate.record['artifacts']['vector_index']['collection']
    check_collection(client, collection, configuration['dimensions'])
    verified_point_ids(client, collection, chunks, configuration)


@contextlib.contextmanager
def build_lock(work_root: Path, apply: bool):
    if not apply:
        yield
        return
    work_root.mkdir(parents=True, exist_ok=True)
    with (work_root / '.incremental.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('another incremental build is running') from exc
        yield


def run(args) -> int:
    if args.activate and not args.apply:
        raise ValueError('--activate requires --apply')
    if args.force or (args.activate and args.no_activate):
        raise ValueError('incremental builds do not support --force or conflicting activation flags')
    if args.batch_size < 1 or args.max_embed_chunks < 0:
        raise ValueError('batch size must be positive and embedding budget nonnegative')
    from qdrant_client import QdrantClient, models
    from sentence_transformers import SentenceTransformer
    active_path = args.release_root / 'active-release.json'
    active_bytes = active_path.read_bytes()
    previous = load_release(active_path)
    old_chunks = read_jsonl(previous.artifact_path('chunks'))
    old_embedding = previous.record['pipeline']['embedding']
    old_collection = previous.record['artifacts']['vector_index']['collection']
    # Planning must not download a new model or write to the model cache.
    model = SentenceTransformer(args.model, revision=args.model_revision or None,
                                device=args.device, local_files_only=True)
    configuration = embedding_configuration(model, args.model)
    manifest = build_manifest(args.sanchaya_root, args.audit_set,
                              paper_scope=args.paper_scope, sanchaya_scope=args.sanchaya_scope)
    chunks, chunk_summary = build_chunks(manifest, target_tokens=args.target_tokens,
                                        max_tokens=args.max_tokens, overlap_tokens=args.overlap_tokens)
    plan = plan_reuse(old_chunks, chunks, old_embedding, configuration, args.legacy_model_attestation)
    client = QdrantClient(url=args.qdrant_url)
    check_collection(client, old_collection, int(old_embedding['dimensions']))
    validate_points(scan_points(client, old_collection), old_chunks,
                    old_embedding.get('configuration') or configuration,
                    legacy=not old_embedding.get('configuration'))
    ontology_bytes = args.ontology.read_bytes()
    old_artifacts = previous.record.get('artifacts', {})
    unchanged = (chunks == old_chunks and old_embedding.get('configuration') == configuration
                 and previous.corpus_revision == manifest['sanchaya']['commit']
                 and old_artifacts.get('ontology_snapshot', {}).get('sha256') == hashlib.sha256(ontology_bytes).hexdigest()
                 and manifest_identity(json.loads(previous.artifact_path('input_manifest').read_text())) == manifest_identity(manifest))
    if unchanged:
        print(json.dumps({'status': 'unchanged', 'release_id': previous.release_id,
                          'chunk_count': len(chunks), 'embedded_this_run': 0,
                          'active_collection_modified': False}, indent=2))
        return 0
    identity = digest({'chunks': chunks, 'configuration': configuration,
                       'scope': manifest['selection'], 'ontology': ontology_bytes.decode(),
                       'previous_release': digest(previous.record)})
    commit = str(manifest['sanchaya']['commit'])
    release_id = args.release_id or f'retrieval-{args.sanchaya_scope}-{args.paper_scope}-{commit[:7]}-inc-{identity[:10]}'
    collection = args.collection or f'sanchaya-inc-{commit[:8]}-{identity[:16]}'
    for label, value in (('release ID', release_id), ('collection', collection)):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,127}', value):
            raise ValueError(f'invalid {label}')
    if collection == old_collection or release_id == previous.release_id:
        raise ValueError('candidate must not overwrite the active release/collection')
    summary = {key: value for key, value in plan.items() if key not in ('reuse_from', 'configuration')}
    summary.update(mode='apply' if args.apply else 'plan', previous_release=previous.release_id,
                   sanchaya_commit=commit, release_id=release_id, collection=collection,
                   max_embed_chunks=args.max_embed_chunks,
                   within_embedding_budget=plan['embed_chunks'] <= args.max_embed_chunks,
                   model_downloads=False, active_collection_modified=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if not args.apply:
        return 0
    if plan['legacy_attestation_required']:
        raise ValueError('legacy model identity is unrecorded; inspect the plan and provide --legacy-model-attestation')
    if plan['embed_chunks'] > args.max_embed_chunks:
        raise ValueError('embedding budget exceeded; review the plan before raising --max-embed-chunks')
    release_dir = args.release_root / release_id
    if release_dir.exists():
        candidate = load_release(release_dir / 'release.json')
        if candidate.record['artifacts']['vector_index']['collection'] != collection:
            raise ValueError('completed candidate collection mismatch')
        verify_candidate(client, candidate, chunks, configuration, manifest, ontology_bytes)
        if active_path.read_bytes() != active_bytes:
            raise RuntimeError('active release changed before activation')
        if args.activate:
            activate_record(args.release_root, candidate.record,
                            expected_sha256=hashlib.sha256(active_bytes).hexdigest())
        print(json.dumps({'status': 'active' if args.activate else 'staged',
                          'release_id': release_id, 'embedded_this_run': 0,
                          'mcp_restart_required': bool(args.activate)}, indent=2))
        return 0
    work = args.work_root / 'incremental' / release_id
    work.mkdir(parents=True, exist_ok=True)
    atomic_json(work / 'plan.json', {**summary, 'configuration': configuration})
    atomic_json(work / 'input-manifest.json', manifest)
    write_jsonl(work / 'chunks.jsonl', chunks)
    atomic_json(work / 'chunk-build.json', chunk_summary)
    started = time.monotonic()
    metrics = build_candidate(
        client=client, model=model, point_factory=models.PointStruct,
        old_collection=old_collection, collection=collection, chunks=chunks,
        old_chunks=old_chunks, plan=plan, checkpoint=work / 'checkpoint.json',
        create_collection=lambda name, dimensions: client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE)),
        batch_size=args.batch_size, max_embed_chunks=args.max_embed_chunks)
    vector_run = work / 'vector-run.json'
    atomic_json(vector_run, {
        'schema_version': 'retrieval.vector-build.v1', 'model': args.model,
        'collection': collection, 'dimensions': configuration['dimensions'], 'normalized': True,
        'embedding_configuration': configuration, 'embedding_fingerprint': digest(configuration),
        'chunks_sha256': hashlib.sha256((work / 'chunks.jsonl').read_bytes()).hexdigest(),
        'chunk_count': len(chunks), 'full_chunk_count': len(chunks),
        'incremental': {**summary, **metrics, 'elapsed_seconds': round(time.monotonic() - started, 3)},
    })
    ontology = json.loads(ontology_bytes)
    mentions = list(iter_mentions(chunks, ontology, corpus_revision=commit))
    registry = registry_from_mentions(ontology, mentions, corpus_revision=commit)
    write_jsonl(work / 'entity-mentions.jsonl', mentions)
    write_jsonl(work / 'entity-registry.jsonl', registry)
    atomic_json(work / 'entity-build.json', build_summary(
        ontology=ontology, chunks_seen=len(chunks), mentions=mentions, registry=registry, corpus_revision=commit))
    # Source bytes, ontology and active pointer must still describe the frozen plan.
    if manifest_identity(build_manifest(args.sanchaya_root, args.audit_set, paper_scope=args.paper_scope,
                      sanchaya_scope=args.sanchaya_scope)) != manifest_identity(manifest):
        raise RuntimeError('source manifest changed during candidate build')
    if args.ontology.read_bytes() != ontology_bytes or active_path.read_bytes() != active_bytes:
        raise RuntimeError('ontology or active release changed during candidate build')
    args.no_activate = not args.activate
    args.expected_active_sha256 = hashlib.sha256(active_bytes).hexdigest()
    run_release_build(args, manifest=work / 'input-manifest.json', chunks=work / 'chunks.jsonl',
                      chunk_build=work / 'chunk-build.json', mentions=work / 'entity-mentions.jsonl',
                      registry=work / 'entity-registry.jsonl', entity_build=work / 'entity-build.json',
                      vector_run=vector_run, release_id=release_id)
    print(json.dumps({'status': 'active' if args.activate else 'staged', 'release_id': release_id,
                      'metrics': metrics, 'mcp_restart_required': bool(args.activate)}, indent=2))
    return 0


def main(argv=None) -> int:
    args = parse_args(argv, incremental=True)
    for key in ('sanchaya_root', 'patra_darpan_root', 'work_root', 'release_root',
                'catalog_sqlite', 'ontology', 'audit_set'):
        setattr(args, key, getattr(args, key).expanduser().resolve())
    with build_lock(args.work_root, args.apply):
        return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
