"""Embedding model registry and validated vector ingestion for local clients."""
from __future__ import annotations

import json
import math
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator

from .db import connect, initialize, utc_now
from .semantic import sync_documents, text_hash, semantic_status


class SemanticModelInput(BaseModel):
    model_key: str = Field(min_length=1, max_length=160, pattern=r'^[A-Za-z0-9][A-Za-z0-9_.:/-]*$')
    provider: str = Field(min_length=1, max_length=120)
    model_name: str = Field(min_length=1, max_length=200)
    model_revision: str = Field(min_length=1, max_length=160)
    dimensions: int = Field(ge=1, le=16384, strict=True)
    preprocessing: Literal['raw-text-v1'] = 'raw-text-v1'

    @field_validator('provider', 'model_name', 'model_revision')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Le champ ne peut pas être vide.')
        return value.strip()


class SemanticEmbeddingInput(BaseModel):
    rule_key: str = Field(min_length=1)
    model_key: str = Field(min_length=1)
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    title_vector: list[float] | None = Field(default=None, min_length=1, max_length=16384)
    description_vector: list[float] | None = Field(default=None, min_length=1, max_length=16384)

    @field_validator('title_vector', 'description_vector', mode='before')
    @classmethod
    def valid_vector(cls, value):
        if value is None:
            return value
        if not isinstance(value, list) or any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in value):
            raise ValueError('Un vecteur doit être une liste de nombres.')
        try:
            finite = all(math.isfinite(x) for x in value)
        except OverflowError:
            finite = False
        if not finite or not any(x != 0 for x in value):
            raise ValueError('Le vecteur doit être fini et non nul.')
        return value

    @model_validator(mode='after')
    def at_least_one_vector(self):
        if self.title_vector is None and self.description_vector is None:
            raise ValueError('Fournir au moins un vecteur de titre ou de description.')
        return self


def decode_embedding(row):
    result = dict(row)
    for field in ('title', 'description'):
        raw = result.pop(f'{field}_vector_json')
        result[f'{field}_vector'] = json.loads(raw) if raw is not None else None
    if 'is_current' in result:
        result['is_current'] = bool(result['is_current'])
    return result


