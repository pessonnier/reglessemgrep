"""Local versioned embedding storage. No model calls or remote transmission."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone


def text_hash(title: str, description: str) -> str:
    content = json.dumps({'title': title, 'description': description}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def sync_documents(conn: sqlite3.Connection, rule_keys: list[str] | None = None) -> int:
    """Snapshot exact text; imports reuse identical content and preserve older versions."""
    if rule_keys == []:
        return 0
    query = "SELECT rule_key,COALESCE(title,'') title,COALESCE(description,'') description FROM rules WHERE status='present'"
    values = []
    if rule_keys is not None:
        # Called per imported rule; bounded public callers may also pass a small batch.
        query += ' AND rule_key IN (' + ','.join('?' for _ in rule_keys) + ')'
        values = rule_keys
    rows = conn.execute(query, values).fetchall()
    now = datetime.now(timezone.utc).isoformat(timespec='seconds')
    added = 0
    for row in rows:
        key, title, description = row
        cursor = conn.execute('''INSERT INTO semantic_documents(rule_key,content_hash,title,description,has_title,has_description,created_at)
            VALUES(?,?,?,?,?,?,?) ON CONFLICT(rule_key,content_hash) DO NOTHING''',
            (key, text_hash(title, description), title, description, int(bool(title.strip())), int(bool(description.strip())), now))
        added += cursor.rowcount
    return added


def semantic_status(conn: sqlite3.Connection) -> dict:
    return {
        'current_documents': conn.execute('SELECT COUNT(*) FROM semantic_current_documents').fetchone()[0],
        'document_versions': conn.execute('SELECT COUNT(*) FROM semantic_documents').fetchone()[0],
        'models': conn.execute('SELECT COUNT(*) FROM semantic_models').fetchone()[0],
        'embedding_records': conn.execute('SELECT COUNT(*) FROM semantic_embeddings').fetchone()[0],
        'title_vectors': conn.execute('SELECT COUNT(*) FROM semantic_embeddings WHERE title_vector_json IS NOT NULL').fetchone()[0],
        'description_vectors': conn.execute('SELECT COUNT(*) FROM semantic_embeddings WHERE description_vector_json IS NOT NULL').fetchone()[0],
        'coverage': [dict(row) for row in conn.execute('SELECT model_key,status,COUNT(*) count FROM semantic_coverage GROUP BY model_key,status ORDER BY model_key,status')],
    }
