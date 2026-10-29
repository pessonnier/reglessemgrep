"""Exercise job recovery and real HTTP boundaries without billable calls."""
import io
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from cast_semgrep.db import connect, create_snapshot, initialize, upsert_rules
from cast_semgrep.openai_embeddings import run_embeddings, request_embeddings, validate_response, EmbeddingError
from test_core import rule, settings


class OpenAIEmbeddingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = replace(settings(Path(self.temp.name)), openai_api_key='test-secret')
        self.rule = rule('CAST:1', 'CAST', '1', '  Title\n', 'CWE-89')
        with connect(self.config.db_path) as conn:
            initialize(conn)
            self.snapshot = create_snapshot(conn, source='CAST', revision='test', archive_path=Path(self.temp.name))
        self.update(self.rule)
        self.send = Mock(side_effect=self.response)

    def update(self, value):
        with connect(self.config.db_path) as conn:
            upsert_rules(conn, [value], source='CAST', snapshot_id=self.snapshot)

    @staticmethod
    def response(key, texts, model, dimensions):
        return {'model': model, 'usage': {'total_tokens': 10},
                'data': [{'index': i, 'embedding': [float(i + 1)] * dimensions} for i in reversed(range(len(texts)))]}

    def run_job(self, **kwargs):
        return run_embeddings(self.config, dimensions=3, send=self.send, **kwargs)

    def test_exact_text_response_indices_and_idempotent_resume(self):
        result = self.run_job()
        self.assertEqual(result['saved_vectors'], 2)
        self.assertEqual(self.send.call_args.args[1], ['  Title\n', self.rule['description']])
        with connect(self.config.db_path) as conn:
            row = conn.execute('SELECT * FROM semantic_embeddings').fetchone()
            self.assertEqual(json.loads(row['title_vector_json']), [1, 1, 1])
            self.assertEqual(json.loads(row['description_vector_json']), [2, 2, 2])
        self.assertEqual(self.run_job()['requests'], 0)
        self.assertEqual(self.send.call_count, 1)

    def test_interrupt_resume_only_missing_fields(self):
        self.send.side_effect = [self.response('', ['x'], 'text-embedding-3-small', 3), EmbeddingError('interrupted')]
        with self.assertRaises(EmbeddingError):
            self.run_job(batch_size=1)
        self.send.side_effect = self.response
        result = self.run_job()
        self.assertEqual(result['saved_vectors'], 1)
        self.assertEqual(self.send.call_args.args[1], [self.rule['description']])

    def test_dry_run_missing_key_and_limit(self):
        self.assertEqual(self.run_job(dry_run=True)['pending_vectors'], 2)
        self.send.assert_not_called()
        with self.assertRaisesRegex(EmbeddingError, 'OPENAI_API_KEY absente'):
            run_embeddings(replace(self.config, openai_api_key=''), send=self.send)
        self.send.assert_not_called()
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_models').fetchone()[0], 0)
        self.assertEqual(self.run_job(limit=1)['saved_vectors'], 1)
        self.assertEqual(self.run_job()['saved_vectors'], 1)

    def test_changes_during_request_never_save_stale_vectors(self):
        def change(key, texts, model, dimensions):
            self.update({**self.rule, 'title': 'Changed'})
            return self.response(key, texts, model, dimensions)
        self.send.side_effect = change
        result = self.run_job()
        self.assertEqual(result['stale_vectors'], 2)
        self.assertEqual(result['saved_vectors'], 0)

    def test_history_new_revision_and_empty_or_oversized_text(self):
        self.run_job()
        self.update({**self.rule, 'title': 'Changed'})
        self.assertEqual(self.run_job()['saved_vectors'], 2)
        self.assertEqual(self.run_job(revision='alias-v2')['saved_vectors'], 2)
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0], 3)
        self.update({**self.rule, 'title': ' ', 'description': 'é' * 5000})
        result = self.run_job()
        self.assertEqual(result['selected_vectors'], 0)
        self.assertEqual(result['oversized_fields'], [{'rule_key': 'CAST:1', 'field': 'description'}])

    def test_bad_response_never_partially_saved(self):
        for corrupt in ('duplicate', 'dimension', 'nan', 'model', 'bool', 'missing'):
            response = self.response('', ['a', 'b'], 'text-embedding-3-small', 3)
            if corrupt == 'duplicate': response['data'][1]['index'] = 1
            if corrupt == 'dimension': response['data'][1]['embedding'] = [1]
            if corrupt == 'nan': response['data'][1]['embedding'] = [float('nan')] * 3
            if corrupt == 'model': response['model'] = 'different'
            if corrupt == 'bool': response['data'][1]['embedding'] = [True] * 3
            if corrupt == 'missing': response['data'].pop()
            self.send.side_effect = None
            self.send.return_value = response
            with self.subTest(corrupt=corrupt), self.assertRaises(EmbeddingError):
                self.run_job()
            with connect(self.config.db_path) as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0], 0)

    def test_http_payload_retries_and_secret_safe_errors(self):
        response = self.response('', ['text'], 'text-embedding-3-small', 3)
        with patch('cast_semgrep.openai_embeddings.urlopen', side_effect=[
                HTTPError('url', 429, 'rate limit', {}, None), io.BytesIO(json.dumps(response).encode())]) as open_url, \
                patch('cast_semgrep.openai_embeddings.time.sleep') as sleep:
            self.assertEqual(request_embeddings('test-secret', ['text'], 'text-embedding-3-small', 3), response)
            request = open_url.call_args.args[0]
            self.assertEqual(request.full_url, 'https://api.openai.com/v1/embeddings')
            self.assertEqual(json.loads(request.data)['input'], ['text'])
            self.assertEqual(request.get_header('Authorization'), 'Bearer test-secret')
            sleep.assert_called_once()
        with patch('cast_semgrep.openai_embeddings.urlopen', side_effect=HTTPError('url', 401, 'test-secret', {}, None)) as open_url:
            with self.assertRaises(EmbeddingError) as error:
                request_embeddings('test-secret', ['text'], 'text-embedding-3-small', 3)
            self.assertNotIn('test-secret', str(error.exception))
            open_url.assert_called_once()

    def test_batch_byte_limit(self):
        self.update({**self.rule, 'title': 'a' * 8191, 'description': 'b' * 8191})
        with patch('cast_semgrep.openai_embeddings.MAX_BATCH_BYTES', 10_000):
            result = self.run_job()
        self.assertEqual(result['requests'], 2)
