"""OWASP joins normalize notation while preserving family, edition and provenance."""
import json
import tempfile
import unittest
from pathlib import Path

from cast_semgrep.cast import normalize_cast
from cast_semgrep.semgrep import normalize_semgrep
from cast_semgrep.normalization import canonical_owasp, extract_owasp
from cast_semgrep.matching import calculate_matches, score_pair
from cast_semgrep.db import connect, initialize, create_snapshot, upsert_rules, decode_rule
from test_core import rule, settings


class OwaspJoinTests(unittest.TestCase):
    def test_format_variants_and_duplicate_labels_have_one_key(self):
        variants=['A03-2021','A03:2021','a3 : 2021','OWASP: A03 – 2021 - Injection',
                  'A03\u00a0—\u00a02021','Ａ０３：２０２１','A03:2021 - Injection']
        for value in variants:
            with self.subTest(value=value): self.assertEqual(extract_owasp(value),['A03:2021'])
        self.assertEqual(canonical_owasp(variants),['A03:2021'])
        self.assertEqual(extract_owasp('A1-2017; A03:2021'),['A01:2017','A03:2021'])

    def test_no_guessing_of_family_edition_or_malformed_ids(self):
        self.assertEqual(canonical_owasp(['API3-2023','A3-2023','M3-2023']),['A03:2023','API03:2023','M03:2023'])
        self.assertNotEqual(extract_owasp('A03-2017'),extract_owasp('A03:2021'))
        for value in ['A03','Injection','A00:2021','A11-2021','A003:2021','XA03:2021','A03:20210','A03:2021x','A03:21']:
            with self.subTest(value=value): self.assertEqual(extract_owasp(value),[])

    def test_imports_use_same_parser_and_keep_original_values(self):
        cast=normalize_cast({'id':1},{'qualityStandards':[{'standard':'OWASP','id':'A3 – 2021'}]},Path('/tmp'),'test')
        semgrep=normalize_semgrep({'id':'s','metadata':{'owasp':['A03 : 2021 - Injection','A03:2021','A3']}},relative_path='s.yaml',checkout=Path('/tmp'),revision='test',duplicate_id=False)
        self.assertEqual(json.loads(cast['owasp_json']),['A03:2021'])
        self.assertEqual(json.loads(semgrep['owasp_json']),['A03:2021'])
        self.assertEqual(json.loads(cast['owasp_raw_json']),['A3 – 2021'])
        self.assertEqual(len(json.loads(semgrep['owasp_raw_json'])),3)

    def test_scoring_normalizes_at_read_time_and_does_not_double_count(self):
        cast={'rule_key':'CAST:1','source':'CAST','source_url':'https://example.invalid/c',
              'title':'SQL injection','description':'unsafe SQL query','rationale':None,'languages':['JEE'],
              'categories':['security'],'category':'security','cwe':[],
              'owasp':['A03-2021'],'owasp_raw':['A03-2021']}
        semgrep={**cast,'rule_key':'Semgrep:1','source':'Semgrep','languages':['java'],
                 'owasp':['A03:2021 - Injection','A3:2021'],'owasp_raw':['A03:2021 - Injection']}
        score,factors,evidence=score_pair(cast,semgrep)
        absent={**semgrep,'owasp':[],'owasp_raw':[]}
        self.assertEqual(score-score_pair(cast,absent)[0],10)
        self.assertEqual(factors['shared_owasp'],['A03:2021'])
        self.assertEqual(factors['owasp_reference_points'],10)
        self.assertEqual(len([e for e in evidence if e['dimension']=='OWASP']),2)
        self.assertIn('A03-2021',[e['excerpt'] for e in evidence])
        self.assertIn('A03:2021 - Injection',[e['excerpt'] for e in evidence])
        with_cwe=score_pair({**cast,'cwe':['CWE-89']},{**semgrep,'cwe':['CWE-89']})[1]
        self.assertEqual(with_cwe['defect_references'],35)
        self.assertEqual(score_pair(cast,{**semgrep,'owasp':['A03:2017'],'owasp_raw':[]})[1]['owasp_reference_points'],0)

    def test_legacy_rows_recovered_before_indexing_and_delta_is_repeatable(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=settings(Path(tmp))
            with connect(config.db_path) as conn:
                initialize(conn)
                for source,reference in [('CAST','A03 – 2021'),('Semgrep','A03:2021 - Injection')]:
                    snapshot=create_snapshot(conn,source=source,revision='test',archive_path=Path(tmp))
                    item=rule(source+':1',source,'1','SQL injection','CWE-89')
                    item.update(cwe_json='[]',owasp_json='[]',owasp_raw_json=json.dumps([reference]))
                    upsert_rules(conn,[item],source=source,snapshot_id=snapshot)
            report=calculate_matches(config,min_score=70)
            self.assertEqual(report['new_pairs'],1)
            self.assertEqual(report['owasp_normalized_rules'],2)
            self.assertEqual(report['newly_matched_rules'],{'CAST':1,'Semgrep':1})
            with connect(config.db_path) as conn:
                cast=decode_rule(conn.execute("SELECT * FROM rules WHERE source='CAST'").fetchone())
                self.assertEqual(cast['owasp'],['A03:2021'])
                self.assertEqual(cast['owasp_raw'],['A03 – 2021'])
            repeat=calculate_matches(config,min_score=70)
            self.assertEqual(repeat['new_pairs'],0)
            self.assertEqual(repeat['removed_pairs'],0)
            self.assertEqual(repeat['changed_scores'],0)
            self.assertEqual(repeat['owasp_normalized_rules'],0)


if __name__ == '__main__': unittest.main()
