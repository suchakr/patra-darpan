from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

from lib.retrieval_adapters import Release, VectorAdapter
from lib.retrieval_release_state import activate_record
from lib.retrieval_vectors import atomic_json, digest, payload_for, point_id
from scripts import build_retrieval_incremental as incremental
from scripts import create_retrieval_release as release_builder
from scripts.build_retrieval_index import parse_args
from test_retrieval_vectors import CONFIG, FakeClient, FakeModel, chunk, embedding


HAS_QDRANT = bool(importlib.util.find_spec('qdrant_client'))


class IncrementalCommandTests(unittest.TestCase):
    def test_cli_is_plan_by_default(self):
        args = parse_args([], incremental=True)
        self.assertFalse(args.apply)
        self.assertFalse(args.activate)
        self.assertEqual(args.max_embed_chunks, 2000)

    def test_invalid_activation_rejected_before_loading_dependencies(self):
        with self.assertRaisesRegex(ValueError, 'requires --apply'):
            incremental.run(parse_args(['--activate'], incremental=True))

    def test_manifest_identity_ignores_only_timestamp(self):
        self.assertEqual(incremental.manifest_identity({'generated_at': 'one', 'sources': [1]}),
                         incremental.manifest_identity({'generated_at': 'two', 'sources': [1]}))
        self.assertNotEqual(incremental.manifest_identity({'sources': [1]}),
                            incremental.manifest_identity({'sources': [2]}))

    def test_concurrent_build_refused_and_plan_creates_no_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'build'
            with incremental.build_lock(root, False):
                self.assertFalse(root.exists())
            with incremental.build_lock(root, True):
                with self.assertRaisesRegex(RuntimeError, 'another incremental'):
                    with incremental.build_lock(root, True):
                        pass

    def test_activation_checks_the_expected_pointer_and_preserves_old_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active = root / 'active-release.json'
            atomic_json(active, {'release_id': 'old'})
            before = active.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                activate_record(root, {'release_id': 'new'}, expected_sha256='wrong')
            self.assertEqual(active.read_bytes(), before)
            activate_record(root, {'release_id': 'new'}, expected_sha256=hashlib.sha256(before).hexdigest())
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                activate_record(root, {'release_id': 'another'}, expected_release_id='old')
            self.assertEqual(json.loads(active.read_text())['release_id'], 'new')


