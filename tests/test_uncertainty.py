"""Regression tests for honest defaults, assessment history, and invalidation."""

import asyncio
import csv
import io
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from cast_semgrep import api
from cast_semgrep.db import MIGRATIONS, connect, create_snapshot, initialize, upsert_rules
from cast_semgrep.matching import calculate_matches
from cast_semgrep.semgrep import normalize_semgrep
from test_core import rule, settings


class UncertaintyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = settings(self.root)
        self.previous_settings = api.settings
        api.settings = self.config
        self.definition = {"id": "sql", "message": "SQL injection", "severity": "ERROR",
                           "languages": ["java"], "pattern": "execute($X)",
                           "metadata": {"confidence": "HIGH", "cwe": "CWE-89"}}
        self.semgrep = normalize_semgrep(self.definition, relative_path="sql.yaml", checkout=self.root,
                                         revision="revision-1", duplicate_id=False)
        with connect(self.config.db_path) as conn:
            initialize(conn)
            self.snapshot = create_snapshot(conn, source="Semgrep", revision="revision-1", archive_path=self.root)
            upsert_rules(conn, [self.semgrep], source="Semgrep", snapshot_id=self.snapshot)
            cast_snapshot = create_snapshot(conn, source="CAST", revision="1", archive_path=self.root)
            upsert_rules(conn, [rule("CAST:1", "CAST", "1", "SQL injection", "CWE-89")], source="CAST", snapshot_id=cast_snapshot)

    def tearDown(self):
        api.settings = self.previous_settings
        self.temp.cleanup()

    def payload(self, **overrides):
        return api.UncertaintyInput(**{
            "rule_key": "Semgrep:sql", "source_version": "revision-1",
            "definition_hash": self.semgrep["definition_hash"], "reviewer": "Expert",
            "uncertainty_level": "medium", "false_positive_risk": "high", "false_negative_risk": "unknown",
            "scope": "Java, appels directs ; propagation non vérifiée",
            "rationale": "Le motif peut inclure des constantes sûres. Aucun corpus exécuté.",
            "evidence": "Lecture de la définition archivée, avis qualitatif", **overrides,
        })

    def test_defaults_do_not_turn_publisher_confidence_into_accuracy(self):
        sg = api.get_rule("Semgrep:sql")
        u = sg["uncertainty"]
        self.assertEqual(sg["source_confidence"], "HIGH")
        self.assertEqual((u["uncertainty_level"], u["false_positive_risk"], u["false_negative_risk"]),
                         ("high", "unknown", "unknown"))
        self.assertEqual(u["status"], "not_evaluated")
        self.assertEqual(u["origin"], "unvalidated_default")
        self.assertIsNone(api.get_rule("CAST:1")["uncertainty"])
        self.assertEqual(api.summary()["uncertainty"], [{"status": "not_evaluated", "uncertainty_level": "high", "count": 1}])

    def test_history_is_append_only_and_import_and_matching_preserve_it(self):
        first = api.add_uncertainty_assessment(self.payload())
        second = api.add_uncertainty_assessment(self.payload(uncertainty_level="low", false_negative_risk="high"))
        with connect(self.config.db_path) as conn:
            upsert_rules(conn, [self.semgrep], source="Semgrep", snapshot_id=self.snapshot)
        calculate_matches(self.config)
        current = api.get_rule("Semgrep:sql")
        self.assertEqual([x["id"] for x in current["uncertainty_history"]], [second["id"], first["id"]])
        self.assertEqual(current["uncertainty"]["uncertainty_level"], "low")
        self.assertEqual(current["uncertainty"]["false_negative_risk"], "high")
        self.assertEqual(current["uncertainty"]["status"], "expert_assessed")
        comparison = api.get_match("CAST:1", "Semgrep:sql")
        self.assertEqual(comparison["semgrep"]["uncertainty"], current["uncertainty"])
        self.assertEqual(comparison["expert_reviews"], [])
        self.assertEqual(comparison["llm_proposals"], [])

    def test_changed_definition_same_revision_invalidates_assessment_and_stale_submission(self):
        api.add_uncertainty_assessment(self.payload())
        changed = normalize_semgrep({**self.definition, "pattern": "other($X)"}, relative_path="sql.yaml",
                                    checkout=self.root, revision="revision-1", duplicate_id=False)
        with connect(self.config.db_path) as conn:
            upsert_rules(conn, [changed], source="Semgrep", snapshot_id=self.snapshot)
        current = api.get_rule("Semgrep:sql")
        self.assertEqual(current["uncertainty"]["status"], "stale")
        self.assertEqual(current["uncertainty"]["false_positive_risk"], "unknown")
        self.assertEqual(current["uncertainty"]["uncertainty_level"], "high")
        self.assertEqual(len(current["uncertainty_history"]), 1)
        with self.assertRaises(HTTPException) as raised:
            api.add_uncertainty_assessment(self.payload())
        self.assertEqual(raised.exception.status_code, 409)
        api.add_uncertainty_assessment(self.payload(definition_hash=changed["definition_hash"]))
        self.assertEqual(api.get_rule("Semgrep:sql")["uncertainty"]["status"], "expert_assessed")

    def test_changed_revision_and_removed_rule_require_fresh_review(self):
        api.add_uncertainty_assessment(self.payload())
        with connect(self.config.db_path) as conn:
            conn.execute("UPDATE rules SET source_version='revision-2' WHERE source='Semgrep'")
        self.assertEqual(api.get_rule("Semgrep:sql")["uncertainty"]["status"], "stale")
        with self.assertRaises(HTTPException) as raised:
            api.add_uncertainty_assessment(self.payload())
        self.assertEqual(raised.exception.status_code, 409)
        with connect(self.config.db_path) as conn:
            conn.execute("UPDATE rules SET status='removed',source_version='revision-1' WHERE source='Semgrep'")
        with self.assertRaises(HTTPException) as raised:
            api.add_uncertainty_assessment(self.payload())
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(api.summary()["uncertainty"], [])

    def test_filter_and_csv_agree_with_effective_opinion(self):
        api.add_uncertainty_assessment(self.payload(evidence="=formula test"))
        filtered = api.list_rules(false_positive_risk="high", uncertainty_level="medium", assessment_status="expert_assessed", page=1, page_size=30)
        self.assertEqual(filtered["total"], 1)
        self.assertEqual(filtered["items"][0]["uncertainty"]["false_negative_risk"], "unknown")
        self.assertEqual(api.list_rules(source="CAST", uncertainty_level="high", page=1, page_size=30)["total"], 1)
        async def body(response):
            return ''.join([chunk async for chunk in response.body_iterator])
        exported = list(csv.DictReader(io.StringIO(asyncio.run(body(api.export_rules("Semgrep"))))))
        self.assertEqual(exported[0]["false_positive_risk"], "high")
        self.assertEqual(exported[0]["assessment_origin"], "expert_opinion")
        self.assertEqual(exported[0]["evidence"], "'=formula test")
        with connect(self.config.db_path) as conn:
            conn.execute("UPDATE rules SET source_version='revision-2' WHERE source='Semgrep'")
        self.assertEqual(api.list_rules(false_positive_risk="high", page=1, page_size=30)["total"], 0)
        self.assertEqual(api.list_rules(assessment_status="stale", false_negative_risk="unknown", page=1, page_size=30)["total"], 1)

    def test_invalid_opinions_and_wrong_sources_are_rejected(self):
        for changes in ({"reviewer": "   "}, {"scope": "\t"}, {"rationale": "\n"},
                        {"false_positive_risk": "0%"}, {"uncertainty_level": "certain"}, {"definition_hash": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.payload(**changes)
        with self.assertRaises(HTTPException) as raised:
            api.add_uncertainty_assessment(self.payload(rule_key="CAST:1"))
        self.assertEqual(raised.exception.status_code, 422)
        with self.assertRaises(HTTPException) as raised:
            api.add_uncertainty_assessment(self.payload(rule_key="Semgrep:missing"))
        self.assertEqual(raised.exception.status_code, 404)

    def test_hash_is_stable_for_key_order_and_specific_to_each_rule(self):
        reordered = normalize_semgrep(dict(reversed(list(self.definition.items()))), relative_path="sql.yaml",
                                     checkout=self.root, revision="revision-1", duplicate_id=False)
        self.assertEqual(reordered["definition_hash"], self.semgrep["definition_hash"])
        changed = normalize_semgrep({**self.definition, "id": "different"}, relative_path="sql.yaml",
                                   checkout=self.root, revision="revision-1", duplicate_id=False)
        self.assertNotEqual(changed["definition_hash"], self.semgrep["definition_hash"])

    def test_migrates_v3_database_without_losing_rules(self):
        old_db = self.root / "v3.sqlite3"
        with connect(old_db) as conn:
            for name in ("001_initial.sql", "002_categories.sql", "003_owasp_raw.sql"):
                conn.executescript((MIGRATIONS / name).read_text())
            conn.execute("PRAGMA user_version=3")
            conn.execute("INSERT INTO snapshots(id,source,revision,archive_path,collected_at) VALUES(1,'Semgrep','old','/tmp','2026-01-01')")
            conn.execute("INSERT INTO rules(rule_key,source,rule_id,source_url,source_version,raw_path,collected_at,snapshot_id) VALUES('Semgrep:old','Semgrep','old','https://example.invalid','old','/tmp/old','2026-01-01',1)")
            initialize(conn)
            initialize(conn)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 4)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM rules").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT status FROM rule_uncertainty").fetchone()[0], "not_evaluated")


if __name__ == "__main__":
    unittest.main()
