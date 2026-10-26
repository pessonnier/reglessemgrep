"""SQLite persistence for catalogues, provenance, and comparison decisions."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


MIGRATIONS = Path(__file__).parent / "migrations"

RULE_COLUMNS = (
    "rule_key", "source", "rule_id", "title", "description", "rationale", "remediation", "severity", "category",
    "classification_origin", "categories_json", "languages_json", "frameworks_json", "technologies_json", "cwe_json",
    "owasp_json", "owasp_raw_json", "standards_json", "detection_method", "source_url", "source_version", "raw_path",
    "status", "collected_at", "snapshot_id",
)


@contextmanager
def connect(path: Path) -> Iterator[sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.executescript((MIGRATIONS / "001_initial.sql").read_text(encoding="utf-8"))
        conn.execute("PRAGMA user_version = 1")
        version = 1
    if version == 1:
        conn.executescript((MIGRATIONS / "002_categories.sql").read_text(encoding="utf-8"))
        conn.execute("PRAGMA user_version = 2")
        version = 2
    if version == 2:
        conn.executescript((MIGRATIONS / "003_owasp_raw.sql").read_text(encoding="utf-8"))
        conn.execute("PRAGMA user_version = 3")
    elif version != 3:
        raise RuntimeError(f"Unsupported database schema version: {version}")


def create_snapshot(
    conn: sqlite3.Connection, *, source: str, revision: str, archive_path: Path,
    auth_mode: str = "public", status: str = "complete", stats: dict | None = None,
) -> int:
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE source=? AND revision=? AND archive_path=? AND auth_mode=? ORDER BY id DESC LIMIT 1",
        (source, revision, str(archive_path), auth_mode),
    ).fetchone()
    if existing is not None:
        conn.execute(
            "UPDATE snapshots SET status=?,stats_json=? WHERE id=?",
            (status, json.dumps(stats or {}, ensure_ascii=False), existing["id"]),
        )
        return int(existing["id"])
    cursor = conn.execute(
        "INSERT INTO snapshots(source, revision, archive_path, collected_at, auth_mode, status, stats_json) VALUES(?,?,?,?,?,?,?)",
        (source, revision, str(archive_path), utc_now(), auth_mode, status, json.dumps(stats or {}, ensure_ascii=False)),
    )
    return int(cursor.lastrowid)


def upsert_rules(conn: sqlite3.Connection, rules: Iterable[dict], *, source: str, snapshot_id: int, mark_missing: bool = True) -> int:
    now = utc_now()
    columns = ",".join(RULE_COLUMNS)
    markers = ",".join("?" for _ in RULE_COLUMNS)
    changes = ",".join(f"{c}=excluded.{c}" for c in RULE_COLUMNS if c != "rule_key")
    sql = f"INSERT INTO rules({columns}) VALUES({markers}) ON CONFLICT(rule_key) DO UPDATE SET {changes}"
    count = 0
    if mark_missing:
        conn.execute("UPDATE rules SET status='unseen' WHERE source=? AND status='present'", (source,))
    for rule in rules:
        record = {**rule, "collected_at": now, "snapshot_id": snapshot_id, "status": "present"}
        conn.execute(sql, tuple(record.get(c) for c in RULE_COLUMNS))
        count += 1
    if mark_missing:
        conn.execute(
            "UPDATE rules SET status='removed' WHERE source=? AND status='unseen'",
            (source,),
        )
    return count


def decode_rule(row: sqlite3.Row | dict) -> dict:
    result = dict(row)
    for field in ("categories_json", "languages_json", "frameworks_json", "technologies_json", "cwe_json", "owasp_json", "owasp_raw_json", "standards_json"):
        result[field.removesuffix("_json")] = json.loads(result.pop(field) or "[]")
    return result
