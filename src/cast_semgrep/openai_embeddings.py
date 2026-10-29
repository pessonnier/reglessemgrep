"""Resumable OpenAI embeddings job; run via comparator embed-openai or python -m."""
from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .db import connect, initialize, utc_now
from .semantic import sync_documents
from .semantic_api import SemanticEmbeddingInput, SemanticModelInput

DEFAULT_MODEL = 'text-embedding-3-small'
MODEL_DIMENSIONS = {DEFAULT_MODEL: 1536, 'text-embedding-3-large': 3072}
# A UTF-8 byte bound is conservative for byte-level tokenization: no truncation.
MAX_INPUT_BYTES = 8191
MAX_BATCH_BYTES = 200_000


class EmbeddingError(RuntimeError):
    """A safe error message which contains neither credentials nor response bodies."""


def request_embeddings(api_key, texts, model, dimensions):
    body = json.dumps({'model': model, 'input': texts, 'dimensions': dimensions,
                       'encoding_format': 'float'}).encode()
    for attempt in range(4):
        request = Request('https://api.openai.com/v1/embeddings', data=body,
                          headers={'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            status = error.code
            error.close()
            if (status == 429 or 500 <= status < 600) and attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            guidance = 'Vérifiez OPENAI_API_KEY.' if status == 401 else 'Vérifiez les droits et le quota du compte OpenAI.'
            raise EmbeddingError(f'OpenAI HTTP {status}. {guidance} Relancez pour reprendre les lots enregistrés.') from None
        except (URLError, TimeoutError, OSError):
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
                continue
            raise EmbeddingError('Connexion OpenAI impossible. Les lots enregistrés sont conservés.') from None
        except (ValueError, UnicodeError):
            raise EmbeddingError('Réponse OpenAI illisible ; aucun vecteur de ce lot enregistré.') from None


def validate_response(response, count, model, dimensions):
    """Use explicit response indices, never assume response list order."""
    try:
        if response['model'] != model or len(response['data']) != count:
            raise ValueError()
        vectors = {}
        for item in response['data']:
            index = item['index']
            if type(index) is not int or not 0 <= index < count or index in vectors:
                raise ValueError()
            vector = SemanticEmbeddingInput.valid_vector(item['embedding'])
            if vector is None or len(vector) != dimensions:
                raise ValueError()
            vectors[index] = vector
        tokens = response['usage']['total_tokens']
        if type(tokens) is not int or tokens < 0:
            raise ValueError()
        return [vectors[i] for i in range(count)], tokens
    except (KeyError, TypeError, ValueError, OverflowError):
        raise EmbeddingError('Réponse OpenAI invalide (modèle, indices ou dimensions) ; lot non enregistré.') from None


def run_embeddings(settings, *, model=DEFAULT_MODEL, dimensions=None, revision='alias-v1',
                   batch_size=64, limit=None, dry_run=False, send=request_embeddings, progress=None):
    if model not in MODEL_DIMENSIONS:
        raise EmbeddingError('Modèle pris en charge : text-embedding-3-small ou text-embedding-3-large.')
    dimensions = MODEL_DIMENSIONS[model] if dimensions is None else dimensions
    if not 1 <= dimensions <= MODEL_DIMENSIONS[model] or not 1 <= batch_size <= 128 or (limit is not None and limit < 1):
        raise EmbeddingError('Dimensions, taille de lot ou limite invalides.')
    try:
        config = SemanticModelInput(model_key=f'openai/{model}/{revision}/{dimensions}', provider='openai',
                                    model_name=model, model_revision=revision, dimensions=dimensions).model_dump()
    except ValueError:
        raise EmbeddingError('Révision invalide ; utilisez lettres, chiffres, tirets et points.') from None
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
                if len(row[field].encode('utf-8')) > MAX_INPUT_BYTES:
                    oversized.append({'rule_key': row['rule_key'], 'field': field})
                else:
                    pending.append((row['rule_key'], row['content_hash'], field, row[field]))
    total_pending = len(pending)
    if limit is not None:
        pending = pending[:limit]
    result = {'model_key': key, 'model': model, 'dimensions': dimensions, 'dry_run': dry_run,
              'pending_vectors': total_pending, 'selected_vectors': len(pending), 'oversized_fields': oversized,
              'saved_vectors': 0, 'stale_vectors': 0, 'already_saved_vectors': 0, 'requests': 0, 'total_tokens': 0}
    if dry_run or not pending:
        return result
    if not settings.openai_api_key:
        raise EmbeddingError('OPENAI_API_KEY absente. Renseignez-la dans .env ou dans l’environnement, puis relancez.')
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
        response = send(settings.openai_api_key, [item[3] for item in batch], model, dimensions)
        vectors, tokens = validate_response(response, len(batch), model, dimensions)
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


if __name__ == '__main__':
    import sys
    from .cli import main
    sys.argv.insert(1, 'embed-openai')
    main()
