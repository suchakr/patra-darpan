from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from lib.retrieval_chunks import make_chunks_for_source
from lib.retrieval_vectors import (
    build_candidate, digest, embedding_key, payload_for, plan_reuse, point_id,
    validate_inventory, validate_points, validate_vector,
)


CONFIG = dict(model='intfloat/multilingual-e5-base', dimensions=2, normalized=True,
              weights_sha256='a' * 64, tokenizer_sha256='b' * 64, max_seq_length=512)


def chunk(identifier, text=None):
    return dict(chunk_id=identifier, embed_text=text or identifier, content_sha256=digest(text or identifier),
                source_id='pd:test', document_id='pd:test', repo_path='test.md',
                heading_path=['Heading'], logical_location=identifier, chunker_version='v1',
                script_counts={}, source_kind='patra-darpan')


def embedding(config=CONFIG):
    return dict(model=config['model'], dimensions=config['dimensions'], normalized=True,
                configuration=config, fingerprint=digest(config))


class FakeClient:
    def __init__(self):
        self.collections = {}
        self.dimensions = {}
        self.upserts = []
        self.fail_after = None

    def collection_exists(self, name):
        return name in self.collections

    def create(self, name, dimension):
        self.collections[name] = {}
        self.dimensions[name] = dimension

    def create_collection(self, collection_name, vectors_config):
        self.create(collection_name, vectors_config.size)

    def get_collection(self, name):
        return NS(config=NS(params=NS(vectors=NS(size=self.dimensions[name], distance='Cosine'))))

    def scroll(self, collection_name, offset=None, limit=256, **kwargs):
        rows = list(self.collections[collection_name].values())
        position = int(offset or 0)
        return copy.deepcopy(rows[position:position + limit]), (position + limit if position + limit < len(rows) else None)

    def retrieve(self, collection_name, ids, **kwargs):
        return [copy.deepcopy(self.collections[collection_name][i]) for i in ids if i in self.collections[collection_name]]

    def upsert(self, collection_name, points, wait):
        self.upserts.append(collection_name)
        for point in points:
            self.collections[collection_name][str(point.id)] = copy.deepcopy(point)
        if self.fail_after == len(self.upserts):
            raise RuntimeError('interrupted after acknowledged database write')


class FakeModel:
    def __init__(self):
        self.inputs = []

    def encode(self, texts, **kwargs):
        self.inputs.extend(texts)
        return [[0.6, 0.8] for _ in texts]


