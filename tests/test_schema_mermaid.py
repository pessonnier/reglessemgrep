"""Schema exports use metadata, preserve composite relations and never migrate live DBs."""
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cast_semgrep.schema_mermaid import generate_schema, schema_mermaid


class SchemaMermaidTests(unittest.TestCase):
    def test_migration_model_contains_all_tables_view_and_composite_foreign_keys(self):
        diagram = generate_schema()
        self.assertEqual(diagram, generate_schema())
        self.assertIn('erDiagram\n', diagram)
        self.assertIn('TEXT cast_key PK, FK', diagram)
        self.assertIn('TEXT code_examples_json', diagram)
        self.assertIn('VIEW - derived column', diagram)
        self.assertIn('match_candidates ||..o{ expert_reviews : "cast_key, semgrep_key → cast_key, semgrep_key"', diagram)
        self.assertEqual(diagram.count('..o{ expert_reviews :'), 1)
        self.assertIn('rules ||--o{ match_candidates : "cast_key → rule_key"', diagram)
        self.assertIn('rules ||--o{ match_candidates : "semgrep_key → rule_key"', diagram)
        self.assertNotIn('rule_uncertainty {', generate_schema(include_views=False))
        self.assertIn('```mermaid\nerDiagram', generate_schema(markdown=True))

    def test_existing_database_is_read_only_and_records_are_never_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.sqlite3'
            with sqlite3.connect(path) as conn:
                conn.execute('CREATE TABLE example(id INTEGER PRIMARY KEY, secret TEXT)')
                conn.execute("INSERT INTO example(secret) VALUES('VALUE_MUST_NOT_BE_EXPORTED')")
                conn.execute('PRAGMA user_version=2')
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            output=generate_schema(database=path)
            self.assertIn('schema version 2', output)
            self.assertIn('TEXT secret', output)
            self.assertNotIn('VALUE_MUST_NOT_BE_EXPORTED',output)
            self.assertNotIn('snapshots',output)
            self.assertEqual(before,hashlib.sha256(path.read_bytes()).hexdigest())
            missing=Path(tmp)/'missing.sqlite3'
            with self.assertRaises(sqlite3.OperationalError): generate_schema(database=missing)
            self.assertFalse(missing.exists())

    def test_optional_unique_relations_and_implicit_parent_pk(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('''CREATE TABLE parent(id TEXT PRIMARY KEY);
                CREATE TABLE child(id INTEGER PRIMARY KEY, parent_id TEXT UNIQUE REFERENCES parent);
                CREATE TABLE multi(a TEXT NOT NULL, b TEXT NOT NULL, PRIMARY KEY(a,b));
                CREATE TABLE ref(a TEXT NOT NULL, b TEXT NOT NULL, FOREIGN KEY(a,b) REFERENCES multi);
            ''')
            text=schema_mermaid(conn)
            self.assertIn('TEXT parent_id FK, UK',text)
            self.assertIn('parent |o..o| child : "parent_id → id"',text)
            self.assertIn('multi ||..o{ ref : "a, b → a, b"',text)

    def test_unusual_names_are_safe_and_do_not_collide(self):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript('''CREATE TABLE "a-b"("1st col" "DECIMAL(10,2)");
                CREATE TABLE a_b("odd""name" TEXT);''')
            diagram=schema_mermaid(conn)
            self.assertIn('a_b {',diagram)
            self.assertIn('a_b_2 {',diagram)
            self.assertIn('item_1st_col',diagram)
            self.assertNotIn('odd"name',diagram)
            self.assertIn('DECIMAL_10_2_',diagram)


if __name__ == '__main__': unittest.main()
