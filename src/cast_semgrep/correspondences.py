"""CAST-first catalogue with active Semgrep candidates and latest expert decisions."""

import json
import sqlite3


ACTIVE_PAIRS = """
WITH active_pairs AS (
  SELECT m.*,
    (SELECT decision FROM expert_reviews e WHERE e.cast_key=m.cast_key
      AND e.semgrep_key=m.semgrep_key ORDER BY id DESC LIMIT 1) AS expert_decision
  FROM match_candidates m
  WHERE EXISTS(SELECT 1 FROM rules c WHERE c.rule_key=m.cast_key AND c.source='CAST' AND c.status='present')
    AND EXISTS(SELECT 1 FROM rules s WHERE s.rule_key=m.semgrep_key AND s.source='Semgrep' AND s.status='present')
), pair_counts AS (
  SELECT cast_key,COUNT(*) AS candidate_count,MAX(score) AS best_score,
    SUM(CASE WHEN expert_decision='equivalent' THEN 1 ELSE 0 END) AS equivalent_count
  FROM active_pairs GROUP BY cast_key
)
"""


def cast_correspondences(conn: sqlite3.Connection, *, q: str = "", language: str = "", cwe: str = "",
                         status: str = "", page: int = 1, page_size: int = 20) -> dict:
    filters = ["r.source='CAST'", "r.status='present'"]
    values = []
    if q.strip():
        filters.append("""(LOWER(r.rule_id || ' ' || COALESCE(r.title,'') || ' ' || COALESCE(r.description,'')) LIKE ?
          OR EXISTS(SELECT 1 FROM active_pairs p JOIN rules s ON s.rule_key=p.semgrep_key
            WHERE p.cast_key=r.rule_key AND LOWER(s.rule_id || ' ' || COALESCE(s.title,'')) LIKE ?))""")
        values.extend([f"%{q.strip().lower()}%"] * 2)
    if language.strip():
        filters.append("EXISTS(SELECT 1 FROM json_each(r.languages_json) WHERE LOWER(value)=?)")
        values.append(language.strip().lower())
    if cwe.strip():
        filters.append("EXISTS(SELECT 1 FROM json_each(r.cwe_json) WHERE LOWER(value)=?)")
        values.append(cwe.strip().lower())
    base = " FROM rules r LEFT JOIN pair_counts pc ON pc.cast_key=r.rule_key WHERE " + " AND ".join(filters)
    summary = dict(conn.execute(ACTIVE_PAIRS + """
      SELECT COUNT(*) AS cast_count,
        COALESCE(SUM(CASE WHEN pc.candidate_count>0 THEN 1 ELSE 0 END),0) AS with_candidates,
        COALESCE(SUM(CASE WHEN pc.candidate_count IS NULL THEN 1 ELSE 0 END),0) AS without_candidates,
        COALESCE(SUM(CASE WHEN pc.equivalent_count>0 THEN 1 ELSE 0 END),0) AS with_expert_equivalent
    """ + base, values).fetchone())
    status_filter = {
        "with_candidates": " AND pc.candidate_count>0",
        "without_candidates": " AND pc.candidate_count IS NULL",
        "expert_equivalent": " AND pc.equivalent_count>0",
    }.get(status, "")
    total = conn.execute(ACTIVE_PAIRS + "SELECT COUNT(*)" + base + status_filter, values).fetchone()[0]
    rows = conn.execute(ACTIVE_PAIRS + """
      SELECT r.rule_key,r.rule_id,r.title,r.languages_json,r.cwe_json,
        COALESCE(pc.candidate_count,0) AS candidate_count,COALESCE(pc.equivalent_count,0) AS equivalent_count
    """ + base + status_filter + """
      ORDER BY COALESCE(pc.equivalent_count,0)>0 DESC,COALESCE(pc.candidate_count,0)>0 DESC,
        pc.best_score DESC,r.rule_id,r.rule_key LIMIT ? OFFSET ?
    """, [*values, page_size, (page-1)*page_size]).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["languages"] = json.loads(item.pop("languages_json"))
        item["cwe"] = json.loads(item.pop("cwe_json"))
        item["matches"] = []
        items.append(item)
    if items:
        by_key = {item["rule_key"]: item for item in items}
        placeholders = ','.join('?' for _ in items)
        pairs = conn.execute(ACTIVE_PAIRS + f""", ranked AS (
          SELECT p.cast_key,p.semgrep_key,p.score,p.expert_decision,COALESCE(json_extract(p.factors_json,'$.manual_association'),0) AS manual_association,s.rule_id,s.title,s.languages_json,
            u.uncertainty_level,u.false_positive_risk,u.false_negative_risk,u.status AS assessment_status,
            ROW_NUMBER() OVER (PARTITION BY p.cast_key ORDER BY
              CASE WHEN p.expert_decision='equivalent' THEN 0 WHEN p.expert_decision='partial' THEN 1
                WHEN p.expert_decision IN ('no_match','not_comparable') THEN 3 ELSE 2 END,
              p.score DESC,p.semgrep_key) AS rank
          FROM active_pairs p JOIN rules s ON s.rule_key=p.semgrep_key
          LEFT JOIN rule_uncertainty u ON u.rule_key=s.rule_key
          WHERE p.cast_key IN ({placeholders})
        ) SELECT * FROM ranked WHERE rank<=3 ORDER BY cast_key,rank
        """, list(by_key)).fetchall()
        for pair in pairs:
            item = dict(pair)
            item.pop("rank")
            item["languages"] = json.loads(item.pop("languages_json"))
            by_key[item["cast_key"]]["matches"].append(item)
    return {"total": total, "page": page, "page_size": page_size, "summary": summary, "items": items}