class VectorReuseTests(unittest.TestCase):
    def test_identical_inputs_are_all_reused(self):
        rows = [chunk('a'), chunk('b')]
        plan = plan_reuse(rows, rows, embedding(), CONFIG)
        self.assertEqual((plan['reuse_chunks'], plan['embed_chunks']), (2, 0))

    def test_added_modified_removed_and_moved_chunks(self):
        old = [chunk('same'), chunk('changed'), chunk('removed'), chunk('old-location', 'unchanged input')]
        new = [chunk('same'), chunk('changed', 'new text'), chunk('added'), chunk('new-location', 'unchanged input')]
        plan = plan_reuse(old, new, embedding(), CONFIG)
        self.assertEqual(plan['reuse_from'], {'same': 'same', 'new-location': 'old-location'})
        self.assertEqual((plan['embed_chunks'], plan['removed_chunk_ids']), (2, 2))

    def test_title_change_is_not_hidden_by_unchanged_chunk_id(self):
        source = dict(source_id='pd:one', repo_path='one.md', title='Old title')
        before = make_chunks_for_source(source, '## Heading\n\nBody of the paper.')
        after = make_chunks_for_source(dict(source, title='New title'), '## Heading\n\nBody of the paper.')
        self.assertEqual(before[0]['chunk_id'], after[0]['chunk_id'])
        self.assertNotEqual(embedding_key(before[0], CONFIG), embedding_key(after[0], CONFIG))
        self.assertEqual(plan_reuse(before, after, embedding(), CONFIG)['embed_chunks'], 1)

    def test_heading_or_truncation_or_weights_change_invalidates_reuse(self):
        rows = [chunk('a')]
        changed_heading = [dict(rows[0], embed_text='Different heading\na')]
        self.assertEqual(plan_reuse(rows, changed_heading, embedding(), CONFIG)['embed_chunks'], 1)
        for key, value in [('weights_sha256', 'changed'), ('tokenizer_sha256', 'changed'),
                           ('max_seq_length', 256), ('model', 'different-model')]:
            with self.subTest(key=key):
                plan = plan_reuse(rows, rows, embedding(), dict(CONFIG, **{key: value}))
                self.assertEqual(plan['reuse_chunks'], 0)

    def test_legacy_requires_exact_explicit_attestation(self):
        old_embedding = {key: CONFIG[key] for key in ('model', 'dimensions', 'normalized')}
        rows = [chunk('a')]
        self.assertTrue(plan_reuse(rows, rows, old_embedding, CONFIG)['legacy_attestation_required'])
        self.assertFalse(plan_reuse(rows, rows, old_embedding, CONFIG, digest(CONFIG))['legacy_attestation_required'])
        with self.assertRaisesRegex(ValueError, 'attestation'):
            plan_reuse(rows, rows, old_embedding, CONFIG, 'wrong')

    def test_corrupt_old_fingerprint_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'corrupt'):
            plan_reuse([chunk('a')], [chunk('a')], dict(embedding(), fingerprint='wrong'), CONFIG)

    def test_empty_or_duplicate_input_rejected(self):
        for rows in ([], [chunk('a'), chunk('a')], [dict(chunk('a'), embed_text=' ')]):
            with self.assertRaises(ValueError):
                validate_inventory(rows)

    def fixture(self, path, old=None, new=None, old_embedding=None, attestation=None):
        old = old or [chunk('a'), chunk('removed')]
        new = new or [chunk('a'), chunk('new')]
        client = FakeClient()
        client.create('serving', 2)
        for row in old:
            identifier = point_id(row['chunk_id'])
            client.collections['serving'][identifier] = NS(id=identifier, vector=[0.6, 0.8], payload=payload_for(row, CONFIG))
        model = FakeModel()
        plan = plan_reuse(old, new, old_embedding or embedding(), CONFIG, attestation)
        kwargs = dict(client=client, model=model, point_factory=NS, old_collection='serving',
                      collection='candidate', chunks=new, old_chunks=old, plan=plan,
                      checkpoint=path / 'state.json', create_collection=client.create, batch_size=1)
        return client, model, kwargs

    def test_build_only_encodes_misses_and_preserves_serving_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            before = copy.deepcopy(client.collections['serving'])
            result = build_candidate(**kwargs)
            self.assertEqual(model.inputs, ['passage: new'])
            self.assertEqual(result['reused_this_run'], 1)
            self.assertEqual(result['embedded_this_run'], 1)
            self.assertEqual(client.collections['serving'], before)
            self.assertNotIn(point_id('removed'), client.collections['candidate'])
            self.assertEqual(set(client.upserts), {'candidate'})

    def test_rerun_and_resume_skip_completed_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            client.fail_after = 1
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                build_candidate(**kwargs)
            client.fail_after = None
            result = build_candidate(**kwargs)
            self.assertEqual(result['resumed_points'], 1)
            self.assertEqual(model.inputs, ['passage: new'])
            model.inputs.clear()
            result = build_candidate(**kwargs)
            self.assertEqual(result['resumed_points'], 2)
            self.assertEqual(model.inputs, [])

    def test_wrong_budget_legacy_or_active_target_never_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            for change in ({'max_embed_chunks': 0}, {'collection': 'serving'},
                           {'batch_size': 0}, {'plan': dict(kwargs['plan'], legacy_attestation_required=True)}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    build_candidate(**dict(kwargs, **change))
            self.assertEqual(client.upserts, [])
            self.assertFalse(kwargs['checkpoint'].exists())

    def test_foreign_collection_or_mismatched_checkpoint_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            client.create('candidate', 2)
            with self.assertRaisesRegex(ValueError, 'unowned'):
                build_candidate(**kwargs)
            kwargs['checkpoint'].write_text(json.dumps({'job_identity': 'different'}))
            with self.assertRaisesRegex(ValueError, 'different build'):
                build_candidate(**kwargs)
            self.assertFalse(client.upserts)

    def test_corrupt_resume_or_missing_source_point_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            build_candidate(**kwargs)
            client.collections['candidate'][point_id('a')].payload['embedding_key'] = 'wrong'
            with self.assertRaisesRegex(ValueError, 'payload'):
                build_candidate(**kwargs)
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            del client.collections['serving'][point_id('a')]
            with self.assertRaisesRegex(ValueError, 'point IDs'):
                build_candidate(**kwargs)

    def test_dimension_distance_and_nonfinite_vectors_rejected(self):
        for vector in ([1], [float('nan'), 0], [0, 0], [2, 0]):
            with self.assertRaises(ValueError):
                validate_vector(vector, 2)
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            build_candidate(**kwargs)
            client.dimensions['candidate'] = 3
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                build_candidate(**kwargs)

    def test_legacy_payload_reused_only_after_attestation(self):
        with tempfile.TemporaryDirectory() as temporary:
            old_embedding = {key: CONFIG[key] for key in ('model', 'dimensions', 'normalized')}
            client, model, kwargs = self.fixture(Path(temporary), old_embedding=old_embedding, attestation=digest(CONFIG))
            for point in client.collections['serving'].values():
                point.payload.pop('embedding_key')
                point.payload.pop('embedding_fingerprint')
            result = build_candidate(**kwargs)
            self.assertEqual(result['reused_this_run'], 1)

    def test_old_point_payload_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            client, model, kwargs = self.fixture(Path(temporary))
            client.collections['serving'][point_id('a')].payload['repo_path'] = 'wrong.md'
            with self.assertRaisesRegex(ValueError, 'payload'):
                build_candidate(**kwargs)


if __name__ == '__main__':
    unittest.main()
