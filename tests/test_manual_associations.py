"""Manual expert workflow, orphan semantics, persistence and HTTP contract."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from fastapi import HTTPException
from cast_semgrep import api
from cast_semgrep.db import connect, initialize, create_snapshot, upsert_rules
from cast_semgrep.matching import calculate_matches
from test_core import rule, settings


async def http_request(method, path, body=None, query=None):
    """Exercise the ASGI contract without another test dependency or network server."""
    messages = []
    async def receive():
        return {'type': 'http.request', 'body': json.dumps(body).encode() if body is not None else b'', 'more_body': False}
    async def send(message):
        messages.append(message)
    await api.app({'type':'http', 'asgi':{'version':'3.0'}, 'http_version':'1.1', 'method':method,
                   'scheme':'http', 'path':path, 'raw_path':path.encode(),
                   'query_string':urlencode(query or {}).encode(), 'headers':[(b'content-type',b'application/json')],
                   'client':('127.0.0.1',1234), 'server':('localhost',80), 'root_path':''}, receive, send)
    status = next(m['status'] for m in messages if m['type']=='http.response.start')
    data = b''.join(m.get('body', b'') for m in messages if m['type']=='http.response.body')
    return status, json.loads(data)


class ManualAssociationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = settings(Path(self.temp.name))
        self.previous = api.settings
        api.settings = self.config
        self.config.data_dir.mkdir(parents=True)
        raw = self.config.data_dir/'rule.yaml'
        raw.write_text('rules:\n  - id: example\n    pattern: foo(...)\n')
        with connect(self.config.db_path) as conn:
            initialize(conn)
            for source in ('CAST','Semgrep'):
                snapshot = create_snapshot(conn, source=source, revision='test', archive_path=self.config.data_dir)
                items = [rule(f'{source}:{i}', source, str(i), f'SQL injection {i}', 'CWE-89') for i in range(1,4)]
                for item in items: item['raw_path'] = str(raw)
                upsert_rules(conn, items, source=source, snapshot_id=snapshot)
            conn.execute("UPDATE rules SET status='removed' WHERE rule_key IN ('CAST:3','Semgrep:3')")
            conn.execute("INSERT INTO match_candidates VALUES('CAST:3','Semgrep:2',20,'{}','indeterminate','test')")

    def tearDown(self):
        api.settings = self.previous
        self.temp.cleanup()

    def unmatched(self, **kwargs):
        return api.list_unmatched_semgrep(page=1,page_size=20,**kwargs)

    def test_orphans_ignore_removed_rules_and_support_filters_and_pagination(self):
        self.assertEqual(self.unmatched()['total'], 2)
        self.assertEqual(self.unmatched(q='SQL injection 2',language='JAVA',cwe='cwe-89')['items'][0]['rule_key'], 'Semgrep:2')
        self.assertEqual(self.unmatched(q='absent')['total'], 0)
        first=api.list_unmatched_semgrep(page=1,page_size=1)
        second=api.list_unmatched_semgrep(page=2,page_size=1)
        self.assertNotEqual(first['items'][0]['rule_key'],second['items'][0]['rule_key'])
        api.add_manual_candidate(api.ManualCandidateInput(cast_key='CAST:1',semgrep_key='Semgrep:1'))
        self.assertEqual(self.unmatched()['total'], 1)
        # An explicit negative opinion still denotes an identified pair, not an orphan.
        api.add_review(api.ReviewInput(cast_key='CAST:1',semgrep_key='Semgrep:1',reviewer='Expert',decision='no_match'))
        self.assertEqual(self.unmatched()['total'], 1)

    def test_preview_is_complete_and_read_only_then_associate_and_review(self):
        preview = api.preview_comparison('CAST:1','Semgrep:1')
        self.assertIsNone(preview['candidate'])
        self.assertIn('pattern: foo(...)',preview['semgrep']['raw_content'])
        self.assertIn('uncertainty_history',preview['semgrep'])
        self.assertEqual(self.unmatched()['total'],2)
        pair=api.ManualCandidateInput(cast_key='CAST:1',semgrep_key='Semgrep:1')
        api.add_manual_candidate(pair)
        first=api.get_match('CAST:1','Semgrep:1')['candidate']
        api.add_manual_candidate(pair)
        self.assertEqual(api.get_match('CAST:1','Semgrep:1')['candidate'],first)
        self.assertEqual(api.get_match('CAST:1','Semgrep:1')['expert_reviews'],[])
        api.add_review(api.ReviewInput(**pair.model_dump(),reviewer='Expert',decision='partial',code_examples=[{'code':'  foo(x);\n'}]))
        data=api.preview_comparison('CAST:1','Semgrep:1')
        self.assertEqual(data['expert_reviews'][0]['code_examples'][0]['code'],'  foo(x);\n')
        self.assertTrue(data['candidate']['factors']['manual_association'])
        self.assertEqual(data['sourced_evidence'],[])
        self.assertEqual(data['llm_proposals'],[])

    def test_manual_link_survives_recalculation_before_review_and_preserves_origin(self):
        api.add_manual_candidate(api.ManualCandidateInput(cast_key='CAST:1',semgrep_key='Semgrep:1'))
        calculate_matches(self.config,min_score=101)
        self.assertTrue(api.get_match('CAST:1','Semgrep:1')['candidate']['factors']['manual_association'])
        calculate_matches(self.config,min_score=0)
        current=api.get_match('CAST:1','Semgrep:1')
        self.assertTrue(current['candidate']['factors']['manual_association'])
        self.assertEqual(current['candidate']['factors']['method'],'deterministic-v1')
        self.assertEqual(current['expert_reviews'],[])
        # Re-association of an automatically ranked pair preserves its computed score.
        score=current['candidate']['score']
        api.add_manual_candidate(api.ManualCandidateInput(cast_key='CAST:1',semgrep_key='Semgrep:1'))
        self.assertEqual(api.get_match('CAST:1','Semgrep:1')['candidate']['score'],score)

    def test_wrong_sources_removed_and_unknown_rules_are_rejected(self):
        for cast,semgrep,status in [('Semgrep:1','CAST:1',422),('CAST:3','Semgrep:1',409),('CAST:1','Semgrep:missing',422)]:
            with self.subTest(cast=cast,semgrep=semgrep),self.assertRaises(HTTPException) as error:
                api.add_manual_candidate(api.ManualCandidateInput(cast_key=cast,semgrep_key=semgrep))
            self.assertEqual(error.exception.status_code,status)
        with self.assertRaises(HTTPException): api.preview_comparison('Semgrep:1','CAST:1')
        self.assertEqual(self.unmatched()['total'],2)

    def test_http_expert_contract_validation_and_history(self):
        async def workflow():
            code,data=await http_request('GET','/api/expert/semgrep-unmatched',query={'page':0})
            self.assertEqual(code,422)
            pair={'cast_key':'CAST:1','semgrep_key':'Semgrep:1'}
            code,data=await http_request('GET','/api/expert/comparison',query=pair)
            self.assertEqual(code,200); self.assertIsNone(data['candidate'])
            code,data=await http_request('POST','/api/expert/reviews',body={**pair,'reviewer':'Expert','decision':'partial'})
            self.assertEqual(code,404)
            code,data=await http_request('POST','/api/expert/associations',body=pair)
            self.assertEqual(code,200)
            code,data=await http_request('POST','/api/expert/reviews',body={**pair,'reviewer':'Expert','decision':'invalid'})
            self.assertEqual(code,422)
            for decision in ('partial','equivalent'):
                code,data=await http_request('POST','/api/expert/reviews',body={**pair,'reviewer':'Expert','decision':decision,'code_examples':[{'kind':'safe','code':'foo("constant");'}]})
                self.assertEqual(code,201)
            code,data=await http_request('GET','/api/expert/reviews',query={**pair,'reviewer':'Expert','page_size':1})
            self.assertEqual(code,200); self.assertEqual(data['total'],2)
            self.assertEqual(data['items'][0]['decision'],'equivalent')
            self.assertEqual(data['items'][0]['code_examples'][0]['kind'],'safe')
        asyncio.run(workflow())


if __name__ == '__main__': unittest.main()
