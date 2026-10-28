"""CAST remains visible, including rules with no match or outdated candidates."""

import tempfile
import unittest
from pathlib import Path

from cast_semgrep import api
from cast_semgrep.db import connect, create_snapshot, initialize, upsert_rules
from test_core import rule, settings


class CorrespondenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = settings(Path(self.temp.name))
        self.previous = api.settings
        api.settings = self.config
        with connect(self.config.db_path) as conn:
            initialize(conn)
            for source, items in (
                ('CAST', [rule('CAST:1','CAST','1','SQL injection','CWE-89'),
                          rule('CAST:2','CAST','2','No candidate','CWE-999'),
                          rule('CAST:3','CAST','3','Removed candidate','CWE-90')]),
                ('Semgrep', [rule(f'Semgrep:{i}','Semgrep',str(i),f'Semgrep detection {i}','CWE-89') for i in range(1,6)]),
            ):
                snapshot = create_snapshot(conn, source=source, revision='test', archive_path=Path(self.temp.name))
                upsert_rules(conn, items, source=source, snapshot_id=snapshot)
            for i in range(1,5):
                conn.execute("INSERT INTO match_candidates VALUES(?,?,?,?,?,?)", ('CAST:1',f'Semgrep:{i}',90-i,'{}','indeterminate','test'))
            conn.execute("INSERT INTO match_candidates VALUES(?,?,?,?,?,?)", ('CAST:3','Semgrep:5',100,'{}','indeterminate','test'))
            conn.execute("UPDATE rules SET status='removed' WHERE rule_key='Semgrep:5'")

    def tearDown(self):
        api.settings = self.previous
        self.temp.cleanup()

    def test_all_cast_rules_and_one_to_many_preview(self):
        data = api.list_correspondences(page=1,page_size=20)
        self.assertEqual(data['total'],3)
        self.assertEqual(data['summary'], {'cast_count':3,'with_candidates':1,'without_candidates':2,'with_expert_equivalent':0})
        first = data['items'][0]
        self.assertEqual(first['rule_key'],'CAST:1')
        self.assertEqual(first['candidate_count'],4)
        self.assertEqual(len(first['matches']),3)
        self.assertEqual(first['matches'][0]['languages'],['java'])
        self.assertTrue(all(x['uncertainty_level']=='high' and x['expert_decision'] is None for x in first['matches']))
        self.assertEqual({x['rule_key'] for x in data['items'] if not x['matches']}, {'CAST:2','CAST:3'})

    def test_no_candidate_filter_includes_removed_only_candidates(self):
        data=api.list_correspondences(status='without_candidates',page=1,page_size=20)
        self.assertEqual(data['total'],2)
        self.assertEqual(data['summary']['cast_count'],3)
        self.assertEqual(api.list_matches('CAST:3',limit=30,offset=0)['total'],0)

    def test_latest_expert_decision_controls_filter_and_preview(self):
        payload=api.ReviewInput(cast_key='CAST:1',semgrep_key='Semgrep:4',reviewer='Expert',decision='equivalent')
        api.add_review(payload)
        result=api.list_correspondences(status='expert_equivalent',page=1,page_size=20)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['matches'][0]['semgrep_key'],'Semgrep:4')
        self.assertEqual(result['items'][0]['matches'][0]['expert_decision'],'equivalent')
        api.add_review(payload.model_copy(update={'decision':'partial'}))
        result=api.list_correspondences(status='expert_equivalent',page=1,page_size=20)
        self.assertEqual(result['total'],0)
        self.assertEqual(result['summary']['with_expert_equivalent'],0)

    def test_search_both_catalogues_and_page_by_cast_not_pair(self):
        self.assertEqual(api.list_correspondences(q='Semgrep detection 4',page=1,page_size=20)['items'][0]['rule_key'],'CAST:1')
        self.assertEqual(api.list_correspondences(q='No candidate',page=1,page_size=20)['total'],1)
        self.assertEqual(api.list_correspondences(cwe='CWE-89',language='java',page=1,page_size=20)['total'],1)
        first=api.list_correspondences(page=1,page_size=1)
        second=api.list_correspondences(page=2,page_size=1)
        self.assertEqual(first['total'],3)
        self.assertNotEqual(first['items'][0]['rule_key'],second['items'][0]['rule_key'])
        self.assertEqual(api.list_correspondences(q='impossible',page=1,page_size=20)['items'],[])

    def test_cast_explorer_ignores_lingering_semgrep_filters(self):
        data=api.list_rules(source='CAST',uncertainty_level='high',assessment_status='not_evaluated',
                            false_positive_risk='low',false_negative_risk='high',page=1,page_size=30)
        self.assertEqual(data['total'],3)
        self.assertTrue(all(x['source']=='CAST' for x in data['items']))
        self.assertEqual(api.list_rules(source='Semgrep',false_positive_risk='low',page=1,page_size=30)['total'],0)

    def test_rule_detail_paginates_all_pairs(self):
        first=api.list_matches('CAST:1',limit=3,offset=0)
        second=api.list_matches('CAST:1',limit=3,offset=3)
        self.assertEqual(first['total'],4)
        self.assertEqual(len(first['items']),3)
        self.assertEqual(len(second['items']),1)
        self.assertEqual({x['semgrep_key'] for x in first['items']}&{x['semgrep_key'] for x in second['items']},set())


if __name__ == '__main__':
    unittest.main()
