"""Focused regression tests for imports, provenance, and expert decisions."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path

from cast_semgrep.cast import import_cast
from cast_semgrep.config import Settings
from cast_semgrep.db import connect, create_snapshot, initialize, upsert_rules
from cast_semgrep.matching import calculate_matches, score_pair
from cast_semgrep.semgrep import import_semgrep
from cast_semgrep import api
from cast_semgrep.normalization import normalize_owasp


def settings(root: Path) -> Settings:
    return Settings(root, root / "data" / "raw", root / "data" / "test.sqlite3", "", "", 0)


def rule(key: str, source: str, rule_id: str, title: str, cwe: str) -> dict:
    return {
        "rule_key": key, "source": source, "rule_id": rule_id, "title": title,
        "description": "Detect unsafe SQL query construction", "rationale": None, "remediation": None,
        "severity": "WARNING", "category": "security", "classification_origin": source,
        "categories_json": '["security"]',
        "languages_json": '["java"]', "frameworks_json": '[]', "technologies_json": '["java"]',
        "cwe_json": json.dumps([cwe]), "owasp_json": '[]', "owasp_raw_json": '[]', "standards_json": '[]',
        "detection_method": None, "source_url": f"https://example.invalid/{source}/{rule_id}",
        "source_version": "test", "raw_path": "/tmp/nonexistent",
    }


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = settings(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_semgrep_counts_rule_objects_and_ignores_test_fixtures(self):
        checkout = self.config.data_dir / "semgrep" / "repo"
        checkout.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(checkout)], check=True)
        (checkout / "two.yaml").write_text("""rules:
  - id: first
    message: first issue
    severity: WARNING
    languages: [java]
    pattern: foo(...)
  - id: second
    message: second issue
    severity: ERROR
    languages: [python]
    pattern: bar(...)
