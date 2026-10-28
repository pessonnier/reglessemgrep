"""Versioned expert opinions, distinct from publisher metadata and test results."""

from __future__ import annotations

import sqlite3
import json

from .db import decode_rule


def rules_with_uncertainty(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[dict]:
    rules = [decode_rule(row) for row in rows]
    keys = [rule['rule_key'] for rule in rules if rule['source'] == 'Semgrep']
    assessments = {}
    if keys:
        marks = ','.join('?' for _ in keys)
        for row in conn.execute(
            f'SELECT u.*,a.code_examples_json FROM rule_uncertainty u LEFT JOIN uncertainty_assessments a '
            f'ON a.id=u.assessment_id WHERE u.rule_key IN ({marks})', keys
        ):
            item = dict(row)
            examples = json.loads(item.pop('code_examples_json') or '[]')
            item['code_examples'] = examples if item['status'] == 'expert_assessed' else []
            assessments[item['rule_key']] = item
    for rule in rules:
        rule['uncertainty'] = assessments.get(rule['rule_key'])
    return rules
