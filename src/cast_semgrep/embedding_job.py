"""Common resumable storage job for validated embedding providers."""
from __future__ import annotations

import json

from .db import connect, initialize, utc_now
from .semantic import sync_documents

MAX_BATCH_BYTES = 200_000


class EmbeddingError(RuntimeError):
    """Safe operational error, without credentials or remote response bodies."""


def run_job(settings, config, *, send, batch_size=64, limit=None, dry_run=False,
            max_input_bytes=None, prepare=None, progress=None):
    if not 1 <= batch_size <= 128 or (limit is not None and limit < 1):
        raise EmbeddingError('Taille de lot ou limite invalide.')
    key = config['model_key']
    with connect(settings.db_path) as conn:
        initialize(conn)
        sync_documents(conn)
        # Reuse an existing registry key for this exact configuration.
        existing = conn.execute('''SELECT * FROM semantic_models WHERE provider=? AND model_name=?
            AND model_revision=? AND dimensions=? AND preprocessing=?''',
            tuple(config[k] for k in ('provider', 'model_name', 'model_revision', 'dimensions', 'preprocessing'))).fetchone()
        if existing:
            key = existing['model_key']
        elif conn.execute('SELECT 1 FROM semantic_models WHERE model_key=?', (key,)).fetchone():
            raise EmbeddingError('Clé de modèle déjà utilisée pour une autre configuration.')
        rows = conn.execute('''SELECT d.*,e.title_vector_json,e.description_vector_json
            FROM semantic_current_documents d LEFT JOIN semantic_embeddings e
            ON e.rule_key=d.rule_key AND e.content_hash=d.content_hash AND e.model_key=? ORDER BY d.rule_key''', (key,)).fetchall()
    pending, oversized = [], []
    for row in rows:
        for field in ('title', 'description'):
            if row[f'has_{field}'] and row[f'{field}_vector_json'] is None:
                if max_input_bytes is not None and len(row[field].encode('utf-8')) > max_input_bytes:
                    oversized.append({'rule_key': row['rule_key'], 'field': field})
                else:
                    pending.append((row['rule_key'], row['content_hash'], field, row[field]))
    total_pending = len(pending)
    if limit is not None:
        pending = pending[:limit]
    result = {'model_key': key, 'model': config['model_name'], 'dimensions': config['dimensions'], 'dry_run': dry_run,
              'pending_vectors': total_pending, 'selected_vectors': len(pending), 'oversized_fields': oversized,
              'saved_vectors': 0, 'stale_vectors': 0, 'already_saved_vectors': 0, 'requests': 0, 'total_tokens': 0}
    if dry_run or not pending:
        return result
    if prepare:
        prepare()
    with connect(settings.db_path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        config['model_key'] = key
        previous = conn.execute('SELECT * FROM semantic_models WHERE model_key=?', (key,)).fetchone()
        if previous and any(previous[k] != v for k, v in config.items()):
            raise EmbeddingError('La configuration du modèle a changé.')
        if not previous:
            conn.execute('''INSERT INTO semantic_models(model_key,provider,model_name,model_revision,dimensions,preprocessing,created_at)
                VALUES(?,?,?,?,?,?,?)''', (*config.values(), utc_now()))
    offset = 0
    while offset < len(pending):
        batch, byte_count = [], 0
        for item in pending[offset:offset + batch_size]:
            size = len(item[3].encode('utf-8'))
            if batch and byte_count + size > MAX_BATCH_BYTES:
                break
            batch.append(item)
            byte_count += size
        vectors, tokens = send([item[3] for item in batch])
        # No transaction is kept open during remote calls. Check current text again.
        saved = stale = already_saved = 0
        with connect(settings.db_path) as conn:
            conn.execute('BEGIN IMMEDIATE')
            for (rule_key, content_hash, field, _), vector in zip(batch, vectors):
                if not conn.execute('SELECT 1 FROM semantic_current_documents WHERE rule_key=? AND content_hash=?',
                                    (rule_key, content_hash)).fetchone():
                    stale += 1
                    continue
                column = field + '_vector_json'  # field comes only from the fixed pair above
                now = utc_now()
                cursor = conn.execute(f'''INSERT INTO semantic_embeddings(rule_key,content_hash,model_key,{column},created_at,updated_at)
                    VALUES(?,?,?,?,?,?) ON CONFLICT(rule_key,content_hash,model_key) DO UPDATE SET
                    {column}=excluded.{column},updated_at=excluded.updated_at WHERE semantic_embeddings.{column} IS NULL''',
                    (rule_key, content_hash, key, json.dumps(vector, allow_nan=False), now, now))
                saved += cursor.rowcount
                already_saved += 1 - cursor.rowcount
        offset += len(batch)
        result['saved_vectors'] += saved
        result['stale_vectors'] += stale
        result['already_saved_vectors'] += already_saved
        result['requests'] += 1
        result['total_tokens'] += tokens
        if progress:
            progress(dict(result))
    return result

