-- Multiple embedding models share the same versioned rule documents.
CREATE TABLE semantic_models (
  model_key TEXT PRIMARY KEY NOT NULL,
  provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  model_revision TEXT NOT NULL,
  dimensions INTEGER NOT NULL CHECK(dimensions BETWEEN 1 AND 16384),
  preprocessing TEXT NOT NULL CHECK(preprocessing='raw-text-v1'),
  created_at TEXT NOT NULL,
  UNIQUE(provider, model_name, model_revision, dimensions, preprocessing)
);

CREATE TABLE semantic_documents (
  rule_key TEXT NOT NULL REFERENCES rules(rule_key),
  content_hash TEXT NOT NULL CHECK(length(content_hash)=64),
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  has_title INTEGER NOT NULL CHECK(has_title IN (0,1)),
  has_description INTEGER NOT NULL CHECK(has_description IN (0,1)),
  created_at TEXT NOT NULL,
  PRIMARY KEY(rule_key, content_hash)
);

CREATE TABLE semantic_embeddings (
  rule_key TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  model_key TEXT NOT NULL REFERENCES semantic_models(model_key),
  title_vector_json TEXT CHECK(title_vector_json IS NULL OR
    (json_valid(title_vector_json) AND json_type(title_vector_json)='array' AND json_array_length(title_vector_json)>0)),
  description_vector_json TEXT CHECK(description_vector_json IS NULL OR
    (json_valid(description_vector_json) AND json_type(description_vector_json)='array' AND json_array_length(description_vector_json)>0)),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(rule_key, content_hash, model_key),
  FOREIGN KEY(rule_key, content_hash) REFERENCES semantic_documents(rule_key, content_hash),
  CHECK(title_vector_json IS NOT NULL OR description_vector_json IS NOT NULL)
);
CREATE INDEX semantic_embeddings_model ON semantic_embeddings(model_key, rule_key);

CREATE VIEW semantic_current_documents AS
SELECT d.*,r.source,r.rule_id,r.source_version
FROM semantic_documents d JOIN rules r ON r.rule_key=d.rule_key
WHERE r.status='present' AND d.title=COALESCE(r.title,'') AND d.description=COALESCE(r.description,'');

-- Missing/obsolete vectors are visible per model; never count old vectors as current.
CREATE VIEW semantic_coverage AS
SELECT d.rule_key,d.content_hash,m.model_key,
  CASE WHEN d.has_title=0 AND d.has_description=0 THEN 'not_applicable'
    WHEN (d.has_title=0 OR e.title_vector_json IS NOT NULL)
     AND (d.has_description=0 OR e.description_vector_json IS NOT NULL) THEN 'complete'
    WHEN e.title_vector_json IS NOT NULL OR e.description_vector_json IS NOT NULL THEN 'partial'
    WHEN EXISTS(SELECT 1 FROM semantic_embeddings old WHERE old.rule_key=d.rule_key AND old.model_key=m.model_key) THEN 'stale'
    ELSE 'pending' END AS status
FROM semantic_current_documents d CROSS JOIN semantic_models m
LEFT JOIN semantic_embeddings e ON e.rule_key=d.rule_key AND e.content_hash=d.content_hash AND e.model_key=m.model_key;
