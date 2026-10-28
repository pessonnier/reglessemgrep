"""Local API and browser interface for catalogues and review."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .config import load_settings
from .db import connect, initialize, utc_now
from .uncertainty import rules_with_uncertainty
from .correspondences import cast_correspondences


settings = load_settings()
static_dir = Path(__file__).parent / "static"
app = FastAPI(title="CAST–Semgrep Rules Comparator", version="0.1.0")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(static_dir / "index.html")


@app.get("/api/summary")
def summary():
    with connect(settings.db_path) as conn:
        initialize(conn)
        counts = {row["source"]: row["count"] for row in conn.execute(
            "SELECT source,COUNT(*) AS count FROM rules WHERE status='present' GROUP BY source"
        )}
        categories = [dict(row) for row in conn.execute("""
            SELECT source,category,COUNT(*) AS count FROM (
              SELECT r.source,j.value AS category FROM rules r,json_each(r.categories_json) j WHERE r.status='present'
              UNION ALL
              SELECT source,'Non renseignée' FROM rules WHERE status='present' AND json_array_length(categories_json)=0
            ) GROUP BY source,category ORDER BY count DESC LIMIT 30
        """)]
        languages = [dict(row) for row in conn.execute(
            "SELECT r.source,j.value AS language,COUNT(*) AS count FROM rules r,json_each(r.languages_json) j "
            "WHERE r.status='present' GROUP BY r.source,j.value ORDER BY count DESC LIMIT 30"
        )]
        severities = [dict(row) for row in conn.execute(
            "SELECT source,COALESCE(severity,'Non renseignée') AS severity,COUNT(*) AS count "
            "FROM rules WHERE status='present' GROUP BY source,severity ORDER BY count DESC LIMIT 30"
        )]
        snapshots = []
        for row in conn.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT 8"):
            item = dict(row)
            item["stats"] = json.loads(item.pop("stats_json"))
            snapshots.append(item)
        candidate_count = conn.execute("SELECT COUNT(*) FROM match_candidates").fetchone()[0]
        reviewed_count = conn.execute("SELECT COUNT(DISTINCT cast_key || '|' || semgrep_key) FROM expert_reviews").fetchone()[0]
        matched_cast = conn.execute("SELECT COUNT(DISTINCT cast_key) FROM match_candidates").fetchone()[0]
        matched_semgrep = conn.execute("SELECT COUNT(DISTINCT semgrep_key) FROM match_candidates").fetchone()[0]
        uncertainty = [dict(row) for row in conn.execute("""
            SELECT u.status,u.uncertainty_level,COUNT(*) AS count FROM rule_uncertainty u
            JOIN rules r USING(rule_key) WHERE r.status='present'
            GROUP BY u.status,u.uncertainty_level ORDER BY u.status,u.uncertainty_level
        """)]
    return {"counts": counts, "candidates": candidate_count, "reviewed": reviewed_count,
            "unmatched": {"CAST": max(0, counts.get("CAST", 0) - matched_cast),
                          "Semgrep": max(0, counts.get("Semgrep", 0) - matched_semgrep)},
            "categories": categories, "languages": languages, "severities": severities, "snapshots": snapshots,
            "uncertainty": uncertainty}


@app.get("/api/rules")
def list_rules(
    q: str = "", source: str = "", language: str = "", category: str = "", cwe: str = "",
    severity: str = "", page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
    uncertainty_level: str = "", assessment_status: str = "",
    false_positive_risk: str = "", false_negative_risk: str = "",
):
    where = ["r.status='present'"]
    values: list[object] = []
    if q.strip():
        where.append("LOWER(COALESCE(r.rule_id,'') || ' ' || COALESCE(r.title,'') || ' ' || COALESCE(r.description,'')) LIKE ?")
        values.append("%" + q.strip().lower() + "%")
    if source:
        where.append("r.source=?")
        values.append(source)
    if language:
        where.append("EXISTS(SELECT 1 FROM json_each(r.languages_json) WHERE LOWER(value)=?)")
        values.append(language.lower())
    if category:
        if category.lower() == "non renseignée":
            where.append("json_array_length(r.categories_json)=0")
        else:
            where.append("EXISTS(SELECT 1 FROM json_each(r.categories_json) WHERE LOWER(value)=?)")
            values.append(category.lower())
    if cwe:
        where.append("EXISTS(SELECT 1 FROM json_each(r.cwe_json) WHERE LOWER(value)=?)")
        values.append(cwe.lower())
    if severity:
        if severity.lower() == "non renseignée":
            where.append("r.severity IS NULL")
        else:
            where.append("LOWER(COALESCE(r.severity,''))=?")
            values.append(severity.lower())
    for field, value in (("uncertainty_level", uncertainty_level), ("status", assessment_status),
                         ("false_positive_risk", false_positive_risk), ("false_negative_risk", false_negative_risk)):
        if value and source != "CAST":
            where.append(f"EXISTS(SELECT 1 FROM rule_uncertainty u WHERE u.rule_key=r.rule_key AND u.{field}=?)")
            values.append(value)
    predicate = " AND ".join(where)
    with connect(settings.db_path) as conn:
        initialize(conn)
        total = conn.execute(f"SELECT COUNT(*) FROM rules r WHERE {predicate}", values).fetchone()[0]
        rows = conn.execute(
            f"SELECT r.* FROM rules r WHERE {predicate} ORDER BY r.source,r.rule_id LIMIT ? OFFSET ?",
            [*values, page_size, (page - 1) * page_size],
        ).fetchall()
        items = rules_with_uncertainty(conn, rows)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/correspondences")
def list_correspondences(
    q: str = "", language: str = "", cwe: str = "",
    status: Literal["", "with_candidates", "without_candidates", "expert_equivalent"] = "",
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    with connect(settings.db_path) as conn:
        initialize(conn)
        return cast_correspondences(conn, q=q, language=language, cwe=cwe, status=status,
                                    page=page, page_size=page_size)


@app.get("/api/rule")
def get_rule(key: str):
    with connect(settings.db_path) as conn:
        initialize(conn)
        row = conn.execute("SELECT * FROM rules WHERE rule_key=?", (key,)).fetchone()
        if row is None:
            raise HTTPException(404, "Rule not found")
        result = rules_with_uncertainty(conn, [row])[0]
        result["uncertainty_history"] = [dict(x) for x in conn.execute(
            "SELECT * FROM uncertainty_assessments WHERE rule_key=? ORDER BY id DESC", (key,)
        )]
    raw_path = Path(result["raw_path"])
    try:
        raw_path.resolve().relative_to(settings.data_dir.resolve())
        result["raw_content"] = raw_path.read_text(encoding="utf-8") if raw_path.is_file() else None
    except (ValueError, OSError, UnicodeError):
        result["raw_content"] = None
    return result


@app.get("/api/matches")
def list_matches(key: str, limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    with connect(settings.db_path) as conn:
        initialize(conn)
        rule = conn.execute("SELECT source FROM rules WHERE rule_key=?", (key,)).fetchone()
        if not rule:
            raise HTTPException(404, "Rule not found")
        own = "cast_key" if rule["source"] == "CAST" else "semgrep_key"
        other = "semgrep_key" if own == "cast_key" else "cast_key"
        rows = conn.execute(f"""
          SELECT m.*,r.rule_id AS other_id,r.title AS other_title,r.source_url AS other_url,
          (SELECT decision FROM expert_reviews e WHERE e.cast_key=m.cast_key AND e.semgrep_key=m.semgrep_key ORDER BY id DESC LIMIT 1) AS expert_decision,
          (SELECT COUNT(*) FROM match_evidence e WHERE e.cast_key=m.cast_key AND e.semgrep_key=m.semgrep_key) AS evidence_count
          FROM match_candidates m JOIN rules r ON r.rule_key=m.{other}
          WHERE m.{own}=? AND r.status='present' ORDER BY m.score DESC,m.{other} LIMIT ? OFFSET ?
        """, (key, limit, offset)).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM match_candidates m JOIN rules r ON r.rule_key=m.{other} "
                             f"WHERE m.{own}=? AND r.status='present'", (key,)).fetchone()[0]
    items = []
    for row in rows:
        item = dict(row)
        item["factors"] = json.loads(item.pop("factors_json"))
        items.append(item)
    return {"items": items, "total": total}


@app.get("/api/match")
def get_match(cast_key: str, semgrep_key: str):
    with connect(settings.db_path) as conn:
        initialize(conn)
        pair = (cast_key, semgrep_key)
        row = conn.execute("SELECT * FROM match_candidates WHERE cast_key=? AND semgrep_key=?", pair).fetchone()
        if not row:
            raise HTTPException(404, "Comparison not found")
        cast = conn.execute("SELECT * FROM rules WHERE rule_key=?", (cast_key,)).fetchone()
        semgrep = conn.execute("SELECT * FROM rules WHERE rule_key=?", (semgrep_key,)).fetchone()
        evidence = [dict(x) for x in conn.execute(
            "SELECT * FROM match_evidence WHERE cast_key=? AND semgrep_key=? ORDER BY dimension,origin", pair
        )]
        llm = [dict(x) for x in conn.execute(
            "SELECT * FROM llm_proposals WHERE cast_key=? AND semgrep_key=? ORDER BY id DESC", pair
        )]
        reviews = [dict(x) for x in conn.execute(
            "SELECT * FROM expert_reviews WHERE cast_key=? AND semgrep_key=? ORDER BY id DESC", pair
        )]
        cast_result, semgrep_result = rules_with_uncertainty(conn, [cast, semgrep])
    result = dict(row)
    result["factors"] = json.loads(result.pop("factors_json"))
    for proposal in llm:
        proposal["proposal"] = json.loads(proposal.pop("proposal_json"))
    return {"candidate": result, "cast": cast_result, "semgrep": semgrep_result,
            "sourced_evidence": evidence, "llm_proposals": llm, "expert_reviews": reviews}


RiskLevel = Literal["unknown", "low", "medium", "high"]


class UncertaintyInput(BaseModel):
    rule_key: str
    source_version: str = Field(min_length=1)
    definition_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer: str = Field(min_length=1, max_length=120)
    uncertainty_level: RiskLevel
    false_positive_risk: RiskLevel
    false_negative_risk: RiskLevel
    scope: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=5000)
    evidence: str = Field(default="", max_length=5000)

    @field_validator("reviewer", "scope", "rationale")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ce champ ne peut pas être vide.")
        return value.strip()


@app.post("/api/uncertainty-assessments", status_code=201)
def add_uncertainty_assessment(payload: UncertaintyInput):
    with connect(settings.db_path) as conn:
        initialize(conn)
        # Keep the version check and insert atomic against concurrent imports.
        conn.execute("BEGIN IMMEDIATE")
        rule = conn.execute("SELECT * FROM rules WHERE rule_key=?", (payload.rule_key,)).fetchone()
        if rule is None:
            raise HTTPException(404, "Règle introuvable")
        if rule["source"] != "Semgrep":
            raise HTTPException(422, "L’évaluation concerne une règle Semgrep")
        if rule["status"] != "present" or rule["source_version"] != payload.source_version or rule["definition_hash"] != payload.definition_hash:
            raise HTTPException(409, "La règle a changé. Réimportez si nécessaire et rechargez sa fiche avant l’évaluation.")
        data = payload.model_dump()
        data["created_at"] = utc_now()
        columns = ','.join(data)
        markers = ','.join('?' for _ in data)
        cursor = conn.execute(f"INSERT INTO uncertainty_assessments({columns}) VALUES({markers})", tuple(data.values()))
        return dict(conn.execute("SELECT * FROM uncertainty_assessments WHERE id=?", (cursor.lastrowid,)).fetchone())


class ReviewInput(BaseModel):
    cast_key: str
    semgrep_key: str
    reviewer: str = Field(min_length=1, max_length=120)
    decision: str
    comment: str = Field(default="", max_length=5000)


DECISIONS = {"equivalent", "partial", "complementary", "related", "no_match", "indeterminate", "not_comparable"}


@app.post("/api/reviews")
def add_review(payload: ReviewInput):
    if payload.decision not in DECISIONS:
        raise HTTPException(422, "Invalid decision")
    with connect(settings.db_path) as conn:
        initialize(conn)
        pair = (payload.cast_key, payload.semgrep_key)
        exists = conn.execute("SELECT 1 FROM match_candidates WHERE cast_key=? AND semgrep_key=?", pair).fetchone()
        if not exists:
            raise HTTPException(404, "Comparison not found")
        cursor = conn.execute(
            "INSERT INTO expert_reviews(cast_key,semgrep_key,reviewer,decision,comment,created_at) VALUES(?,?,?,?,?,?)",
            (*pair, payload.reviewer.strip(), payload.decision, payload.comment.strip(), utc_now()),
        )
        review = conn.execute("SELECT * FROM expert_reviews WHERE id=?", (cursor.lastrowid,)).fetchone()
    return dict(review)


class ManualCandidateInput(BaseModel):
    cast_key: str
    semgrep_key: str


@app.post("/api/candidates")
def add_manual_candidate(payload: ManualCandidateInput):
    with connect(settings.db_path) as conn:
        initialize(conn)
        source_rows = conn.execute("SELECT rule_key,source FROM rules WHERE rule_key IN (?,?)", (payload.cast_key, payload.semgrep_key)).fetchall()
        sources = {row["rule_key"]: row["source"] for row in source_rows}
        if sources.get(payload.cast_key) != "CAST" or sources.get(payload.semgrep_key) != "Semgrep":
            raise HTTPException(422, "Select one CAST and one Semgrep rule")
        conn.execute("""
          INSERT INTO match_candidates(cast_key,semgrep_key,score,factors_json,suggested_status,updated_at)
          VALUES(?,?,?,?,?,?) ON CONFLICT(cast_key,semgrep_key) DO NOTHING
        """, (payload.cast_key, payload.semgrep_key, 0, json.dumps({"method":"manual"}), "indeterminate", utc_now()))
    return {"cast_key": payload.cast_key, "semgrep_key": payload.semgrep_key}


def _csv_response(rows: list[dict], filename: str) -> StreamingResponse:
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value
                             for key, value in row.items()})
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/export/rules.csv")
def export_rules(source: str = ""):
    with connect(settings.db_path) as conn:
        initialize(conn)
        predicate = "AND r.source=?" if source in ("CAST", "Semgrep") else ""
        values = (source,) if predicate else ()
        rows = [dict(row) for row in conn.execute(
            "SELECT r.source,r.rule_id,r.title,r.category,r.classification_origin,r.severity,r.source_url,r.source_version,r.status,"
            "r.definition_hash,r.source_confidence,u.status AS assessment_status,u.uncertainty_level,"
            "u.false_positive_risk,u.false_negative_risk,u.origin AS assessment_origin,u.scope,u.rationale,u.evidence,u.reviewer,u.created_at AS assessed_at "
            f"FROM rules r LEFT JOIN rule_uncertainty u USING(rule_key) WHERE r.status='present' {predicate} ORDER BY r.source,r.rule_id", values
        )]
    return _csv_response(rows, "rules.csv")


@app.get("/api/export/matches.csv")
def export_matches():
    with connect(settings.db_path) as conn:
        initialize(conn)
        rows = [dict(row) for row in conn.execute("""
          SELECT c.rule_id AS cast_id,s.rule_id AS semgrep_id,m.score,m.suggested_status,
          (SELECT decision FROM expert_reviews e WHERE e.cast_key=m.cast_key AND e.semgrep_key=m.semgrep_key ORDER BY id DESC LIMIT 1) AS expert_decision,
          c.source_url AS cast_url,s.source_url AS semgrep_url,
          u.uncertainty_level,u.false_positive_risk,u.false_negative_risk,
          u.status AS assessment_status,u.origin AS assessment_origin,u.scope AS assessment_scope
          FROM match_candidates m JOIN rules c ON c.rule_key=m.cast_key JOIN rules s ON s.rule_key=m.semgrep_key
          LEFT JOIN rule_uncertainty u ON u.rule_key=s.rule_key
          ORDER BY c.rule_id,m.score DESC
        """)]
    return _csv_response(rows, "matches.csv")