def semantic_router(settings_provider) -> APIRouter:
    router = APIRouter(prefix='/api/semantic', tags=['Semantic'])

    @router.get('/status')
    def status():
        with connect(settings_provider().db_path) as conn:
            initialize(conn)
            return semantic_status(conn)

    @router.get('/models')
    def models():
        with connect(settings_provider().db_path) as conn:
            initialize(conn)
            return {'items': [dict(r) for r in conn.execute('SELECT * FROM semantic_models ORDER BY model_key')]}

    @router.post('/models')
    def register_model(payload: SemanticModelInput):
        """Idempotent registry. Model identity, dimensions and preprocessing are immutable."""
        data = payload.model_dump()
        with connect(settings_provider().db_path) as conn:
            initialize(conn)
            conn.execute('BEGIN IMMEDIATE')
            previous = conn.execute('SELECT * FROM semantic_models WHERE model_key=?', (payload.model_key,)).fetchone()
            if previous:
                if any(previous[key] != value for key, value in data.items()):
                    raise HTTPException(409, 'Cette clé désigne déjà un autre modèle ou une autre configuration. Utilisez une nouvelle clé.')
                return dict(previous)
            data['created_at'] = utc_now()
            try:
                conn.execute(f'INSERT INTO semantic_models({",".join(data)}) VALUES({",".join("?" for _ in data)})', tuple(data.values()))
            except sqlite3.IntegrityError:
                raise HTTPException(409, 'Cette configuration est déjà enregistrée sous une autre clé.') from None
        return data

    @router.get('/documents')
    def documents(source: Literal['', 'CAST', 'Semgrep'] = '', model_key: str = '',
                  status: Literal['', 'pending', 'partial', 'complete', 'stale', 'not_applicable'] = '',
                  rule_key: str = '', page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
        """Exact current text to embed, with optimistic-lock content_hash and optional model coverage."""
        if status and not model_key:
            raise HTTPException(422, 'Le filtre de couverture nécessite model_key.')
        with connect(settings_provider().db_path) as conn:
            initialize(conn)
            if model_key and not conn.execute('SELECT 1 FROM semantic_models WHERE model_key=?', (model_key,)).fetchone():
                raise HTTPException(404, 'Modèle inconnu.')
            where, values = ['1=1'], []
            join, extra = '', ''
            if model_key:
                join = ' JOIN semantic_coverage cov ON cov.rule_key=d.rule_key AND cov.content_hash=d.content_hash'
                extra = ',cov.status'
                where.append('cov.model_key=?'); values.append(model_key)
            for column, value in [('d.source', source), ('d.rule_key', rule_key), ('cov.status', status)]:
                if value:
                    where.append(f'{column}=?'); values.append(value)
            base = ' FROM semantic_current_documents d' + join + ' WHERE ' + ' AND '.join(where)
            total = conn.execute('SELECT COUNT(*)' + base, values).fetchone()[0]
            items = [dict(r) for r in conn.execute('SELECT d.*' + extra + base + ' ORDER BY d.rule_key LIMIT ? OFFSET ?',
                                                  [*values, page_size, (page-1)*page_size])]
        return {'total': total, 'page': page, 'page_size': page_size, 'items': items}

    @router.put('/embeddings')
    def put_embedding(payload: SemanticEmbeddingInput):
        """Append missing fields idempotently; reject stale text and conflicting replacement vectors."""
        with connect(settings_provider().db_path) as conn:
            initialize(conn)
            conn.execute('BEGIN IMMEDIATE')
            model = conn.execute('SELECT * FROM semantic_models WHERE model_key=?', (payload.model_key,)).fetchone()
            rule = conn.execute('SELECT * FROM rules WHERE rule_key=?', (payload.rule_key,)).fetchone()
            if model is None or rule is None:
                raise HTTPException(404, 'Règle ou modèle inconnu.')
            title, description = rule['title'] or '', rule['description'] or ''
            if rule['status'] != 'present' or payload.content_hash != text_hash(title, description):
                raise HTTPException(409, 'Le texte de la règle a changé ou la règle est retirée. Relisez le document.')
            for field, text in [('title', title), ('description', description)]:
                vector = getattr(payload, field + '_vector')
                if vector is not None and (len(vector) != model['dimensions'] or not text.strip()):
                    raise HTTPException(422, 'Dimension incompatible avec le modèle ou texte source vide.')
            sync_documents(conn, [payload.rule_key])
            key = (payload.rule_key, payload.content_hash, payload.model_key)
            previous = conn.execute('SELECT * FROM semantic_embeddings WHERE rule_key=? AND content_hash=? AND model_key=?', key).fetchone()
            vectors = []
            changed = previous is None
            for field in ('title', 'description'):
                incoming = getattr(payload, field + '_vector')
                old = previous[field + '_vector_json'] if previous else None
                if old is not None and incoming is not None and json.loads(old) != incoming:
                    raise HTTPException(409, 'Un vecteur différent existe déjà pour ce texte et ce modèle. Enregistrez une nouvelle révision du modèle.')
                changed |= old is None and incoming is not None
                vectors.append(old if old is not None else json.dumps(incoming, allow_nan=False) if incoming is not None else None)
            if changed:
                now = utc_now()
                conn.execute('''INSERT INTO semantic_embeddings(rule_key,content_hash,model_key,title_vector_json,description_vector_json,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?) ON CONFLICT(rule_key,content_hash,model_key) DO UPDATE SET
                  title_vector_json=excluded.title_vector_json,description_vector_json=excluded.description_vector_json,updated_at=excluded.updated_at''',
                  (*key, *vectors, now, now))
            return decode_embedding(conn.execute('SELECT * FROM semantic_embeddings WHERE rule_key=? AND content_hash=? AND model_key=?', key).fetchone())

    @router.get('/embeddings')
    def embeddings(rule_key: str, model_key: str = '', history: bool = False,
                   page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100)):
        with connect(settings_provider().db_path) as conn:
            initialize(conn)
            if not conn.execute('SELECT 1 FROM rules WHERE rule_key=?', (rule_key,)).fetchone():
                raise HTTPException(404, 'Règle inconnue.')
            where, values = ['e.rule_key=?'], [rule_key]
            if model_key:
                where.append('e.model_key=?'); values.append(model_key)
            if not history:
                where.append('d.rule_key IS NOT NULL')
            base = ''' FROM semantic_embeddings e LEFT JOIN semantic_current_documents d
                ON d.rule_key=e.rule_key AND d.content_hash=e.content_hash WHERE ''' + ' AND '.join(where)
            total = conn.execute('SELECT COUNT(*)' + base, values).fetchone()[0]
            items = [decode_embedding(r) for r in conn.execute('SELECT e.*,d.rule_key IS NOT NULL AS is_current' + base +
                ' ORDER BY e.created_at DESC,e.model_key,e.content_hash LIMIT ? OFFSET ?', [*values, page_size, (page-1)*page_size])]
        return {'total': total, 'page': page, 'page_size': page_size, 'items': items}

    return router
