"""Ollama contract, model provenance and resumable multi-provider persistence."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from cast_semgrep.db import connect, initialize, create_snapshot, upsert_rules
from cast_semgrep.ollama_embeddings import OllamaClient, run_embeddings, EmbeddingError, DEFAULT_MODEL
from test_core import rule, settings

DIGEST = 'a' * 64


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = settings(Path(self.temp.name))
        self.rule = rule('CAST:1', 'CAST', '1', ' exact\ntitle ', 'CWE-89')
        with connect(self.config.db_path) as conn:
            initialize(conn)
            self.snapshot = create_snapshot(conn, source='CAST', revision='v1', archive_path=Path(self.temp.name))
            upsert_rules(conn, [self.rule], source='CAST', snapshot_id=self.snapshot)
        self.client = OllamaClient()
        self.response = {'model': DEFAULT_MODEL, 'embeddings': [[1, 2, 3], [3, 2, 1]], 'prompt_eval_count': 12}

        def request(path, payload=None):
            if path == '/api/tags': return {'models': [{'name': DEFAULT_MODEL, 'digest': DIGEST}]}
            if path == '/api/show': return {'capabilities': ['embedding'], 'model_info': {'general.architecture': 'bert', 'bert.embedding_length': 3}}
            if path == '/api/embed': return self.response
            raise AssertionError(path)
        self.client.request = Mock(side_effect=request)

    def job(self, **kwargs):
        return run_embeddings(self.config, client=self.client, **kwargs)

    def test_contract_digest_and_idempotent_resume(self):
        result = self.job()
        self.assertEqual(result['saved_vectors'], 2)
        payload = next(c.args[1] for c in self.client.request.call_args_list if c.args[0] == '/api/embed')
        self.assertEqual(payload['input'], [self.rule['title'], self.rule['description']])
        self.assertIs(payload['truncate'], False)
        self.assertEqual(payload['model'], DEFAULT_MODEL)
        with connect(self.config.db_path) as conn:
            model = conn.execute('SELECT * FROM semantic_models').fetchone()
            self.assertEqual(model['provider'], 'ollama')
            self.assertEqual(model['model_revision'], 'sha256:' + DIGEST)
            self.assertEqual(model['dimensions'], 3)
        self.client.request.reset_mock()
        self.assertEqual(self.job()['requests'], 0)
        self.assertFalse(any(c.args[0] == '/api/embed' for c in self.client.request.call_args_list))

    def test_dry_run_no_inference_or_registration(self):
        result = self.job(dry_run=True)
        self.assertEqual(result['pending_vectors'], 2)
        self.assertFalse(any(c.args[0] == '/api/embed' for c in self.client.request.call_args_list))
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_models').fetchone()[0], 0)

    def test_reject_generation_model_or_unknown_dimensions(self):
        for metadata in ({'capabilities': ['completion']}, {'capabilities': ['embedding'], 'model_info': {}}):
            original = self.client.request.side_effect
            self.client.request.side_effect = lambda path, payload=None: metadata if path == '/api/show' else original(path, payload)
            with self.assertRaises(EmbeddingError): self.job()
            self.client.request.side_effect = original

    def test_response_validation_atomicity(self):
        for response in (
            {'model': DEFAULT_MODEL, 'embeddings': [[1, 2, 3]]},
            {'model': DEFAULT_MODEL, 'embeddings': [[1, 2, 3], [0, 0, 0]]},
            {'model': DEFAULT_MODEL, 'embeddings': [[1, 2, 3], [1, float('nan'), 3]]},
            {'model': DEFAULT_MODEL, 'embeddings': [[1, 2, 3], [1, 2]]},
            {'model': 'other', 'embeddings': [[1, 2, 3], [3, 2, 1]]},
        ):
            self.response = response
            with self.subTest(response=response), self.assertRaises(EmbeddingError): self.job()
            with connect(self.config.db_path) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0], 0)

    def test_digest_change_during_inference_rejects_entire_batch(self):
        original = self.client.request.side_effect
        changed = False
        def request(path, payload=None):
            nonlocal changed
            if path == '/api/embed': changed = True
            if path == '/api/tags' and changed:
                return {'models': [{'name': DEFAULT_MODEL, 'digest': 'b' * 64}]}
            return original(path, payload)
        self.client.request.side_effect = request
        with self.assertRaisesRegex(EmbeddingError, 'changé'): self.job()
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0], 0)

    def test_new_digest_creates_separate_model(self):
        self.job()
        original = self.client.request.side_effect
        self.client.request.side_effect = lambda path, payload=None: {'models': [{'name': DEFAULT_MODEL, 'digest': 'b' * 64}]} if path == '/api/tags' else original(path, payload)
        self.assertEqual(self.job()['saved_vectors'], 2)
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_models').fetchone()[0], 2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0], 2)

    def test_loopback_only_and_http_error(self):
        for url in ('http://example.com', 'http://127.0.0.1/api', 'http://user:secret@localhost', 'file:///tmp/test'):
            with self.subTest(url=url), self.assertRaises(EmbeddingError): OllamaClient(url)
        for url in ('http://127.0.0.1:11436', 'http://localhost:11434', 'http://[::1]:11434'):
            self.assertEqual(OllamaClient(url).base_url, url)
        client = OllamaClient()
        client.opener = Mock()
        client.opener.open.side_effect = [HTTPError('url', 503, 'body', {}, None), io.BytesIO(b'{"models": []}')]
        with patch('cast_semgrep.ollama_embeddings.time.sleep'):
            self.assertEqual(client.models(), [])
        self.assertEqual(client.opener.open.call_count, 2)
        client.opener.open.side_effect = HTTPError('url', 400, 'sensitive body', {}, None)
        with self.assertRaises(EmbeddingError) as error: client.request('/api/embed', {})
        self.assertNotIn('sensitive body', str(error.exception))
