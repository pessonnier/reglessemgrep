"""Semantic candidates, fallback, provenance, and expert-preserving recalculation."""
import json
import tempfile
import unittest
from pathlib import Path

from cast_semgrep.db import connect, create_snapshot, initialize, upsert_rules
from cast_semgrep.matching import calculate_matches, score_pair
from cast_semgrep.semantic_matching import SemanticIndex, apply_semantic_score
from test_core import rule, settings


class SemanticMatchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = settings(Path(self.temp.name))
        self.cast = {**rule('CAST:1', 'CAST', '1', 'Prevent credentials disclosure', ''), 'cwe_json': '[]', 'description': 'Never expose secrets'}
        self.semgrep = {**rule('Semgrep:1', 'Semgrep', '1', 'credential-leakage', ''), 'cwe_json': '[]', 'description': 'Protect authentication material'}
        self.snapshots = {}
        with connect(self.config.db_path) as conn:
            initialize(conn)
            for item in (self.cast, self.semgrep):
                sid = create_snapshot(conn, source=item['source'], revision='v1', archive_path=Path(self.temp.name))
                self.snapshots[item['source']] = sid
                upsert_rules(conn, [item], source=item['source'], snapshot_id=sid)
            conn.execute("INSERT INTO semantic_models VALUES('model','ollama','fixture','sha256:fixture',2,'raw-text-v1','now')")

    def vectors(self, key, title=(1, 0), description=(1, 0), model='model'):
        with connect(self.config.db_path) as conn:
            h = conn.execute('SELECT content_hash FROM semantic_current_documents WHERE rule_key=?', (key,)).fetchone()[0]
            conn.execute('INSERT OR REPLACE INTO semantic_embeddings VALUES(?,?,?,?,?,?,?)',
                         (key, h, model, json.dumps(title) if title is not None else None,
                          json.dumps(description) if description is not None else None, 'now', 'now'))

    def pair(self):
        with connect(self.config.db_path) as conn:
            row = conn.execute('SELECT * FROM match_candidates').fetchone()
            return dict(row) if row else None

    def test_semantic_discovery_without_terms_and_sources_remain_separate(self):
        self.assertEqual(calculate_matches(self.config)['candidates'], 0)
        self.vectors('CAST:1'); self.vectors('Semgrep:1')
        result = calculate_matches(self.config)
        self.assertEqual(result['newly_matched_rules'], {'CAST': 1, 'Semgrep': 1})
        f = json.loads(self.pair()['factors_json'])
        self.assertEqual(f['semantic_points'], 20)
        self.assertEqual(f['semantic_details']['model_key'], 'model')
        self.assertEqual(f['semantic_similarity'], 1)
        self.assertEqual(f['evidence_level'], 'semantic_hypothesis')
        self.assertEqual(f['candidate_origins'], ['semantic'])
        self.assertEqual(self.pair()['suggested_status'], 'indeterminate')
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM match_evidence WHERE dimension LIKE '%semantic%'").fetchone()[0], 0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM llm_proposals').fetchone()[0], 0)
        repeat = calculate_matches(self.config)
        self.assertEqual((repeat['new_pairs'],repeat['removed_pairs'],repeat['changed_scores']), (0,0,0))
        self.assertEqual(calculate_matches(self.config, semantic=False)['candidates'], 0)

    def test_language_incompatibility_and_threshold(self):
        self.vectors('CAST:1'); self.vectors('Semgrep:1', (.7, .71414284), (.7, .71414284))
        self.assertEqual(calculate_matches(self.config)['candidates'], 0)
        self.assertEqual(calculate_matches(self.config, semantic_threshold=.69)['candidates'], 1)
        with connect(self.config.db_path) as conn:
            conn.execute("UPDATE rules SET languages_json='[\"python\"]' WHERE source='Semgrep'")
        self.assertEqual(calculate_matches(self.config, semantic_threshold=.69)['candidates'], 0)

    def test_stale_missing_and_different_model_vectors_not_joined(self):
        self.vectors('CAST:1'); self.vectors('Semgrep:1', description=None)
        self.assertEqual(calculate_matches(self.config)['candidates'], 0)
        self.vectors('Semgrep:1')
        with connect(self.config.db_path) as conn:
            upsert_rules(conn,[{**self.cast,'title':'Updated text'}], source='CAST',snapshot_id=self.snapshots['CAST'])
        self.assertEqual(calculate_matches(self.config)['candidates'], 0)
        self.vectors('CAST:1')
        with connect(self.config.db_path) as conn:
            conn.execute("INSERT INTO semantic_models VALUES('different','openai','other','v1',2,'raw-text-v1','now')")
            conn.execute("UPDATE semantic_embeddings SET model_key='different' WHERE rule_key='Semgrep:1'")
        self.assertEqual(calculate_matches(self.config, semantic_model='model')['candidates'], 0)
        with self.assertRaises(ValueError): calculate_matches(self.config, semantic_model='absent')

    def test_invalid_vectors_and_auto_selection(self):
        self.vectors('CAST:1'); self.vectors('Semgrep:1', (0,0), (0,0))
        result = calculate_matches(self.config)
        self.assertEqual(result['invalid_vectors'], 2)
        self.assertEqual(result['candidates'], 0)
        self.vectors('Semgrep:1')
        with connect(self.config.db_path) as conn:
            conn.execute("INSERT INTO semantic_models VALUES('empty','openai','unused','v1',2,'raw-text-v1','now')")
        self.assertEqual(calculate_matches(self.config)['semantic_model']['model_key'], 'model')

    def test_expert_manual_and_llm_pairs_survive_and_scores_refresh(self):
        self.vectors('CAST:1'); self.vectors('Semgrep:1')
        calculate_matches(self.config)
        with connect(self.config.db_path) as conn:
            conn.execute("UPDATE match_candidates SET factors_json=json_set(factors_json,'$.manual_association',json('true'))")
            conn.execute("INSERT INTO expert_reviews(cast_key,semgrep_key,reviewer,decision,comment,created_at) VALUES('CAST:1','Semgrep:1','expert','no_match','Different principles','now')")
            conn.execute("INSERT INTO llm_proposals(cast_key,semgrep_key,model,proposal_json,created_at) VALUES('CAST:1','Semgrep:1','reviewer','{}','now')")
        old_score = self.pair()['score']
        self.vectors('Semgrep:1', (0,1), (0,1))
        calculate_matches(self.config, min_score=101)
        self.assertLess(self.pair()['score'], old_score)
        self.assertTrue(json.loads(self.pair()['factors_json'])['manual_association'])
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute('SELECT decision,comment FROM expert_reviews').fetchone()[:], ('no_match','Different principles'))
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM llm_proposals').fetchone()[0], 1)

    def test_partial_field_fallback_and_score_bounds(self):
        base = {'technical_compatibility':15,'defect_references':35,'title_similarity':20,'description_similarity':20,'category_similarity':10}
        details = {'title_cosine': 1., 'description_cosine': None, 'combined_cosine':1., 'complete':False}
        score,factors = apply_semantic_score(100,base,details)
        self.assertEqual(score,100)
        self.assertEqual(factors['description_similarity'],20)
        self.assertFalse(factors['semantic_admission'])
        score,_ = apply_semantic_score(100,base,{**details,'title_cosine':-1.})
        self.assertEqual(score,90)
        self.assertEqual(apply_semantic_score(100,base,None), (100,base))
