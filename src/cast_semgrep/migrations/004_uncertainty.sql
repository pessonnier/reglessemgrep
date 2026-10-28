ALTER TABLE rules ADD COLUMN definition_hash TEXT;
ALTER TABLE rules ADD COLUMN source_confidence TEXT;

CREATE TABLE uncertainty_assessments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule_key TEXT NOT NULL REFERENCES rules(rule_key),
  source_version TEXT NOT NULL,
  definition_hash TEXT NOT NULL,
  reviewer TEXT NOT NULL CHECK(length(trim(reviewer)) > 0),
  uncertainty_level TEXT NOT NULL CHECK(uncertainty_level IN ('unknown','low','medium','high')),
  false_positive_risk TEXT NOT NULL CHECK(false_positive_risk IN ('unknown','low','medium','high')),
  false_negative_risk TEXT NOT NULL CHECK(false_negative_risk IN ('unknown','low','medium','high')),
  scope TEXT NOT NULL CHECK(length(trim(scope)) > 0),
  rationale TEXT NOT NULL CHECK(length(trim(rationale)) > 0),
  evidence TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX uncertainty_rule_date ON uncertainty_assessments(rule_key, id DESC);

-- A stale opinion remains in history, but does not describe the current rule.
CREATE VIEW rule_uncertainty AS
WITH latest AS (
  SELECT r.rule_key,r.source_version,r.definition_hash,r.source_confidence,
    a.id AS assessment_id,a.source_version AS assessed_version,
    a.definition_hash AS assessed_hash,a.uncertainty_level,a.false_positive_risk,
    a.false_negative_risk,a.scope,a.rationale,a.evidence,a.reviewer,a.created_at
  FROM rules r LEFT JOIN uncertainty_assessments a ON a.id=(
    SELECT MAX(id) FROM uncertainty_assessments WHERE rule_key=r.rule_key
  ) WHERE r.source='Semgrep'
), checked AS (
  SELECT *,CASE
    WHEN assessment_id IS NULL THEN 'not_evaluated'
    WHEN definition_hash IS NULL OR definition_hash<>assessed_hash
      OR source_version<>assessed_version THEN 'stale'
    ELSE 'expert_assessed' END AS status
  FROM latest
)
SELECT rule_key,status,assessment_id,source_confidence,
  CASE WHEN status='expert_assessed' THEN uncertainty_level ELSE 'high' END AS uncertainty_level,
  CASE WHEN status='expert_assessed' THEN false_positive_risk ELSE 'unknown' END AS false_positive_risk,
  CASE WHEN status='expert_assessed' THEN false_negative_risk ELSE 'unknown' END AS false_negative_risk,
  CASE WHEN status='expert_assessed' THEN 'expert_opinion' ELSE 'unvalidated_default' END AS origin,
  CASE WHEN status='expert_assessed' THEN scope ELSE NULL END AS scope,
  CASE WHEN status='expert_assessed' THEN rationale
    WHEN status='stale' THEN 'La version ou la définition a changé. Une nouvelle évaluation est nécessaire.'
    ELSE 'Aucune évaluation enregistrée. Incertitude élevée par défaut ; risques de faux positifs et de non-détection non évalués.' END AS rationale,
  CASE WHEN status='expert_assessed' THEN evidence ELSE NULL END AS evidence,
  CASE WHEN status='expert_assessed' THEN reviewer ELSE NULL END AS reviewer,
  CASE WHEN status='expert_assessed' THEN created_at ELSE NULL END AS created_at
FROM checked;
