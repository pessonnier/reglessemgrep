"""Multi-model vectors retain provenance, reject stale text and survive catalogue updates."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from cast_semgrep import api
from cast_semgrep.db import connect, initialize, create_snapshot, upsert_rules, MIGRATIONS
from cast_semgrep.semantic import text_hash, sync_documents
from test_core import rule, settings
from test_manual_associations import http_request


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.config=settings(Path(self.temp.name))
        self.previous=api.settings
        api.settings=self.config
        with connect(self.config.db_path) as conn:
            initialize(conn)
            self.snapshot=create_snapshot(conn,source='CAST',revision='v1',archive_path=Path(self.temp.name))
            self.rule=rule('CAST:1','CAST','1','  SQL title\n','CWE-89')
            upsert_rules(conn,[self.rule],source='CAST',snapshot_id=self.snapshot)
        self.hash=text_hash(self.rule['title'],self.rule['description'])

    def tearDown(self):
        api.settings=self.previous
        self.temp.cleanup()

    def request(self,method,path,body=None,query=None):
        return asyncio.run(http_request(method,'/api/semantic'+path,body,query))

    def model(self,key='model-a',dimensions=3):
        data={'model_key':key,'provider':'local','model_name':key,'model_revision':'v1','dimensions':dimensions}
        code,result=self.request('POST','/models',data)
        self.assertEqual(code,200)
        return data,result

    def put(self,**updates):
        return self.request('PUT','/embeddings',{'rule_key':'CAST:1','model_key':'model-a','content_hash':self.hash,'title_vector':[1,2,3],**updates})

    def coverage(self):
        code,data=self.request('GET','/documents',query={'model_key':'model-a'})
        self.assertEqual(code,200)
        return data['items'][0]['status']

    def test_multi_model_dimensions_independent_vectors_and_idempotence(self):
        data,model=self.model()
        self.model('model-b',2)
        self.assertEqual(self.request('POST','/models',data),(200,model))
        self.assertEqual(self.request('POST','/models',{**data,'dimensions':4})[0],409)
        self.assertEqual(self.request('POST','/models',{**data,'model_key':'alias'})[0],409)
        first=self.put()
        self.assertEqual(first[0],200)
        self.assertEqual(first,self.put())
        self.assertEqual(self.put(model_key='model-b',title_vector=[9,8])[0],200)
        code,all_vectors=self.request('GET','/embeddings',query={'rule_key':'CAST:1'})
        self.assertEqual(code,200);self.assertEqual(all_vectors['total'],2)
        by_model={x['model_key']:x['title_vector'] for x in all_vectors['items']}
        self.assertEqual(by_model,{'model-a':[1,2,3],'model-b':[9,8]})
        self.assertEqual(self.put(title_vector=[3,2,1])[0],409)
        self.assertEqual(self.request('POST','/models',{**data,'model_revision':'v2','model_key':'model-a-v2'})[0],200)

    def test_partial_complete_stale_history_and_removed(self):
        self.model();self.assertEqual(self.coverage(),'pending')
        self.put();self.assertEqual(self.coverage(),'partial')
        self.assertEqual(self.put(title_vector=None,description_vector=[4,5,6])[0],200)
        self.assertEqual(self.coverage(),'complete')
        with connect(self.config.db_path) as conn:
            item={**self.rule,'title':'Changed title'}
            upsert_rules(conn,[item],source='CAST',snapshot_id=self.snapshot)
        self.assertEqual(self.coverage(),'stale')
        self.assertEqual(self.put()[0],409)
        code,data=self.request('GET','/embeddings',query={'rule_key':'CAST:1'})
        self.assertEqual(data['total'],0)
        code,data=self.request('GET','/embeddings',query={'rule_key':'CAST:1','history':'true'})
        self.assertEqual(data['total'],1);self.assertFalse(data['items'][0]['is_current'])
        self.hash=text_hash(item['title'],item['description'])
        self.put(description_vector=[4,5,6]);self.assertEqual(self.coverage(),'complete')
        with connect(self.config.db_path) as conn:
            upsert_rules(conn,[],source='CAST',snapshot_id=self.snapshot)
        self.assertEqual(self.put()[0],409)
        self.assertEqual(self.request('GET','/documents')[1]['total'],0)
        self.assertEqual(self.request('GET','/embeddings',query={'rule_key':'CAST:1','history':'true'})[1]['total'],2)

    def test_metadata_only_changes_reuse_vectors_and_text_is_exact(self):
        self.model();self.put(description_vector=[4,5,6])
        code,docs=self.request('GET','/documents')
        self.assertEqual(docs['items'][0]['title'],'  SQL title\n')
        self.assertEqual(docs['items'][0]['content_hash'],self.hash)
        with connect(self.config.db_path) as conn:
            upsert_rules(conn,[{**self.rule,'source_version':'v2','severity':'ERROR'}],source='CAST',snapshot_id=self.snapshot)
            self.assertEqual(sync_documents(conn),0)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_documents').fetchone()[0],1)
        self.assertEqual(self.coverage(),'complete')

    def test_bad_vectors_filters_and_unknown_keys_are_rejected(self):
        self.model()
        for vector in ([0,0,0],[1,2],[],[True,2,3],['1',2,3],[float('nan'),1,2],[float('inf'),1,2],[1]*16385):
            with self.subTest(vector_size=len(vector)):
                self.assertEqual(self.put(title_vector=vector)[0],422)
        self.assertEqual(self.put(title_vector=None)[0],422)
        self.assertEqual(self.put(model_key='unknown')[0],404)
        self.assertEqual(self.put(rule_key='CAST:missing')[0],404)
        self.assertEqual(self.request('GET','/documents',query={'status':'pending'})[0],422)
        self.assertEqual(self.request('GET','/documents',query={'model_key':'unknown'})[0],404)
        self.assertEqual(self.request('GET','/documents',query={'page':0})[0],422)
        self.assertEqual(self.request('GET','/status')[1]['embedding_records'],0)

    def test_missing_fields_not_applicable_and_model_coverage_filters(self):
        self.model()
        with connect(self.config.db_path) as conn:
            item={**self.rule,'description':' \n\t'}
            upsert_rules(conn,[item],source='CAST',snapshot_id=self.snapshot)
        self.hash=text_hash(item['title'],item['description'])
        self.assertEqual(self.put(description_vector=[4,5,6])[0],422)
        self.assertEqual(self.put()[0],200);self.assertEqual(self.coverage(),'complete')
        self.assertEqual(self.request('GET','/documents',query={'model_key':'model-a','status':'pending'})[1]['total'],0)
        with connect(self.config.db_path) as conn:
            upsert_rules(conn,[{**item,'title':None}],source='CAST',snapshot_id=self.snapshot)
        self.assertEqual(self.coverage(),'not_applicable')

    def test_real_v5_migration_backfills_and_keeps_opinions(self):
        path=Path(self.temp.name)/'old.sqlite3'
        with connect(path) as conn:
            for name in ['001_initial.sql','002_categories.sql','003_owasp_raw.sql','004_uncertainty.sql','005_expert_code.sql']:
                conn.executescript((MIGRATIONS/name).read_text())
            conn.execute('PRAGMA user_version=5')
            for source in ['CAST','Semgrep']:
                snapshot=create_snapshot(conn,source=source,revision='test',archive_path=Path(self.temp.name))
                upsert_rules(conn,[rule(source+':1',source,'1','Existing title','CWE-89')],source=source,snapshot_id=snapshot)
            conn.execute("INSERT INTO match_candidates VALUES('CAST:1','Semgrep:1',50,'{}','indeterminate','test')")
            conn.execute("INSERT INTO expert_reviews(cast_key,semgrep_key,reviewer,decision,created_at) VALUES('CAST:1','Semgrep:1','Expert','partial','test')")
            initialize(conn)
            self.assertEqual(conn.execute('PRAGMA user_version').fetchone()[0],6)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_current_documents').fetchone()[0],2)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM expert_reviews').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0],0)
            initialize(conn)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM semantic_documents').fetchone()[0],2)


if __name__=='__main__': unittest.main()