@unittest.skipUnless(HAS_QDRANT, 'optional qdrant-client required')
class IncrementalOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.releases = self.root / 'releases'
        self.releases.mkdir()
        self.active = self.releases / 'active-release.json'
        self.old = [chunk('same'), chunk('removed')]
        self.new = [chunk('same'), chunk('new')]
        self.ontology = self.root / 'ontology.json'
        self.ontology.write_text('{}')
        self.manifest = {'generated_at': 'one', 'sanchaya': {'commit': 'b' * 40},
                         'sources': [], 'selection': {'paper_scope': 'all', 'sanchaya_scope': 'jyotisham'}}
        self.client = FakeClient()
        self.client.create('serving', 2)
        for row in self.old:
            identifier = point_id(row['chunk_id'])
            self.client.collections['serving'][identifier] = NS(id=identifier, vector=[0.6, 0.8],
                                                               payload=payload_for(row, CONFIG))
        self.model = FakeModel()
        old_manifest = dict(self.manifest, sanchaya={'commit': 'a' * 40})
        record = self.make_record('old-release', 'serving', self.old, old_manifest)
        atomic_json(self.active, record)
        self.before_active = self.active.read_bytes()
        self.created = []
        for target, value in [
            ('qdrant_client.QdrantClient', lambda **kwargs: self.client),
            ('scripts.build_retrieval_incremental.embedding_configuration', lambda *args: CONFIG),
            ('scripts.build_retrieval_incremental.build_manifest', lambda *args, **kwargs: copy.deepcopy(self.manifest)),
            ('scripts.build_retrieval_incremental.build_chunks', lambda *args, **kwargs: (self.new, {'chunk_count': len(self.new)})),
            ('scripts.build_retrieval_incremental.iter_mentions', lambda *args, **kwargs: []),
            ('scripts.build_retrieval_incremental.registry_from_mentions', lambda *args, **kwargs: []),
            ('scripts.build_retrieval_incremental.build_summary', lambda **kwargs: {}),
            ('scripts.build_retrieval_incremental.run_release_build', self.create_release),
        ]:
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict('sys.modules', sentence_transformers=NS(SentenceTransformer=lambda *args, **kwargs: self.model))
        p.start()
        self.addCleanup(p.stop)

    def args(self, *flags):
        return parse_args(['--release-root', str(self.releases), '--work-root', str(self.root / 'build'),
                           '--ontology', str(self.ontology), *flags], incremental=True)

    def make_record(self, release_id, collection, chunks, manifest):
        directory = self.releases / release_id
        directory.mkdir()
        (directory / 'chunks.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in chunks))
        (directory / 'input-manifest.json').write_text(json.dumps(manifest))
        (directory / 'ontology.json').write_bytes(self.ontology.read_bytes())
        artifacts = {}
        for name, filename in [('chunks', 'chunks.jsonl'), ('input_manifest', 'input-manifest.json'),
                               ('ontology_snapshot', 'ontology.json')]:
            path = directory / filename
            artifacts[name] = {'path': f'{release_id}/{filename}', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        artifacts['vector_index'] = {'collection': collection, 'dimensions': 2}
        record = {'schema_version': 'retrieval.release.v1', 'status': 'ready', 'release_id': release_id,
                  'source': {'sanchaya_commit': manifest['sanchaya']['commit']},
                  'artifacts': artifacts, 'pipeline': {'embedding': embedding()}}
        atomic_json(directory / 'release.json', record)
        return record

    def create_release(self, args, **kwargs):
        record = self.make_record(kwargs['release_id'],
                                  json.loads(kwargs['vector_run'].read_text())['collection'],
                                  self.new, self.manifest)
        self.created.append(record)
        if not args.no_activate:
            atomic_json(self.active, record)

    def execute(self, *flags):
        with redirect_stdout(io.StringIO()):
            return incremental.run(self.args(*flags))

    def test_read_only_plan_writes_nothing_and_encodes_nothing(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.execute()
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.model.inputs, [])
        self.assertFalse(self.client.upserts)

    def test_stage_activate_and_unchanged_rerun(self):
        before_serving = copy.deepcopy(self.client.collections['serving'])
        self.execute('--apply')
        self.assertEqual(self.active.read_bytes(), self.before_active)
        self.assertEqual(self.model.inputs, ['passage: new'])
        self.assertEqual(self.client.collections['serving'], before_serving)
        self.model.inputs.clear()
        self.manifest['generated_at'] = 'later'
        self.execute('--apply', '--activate')
        self.assertEqual(len(self.created), 1)
        self.assertEqual(self.model.inputs, [])
        self.assertNotEqual(self.active.read_bytes(), self.before_active)
        upserts = list(self.client.upserts)
        self.execute('--apply', '--activate')
        self.assertEqual(self.client.upserts, upserts)
        self.assertEqual(len(self.created), 1)

    def test_source_or_active_pointer_changes_prevent_release_publication(self):
        original_encode = self.model.encode

        def change_during_encode(texts, **kwargs):
            self.manifest['sources'].append({'changed': True})
            return original_encode(texts, **kwargs)

        self.model.encode = change_during_encode
        with self.assertRaisesRegex(RuntimeError, 'source manifest changed'):
            self.execute('--apply', '--activate')
        self.assertEqual(self.active.read_bytes(), self.before_active)
        self.assertFalse(self.created)

    def test_active_pointer_race_prevents_activation(self):
        original_encode = self.model.encode

        def change_during_encode(texts, **kwargs):
            self.active.write_bytes(self.before_active + b'\n')
            return original_encode(texts, **kwargs)

        self.model.encode = change_during_encode
        with self.assertRaisesRegex(RuntimeError, 'active release changed'):
            self.execute('--apply', '--activate')
        self.assertFalse(self.created)


@unittest.skipUnless(HAS_QDRANT, 'optional qdrant-client required')
class QdrantLocalIntegrationTests(unittest.TestCase):
    def test_actual_sdk_copy_embed_verify_and_resume(self):
        from qdrant_client import QdrantClient, models
        from lib.retrieval_vectors import build_candidate, plan_reuse
        client = QdrantClient(location=':memory:')
        self.addCleanup(client.close)

        def create(name, dimensions):
            client.create_collection(collection_name=name,
                                     vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE))

        old = [chunk('a'), chunk('removed')]
        new = [chunk('moved-a', 'a'), chunk('new')]
        create('serving', 2)
        client.upsert(collection_name='serving', points=[models.PointStruct(
            id=point_id(row['chunk_id']), vector=[0.6, 0.8], payload=payload_for(row, CONFIG)) for row in old], wait=True)
        with tempfile.TemporaryDirectory() as temporary:
            model = FakeModel()
            kwargs = dict(client=client, model=model, point_factory=models.PointStruct,
                          old_collection='serving', collection='candidate', chunks=new, old_chunks=old,
                          plan=plan_reuse(old, new, embedding(), CONFIG),
                          checkpoint=Path(temporary) / 'state.json', create_collection=create)
            first = build_candidate(**kwargs)
            second = build_candidate(**kwargs)
            self.assertEqual((first['reused_this_run'], first['embedded_this_run']), (1, 1))
            self.assertEqual(second['resumed_points'], 2)
            self.assertEqual(model.inputs, ['passage: new'])
            self.assertEqual(client.count('serving', exact=True).count, 2)
            self.assertEqual(client.count('candidate', exact=True).count, 2)


class QueryFingerprintTests(unittest.TestCase):
    def test_query_model_mismatch_fails_closed_on_every_attempt(self):
        release = Release(Path('/unused'), {'pipeline': {'embedding': embedding()},
                                          'artifacts': {'vector_index': {'collection': 'serving'}}})
        adapter = VectorAdapter(release, qdrant_url='http://unused')
        with patch.dict('sys.modules', qdrant_client=NS(QdrantClient=lambda **kwargs: object()),
                        sentence_transformers=NS(SentenceTransformer=lambda *args, **kwargs: object())), \
                patch('lib.retrieval_vectors.embedding_configuration', return_value=dict(CONFIG, weights_sha256='wrong')):
            for _ in range(2):
                with self.assertRaisesRegex(Exception, 'differs from the active release'):
                    adapter._load()
                self.assertIsNone(adapter._model)

    def test_query_loads_verified_revision_without_download(self):
        configuration = dict(CONFIG, resolved_revision='a' * 40)
        release = Release(Path('/unused'), {'pipeline': {'embedding': embedding(configuration)},
                                          'artifacts': {'vector_index': {'collection': 'serving'}}})
        adapter = VectorAdapter(release, qdrant_url='http://unused')
        with patch.dict('sys.modules', qdrant_client=NS(QdrantClient=lambda **kwargs: object()),
                        sentence_transformers=NS(SentenceTransformer=lambda *args, **kwargs: object())), \
                patch('lib.retrieval_vectors.embedding_configuration', return_value=configuration):
            self.assertIsNotNone(adapter._load()[1])


class ReleaseRecordIntegrationTests(unittest.TestCase):
    def test_materialized_release_keeps_configuration_and_validates_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sanchaya = root / 'sanchaya'
            corpus = sanchaya / 'patra-darpan/catalog/corpus-manifest.jsonl'
            corpus.parent.mkdir(parents=True)
            corpus.write_text('{}\n')
            canonical = root / 'canonical.sqlite'
            with sqlite3.connect(canonical) as conn:
                conn.executescript('''
                    CREATE TABLE documents (doc_id TEXT PRIMARY KEY, title TEXT,
                      author_display TEXT, year TEXT, journal_label TEXT);
                    CREATE TABLE asset_refs (asset_id INTEGER PRIMARY KEY, doc_id TEXT,
                      asset_role TEXT, remote_url TEXT, local_rel_path TEXT, gcs_key TEXT);
                    INSERT INTO documents VALUES ('test', 'Test', 'Author', '2024', 'IJHS');
                ''')
            release_id = 'test-incremental'
            release_dir = root / 'releases' / release_id
            release_dir.mkdir(parents=True)
            manifest = root / 'input.json'
            atomic_json(manifest, {'sanchaya': {'commit': 'd' * 40}, 'sources': [{
                'source_kind': 'patra-darpan', 'document_id': 'pd:test', 'title': 'Test',
                'repo_path': 'patra-darpan/papers/test/document.md'}], 'selection': {'paper_count': 1}})
            chunks = root / 'chunks.jsonl'
            chunks.write_text(json.dumps(chunk('a')) + '\n')
            mentions = root / 'mentions.jsonl'
            mentions.write_text('')
            registry = root / 'registry.jsonl'
            registry.write_text('')
            chunk_build = root / 'chunk-build.json'
            atomic_json(chunk_build, {'chunker_version': 'v1', 'chunk_count': 1})
            entity_build = root / 'entity-build.json'
            atomic_json(entity_build, {'extractor_version': 'v1', 'mention_count': 0})
            vector_run = root / 'vector-run.json'
            atomic_json(vector_run, {'model': CONFIG['model'], 'collection': 'candidate', 'dimensions': 2,
                                    'chunk_count': 1, 'embedding_configuration': CONFIG,
                                    'embedding_fingerprint': digest(CONFIG)})
            ontology = root / 'ontology.json'
            ontology.write_text('{}')
            args = NS(input_manifest=manifest, chunk_build=chunk_build, entity_build=entity_build,
                      vector_run=vector_run, sanchaya_root=sanchaya, patra_darpan_root=root,
                      catalog_sqlite=canonical, source_manifest=manifest, chunks=chunks,
                      mentions=mentions, registry=registry, ontology=ontology, notes='test')
            with patch.object(release_builder, 'ROOT', root), \
                    patch.object(release_builder, 'git_revision', return_value='d' * 40), \
                    patch.object(release_builder, 'git_origin', return_value='https://example.invalid/repo'):
                record = release_builder.build_record(args, release_id, release_dir)
            self.assertEqual(record['pipeline']['embedding']['fingerprint'], digest(CONFIG))
            self.assertEqual(record['pipeline']['embedding']['configuration'], CONFIG)
            self.assertTrue((release_dir / 'vector-build.json').exists())
            self.assertTrue((release_dir / 'ontology.json').exists())
            if importlib.util.find_spec('jsonschema'):
                import jsonschema
                schema = json.loads((Path(__file__).resolve().parents[1] / 'docs/retrieval/release.schema.json').read_text())
                jsonschema.Draft202012Validator(schema).validate(record)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'optional torch required')
