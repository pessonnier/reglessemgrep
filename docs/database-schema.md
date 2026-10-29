# Modèle de la base de données

Diagramme généré à partir du schéma SQLite. PK : clé primaire ; FK : clé étrangère ; UK : unicité sur une colonne. Les clés composites restent groupées dans les relations. Les vues sont indiquées par VIEW et leurs dépendances ne sont pas inférées.

```mermaid
erDiagram
    %% SQLite schema version 5
    %% Generated from metadata only; no records or inferred view dependencies.
    %% table: expert_reviews
    expert_reviews {
        INTEGER id PK "NOT NULL"
        TEXT cast_key FK "NOT NULL"
        TEXT semgrep_key FK "NOT NULL"
        TEXT reviewer "NOT NULL"
        TEXT decision "NOT NULL"
        TEXT comment "NOT NULL"
        TEXT created_at "NOT NULL"
        TEXT code_examples_json "NOT NULL"
    }
    %% table: llm_proposals
    llm_proposals {
        INTEGER id PK "NOT NULL"
        TEXT cast_key FK "NOT NULL"
        TEXT semgrep_key FK "NOT NULL"
        TEXT model "NOT NULL"
        TEXT proposal_json "NOT NULL"
        TEXT created_at "NOT NULL"
    }
    %% table: match_candidates
    match_candidates {
        TEXT cast_key PK, FK "NOT NULL"
        TEXT semgrep_key PK, FK "NOT NULL"
        INTEGER score "NOT NULL"
        TEXT factors_json "NOT NULL"
        TEXT suggested_status "NOT NULL"
        TEXT updated_at "NOT NULL"
    }
    %% table: match_evidence
    match_evidence {
        INTEGER id PK "NOT NULL"
        TEXT cast_key FK "NOT NULL"
        TEXT semgrep_key FK "NOT NULL"
        TEXT dimension "NOT NULL"
        TEXT source_rule_key "NOT NULL"
        TEXT reference_url "NOT NULL"
        TEXT reference_field "NOT NULL"
        TEXT excerpt "NOT NULL"
        TEXT origin "NOT NULL"
    }
    %% view: rule_uncertainty
    rule_uncertainty {
        TEXT rule_key "VIEW - derived column"
        UNKNOWN status "VIEW - derived column"
        INTEGER assessment_id "VIEW - derived column"
        TEXT source_confidence "VIEW - derived column"
        UNKNOWN uncertainty_level "VIEW - derived column"
        UNKNOWN false_positive_risk "VIEW - derived column"
        UNKNOWN false_negative_risk "VIEW - derived column"
        UNKNOWN origin "VIEW - derived column"
        UNKNOWN scope "VIEW - derived column"
        UNKNOWN rationale "VIEW - derived column"
        UNKNOWN evidence "VIEW - derived column"
        UNKNOWN reviewer "VIEW - derived column"
        UNKNOWN created_at "VIEW - derived column"
    }
    %% table: rules
    rules {
        TEXT rule_key PK "NULL allowed"
        TEXT source "NOT NULL"
        TEXT rule_id "NOT NULL"
        TEXT title "NULL allowed"
        TEXT description "NULL allowed"
        TEXT rationale "NULL allowed"
        TEXT remediation "NULL allowed"
        TEXT severity "NULL allowed"
        TEXT category "NULL allowed"
        TEXT classification_origin "NOT NULL"
        TEXT languages_json "NOT NULL"
        TEXT frameworks_json "NOT NULL"
        TEXT technologies_json "NOT NULL"
        TEXT cwe_json "NOT NULL"
        TEXT owasp_json "NOT NULL"
        TEXT standards_json "NOT NULL"
        TEXT detection_method "NULL allowed"
        TEXT source_url "NOT NULL"
        TEXT source_version "NOT NULL"
        TEXT raw_path "NOT NULL"
        TEXT status "NOT NULL"
        TEXT collected_at "NOT NULL"
        INTEGER snapshot_id FK "NOT NULL"
        TEXT categories_json "NOT NULL"
        TEXT owasp_raw_json "NOT NULL"
        TEXT definition_hash "NULL allowed"
        TEXT source_confidence "NULL allowed"
    }
    %% table: snapshots
    snapshots {
        INTEGER id PK "NOT NULL"
        TEXT source "NOT NULL"
        TEXT revision "NOT NULL"
        TEXT archive_path "NOT NULL"
        TEXT collected_at "NOT NULL"
        TEXT auth_mode "NOT NULL"
        TEXT status "NOT NULL"
        TEXT stats_json "NOT NULL"
    }
    %% table: uncertainty_assessments
    uncertainty_assessments {
        INTEGER id PK "NOT NULL"
        TEXT rule_key FK "NOT NULL"
        TEXT source_version "NOT NULL"
        TEXT definition_hash "NOT NULL"
        TEXT reviewer "NOT NULL"
        TEXT uncertainty_level "NOT NULL"
        TEXT false_positive_risk "NOT NULL"
        TEXT false_negative_risk "NOT NULL"
        TEXT scope "NOT NULL"
        TEXT rationale "NOT NULL"
        TEXT evidence "NOT NULL"
        TEXT created_at "NOT NULL"
        TEXT code_examples_json "NOT NULL"
    }
    match_candidates ||..o{ expert_reviews : "cast_key, semgrep_key → cast_key, semgrep_key"
    match_candidates ||..o{ llm_proposals : "cast_key, semgrep_key → cast_key, semgrep_key"
    match_candidates ||..o{ match_evidence : "cast_key, semgrep_key → cast_key, semgrep_key"
    rules ||--o{ match_candidates : "cast_key → rule_key"
    rules ||--o{ match_candidates : "semgrep_key → rule_key"
    rules ||..o{ uncertainty_assessments : "rule_key → rule_key"
    snapshots ||..o{ rules : "snapshot_id → id"
```
