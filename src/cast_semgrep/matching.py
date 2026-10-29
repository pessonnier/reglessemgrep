"""Deterministic candidate ranking. A score is never an equivalence verdict."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .config import Settings
from .db import connect, decode_rule, initialize, utc_now
from .normalization import canonical_owasp, extract_owasp


WORD_RE = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
STOPWORDS = {
    "and", "the", "for", "from", "with", "this", "that", "into", "when", "using", "use", "not", "are",
    "rule", "rules", "avoid", "ensure", "detect", "check", "code", "data", "function", "functions", "possible",
    "des", "les", "une", "pour", "avec", "dans", "sur", "est", "pas", "par", "plus", "qui", "que",
}
LANGUAGE_ALIASES = {
    "jee": "java", "j2ee": "java", "java": "java", "c#": "csharp", "c sharp": "csharp",
    "asp.net": "csharp", "vb.net": "vbnet", "javascript": "javascript", "typescript": "typescript",
    "js": "javascript", "ts": "typescript", "kt": "kotlin",
    "html5": "html", "python": "python", "php": "php", "go": "go", "golang": "go",
    "c/c++": "cpp", "c++": "cpp", "cpp": "cpp", "c": "c", "sql": "sql", "pli": "pli",
    "pl/sql": "plsql", "kotlin": "kotlin", "swift": "swift", "ruby": "ruby", "scala": "scala",
}
CATEGORY_ALIASES = {
    "security": "security", "securite": "security", "performance": "performance",
    "robustness": "reliability", "reliability": "reliability", "correctness": "reliability",
    "architecture": "architecture", "architectural design": "architecture",
    "maintainability": "maintainability", "changeability": "maintainability",
}
GENERIC_DEFECT_TERMS = {"injection", "security", "unsafe", "insecure", "vulnerability", "access", "input"}


def tokens(text: str | None) -> set[str]:
    return {word.lower() for word in WORD_RE.findall(text or "") if word.lower() not in STOPWORDS}


def languages(rule: dict) -> set[str]:
    result = set()
    for value in rule.get("languages", []):
        key = str(value).lower().strip()
        if key in {"all technologies", "no label", "other", "unknown", "generic", "regex"}:
            continue
        if key == "c/c++":
            result.update({"c", "cpp"})
            continue
        if key in LANGUAGE_ALIASES:
            result.add(LANGUAGE_ALIASES[key])
        elif rule.get("source") == "Semgrep":
            result.add(key)
    return result


def categories(rule: dict) -> set[str]:
    values = rule.get("categories") or ([rule["category"]] if rule.get("category") else [])
    return {CATEGORY_ALIASES[value.lower().strip()] for value in values
            if isinstance(value, str) and value.lower().strip() in CATEGORY_ALIASES}


def _evidence(rule: dict, dimension: str, field: str, excerpt: str) -> dict:
    return {
        "dimension": dimension,
        "source_rule_key": rule["rule_key"],
        "reference_url": rule["source_url"],
        "reference_field": field,
        "excerpt": excerpt[:700],
        "origin": rule["source"],
    }


def _original_owasp_reference(rule: dict, normalized: str) -> str:
    for value in rule.get("owasp_raw", []):
        if normalized in extract_owasp(str(value)):
            return str(value)
    return f"Identifiant normalisé : {normalized}"


def owasp_keys(rule: dict) -> list[str]:
    # Also read preserved originals to recover references missed by older importers.
    return canonical_owasp([*rule.get("owasp", []), *rule.get("owasp_raw", [])])


def score_pair(cast: dict, semgrep: dict) -> tuple[int, dict, list[dict]]:
    common_cwe = set(cast["cwe"]) & set(semgrep["cwe"])
    common_owasp = set(owasp_keys(cast)) & set(owasp_keys(semgrep))
    common_language = languages(cast) & languages(semgrep)
    cast_title = tokens(cast["title"])
    semgrep_title = tokens(semgrep["title"])
    title_overlap = cast_title & semgrep_title
    title_union = cast_title | semgrep_title
    title_similarity = len(title_overlap) / len(title_union) if title_union else 0.0
    cast_text = tokens(" ".join(x or "" for x in (cast["description"], cast["rationale"])))
    semgrep_text = tokens(semgrep["description"])
    text_overlap = cast_text & semgrep_text
    text_similarity = len(text_overlap) / max(1, min(len(cast_text), len(semgrep_text)))
    category_match = bool(categories(cast) & categories(semgrep))

    factors = {
        "shared_cwe": sorted(common_cwe), "shared_owasp": sorted(common_owasp),
        "shared_languages": sorted(common_language), "shared_title_terms": sorted(title_overlap),
        "shared_description_terms": sorted(text_overlap)[:20],
        "category_match": bool(category_match),
        "technical_compatibility": 15 if common_language else 0,
        "cwe_reference_points": 30 if common_cwe else 0,
        "owasp_reference_points": 10 if common_owasp else 0,
        "reference_points_cap": 35,
        "defect_references": min(35, (30 if common_cwe else 0) + (10 if common_owasp else 0)),
        "title_similarity": round(20 * title_similarity),
        "description_similarity": round(20 * min(1.0, text_similarity)),
        "category_similarity": 10 if category_match else 0,
        "precondition_alignment": None,
        "semantic_similarity": None,
        "evidence_level": "shared_reference" if common_cwe or common_owasp else "shared_terms_only",
        "method": "deterministic-v2-owasp",
        "limitations": "A high score ranks candidates; it does not establish equivalent detection scope.",
    }
    score = min(100, sum(factors[k] for k in (
        "technical_compatibility", "defect_references", "title_similarity", "description_similarity", "category_similarity"
    )))
    evidence = []
    for ref in sorted(common_cwe):
        evidence.extend([
            _evidence(cast, "CWE", "qualityStandards", ref),
            _evidence(semgrep, "CWE", "metadata.cwe", ref),
        ])
    for ref in sorted(common_owasp):
        evidence.extend([
            _evidence(cast, "OWASP", "qualityStandards", _original_owasp_reference(cast, ref)),
            _evidence(semgrep, "OWASP", "metadata.owasp", _original_owasp_reference(semgrep, ref)),
        ])
    if title_overlap:
        evidence.extend([
            _evidence(cast, "title", "name", cast["title"] or ""),
            _evidence(semgrep, "title", "id/metadata.title", semgrep["title"] or ""),
        ])
    if common_language:
        evidence.extend([
            _evidence(cast, "language", "technologies", ", ".join(cast["languages"])),
            _evidence(semgrep, "language", "languages", ", ".join(semgrep["languages"])),
        ])
    if category_match:
        evidence.extend([
            _evidence(cast, "category", "businessCriteria", cast["category"] or ""),
            _evidence(semgrep, "category", "metadata.category", semgrep["category"] or ""),
        ])
    return score, factors, evidence


def calculate_matches(settings: Settings, *, top_k: int = 15, min_score: int = 18) -> dict:
    with connect(settings.db_path) as conn:
        initialize(conn)
        active_pair_sql = """SELECT m.cast_key,m.semgrep_key,m.score FROM match_candidates m
            JOIN rules c ON c.rule_key=m.cast_key JOIN rules s ON s.rule_key=m.semgrep_key
            WHERE c.status='present' AND s.status='present'"""
        before = {(row["cast_key"], row["semgrep_key"]): row["score"] for row in conn.execute(active_pair_sql)}
        cast = [decode_rule(row) for row in conn.execute("SELECT * FROM rules WHERE source='CAST' AND status='present'")]
        semgrep = [decode_rule(row) for row in conn.execute("SELECT * FROM rules WHERE source='Semgrep' AND status='present'")]
        normalized_rules = 0
        for rule in [*cast, *semgrep]:
            normalized = owasp_keys(rule)
            if rule["owasp"] != normalized:
                conn.execute("UPDATE rules SET owasp_json=? WHERE rule_key=?",
                             (json.dumps(normalized), rule["rule_key"]))
                normalized_rules += 1
            rule["owasp"] = normalized
        by_cwe: dict[str, set[int]] = defaultdict(set)
        by_owasp: dict[str, set[int]] = defaultdict(set)
        by_token: dict[str, set[int]] = defaultdict(set)
        for i, rule in enumerate(semgrep):
            for ref in rule["cwe"]:
                by_cwe[ref].add(i)
            for ref in rule["owasp"]:
                by_owasp[ref].add(i)
            for term in tokens(rule["title"]):
                by_token[term].add(i)

        # Preserve pairs that an expert has reviewed; unreviewed suggestions are reproducible.
        conn.execute("""
          DELETE FROM match_candidates
          WHERE COALESCE(json_extract(factors_json, '$.manual_association'), 0) != 1
            AND COALESCE(json_extract(factors_json, '$.method'), '') != 'manual'
            AND NOT EXISTS (
            SELECT 1 FROM expert_reviews r WHERE r.cast_key=match_candidates.cast_key AND r.semgrep_key=match_candidates.semgrep_key
          ) AND NOT EXISTS (
            SELECT 1 FROM llm_proposals l WHERE l.cast_key=match_candidates.cast_key AND l.semgrep_key=match_candidates.semgrep_key
          )
        """)
        pair_count = 0
        for cast_rule in cast:
            candidate_indexes: set[int] = set()
            for ref in cast_rule["cwe"]:
                candidate_indexes.update(by_cwe.get(ref, ()))
            for ref in cast_rule["owasp"]:
                candidate_indexes.update(by_owasp.get(ref, ()))
            for term in tokens(cast_rule["title"]):
                if len(by_token.get(term, ())) <= 250:
                    candidate_indexes.update(by_token.get(term, ()))
            ranked = []
            for i in candidate_indexes:
                target = semgrep[i]
                cast_languages, target_languages = languages(cast_rule), languages(target)
                if cast_languages and target_languages and not (cast_languages & target_languages):
                    continue
                score, factors, evidence = score_pair(cast_rule, target)
                distinctive_title_terms = set(factors["shared_title_terms"]) - GENERIC_DEFECT_TERMS
                plausible = (
                    bool(factors["shared_cwe"])
                    or (bool(factors["shared_owasp"]) and
                        bool(distinctive_title_terms) and len(factors["shared_description_terms"]) >= 2)
                    or len(factors["shared_title_terms"]) >= 2
                )
                if score >= min_score and plausible:
                    ranked.append((score, target["rule_key"], factors, evidence))
            for score, target_key, factors, evidence in sorted(ranked, key=lambda x: (-x[0], x[1]))[:top_k]:
                pair = (cast_rule["rule_key"], target_key)
                conn.execute("""
                  INSERT INTO match_candidates(cast_key,semgrep_key,score,factors_json,suggested_status,updated_at)
                  VALUES(?,?,?,?,?,?)
                  ON CONFLICT(cast_key,semgrep_key) DO UPDATE SET
                    score=excluded.score,factors_json=CASE
                      WHEN json_extract(match_candidates.factors_json,'$.manual_association')=1
                        OR json_extract(match_candidates.factors_json,'$.method')='manual'
                      THEN json_set(excluded.factors_json,'$.manual_association',json('true'),
                        '$.manually_associated_at',json_extract(match_candidates.factors_json,'$.manually_associated_at'))
                      ELSE excluded.factors_json END,updated_at=excluded.updated_at
                """, (*pair, score, json.dumps(factors, ensure_ascii=False), "indeterminate", utc_now()))
                conn.execute("DELETE FROM match_evidence WHERE cast_key=? AND semgrep_key=?", pair)
                conn.executemany("""
                  INSERT INTO match_evidence(cast_key,semgrep_key,dimension,source_rule_key,reference_url,reference_field,excerpt,origin)
                  VALUES(?,?,?,?,?,?,?,?)
                """, [(*pair, ev["dimension"], ev["source_rule_key"], ev["reference_url"],
                       ev["reference_field"], ev["excerpt"], ev["origin"]) for ev in evidence])
                pair_count += 1
        after = {(row["cast_key"], row["semgrep_key"]): row["score"] for row in conn.execute(active_pair_sql)}
        new_pairs, removed_pairs = after.keys() - before.keys(), before.keys() - after.keys()
        newly_matched = {source: len({pair[index] for pair in after} - {pair[index] for pair in before})
                         for index, source in enumerate(("CAST", "Semgrep"))}
    return {"cast_rules": len(cast), "semgrep_rules": len(semgrep), "candidates": pair_count,
            "method": "deterministic-v2-owasp", "top_k": top_k, "min_score": min_score,
            "owasp_normalized_rules": normalized_rules,
            "active_pairs_before": len(before), "active_pairs_after": len(after),
            "new_pairs": len(new_pairs), "removed_pairs": len(removed_pairs),
            "changed_scores": sum(before[pair] != after[pair] for pair in before.keys() & after.keys()),
            "newly_matched_rules": newly_matched}