class ActualWeightFingerprintTests(unittest.TestCase):
    def test_weight_tokenizer_revision_and_sequence_changes_alter_fingerprint(self):
        import torch
        from lib.retrieval_vectors import embedding_configuration
        class Module:
            auto_model = NS(config=NS(_commit_hash='c' * 40))
            def get_config_dict(self):
                return {'pooling': 'mean'}
        module = Module()
        weights = {'tensor': torch.tensor([[0.1, 0.2]], dtype=torch.float32)}
        tokenizer = NS(backend_tokenizer=NS(to_str=lambda: 'tokenizer-v1'))
        model = NS(state_dict=lambda: weights, tokenizer=tokenizer, _modules={'0': module},
                   _first_module=lambda: module, max_seq_length=512,
                   get_sentence_embedding_dimension=lambda: 2)
        with patch('lib.retrieval_vectors.importlib.metadata.version', return_value='test'):
            first = embedding_configuration(model, CONFIG['model'])
            self.assertEqual(first, embedding_configuration(model, CONFIG['model']))
            weights['tensor'][0, 0] = 0.5
            changed = embedding_configuration(model, CONFIG['model'])
            self.assertNotEqual(first['weights_sha256'], changed['weights_sha256'])
            model.max_seq_length = 256
            self.assertNotEqual(digest(changed), digest(embedding_configuration(model, CONFIG['model'])))


if __name__ == '__main__':
    unittest.main()
