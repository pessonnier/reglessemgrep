"""Versioned expert opinions, distinct from publisher metadata and test results."""

from __future__ import annotations

import sqlite3

from .db import decode_rule


def rules_with_uncertainty(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    rules = [decode_rule(row) for row in rows]
    keys = [rule['rule_key'] for rule in rules if rule['source'] == 'Semgrep']
    assessments = {}
    if keys:
        marks = ','.join('?' for _ in keys)
        assessments = {row['rule_key']: dict(row) for row in conn.execute(
            f'SELECT * FROM rule_uncertainty WHERE rule_key IN ({marks})', keys
        )}
    for rule in rules:
        rule['uncertainty'] = assessments.get(rule['rule_key'])
    return rules
