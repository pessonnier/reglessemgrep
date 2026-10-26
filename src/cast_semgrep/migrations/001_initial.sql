PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL CHECK(source IN ('CAST', 'Semgrep')),
  revision TEXT NOT NULL,
  archive_path TEXT NOT NULL,
  collected_at TEXT NOT NULL,
  auth_mode TEXT NOT NULL DEFAULT 'public',
  status TEXT NOT NULL DEFAULT 'complete',
  stats_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS snapshots_source_date ON snapshots(source, id DESC);

CREATE TABLE IF NOT EXISTS rules (
  rule_key TEXT PRIMARY KEY,
  source TEXT NOT NULL CHECK(source IN ('CAST', 'Semgrep')),
  rule_id TEXT NOT NULL,
  title TEXT,
  description TEXT,
  rationale TEXT,
  remediation TEXT,
  severity TEXT,
  category TEXT,
  classification_origin TEXT NOT NULL DEFAULT 'unknown',
  languages_json TEXT NOT NULL DEFAULT '[]',
  frameworks_json TEXT NOT NULL DEFAULT '[]',
  technologies_json TEXT NOT NULL DEFAULT '[]',
  cwe_json TEXT NOT NULL DEFAULT '[]',
  owasp_json TEXT NOT NULL DEFAULT '[]',
  standards_json TEXT NOT NULL DEFAULT '[]',
  detection_method TEXT,
  source_url TEXT NOT NULL,
  source_version TEXT NOT NULL,
  raw_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'present',
  collected_at TEXT NOT NULL,
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(id)
);
CREATE INDEX IF NOT EXISTS rules_source_id ON rules(source, rule_id);
CREATE INDEX IF NOT EXISTS rules_source_category ON rules(source, category);
CREATE INDEX IF NOT EXISTS rules_source_status ON rules(source, status);

CREATE TABLE IF NOT EXISTS match_candidates (
  cast_key TEXT NOT NULL REFERENCES rules(rule_key),
  semgrep_key TEXT NOT NULL REFERENCES rules(rule_key),
  score INTEGER NOT NULL CHECK(score BETWEEN 0 AND 100),
  factors_json TEXT NOT NULL,
  suggested_status TEXT NOT NULL DEFAULT 'indeterminate',
  updated_at TEXT NOT NULL,
  PRIMARY KEY(cast_key, semgrep_key)
);
CREATE INDEX IF NOT EXISTS match_candidates_cast_score ON match_candidates(cast_key, score DESC);
CREATE INDEX IF NOT EXISTS match_candidates_semgrep_score ON match_candidates(semgrep_key, score DESC);

CREATE TABLE IF NOT EXISTS match_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cast_key TEXT NOT NULL,
  semgrep_key TEXT NOT NULL,
  dimension TEXT NOT NULL,
  source_rule_key TEXT NOT NULL,
  reference_url TEXT NOT NULL,
  reference_field TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  origin TEXT NOT NULL CHECK(origin IN ('CAST', 'Semgrep', 'reference')),
  FOREIGN KEY(cast_key, semgrep_key) REFERENCES match_candidates(cast_key, semgrep_key) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS match_evidence_pair ON match_evidence(cast_key, semgrep_key);

CREATE TABLE IF NOT EXISTS llm_proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cast_key TEXT NOT NULL,
  semgrep_key TEXT NOT NULL,
  model TEXT NOT NULL,
  proposal_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(cast_key, semgrep_key) REFERENCES match_candidates(cast_key, semgrep_key)
);

CREATE TABLE IF NOT EXISTS expert_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cast_key TEXT NOT NULL,
  semgrep_key TEXT NOT NULL,
  reviewer TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('equivalent', 'partial', 'complementary', 'related', 'no_match', 'indeterminate', 'not_comparable')),
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(cast_key, semgrep_key) REFERENCES match_candidates(cast_key, semgrep_key)
);
CREATE INDEX IF NOT EXISTS expert_reviews_pair_date ON expert_reviews(cast_key, semgrep_key, id DESC);