""", encoding="utf-8")
        (checkout / "sample.test.yaml").write_text("rules:\n  - apiGroups: ['*']\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(checkout), "add", "."], check=True)
        subprocess.run(["git", "-C", str(checkout), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"], check=True)
        report = import_semgrep(self.config)
        self.assertEqual(report["rule_objects"], 2)
        self.assertEqual(report["imported"], 2)
        self.assertEqual(report["ignored_test_files"], 1)
        self.assertEqual(report["errors"], 0)

    def test_snapshot_reimport_reuses_same_revision(self):
        with connect(self.config.db_path) as conn:
            initialize(conn)
            first = create_snapshot(conn, source="Semgrep", revision="abc123", archive_path=self.root, stats={"imported": 1})
            second = create_snapshot(conn, source="Semgrep", revision="abc123", archive_path=self.root, stats={"imported": 2})
            self.assertEqual(first, second)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1)
            self.assertEqual(json.loads(conn.execute("SELECT stats_json FROM snapshots").fetchone()[0])["imported"], 2)

    def test_owasp_versions_normalize_without_losing_family(self):
        self.assertEqual(normalize_owasp("A3-2021"), "A03:2021")
        self.assertEqual(normalize_owasp("API10-2023"), "API10:2023")
        cast = {"rule_key":"CAST:1","source":"CAST","source_url":"https://example.invalid/cast","title":"SQL injection",
                "description":"Unsafe SQL","rationale":None,"languages":["JEE"],"categories":["Security"],"category":"Security",
                "cwe":[],"owasp":["A03:2021"],"owasp_raw":["A03-2021"]}
        semgrep = {"rule_key":"Semgrep:1","source":"Semgrep","source_url":"https://example.invalid/semgrep","title":"sql-injection",
                   "description":"Unsafe SQL","rationale":None,"languages":["java"],"categories":["security"],"category":"security",
                   "cwe":[],"owasp":["A03:2021"],"owasp_raw":["A03:2021 - Injection"]}
        _, _, evidence = score_pair(cast, semgrep)
        self.assertIn("A03-2021", [item["excerpt"] for item in evidence])
        self.assertIn("A03:2021 - Injection", [item["excerpt"] for item in evidence])

    def test_partial_cast_import_preserves_prior_rule(self):
        full = self.config.data_dir / "cast" / "20260101T000000Z-public"
        partial = self.config.data_dir / "cast" / "20260102T000000Z-public"
        for folder, ids in ((full, [1, 2]), (partial, [1, 2])):
            (folder / "rules").mkdir(parents=True)
            (folder / "index.json").write_text(json.dumps({"qualityRules": [{"id": i, "name": f"Rule {i}"} for i in ids]}))
            (folder / "manifest.json").write_text(json.dumps({"auth_mode": "public"}))
        for i in (1, 2):
            (full / "rules" / f"{i}.json").write_text(json.dumps({"id": i, "name": f"Rule {i}"}))
        (partial / "rules" / "1.json").write_text(json.dumps({"id": 1, "name": "Rule 1"}))
        self.assertEqual(import_cast(self.config, full)["imported"], 2)
        self.assertEqual(import_cast(self.config, partial)["missing"], 1)
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute("SELECT status FROM rules WHERE rule_key='CAST:2'").fetchone()[0], "present")

    def test_matching_keeps_expert_review_and_source_evidence(self):
        with connect(self.config.db_path) as conn:
            initialize(conn)
            cast_snapshot = create_snapshot(conn, source="CAST", revision="test", archive_path=self.root)
            semgrep_snapshot = create_snapshot(conn, source="Semgrep", revision="test", archive_path=self.root)
            upsert_rules(conn, [rule("CAST:1", "CAST", "1", "Avoid SQL injection", "CWE-89")], source="CAST", snapshot_id=cast_snapshot)
            upsert_rules(conn, [rule("Semgrep:sql", "Semgrep", "sql", "SQL injection detected", "CWE-89")], source="Semgrep", snapshot_id=semgrep_snapshot)
        result = calculate_matches(self.config)
        self.assertEqual(result["candidates"], 1)
        with connect(self.config.db_path) as conn:
            rows = conn.execute("SELECT origin,reference_url FROM match_evidence ORDER BY origin").fetchall()
            self.assertEqual({row[0] for row in rows}, {"CAST", "Semgrep"})
            self.assertTrue(all(row[1].startswith("https://") for row in rows))
            conn.execute("INSERT INTO expert_reviews(cast_key,semgrep_key,reviewer,decision,comment,created_at) VALUES(?,?,?,?,?,?)",
                         ("CAST:1", "Semgrep:sql", "Expert", "partial", "Different scope", "2026-01-01"))
        calculate_matches(self.config)
        with connect(self.config.db_path) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM expert_reviews").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT decision FROM expert_reviews").fetchone()[0], "partial")

    def test_api_keeps_sources_llm_and_expert_opinion_separate(self):
        with connect(self.config.db_path) as conn:
            initialize(conn)
            cast_snapshot = create_snapshot(conn, source="CAST", revision="test", archive_path=self.root)
            semgrep_snapshot = create_snapshot(conn, source="Semgrep", revision="test", archive_path=self.root)
            upsert_rules(conn, [rule("CAST:1", "CAST", "1", "Avoid SQL injection", "CWE-89")], source="CAST", snapshot_id=cast_snapshot)
            upsert_rules(conn, [rule("Semgrep:sql", "Semgrep", "sql", "SQL injection detected", "CWE-89")], source="Semgrep", snapshot_id=semgrep_snapshot)
        calculate_matches(self.config)
        previous = api.settings
        api.settings = self.config
        try:
            api.add_review(api.ReviewInput(cast_key="CAST:1", semgrep_key="Semgrep:sql", reviewer="Expert", decision="partial", comment="Scope differs"))
            comparison = api.get_match("CAST:1", "Semgrep:sql")
            self.assertTrue(comparison["sourced_evidence"])
            self.assertEqual(comparison["llm_proposals"], [])
            self.assertEqual(comparison["expert_reviews"][0]["decision"], "partial")
            self.assertEqual(api.list_rules(source="CAST", page=1, page_size=30)["total"], 1)
            self.assertEqual(api.summary()["unmatched"], {"CAST": 0, "Semgrep": 0})
        finally:
            api.settings = previous


if __name__ == "__main__":
    unittest.main()
