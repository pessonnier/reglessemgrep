ALTER TABLE expert_reviews ADD COLUMN code_examples_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE uncertainty_assessments ADD COLUMN code_examples_json TEXT NOT NULL DEFAULT '[]';
