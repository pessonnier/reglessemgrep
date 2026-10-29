"""Generate a Mermaid ER model from SQLite metadata, without reading records."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .db import initialize


def _rows(conn: sqlite3.Connection, sql: str) -> list[dict]:
    cursor = conn.execute(sql)
    cursor.row_factory = sqlite3.Row
    return [dict(row) for row in cursor.fetchall()]


def _quoted(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _text(value: str) -> str:
    # Mermaid comments/labels must not introduce syntax or HTML.
    return re.sub(r'["<>`\r\n]', "'", value)


def _names(names: list[str]) -> dict[str, str]:
    result, used = {}, set()
    for name in names:
        base = re.sub(r'[^A-Za-z0-9_]', '_', name)
        if not base or not base[0].isalpha():
            base = 'item_' + base
        candidate, suffix = base, 2
        while candidate in used:
            candidate = f'{base}_{suffix}'
            suffix += 1
        result[name] = candidate
        used.add(candidate)
    return result


def schema_mermaid(conn: sqlite3.Connection, *, include_views: bool = True) -> str:
    """Inspect schema only. Stable ordering makes generated files suitable for Git."""
    entities = _rows(conn, "SELECT name,type FROM sqlite_schema WHERE type IN ('table','view') "
                           "AND name NOT LIKE 'sqlite_%' ORDER BY name")
    entities = [e for e in entities if include_views or e['type'] == 'table']
    identifiers = _names([e['name'] for e in entities])
    columns = {e['name']: _rows(conn, f'PRAGMA table_xinfo({_quoted(e["name"])})') for e in entities}
    lines = ['erDiagram', f'    %% SQLite schema version {conn.execute("PRAGMA user_version").fetchone()[0]}',
             '    %% Generated from metadata only; no records or inferred view dependencies.']
    relations = []
    for entity in entities:
        name = entity['name']
        fields = columns[name]
        field_ids = _names([c['name'] for c in fields])
        pk = [c['name'] for c in sorted(fields, key=lambda c: c['pk']) if c['pk']]
        foreign_keys = {}
        for fk in _rows(conn, f'PRAGMA foreign_key_list({_quoted(name)})'):
            foreign_keys.setdefault(fk['id'], []).append(fk)
        fk_columns = {fk['from'] for group in foreign_keys.values() for fk in group}
        unique_sets = [set(pk)] if pk else []
        indexes = _rows(conn, f'PRAGMA index_list({_quoted(name)})')
        for index in indexes:
            if index['unique'] and not index['partial']:
                members = _rows(conn, f'PRAGMA index_info({_quoted(index["name"])})')
                if members and all(c['name'] is not None for c in members):
                    unique_sets.append({c['name'] for c in members})
        implicit_pk = {c['name'] for c in fields if c['pk'] and (
            len(pk) == 1 and c['type'].upper() == 'INTEGER' and not any(i['origin'] == 'pk' for i in indexes))}
        required_columns = {c['name'] for c in fields if c['notnull']} | implicit_pk
        lines.append(f'    %% {entity["type"]}: {_text(name)}')
        lines.append(f'    {identifiers[name]} {{')
        for column in fields:
            cname = column['name']
            keys = (['PK'] if column['pk'] else []) + (['FK'] if cname in fk_columns else [])
            if {cname} in unique_sets and not column['pk']:
                keys.append('UK')
            declared_type = column['type'] or 'UNKNOWN'
            type_id = _names([declared_type])[declared_type]
            notes = []
            if entity['type'] == 'view':
                notes.append('VIEW - derived column')
            else:
                notes.append('NOT NULL' if cname in required_columns else 'NULL allowed')
            if cname != field_ids[cname]:
                notes.append('SQL name: ' + cname)
            if declared_type != type_id:
                notes.append('SQL type: ' + declared_type)
            if column['hidden']:
                notes.append('generated or hidden')
            key_text = ' ' + ', '.join(keys) if keys else ''
            lines.append(f'        {type_id} {field_ids[cname]}{key_text} "{_text("; ".join(notes))}"')
        lines.append('    }')
        for group in foreign_keys.values():
            group.sort(key=lambda fk: fk['seq'])
            parent = group[0]['table']
            if parent not in identifiers:
                continue
            child_keys = {fk['from'] for fk in group}
            parent_pk = [c['name'] for c in sorted(columns[parent], key=lambda c: c['pk']) if c['pk']]
            targets = [fk['to'] or (parent_pk[i] if i < len(parent_pk) else '?') for i, fk in enumerate(group)]
            required = child_keys <= required_columns
            left = '||' if required else '|o'
            right = 'o|' if any(u <= child_keys for u in unique_sets) else 'o{'
            line = '--' if child_keys <= set(pk) else '..'
            label = ', '.join(fk['from'] for fk in group) + ' → ' + ', '.join(targets)
            relations.append(f'    {identifiers[parent]} {left}{line}{right} {identifiers[name]} : "{_text(label)}"')
    lines.extend(sorted(relations))
    return '\n'.join(lines) + '\n'


def generate_schema(*, database: Path | None = None, include_views: bool = True, markdown: bool = False) -> str:
    """Read an existing DB in read-only mode, or build an empty model from migrations."""
    if database is None:
        conn = sqlite3.connect(':memory:')
    else:
        conn = sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if database is None:
            initialize(conn)
        diagram = schema_mermaid(conn, include_views=include_views)
    finally:
        conn.close()
    if not markdown:
        return diagram
    return ('# Modèle de la base de données\n\n'
            'Diagramme généré à partir du schéma SQLite. PK : clé primaire ; FK : clé étrangère ; '
            'UK : unicité sur une colonne. Les clés composites restent groupées dans les relations. '
            'Les vues sont indiquées par VIEW et leurs dépendances ne sont pas inférées.\n\n'
            '```mermaid\n' + diagram + '```\n')
