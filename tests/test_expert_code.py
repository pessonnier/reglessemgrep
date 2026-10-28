"""Expert examples are versioned text, never executable or implicit scan results."""

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from cast_semgrep import api
from cast_semgrep.db import connect, create_snapshot, initialize, upsert_rules, MIGRATIONS
from cast_semgrep.matching import calculate_matches
from test_core import rule, settings


class ExpertCodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = settings(Path(self.temp.name))
        self.previous = api.settings
        api.settings = self.config
        with connect(self.config.db_path) as conn:
            # Build a genuine v4 database with a pre-existing expert opinion.
            for name in ('001_initial.sql','002_categories.sql','003_owasp_raw.sql','004_uncertainty.sql'):
                conn.executescript((MIGRATIONS/name).read_text())
            conn.execute('PRAGMA user_version=4')
            for source,key in [('CAST','CAST:1'),('Semgrep','Semgrep:1')]:
                snapshot=create_snapshot(conn, source=source, revision='test', archive_path=Path(self.temp.name))
                item=rule(key,source,'1','SQL injection','CWE-89')
                item['definition_hash']='a'*64
                upsert_rules(conn,[item],source=source,snapshot_id=snapshot)
            conn.execute("INSERT INTO match_candidates VALUES('CAST:1','Semgrep:1',70,'{}','indeterminate','test')")
            conn.execute("INSERT INTO expert_reviews(cast_key,semgrep_key,reviewer,decision,comment,created_at) VALUES('CAST:1','Semgrep:1','Previous expert','indeterminate','Existing opinion','test')")
            initialize(conn)

    def tearDown(self):
        api.settings=self.previous
        self.temp.cleanup()

    def test_migration_preserves_old_opinions_and_defaults_to_no_examples(self):
        with connect(self.config.db_path) as conn:
            initialize(conn)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],5)
        old=api.get_match('CAST:1','Semgrep:1')['expert_reviews'][0]
        self.assertEqual(old['comment'],'Existing opinion')
        self.assertEqual(old['code_examples'],[])

    def test_multiple_examples_preserve_code_and_history_across_recalculation(self):
        source='  if user_input:\n\tprint("<script>alert(1)</script>")\n\n'
        examples=[api.CodeExample(title='Example',language='python',kind='vulnerable',code=source,explanation='Illustration only'),
                  api.CodeExample(title='Correction',language='python',kind='safe',code='print("constant")\n')]
        saved=api.add_review(api.ReviewInput(cast_key='CAST:1',semgrep_key='Semgrep:1',reviewer='Expert',decision='partial',code_examples=examples))
        self.assertEqual(saved['code_examples'][0]['code'],source)
        api.add_review(api.ReviewInput(cast_key='CAST:1',semgrep_key='Semgrep:1',reviewer='Expert',decision='indeterminate'))
        calculate_matches(self.config)
        comparison=api.get_match('CAST:1','Semgrep:1')
        self.assertEqual(comparison['expert_reviews'][0]['code_examples'],[])
        self.assertEqual(comparison['expert_reviews'][1]['code_examples'][0]['code'],source)
        self.assertEqual(len(comparison['expert_reviews'][1]['code_examples']),2)
        self.assertEqual(comparison['llm_proposals'],[])

    def test_uncertainty_examples_stay_in_history_after_definition_changes(self):
        saved=api.add_uncertainty_assessment(api.UncertaintyInput(
            rule_key='Semgrep:1',source_version='test',definition_hash='a'*64,reviewer='Expert',
            uncertainty_level='high',false_positive_risk='unknown',false_negative_risk='unknown',
            scope='Java',rationale='Case to examine',code_examples=[api.CodeExample(language='java',kind='boundary',code='  query(value);\n')]))
        current=api.get_rule('Semgrep:1')
        self.assertEqual(current['uncertainty']['code_examples'],saved['code_examples'])
        with connect(self.config.db_path) as conn:
            conn.execute("UPDATE rules SET definition_hash=? WHERE rule_key='Semgrep:1'",('b'*64,))
        current=api.get_rule('Semgrep:1')
        self.assertEqual(current['uncertainty']['status'],'stale')
        self.assertEqual(current['uncertainty']['code_examples'],[])
        self.assertEqual(current['uncertainty_history'][0]['code_examples'][0]['code'],'  query(value);\n')

    def test_invalid_examples_are_rejected(self):
        for data in ({'code':'  \n\t'}, {'code':'x'*20001}, {'code':'x','kind':'executed'}, {'code':'x','language':'x'*81}):
            with self.subTest(data_size=len(data.get('code',''))),self.assertRaises(ValidationError):
                api.CodeExample(**data)
        with self.assertRaises(ValidationError):
            api.ReviewInput(cast_key='CAST:1',semgrep_key='Semgrep:1',reviewer='Expert',decision='partial',code_examples=[{'code':'x'}]*11)


if __name__ == '__main__':
    unittest.main()
